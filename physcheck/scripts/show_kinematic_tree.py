from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Callable, Sequence

import tkinter as tk
from tkinter import font as tkfont

import networkx as nx

from physcheck.urdf import build_kinematic_tree, load_urdf
from physcheck.visualization import compute_tree_layout

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ROBOTS_DIR = PROJECT_ROOT / "robots"


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
        help="Optional PostScript file path to export the canvas rendering.",
    )
    return parser.parse_args()


class TreeCanvas(tk.Canvas):
    """Canvas widget that renders a kinematic tree."""

    def __init__(
        self,
        master: tk.Misc,
        graph: nx.DiGraph,
        positions: dict[str, tuple[float, float]],
        title: str,
        **kwargs,
    ) -> None:
        super().__init__(master, background="white", highlightthickness=0, **kwargs)
        self.graph = graph
        self.positions = positions
        self.node_font = tkfont.Font(family="Helvetica", size=16, weight="bold")
        self.edge_font = tkfont.Font(family="Helvetica", size=14)
        self.node_boxes: dict[str, tuple[float, float, float, float]] = {}
        master.title(title)
        self.pack(fill="both", expand=True)
        self.bind("<Configure>", self._on_resize)
        self._draw(self.winfo_reqwidth(), self.winfo_reqheight())

    def _on_resize(self, event: tk.Event) -> None:
        self.delete("all")
        self.node_boxes.clear()
        self._draw(event.width, event.height)

    def _draw(self, width: int, height: int) -> None:
        if not self.positions:
            return

        xs = [pos[0] for pos in self.positions.values()]
        ys = [pos[1] for pos in self.positions.values()]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)

        margin_x = 80
        margin_y = 80
        avail_w = max(width - 2 * margin_x, 1)
        avail_h = max(height - 2 * margin_y, 1)
        span_x = max(max_x - min_x, 1e-3)
        span_y = max(max_y - min_y, 1e-3)

        def map_position(x: float, y: float) -> tuple[float, float]:
            px = margin_x + ((x - min_x) / span_x) * avail_w
            # Flip Y so the root (largest y) appears near the top.
            py = margin_y + ((max_y - y) / span_y) * avail_h
            return px, py

        # Pre-compute boxes and render nodes.
        for node, (x, y) in self.positions.items():
            px, py = map_position(x, y)
            text_width = self.node_font.measure(node)
            text_height = self.node_font.metrics("linespace")
            padding_x = 16
            padding_y = 10
            half_w = (text_width / 2) + padding_x
            half_h = (text_height / 2) + padding_y
            x0 = px - half_w
            y0 = py - half_h
            x1 = px + half_w
            y1 = py + half_h
            self.node_boxes[node] = (x0, y0, x1, y1)
            self.create_rectangle(
                x0,
                y0,
                x1,
                y1,
                outline="#1565c0",
                width=2,
                fill="#1976d2",
            )
            self.create_text(
                px,
                py,
                text=node,
                fill="white",
                font=self.node_font,
            )

        # Draw edges after nodes so they sit behind labels.
        for parent, child, data in self.graph.edges(data=True):
            parent_box = self.node_boxes[parent]
            child_box = self.node_boxes[child]
            start_x = (parent_box[0] + parent_box[2]) / 2
            start_y = parent_box[3] - 4
            end_x = (child_box[0] + child_box[2]) / 2
            end_y = child_box[1] + 4
            self.create_line(
                start_x,
                start_y,
                end_x,
                end_y,
                width=2,
                fill="#424242",
                arrow=tk.LAST,
            )
            label = data.get("joint")
            if label:
                mid_x = (start_x + end_x) / 2
                mid_y = (start_y + end_y) / 2 - 10
                self.create_text(
                    mid_x,
                    mid_y,
                    text=label,
                    fill="#424242",
                    font=self.edge_font,
                )

    def save_postscript(self, destination: Path) -> None:
        """Save the current canvas to a PostScript file."""

        self.update_idletasks()
        self.postscript(file=str(destination))


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

    root = tk.Tk()
    root.attributes("-alpha", 0.0)
    root.update_idletasks()
    root.state("zoomed")
    viewer = TreeCanvas(root, graph, positions, f"{model.robot_name} kinematic tree")
    root.deiconify()
    root.attributes("-alpha", 1.0)
    root.lift()
    root.focus_force()

    if args.output:
        try:
            viewer.save_postscript(args.output)
        except tk.TclError as exc:
            print(f"Failed to save canvas: {exc}", file=sys.stderr)

    root.mainloop()


if __name__ == "__main__":
    main()
