"""CSV parser returning a pandas DataFrame."""

import io
from pathlib import Path
from typing import IO, Union

import pandas as pd


def parse_csv(
    source: Union[str, Path, IO[str]],
    required_columns: list[str] | None = None,
) -> pd.DataFrame:
    """Read a CSV into a DataFrame.

    Parameters
    ----------
    source:
        File path (str or Path) or any file-like object accepted by pandas.
    required_columns:
        If given, columns absent from the CSV are added with ``float('nan')``.

    Returns
    -------
    DataFrame with all columns present in the file, plus any
    required columns that were missing.
    """
    df = pd.read_csv(source)
    if required_columns:
        for col in required_columns:
            if col not in df.columns:
                df[col] = float("nan")
    return df
