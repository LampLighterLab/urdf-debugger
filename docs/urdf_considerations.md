URDF Integration Considerations
===============================

This note distills guidance from the official ROS tutorials, the ROS 2 documentation, MuJoCo’s modeling guide, and NVIDIA Isaac Sim’s URDF importer docs to surface constraints that Physcheck should account for.

ROS Tutorials: Core Modeling Patterns
-------------------------------------
- URDF describes a rooted tree of `link` and `joint` elements; each joint names a parent and child link, so the kinematic tree cannot contain cycles natively. This structure underpins `joint_state_publisher` and `robot_state_publisher`, which generate TF frames for visualization in RViz. [ROS URDF Tutorial][ros-tut]
- Separate `visual` and `collision` sub-elements per link enable distinct meshes. Collision geometry is often simplified (boxes, cylinders) to reduce contact solver cost, or intentionally inflated to create “keep-out” zones. Origins (`xyz`, `rpy`) on both visuals and joints define alignment and must be managed carefully to avoid overlapping or misaligned parts.
- Joint types matter for downstream tooling: `continuous`, `revolute`, `prismatic`, `planar`, and `floating` joints have different limit semantics (angles vs. meters) and default axes. Limits, effort, and velocity tags are required for non-fixed joints to drive GUI sliders and controllers.
- Materials and color definitions are optional but allow shared palettes across links. Tutorials recommend extracting common elements into named materials and reusing them by reference.
- Inertial modeling is critical for simulation fidelity. Each simulated link needs a `<mass>` and `<inertia>` tensor. Tutorial guidance warns against unrealistic defaults (e.g., identity matrices) and suggests computing moments for primitive shapes when CAD data is unavailable. Center-of-mass offsets can be provided via an `origin` inside `<inertial>`.
- Joint `dynamics` (friction, damping) and collision `contact_coefficients` are part of the URDF spec even if not always exported; tools should flag near-zero inertias or absent damping that can destabilize real-time controllers.
- Complex robots rely on Xacro macros (`<xacro:...>`), includes, and parameter substitution to stay maintainable. Physcheck should either expand Xacro before analysis or provide warnings when macros remain unresolved, because structure may not be visible until expansion.

ROS 2 Documentation: Workflow Expectations
------------------------------------------
- The ROS 2 URDF overview mostly curates the tutorial series but reinforces that URDF files are typically generated via launch-time macro expansion and loaded onto the parameter server before visualization or simulation. Any analysis pipeline must therefore tolerate inline Xacro, include relative paths, and ROS-specific resource resolution (e.g., `$(find package)` macro). [ROS 2 URDF Docs][ros2-urdf]

MuJoCo: URDF Support and Extensions
-----------------------------------
- MuJoCo loads URDF as a subset of MJCF features; unsupported constructs require conversion to full MJCF. URDF files may embed a `<mujoco>` child under the root `<robot>` to override compiler defaults, physics options, or mesh lookup paths. Attributes like `balanceinertia`, `discardvisual`, `fusestatic`, and `strippath` have URDF-specific defaults to accommodate legacy models with imperfect physical parameters. [MuJoCo Modeling Guide][mujoco-modeling]
- The MuJoCo parser does not validate URDF against a schema; misspelled attributes are silently ignored, making automated linting valuable. Physcheck should surface unknown tags/attributes when targeting MuJoCo users.
- MJCF organizes nested `<body>` elements, contrasting with URDF’s flat link list plus parent pointers. When exporting from URDF, MuJoCo nests child bodies directly under parents. Physcheck should verify that parent-child relationships match expectations when users round-trip between formats.

Isaac Sim URDF Importer: USD Conversion Gotchas
-----------------------------------------------
- Import options differentiate between “Moveable base” vs. “Static base”, setting whether the base link is fixed via a generated `root_joint`. Links without explicit mass can use a “Default Density” fallback; setting this to zero defers to the physics engine’s default density. [Isaac Sim URDF Importer][isaac-urdf]
- Collision conversion offers convex hull and convex decomposition modes, plus an option to replace cylinders with capsules. Enabling “Allow self-collision” may destabilize models if colliders intersect at joints, so pre-checks for intersecting collision meshes are useful.
- Joint drives can be tuned by stiffness/damping or by specifying a desired natural frequency and damping ratio; the importer converts these to PhysX drive parameters. Verifying consistent units (rad vs. m) and highlighting missing limits remain important.
- The importer sanitizes names (replacing disallowed characters and adding prefixes when necessary) to satisfy USD prim naming rules. Physcheck should warn when sanitized names drift from the URDF source so downstream tooling stays consistent.
- Isaac Sim defines extra tags: `loop_joint` closes kinematic cycles (not supported in vanilla URDF), `fixed_frame` defines named frames without extra links, and `sensor` elements accept an `isaac_sim_config` attribute pointing to built-in or custom sensor profiles. Recognizing—but not misinterpreting—these extensions will prevent false alarms.
- Logs are emitted to the Output Log and main log file; aligning Physcheck diagnostics with these conventions will help users resolve import issues rapidly.

Implications for Physcheck
--------------------------
- Structural validation must respect URDF trees, differentiating visual vs. collision frames, and reporting links lacking inertia or mass.
- Provide heuristics or calculators for primitive inertias, mass-density inference, and mismatches between collision volume and mass to help users tune physical plausibility.
- Surface warnings about missing joint limits/dynamics, mimic relationships, and axis definitions that differ from ROS expectations.
- Detect simulator-specific extensions (`<mujoco>`, Isaac-specific tags) and either parse them or clearly state when they are ignored.
- Flag naming or path constructs that could break downstream tools (e.g., unresolved `$(find ...)`, invalid characters before importer sanitization).
- Encourage workflows that expand Xacro before running checks or integrate with the ROS package path to evaluate macros safely.

References
----------
- [ROS URDF Tutorial][ros-tut]
- [ROS 2 URDF Overview][ros2-urdf]
- [MuJoCo Modeling Guide – URDF extensions][mujoco-modeling]
- [Isaac Sim URDF Importer Docs][isaac-urdf]

[ros-tut]: https://github.com/ros/urdf_tutorial
[ros2-urdf]: https://docs.ros.org/en/rolling/Tutorials/Intermediate/URDF/URDF-Main.html
[mujoco-modeling]: https://mujoco.readthedocs.io/en/stable/modeling.html#urdf-extensions
[isaac-urdf]: https://docs.isaacsim.omniverse.nvidia.com/latest/importer_exporter/ext_isaacsim_asset_importer_urdf.html
