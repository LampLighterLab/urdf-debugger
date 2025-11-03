from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Mapping, Optional, Tuple

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
) -> TreeScene:
    """Construct a :class:`TreeScene` for the provided kinematic tree."""

    if positions is None:
        positions = compute_tree_layout(tree)

    node_lookup: dict[str, Position] = {
        name: pos for name, pos in positions.items()
    }
    nodes: List[TreeNode] = []
    for link in tree.model.links:
        position = node_lookup.get(link.name, (0.0, 0.0))
        has_inertia = link.inertial is not None
        has_collision = bool(link.collisions)
        payload = {
            "link": link,
            "inertial": link.inertial,
            "visuals": link.visuals,
            "collisions": link.collisions,
            "has_inertia": has_inertia,
            "has_collision": has_collision,
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
        outline = "#1565c0" if has_inertia else "#90a4ae"
        visual_style = {
            "shape": "ellipse" if has_inertia else "rectangle",
            "fill": fill,
            "outline": outline,
            "font_color": font_color,
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
