# SPDX-FileCopyrightText: 2026 ysk424
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""World-space VR bicycle instruments anchored near the right controller."""

from dataclasses import dataclass
from datetime import datetime
import math
import time

import bpy
from bpy.props import FloatProperty
from bpy.types import Operator
from mathutils import Matrix, Quaternion, Vector

from . import flight, navigation, steering, trainer


COLLECTION_NAME = "Arrietty Instruments (Runtime)"
ROOT_NAME = "Arrietty Instrument Root"
RIGHT_CONTROLLER_INDEX = 1
UPDATE_INTERVAL_SECONDS = 1.0 / 30.0
TEXT_UPDATE_INTERVAL_SECONDS = 0.10
FALLBACK_FORWARD_M = 0.68
FALLBACK_HEIGHT_M = 1.02
GENERATED_TAG = "arrietty_instrument_generated"


@dataclass(frozen=True)
class InstrumentSnapshot:
    """Values rendered on the instrument panel."""

    speed_kmh: float
    heart_rate_bpm: int | None
    clock_text: str
    cadence_rpm: float
    power_w: int
    distance_m: float
    laps_completed: int
    altitude_m: float
    flight_enabled: bool
    x_m: float
    y_m: float
    trainer_preset: int


class _InstrumentRuntime:
    def __init__(self) -> None:
        self.visible = False
        self.timer_registered = False
        self.anchor_source = "HIDDEN"
        self.message = "Instrument panel is hidden"
        self.last_text_update = 0.0
        self.heart_rate_bpm: int | None = None
        self.calibrated_anchor_local: tuple[float, float, float] | None = None
        self.calibrated_anchor_source = ""


_runtime = _InstrumentRuntime()


def _generated(id_data) -> bool:
    return bool(id_data.get(GENERATED_TAG, False))


def _tag_generated(id_data) -> None:
    id_data[GENERATED_TAG] = True


def _remove_generated_objects() -> None:
    collection = bpy.data.collections.get(COLLECTION_NAME)
    if collection is not None and _generated(collection):
        for obj in list(collection.objects):
            data = obj.data
            bpy.data.objects.remove(obj, do_unlink=True)
            if data is None or data.users != 0 or not _generated(data):
                continue
            if isinstance(data, bpy.types.Mesh):
                bpy.data.meshes.remove(data)
            elif isinstance(data, bpy.types.Curve):
                bpy.data.curves.remove(data)
        bpy.data.collections.remove(collection)

    for material in list(bpy.data.materials):
        if material.users == 0 and _generated(material):
            bpy.data.materials.remove(material)


def _ensure_collection(context: bpy.types.Context) -> bpy.types.Collection:
    collection = bpy.data.collections.get(COLLECTION_NAME)
    if collection is None:
        collection = bpy.data.collections.new(COLLECTION_NAME)
        _tag_generated(collection)
    if collection.name not in context.scene.collection.children:
        context.scene.collection.children.link(collection)
    collection.hide_viewport = False
    collection.hide_render = False
    return collection


def _material(name: str, color: tuple[float, float, float, float], emission: float):
    material = bpy.data.materials.get(name)
    if material is None:
        material = bpy.data.materials.new(name)
        _tag_generated(material)
    material.diffuse_color = color
    material.use_nodes = True
    nodes = material.node_tree.nodes
    bsdf = nodes.get("Principled BSDF")
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = color
        bsdf.inputs["Roughness"].default_value = 0.3
        emission_input = bsdf.inputs.get("Emission Color") or bsdf.inputs.get("Emission")
        if emission_input is not None:
            emission_input.default_value = color
        strength_input = bsdf.inputs.get("Emission Strength")
        if strength_input is not None:
            strength_input.default_value = emission
    return material


def _make_text(
    collection: bpy.types.Collection,
    name: str,
    body: str,
    location: tuple[float, float, float],
    size: float,
    align_x: str,
    material,
) -> bpy.types.Object:
    curve = bpy.data.curves.new(name=f"{name} Font", type="FONT")
    _tag_generated(curve)
    curve.body = body
    curve.align_x = align_x
    curve.align_y = "TOP_BASELINE"
    curve.size = size
    curve.extrude = 0.0005
    curve.resolution_u = 2
    curve.space_line = 1.18
    curve.materials.append(material)
    obj = bpy.data.objects.new(name, curve)
    _tag_generated(obj)
    obj.location = location
    collection.objects.link(obj)
    return obj


def _ensure_objects(context: bpy.types.Context) -> bpy.types.Object:
    root = bpy.data.objects.get(ROOT_NAME)
    if root is not None and _generated(root):
        return root

    _remove_generated_objects()
    collection = _ensure_collection(context)
    green = _material(
        "Arrietty Instrument Green", (0.04, 1.0, 0.12, 1.0), 4.0
    )
    orange = _material(
        "Arrietty Instrument Orange", (1.0, 0.25, 0.01, 1.0), 4.0
    )

    root = bpy.data.objects.new(ROOT_NAME, None)
    _tag_generated(root)
    root.empty_display_type = "PLAIN_AXES"
    root.empty_display_size = 0.04
    collection.objects.link(root)

    objects = (
        _make_text(
            collection, "Arrietty Speed", "0.0", (0.0, 0.092, 0.009),
            0.072, "CENTER", green,
        ),
        _make_text(
            collection, "Arrietty Speed Unit", "km/h", (0.145, 0.076, 0.009),
            0.017, "RIGHT", green,
        ),
        _make_text(
            collection, "Arrietty Heart Rate", "HR  -- bpm", (-0.145, 0.020, 0.009),
            0.026, "LEFT", orange,
        ),
        _make_text(
            collection, "Arrietty Clock", "00:00:00", (0.145, 0.020, 0.009),
            0.025, "RIGHT", orange,
        ),
        _make_text(
            collection,
            "Arrietty Ride Data",
            "CAD   0 rpm    PWR    0 W\nDIST    0 m     LAP    0\nALT   0.0 m     GROUND",
            (-0.145, -0.019, 0.009),
            0.021,
            "LEFT",
            green,
        ),
        _make_text(
            collection, "Arrietty Position", "X +0.0   Y +0.0 m",
            (-0.145, -0.100, 0.009), 0.017, "LEFT", green,
        ),
    )
    for obj in objects:
        obj.parent = root
    return root


def _right_controller_location(context: bpy.types.Context) -> Vector | None:
    if not navigation._is_vr_session_running(context):
        return None
    state = context.window_manager.xr_session_state
    if state is None:
        return None
    try:
        location = Vector(
            state.controller_grip_location_get(context, RIGHT_CONTROLLER_INDEX)
        )
    except (AttributeError, IndexError, RuntimeError, TypeError, ValueError):
        return None
    if not all(math.isfinite(value) for value in location):
        return None
    viewer = Vector(state.viewer_pose_location)
    if location.length_squared >= 1.0e-6 and (location - viewer).length <= 3.0:
        _runtime.anchor_source = "RIGHT OPENXR GRIP"
        _runtime.message = "Following the right OpenXR controller grip"
        return location

    steering_state = steering.snapshot()
    offset = steering_state.controller_offset_from_hmd
    if steering_state.tracking and offset is not None:
        offset_world = Quaternion(state.viewer_pose_rotation) @ Vector(offset)
        if 0.05 <= offset_world.length <= 3.0:
            _runtime.anchor_source = "RIGHT OPENVR GRIP"
            _runtime.message = "Following the steering controller relative to the HMD"
            return viewer + offset_world
    return None


def _panel_axes(heading: float) -> tuple[Vector, Vector, Vector, Vector]:
    forward = Vector((math.cos(heading), math.sin(heading), 0.0))
    right = Vector((forward.y, -forward.x, 0.0))
    normal = (-forward + Vector((0.0, 0.0, 0.45))).normalized()
    screen_up = normal.cross(right).normalized()
    return forward, right, screen_up, normal


def _panel_matrix(
    location: Vector,
    heading: float,
    scale: float,
) -> Matrix:
    _forward, right, screen_up, normal = _panel_axes(heading)
    return Matrix((
        (right.x * scale, screen_up.x * scale, normal.x * scale, location.x),
        (right.y * scale, screen_up.y * scale, normal.y * scale, location.y),
        (right.z * scale, screen_up.z * scale, normal.z * scale, location.z),
        (0.0, 0.0, 0.0, 1.0),
    ))


def _target_pose(context: bpy.types.Context) -> tuple[Vector, float]:
    scene = context.scene
    heading = scene.arrietty_heading
    forward, right, _screen_up, _normal = _panel_axes(heading)
    x, y = scene.arrietty_position
    ground_z = navigation.current_ground_height(context) + scene.arrietty_altitude
    bicycle_origin = Vector((x, y, ground_z))
    if _runtime.calibrated_anchor_local is not None:
        forward_m, side_m, height_m = _runtime.calibrated_anchor_local
        location = (
            bicycle_origin
            + forward * forward_m
            + right * side_m
            + Vector((0.0, 0.0, height_m))
        )
        _runtime.anchor_source = f"CALIBRATED {_runtime.calibrated_anchor_source}"
        _runtime.message = "Controller position captured once; tracking jitter is ignored"
    else:
        controller_location = _right_controller_location(context)
        if controller_location is not None:
            source = _runtime.anchor_source
            delta = controller_location - bicycle_origin
            _runtime.calibrated_anchor_local = (
                delta.dot(forward),
                delta.dot(right),
                delta.z,
            )
            _runtime.calibrated_anchor_source = source
            location = controller_location
            _runtime.anchor_source = f"CALIBRATED {source}"
            _runtime.message = "Controller position captured once; tracking jitter is ignored"
        else:
            location = (
                bicycle_origin
                + forward * FALLBACK_FORWARD_M
                + Vector((0.0, 0.0, FALLBACK_HEIGHT_M))
            )
            _runtime.anchor_source = "VIRTUAL STEM"
            _runtime.message = "Waiting to calibrate the right controller position"
    location += forward * scene.arrietty_panel_forward_offset
    location += right * scene.arrietty_panel_side_offset
    location.z += scene.arrietty_panel_height_offset
    return location, heading


def snapshot(context: bpy.types.Context) -> InstrumentSnapshot:
    runtime = trainer.get_runtime()
    flight_state = flight.snapshot()
    x_m, y_m = context.scene.arrietty_position
    return InstrumentSnapshot(
        speed_kmh=runtime.speed_kmh,
        heart_rate_bpm=_runtime.heart_rate_bpm,
        clock_text=datetime.now().astimezone().strftime("%H:%M:%S"),
        cadence_rpm=runtime.cadence_rpm,
        power_w=runtime.power_w,
        distance_m=runtime.distance_m,
        laps_completed=trainer.completed_laps(
            runtime.distance_m, runtime.course_length_m
        ),
        altitude_m=flight_state.altitude_m,
        flight_enabled=flight_state.enabled,
        x_m=x_m,
        y_m=y_m,
        trainer_preset=(
            runtime.applied_control_preset
            if runtime.applied_control_preset is not None
            else runtime.selected_control_preset
        ),
    )


def _distance_text(distance_m: float) -> str:
    if distance_m < 1000.0:
        return f"{distance_m:5.0f} m"
    return f"{distance_m / 1000.0:5.2f} km"


def _update_text(context: bpy.types.Context) -> None:
    values = snapshot(context)
    speed = bpy.data.objects.get("Arrietty Speed")
    heart = bpy.data.objects.get("Arrietty Heart Rate")
    clock = bpy.data.objects.get("Arrietty Clock")
    ride_data = bpy.data.objects.get("Arrietty Ride Data")
    position = bpy.data.objects.get("Arrietty Position")
    def set_body(obj, body: str) -> None:
        if obj is not None and obj.data.body != body:
            obj.data.body = body

    set_body(speed, f"{values.speed_kmh:4.1f}")
    if heart is not None:
        bpm = "--" if values.heart_rate_bpm is None else str(values.heart_rate_bpm)
        set_body(heart, f"HR  {bpm} bpm")
    set_body(clock, values.clock_text)
    if ride_data is not None:
        mode = "FLIGHT" if values.flight_enabled else "GROUND"
        set_body(ride_data, (
            f"CAD {values.cadence_rpm:3.0f} rpm    PWR {values.power_w:4d} W\n"
            f"DIST {_distance_text(values.distance_m)}  LAP {values.laps_completed:4d}\n"
            f"ALT {values.altitude_m:5.1f} m   {mode} P{values.trainer_preset}"
        ))
    set_body(position, f"X {values.x_m:+.1f}   Y {values.y_m:+.1f} m")


def update(context: bpy.types.Context) -> None:
    """Update instrument pose and telemetry from Blender's main thread."""
    if not _runtime.visible:
        return
    root = _ensure_objects(context)
    location, heading = _target_pose(context)
    target_matrix = _panel_matrix(
        location, heading, context.scene.arrietty_panel_scale
    )
    if any(
        abs(root.matrix_world[row][column] - target_matrix[row][column]) > 1.0e-6
        for row in range(4)
        for column in range(4)
    ):
        root.matrix_world = target_matrix
    now = time.monotonic()
    if now - _runtime.last_text_update >= TEXT_UPDATE_INTERVAL_SECONDS:
        _update_text(context)
        _runtime.last_text_update = now


def _timer_tick():
    if not _runtime.visible:
        _runtime.timer_registered = False
        return None
    try:
        update(bpy.context)
    except (AttributeError, ReferenceError, RuntimeError):
        _runtime.message = "Waiting for a usable Blender scene"
    return UPDATE_INTERVAL_SECONDS


def _ensure_timer() -> None:
    if _runtime.timer_registered:
        return
    bpy.app.timers.register(_timer_tick, first_interval=0.0)
    _runtime.timer_registered = True


def show(context: bpy.types.Context) -> None:
    """Show the runtime-only panel and begin pose/telemetry updates."""
    _runtime.visible = True
    _runtime.last_text_update = 0.0
    _runtime.calibrated_anchor_local = None
    _runtime.calibrated_anchor_source = ""
    _ensure_objects(context)
    update(context)
    _ensure_timer()


def hide() -> None:
    """Hide and remove all generated panel data from the current blend file."""
    _runtime.visible = False
    if bpy.app.timers.is_registered(_timer_tick):
        bpy.app.timers.unregister(_timer_tick)
    _runtime.timer_registered = False
    _runtime.anchor_source = "HIDDEN"
    _runtime.message = "Instrument panel is hidden"
    _runtime.calibrated_anchor_local = None
    _runtime.calibrated_anchor_source = ""
    _remove_generated_objects()


def is_visible() -> bool:
    return _runtime.visible


def status() -> tuple[str, str]:
    return _runtime.anchor_source, _runtime.message


def set_heart_rate(heart_rate_bpm: int | None) -> None:
    """Publish a future heart-rate receiver value without coupling its transport."""
    if heart_rate_bpm is None:
        _runtime.heart_rate_bpm = None
    else:
        _runtime.heart_rate_bpm = max(0, min(255, int(heart_rate_bpm)))


class ARRIETTY_OT_toggle_instrument_panel(Operator):
    """Show or hide the world-space instrument panel."""

    bl_idname = "arrietty.toggle_instrument_panel"
    bl_label = "Toggle Instrument Panel"
    bl_description = "Show or hide the VR instrument panel near the bicycle stem"

    def execute(self, context: bpy.types.Context) -> set[str]:
        if is_visible():
            hide()
        else:
            show(context)
        return {"FINISHED"}


_CLASSES = (ARRIETTY_OT_toggle_instrument_panel,)


def _register_properties() -> None:
    bpy.types.Scene.arrietty_panel_forward_offset = FloatProperty(
        name="Forward",
        description="Instrument offset along the bicycle's forward direction",
        default=0.0,
        min=-0.5,
        max=0.5,
        unit="LENGTH",
    )
    bpy.types.Scene.arrietty_panel_side_offset = FloatProperty(
        name="Side",
        description="Instrument offset to the rider's right",
        default=0.0,
        min=-0.5,
        max=0.5,
        unit="LENGTH",
    )
    bpy.types.Scene.arrietty_panel_height_offset = FloatProperty(
        name="Height",
        description="Instrument height above the tracked controller or virtual stem",
        default=0.10,
        min=-0.5,
        max=0.5,
        unit="LENGTH",
    )
    bpy.types.Scene.arrietty_panel_scale = FloatProperty(
        name="Scale",
        description="Scale of the VR instrument panel",
        default=1.0,
        min=0.5,
        max=2.0,
    )


def _unregister_properties() -> None:
    del bpy.types.Scene.arrietty_panel_scale
    del bpy.types.Scene.arrietty_panel_height_offset
    del bpy.types.Scene.arrietty_panel_side_offset
    del bpy.types.Scene.arrietty_panel_forward_offset


def register() -> None:
    """Register the instrument preview operator and placement properties."""
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    _register_properties()


def unregister() -> None:
    """Remove runtime instruments without leaving them in saved worlds."""
    hide()
    _unregister_properties()
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
