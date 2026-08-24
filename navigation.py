# SPDX-FileCopyrightText: 2026 ysk424
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Event-driven numpad navigation for the Arrietty XR base pose."""

import math

import bpy
from bpy.props import EnumProperty, FloatProperty, FloatVectorProperty
from bpy.types import Operator
from mathutils import Quaternion, Vector


EYE_HEIGHT_M = 1.5
DEFAULT_MOVE_STEP_M = 0.5
DEFAULT_TURN_STEP_DEGREES = 5.0

_KEYMAP_ITEMS = (
    ("NUMPAD_4", "TURN_LEFT"),
    ("NUMPAD_6", "TURN_RIGHT"),
    ("NUMPAD_8", "MOVE_FORWARD"),
    ("NUMPAD_2", "MOVE_BACKWARD"),
)
_addon_keymaps = []
_session_yaw_offset = None
_session_state_pointer = None


def _normalized_angle(angle: float) -> float:
    """Wrap an angle to the range -pi through pi."""
    return math.atan2(math.sin(angle), math.cos(angle))


def _is_vr_session_running(context: bpy.types.Context) -> bool:
    """Return whether an OpenXR session is running."""
    try:
        return bpy.types.XrSessionState.is_running(context)
    except (AttributeError, RuntimeError):
        return False


def reset_session_calibration() -> None:
    """Forget the HMD-to-body yaw calibration for the current XR session."""
    global _session_yaw_offset, _session_state_pointer
    _session_yaw_offset = None
    _session_state_pointer = None


def _heading_from_viewer_rotation(rotation) -> float | None:
    """Return the horizontal heading of Blender's XR viewer forward axis."""
    forward = Quaternion(rotation) @ Vector((0.0, 0.0, -1.0))
    if forward.x * forward.x + forward.y * forward.y < 1.0e-8:
        return None
    return math.atan2(-forward.x, forward.y)


def _movement_heading(context: bpy.types.Context, body_heading: float) -> float:
    """Combine body heading with a once-per-session HMD yaw calibration."""
    global _session_yaw_offset, _session_state_pointer

    if not _is_vr_session_running(context):
        reset_session_calibration()
        return body_heading

    state = context.window_manager.xr_session_state
    if state is None:
        return body_heading

    try:
        state_pointer = state.as_pointer()
    except AttributeError:
        state_pointer = id(state)

    if _session_state_pointer != state_pointer:
        _session_yaw_offset = None
        _session_state_pointer = state_pointer

    if _session_yaw_offset is None:
        viewer_heading = _heading_from_viewer_rotation(state.viewer_pose_rotation)
        if viewer_heading is None:
            return body_heading
        _session_yaw_offset = _normalized_angle(viewer_heading - body_heading)

    return _normalized_angle(body_heading + _session_yaw_offset)


def apply_base_pose(context: bpy.types.Context, *, reset_running: bool = True) -> None:
    """Apply the persistent Arrietty start pose to Blender's XR settings."""
    scene = context.scene
    settings = context.window_manager.xr_session_settings
    x, y = scene.arrietty_position

    settings.base_pose_type = "CUSTOM"
    settings.base_pose_location = (x, y, EYE_HEIGHT_M)
    settings.base_pose_angle = scene.arrietty_heading
    settings.base_scale = 1.0

    if reset_running and _is_vr_session_running(context):
        state = context.window_manager.xr_session_state
        if state is not None:
            state.reset_to_base_pose(context)


class ARRIETTY_OT_navigate(Operator):
    """Move or turn the Arrietty XR base pose using the numeric keypad."""

    bl_idname = "arrietty.navigate"
    bl_label = "Adjust Arrietty Start Pose"
    bl_description = "Move or turn the fixed-height Arrietty XR base pose"
    bl_options = {"REGISTER", "UNDO"}

    action: EnumProperty(
        items=(
            ("TURN_LEFT", "Turn Left", "Turn left around the fixed Z axis"),
            ("TURN_RIGHT", "Turn Right", "Turn right around the fixed Z axis"),
            ("MOVE_FORWARD", "Move Forward", "Move forward on the XY plane"),
            ("MOVE_BACKWARD", "Move Backward", "Move backward on the XY plane"),
        ),
    )

    def execute(self, context: bpy.types.Context) -> set[str]:
        scene = context.scene
        heading = scene.arrietty_heading
        movement_heading = _movement_heading(context, heading)

        if self.action == "TURN_LEFT":
            heading += scene.arrietty_turn_step
        elif self.action == "TURN_RIGHT":
            heading -= scene.arrietty_turn_step
        elif self.action in {"MOVE_FORWARD", "MOVE_BACKWARD"}:
            direction = 1.0 if self.action == "MOVE_FORWARD" else -1.0
            distance = direction * scene.arrietty_move_step
            x, y = scene.arrietty_position
            scene.arrietty_position = (
                x - math.sin(movement_heading) * distance,
                y + math.cos(movement_heading) * distance,
            )
        else:
            self.report({"ERROR"}, f"Unknown navigation action: {self.action}")
            return {"CANCELLED"}

        scene.arrietty_heading = _normalized_angle(heading)
        apply_base_pose(context)

        for area in context.screen.areas if context.screen else ():
            if area.type == "VIEW_3D":
                area.tag_redraw()

        return {"FINISHED"}


_CLASSES = (ARRIETTY_OT_navigate,)


def _register_properties() -> None:
    bpy.types.Scene.arrietty_position = FloatVectorProperty(
        name="Start Position",
        description="Arrietty start position on the XY plane",
        size=2,
        default=(0.0, 0.0),
        unit="LENGTH",
    )
    bpy.types.Scene.arrietty_heading = FloatProperty(
        name="Start Direction",
        description="Arrietty start direction around the Z axis",
        default=0.0,
        subtype="ANGLE",
        unit="ROTATION",
    )
    bpy.types.Scene.arrietty_move_step = FloatProperty(
        name="Move Step",
        description="Distance moved by each Numpad 8 or Numpad 2 event",
        default=DEFAULT_MOVE_STEP_M,
        min=0.01,
        soft_max=10.0,
        unit="LENGTH",
    )
    bpy.types.Scene.arrietty_turn_step = FloatProperty(
        name="Turn Step",
        description="Angle turned by each Numpad 4 or Numpad 6 event",
        default=math.radians(DEFAULT_TURN_STEP_DEGREES),
        min=math.radians(0.1),
        soft_max=math.radians(90.0),
        subtype="ANGLE",
        unit="ROTATION",
    )


def _unregister_properties() -> None:
    del bpy.types.Scene.arrietty_turn_step
    del bpy.types.Scene.arrietty_move_step
    del bpy.types.Scene.arrietty_heading
    del bpy.types.Scene.arrietty_position


def _register_keymaps() -> None:
    key_config = bpy.context.window_manager.keyconfigs.addon
    if key_config is None:
        return

    keymap = key_config.keymaps.new(name="3D View", space_type="VIEW_3D")
    for key_type, action in _KEYMAP_ITEMS:
        item = keymap.keymap_items.new(
            ARRIETTY_OT_navigate.bl_idname,
            type=key_type,
            value="PRESS",
        )
        item.properties.action = action
        _addon_keymaps.append((keymap, item))


def _unregister_keymaps() -> None:
    for keymap, item in reversed(_addon_keymaps):
        keymap.keymap_items.remove(item)
    _addon_keymaps.clear()


def register() -> None:
    """Register navigation properties, operator, and event keymaps."""
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    _register_properties()
    _register_keymaps()


def unregister() -> None:
    """Unregister navigation in reverse dependency order."""
    reset_session_calibration()
    _unregister_keymaps()
    _unregister_properties()
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
