# SPDX-FileCopyrightText: 2026 ysk424
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Registration smoke test executed with Blender in background mode."""

import csv
from pathlib import Path
import math
import sys
import tempfile
import tomllib
from types import SimpleNamespace

import bpy
from mathutils import Quaternion


REPOSITORY_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_DIR.parent))

import Arrietty  # noqa: E402
from Arrietty import flight, gui, navigation, ride_log, steering, trainer  # noqa: E402


assert bpy.app.version >= (5, 2, 0)
assert gui.VERSION == "0.6.5"
manifest = tomllib.loads(
    (REPOSITORY_DIR / "blender_manifest.toml").read_text(encoding="utf-8")
)
assert manifest["version"] == gui.VERSION
assert gui.ARRIETTY_PT_vr_session.bl_space_type == "VIEW_3D"
assert gui.ARRIETTY_PT_vr_session.bl_region_type == "UI"
assert gui.ARRIETTY_PT_vr_session.bl_category == "Arrietty"

viewer_rotation = Quaternion((0.0, 0.0, 1.0), -math.pi / 2.0) @ Quaternion(
    (1.0, 0.0, 0.0),
    math.pi / 2.0,
)
viewer_forward = navigation._forward_from_viewer_rotation(viewer_rotation)
assert viewer_forward is not None
assert math.isclose(viewer_forward.x, 1.0, abs_tol=1.0e-6)
assert math.isclose(viewer_forward.y, 0.0, abs_tol=1.0e-6)
assert viewer_forward.z == 0.0

sample = trainer._parse_indoor_bike_data(bytes.fromhex("44 00 e0 07 b8 00 b0 00"))
assert sample is not None
assert math.isclose(sample.speed_kmh, 20.16)
assert sample.cadence_rpm == 92.0
assert sample.power_w == 176

assert flight.altitude_for_speed(0.0) == 0.0
assert flight.altitude_for_speed(10.0) == 0.0
assert math.isclose(flight.altitude_for_speed(10.1), 0.1)
assert flight.altitude_for_speed(15.0) == 5.0
assert flight.altitude_for_speed(20.0) == 10.0

assert trainer.DEFAULT_COURSE_LENGTH_M == 143.0
assert trainer.completed_laps(0.0, 143.0) == 0
assert trainer.completed_laps(142.9, 143.0) == 0
assert trainer.completed_laps(143.0, 143.0) == 1
assert trainer.completed_laps(571.9, 143.0) == 3
assert trainer.completed_laps(572.0, 143.0) == 4

with tempfile.TemporaryDirectory() as directory:
    first_path = ride_log.start(Path(directory))
    ride_log.record(
        speed_kmh=15.0,
        cadence_rpm=90.0,
        power_w=175,
        distance_m=12.5,
        flight_mode=True,
        altitude_m=5.0,
        target_altitude_m=5.0,
        xr_base_z_m=1.5,
        xr_navigation_z_m=5.0,
        xr_viewer_z_m=6.5,
        x_m=10.0,
        y_m=-2.0,
        heading_degrees=90.0,
    )
    ride_log.stop(event="BACK_TO_REAL_WORLD")
    assert first_path.name == "arrietty_ride.csv"
    with first_path.open(encoding="utf-8", newline="") as log_file:
        first_rows = list(csv.DictReader(log_file))
    assert [row["event"] for row in first_rows] == [
        "START",
        "SAMPLE",
        "BACK_TO_REAL_WORLD",
    ]
    assert first_rows[1]["speed_kmh"] == "15.00"
    assert first_rows[1]["flight_mode"] == "1"
    assert first_rows[1]["altitude_m"] == "5.000"
    assert first_rows[1]["target_altitude_m"] == "5.000"
    assert first_rows[1]["xr_base_z_m"] == "1.500"
    assert first_rows[1]["xr_navigation_z_m"] == "5.000"
    assert first_rows[1]["xr_viewer_z_m"] == "6.500"

    second_path = ride_log.start(Path(directory))
    ride_log.stop()
    assert second_path == first_path
    assert len(list(Path(directory).glob("*.csv"))) == 1
    with second_path.open(encoding="utf-8", newline="") as log_file:
        second_rows = list(csv.DictReader(log_file))
    assert [row["event"] for row in second_rows] == ["START", "STOP"]

direction = trainer._direction_from_heading(0.0)
assert math.isclose(direction[0], 1.0, abs_tol=1.0e-6)
assert math.isclose(direction[1], 0.0, abs_tol=1.0e-6)
direction = trainer._direction_from_heading(math.pi / 2.0)
assert math.isclose(direction[0], 0.0, abs_tol=1.0e-6)
assert math.isclose(direction[1], 1.0, abs_tol=1.0e-6)
direction = trainer._direction_from_heading(math.pi)
assert math.isclose(direction[0], -1.0, abs_tol=1.0e-6)
assert math.isclose(direction[1], 0.0, abs_tol=1.0e-6)
direction = trainer._direction_from_heading(-math.pi / 2.0)
assert math.isclose(direction[0], 0.0, abs_tol=1.0e-6)
assert math.isclose(direction[1], -1.0, abs_tol=1.0e-6)

fake_state = SimpleNamespace(
    navigation_location=(2.0, 3.0, 12.0),
    viewer_pose_location=(10.0, 20.0, 13.5),
)
fake_settings = SimpleNamespace(
    base_pose_type="",
    base_pose_location=(0.0, 0.0, 0.0),
    base_pose_angle=0.0,
    base_scale=0.0,
)
fake_scene = SimpleNamespace(
    arrietty_position=(10.0, 20.0),
    arrietty_heading=0.0,
    arrietty_altitude=5.0,
)
fake_context = SimpleNamespace(
    scene=fake_scene,
    window_manager=SimpleNamespace(
        xr_session_settings=fake_settings,
        xr_session_state=fake_state,
    ),
)
original_navigation_is_running = navigation._is_vr_session_running
navigation._is_vr_session_running = lambda _context: True
try:
    navigation.apply_base_pose(fake_context, reset_running=False)
    assert fake_settings.base_pose_location == (10.0, 20.0, 1.5)
    assert fake_state.navigation_location == (2.0, 3.0, 5.0)
    assert navigation.get_xr_heights(fake_context) == (1.5, 5.0, 13.5)

    fake_scene.arrietty_altitude = 0.0
    navigation.apply_base_pose(fake_context, reset_running=False)
    assert fake_state.navigation_location == (2.0, 3.0, 0.0)
finally:
    navigation._is_vr_session_running = original_navigation_is_running

identity = (
    (1.0, 0.0, 0.0),
    (0.0, 1.0, 0.0),
    (0.0, 0.0, 1.0),
)
left_angle = math.radians(20.0)
left_rotation = (
    (math.cos(left_angle), 0.0, math.sin(left_angle)),
    (0.0, 1.0, 0.0),
    (-math.sin(left_angle), 0.0, math.cos(left_angle)),
)
right_angle = -math.radians(20.0)
right_rotation = (
    (math.cos(right_angle), 0.0, math.sin(right_angle)),
    (0.0, 1.0, 0.0),
    (-math.sin(right_angle), 0.0, math.cos(right_angle)),
)
assert math.isclose(
    steering._world_yaw_from_delta(left_rotation, identity),
    left_angle,
    abs_tol=1.0e-6,
)
assert math.isclose(
    steering._world_yaw_from_delta(right_rotation, identity),
    right_angle,
    abs_tol=1.0e-6,
)
assert math.isclose(
    math.degrees(steering._effective_angle(left_angle)),
    9.25,
    abs_tol=1.0e-6,
)


class FakeOpenVR:
    VRApplication_Background = 3

    def __init__(self) -> None:
        self.init_count = 0

    def init(self, application_type):
        assert application_type == self.VRApplication_Background
        self.init_count += 1
        return object()


fake_openvr = FakeOpenVR()
first_vr = steering._get_openvr_system(fake_openvr)
second_vr = steering._get_openvr_system(fake_openvr)
assert first_vr is second_vr
assert fake_openvr.init_count == 1


class FakeLayout:
    """Record the small subset of Blender UI calls used by the panel."""

    def __init__(self) -> None:
        self.labels = []
        self.operators = []

    def label(self, **kwargs) -> None:
        self.labels.append(kwargs)

    def separator(self) -> None:
        pass

    def operator(self, operator_id, **kwargs) -> None:
        self.operators.append((operator_id, kwargs))

    def box(self):
        return self

    def row(self, **_kwargs):
        return self

    def prop(self, *_args, **_kwargs) -> None:
        pass


Arrietty.register()
original_has_openxr_support = gui._has_openxr_support
original_is_running = gui._is_vr_session_running
original_stop_trainer = trainer.stop_trainer
original_toggle_xr_session = gui._toggle_xr_session
try:
    assert hasattr(bpy.types, "ARRIETTY_OT_toggle_vr_session")
    assert hasattr(bpy.types, "ARRIETTY_OT_navigate")
    assert hasattr(bpy.types, "ARRIETTY_OT_toggle_flight_mode")
    assert hasattr(bpy.types, "ARRIETTY_OT_toggle_trainer")
    assert hasattr(bpy.types, "ARRIETTY_PT_vr_session")
    assert hasattr(bpy.ops.arrietty, "toggle_vr_session")
    assert hasattr(bpy.ops.arrietty, "navigate")
    assert hasattr(bpy.ops.arrietty, "toggle_flight_mode")
    assert hasattr(bpy.ops.arrietty, "toggle_trainer")
    assert hasattr(bpy.ops.wm, "xr_session_toggle")
    assert len(flight._addon_keymaps) == 1
    flight_keymap, flight_keymap_item = flight._addon_keymaps[0]
    assert flight_keymap.name == "3D View"
    assert flight_keymap_item.type == "NUMPAD_7"
    assert flight_keymap_item.value == "PRESS"

    stopped_layout = FakeLayout()
    gui.ARRIETTY_PT_vr_session.draw(
        SimpleNamespace(layout=stopped_layout),
        bpy.context,
    )
    assert stopped_layout.labels[0]["text"] == "Version v0.6.5"
    assert stopped_layout.labels[1]["text"] == "Start Pose"
    assert "Z 1.50 m" in stopped_layout.labels[2]["text"]
    assert len(stopped_layout.operators) == 3
    assert stopped_layout.operators[0][1]["text"] == "Dive into Secret World"

    gui._is_vr_session_running = lambda _context: True
    running_layout = FakeLayout()
    gui.ARRIETTY_PT_vr_session.draw(
        SimpleNamespace(layout=running_layout),
        bpy.context,
    )
    assert len(running_layout.operators) == 3
    assert running_layout.operators[0][1]["text"] == "Back to Real World"
    gui._is_vr_session_running = original_is_running

    gui._has_openxr_support = lambda: False
    reports = []
    result = gui.ARRIETTY_OT_toggle_vr_session.execute(
        SimpleNamespace(report=lambda level, message: reports.append((level, message))),
        bpy.context,
    )
    assert result == {"CANCELLED"}
    assert reports == [
        ({"ERROR"}, "OpenXR support is unavailable in this Blender build")
    ]
    gui._has_openxr_support = original_has_openxr_support

    gui._has_openxr_support = lambda: True
    gui._toggle_xr_session = lambda: {"CANCELLED"}
    reports = []
    result = gui.ARRIETTY_OT_toggle_vr_session.execute(
        SimpleNamespace(report=lambda level, message: reports.append((level, message))),
        bpy.context,
    )
    assert result == {"CANCELLED"}
    assert reports == [
        (
            {"ERROR"},
            "Could not start VR. Start SteamVR, set it as the active "
            "OpenXR runtime, and connect the HMD",
        )
    ]
    gui._has_openxr_support = original_has_openxr_support
    gui._toggle_xr_session = original_toggle_xr_session

    stopped_events = []
    gui._has_openxr_support = lambda: True
    gui._is_vr_session_running = lambda _context: True
    gui._toggle_xr_session = lambda: {"FINISHED"}
    trainer.stop_trainer = lambda _context, **kwargs: stopped_events.append(
        kwargs["log_event"]
    )
    result = gui.ARRIETTY_OT_toggle_vr_session.execute(
        SimpleNamespace(report=lambda _level, _message: None),
        bpy.context,
    )
    assert result == {"FINISHED"}
    assert stopped_events == ["BACK_TO_REAL_WORLD"]
    gui._has_openxr_support = original_has_openxr_support
    gui._is_vr_session_running = original_is_running
    gui._toggle_xr_session = original_toggle_xr_session
    trainer.stop_trainer = original_stop_trainer

    runtime = trainer.get_runtime()
    runtime.status = "RIDING"
    assert bpy.ops.arrietty.toggle_trainer() == {"FINISHED"}
    assert runtime.status == "RIDING"
    assert runtime.message == "Ride continues until Back to Real World"
    runtime.status = "IDLE"

    scene = bpy.context.scene
    scene.arrietty_position = (0.0, 0.0)
    scene.arrietty_heading = 0.0
    scene.arrietty_move_step = 0.5
    scene.arrietty_turn_step = math.radians(5.0)
    scene.arrietty_altitude = 0.0

    assert bpy.ops.arrietty.navigate(action="MOVE_FORWARD") == {"FINISHED"}
    assert tuple(scene.arrietty_position) == (0.5, 0.0)
    assert bpy.context.window_manager.xr_session_settings.base_pose_type == "CUSTOM"
    assert tuple(bpy.context.window_manager.xr_session_settings.base_pose_location) == (
        0.5,
        0.0,
        navigation.EYE_HEIGHT_M,
    )

    assert bpy.ops.arrietty.toggle_flight_mode() == {"FINISHED"}
    assert flight.snapshot().enabled
    assert flight.update_altitude(bpy.context, 15.0)
    navigation.apply_base_pose(bpy.context, reset_running=False)
    assert tuple(bpy.context.window_manager.xr_session_settings.base_pose_location) == (
        0.5,
        0.0,
        navigation.EYE_HEIGHT_M + 5.0,
    )
    assert bpy.ops.arrietty.toggle_flight_mode() == {"FINISHED"}
    assert not flight.snapshot().enabled
    assert scene.arrietty_altitude == 0.0

    assert bpy.ops.arrietty.navigate(action="TURN_LEFT") == {"FINISHED"}
    assert math.isclose(
        scene.arrietty_heading,
        math.radians(5.0),
        abs_tol=1.0e-6,
    )
finally:
    trainer.stop_trainer = original_stop_trainer
    gui._is_vr_session_running = original_is_running
    gui._has_openxr_support = original_has_openxr_support
    gui._toggle_xr_session = original_toggle_xr_session
    Arrietty.unregister()

assert not hasattr(bpy.types, "ARRIETTY_OT_toggle_vr_session")
assert not hasattr(bpy.types, "ARRIETTY_OT_navigate")
assert not hasattr(bpy.types, "ARRIETTY_OT_toggle_flight_mode")
assert not hasattr(bpy.types, "ARRIETTY_OT_toggle_trainer")
assert not hasattr(bpy.types, "ARRIETTY_PT_vr_session")

print("Arrietty Blender smoke test passed")
