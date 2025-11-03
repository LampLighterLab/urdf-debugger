from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from physcheck.analysis.inertia import InertiaCheck

from .tree import KinematicTree, compute_tree_layout

Position = Tuple[float, float]


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
        payload = {
            "link": link,
            "inertial": link.inertial,
            "visuals": link.visuals,
            "collisions": link.collisions,
            "has_inertia": has_inertia,
            "has_collision": has_collision,
            "checks": checks,
            "check_entries": status_entries,
        }
        collision_fill = "#66bb6a"
        if has_collision:
            fill = collision_fill
            font_color = "#ffffff"
        elif has_inertia:
            fill = "#e3f2fd"
            font_color = "#0d47a1"
        else:
            fill = "#eceff1"
            font_color = "#37474f"
        outline = outline_color
        visual_style = {
            "shape": "ellipse" if has_inertia else "rectangle",
            "fill": fill,
            "outline": outline,
            "font_color": font_color,
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
) -> Tuple[str, int, List[Tuple[str, str]]]:
    severity_rank = {"error": 2, "warning": 1, "info": 0}
    best_severity = "info"
    max_rank = -1
    formatted: List[Tuple[str, str]] = []

    for check in checks:
        if check.passed:
            status = "OK"
            severity = "info"
            text = check.check
        elif check.severity == "warning":
            status = "WARN"
            severity = "warning"
            text = _format_message(check)
        else:
            status = "FAIL"
            severity = "error"
            text = _format_message(check)

        rank = severity_rank.get(severity, 0)
        if rank > max_rank:
            max_rank = rank
            best_severity = severity
        formatted.append((status, text))

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
        return f"{float(number):.3g}"
    except (TypeError, ValueError):
        return str(number)
