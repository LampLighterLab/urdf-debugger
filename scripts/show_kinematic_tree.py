from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Callable, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

ROBOTS_DIR = PROJECT_ROOT / "robots"

import matplotlib.pyplot as plt
import networkx as nx

from physcheck.urdf import build_kinematic_tree, load_urdf
from physcheck.visualization import compute_tree_layout


def list_robot_urdfs(robots_root: Path) -> dict[str, list[Path]]:
    """Return a mapping of robot names to URDF files beneath ``robots_root``."""

    if not robots_root.exists():
        return {}

    mapping: dict[str, list[Path]] = {}
    for robot_dir in sorted(robots_root.iterdir(), key=lambda p: p.name.lower()):
        if not robot_dir.is_dir():
            continue
        urdfs = _list_directory_urdfs(robot_dir)
        if urdfs:
            mapping[robot_dir.name] = urdfs
    return mapping


def prompt_choice(
    prompt: str,
    options: Sequence[str],
    input_fn: Callable[[str], str] = input,
    print_fn: Callable[[str], None] = print,
) -> int:
    """Prompt the user to choose from ``options`` and return the selected index."""

    if not options:
        raise ValueError("No options available for selection.")
    if len(options) == 1:
        return 0

    while True:
        print_fn("")
        print_fn(prompt)
        for idx, option in enumerate(options, start=1):
            print_fn(f"  {idx}. {option}")
        response = input_fn("Enter selection number: ").strip()
        try:
            index = int(response)
        except ValueError:
            print_fn("Please enter a valid integer selection.")
            continue
        if 1 <= index <= len(options):
            return index - 1
        print_fn(f"Selection must be between 1 and {len(options)}.")


def _list_directory_urdfs(directory: Path) -> list[Path]:
    def _collect(root: Path) -> list[Path]:
        return sorted(
            (
                path
                for path in root.iterdir()
                if path.is_file() and path.suffix.lower() == ".urdf"
            ),
            key=lambda p: p.name.lower(),
        )

    direct = _collect(directory)
    if direct:
        return direct
    nested = directory / "urdf"
    if nested.is_dir():
        return _collect(nested)
    return []


def resolve_urdf_path(
    target: str | None,
    robots_root: Path,
    *,
    input_fn: Callable[[str], str] = input,
    print_fn: Callable[[str], None] = print,
) -> Path:
    """Resolve the URDF path from an optional name or direct path."""

    robots = list_robot_urdfs(robots_root)
    name_lookup = {name.lower(): name for name in robots}

    if target:
        candidate = Path(target).expanduser()
        if candidate.is_file():
            return candidate.resolve()
        if candidate.is_dir():
            urdfs = _list_directory_urdfs(candidate)
            if not urdfs:
                raise FileNotFoundError(f"No URDF files found under {candidate}")
            if len(urdfs) == 1:
                return urdfs[0].resolve()
            index = prompt_choice(
                f"Select URDF file inside {candidate}:",
                [path.name for path in urdfs],
                input_fn=input_fn,
                print_fn=print_fn,
            )
            return urdfs[index].resolve()
        robot_key = target.lower()
        if robot_key not in name_lookup:
            raise FileNotFoundError(
                f"Robot {target!r} not found under {robots_root}."
            )
        robot_name = name_lookup[robot_key]
        urdf_candidates = robots[robot_name]
    else:
        if not robots:
            raise FileNotFoundError(f"No robots found under {robots_root}.")
        robot_names = list(robots.keys())
        index = prompt_choice(
            "Select a robot:",
            robot_names,
            input_fn=input_fn,
            print_fn=print_fn,
        )
        robot_name = robot_names[index]
        urdf_candidates = robots[robot_name]

    if len(urdf_candidates) == 1:
        return urdf_candidates[0].resolve()

    index = prompt_choice(
        f"Select a URDF for {robot_name}:",
        [path.name for path in urdf_candidates],
        input_fn=input_fn,
        print_fn=print_fn,
    )
    return urdf_candidates[index].resolve()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Visualize the kinematic tree of a URDF file."
    )
    parser.add_argument(
        "target",
        nargs="?",
        help=(
            "Robot name (e.g. 'cartpole') or path to a URDF file. "
            "If omitted, an interactive selector will be shown."
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path to save the rendered tree image.",
    )
    return parser.parse_args()


def draw_tree(
    graph: nx.DiGraph, positions: dict[str, tuple[float, float]], title: str
):
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
    try:
        urdf_path = resolve_urdf_path(args.target, ROBOTS_DIR)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    model = load_urdf(urdf_path)
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
