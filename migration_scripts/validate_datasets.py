#!/usr/bin/env python3
"""Utilities for optical dataset similarity validation."""

from __future__ import annotations

import math
import sqlite3

import numpy as np


def classify_correlation(pearson_r: float | None) -> str:
    if pearson_r is None or not math.isfinite(pearson_r):
        return "insufficient"
    if pearson_r > 0.99:
        return "excellent"
    if pearson_r >= 0.95:
        return "acceptable"
    if pearson_r >= 0.90:
        return "warning"
    return "suspicious"


def compare_spectra(left: np.ndarray, right: np.ndarray) -> dict:
    left = np.asarray(left, dtype=float)
    right = np.asarray(right, dtype=float)
    mask = np.isfinite(left) & np.isfinite(right)
    if mask.sum() < 2:
        return {
            "pearson_r": None,
            "rmse": None,
            "mean_relative_error": None,
            "classification": "insufficient",
        }

    left = left[mask]
    right = right[mask]
    pearson_r = float(np.corrcoef(left, right)[0, 1])
    rmse = float(np.sqrt(np.mean((left - right) ** 2)))
    denominator = (np.abs(left) + np.abs(right)) / 2.0
    relative = np.divide(
        np.abs(left - right),
        denominator,
        out=np.zeros_like(left),
        where=denominator != 0,
    )
    mean_relative_error = float(np.mean(relative))
    return {
        "pearson_r": pearson_r,
        "rmse": rmse,
        "mean_relative_error": mean_relative_error,
        "classification": classify_correlation(pearson_r),
    }


def validate_optical_material(conn: sqlite3.Connection, material_id: int, property_name: str = "n") -> int:
    rows = conn.execute(
        """
        SELECT dataset_label, wavelength_nm, n, k
        FROM optical_dispersion
        WHERE material_id = ?
        ORDER BY dataset_label, wavelength_nm
        """,
        (material_id,),
    ).fetchall()
    grouped: dict[str, list[tuple[float, float]]] = {}
    value_index = 2 if property_name == "n" else 3
    for row in rows:
        if row[value_index] is None:
            continue
        grouped.setdefault(row[0] or "unknown", []).append((float(row[1]), float(row[value_index])))

    inserted = 0
    labels = sorted(grouped)
    for left_index, left_label in enumerate(labels):
        for right_label in labels[left_index + 1 :]:
            left = grouped[left_label]
            right = grouped[right_label]
            min_wavelength = max(min(w for w, _v in left), min(w for w, _v in right))
            max_wavelength = min(max(w for w, _v in left), max(w for w, _v in right))
            if min_wavelength >= max_wavelength:
                continue
            grid = np.linspace(min_wavelength, max_wavelength, 200)
            left_interp = np.interp(grid, [w for w, _v in left], [v for _w, v in left])
            right_interp = np.interp(grid, [w for w, _v in right], [v for _w, v in right])
            metrics = compare_spectra(left_interp, right_interp)
            conn.execute(
                """
                INSERT OR REPLACE INTO dataset_validation(
                    material_id, property_name, dataset_a, dataset_b,
                    pearson_r, rmse, mean_relative_error, classification
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    material_id,
                    property_name,
                    left_label,
                    right_label,
                    metrics["pearson_r"],
                    metrics["rmse"],
                    metrics["mean_relative_error"],
                    metrics["classification"],
                ),
            )
            inserted += 1
    return inserted
