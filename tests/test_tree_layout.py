from physcheck.urdf import build_kinematic_tree
from physcheck.visualization import compute_tree_layout


def test_tree_layout_depth(cartpole_model):
    tree = build_kinematic_tree(cartpole_model)
    positions = compute_tree_layout(tree)

    assert positions["slider"] == (0.0, 0.0)
    assert positions["cart"] == (0.0, -1.0)
    assert positions["pole"] == (0.0, -2.0)
