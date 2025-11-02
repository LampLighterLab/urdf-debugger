from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterator, Mapping, MutableMapping, Tuple

from .loader import UrdfModel

try:  # pragma: no cover - optional import for visualization only
    import networkx as nx
except ModuleNotFoundError:  # pragma: no cover
    nx = None  # type: ignore[assignment]


@dataclass(slots=True)
class KinematicTree:
    """Represents the parent/child relationships between URDF links."""

    model: UrdfModel
    root: str
    child_to_parent: Mapping[str, str]
    child_to_joint: Mapping[str, str]
    parent_to_children: Mapping[str, Tuple[str, ...]]

    def parent_of(self, link: str) -> str | None:
        return self.child_to_parent.get(link)

    def joint_for(self, child_link: str) -> str | None:
        return self.child_to_joint.get(child_link)

    def children_of(self, link: str) -> Tuple[str, ...]:
        return self.parent_to_children.get(link, ())

    def descendants(self) -> Iterator[str]:
        """Depth-first traversal of the kinematic tree starting at the root."""

        stack = [self.root]
        visited = set()
        while stack:
            node = stack.pop()
            if node in visited:
                continue
            visited.add(node)
            yield node
            stack.extend(reversed(self.children_of(node)))

    def to_networkx(self):
        """Convert the tree to a NetworkX `DiGraph` for visualization."""

        if nx is None:  # pragma: no cover - depends on optional extra
            raise RuntimeError(
                "networkx is not available; install the visualization dependencies."
            )
        graph = nx.DiGraph()
        for link in self.model.link_names:
            graph.add_node(link)
        for child, parent in self.child_to_parent.items():
            graph.add_edge(parent, child, joint=self.child_to_joint[child])
        return graph


def build_kinematic_tree(model: UrdfModel) -> KinematicTree:
    child_to_parent: MutableMapping[str, str] = {}
    child_to_joint: MutableMapping[str, str] = {}
    parent_to_children: MutableMapping[str, list[str]] = {
        link.name: [] for link in model.links
    }

    for joint in model.joints:
        parent = joint.parent
        child = joint.child
        child_to_parent[child] = parent
        child_to_joint[child] = joint.name
        parent_to_children.setdefault(parent, []).append(child)
        parent_to_children.setdefault(child, [])

    frozen_children: Dict[str, Tuple[str, ...]] = {
        link: tuple(children)
        for link, children in parent_to_children.items()
    }
    return KinematicTree(
        model=model,
        root=model.base_link,
        child_to_parent=dict(child_to_parent),
        child_to_joint=dict(child_to_joint),
        parent_to_children=frozen_children,
    )
