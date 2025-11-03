from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Callable, Sequence

from physcheck.analysis import summarize_model_inertia
from physcheck.urdf import build_kinematic_tree, load_urdf
from physcheck.visualization import build_tree_scene, compute_tree_layout
from physcheck.viewers import TkTreeViewer

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
        help="Optional PostScript file path to export the rendering.",
    )
    return parser.parse_args()


def _print_inertia_summary(results: dict[str, list]):
    use_color = sys.stdout.isatty()

    def colorize(text: str, code: str) -> str:
        if not use_color:
            return text
        reset = "\033[0m"
        return f"{code}{text}{reset}"

    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"

    stats = {"ok": 0, "warn": 0, "fail": 0}

    for link_name, checks in results.items():
        print(f"  Link: {link_name}")
        if not checks:
            print("    (no checks run)")
            continue
        for check in checks:
            if check.passed:
                status_label = "OK"
                status_color = GREEN
                stats["ok"] += 1
            elif check.severity == "warning":
                status_label = "WARN"
                status_color = YELLOW
                stats["warn"] += 1
            else:
                status_label = "FAIL"
                status_color = RED
                stats["fail"] += 1

            formatted = colorize(f"[{status_label}]", status_color)
            print(f"    {formatted} {check.check}: {check.message}")
            if check.details:
                for key, value in check.details.items():
                    print(f"      - {key}: {value}")

    summary_parts = []
    if stats["ok"]:
        summary_parts.append(colorize(f"{stats['ok']} ok", GREEN))
    if stats["warn"]:
        summary_parts.append(colorize(f"{stats['warn']} warnings", YELLOW))
    if stats["fail"]:
        summary_parts.append(colorize(f"{stats['fail']} failures", RED))
    if not summary_parts:
        summary_parts.append("no checks run")

    print("  Summary: " + ", ".join(summary_parts))


def main() -> None:
    args = parse_args()
    try:
        urdf_path = resolve_urdf_path(args.target, ROBOTS_DIR)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    model = load_urdf(urdf_path)

    print("Inertia checks:")
    inertia_results = summarize_model_inertia(model.links)
    _print_inertia_summary(inertia_results)
    print("")

    tree = build_kinematic_tree(model)
    positions = compute_tree_layout(tree)
    scene = build_tree_scene(tree, positions, inertia_results)

    viewer = TkTreeViewer(scene, title=f"{model.robot_name} kinematic tree")
    viewer.run(output=args.output)


if __name__ == "__main__":
    main()
