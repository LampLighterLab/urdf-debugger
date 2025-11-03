from __future__ import annotations

from typing import Dict, List

import numpy as np

from physcheck.analysis import evaluate_link_inertia
from physcheck.urdf.loader import Collision, Geometry, Inertial, Joint, Link, Origin, UrdfModel
from physcheck.urdf.tree import build_kinematic_tree
from physcheck.visualization.scene import build_tree_scene


def _make_single_link_model(link: Link) -> UrdfModel:
    return UrdfModel(
        source_path=None,
        robot_name="dummy",
        links=(link,),
        joints=(),
        base_link=link.name,
    )


def _modified_inertia_checks(link: Link) -> Dict[str, List]:
    checks = evaluate_link_inertia(link)
    for check in checks:
        if check.check == "geometry_consistency":
            # Inject conflicting expected eigenvalues to highlight the mismatch bug.
            check.details["expected_eigenvalues"] = [1.0, 2.0, 3.0]
    return {link.name: checks}


def test_geometry_check_expected_matches_visualization_payload():
    mass = 5.0
    inertia_tensor = (2.0, 0.0, 0.0, 3.0, 0.0, 4.0)

    link = Link(
        name="arm",
        inertial=Inertial(
            mass=mass,
            com=(0.0, 0.0, 0.0),
            inertia=inertia_tensor,
        ),
        collisions=(
            Collision(
                origin=Origin((0.0, 0.0, 0.0), (0.0, 0.0, 0.0)),
                geometry=Geometry(type="box", size=(0.5, 0.5, 0.5)),
            ),
        ),
    )

    model = _make_single_link_model(link)
    tree = build_kinematic_tree(model)
    inertia_results = _modified_inertia_checks(link)
    scene = build_tree_scene(tree, inertia_results=inertia_results)

    node = scene.nodes[0]
    payload = node.payload
    viz = payload.get("visualization", {})

    geom_check = next(
        check for check in payload["checks"] if check.check == "geometry_consistency"
    )

    expected_from_check = geom_check.details.get("expected_eigenvalues")
    expected_from_viz = viz.get("expected_eigenvalues")

    assert expected_from_check is not None
    assert expected_from_viz is not None

    # This assertion documents the current bug: the visualization payload should
    # respect the value provided by the geometry_consistency check.
    assert expected_from_viz == expected_from_check
