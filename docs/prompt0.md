physcheck
=========

## Project Plan

### Phase 1 — URDF ingestion & kinematic inspection
- Build `physcheck.urdf.loader` on top of a lightweight XML parser (no ROS dependencies) to deserialize URDF files into dataclasses that expose links, joints, inertias, and collision geometry.
- Add `physcheck.urdf.tree` utilities to derive parent/child relationships and metadata, exposing both structured data and pre-built NetworkX graphs.
- Provide a CLI entry point (`physcheck cli inspect`) plus a lightweight script (`scripts/show_kinematic_tree.py`) that reuses the tree module to render the kinematic chain.
- Initial GUI prototype (Qt or WebView) will consume the same tree data to display selectable joints/links.
- Unit tests focus on loader correctness and tree construction using fixtures from `robots/`.

### Phase 2 — Physical consistency checks
- Create `physcheck.analysis.inertia` to validate inertia matrices (triangle inequality, positive definiteness, eigenvalue ratios).
- Implement `physcheck.analysis.geometry` to approximate volumes from primitive visual/collision elements and infer density against inertia.
- Add comparison utilities to flag asymmetries between mirrored limbs by pairing links and reporting geometric/inertial differences.
- Extend CLI with `physcheck cli check` that aggregates these analyses and emits machine-readable diagnostics for automation.
- Tests cover analytic edge cases (e.g., singular inertia, mirrored link mismatches) and regression snapshots for known URDFs.

### Phase 3 — Visualization and editing tools
- Build a 3D visualization module (`physcheck.visualization`) backed by `pythreejs` or `vtk` for mesh rendering and frame visualization.
- Layer a selectable scene graph that highlights joints/links, overlays inertia ellipsoids, and displays collision/visual meshes.
- Add interactive editing hooks (e.g., inertia tweaking, symmetry alignment) that feed back into URDF diffs.
- Package a standalone GUI app (Qt/PySide) that orchestrates visualization, analysis, and export workflows.
- Integration tests simulate user flows via headless GUI harnesses where possible; snapshot tests for rendered scenes ensure regression coverage.

### Tooling & environment
- Manage dependencies with `uv`; expose development tasks (lint, test, format, docs) through `uv tool` scripts.
- Adopt `pytest` with hypothesis-based generators for numerical checks, plus golden files for CLI outputs.
- Enable CI (GitHub Actions) to run unit/integration suites and publish artifacts (reports, visualizations).

## Planned Test Suite
- `tests/test_loader.py`: verify URDFs load, links/joints counts match expectations, inertia tensors parse correctly.
- `tests/test_tree.py`: ensure kinematic tree generation yields correct parentage and root detection; round-trip to adjacency lists.
- `tests/test_cli_inspect.py`: smoke-test CLI entry to print the tree and handle invalid paths gracefully.
- `tests/test_inertia_checks.py`: numerical unit tests for triangle inequality, positive-definite detection, eigenvalue ratio thresholds.
- `tests/test_geometry_density.py`: compare computed densities against known fixtures; guard against division-by-zero on missing masses.
- `tests/test_symmetry.py`: mock mirrored link data to ensure asymmetry reports flag mismatching masses/inertia/geometry.
- GUI/visualization tests: screenshot comparisons or geometry hash checks for deterministic rendering once visualization stack lands.
