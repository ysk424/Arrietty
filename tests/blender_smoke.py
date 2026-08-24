# SPDX-FileCopyrightText: 2026 ysk424
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Registration smoke test executed with Blender in background mode."""

from pathlib import Path
import math
import sys
import tomllib
from types import SimpleNamespace

import bpy
from mathutils import Quaternion


REPOSITORY_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_DIR.parent))

import Arrietty  # noqa: E402
from Arrietty import gui, navigation  # noqa: E402


assert bpy.app.version >= (5, 2, 0)
assert gui.VERSION == "0.3.0"
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
try:
    assert hasattr(bpy.types, "ARRIETTY_OT_toggle_vr_session")
    assert hasattr(bpy.types, "ARRIETTY_OT_navigate")
    assert hasattr(bpy.types, "ARRIETTY_PT_vr_session")
    assert hasattr(bpy.ops.arrietty, "toggle_vr_session")
    assert hasattr(bpy.ops.arrietty, "navigate")
    assert hasattr(bpy.ops.wm, "xr_session_toggle")

    stopped_layout = FakeLayout()
    gui.ARRIETTY_PT_vr_session.draw(
        SimpleNamespace(layout=stopped_layout),
        bpy.context,
    )
    assert stopped_layout.labels[0]["text"] == "Version v0.3.0"
    assert stopped_layout.labels[1]["text"] == "Start Pose"
    assert "Z 1.50 m" in stopped_layout.labels[2]["text"]
    assert len(stopped_layout.operators) == 1
    assert stopped_layout.operators[0][1]["text"] == "Dive into Secret World"

    original_is_running = gui._is_vr_session_running
    gui._is_vr_session_running = lambda _context: True
    running_layout = FakeLayout()
    gui.ARRIETTY_PT_vr_session.draw(
        SimpleNamespace(layout=running_layout),
        bpy.context,
    )
    assert len(running_layout.operators) == 1
    assert running_layout.operators[0][1]["text"] == "Back to Real World"
    gui._is_vr_session_running = original_is_running

    original_has_openxr_support = gui._has_openxr_support
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

    original_toggle_xr_session = gui._toggle_xr_session
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

    scene = bpy.context.scene
    scene.arrietty_position = (0.0, 0.0)
    scene.arrietty_heading = 0.0
    scene.arrietty_move_step = 0.5
    scene.arrietty_turn_step = math.radians(5.0)

    assert bpy.ops.arrietty.navigate(action="MOVE_FORWARD") == {"FINISHED"}
    assert tuple(scene.arrietty_position) == (0.0, 0.5)
    assert bpy.context.window_manager.xr_session_settings.base_pose_type == "CUSTOM"
    assert tuple(bpy.context.window_manager.xr_session_settings.base_pose_location) == (
        0.0,
        0.5,
        navigation.EYE_HEIGHT_M,
    )

    assert bpy.ops.arrietty.navigate(action="TURN_LEFT") == {"FINISHED"}
    assert math.isclose(
        scene.arrietty_heading,
        math.radians(5.0),
        abs_tol=1.0e-6,
    )
finally:
    Arrietty.unregister()

assert not hasattr(bpy.types, "ARRIETTY_OT_toggle_vr_session")
assert not hasattr(bpy.types, "ARRIETTY_OT_navigate")
assert not hasattr(bpy.types, "ARRIETTY_PT_vr_session")

print("Arrietty Blender smoke test passed")
