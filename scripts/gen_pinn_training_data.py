"""Generate PINN training data by sampling thickness / roughness from stack bounds.

For every JSON file in data/stacks/ the script:
  1. Parses all layers regardless of schema version (slab-v1 or Aiden's
     wrapped-BoundedValue format).
  2. Identifies film layers (those without a role / with role absent or null).
  3. Draws *N_SAMPLES* independent samples of (thickness, roughness) per film
     layer from a uniform distribution over [min, max]; falls back to the
     nominal value when bounds are absent.
  4. Runs the Parratt XRR simulation for each sample.
  5. Saves one compressed NPZ per source stack plus a manifest CSV.

Outputs
-------
  data/pinn_training/<stack_id>.npz
      keys: Q (500,), R_matrix (N×500), thickness_matrix (N×n_layers),
            roughness_matrix (N×n_layers), sld (n_layers,), labels (n_layers,)
  data/pinn_training/manifest.csv
      one row per (stack, sample) with stack_id, sample_idx, npz_file,
      n_layers, layer_labels (JSON list).

Usage::

    python scripts/gen_pinn_training_data.py
    python scripts/gen_pinn_training_data.py --stacks-dir data/stacks \\
        --out-dir data/pinn_training --n-samples 50 --seed 42
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
from pathlib import Path

import numpy as np

# Parratt recursion from the project's simulation module.
from materials_db.simulation.xrr import parratt

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Defaults ───────────────────────────────────────────────────────────────────

_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_STACKS = _ROOT / "data" / "stacks"
_DEFAULT_OUT    = _ROOT / "data" / "pinn_training"
_N_SAMPLES      = 50
_SEED           = 42
_Q              = np.linspace(0.01, 0.60, 500)   # Å⁻¹, matches verify_all.py
_DEFAULT_ROUGH  = 3.0                              # Å fallback roughness


# ── Schema-agnostic field extractors ──────────────────────────────────────────

def _scalar(field) -> float | None:
    """Return a plain float from either a bare number or a {value:...} dict."""
    if field is None:
        return None
    if isinstance(field, dict):
        v = field.get("value")
        return float(v) if v is not None else None
    try:
        return float(field)
    except (TypeError, ValueError):
        return None


def _bounds(field) -> tuple[float | None, float | None, float | None]:
    """Return (value, lo, hi) from a bare number or {value, min, max} dict."""
    if isinstance(field, dict):
        val = _scalar(field.get("value"))
        lo  = _scalar(field.get("min"))
        hi  = _scalar(field.get("max"))
        return val, lo, hi
    v = _scalar(field)
    return v, None, None


# ── Layer extraction ──────────────────────────────────────────────────────────

def _extract_layers(stack_data: dict) -> list[dict]:
    """Return a normalised layer list from any supported stack JSON format.

    Each element contains:
        label, role, sld, thickness_val/lo/hi, roughness_val/lo/hi
    """
    layers: list[dict] = []
    for layer in stack_data.get("stack", []):
        role  = layer.get("role")        # "ambient" | "substrate" | None
        label = layer.get("label", "?")

        # SLD — both formats place it at scattering.sld_real
        scat     = layer.get("scattering") or {}
        sld_raw  = scat.get("sld_real")
        sld      = _scalar(sld_raw) or 0.0

        # Thickness and roughness
        struct = layer.get("structural") or {}
        t_val, t_lo, t_hi = _bounds(struct.get("thickness"))
        r_val, r_lo, r_hi = _bounds(struct.get("roughness"))

        layers.append({
            "label":         label,
            "role":          role,
            "sld":           float(sld),
            "thickness_val": t_val,
            "thickness_lo":  t_lo,
            "thickness_hi":  t_hi,
            "roughness_val": r_val,
            "roughness_lo":  r_lo,
            "roughness_hi":  r_hi,
        })
    return layers


# ── Sampling ──────────────────────────────────────────────────────────────────

def _sample_uniform(val: float | None, lo: float | None, hi: float | None,
                    rng: np.random.Generator, default: float = 0.0) -> float:
    """Sample from [lo, hi] if both are finite and lo < hi, else return val."""
    if lo is not None and hi is not None and hi > lo:
        return float(rng.uniform(lo, hi))
    return float(val) if val is not None else default


def _generate_samples(
    layers: list[dict],
    n_samples: int,
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray]:
    """Return (thickness_matrix, roughness_matrix), each shape (n_samples, n_layers).

    Ambient and substrate layers are assigned thickness 0 (semi-infinite).
    Roughness defaults to _DEFAULT_ROUGH when no information is present.
    """
    n = len(layers)
    t_mat   = np.zeros((n_samples, n), dtype=np.float64)
    sig_mat = np.full((n_samples, n), _DEFAULT_ROUGH, dtype=np.float64)

    for i, lyr in enumerate(layers):
        is_film = lyr["role"] is None
        for s in range(n_samples):
            if is_film:
                t_mat[s, i] = _sample_uniform(
                    lyr["thickness_val"],
                    lyr["thickness_lo"],
                    lyr["thickness_hi"],
                    rng,
                    default=0.0,
                )
            sig_mat[s, i] = _sample_uniform(
                lyr["roughness_val"],
                lyr["roughness_lo"],
                lyr["roughness_hi"],
                rng,
                default=_DEFAULT_ROUGH,
            )

    return t_mat, sig_mat


# ── Per-stack processing ──────────────────────────────────────────────────────

def _process_stack(
    json_path: Path,
    out_dir: Path,
    n_samples: int,
    rng: np.random.Generator,
) -> list[dict]:
    """Simulate *n_samples* XRR curves for one stack file.

    Writes a compressed NPZ and returns a list of manifest-row dicts.
    Returns an empty list when the file has no usable film layers.
    """
    raw = json.loads(json_path.read_text(encoding="utf-8"))
    stack_id = raw.get("stack_id", json_path.stem)
    layers   = _extract_layers(raw)

    film_count = sum(1 for l in layers if l["role"] is None)
    if film_count == 0:
        log.warning("%s: no film layers found — skipping", json_path.name)
        return []

    n_lyr   = len(layers)
    sld_arr = np.array([l["sld"] for l in layers], dtype=np.float64)
    labels  = [l["label"] for l in layers]

    t_mat, sig_mat = _generate_samples(layers, n_samples, rng)

    R_mat = np.empty((n_samples, len(_Q)), dtype=np.float64)
    for s in range(n_samples):
        R_mat[s] = parratt(_Q, sld_arr, t_mat[s], sig_mat[s])

    # ── Atomic write ──────────────────────────────────────────────────────────
    # np.savez_compressed appends .npz automatically when the path doesn't end
    # in .npz.  Use a stem-only tmp so numpy names the file _tmp_<id>.npz,
    # then rename atomically to the final path.
    out_path  = out_dir / f"{stack_id}.npz"
    tmp_stem  = out_dir / f"_tmp_{stack_id}"   # no .npz — numpy will add it
    tmp_actual = out_dir / f"_tmp_{stack_id}.npz"
    np.savez_compressed(
        tmp_stem,
        Q=_Q,
        R_matrix=R_mat,
        thickness_matrix=t_mat,
        roughness_matrix=sig_mat,
        sld=sld_arr,
        labels=np.array(labels, dtype=object),
    )
    os.replace(tmp_actual, out_path)
    log.info(
        "%-50s  %2d layers  %d samples → %s",
        json_path.name, n_lyr, n_samples, out_path.name,
    )

    return [
        {
            "stack_id":     stack_id,
            "sample_idx":   s,
            "npz_file":     out_path.name,
            "n_layers":     n_lyr,
            "layer_labels": json.dumps(labels),
        }
        for s in range(n_samples)
    ]


# ── Manifest writer ───────────────────────────────────────────────────────────

def _write_manifest(rows: list[dict], out_dir: Path) -> None:
    if not rows:
        return
    manifest_path = out_dir / "manifest.csv"
    tmp_path = manifest_path.with_suffix(".csv.tmp")
    fieldnames = ["stack_id", "sample_idx", "npz_file", "n_layers", "layer_labels"]
    with open(tmp_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp_path, manifest_path)
    log.info("Manifest → %s  (%d rows)", manifest_path.name, len(rows))


# ── Entry point ───────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python scripts/gen_pinn_training_data.py",
        description="Sample XRR training curves from stack JSON files.",
    )
    parser.add_argument(
        "--stacks-dir", type=Path, default=_DEFAULT_STACKS,
        metavar="DIR", help="Directory containing stack JSON files",
    )
    parser.add_argument(
        "--out-dir", type=Path, default=_DEFAULT_OUT,
        metavar="DIR", help="Output directory for NPZ files and manifest",
    )
    parser.add_argument(
        "--n-samples", type=int, default=_N_SAMPLES,
        metavar="N", help="Number of random (thickness, roughness) samples per stack",
    )
    parser.add_argument(
        "--seed", type=int, default=_SEED,
        help="Random seed for reproducibility",
    )
    args = parser.parse_args(argv)

    stacks_dir: Path = args.stacks_dir
    out_dir:    Path = args.out_dir
    n_samples:  int  = args.n_samples

    if not stacks_dir.exists():
        log.error("Stacks directory not found: %s", stacks_dir)
        raise SystemExit(1)

    out_dir.mkdir(parents=True, exist_ok=True)

    json_files = sorted(stacks_dir.glob("*.json"))
    if not json_files:
        log.warning("No JSON files in %s", stacks_dir)
        return

    log.info(
        "Processing %d stack file(s) — %d samples each (seed=%d)",
        len(json_files), n_samples, args.seed,
    )
    rng = np.random.default_rng(seed=args.seed)

    all_rows: list[dict] = []
    for jf in json_files:
        try:
            rows = _process_stack(jf, out_dir, n_samples, rng)
            all_rows.extend(rows)
        except Exception as exc:
            log.error("Failed to process %s: %s", jf.name, exc)

    _write_manifest(all_rows, out_dir)

    total_curves = len(all_rows)
    log.info(
        "Done — %d training curves from %d stack(s) in %s",
        total_curves, len(json_files), out_dir,
    )


if __name__ == "__main__":
    main()
