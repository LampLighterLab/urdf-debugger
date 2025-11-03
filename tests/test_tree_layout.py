from pytest import approx

from physcheck.urdf import build_kinematic_tree
from physcheck.visualization import compute_tree_layout


def test_tree_layout_depth(cartpole_model):
    tree = build_kinematic_tree(cartpole_model)
    positions = compute_tree_layout(tree)

    assert positions["slider"][0] == approx(0.0)
    assert positions["slider"][1] == approx(0.0)

    assert positions["cart"][0] == approx(0.0)
    assert positions["cart"][1] == approx(positions["slider"][1] - 1.2)

    assert positions["pole"][0] == approx(0.0)
    assert positions["pole"][1] == approx(positions["cart"][1] - 1.2)
