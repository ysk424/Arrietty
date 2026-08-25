# SPDX-FileCopyrightText: 2026 ysk424
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Validate the generated large flight-world blend file."""

import math
from pathlib import Path
import sys

import bpy
from mathutils import Vector


REPOSITORY_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_DIR.parent))

import Arrietty  # noqa: E402


assert bpy.app.version >= (5, 2, 0)
assert Path(bpy.data.filepath).name == "arrietty_flight_world.blend"

Arrietty.register()
try:
    scene = bpy.context.scene
    assert scene.name == "Arrietty Flight World"
    assert scene.unit_settings.scale_length == 1.0
    assert scene["arrietty_world_width_m"] == 3200.0
    assert scene["arrietty_world_depth_m"] == 2400.0
    assert 2600.0 < scene["arrietty_lap_length_m"] < 2610.0
    assert math.isclose(
        scene.arrietty_course_length,
        scene["arrietty_lap_length_m"],
        abs_tol=1.0e-3,
    )
    assert tuple(scene.arrietty_position) == (0.0, -320.0)
    assert scene.arrietty_heading == 0.0

    terrain = bpy.data.objects["Flight World Terrain"]
    assert len(terrain.data.vertices) == 12513
    road = bpy.data.objects["Grand Loop Road"]
    road_corners = [road.matrix_world @ Vector(corner) for corner in road.bound_box]
    assert max(point.x for point in road_corners) - min(
        point.x for point in road_corners
    ) > 1000.0
    assert max(point.y for point in road_corners) - min(
        point.y for point in road_corners
    ) > 640.0
    assert len([obj for obj in bpy.data.objects if obj.name.startswith("Flight Ring")]) == 5
    assert "Mirror Lake" in bpy.data.objects
    assert "Start Gate Header" in bpy.data.objects
finally:
    Arrietty.unregister()

print("Arrietty flight world smoke test passed")
