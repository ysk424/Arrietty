# SPDX-FileCopyrightText: 2026 ysk424
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Generate the large Arrietty flight test world with Blender."""

import argparse
import math
from pathlib import Path
import random
import sys

import bpy
from mathutils import Vector


REPOSITORY_DIR = Path(__file__).resolve().parents[1]
WORLD_WIDTH_M = 3200.0
WORLD_DEPTH_M = 2400.0
ROAD_RADIUS_X_M = 500.0
ROAD_RADIUS_Y_M = 320.0
ROAD_WIDTH_M = 14.0
ROAD_SAMPLES = 384


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=REPOSITORY_DIR / "test_data" / "arrietty_flight_world.blend",
    )
    parser.add_argument("--preview", type=Path)
    arguments = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    return parser.parse_args(arguments)


def _material(
    name: str,
    color: tuple[float, float, float, float],
    *,
    metallic: float = 0.0,
    roughness: float = 0.7,
    emission_strength: float = 0.0,
) -> bpy.types.Material:
    material = bpy.data.materials.new(name)
    material.diffuse_color = color
    material.use_nodes = True
    principled = material.node_tree.nodes.get("Principled BSDF")
    principled.inputs["Base Color"].default_value = color
    principled.inputs["Metallic"].default_value = metallic
    principled.inputs["Roughness"].default_value = roughness
    if emission_strength:
        emission_input = principled.inputs.get("Emission Color")
        if emission_input is None:
            emission_input = principled.inputs.get("Emission")
        emission_input.default_value = color
        principled.inputs["Emission Strength"].default_value = emission_strength
    return material


def _move_to_collection(
    obj: bpy.types.Object,
    collection: bpy.types.Collection,
) -> bpy.types.Object:
    for current_collection in tuple(obj.users_collection):
        current_collection.objects.unlink(obj)
    collection.objects.link(obj)
    return obj


def _box(
    name: str,
    location: tuple[float, float, float],
    dimensions: tuple[float, float, float],
    material: bpy.types.Material,
    collection: bpy.types.Collection,
    *,
    rotation_z: float = 0.0,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cube_add(location=location, rotation=(0.0, 0.0, rotation_z))
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dimensions
    obj.data.materials.append(material)
    return _move_to_collection(obj, collection)


def _terrain_height(x: float, y: float) -> float:
    elliptical_radius = math.sqrt((x / 700.0) ** 2 + (y / 500.0) ** 2)
    blend = max(0.0, min(1.0, (elliptical_radius - 1.12) / 0.55))
    blend = blend * blend * (3.0 - 2.0 * blend)
    rolling = (
        22.0
        + 18.0 * math.sin(x / 180.0) * math.cos(y / 145.0)
        + 10.0 * math.sin((x + y) / 105.0)
    )
    peaks = (
        250.0 * math.exp(-((x + 1120.0) ** 2 + (y - 620.0) ** 2) / 155000.0)
        + 210.0 * math.exp(-((x - 1080.0) ** 2 + (y - 650.0) ** 2) / 180000.0)
        + 170.0 * math.exp(-((x + 1050.0) ** 2 + (y + 700.0) ** 2) / 170000.0)
        + 235.0 * math.exp(-((x - 1120.0) ** 2 + (y + 660.0) ** 2) / 145000.0)
    )
    return max(0.0, blend * (rolling + peaks))


def _create_terrain(
    material: bpy.types.Material,
    collection: bpy.types.Collection,
) -> bpy.types.Object:
    columns = 129
    rows = 97
    vertices = []
    for row in range(rows):
        y = -WORLD_DEPTH_M / 2.0 + WORLD_DEPTH_M * row / (rows - 1)
        for column in range(columns):
            x = -WORLD_WIDTH_M / 2.0 + WORLD_WIDTH_M * column / (columns - 1)
            vertices.append((x, y, _terrain_height(x, y)))

    faces = []
    for row in range(rows - 1):
        for column in range(columns - 1):
            index = row * columns + column
            faces.append((index, index + 1, index + columns + 1, index + columns))

    mesh = bpy.data.meshes.new("FlightWorldTerrainMesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.materials.append(material)
    mesh.update()
    obj = bpy.data.objects.new("Flight World Terrain", mesh)
    collection.objects.link(obj)
    for polygon in mesh.polygons:
        polygon.use_smooth = True
    return obj


def _ellipse_point(parameter: float) -> tuple[Vector, Vector, Vector]:
    center = Vector(
        (
            ROAD_RADIUS_X_M * math.cos(parameter),
            ROAD_RADIUS_Y_M * math.sin(parameter),
            0.06,
        )
    )
    tangent = Vector(
        (
            -ROAD_RADIUS_X_M * math.sin(parameter),
            ROAD_RADIUS_Y_M * math.cos(parameter),
            0.0,
        )
    ).normalized()
    normal = Vector((tangent.y, -tangent.x, 0.0))
    return center, tangent, normal


def _road_length() -> float:
    total = 0.0
    previous, _tangent, _normal = _ellipse_point(0.0)
    for index in range(1, ROAD_SAMPLES + 1):
        current, _tangent, _normal = _ellipse_point(
            math.tau * index / ROAD_SAMPLES
        )
        total += (current - previous).length
        previous = current
    return total


def _create_road(
    road_material: bpy.types.Material,
    line_material: bpy.types.Material,
    collection: bpy.types.Collection,
) -> None:
    vertices = []
    faces = []
    half_width = ROAD_WIDTH_M / 2.0
    for index in range(ROAD_SAMPLES):
        center, _tangent, normal = _ellipse_point(math.tau * index / ROAD_SAMPLES)
        vertices.extend((center + normal * half_width, center - normal * half_width))
    for index in range(ROAD_SAMPLES):
        next_index = (index + 1) % ROAD_SAMPLES
        faces.append((2 * index, 2 * next_index, 2 * next_index + 1, 2 * index + 1))
    mesh = bpy.data.meshes.new("GrandLoopRoadMesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.materials.append(road_material)
    road = bpy.data.objects.new("Grand Loop Road", mesh)
    collection.objects.link(road)

    line_vertices = []
    line_faces = []
    for index in range(0, ROAD_SAMPLES, 4):
        next_index = (index + 2) % ROAD_SAMPLES
        start, _start_tangent, start_normal = _ellipse_point(
            math.tau * index / ROAD_SAMPLES
        )
        end, _end_tangent, end_normal = _ellipse_point(
            math.tau * next_index / ROAD_SAMPLES
        )
        start.z = 0.09
        end.z = 0.09
        half_line_width = 0.16
        offset = len(line_vertices)
        line_vertices.extend(
            (
                start + start_normal * half_line_width,
                end + end_normal * half_line_width,
                end - end_normal * half_line_width,
                start - start_normal * half_line_width,
            )
        )
        line_faces.append((offset, offset + 1, offset + 2, offset + 3))
    line_mesh = bpy.data.meshes.new("GrandLoopCenterLineMesh")
    line_mesh.from_pydata(line_vertices, [], line_faces)
    line_mesh.materials.append(line_material)
    center_line = bpy.data.objects.new("Grand Loop Center Dashes", line_mesh)
    collection.objects.link(center_line)


def _create_gate(
    name: str,
    parameter: float,
    color: bpy.types.Material,
    collection: bpy.types.Collection,
) -> None:
    center, _tangent, normal = _ellipse_point(parameter)
    rotation_z = math.atan2(normal.y, normal.x)
    left = center + normal * 6.0
    right = center - normal * 6.0
    for side, point in (("L", left), ("R", right)):
        _box(
            f"{name} Post {side}",
            (point.x, point.y, 3.5),
            (0.65, 0.65, 7.0),
            color,
            collection,
            rotation_z=rotation_z,
        )
    _box(
        f"{name} Header",
        (center.x, center.y, 7.0),
        (13.0, 0.75, 0.75),
        color,
        collection,
        rotation_z=rotation_z,
    )


def _create_lake(
    water_material: bpy.types.Material,
    island_material: bpy.types.Material,
    collection: bpy.types.Collection,
) -> None:
    bpy.ops.mesh.primitive_cylinder_add(vertices=96, radius=1.0, depth=0.12, location=(-90.0, 0.0, 0.26))
    lake = bpy.context.object
    lake.name = "Mirror Lake"
    lake.scale = (285.0, 165.0, 1.0)
    lake.data.materials.append(water_material)
    _move_to_collection(lake, collection)

    bpy.ops.mesh.primitive_cone_add(
        vertices=48,
        radius1=68.0,
        radius2=28.0,
        depth=16.0,
        location=(-115.0, 5.0, 8.2),
    )
    island = bpy.context.object
    island.name = "Mirror Lake Island"
    island.scale.y = 0.65
    island.data.materials.append(island_material)
    _move_to_collection(island, collection)


def _create_village(
    materials: list[bpy.types.Material],
    collection: bpy.types.Collection,
) -> None:
    random_source = random.Random(424)
    for index in range(28):
        column = index % 7
        row = index // 7
        x = 205.0 + column * 34.0 + random_source.uniform(-5.0, 5.0)
        y = -62.0 + row * 42.0 + random_source.uniform(-5.0, 5.0)
        height = random_source.uniform(12.0, 52.0)
        width = random_source.uniform(14.0, 25.0)
        depth = random_source.uniform(14.0, 25.0)
        _box(
            f"Village Building {index + 1:02d}",
            (x, y, height / 2.0),
            (width, depth, height),
            materials[index % len(materials)],
            collection,
            rotation_z=random_source.uniform(-0.08, 0.08),
        )


def _create_trees(
    trunk_material: bpy.types.Material,
    leaf_material: bpy.types.Material,
    collection: bpy.types.Collection,
) -> None:
    random_source = random.Random(825)
    for index in range(42):
        angle = math.tau * index / 42.0 + random_source.uniform(-0.04, 0.04)
        radius_x = random_source.choice((650.0, 760.0))
        radius_y = random_source.choice((445.0, 535.0))
        x = radius_x * math.cos(angle)
        y = radius_y * math.sin(angle)
        z = _terrain_height(x, y)
        height = random_source.uniform(9.0, 18.0)
        bpy.ops.mesh.primitive_cylinder_add(
            vertices=6,
            radius=0.65,
            depth=height * 0.42,
            location=(x, y, z + height * 0.21),
        )
        trunk = bpy.context.object
        trunk.name = f"Tree {index + 1:02d} Trunk"
        trunk.data.materials.append(trunk_material)
        _move_to_collection(trunk, collection)
        bpy.ops.mesh.primitive_cone_add(
            vertices=8,
            radius1=height * 0.23,
            radius2=0.0,
            depth=height * 0.72,
            location=(x, y, z + height * 0.69),
        )
        crown = bpy.context.object
        crown.name = f"Tree {index + 1:02d} Crown"
        crown.data.materials.append(leaf_material)
        _move_to_collection(crown, collection)


def _create_flight_rings(
    materials: list[bpy.types.Material],
    collection: bpy.types.Collection,
) -> None:
    rings = (
        ((-360.0, -120.0, 10.0), (1.0, 0.2, 0.0)),
        ((-170.0, 105.0, 16.0), (0.8, 0.6, 0.0)),
        ((55.0, 165.0, 22.0), (1.0, 0.0, 0.0)),
        ((305.0, 110.0, 28.0), (0.8, -0.5, 0.0)),
        ((365.0, -105.0, 18.0), (0.1, -1.0, 0.0)),
    )
    for index, (location, direction) in enumerate(rings):
        bpy.ops.mesh.primitive_torus_add(
            align="WORLD",
            major_segments=40,
            minor_segments=8,
            location=location,
            major_radius=7.5,
            minor_radius=0.55,
        )
        ring = bpy.context.object
        ring.name = f"Flight Ring {index + 1}"
        ring.rotation_mode = "QUATERNION"
        ring.rotation_quaternion = Vector((0.0, 0.0, 1.0)).rotation_difference(
            Vector(direction).normalized()
        )
        ring.data.materials.append(materials[index % len(materials)])
        _move_to_collection(ring, collection)


def _create_mountain_caps(
    snow_material: bpy.types.Material,
    beacon_material: bpy.types.Material,
    collection: bpy.types.Collection,
) -> None:
    peaks = ((-1120.0, 620.0), (1080.0, 650.0), (1120.0, -660.0))
    for index, (x, y) in enumerate(peaks):
        ground = _terrain_height(x, y)
        bpy.ops.mesh.primitive_cone_add(
            vertices=12,
            radius1=70.0,
            radius2=2.0,
            depth=58.0,
            location=(x, y, ground + 18.0),
        )
        cap = bpy.context.object
        cap.name = f"Snow Peak {index + 1}"
        cap.data.materials.append(snow_material)
        _move_to_collection(cap, collection)
        bpy.ops.mesh.primitive_uv_sphere_add(
            segments=20,
            ring_count=10,
            radius=5.0,
            location=(x, y, ground + 53.0),
        )
        beacon = bpy.context.object
        beacon.name = f"Mountain Beacon {index + 1}"
        beacon.data.materials.append(beacon_material)
        _move_to_collection(beacon, collection)


def _look_at(obj: bpy.types.Object, target: Vector) -> None:
    obj.rotation_euler = (target - obj.location).to_track_quat("-Z", "Y").to_euler()


def _create_world(output: Path, preview: Path | None) -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.name = "Arrietty Flight World"
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0

    terrain_collection = bpy.data.collections.new("Terrain")
    route_collection = bpy.data.collections.new("Grand Loop")
    landmark_collection = bpy.data.collections.new("Landmarks")
    scene.collection.children.link(terrain_collection)
    scene.collection.children.link(route_collection)
    scene.collection.children.link(landmark_collection)

    grass = _material("Highland Grass", (0.055, 0.24, 0.075, 1.0), roughness=0.95)
    road = _material("Road", (0.035, 0.045, 0.052, 1.0), roughness=0.82)
    road_line = _material("Road Center Line", (1.0, 0.62, 0.06, 1.0), emission_strength=0.35)
    water = _material("Mirror Water", (0.015, 0.19, 0.38, 1.0), metallic=0.15, roughness=0.2)
    island = _material("Island", (0.12, 0.34, 0.09, 1.0), roughness=0.9)
    trunk = _material("Tree Trunks", (0.15, 0.06, 0.025, 1.0), roughness=0.95)
    leaves = _material("Pine Green", (0.015, 0.16, 0.055, 1.0), roughness=0.9)
    snow = _material("Snow Caps", (0.82, 0.91, 0.98, 1.0), roughness=0.65)
    orange = _material("Arrietty Orange", (1.0, 0.16, 0.015, 1.0), emission_strength=1.8)
    cyan = _material("Flight Cyan", (0.0, 0.7, 1.0, 1.0), emission_strength=2.2)
    magenta = _material("Flight Magenta", (1.0, 0.02, 0.45, 1.0), emission_strength=2.2)
    lime = _material("Flight Lime", (0.2, 1.0, 0.05, 1.0), emission_strength=2.2)
    building_materials = [
        _material("Village Ochre", (0.65, 0.22, 0.055, 1.0)),
        _material("Village Gold", (0.8, 0.47, 0.06, 1.0)),
        _material("Village Blue", (0.055, 0.28, 0.65, 1.0)),
        _material("Village White", (0.68, 0.73, 0.72, 1.0)),
    ]

    _create_terrain(grass, terrain_collection)
    _create_road(road, road_line, route_collection)
    _create_lake(water, island, landmark_collection)
    _create_village(building_materials, landmark_collection)
    _create_trees(trunk, leaves, landmark_collection)
    _create_flight_rings([cyan, magenta, lime], landmark_collection)
    _create_mountain_caps(snow, orange, landmark_collection)

    for index, parameter in enumerate(
        (-math.pi / 2.0, -math.pi / 4.0, 0.0, math.pi / 2.0, math.pi)
    ):
        _create_gate(
            "Start Gate" if index == 0 else f"Checkpoint {index}",
            parameter,
            lime if index == 0 else orange,
            route_collection,
        )

    bpy.ops.object.light_add(type="SUN", location=(0.0, 0.0, 900.0))
    sun = bpy.context.object
    sun.name = "Preview Sun (v0.8 sky replaces this)"
    sun.rotation_euler = (math.radians(28.0), math.radians(-18.0), math.radians(32.0))
    sun.data.energy = 2.2
    sun.data.angle = math.radians(8.0)

    world = bpy.data.worlds.new("Temporary Blue World")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (
        0.055,
        0.16,
        0.32,
        1.0,
    )
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.45
    scene.world = world

    bpy.ops.object.camera_add(location=(1220.0, -1580.0, 1180.0))
    camera = bpy.context.object
    camera.name = "World Preview Camera"
    camera.data.lens = 42.0
    camera.data.clip_end = 10000.0
    _look_at(camera, Vector((0.0, 0.0, 35.0)))
    scene.camera = camera

    repository_parent = str(REPOSITORY_DIR.parent)
    if repository_parent not in sys.path:
        sys.path.insert(0, repository_parent)
    import Arrietty

    Arrietty.register()
    lap_length = _road_length()
    scene.arrietty_position = (0.0, -ROAD_RADIUS_Y_M)
    scene.arrietty_heading = 0.0
    scene.arrietty_altitude = 0.0
    scene.arrietty_course_length = lap_length
    scene["arrietty_world_width_m"] = WORLD_WIDTH_M
    scene["arrietty_world_depth_m"] = WORLD_DEPTH_M
    scene["arrietty_lap_length_m"] = lap_length
    scene["arrietty_description"] = "Large ground and flight test world"

    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 960
    scene.render.resolution_y = 600
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(output.resolve()), check_existing=False)

    if preview is not None:
        preview.parent.mkdir(parents=True, exist_ok=True)
        scene.render.filepath = str(preview.resolve())
        bpy.ops.render.render(write_still=True)

    print(
        f"Created {output} — {WORLD_WIDTH_M:.0f} x {WORLD_DEPTH_M:.0f} m, "
        f"lap {lap_length:.1f} m"
    )


if __name__ == "__main__":
    options = _arguments()
    _create_world(options.output, options.preview)
