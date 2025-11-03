from physcheck.analysis import evaluate_link_inertia
from physcheck.urdf.loader import Collision, Geometry, Inertial, Link, Origin


def test_missing_inertial_flagged():
    link = Link(name="test_link")
    results = evaluate_link_inertia(link)
    assert results and results[0].check == "inertial_present"
    assert not results[0].passed


def test_negative_mass_detected():
    inertial = Inertial(
        mass=-1.0,
        com=(0.0, 0.0, 0.0),
        inertia=(1.0, 0.0, 0.0, 1.0, 0.0, 1.0),
    )
    link = Link(name="negative_mass", inertial=inertial)
    results = evaluate_link_inertia(link)
    found = {res.check: res for res in results}
    assert not found["mass_positive"].passed


def test_geometry_consistency_runs_for_box():
    inertial = Inertial(
        mass=10.0,
        com=(0.0, 0.0, 0.0),
        inertia=(10.0, 0.0, 0.0, 10.0, 0.0, 10.0),
    )
    collision = Collision(
        origin=Origin((0.0, 0.0, 0.0), (0.0, 0.0, 0.0)),
        geometry=Geometry(type="box", size=(1.0, 1.0, 1.0)),
    )
    link = Link(name="box", inertial=inertial, collisions=(collision,))
    results = evaluate_link_inertia(link)
    checks = {res.check: res for res in results}
    assert "geometry_consistency" in checks
