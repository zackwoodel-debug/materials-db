"""Read-only access to a materials-db release (the SQLite file and its package), for people, programs and AI agents.

One library, two front ends: materials_db.access.http (a FastAPI app) and materials_db.access.mcp_server (an MCP server).
Every answer is plain JSON-able data carrying the release version, and the values come unchanged from the release:

  * n, k at a wavelength are interpolated linearly in wavelength between the dataset's stored points, only inside its own range
    (outside it: no value, never extrapolated), as the validation and the ML feature matrix do. A dataset the source gives as a
    dispersion formula is stored sampled so that this is within 1e-6 of the formula (from v0.15.0; v0.14.0 and earlier used a
    fixed 500-point grid that was up to 0.14% off, ZnTe Li1984), except right at a pole of the formula.
  * The default dataset of a material is the release's primary dataset (measured before model fit, covering 633 nm, then the
    widest range; the family tables name it). Every other dataset stays one argument away and is never averaged in.
  * Datasets of different phases, axes or temperatures are separate datasets (dataset_label); nothing merges them.
  * The database is opened read-only (SQLite mode=ro, query_only) and ad-hoc SQL passes an authorizer that allows reading only.

Release location, first found: the `release` argument, $MATERIALS_DB_RELEASE (a release folder or its .sqlite), the newest
release/materials-db-v*/ folder of this repository.
"""
import json
import math
import os
import re
import sqlite3
import sys
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parents[3]
MAX_ROWS = 1000
MAX_POINTS = 2000


class AccessError(ValueError):
    """A request the database cannot answer as asked (unknown or ambiguous material, bad argument, rejected SQL)."""


def _version_key(p):
    m = re.search(r"v(\d+)\.(\d+)\.(\d+)$", p.name)
    return tuple(map(int, m.groups())) if m else (-1,)


def find_release(release=None):
    cand = release or os.environ.get("MATERIALS_DB_RELEASE")
    if cand:
        p = Path(cand).expanduser()
        if p.is_file() and p.suffix == ".sqlite":
            return p.parent, p
        if p.is_dir():
            dbs = sorted(p.glob("materials-db-v*.sqlite"))
            if dbs:
                return p, dbs[-1]
        raise AccessError(f"no materials-db release at {p}")
    dirs = sorted((d for d in (_ROOT / "release").glob("materials-db-v*") if d.is_dir()), key=_version_key)
    for d in reversed(dirs):
        dbs = list(d.glob("materials-db-v*.sqlite"))
        if dbs:
            return d, dbs[0]
    raise AccessError("no release found: build one (scripts/build_release.py), download it from the GitHub release, "
                      "or set MATERIALS_DB_RELEASE")


def _clean(v):
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    if hasattr(v, "item"):  # numpy scalar
        return _clean(v.item())
    return v


def _records(df):
    return [{k: _clean(v) for k, v in r.items()} for r in df.to_dict("records")]


_READ_ACTIONS = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION}


def _authorizer(action, arg1, arg2, dbname, source):
    if action in _READ_ACTIONS:
        return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_PRAGMA and arg1 in ("table_info", "table_list", "index_list", "foreign_key_list") and arg2 is None:
        return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY


class ReleaseDB:
    def __init__(self, release=None):
        self.release_dir, self.sqlite_path = find_release(release)
        self.con = sqlite3.connect(f"file:{self.sqlite_path}?mode=ro", uri=True, check_same_thread=False)
        self.con.execute("PRAGMA query_only = ON")
        manifest = self.release_dir / "MANIFEST.json"
        self.manifest = json.loads(manifest.read_text()) if manifest.exists() else {}
        self.version = self.manifest.get("version") or re.search(r"v([\d.]+)\.sqlite$", self.sqlite_path.name).group(1)
        self._load_index()

    # ---------------------------------------------------------------- indexes

    def _load_index(self):
        mats = pd.read_sql("SELECT material_id, name, formula FROM materials", self.con)
        reg = self.release_dir / "material_registry.csv"
        key_of = dict(pd.read_csv(reg)[["material_id", "key"]].values) if reg.exists() else {}
        mats["key"] = mats.material_id.map(key_of)
        fam = {}
        ft = self.release_dir / "family_tables"
        for csv in sorted(ft.glob("*.csv")) if ft.exists() else []:
            if csv.stem.endswith("_gaps"):
                continue
            t = pd.read_csv(csv)
            for _, r in t.iterrows():
                fam.setdefault(r["name"], dict(family=csv.stem, row=r))
        mats["family"] = mats.name.map(lambda n: fam.get(n, {}).get("family"))
        mats["material_class"] = mats.name.map(lambda n: _clean(fam[n]["row"].get("materialclass")) if n in fam else None)
        self._family_rows = fam
        syn = pd.read_sql("SELECT material_id, synonym FROM material_synonyms", self.con)
        self.synonyms = syn.groupby("material_id").synonym.apply(list).to_dict()
        self.materials = mats.set_index("material_id").sort_index()
        self.primary = self._primary_tables()
        self.datasets = pd.read_sql(
            "SELECT material_id, dataset_label, raw_record_table, MIN(wavelength_nm) AS wl_min_nm, MAX(wavelength_nm) AS wl_max_nm, "
            "COUNT(*) AS points, SUM(k IS NOT NULL) AS points_with_k, MIN(temperature_c) AS t_min, MAX(temperature_c) AS t_max, "
            "MIN(source_id) AS source_id FROM optical_dispersion GROUP BY material_id, dataset_label ORDER BY material_id, dataset_label",
            self.con)

    def _primary_tables(self):
        """material_id -> raw_record_table of the primary dataset, resolved exactly as the ML sets do (needs the repository's
        selection inputs; without them there is no primary and callers must name a dataset)."""
        try:
            sys.path.insert(0, str(_ROOT / "scripts"))
            from generate_ml_release_set import primary_pages
            pages = primary_pages(self.release_dir)
        except Exception as exc:  # e.g. a downloaded release without the repository's selection inputs: reported by info()
            self.primary_unavailable = f"{type(exc).__name__}: {exc}"
            return {}
        self.primary_unavailable = None
        by_name = self.materials.reset_index().set_index("name").material_id
        return {int(by_name[n]): path for n, (_, path) in pages.items() if path and n in by_name}

    def _model_fit(self, table):
        try:
            from dataset_kind import model_fit_reason
            return model_fit_reason(table) is not None
        except Exception:
            return None

    # ---------------------------------------------------------------- lookups

    def resolve(self, ref):
        """A material from its id, stable key, name, synonym or formula (case-insensitive). Ambiguity is an error listing the
        candidates, never a guess."""
        m = self.materials
        s = str(ref).strip()
        if re.fullmatch(r"\d+", s) and int(s) in m.index:
            return int(s)
        low = s.lower()
        for col in ("key", "name"):
            hit = m.index[m[col].fillna("").str.lower() == low]
            if len(hit) == 1:
                return int(hit[0])
        hits = {mid for mid, names in self.synonyms.items() if low in (x.lower() for x in names)}
        hits |= set(m.index[m.formula.fillna("").str.lower() == low])
        if len(hits) == 1:
            return int(next(iter(hits)))
        if len(hits) > 1:
            raise AccessError(f"{ref!r} is ambiguous: " + "; ".join(f"{i} {m.loc[i, 'key']} ({m.loc[i, 'name']})" for i in sorted(hits))
                              + ". Use the material_id or key.")
        near = self.search(s, limit=8)["materials"]
        hint = ("; candidates: " + "; ".join(f"{x['material_id']} {x['key']} ({x['name']})" for x in near)) if near else "; try search_materials"
        raise AccessError(f"no material exactly named {ref!r}{hint}")

    def _ident(self, mid):
        r = self.materials.loc[mid]
        return dict(material_id=int(mid), key=r.key, name=r["name"], formula=_clean(r.formula), family=r.family,
                    material_class=r.material_class)

    def _dataset(self, mid, label=None):
        ds = self.datasets[self.datasets.material_id == mid]
        if label is None:
            prim = self.primary.get(mid)
            hit = ds[ds.raw_record_table == prim] if prim else ds.iloc[0:0]
            if hit.empty:
                raise AccessError(f"material {mid} has no primary dataset here; name one of: {sorted(ds.dataset_label)}")
            return hit.iloc[0]
        hit = ds[ds.dataset_label == label]
        if hit.empty:
            raise AccessError(f"material {mid} has no dataset {label!r}; its datasets: {sorted(ds.dataset_label)}")
        return hit.iloc[0]

    def _source(self, source_id):
        if source_id is None or (isinstance(source_id, float) and math.isnan(source_id)):
            return None
        r = self.con.execute("SELECT source_id, doi, title, authors, journal, year, url FROM sources WHERE source_id=?",
                             (int(source_id),)).fetchone()
        return dict(zip(("source_id", "doi", "title", "authors", "journal", "year", "url"), r)) if r else None

    def _dataset_info(self, d):
        mid = int(d.material_id)
        from_label = d.dataset_label.split(" | ")
        t0, t1 = _clean(d.t_min), _clean(d.t_max)
        return dict(dataset_label=d.dataset_label, source_file=d.raw_record_table, is_primary=self.primary.get(mid) == d.raw_record_table,
                    is_model_fit=self._model_fit(d.raw_record_table), wl_min_nm=_clean(d.wl_min_nm), wl_max_nm=_clean(d.wl_max_nm),
                    points=int(d.points), has_k=bool(d.points_with_k), temperature_c=t0 if t0 == t1 else None,
                    temperature_range_c=[t0, t1] if t0 != t1 else None, label_parts=from_label, source=self._source(d.source_id))

    # ---------------------------------------------------------------- queries

    def info(self):
        c = self.manifest.get("counts", {})
        return dict(release=self.version, sqlite=self.sqlite_path.name, license=self.manifest.get("license", "CC-BY-4.0"),
                    materials=len(self.materials), optical_datasets=len(self.datasets), counts=c,
                    materials_with_primary_dataset=len(self.primary), primary_unavailable=self.primary_unavailable,
                    families=self.materials.family.value_counts().sort_index().to_dict(),
                    rules=["n, k at a wavelength: linear interpolation between a dataset's own points, inside its range only; never extrapolated",
                           "default dataset = the release's primary (measured first, covering 633 nm, then widest range)",
                           "phases, axes and temperatures are separate datasets and are never merged",
                           "cite the dataset and each dataset's source (DATA_LICENSE.md)"])

    def search(self, query=None, family=None, material_class=None, limit=25):
        m = self.materials.reset_index()
        if query:
            q = str(query).lower()
            syn_hit = {mid for mid, names in self.synonyms.items() if any(q in x.lower() for x in names)}
            hit = (m.name.str.lower().str.contains(q, regex=False) | m.formula.fillna("").str.lower().str.contains(q, regex=False)
                   | m.key.fillna("").str.lower().str.contains(q, regex=False) | m.material_id.isin(syn_hit))
            exact = (m.name.str.lower() == q) | (m.formula.fillna("").str.lower() == q) | (m.key.fillna("").str.lower() == q)
            m = m.assign(_exact=exact)[hit].sort_values(["_exact", "name"], ascending=[False, True])
        if family:
            m = m[m.family == family]
        if material_class:
            m = m[m.material_class.fillna("").str.lower() == str(material_class).lower()]
        n_ds = self.datasets.groupby("material_id").size()
        total = len(m)
        m = m.head(max(1, min(int(limit), 200)))
        return dict(release=self.version, total=total, returned=len(m),
                    materials=[dict(self._ident(int(r.material_id)), optical_datasets=int(n_ds.get(r.material_id, 0))) for r in m.itertuples()])

    def material(self, ref):
        mid = self.resolve(ref)
        r = self.con.execute("SELECT smiles, inchikey, molecular_weight, cas_number, pubchem_cid FROM materials WHERE material_id=?", (mid,)).fetchone()
        phys = pd.read_sql("SELECT p.density_g_cm3, p.xray_sld, p.neutron_sld, p.dielectric_constant, p.temperature_c, p.frequency_hz, "
                           "p.wavelength_nm, p.energy_ev, p.dataset_label, s.title AS source_title, s.doi AS source_doi "
                           "FROM physical_properties p LEFT JOIN sources s USING (source_id) WHERE p.material_id=?", self.con, params=(mid,))
        phys = phys.dropna(axis=1, how="all")
        cons = pd.read_sql("SELECT property_name, consensus_value, std_dev, num_sources, classification FROM consensus_properties "
                           "WHERE material_id=?", self.con, params=(mid,))
        name = self.materials.loc[mid, "name"]
        fam = self._family_rows.get(name, {}).get("row")
        family_notes = {k: _clean(fam.get(k)) for k in ("polymorph", "flags", "notes", "note", "caution", "density_source")
                        if fam is not None and k in fam and _clean(fam.get(k)) not in (None, "")}
        ds = self.datasets[self.datasets.material_id == mid]
        return dict(release=self.version, **self._ident(mid),
                    identifiers=dict(zip(("smiles", "inchikey", "molecular_weight", "cas_number", "pubchem_cid"), r)),
                    synonyms=self.synonyms.get(mid, []), family_notes=family_notes, physical_properties=_records(phys),
                    consensus=_records(cons), optical_datasets=[self._dataset_info(d) for d in ds.itertuples(index=False)])

    def optical(self, ref, dataset_label=None, wl_min_nm=None, wl_max_nm=None, max_points=500):
        mid = self.resolve(ref)
        d = self._dataset(mid, dataset_label)
        sql = "SELECT wavelength_nm, n, k, temperature_c FROM optical_dispersion WHERE material_id=? AND dataset_label=?"
        args = [mid, d.dataset_label]
        if wl_min_nm is not None:
            sql, args = sql + " AND wavelength_nm >= ?", args + [float(wl_min_nm)]
        if wl_max_nm is not None:
            sql, args = sql + " AND wavelength_nm <= ?", args + [float(wl_max_nm)]
        pts = pd.read_sql(sql + " ORDER BY wavelength_nm", self.con, params=args)
        cap = max(2, min(int(max_points), MAX_POINTS))
        thinned = len(pts) > cap
        if thinned:  # evenly spaced source points, first and last kept; the values themselves are untouched
            idx = sorted({round(i * (len(pts) - 1) / (cap - 1)) for i in range(cap)})
            pts = pts.iloc[idx]
        return dict(release=self.version, **self._ident(mid), dataset=self._dataset_info(d), returned=len(pts), thinned=thinned,
                    note="source points, unchanged; thinned=true means an evenly spaced subset (raise max_points or narrow the range)",
                    data=_records(pts.dropna(axis=1, how="all")))

    def _interp(self, mid, label, wl):
        pts = pd.read_sql("SELECT wavelength_nm AS w, n, k FROM optical_dispersion WHERE material_id=? AND dataset_label=?",
                          self.con, params=(mid, label))
        out = {}
        for col in ("n", "k"):
            s = pts.dropna(subset=[col]).groupby("w")[col].mean().sort_index()
            if len(s) < 1 or not (s.index[0] <= wl <= s.index[-1]):
                out[col] = None
                continue
            if wl in s.index:
                out[col] = float(s.loc[wl])
                continue
            hi = s.index.searchsorted(wl)
            w0, w1 = s.index[hi - 1], s.index[hi]
            t = (wl - w0) / (w1 - w0)
            out[col] = float(s.iloc[hi - 1] + t * (s.iloc[hi] - s.iloc[hi - 1]))
            out[f"{col}_bracket_nm"] = [float(w0), float(w1)]
        return out

    def nk_at(self, ref, wavelength_nm, dataset_label=None, all_datasets=False):
        mid = self.resolve(ref)
        wl = float(wavelength_nm)
        if not wl > 0:
            raise AccessError("wavelength_nm must be positive")
        base = dict(release=self.version, **self._ident(mid), wavelength_nm=wl,
                    method="linear in wavelength between the dataset's own points; none outside its range")
        if all_datasets:
            ds = self.datasets[self.datasets.material_id == mid]
            rows = []
            for d in ds.itertuples(index=False):
                v = self._interp(mid, d.dataset_label, wl)
                info = self._dataset_info(d)
                rows.append(dict(dataset_label=d.dataset_label, is_primary=info["is_primary"], is_model_fit=info["is_model_fit"],
                                 temperature_c=info["temperature_c"], covers=v["n"] is not None or v["k"] is not None,
                                 wl_range_nm=[info["wl_min_nm"], info["wl_max_nm"]], **v))
            return dict(base, datasets=rows,
                        note="values of different phases, axes, temperatures or pressures are different quantities: compare like with like")
        d = self._dataset(mid, dataset_label)
        v = self._interp(mid, d.dataset_label, wl)
        info = self._dataset_info(d)
        if v["n"] is None and v["k"] is None:
            raise AccessError(f"{wl:g} nm is outside dataset {d.dataset_label!r} ({info['wl_min_nm']:g}-{info['wl_max_nm']:g} nm); "
                              "use all_datasets=true to see which datasets cover it")
        return dict(base, dataset=info, **v)

    def comparisons(self, ref):
        mid = self.resolve(ref)
        v = pd.read_sql("SELECT property_name, dataset_a, dataset_b, pearson_r, rmse, mean_relative_error, classification, notes "
                        "FROM dataset_validation WHERE material_id=? ORDER BY property_name, dataset_a, dataset_b", self.con, params=(mid,))
        return dict(release=self.version, **self._ident(mid), comparisons=_records(v),
                    note="like-for-like comparisons only (same phase, axis and temperature), over each pair's wavelength overlap")

    def schema(self):
        p = self.release_dir / "data_dictionary.json"
        if p.exists():
            return json.loads(p.read_text())
        tables = [r[0] for r in self.con.execute("SELECT name FROM sqlite_master WHERE type IN ('table','view') ORDER BY 1")]
        return dict(release=self.version, tables={t: [c[1] for c in self.con.execute(f"PRAGMA table_info({t})")] for t in tables})

    def sql(self, query, limit=MAX_ROWS):
        """One read-only SELECT (or WITH ... SELECT). Anything that is not reading is refused by the SQLite authorizer."""
        q = str(query).strip().rstrip(";").strip()
        if not re.match(r"(?is)^(select|with)\b", q) or ";" in q:
            raise AccessError("only a single SELECT (or WITH ... SELECT) statement is allowed")
        cap = max(1, min(int(limit), MAX_ROWS))
        self.con.set_authorizer(_authorizer)
        try:
            cur = self.con.execute(q)
            cols = [c[0] for c in cur.description]
            rows = cur.fetchmany(cap + 1)
        except sqlite3.DatabaseError as exc:
            raise AccessError(f"SQL error: {exc}") from None
        finally:
            self.con.set_authorizer(None)
        return dict(release=self.version, columns=cols, rows=[[_clean(v) for v in r] for r in rows[:cap]], truncated=len(rows) > cap)
