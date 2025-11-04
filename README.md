physcheck
=========

Lightweight URDF inspector that checks inertia tensors and kinematics, shows a simple tree viewer, and can auto-fix implausible inertias from link geometry.

Quickstart
----------

Requirements
- Python >= 3.13
- [uv](https://docs.astral.sh/uv/getting-started/installation/) (recommended)

Install (editable)
- `uv venv`
- `uv pip install -e .`

Run the tests
- `uv run pytest -q`

Use
- Kinematic tree + inertia summary:
  - Interactive under `robots/`: `uv run python -m physcheck.scripts.show_kinematic_tree`
  - By name: `uv run python -m physcheck.scripts.show_kinematic_tree cartpole`
  - By path: `uv run python -m physcheck.scripts.show_kinematic_tree robots/cartpole/urdf/cartpole.urdf`
  - Headless (no GUI): add `--no-gui` to print only the summary
  - Export viewer to PostScript: add `--output out.ps`

- Auto-fix implausible inertias from geometry:
  - `uv run python -m physcheck.scripts.fix_inertials cartpole`
  - Flags:
    - `--include-warnings` to also fix warning-level issues
    - `--include-triangle` or `--skip-triangle` to control triangle-inequality fixes non-interactively
    - `--prefer-geometry {collision,visual}` to pick geometry when both exist
    - `--output PATH` to choose output (defaults to `*_fixed.urdf` next to source)
    - `-y/--yes` to skip prompts
  - Notes:
    - Only box, cylinder, and sphere primitives are used to estimate inertia
    - Mass is preserved; the tensor is rotated into the link frame, and inertial origin rpy is set to zero so components match link axes
    - Mesh-only links are skipped

