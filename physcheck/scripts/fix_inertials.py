"""CLI to replace implausible URDF inertias with geometry-based estimates.

Usage examples:
- python -m physcheck.scripts.fix_inertials cartpole
- python -m physcheck.scripts.fix_inertials robots/cartpole/urdf/cartpole.urdf

The tool asks whether to fix only failing checks (errors) or also warnings,
whether to include triangle-inequality violations, and whether to prefer
collision vs visual geometry when both exist. It writes an output URDF with a
`_fixed` suffix unless `--output` is provided.
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import xml.etree.ElementTree as ET
import numpy as np

from physcheck.analysis import summarize_model_inertia
from physcheck.urdf.loader import Geometry, Link, load_urdf
from physcheck.scripts.show_kinematic_tree import resolve_urdf_path, ROBOTS_DIR


def _fmt(x: float) -> str:
    try:
        return f"{float(x):.9g}"
    except Exception:
        return str(x)


def _rpy_to_matrix(rpy: Tuple[float, float, float]) -> np.ndarray:
    roll, pitch, yaw = rpy
    cr, sr = math.cos(roll), math.sin(roll)
    cp, sp = math.cos(pitch), math.sin(pitch)
    cy, sy = math.cos(yaw), math.sin(yaw)
    # URDF rpy is applied as roll (X), then pitch (Y), then yaw (Z): Rz * Ry * Rx
    Rx = np.array([[1, 0, 0], [0, cr, -sr], [0, sr, cr]], dtype=float)
    Ry = np.array([[cp, 0, sp], [0, 1, 0], [-sp, 0, cp]], dtype=float)
    Rz = np.array([[cy, -sy, 0], [sy, cy, 0], [0, 0, 1]], dtype=float)
    return Rz @ Ry @ Rx


def _primitive_inertia_diag(geom: Geometry, mass: float) -> Optional[np.ndarray]:
    if mass <= 0.0 or not np.isfinite(mass):
        return None
    if geom.type == "box" and geom.size:
        lx, ly, lz = geom.size
        ixx = (mass / 12.0) * (ly ** 2 + lz ** 2)
        iyy = (mass / 12.0) * (lx ** 2 + lz ** 2)
        izz = (mass / 12.0) * (lx ** 2 + ly ** 2)
        return np.array([ixx, iyy, izz], dtype=float)
    if geom.type == "cylinder" and geom.radius and geom.length:
        r = geom.radius
        L = geom.length
        ixx = iyy = (mass / 12.0) * (3.0 * r ** 2 + L ** 2)
        izz = 0.5 * mass * r ** 2
        return np.array([ixx, iyy, izz], dtype=float)
    if geom.type == "sphere" and geom.radius:
        r = geom.radius
        moment = 0.4 * mass * r ** 2
        return np.array([moment, moment, moment], dtype=float)
    return None


def _rotate_inertia(diag_moments: np.ndarray, R: np.ndarray) -> np.ndarray:
    I_body = np.diag(diag_moments)
    return R @ I_body @ R.T


def _sanitize_inertia_matrix(matrix: np.ndarray, tol: float = 1e-12) -> np.ndarray:
    """Symmetrize and zero-out near-zero terms before serialization."""

    sym = 0.5 * (matrix + matrix.T)
    sym[np.abs(sym) < tol] = 0.0
    return sym


def _collect_problem_links(
    links: Iterable[Link],
    *,
    include_warnings: bool,
    include_triangle: bool,
) -> Dict[str, Dict[str, object]]:
    """Return mapping of link name -> summary of failing checks.

    Includes any link with at least one failing check of the desired severities.
    """
    problems: Dict[str, Dict[str, object]] = {}
    results = summarize_model_inertia(links)
    for link in links:
        checks = results.get(link.name, [])
        failing = [c for c in checks if not c.passed]
        if not failing:
            continue
        if not include_warnings:
            failing = [c for c in failing if c.severity == "error"]
        if not include_triangle:
            failing = [c for c in failing if c.check != "triangle_inequality"]
        if not failing:
            continue
        problems[link.name] = {
            "link": link,
            "checks": failing,
        }
    return problems


def _pick_geometry_source(prefer_collision: bool, link: Link) -> Tuple[str, Optional[Geometry], Tuple[float, float, float], Tuple[float, float, float]]:
    """Pick a geometry for inertia estimation and return its type, geometry, and origin.

    Returns (source_label, geometry, xyz, rpy). If no usable geometry exists, geometry is None.
    """
    xyz = (0.0, 0.0, 0.0)
    rpy = (0.0, 0.0, 0.0)
    if prefer_collision:
        if link.collisions:
            col = link.collisions[0]
            return ("collision", col.geometry, col.origin.xyz, col.origin.rpy)
        if link.visuals:
            vis = link.visuals[0]
            return ("visual", vis.geometry, vis.origin.xyz, vis.origin.rpy)
    else:
        if link.visuals:
            vis = link.visuals[0]
            return ("visual", vis.geometry, vis.origin.xyz, vis.origin.rpy)
        if link.collisions:
            col = link.collisions[0]
            return ("collision", col.geometry, col.origin.xyz, col.origin.rpy)
    return ("none", None, xyz, rpy)


def _find_link_element(root: ET.Element, name: str) -> Optional[ET.Element]:
    for link_el in root.findall("link"):
        if link_el.get("name") == name:
            return link_el
    return None


def _get_mass_from_link_element(link_el: ET.Element) -> Optional[float]:
    inertial = link_el.find("inertial")
    if inertial is None:
        return None
    mass_el = inertial.find("mass")
    if mass_el is None:
        return None
    try:
        return float(mass_el.get("value"))
    except Exception:
        return None


def _ensure_inertial(link_el: ET.Element) -> ET.Element:
    inertial = link_el.find("inertial")
    if inertial is None:
        inertial = ET.SubElement(link_el, "inertial")
    return inertial


def _set_origin(element: ET.Element, xyz: Tuple[float, float, float], rpy: Tuple[float, float, float]) -> None:
    origin = element.find("origin")
    if origin is None:
        origin = ET.SubElement(element, "origin")
    origin.set("xyz", f"{_fmt(xyz[0])} {_fmt(xyz[1])} {_fmt(xyz[2])}")
    origin.set("rpy", f"{_fmt(rpy[0])} {_fmt(rpy[1])} {_fmt(rpy[2])}")


def _set_inertia(element: ET.Element, I: np.ndarray) -> None:
    inertia = element.find("inertia")
    if inertia is None:
        inertia = ET.SubElement(element, "inertia")
    # Symmetric tensor
    inertia.set("ixx", _fmt(I[0, 0]))
    inertia.set("ixy", _fmt(I[0, 1]))
    inertia.set("ixz", _fmt(I[0, 2]))
    inertia.set("iyy", _fmt(I[1, 1]))
    inertia.set("iyz", _fmt(I[1, 2]))
    inertia.set("izz", _fmt(I[2, 2]))


def fix_inertias(
    urdf_path: Path,
    *,
    include_warnings: bool,
    include_triangle: bool,
    prefer_collision: bool,
    output_path: Optional[Path] = None,
    print_fn=print,
) -> Path:
    model = load_urdf(urdf_path)

    problems = _collect_problem_links(
        model.links,
        include_warnings=include_warnings,
        include_triangle=include_triangle,
    )
    if not problems:
        raise SystemExit("No links with failing checks at requested severities.")

    # Parse XML for in-place edits
    tree = ET.parse(urdf_path)
    root = tree.getroot()
    fixed_links: List[str] = []
    skipped: Dict[str, str] = {}

    for link_name, entry in problems.items():
        link: Link = entry["link"]  # type: ignore[assignment]
        link_el = _find_link_element(root, link_name)
        if link_el is None:
            skipped[link_name] = "link element not found"
            continue

        # Determine mass – must come from the XML inertial/mass for reliability
        mass = _get_mass_from_link_element(link_el)
        if mass is None or mass <= 0.0 or not np.isfinite(mass):
            skipped[link_name] = "missing or non-positive mass"
            continue

        source_label, geom, xyz, rpy = _pick_geometry_source(prefer_collision, link)
        if geom is None:
            skipped[link_name] = "no usable geometry (box/cylinder/sphere)"
            continue

        diag = _primitive_inertia_diag(geom, mass)
        if diag is None:
            skipped[link_name] = f"unsupported geometry type for {source_label}: {geom.type}"
            continue

        # Express the inertia matrix in the link frame by rotating the
        # principal moments from the geometry frame.
        R = _rpy_to_matrix(rpy)
        I = _sanitize_inertia_matrix(_rotate_inertia(diag, R))

        inertial_el = _ensure_inertial(link_el)
        # Preserve mass; align the inertial frame with the link frame so the
        # tensor components are expressed directly in link coordinates.
        _set_origin(inertial_el, xyz, (0.0, 0.0, 0.0))
        _set_inertia(inertial_el, I)
        fixed_links.append(link_name)

    if not fixed_links:
        details = ", ".join(f"{k} ({v})" for k, v in skipped.items()) or "none"
        raise SystemExit(f"No links were updated. Reasons: {details}")

    if output_path is None:
        output_path = urdf_path.with_name(urdf_path.stem + "_fixed" + urdf_path.suffix)

    # Write result
    tree.write(output_path, encoding="utf-8", xml_declaration=True)

    print_fn(f"Updated {len(fixed_links)} link(s): {', '.join(sorted(fixed_links))}")
    if skipped:
        print_fn(
            "Skipped: "
            + ", ".join(f"{name} [{reason}]" for name, reason in skipped.items())
        )
    print_fn(f"Wrote: {output_path}")
    return output_path


def _prompt_boolean(prompt: str, default: Optional[bool] = None) -> bool:
    suffix = " [y/n]"
    if default is True:
        suffix = " [Y/n]"
    elif default is False:
        suffix = " [y/N]"
    while True:
        resp = input(f"{prompt}{suffix}: ").strip().lower()
        if not resp and default is not None:
            return default
        if resp in ("y", "yes"):
            return True
        if resp in ("n", "no"):
            return False
        print("Please answer 'y' or 'n'.")


def _prompt_choice(prompt: str, options: List[str], default_index: int = 0) -> int:
    while True:
        print(prompt)
        for i, opt in enumerate(options, start=1):
            marker = "*" if (i - 1) == default_index else " "; print(f"  {i}. {opt} {marker}")
        resp = input("Enter number: ").strip()
        if not resp:
            return default_index
        try:
            idx = int(resp) - 1
        except ValueError:
            print("Please enter a valid integer.")
            continue
        if 0 <= idx < len(options):
            return idx
        print("Selection out of range.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create a fixed URDF by replacing implausible inertias with geometry-based estimates."
        )
    )
    parser.add_argument(
        "target",
        nargs="?",
        help=(
            "Robot name under robots/ or a path to a URDF file. "
            "If omitted, an interactive selector will be shown."
        ),
    )
    parser.add_argument("--output", type=Path, default=None, help="Output URDF path.")
    parser.add_argument(
        "--include-warnings",
        action="store_true",
        help="Include warning-level issues (not only errors).",
    )
    triangle_group = parser.add_mutually_exclusive_group()
    triangle_group.add_argument(
        "--include-triangle",
        action="store_true",
        help="Include triangle-inequality violations without prompting.",
    )
    triangle_group.add_argument(
        "--skip-triangle",
        action="store_true",
        help="Skip triangle-inequality violations without prompting.",
    )
    parser.add_argument(
        "--prefer-geometry",
        choices=["collision", "visual"],
        default=None,
        help="Preferred geometry when both are present.",
    )
    parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Do not prompt for confirmation.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        urdf_path = resolve_urdf_path(args.target, ROBOTS_DIR)
    except FileNotFoundError as exc:
        print(f"Error: {exc}")
        raise SystemExit(1)

    # Ask severities if not given
    include_warnings: bool
    if args.include_warnings:
        include_warnings = True
    elif args.yes:
        include_warnings = False
    else:
        include_warnings = _prompt_boolean(
            "Fix warning-level issues in addition to errors?", default=False
        )

    if args.include_triangle:
        include_triangle = True
    elif args.skip_triangle:
        include_triangle = False
    elif args.yes:
        include_triangle = True
    else:
        include_triangle = _prompt_boolean(
            "Fix triangle-inequality violations?", default=True
        )

    # Ask geometry preference if not provided
    if args.prefer_geometry is None:
        idx = _prompt_choice(
            "Preferred geometry source (used when both are present):",
            ["collision (recommended)", "visual"],
            default_index=0,
        )
        prefer_collision = (idx == 0)
    else:
        prefer_collision = args.prefer_geometry == "collision"

    output = args.output or urdf_path.with_name(
        urdf_path.stem + "_fixed" + urdf_path.suffix
    )

    if not args.yes:
        proceed = _prompt_boolean(
            f"Proceed to write fixed URDF to {output}?", default=False
        )
        if not proceed:
            print("Aborted.")
            raise SystemExit(0)

    try:
        fix_inertias(
            urdf_path,
            include_warnings=include_warnings,
            include_triangle=include_triangle,
            prefer_collision=prefer_collision,
            output_path=output,
        )
    except SystemExit as exc:
        # Bubble up messages cleanly
        if exc.code and exc.code != 0:
            raise


if __name__ == "__main__":
    main()
