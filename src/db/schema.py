"""SQLite schema and DB initialization for materials informatics."""

import sqlite3


_DDL = """
CREATE TABLE IF NOT EXISTS materials (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    name  TEXT    NOT NULL,
    phase TEXT
);

CREATE TABLE IF NOT EXISTS optical_constants (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    material_id   INTEGER NOT NULL REFERENCES materials(id),
    phase         TEXT,
    wavelength_nm REAL    NOT NULL,
    n             REAL    NOT NULL,
    k             REAL
);

CREATE TABLE IF NOT EXISTS mechanical_qcmd (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    material_id          INTEGER NOT NULL REFERENCES materials(id),
    config               TEXT,
    rho_g_cm3            REAL,
    shear_storage_pascal REAL,
    shear_loss_pascal    REAL,
    eta_mPas             REAL
);
"""


def init_db(path: str = ":memory:") -> sqlite3.Connection:
    """Create tables and return an open connection."""
    conn = sqlite3.connect(path)
    conn.executescript(_DDL)
    conn.commit()
    return conn


def insert_material(conn: sqlite3.Connection, name: str, phase: str | None = None) -> int:
    """Insert a material row and return its id."""
    cur = conn.execute(
        "INSERT INTO materials (name, phase) VALUES (?, ?)", (name, phase)
    )
    conn.commit()
    return cur.lastrowid  # type: ignore[return-value]


def insert_optical(
    conn: sqlite3.Connection,
    material_id: int,
    phase: str | None,
    wavelength_nm: float,
    n: float,
    k: float | None = None,
) -> None:
    """Insert one row into optical_constants."""
    conn.execute(
        "INSERT INTO optical_constants "
        "(material_id, phase, wavelength_nm, n, k) VALUES (?,?,?,?,?)",
        (material_id, phase, wavelength_nm, n, k),
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
) -> None:
    """Insert one row into mechanical_qcmd."""
    conn.execute(
        "INSERT INTO mechanical_qcmd "
        "(material_id, config, rho_g_cm3, shear_storage_pascal, shear_loss_pascal, eta_mPas) "
        "VALUES (?,?,?,?,?,?)",
        (material_id, config, rho_g_cm3, shear_storage_pascal, shear_loss_pascal, eta_mPas),
    )
    conn.commit()
