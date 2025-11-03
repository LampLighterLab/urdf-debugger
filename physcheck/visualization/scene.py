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


@dataclass(slots=True)
class TreeEdge:
    """Represents a directed edge between two nodes."""

    parent: str
    child: str
    label: Optional[str] = None
    payload: dict[str, Any] = field(default_factory=dict)


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
        payload = {
            "link": link,
            "inertial": link.inertial,
            "visuals": link.visuals,
            "collisions": link.collisions,
        }
        nodes.append(TreeNode(name=link.name, position=position, payload=payload))

    edges: List[TreeEdge] = []
    for child, parent in tree.child_to_parent.items():
        payload = {"joint": tree.child_to_joint.get(child)}
        edges.append(
            TreeEdge(
                parent=parent,
                child=child,
                label=tree.child_to_joint.get(child),
                payload=payload,
            )
        )

    metadata = {
        "robot_name": tree.model.robot_name,
        "base_link": tree.root,
    }

    return TreeScene(nodes=nodes, edges=edges, metadata=metadata)
