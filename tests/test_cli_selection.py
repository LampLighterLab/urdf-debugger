import pytest

from physcheck.scripts.show_kinematic_tree import ROBOTS_DIR, list_robot_urdfs, resolve_urdf_path


def _silent_print(_: str) -> None:  # pragma: no cover - helper for tests
    return None


def test_resolve_by_direct_path():
    explicit = ROBOTS_DIR / "cartpole" / "urdf" / "cartpole.urdf"
    resolved = resolve_urdf_path(str(explicit), ROBOTS_DIR, print_fn=_silent_print)
    assert resolved == explicit.resolve()


def test_resolve_by_robot_name_single_urdf():
    resolved = resolve_urdf_path("cartpole", ROBOTS_DIR, print_fn=_silent_print)
    assert resolved.name == "cartpole.urdf"
    assert resolved.parent == (ROBOTS_DIR / "cartpole" / "urdf").resolve()


def test_resolve_by_robot_with_multiple_urdfs(monkeypatch):
    inputs = iter(["2"])
    resolved = resolve_urdf_path(
        "mini_cheetah",
        ROBOTS_DIR,
        input_fn=lambda _: next(inputs),
        print_fn=_silent_print,
    )
    assert resolved.name == "mini_cheetah_simple.urdf"


def test_interactive_robot_selection(monkeypatch):
    inputs = iter(["3"])
    resolved = resolve_urdf_path(
        None,
        ROBOTS_DIR,
        input_fn=lambda _: next(inputs),
        print_fn=_silent_print,
    )
    assert resolved.name == "cartpole.urdf"


def test_invalid_robot_name():
    with pytest.raises(FileNotFoundError):
        resolve_urdf_path("does_not_exist", ROBOTS_DIR, print_fn=_silent_print)


def test_case_insensitive_urdf_suffix(tmp_path):
    robot_dir = tmp_path / "ExampleBot"
    urdf_dir = robot_dir / "urdf"
    urdf_dir.mkdir(parents=True)
    uppercase = urdf_dir / "example.URDF"
    uppercase.write_text("<robot name='example'/>")

    robots = list_robot_urdfs(tmp_path)
    assert "ExampleBot" in robots
    assert robots["ExampleBot"][0] == uppercase
