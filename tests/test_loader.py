from physcheck.urdf import build_kinematic_tree


def test_loads_cartpole(cartpole_model):
    assert cartpole_model.robot_name == "cartpole"
    assert cartpole_model.base_link == "slider"
    assert "cart" in cartpole_model.link_names
    assert "pole" in cartpole_model.link_names
    assert cartpole_model.source_path.name == "cartpole.urdf"


def test_kinematic_tree_structure(cartpole_model):
    tree = build_kinematic_tree(cartpole_model)
    assert tree.root == "slider"
    assert tree.parent_of("cart") == "slider"
    assert tree.joint_for("cart") == "slider_to_cart"
    assert tree.children_of("slider") == ("cart",)
    assert set(tree.descendants()) == {"slider", "cart", "pole"}
    assert tree.children_of("cart") == ("pole",)
    assert tree.joint_for("pole") == "cart_to_pole"
