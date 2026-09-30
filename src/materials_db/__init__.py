"""materials_db: the software package. __version__ is the SOFTWARE version, not the dataset release (docs/versioning.md)."""
from importlib import metadata as _metadata


def _software_version():
    """The installed distribution's version; from a checkout that is not installed, the same authoritative field in pyproject.toml."""
    try:
        return _metadata.version("materials_db")
    except _metadata.PackageNotFoundError:
        import tomllib
        from pathlib import Path

        return tomllib.loads((Path(__file__).resolve().parents[2] / "pyproject.toml").read_text())["project"]["version"]


__version__ = _software_version()
