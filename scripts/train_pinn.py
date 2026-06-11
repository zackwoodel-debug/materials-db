"""Train a Physics-Informed Neural Network on optical NK and XRR reflectivity data.

Dataset 1 — optical NK:
    Source : optical_nk JOIN materials in materials.db
    Input  : [wavelength_nm (normalised), material one-hot]
    Output : [n, k]
    Physics: n > 1.0 for dielectrics; k >= 0 for all materials

Dataset 2 — XRR reflectivity:
    Source : data/xrr_simulation_output.csv (single Parratt simulation)
    Input  : [q (normalised), stack encoding (SLD × 1e5, thickness / 300) per layer]
    Output : [log10(R)]

Architecture: two separate PINN instances (same class), each 4 × 128 hidden layers.
Training    : 1000 epochs, Adam lr=1e-3, 80/20 split, checkpoint every 100 epochs.
"""

import csv
import logging
import sqlite3
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset, random_split

# ── Paths ──────────────────────────────────────────────────────────────────────
_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = _ROOT / "data" / "materials.db"
XRR_CSV = _ROOT / "data" / "xrr_simulation_output.csv"
MODELS_DIR = _ROOT / "models"

# ── Hyperparameters ────────────────────────────────────────────────────────────
HIDDEN_DIM = 128
NUM_HIDDEN = 4
EPOCHS = 1000
LR = 1e-3
CHECKPOINT_INTERVAL = 100
VAL_FRACTION = 0.20
BATCH_SIZE = 256
PHYSICS_WEIGHT = 0.1

# Material classes where n > 1.0 is physically required.
DIELECTRIC_CLASSES = frozenset({"biological", "oxide", "polymer", "semiconductor", "solvent"})

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Device ─────────────────────────────────────────────────────────────────────
device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")


# ── Data loaders ───────────────────────────────────────────────────────────────

def load_nk_data(db_path: Path) -> tuple:
    """Return (X, y_n, y_k, diel_mask, num_mats, wl_min, wl_max).

    X shape: (N, 1 + num_materials)  — [wl_norm, one_hot...]
    y_n / y_k shape: (N,)
    diel_mask shape: (N,) — 1.0 for dielectric materials, 0.0 for metals
    """
    conn = sqlite3.connect(db_path)
    rows = conn.execute("""
        SELECT m.id, m.material_class, o.wavelength_nm,
               o.n, COALESCE(o.k, 0.0)
        FROM optical_nk o
        JOIN materials m ON o.material_id = m.id
        WHERE o.n IS NOT NULL
        ORDER BY m.id, o.wavelength_nm
    """).fetchall()
    conn.close()

    mat_ids = sorted({r[0] for r in rows})
    id_to_idx = {mid: i for i, mid in enumerate(mat_ids)}
    num_mats = len(mat_ids)

    wl_list, oh_list, n_list, k_list, diel_list = [], [], [], [], []
    for mat_id, mat_cls, wl, n, k in rows:
        oh = np.zeros(num_mats, dtype=np.float32)
        oh[id_to_idx[mat_id]] = 1.0
        wl_list.append(wl)
        oh_list.append(oh)
        n_list.append(float(n))
        k_list.append(float(k))
        diel_list.append(1.0 if mat_cls in DIELECTRIC_CLASSES else 0.0)

    wl_arr = np.array(wl_list, dtype=np.float32)
    wl_min, wl_max = float(wl_arr.min()), float(wl_arr.max())
    wl_norm = (wl_arr - wl_min) / (wl_max - wl_min + 1e-8)

    X = np.concatenate([wl_norm[:, None], np.stack(oh_list)], axis=1)
    return (
        X,
        np.array(n_list, dtype=np.float32),
        np.array(k_list, dtype=np.float32),
        np.array(diel_list, dtype=np.float32),
        num_mats,
        wl_min,
        wl_max,
    )


def _query_stack_slds(db_path: Path) -> dict[str, float]:
    """Fetch x-ray SLD (Å⁻²) for the default stack materials from calculated_sld."""
    conn = sqlite3.connect(db_path)
    rows = conn.execute("""
        SELECT m.name, AVG(cs.sld_xray_real)
        FROM calculated_sld cs
        JOIN materials m ON cs.material_id = m.id
        WHERE m.name IN ('PMMA', 'Gold', 'Silicon')
        GROUP BY m.name
    """).fetchall()
    conn.close()
    return {name: float(sld) for name, sld in rows}


def build_xrr_stack_encoding(db_path: Path) -> list[float]:
    """Return a flat, normalised feature vector for Vacuum | PMMA:120Å | Gold:250Å | Silicon.

    Each layer contributes two features: SLD scaled by ×1e5 (brings ~1 range),
    and thickness divided by 300 (brings ~[0, 1] range).  Semi-infinite layers
    have thickness 0.
    """
    sld = _query_stack_slds(db_path)
    layers = [
        (0.0,                             0.0),    # Vacuum superstrate (semi-inf)
        (sld.get("PMMA",    1.089e-5), 120.0),     # PMMA film
        (sld.get("Gold",    1.315e-4), 250.0),     # Gold film
        (sld.get("Silicon", 1.970e-5),   0.0),     # Silicon substrate (semi-inf)
    ]
    flat: list[float] = []
    for sld_val, thick in layers:
        flat.append(sld_val * 1e5)    # scale SLD
        flat.append(thick / 300.0)    # scale thickness
    return flat


def load_xrr_data(csv_path: Path, stack_enc: list[float]) -> tuple:
    """Return (X, y_log_r, q_min, q_max).

    X shape: (M, 1 + len(stack_enc))  — [q_norm, stack_encoding...]
    y_log_r shape: (M, 1)             — log10(R)
    """
    q_list: list[float] = []
    r_list: list[float] = []
    with open(csv_path, newline="") as f:
        for row in csv.DictReader(f):
            q_list.append(float(row["q (1/Ang)"]))
            r_list.append(float(row["Reflectivity"]))

    q = np.array(q_list, dtype=np.float32)
    r = np.array(r_list, dtype=np.float32)
    q_min, q_max = float(q.min()), float(q.max())
    q_norm = (q - q_min) / (q_max - q_min + 1e-8)

    # log10(R) is smoother to fit: R spans ~5 decades in real experiments.
    r_log = np.log10(r + 1e-15).astype(np.float32)

    enc = np.array(stack_enc, dtype=np.float32)
    X = np.concatenate([q_norm[:, None], np.tile(enc, (len(q_norm), 1))], axis=1)
    return X, r_log[:, None], q_min, q_max


# ── Model ──────────────────────────────────────────────────────────────────────

class PINN(nn.Module):
    """MLP with 4 hidden layers of 128 neurons each."""

    def __init__(self, input_dim: int, output_dim: int) -> None:
        super().__init__()
        layers: list[nn.Module] = [nn.Linear(input_dim, HIDDEN_DIM), nn.ReLU()]
        for _ in range(NUM_HIDDEN - 1):
            layers += [nn.Linear(HIDDEN_DIM, HIDDEN_DIM), nn.ReLU()]
        layers.append(nn.Linear(HIDDEN_DIM, output_dim))
        self.net = nn.Sequential(*layers)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


# ── Physics loss ───────────────────────────────────────────────────────────────

def physics_loss_nk(
    n_pred: torch.Tensor,
    k_pred: torch.Tensor,
    is_dielectric: torch.Tensor,
) -> torch.Tensor:
    """Return combined physics penalty for optical constant predictions.

    Constraint 1: n > 1.0 for dielectrics — below-vacuum phase velocity
                  violates causality for passive media with no gain.
    Constraint 2: k >= 0 for all materials — negative extinction implies
                  optical gain, which requires external pumping.
    """
    # Squeeze last dim: (B, 1) → (B,)
    n_sq = n_pred.squeeze(-1)
    k_sq = k_pred.squeeze(-1)

    n_violation = torch.clamp(1.0 - n_sq, min=0.0)
    n_loss = (is_dielectric * n_violation).mean()

    k_loss = torch.clamp(-k_sq, min=0.0).mean()

    return n_loss + k_loss


# ── Dataset utilities ──────────────────────────────────────────────────────────

def make_loaders(
    X: np.ndarray,
    *targets: np.ndarray,
    batch_size: int = BATCH_SIZE,
) -> tuple[DataLoader, DataLoader]:
    """80/20 random split → (train_loader, val_loader)."""
    tensors = [torch.tensor(X)] + [torch.tensor(t) for t in targets]
    ds = TensorDataset(*tensors)
    n_val = max(1, int(len(ds) * VAL_FRACTION))
    n_train = len(ds) - n_val
    train_ds, val_ds = random_split(
        ds, [n_train, n_val],
        generator=torch.Generator().manual_seed(42),
    )
    return (
        DataLoader(train_ds, batch_size=batch_size, shuffle=True,  drop_last=False),
        DataLoader(val_ds,   batch_size=batch_size, shuffle=False, drop_last=False),
    )


def save_checkpoint(
    model_nk: PINN, model_xrr: PINN, epoch: int, path: Path
) -> None:
    torch.save(
        {
            "epoch":     epoch,
            "nk_state":  model_nk.state_dict(),
            "xrr_state": model_xrr.state_dict(),
        },
        path,
    )
    log.info("Checkpoint saved → %s", path.name)


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    MODELS_DIR.mkdir(exist_ok=True)
    log.info("Device: %s", device)

    # ── NK dataset ─────────────────────────────────────────────────────────────
    log.info("Loading optical NK data from %s", DB_PATH)
    X_nk, y_n, y_k, diel, num_mats, wl_min, wl_max = load_nk_data(DB_PATH)
    log.info(
        "NK dataset: %d rows, %d materials, wavelength %.0f–%.0f nm",
        len(X_nk), num_mats, wl_min, wl_max,
    )

    # ── XRR dataset ────────────────────────────────────────────────────────────
    stack_enc = build_xrr_stack_encoding(DB_PATH)
    log.info(
        "XRR stack encoding (%d features): %s",
        len(stack_enc),
        ", ".join(f"{v:.4f}" for v in stack_enc),
    )
    X_xrr, y_r, q_min, q_max = load_xrr_data(XRR_CSV, stack_enc)
    log.info("XRR dataset: %d rows, q %.4f–%.4f Å⁻¹", len(X_xrr), q_min, q_max)
    if len(X_xrr) < 20:
        log.warning(
            "XRR dataset has only %d rows — model will memorise the single simulated curve",
            len(X_xrr),
        )

    # ── Data loaders ───────────────────────────────────────────────────────────
    y_nk = np.stack([y_n, y_k], axis=1)           # (N, 2)
    train_nk,  val_nk  = make_loaders(X_nk,  y_nk, diel)
    train_xrr, val_xrr = make_loaders(
        X_xrr, y_r, batch_size=max(1, len(X_xrr))
    )

    # ── Models ─────────────────────────────────────────────────────────────────
    nk_in  = X_nk.shape[1]   # 1 (wl_norm) + num_mats
    xrr_in = X_xrr.shape[1]  # 1 (q_norm)  + len(stack_enc)

    model_nk  = PINN(nk_in,  2).to(device)
    model_xrr = PINN(xrr_in, 1).to(device)
    log.info(
        "NK model  input_dim=%d, output_dim=2  |  "
        "XRR model input_dim=%d, output_dim=1",
        nk_in, xrr_in,
    )

    opt_nk  = torch.optim.Adam(model_nk.parameters(),  lr=LR)
    opt_xrr = torch.optim.Adam(model_xrr.parameters(), lr=LR)
    mse = nn.MSELoss()

    best_val_nk = float("inf")
    log_rows: list[dict] = []

    # ── Training loop ──────────────────────────────────────────────────────────
    for epoch in range(1, EPOCHS + 1):
        model_nk.train()
        model_xrr.train()
        running_loss = 0.0
        n_steps = 0

        # NK batches — data loss + physics penalty
        for batch in train_nk:
            Xb, yb, db = (t.to(device) for t in batch)
            pred = model_nk(Xb)                                   # (B, 2)
            data_loss = mse(pred, yb)
            phys_loss = physics_loss_nk(pred[:, 0:1], pred[:, 1:2], db)
            loss = data_loss + PHYSICS_WEIGHT * phys_loss
            opt_nk.zero_grad()
            loss.backward()
            opt_nk.step()
            running_loss += loss.item()
            n_steps += 1

        # XRR batches — data loss only
        for batch in train_xrr:
            Xb, yb = (t.to(device) for t in batch)
            pred = model_xrr(Xb)                                  # (B, 1)
            loss = mse(pred, yb)
            opt_xrr.zero_grad()
            loss.backward()
            opt_xrr.step()
            running_loss += loss.item()
            n_steps += 1

        train_loss = running_loss / max(n_steps, 1)

        # ── Validation ─────────────────────────────────────────────────────────
        model_nk.eval()
        model_xrr.eval()
        nk_mse_list: list[float] = []
        err_n: list[torch.Tensor] = []
        err_k: list[torch.Tensor] = []
        xrr_mse_list: list[float] = []

        with torch.no_grad():
            for batch in val_nk:
                Xb, yb, _ = (t.to(device) for t in batch)
                pred = model_nk(Xb)
                nk_mse_list.append(mse(pred, yb).item())
                err_n.append((pred[:, 0] - yb[:, 0]).abs().cpu())
                err_k.append((pred[:, 1] - yb[:, 1]).abs().cpu())

            for batch in val_xrr:
                Xb, yb = (t.to(device) for t in batch)
                xrr_mse_list.append(mse(model_xrr(Xb), yb).item())

        val_nk_loss  = float(np.mean(nk_mse_list))  if nk_mse_list  else float("nan")
        mae_n        = torch.cat(err_n).mean().item() if err_n       else float("nan")
        mae_k        = torch.cat(err_k).mean().item() if err_k       else float("nan")
        val_xrr_loss = float(np.mean(xrr_mse_list)) if xrr_mse_list else float("nan")

        log_rows.append({
            "epoch":        epoch,
            "train_loss":   train_loss,
            "val_loss_nk":  val_nk_loss,
            "val_mae_n":    mae_n,
            "val_mae_k":    mae_k,
            "val_loss_xrr": val_xrr_loss,
        })

        if epoch % 100 == 0 or epoch == 1:
            log.info(
                "Epoch %4d | train=%.6f  val_nk=%.6f  "
                "mae_n=%.5f  mae_k=%.5f  val_xrr=%.4f",
                epoch, train_loss, val_nk_loss, mae_n, mae_k, val_xrr_loss,
            )

        # ── Periodic checkpoint ─────────────────────────────────────────────────
        if epoch % CHECKPOINT_INTERVAL == 0:
            save_checkpoint(
                model_nk, model_xrr, epoch,
                MODELS_DIR / f"pinn_checkpoint_epoch{epoch}.pt",
            )

        # ── Best model (lowest val NK MSE) ─────────────────────────────────────
        if val_nk_loss < best_val_nk:
            best_val_nk = val_nk_loss
            torch.save(
                {
                    "epoch":      epoch,
                    "val_loss_nk": best_val_nk,
                    "nk_state":   model_nk.state_dict(),
                    "xrr_state":  model_xrr.state_dict(),
                    # Normalisation params needed for inference
                    "wl_min":     wl_min,
                    "wl_max":     wl_max,
                    "q_min":      q_min,
                    "q_max":      q_max,
                    "stack_enc":  stack_enc,
                    "num_mats":   num_mats,
                },
                MODELS_DIR / "pinn_best.pt",
            )

    log.info("Training complete — best val NK MSE: %.6f", best_val_nk)
    log.info(
        "Final val MAE — n: %.5f, k: %.5f",
        log_rows[-1]["val_mae_n"],
        log_rows[-1]["val_mae_k"],
    )

    # ── Training log ───────────────────────────────────────────────────────────
    log_path = MODELS_DIR / "training_log.csv"
    with open(log_path, "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["epoch", "train_loss", "val_loss_nk",
                        "val_mae_n", "val_mae_k", "val_loss_xrr"],
        )
        writer.writeheader()
        writer.writerows(log_rows)
    log.info("Training log saved → %s", log_path)


if __name__ == "__main__":
    main()
