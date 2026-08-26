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
RIDE_SURFACE_TAG = "secret_world_ride_surface"
GROUND_RAY_START_Z_M = 10000.0
GROUND_RAY_DISTANCE_M = 20000.0

_KEYMAP_ITEMS = (
    ("NUMPAD_4", "TURN_LEFT"),
    ("NUMPAD_6", "TURN_RIGHT"),
    ("NUMPAD_8", "MOVE_FORWARD"),
    ("NUMPAD_2", "MOVE_BACKWARD"),
)
_addon_keymaps = []
_ground_height_cache: dict[int, tuple[float, float, float]] = {}


def _normalized_angle(angle: float) -> float:
    """Wrap an angle to the range -pi through pi."""
    return math.atan2(math.sin(angle), math.cos(angle))


def _is_vr_session_running(context: bpy.types.Context) -> bool:
    """Return whether an OpenXR session is running."""
    try:
        return bpy.types.XrSessionState.is_running(context)
    except (AttributeError, RuntimeError):
        return False


def _forward_from_viewer_rotation(rotation) -> Vector | None:
    """Return Blender's normalized XR viewer-forward axis on the XY plane."""
    forward = Quaternion(rotation) @ Vector((0.0, 0.0, -1.0))
    forward.z = 0.0
    if forward.length_squared < 1.0e-8:
        return None
    forward.normalize()
    return forward


def get_hmd_forward(context: bpy.types.Context) -> Vector | None:
    """Return the current HMD forward direction projected onto the ground."""
    if not _is_vr_session_running(context):
        return None
    state = context.window_manager.xr_session_state
    if state is None:
        return None
    return _forward_from_viewer_rotation(state.viewer_pose_rotation)


def _movement_forward(context: bpy.types.Context, body_heading: float) -> Vector:
    """Use live HMD forward in VR, or body heading before the session starts."""
    hmd_forward = get_hmd_forward(context)
    if hmd_forward is not None:
        return hmd_forward
    return Vector((math.cos(body_heading), math.sin(body_heading), 0.0))


def _set_navigation_altitude(state, altitude_m: float) -> bool:
    """Set the live XR navigation Z offset without accumulating deltas."""
    location = tuple(state.navigation_location)
    altitude_m = max(0.0, altitude_m)
    if abs(location[2] - altitude_m) <= 1.0e-6:
        return False
    state.navigation_location = (location[0], location[1], altitude_m)
    return True


def get_xr_heights(
    context: bpy.types.Context,
) -> tuple[float, float | None, float | None]:
    """Return base, live-navigation, and final viewer Z values for logging."""
    base_z = float(context.window_manager.xr_session_settings.base_pose_location[2])
    if not _is_vr_session_running(context):
        return base_z, None, None
    state = context.window_manager.xr_session_state
    if state is None:
        return base_z, None, None
    return (
        base_z,
        float(state.navigation_location[2]),
        float(state.viewer_pose_location[2]),
    )


def _scene_cache_key(scene) -> int:
    try:
        return int(scene.as_pointer())
    except AttributeError:
        return id(scene)


def scene_uses_ride_surfaces(context: bpy.types.Context) -> bool:
    """Return whether Secret World supplied explicit bicycle surfaces."""
    return any(
        obj.type == "MESH" and bool(obj.get(RIDE_SURFACE_TAG, False))
        for obj in getattr(context.scene, "objects", ())
    )


def ride_surface_height(
    context: bpy.types.Context,
    x_m: float,
    y_m: float,
) -> float | None:
    """Return the highest tagged ride-surface height under an XY position."""
    surfaces = [
        obj
        for obj in getattr(context.scene, "objects", ())
        if obj.type == "MESH" and bool(obj.get(RIDE_SURFACE_TAG, False))
    ]
    if not surfaces:
        return None
    try:
        depsgraph = context.evaluated_depsgraph_get()
    except (AttributeError, RuntimeError):
        return None

    world_origin = Vector((x_m, y_m, GROUND_RAY_START_Z_M))
    world_direction = Vector((0.0, 0.0, -1.0))
    highest = None
    for original in surfaces:
        try:
            evaluated = original.evaluated_get(depsgraph)
            inverse = evaluated.matrix_world.inverted_safe()
            local_origin = inverse @ world_origin
            local_direction = (inverse.to_3x3() @ world_direction).normalized()
            hit, location, _normal, _face_index = evaluated.ray_cast(
                local_origin,
                local_direction,
                distance=GROUND_RAY_DISTANCE_M,
            )
        except (AttributeError, RuntimeError, ValueError):
            continue
        if not hit:
            continue
        world_height = float((evaluated.matrix_world @ location).z)
        if highest is None or world_height > highest:
            highest = world_height
    if highest is not None:
        _ground_height_cache[_scene_cache_key(context.scene)] = (
            x_m,
            y_m,
            highest,
        )
    return highest


def current_ground_height(context: bpy.types.Context) -> float:
    """Resolve ground under the bicycle, retaining the last valid surface height."""
    scene = context.scene
    key = _scene_cache_key(scene)
    if not scene_uses_ride_surfaces(context):
        _ground_height_cache.pop(key, None)
        return 0.0
    x_m, y_m = scene.arrietty_position
    cached = _ground_height_cache.get(key)
    if cached is not None:
        cached_x, cached_y, cached_height = cached
        if math.hypot(x_m - cached_x, y_m - cached_y) <= 1.0e-4:
            return cached_height
    height = ride_surface_height(context, x_m, y_m)
    if height is not None:
        return height
    return cached[2] if cached is not None else 0.0


def apply_base_pose(context: bpy.types.Context, *, reset_running: bool = True) -> None:
    """Apply the persistent Arrietty start pose to Blender's XR settings."""
    scene = context.scene
    settings = context.window_manager.xr_session_settings
    x, y = scene.arrietty_position
    altitude_m = max(0.0, scene.arrietty_altitude)
    ground_height_m = current_ground_height(context)
    is_running = _is_vr_session_running(context)
    state = context.window_manager.xr_session_state if is_running else None
    eye_height_m = ground_height_m + EYE_HEIGHT_M
    if state is None:
        eye_height_m += altitude_m

    settings.base_pose_type = "CUSTOM"
    settings.base_pose_location = (x, y, eye_height_m)
    settings.base_pose_angle = scene.arrietty_heading
    settings.base_scale = 1.0

    if state is not None:
        if reset_running:
            state.reset_to_base_pose(context)
        _set_navigation_altitude(state, altitude_m)


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
        movement_forward = _movement_forward(context, heading)

        if self.action == "TURN_LEFT":
            heading += scene.arrietty_turn_step
        elif self.action == "TURN_RIGHT":
            heading -= scene.arrietty_turn_step
        elif self.action in {"MOVE_FORWARD", "MOVE_BACKWARD"}:
            direction = 1.0 if self.action == "MOVE_FORWARD" else -1.0
            distance = direction * scene.arrietty_move_step
            x, y = scene.arrietty_position
            scene.arrietty_position = (
                x + movement_forward.x * distance,
                y + movement_forward.y * distance,
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
    bpy.types.Scene.arrietty_altitude = FloatProperty(
        name="Flight Altitude",
        description="Current flight height above the ground",
        default=0.0,
        min=0.0,
        unit="LENGTH",
        options={"HIDDEN", "SKIP_SAVE"},
    )


def _unregister_properties() -> None:
    del bpy.types.Scene.arrietty_altitude
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
    _unregister_keymaps()
    _unregister_properties()
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
