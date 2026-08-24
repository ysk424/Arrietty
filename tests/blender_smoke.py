# SPDX-FileCopyrightText: 2026 ysk424
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Registration smoke test executed with Blender in background mode."""

from pathlib import Path
import sys
import tomllib
from types import SimpleNamespace

import bpy


REPOSITORY_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_DIR.parent))

import Arrietty  # noqa: E402
from Arrietty import gui  # noqa: E402


assert bpy.app.version >= (5, 2, 0)
assert gui.VERSION == "0.1.0"
manifest = tomllib.loads(
    (REPOSITORY_DIR / "blender_manifest.toml").read_text(encoding="utf-8")
)
assert manifest["version"] == gui.VERSION
assert gui.ARRIETTY_PT_vr_session.bl_space_type == "VIEW_3D"
assert gui.ARRIETTY_PT_vr_session.bl_region_type == "UI"
assert gui.ARRIETTY_PT_vr_session.bl_category == "Arrietty"


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


stopped_layout = FakeLayout()
gui.ARRIETTY_PT_vr_session.draw(
    SimpleNamespace(layout=stopped_layout),
    bpy.context,
)
assert [label["text"] for label in stopped_layout.labels] == ["Version v0.1.0"]
assert len(stopped_layout.operators) == 1
assert stopped_layout.operators[0][1]["text"] == "Dive into Secret World"

original_is_running = gui._is_vr_session_running
gui._is_vr_session_running = lambda _context: True
try:
    running_layout = FakeLayout()
    gui.ARRIETTY_PT_vr_session.draw(
        SimpleNamespace(layout=running_layout),
        bpy.context,
    )
    assert len(running_layout.operators) == 1
    assert running_layout.operators[0][1]["text"] == "Back to Real World"
finally:
    gui._is_vr_session_running = original_is_running

original_has_openxr_support = gui._has_openxr_support
gui._has_openxr_support = lambda: False
try:
    reports = []
    result = gui.ARRIETTY_OT_toggle_vr_session.execute(
        SimpleNamespace(report=lambda level, message: reports.append((level, message))),
        bpy.context,
    )
    assert result == {"CANCELLED"}
    assert reports == [
        ({"ERROR"}, "OpenXR support is unavailable in this Blender build")
    ]
finally:
    gui._has_openxr_support = original_has_openxr_support

original_toggle_xr_session = gui._toggle_xr_session
gui._has_openxr_support = lambda: True
gui._toggle_xr_session = lambda: {"CANCELLED"}
try:
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
finally:
    gui._has_openxr_support = original_has_openxr_support
    gui._toggle_xr_session = original_toggle_xr_session

Arrietty.register()
try:
    assert hasattr(bpy.types, "ARRIETTY_OT_toggle_vr_session")
    assert hasattr(bpy.types, "ARRIETTY_PT_vr_session")
    assert hasattr(bpy.ops.arrietty, "toggle_vr_session")
    assert hasattr(bpy.ops.wm, "xr_session_toggle")
finally:
    Arrietty.unregister()

assert not hasattr(bpy.types, "ARRIETTY_OT_toggle_vr_session")
assert not hasattr(bpy.types, "ARRIETTY_PT_vr_session")

print("Arrietty Blender smoke test passed")
