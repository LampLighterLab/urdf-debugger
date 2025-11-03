from __future__ import annotations

from typing import Dict, Tuple

from physcheck.urdf.tree import KinematicTree


def compute_tree_layout(tree: KinematicTree) -> Dict[str, Tuple[float, float]]:
    """Compute 2D positions for drawing a kinematic tree top-down.

    The layout groups siblings tightly under their parent using a simple
    Reingold–Tilford-style algorithm. Each leaf occupies a unit width and
    internal nodes are centered above their children.
    """

    spans: Dict[str, float] = {}

    def compute_span(node: str) -> float:
        children = tree.children_of(node)
        if not children:
            spans[node] = 1.0
            return 1.0
        total = 0.0
        for child in children:
            total += compute_span(child)
        spans[node] = max(total, 1.0)
        return spans[node]

    compute_span(tree.root)

    horizontal_spacing = 1.8
    vertical_spacing = 1.2
    positions: Dict[str, Tuple[float, float]] = {}

    def assign_positions(node: str, depth: int, left: float) -> None:
        span = spans[node]
        center = left + span / 2.0
        positions[node] = (
            (center - spans[tree.root] / 2.0) * horizontal_spacing,
            -depth * vertical_spacing,
        )
        children = tree.children_of(node)
        if not children:
            return
        cursor = left
        for child in children:
            assign_positions(child, depth + 1, cursor)
            cursor += spans[child]

    assign_positions(tree.root, 0, 0.0)
    return positions
