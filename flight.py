# SPDX-FileCopyrightText: 2026 ysk424
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Speed-controlled flight mode kept separate from ground-course movement."""

from dataclasses import dataclass

import bpy
from bpy.types import Operator

from . import navigation


TAKEOFF_SPEED_KMH = 10.0
ALTITUDE_METERS_PER_KMH = 1.0


@dataclass(frozen=True)
class FlightSnapshot:
    """Read-only flight state for the UI."""

    enabled: bool
    altitude_m: float


class _FlightRuntime:
    def __init__(self) -> None:
        self.enabled = False
        self.altitude_m = 0.0


_runtime = _FlightRuntime()
_addon_keymaps = []


def altitude_for_speed(speed_kmh: float) -> float:
    """Return height above ground for a trainer speed in km/h."""
    return max(0.0, speed_kmh - TAKEOFF_SPEED_KMH) * ALTITUDE_METERS_PER_KMH


def update_altitude(context: bpy.types.Context, speed_kmh: float) -> bool:
    """Apply the current speed-derived altitude and report whether it changed."""
    altitude_m = altitude_for_speed(speed_kmh) if _runtime.enabled else 0.0
    changed = abs(altitude_m - _runtime.altitude_m) > 1.0e-6
    _runtime.altitude_m = altitude_m
    context.scene.arrietty_altitude = altitude_m
    return changed


def reset(context: bpy.types.Context) -> bool:
    """Return to ground mode and report whether the base pose must be refreshed."""
    changed = _runtime.enabled or abs(_runtime.altitude_m) > 1.0e-6
    _runtime.enabled = False
    _runtime.altitude_m = 0.0
    context.scene.arrietty_altitude = 0.0
    return changed


def snapshot() -> FlightSnapshot:
    return FlightSnapshot(enabled=_runtime.enabled, altitude_m=_runtime.altitude_m)


class ARRIETTY_OT_toggle_flight_mode(Operator):
    """Switch between ground mode and speed-controlled flight mode."""

    bl_idname = "arrietty.toggle_flight_mode"
    bl_label = "Toggle Flight Mode"
    bl_description = "Switch between ground mode and speed-controlled flight mode"

    def execute(self, context: bpy.types.Context) -> set[str]:
        if _runtime.enabled:
            reset(context)
        else:
            _runtime.enabled = True
            update_altitude(context, 0.0)
        navigation.apply_base_pose(context, reset_running=False)
        return {"FINISHED"}


_CLASSES = (ARRIETTY_OT_toggle_flight_mode,)


def _register_keymaps() -> None:
    key_config = bpy.context.window_manager.keyconfigs.addon
    if key_config is None:
        return
    keymap = key_config.keymaps.new(name="3D View", space_type="VIEW_3D")
    item = keymap.keymap_items.new(
        ARRIETTY_OT_toggle_flight_mode.bl_idname,
        type="NUMPAD_ENTER",
        value="PRESS",
    )
    _addon_keymaps.append((keymap, item))


def _unregister_keymaps() -> None:
    for keymap, item in reversed(_addon_keymaps):
        keymap.keymap_items.remove(item)
    _addon_keymaps.clear()


def register() -> None:
    """Register the flight toggle and Numpad Enter shortcut."""
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    _register_keymaps()


def unregister() -> None:
    """Return to ground mode and unregister flight resources."""
    reset(bpy.context)
    _unregister_keymaps()
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
