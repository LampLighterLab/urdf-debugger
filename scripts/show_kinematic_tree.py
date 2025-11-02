from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import matplotlib.pyplot as plt
import networkx as nx

from physcheck.urdf import build_kinematic_tree, load_urdf
from physcheck.visualization import compute_tree_layout


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Visualize the kinematic tree of a URDF file."
    )
    parser.add_argument(
        "urdf_path",
        type=Path,
        help="Path to the URDF file to load.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path to save the rendered tree image.",
    )
    return parser.parse_args()


def draw_tree(graph: nx.DiGraph, positions: dict[str, tuple[float, float]], title: str):
    fig, ax = plt.subplots(figsize=(8, 6))
    nx.draw_networkx(
        graph,
        pos=positions,
        ax=ax,
        node_color="#1976d2",
        node_size=1400,
        font_color="white",
        font_size=10,
        arrows=True,
        arrowsize=15,
        width=1.5,
    )
    edge_labels = {(u, v): data.get("joint", "") for u, v, data in graph.edges(data=True)}
    nx.draw_networkx_edge_labels(graph, pos=positions, edge_labels=edge_labels, ax=ax)
    ax.set_title(title)
    ax.axis("off")
    fig.tight_layout()
    return fig


def main():
    args = parse_args()
    model = load_urdf(args.urdf_path)
    tree = build_kinematic_tree(model)
    graph = tree.to_networkx()
    positions = compute_tree_layout(tree)

    fig = draw_tree(graph, positions, f"{model.robot_name} kinematic tree")

    if args.output:
        fig.savefig(args.output, bbox_inches="tight")
    else:
        plt.show()


if __name__ == "__main__":
    main()
