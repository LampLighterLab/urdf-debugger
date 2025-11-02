from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Tuple


def _parse_vector3(raw: str, default: Tuple[float, float, float]) -> Tuple[float, float, float]:
    if raw is None:
        return default
    parts = [p for p in raw.strip().split() if p]
    if len(parts) != 3:
        raise ValueError(f"Expected 3 components in vector, got {raw!r}")
    return tuple(float(p) for p in parts)  # type: ignore[return-value]


def _parse_rpy(raw: str | None) -> Tuple[float, float, float]:
    return _parse_vector3(raw or "0 0 0", (0.0, 0.0, 0.0))


@dataclass(slots=True, frozen=True)
class Origin:
    xyz: Tuple[float, float, float]
    rpy: Tuple[float, float, float]


@dataclass(slots=True, frozen=True)
class Inertial:
    mass: float
    com: Tuple[float, float, float]
    inertia: Tuple[float, float, float, float, float, float]  # ixx, ixy, ixz, iyy, iyz, izz


@dataclass(slots=True, frozen=True)
class Geometry:
    type: str
    size: Tuple[float, float, float] | None = None
    radius: float | None = None
    length: float | None = None
    filename: str | None = None


@dataclass(slots=True, frozen=True)
class Visual:
    origin: Origin
    geometry: Geometry
    material: str | None


@dataclass(slots=True, frozen=True)
class Collision:
    origin: Origin
    geometry: Geometry


@dataclass(slots=True, frozen=True)
class Link:
    name: str
    inertial: Inertial | None = None
    visuals: Tuple[Visual, ...] = ()
    collisions: Tuple[Collision, ...] = ()


@dataclass(slots=True, frozen=True)
class Joint:
    name: str
    type: str
    parent: str
    child: str
    origin: Origin
    axis: Tuple[float, float, float] | None
    limit: dict[str, float]


@dataclass(slots=True)
class UrdfModel:
    """Lightweight URDF container with cached metadata."""

    source_path: Path
    robot_name: str
    links: Tuple[Link, ...]
    joints: Tuple[Joint, ...]
    base_link: str

    @property
    def link_names(self) -> Tuple[str, ...]:
        return tuple(link.name for link in self.links)

    @property
    def joint_names(self) -> Tuple[str, ...]:
        return tuple(joint.name for joint in self.joints)

    def iter_links(self) -> Iterable[Link]:
        return iter(self.links)

    def iter_joints(self) -> Iterable[Joint]:
        return iter(self.joints)

    def link(self, name: str) -> Link:
        for link in self.links:
            if link.name == name:
                return link
        raise KeyError(f"Link {name!r} not found")


def _parse_origin(element: ET.Element | None) -> Origin:
    if element is None:
        return Origin((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
    xyz = _parse_vector3(element.attrib.get("xyz", "0 0 0"), (0.0, 0.0, 0.0))
    rpy = _parse_rpy(element.attrib.get("rpy"))
    return Origin(xyz, rpy)


def _parse_geometry(element: ET.Element) -> Geometry:
    if (box := element.find("box")) is not None:
        size = _parse_vector3(box.attrib["size"], (1.0, 1.0, 1.0))
        return Geometry(type="box", size=size)
    if (cylinder := element.find("cylinder")) is not None:
        radius = float(cylinder.attrib["radius"])
        length = float(cylinder.attrib["length"])
        return Geometry(type="cylinder", radius=radius, length=length)
    if (sphere := element.find("sphere")) is not None:
        radius = float(sphere.attrib["radius"])
        return Geometry(type="sphere", radius=radius)
    if (mesh := element.find("mesh")) is not None:
        filename = mesh.attrib.get("filename")
        scale = mesh.attrib.get("scale")
        geom = Geometry(type="mesh", filename=filename)
        if scale:
            values = _parse_vector3(scale, (1.0, 1.0, 1.0))
            geom = Geometry(type="mesh", filename=filename, size=values)
        return geom
    return Geometry(type="unknown")


def _parse_inertial(element: ET.Element | None) -> Inertial | None:
    if element is None:
        return None
    mass_el = element.find("mass")
    inertia_el = element.find("inertia")
    if mass_el is None or inertia_el is None:
        return None
    mass = float(mass_el.attrib["value"])
    origin = _parse_origin(element.find("origin"))
    inertia = (
        float(inertia_el.attrib.get("ixx", "0")),
        float(inertia_el.attrib.get("ixy", "0")),
        float(inertia_el.attrib.get("ixz", "0")),
        float(inertia_el.attrib.get("iyy", "0")),
        float(inertia_el.attrib.get("iyz", "0")),
        float(inertia_el.attrib.get("izz", "0")),
    )
    return Inertial(mass=mass, com=origin.xyz, inertia=inertia)


def _parse_visuals(parent: ET.Element) -> Tuple[Visual, ...]:
    visuals = []
    for visual in parent.findall("visual"):
        origin = _parse_origin(visual.find("origin"))
        geometry_el = visual.find("geometry")
        if geometry_el is None:
            continue
        geometry = _parse_geometry(geometry_el)
        material_el = visual.find("material")
        material = material_el.attrib.get("name") if material_el is not None else None
        visuals.append(Visual(origin=origin, geometry=geometry, material=material))
    return tuple(visuals)


def _parse_collisions(parent: ET.Element) -> Tuple[Collision, ...]:
    collisions = []
    for collision in parent.findall("collision"):
        origin = _parse_origin(collision.find("origin"))
        geometry_el = collision.find("geometry")
        if geometry_el is None:
            continue
        geometry = _parse_geometry(geometry_el)
        collisions.append(Collision(origin=origin, geometry=geometry))
    return tuple(collisions)


def _parse_links(robot: ET.Element) -> Tuple[Link, ...]:
    links = []
    for link_el in robot.findall("link"):
        name = link_el.attrib["name"]
        inertial = _parse_inertial(link_el.find("inertial"))
        visuals = _parse_visuals(link_el)
        collisions = _parse_collisions(link_el)
        links.append(Link(name=name, inertial=inertial, visuals=visuals, collisions=collisions))
    return tuple(links)


def _parse_joint(element: ET.Element) -> Joint:
    name = element.attrib["name"]
    joint_type = element.attrib.get("type", "fixed")
    parent_el = element.find("parent")
    child_el = element.find("child")
    if parent_el is None or child_el is None:
        raise ValueError(f"Joint {name} is missing parent or child link")
    parent = parent_el.attrib["link"]
    child = child_el.attrib["link"]
    origin = _parse_origin(element.find("origin"))
    axis_el = element.find("axis")
    axis = _parse_vector3(axis_el.attrib["xyz"], (0.0, 0.0, 1.0)) if axis_el is not None else None
    limit: dict[str, float] = {}
    if (limit_el := element.find("limit")) is not None:
        for key, value in limit_el.attrib.items():
            try:
                limit[key] = float(value)
            except ValueError:
                continue
    return Joint(
        name=name,
        type=joint_type,
        parent=parent,
        child=child,
        origin=origin,
        axis=axis,
        limit=limit,
    )


def _parse_joints(robot: ET.Element) -> Tuple[Joint, ...]:
    return tuple(_parse_joint(joint_el) for joint_el in robot.findall("joint"))


def _detect_base_link(links: Tuple[Link, ...], joints: Tuple[Joint, ...]) -> str:
    child_links = {joint.child for joint in joints}
    for link in links:
        if link.name not in child_links:
            return link.name
    return links[0].name if links else ""


def load_urdf(path: Path | str) -> UrdfModel:
    resolved = Path(path).expanduser().resolve()
    tree = ET.parse(resolved)
    robot = tree.getroot()
    if robot.tag != "robot":
        raise ValueError(f"Expected root <robot> element, got <{robot.tag}>")
    links = _parse_links(robot)
    joints = _parse_joints(robot)
    base_link = _detect_base_link(links, joints)
    return UrdfModel(
        source_path=resolved,
        robot_name=robot.attrib.get("name", resolved.stem),
        links=links,
        joints=joints,
        base_link=base_link,
    )
