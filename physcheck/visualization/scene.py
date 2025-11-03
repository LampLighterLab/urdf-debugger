from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

import numpy as np

from physcheck.analysis.inertia import InertiaCheck

from .tree import KinematicTree, compute_tree_layout

Position = Tuple[float, float]


def _estimate_collision_eigenvalues(
    collisions: Iterable[Any], mass: float
) -> Optional[np.ndarray]:
    if not np.isfinite(mass) or mass <= 0.0:
        return None

    for collision in collisions:
        geom = getattr(collision, "geometry", None)
        if geom is None:
            continue
        gtype = getattr(geom, "type", "")
        if gtype == "box" and geom.size:
            lx, ly, lz = geom.size
            ixx = (mass / 12.0) * (ly ** 2 + lz ** 2)
            iyy = (mass / 12.0) * (lx ** 2 + lz ** 2)
            izz = (mass / 12.0) * (lx ** 2 + ly ** 2)
            return np.array([ixx, iyy, izz], dtype=float)
        if gtype == "cylinder" and geom.radius and geom.length:
            r = geom.radius
            L = geom.length
            ixx = iyy = (mass / 12.0) * (3.0 * r ** 2 + L ** 2)
            izz = 0.5 * mass * r ** 2
            return np.array([ixx, iyy, izz], dtype=float)
        if gtype == "sphere" and geom.radius:
            r = geom.radius
            moment = 0.4 * mass * r ** 2
            return np.array([moment, moment, moment], dtype=float)
    return None


@dataclass(slots=True)
class TreeNode:
    """Represents a node in a visualization scene."""

    name: str
    position: Position
    payload: dict[str, Any] = field(default_factory=dict)
    visual_style: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class TreeEdge:
    """Represents a directed edge between two nodes."""

    parent: str
    child: str
    label: Optional[str] = None
    payload: dict[str, Any] = field(default_factory=dict)
    visual_style: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class TreeScene:
    """Container for visualization nodes, edges, and metadata."""

    nodes: List[TreeNode]
    edges: List[TreeEdge]
    metadata: dict[str, Any] = field(default_factory=dict)


def build_tree_scene(
    tree: KinematicTree,
    positions: Optional[Mapping[str, Position]] = None,
    inertia_results: Optional[Dict[str, List[InertiaCheck]]] = None,
) -> TreeScene:
    """Construct a :class:`TreeScene` for the provided kinematic tree."""

    if positions is None:
        positions = compute_tree_layout(tree)

    node_lookup: dict[str, Position] = {name: pos for name, pos in positions.items()}
    nodes: List[TreeNode] = []
    severity_lookup: Dict[str, List[InertiaCheck]] = inertia_results or {}
    for link in tree.model.links:
        position = node_lookup.get(link.name, (0.0, 0.0))
        has_inertia = link.inertial is not None
        has_collision = bool(link.collisions)
        checks = severity_lookup.get(link.name, [])
        outline_color, outline_width, status_entries = _derive_status_style(
            checks, has_inertia
        )
        expected = None
        if link.collisions and link.inertial is not None:
            estimated = _estimate_collision_eigenvalues(link.collisions, link.inertial.mass)
            expected = estimated.tolist() if estimated is not None else None
        payload = {
            "link": link,
            "inertial": link.inertial,
            "visuals": link.visuals,
            "collisions": link.collisions,
            "has_inertia": has_inertia,
            "has_collision": has_collision,
            "checks": checks,
            "check_entries": status_entries,
            "visualization": {
                "mass": link.inertial.mass if link.inertial else None,
                "inertia_tensor": list(link.inertial.inertia) if link.inertial else None,
                "expected_eigenvalues": expected,
            },
        }
        collision_fill = "#66bb6a"
        if has_collision:
            fill = collision_fill
        elif has_inertia:
            fill = "#e3f2fd"
        else:
            fill = "#eceff1"
        outline = outline_color
        visual_style = {
            "shape": "ellipse" if has_inertia else "rectangle",
            "fill": fill,
            "outline": outline,
            "font_color": "#000000",
            "outline_width": outline_width,
        }
        nodes.append(
            TreeNode(
                name=link.name,
                position=position,
                payload=payload,
                visual_style=visual_style,
            )
        )

    edges: List[TreeEdge] = []
    for child, parent in tree.child_to_parent.items():
        joint_name = tree.child_to_joint.get(child)
        joint = next((j for j in tree.model.joints if j.name == joint_name), None)
        joint_type = joint.type if joint else None
        payload = {
            "joint": joint_name,
            "joint_type": joint_type,
        }
        stroke = {
            "revolute": "#1976d2",
            "continuous": "#00796b",
            "prismatic": "#f57c00",
            "planar": "#6a1b9a",
            "fixed": "#424242",
        }.get(joint_type or "fixed", "#424242")
        edges.append(
            TreeEdge(
                parent=parent,
                child=child,
                label=tree.child_to_joint.get(child),
                payload=payload,
                visual_style={"stroke": stroke},
            )
        )

    metadata = {
        "robot_name": tree.model.robot_name,
        "base_link": tree.root,
    }

    return TreeScene(nodes=nodes, edges=edges, metadata=metadata)


def _derive_status_style(
    checks: List[InertiaCheck], has_inertia: bool
) -> Tuple[str, int, List[Dict[str, Any]]]:
    severity_rank = {"error": 2, "warning": 1, "info": 0}
    best_severity = "info"
    max_rank = -1
    formatted: List[Dict[str, Any]] = []

    for check in checks:
        if check.passed:
            status = "OK"
            severity = "info"
        elif check.severity == "warning":
            status = "WARN"
            severity = "warning"
        else:
            status = "FAIL"
            severity = "error"

        rank = severity_rank.get(severity, 0)
        if rank > max_rank:
            max_rank = rank
            best_severity = severity

        description = check.message or ""
        detail_text = _format_message(check)
        formatted.append(
            {
                "status": status,
                "severity": severity,
                "headline": check.check,
                "summary": description or detail_text,
                "detail_text": detail_text,
                "details": dict(check.details),
                "passed": check.passed,
                "raw_check": check,
            }
        )

    if best_severity == "error":
        outline = "#c62828"
        width = 5
    elif best_severity == "warning":
        outline = "#f9a825"
        width = 4
    else:
        outline = "#1565c0" if has_inertia else "#90a4ae"
        width = 3 if has_inertia else 2

    return outline, width, formatted


def _format_message(check: InertiaCheck) -> str:
    base = f"{check.check}: {check.message}"
    if check.details:
        detail_text = "; ".join(
            f"{key}={_format_detail_value(value)}"
            for key, value in check.details.items()
        )
        return f"{base} ({detail_text})"
    return base


def _format_detail_value(value: Any) -> Any:
    if isinstance(value, (int, float)):
        return _format_number(value)
    if isinstance(value, Iterable) and not isinstance(value, (str, bytes, dict)):
        return [
            _format_number(item) if isinstance(item, (int, float)) else item
            for item in value
        ]
    return value


def _format_number(number: float) -> str:
    try:
        return f"{float(number):.3e}"
    except (TypeError, ValueError):
        return str(number)
