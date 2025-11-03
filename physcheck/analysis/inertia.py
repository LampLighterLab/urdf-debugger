from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np

from physcheck.urdf.loader import Collision, Geometry, Link


@dataclass(slots=True)
class InertiaCheck:
    check: str
    passed: bool
    severity: str
    message: str
    details: Dict[str, Any] = field(default_factory=dict)


def summarize_model_inertia(links: Iterable[Link]) -> Dict[str, List[InertiaCheck]]:
    return {link.name: evaluate_link_inertia(link) for link in links}


def evaluate_link_inertia(link: Link) -> List[InertiaCheck]:
    results: List[InertiaCheck] = []
    inertial = link.inertial

    if inertial is None:
        results.append(
            InertiaCheck(
                check="inertial_present",
                passed=False,
                severity="warning",
                message="Link has no <inertial> definition.",
            )
        )
        return results

    mass = inertial.mass
    matrix = _build_inertia_matrix(inertial.inertia)

    if mass is None or not isfinite(mass):
        results.append(
            InertiaCheck(
                check="mass_finite",
                passed=False,
                severity="error",
                message="Link mass is missing or non-finite.",
                details={"mass": mass},
            )
        )
    elif mass <= 0.0:
        results.append(
            InertiaCheck(
                check="mass_positive",
                passed=False,
                severity="error",
                message="Link mass must be positive.",
                details={"mass": mass},
            )
        )
    else:
        results.append(
            InertiaCheck(
                check="mass_positive",
                passed=True,
                severity="info",
                message="Mass is positive.",
                details={"mass": mass},
            )
        )

    if mass == 0.0 and np.any(np.abs(matrix) > 1e-12):
        results.append(
            InertiaCheck(
                check="zero_mass_inertia",
                passed=False,
                severity="error",
                message="Zero-mass link has non-zero inertia tensor.",
            )
        )

    eigvals = np.linalg.eigvalsh(matrix)
    tol = 1e-9
    positive_definite = bool(np.all(eigvals > tol))
    results.append(
        InertiaCheck(
            check="positive_definite",
            passed=positive_definite,
            severity="error" if not positive_definite else "info",
            message="Inertia tensor is positive definite." if positive_definite else "Inertia tensor is not positive definite.",
            details={"eigenvalues": eigvals.tolist()},
        )
    )

    triangle_ok = _check_triangle_inequality(eigvals, tol=tol)
    results.append(
        InertiaCheck(
            check="triangle_inequality",
            passed=triangle_ok,
            severity="error" if not triangle_ok else "info",
            message="Triangle inequalities satisfied." if triangle_ok else "Triangle inequality violated for principal moments.",
            details={"eigenvalues": eigvals.tolist()},
        )
    )

    ratio_ok, ratio_details = _check_eigenvalue_ratio(eigvals)
    results.append(
        InertiaCheck(
            check="eigenvalue_ratio",
            passed=ratio_ok,
            severity="warning" if not ratio_ok else "info",
            message="Eigenvalue ratio within bounds." if ratio_ok else "Eigenvalue ratio exceeds recommended threshold.",
            details=ratio_details,
        )
    )

    geom_check = _check_geometry_consistency(link, mass, eigvals)
    if geom_check:
        results.append(geom_check)

    return results


def _build_inertia_matrix(entries: Tuple[float, float, float, float, float, float]) -> np.ndarray:
    ixx, ixy, ixz, iyy, iyz, izz = entries
    return np.array(
        [
            [ixx, ixy, ixz],
            [ixy, iyy, iyz],
            [ixz, iyz, izz],
        ]
    )


def _check_triangle_inequality(eigvals: np.ndarray, tol: float) -> bool:
    vals = np.sort(eigvals)
    if np.any(vals < tol):
        return False
    a, b, c = vals
    return (a <= b + c + tol) and (b <= a + c + tol) and (c <= a + b + tol)


def _check_eigenvalue_ratio(eigvals: np.ndarray, max_ratio: float = 1e3) -> Tuple[bool, Dict[str, Any]]:
    vals = np.sort(eigvals)
    min_val = max(vals[0], 1e-9)
    max_val = vals[-1]
    ratio = float(max_val / min_val)
    return (ratio <= max_ratio), {"max": max_val, "min": min_val, "ratio": ratio}


def _check_geometry_consistency(link: Link, mass: float, eigvals: np.ndarray) -> Optional[InertiaCheck]:
    if mass is None or mass <= 0.0:
        return None

    approx = _approximate_collision_inertia(link.collisions, mass)
    if approx is None:
        return None

    expected_eigs, density = approx
    actual_sorted = np.sort(eigvals)
    expected_sorted = np.sort(expected_eigs)

    ratios = []
    for actual, expected in zip(actual_sorted, expected_sorted):
        if expected < 1e-9 or actual < 1e-9:
            continue
        ratios.append(actual / expected)

    if not ratios:
        return None

    min_ratio = min(ratios)
    max_ratio = max(ratios)
    ratio_ok = (0.2 <= min_ratio) and (max_ratio <= 5.0)

    return InertiaCheck(
        check="geometry_consistency",
        passed=ratio_ok,
        severity="warning" if not ratio_ok else "info",
        message="Inertia aligns with collision geometry estimate." if ratio_ok else "Inertia deviates from collision geometry estimate.",
        details={
            "expected_eigenvalues": expected_sorted.tolist(),
            "actual_eigenvalues": actual_sorted.tolist(),
            "ratio_range": [min_ratio, max_ratio],
            "density_estimate": density,
        },
    )


def _approximate_collision_inertia(
    collisions: Tuple[Collision, ...], mass: float
) -> Optional[Tuple[np.ndarray, float]]:
    for collision in collisions:
        geom = collision.geometry
        if geom.type == "box" and geom.size:
            return _box_inertia(geom.size, mass)
        if geom.type == "cylinder" and geom.radius and geom.length:
            return _cylinder_inertia(geom.radius, geom.length, mass)
        if geom.type == "sphere" and geom.radius:
            return _sphere_inertia(geom.radius, mass)
    return None


def _box_inertia(size: Tuple[float, float, float], mass: float) -> Tuple[np.ndarray, float]:
    lx, ly, lz = size
    volume = lx * ly * lz
    density = mass / volume if volume > 0 else float("nan")
    ixx = (mass / 12.0) * (ly ** 2 + lz ** 2)
    iyy = (mass / 12.0) * (lx ** 2 + lz ** 2)
    izz = (mass / 12.0) * (lx ** 2 + ly ** 2)
    return np.array([ixx, iyy, izz]), density


def _cylinder_inertia(radius: float, length: float, mass: float) -> Tuple[np.ndarray, float]:
    volume = np.pi * radius ** 2 * length
    density = mass / volume if volume > 0 else float("nan")
    ixx = iyy = (mass / 12.0) * (3 * radius ** 2 + length ** 2)
    izz = 0.5 * mass * radius ** 2
    return np.array([ixx, iyy, izz]), density


def _sphere_inertia(radius: float, mass: float) -> Tuple[np.ndarray, float]:
    volume = (4 / 3) * np.pi * radius ** 3
    density = mass / volume if volume > 0 else float("nan")
    moment = 0.4 * mass * radius ** 2
    return np.array([moment, moment, moment]), density
