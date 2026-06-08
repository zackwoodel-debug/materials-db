"""SQLite schema and DB initialization for materials informatics."""

import sqlite3


_DDL = """
CREATE TABLE IF NOT EXISTS references_db (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    doi           TEXT    UNIQUE,
    citation_text TEXT    NOT NULL,
    url           TEXT,
    bibtex        TEXT
);

CREATE TABLE IF NOT EXISTS materials (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    name             TEXT    NOT NULL UNIQUE,
    phase            TEXT,
    formula          TEXT,
    smiles           TEXT,
    molecular_weight REAL,
    material_class   TEXT,
    notes            TEXT,
    density_g_cm3    REAL
);

CREATE TABLE IF NOT EXISTS chemical_descriptors (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    material_id     INTEGER NOT NULL REFERENCES materials(id) ON DELETE CASCADE,
    descriptor_name TEXT    NOT NULL,
    value           REAL    NOT NULL,
    source_library  TEXT,
    UNIQUE(material_id, descriptor_name)
);

CREATE TABLE IF NOT EXISTS optical_constants (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    material_id   INTEGER NOT NULL REFERENCES materials(id) ON DELETE CASCADE,
    reference_id  INTEGER REFERENCES references_db(id),
    phase         TEXT,
    wavelength_nm REAL    NOT NULL,
    n             REAL    NOT NULL,
    k             REAL,
    UNIQUE(material_id, wavelength_nm, phase)
);

CREATE TABLE IF NOT EXISTS mechanical_qcmd (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    material_id          INTEGER NOT NULL REFERENCES materials(id) ON DELETE CASCADE,
    reference_id         INTEGER REFERENCES references_db(id),
    config               TEXT,
    rho_g_cm3            REAL,
    shear_storage_pascal REAL,
    shear_loss_pascal    REAL,
    eta_mPas             REAL,
    frequency_hz         REAL,
    temperature_C        REAL,
    UNIQUE(material_id, frequency_hz, config)
);

CREATE TABLE IF NOT EXISTS dielectrics (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    material_id       INTEGER NOT NULL REFERENCES materials(id) ON DELETE CASCADE,
    reference_id      INTEGER REFERENCES references_db(id),
    frequency_hz      REAL    NOT NULL,
    temperature_C     REAL,
    real_permittivity REAL    NOT NULL,
    imag_permittivity REAL,
    UNIQUE(material_id, frequency_hz, temperature_C)
);

CREATE TABLE IF NOT EXISTS calculated_slds (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    material_id       INTEGER NOT NULL REFERENCES materials(id) ON DELETE CASCADE,
    reference_id      INTEGER REFERENCES references_db(id),
    energy_ev         REAL    NOT NULL,
    wavelength_nm     REAL    NOT NULL,
    xray_sld_real     REAL    NOT NULL,
    xray_sld_imag     REAL,
    neutron_sld_real  REAL    NOT NULL,
    neutron_sld_imag  REAL,
    UNIQUE(material_id, energy_ev)
);
"""


def init_db(path: str = ":memory:") -> sqlite3.Connection:
    """Create tables and return an open connection."""
    conn = sqlite3.connect(path)
    conn.executescript(_DDL)
    conn.commit()
    return conn


def insert_material(
    conn: sqlite3.Connection,
    name: str,
    phase: str | None = None,
    formula: str | None = None,
    smiles: str | None = None,
    molecular_weight: float | None = None,
    material_class: str | None = None,
    notes: str | None = None,
    density_g_cm3: float | None = None,
) -> int:
    """Insert a material row and return its id."""
    cur = conn.execute(
        "INSERT OR IGNORE INTO materials "
        "(name, phase, formula, smiles, molecular_weight, material_class, notes, density_g_cm3) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (name, phase, formula, smiles, molecular_weight, material_class, notes, density_g_cm3),
    )
    conn.commit()
    # In case of IGNORE, fetch the id
    if cur.lastrowid:
        return cur.lastrowid
    row = conn.execute("SELECT id FROM materials WHERE name = ?", (name,)).fetchone()
    return row[0]


def insert_optical(
    conn: sqlite3.Connection,
    material_id: int,
    phase: str | None,
    wavelength_nm: float,
    n: float,
    k: float | None = None,
    reference_id: int | None = None,
) -> None:
    """Insert one row into optical_constants."""
    conn.execute(
        "INSERT OR IGNORE INTO optical_constants "
        "(material_id, phase, wavelength_nm, n, k, reference_id) VALUES (?,?,?,?,?,?)",
        (material_id, phase, wavelength_nm, n, k, reference_id),
    )
    conn.commit()


def insert_mechanical(
    conn: sqlite3.Connection,
    material_id: int,
    config: str | None,
    rho_g_cm3: float | None,
    shear_storage_pascal: float | None,
    shear_loss_pascal: float | None,
    eta_mPas: float | None,
    frequency_hz: float | None = None,
    temperature_C: float | None = None,
    reference_id: int | None = None,
) -> None:
    """Insert one row into mechanical_qcmd."""
    conn.execute(
        "INSERT OR IGNORE INTO mechanical_qcmd "
        "(material_id, config, rho_g_cm3, shear_storage_pascal, shear_loss_pascal, eta_mPas, frequency_hz, temperature_C, reference_id) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (material_id, config, rho_g_cm3, shear_storage_pascal, shear_loss_pascal, eta_mPas, frequency_hz, temperature_C, reference_id),
    )
    conn.commit()
