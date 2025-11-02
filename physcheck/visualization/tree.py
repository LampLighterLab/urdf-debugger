from __future__ import annotations

from collections import deque
from typing import Dict, List, Tuple

from physcheck.urdf.tree import KinematicTree


def compute_tree_layout(tree: KinematicTree) -> Dict[str, Tuple[float, float]]:
    """Compute 2D positions for drawing a kinematic tree top-down."""

    levels: Dict[int, List[str]] = {}
    queue = deque([(tree.root, 0)])
    seen = set()

    while queue:
        node, depth = queue.popleft()
        if node in seen:
            continue
        seen.add(node)
        levels.setdefault(depth, []).append(node)
        for child in tree.children_of(node):
            queue.append((child, depth + 1))

    positions: Dict[str, Tuple[float, float]] = {}
    for depth in sorted(levels):
        nodes = levels[depth]
        count = len(nodes)
        if count == 1:
            positions[nodes[0]] = (0.0, -float(depth))
            continue
        spacing = 1.5
        offset = -(count - 1) * spacing / 2.0
        for index, node in enumerate(nodes):
            positions[node] = (offset + index * spacing, -float(depth))

    return positions
