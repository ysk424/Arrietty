# SPDX-FileCopyrightText: 2026 ysk424
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""CYCPLUS T2 BLE notifications and straight-course movement."""

import asyncio
from dataclasses import dataclass
import queue
import struct
import sys
import threading
import time

import bpy
from bpy.props import FloatProperty
from bpy.types import Operator
from mathutils import Vector

from . import navigation


FTMS_INDOOR_BIKE_DATA = "00002ad2-0000-1000-8000-00805f9b34fb"
T2_NAME_FRAGMENT = "t2"
DEFAULT_COURSE_LENGTH_M = 100.0
TIMER_INTERVAL_SECONDS = 0.05
SAMPLE_STALE_SECONDS = 2.0


@dataclass(frozen=True)
class TrainerSample:
    """Values decoded from one FTMS Indoor Bike Data notification."""

    speed_kmh: float | None
    cadence_rpm: float | None
    power_w: int | None


class _TrainerRuntime:
    """Main-thread-owned runtime state; workers communicate through events."""

    def __init__(self) -> None:
        self.status = "IDLE"
        self.message = "Press Numpad 0 when the T2 is awake"
        self.speed_kmh = 0.0
        self.cadence_rpm = 0.0
        self.power_w = 0
        self.distance_m = 0.0
        self.course_length_m = DEFAULT_COURSE_LENGTH_M
        self.start_position = (0.0, 0.0)
        self.direction = (0.0, 1.0)
        self.last_sample_time = 0.0
        self.last_tick_time = 0.0
        self.signal_received = False
        self.generation = 0
        self.events = queue.SimpleQueue()
        self.stop_event: threading.Event | None = None
        self.thread: threading.Thread | None = None
        self.timer_registered = False

    @property
    def active(self) -> bool:
        return self.status in {"SEARCHING", "CONNECTING", "RIDING", "STOPPING"}


_runtime = _TrainerRuntime()
_addon_keymaps = []


def _take_unsigned(data: bytes | bytearray, offset: int, size: int):
    if offset + size > len(data):
        return None, len(data)
    return int.from_bytes(data[offset:offset + size], "little"), offset + size


def _parse_indoor_bike_data(data: bytes | bytearray) -> TrainerSample | None:
    """Decode the speed, cadence, and power fields of FTMS characteristic 0x2AD2."""
    if len(data) < 2:
        return None

    flags = int.from_bytes(data[0:2], "little")
    offset = 2
    speed_kmh = None
    cadence_rpm = None
    power_w = None

    if not flags & 0x0001:
        value, offset = _take_unsigned(data, offset, 2)
        if value is None:
            return None
        speed_kmh = value * 0.01
    if flags & 0x0002:
        _value, offset = _take_unsigned(data, offset, 2)
    if flags & 0x0004:
        value, offset = _take_unsigned(data, offset, 2)
        if value is None:
            return None
        cadence_rpm = value * 0.5
    if flags & 0x0008:
        _value, offset = _take_unsigned(data, offset, 2)
    if flags & 0x0010:
        _value, offset = _take_unsigned(data, offset, 3)
    if flags & 0x0020:
        _value, offset = _take_unsigned(data, offset, 2)
    if flags & 0x0040:
        if offset + 2 > len(data):
            return None
        power_w = struct.unpack_from("<h", data, offset)[0]

    return TrainerSample(speed_kmh, cadence_rpm, power_w)


def _queue_event(generation: int, event_type: str, payload=None) -> None:
    _runtime.events.put((generation, event_type, payload))


async def _ble_session(generation: int, stop_event: threading.Event) -> None:
    """Find the T2, subscribe to push notifications, and wait for shutdown."""
    from bleak import BleakClient, BleakScanner

    _queue_event(generation, "status", ("SEARCHING", "Searching for CYCPLUS T2"))
    device = await BleakScanner.find_device_by_filter(
        lambda dev, adv: T2_NAME_FRAGMENT
        in ((dev.name or adv.local_name or "").lower()),
        timeout=20.0,
    )
    if device is None:
        raise RuntimeError("T2 was not found. Pedal several times, then press Numpad 0 again")
    if stop_event.is_set():
        return

    _queue_event(generation, "status", ("CONNECTING", "Connecting to CYCPLUS T2"))
    disconnected = asyncio.Event()
    event_loop = asyncio.get_running_loop()

    def on_disconnect(_client) -> None:
        event_loop.call_soon_threadsafe(disconnected.set)

    async with BleakClient(
        device,
        disconnected_callback=on_disconnect,
        timeout=20.0,
    ) as client:
        def on_notification(_sender, data: bytearray) -> None:
            sample = _parse_indoor_bike_data(data)
            if sample is not None:
                _queue_event(generation, "sample", (time.monotonic(), sample))

        await client.start_notify(FTMS_INDOOR_BIKE_DATA, on_notification)
        _queue_event(generation, "connected", None)

        while not stop_event.is_set() and not disconnected.is_set():
            await asyncio.sleep(0.1)

        if client.is_connected:
            await client.stop_notify(FTMS_INDOOR_BIKE_DATA)

    if disconnected.is_set() and not stop_event.is_set():
        raise RuntimeError("The T2 Bluetooth connection was lost")


def _ble_worker(generation: int, stop_event: threading.Event) -> None:
    """Run Bleak in its own thread and never touch Blender data."""
    try:
        asyncio.run(_ble_session(generation, stop_event))
    except Exception as error:  # BLE backends expose several exception types.
        if not stop_event.is_set():
            _queue_event(generation, "error", str(error))
    finally:
        _queue_event(generation, "worker_stopped", None)


def _beep(pattern: tuple[tuple[int, int], ...]) -> None:
    try:
        import winsound

        for frequency, duration_ms in pattern:
            winsound.Beep(frequency, duration_ms)
    except (ImportError, RuntimeError):
        pass


def _play_start_sound() -> None:
    threading.Thread(
        target=_beep,
        args=(((1200, 700),),),
        name="ArriettyStartSound",
        daemon=True,
    ).start()


def _play_finish_sound() -> None:
    threading.Thread(
        target=_beep,
        args=(((700, 180), (1000, 180), (1300, 500)),),
        name="ArriettyFinishSound",
        daemon=True,
    ).start()


def _tag_view3d_redraw() -> None:
    for window in bpy.context.window_manager.windows:
        screen = window.screen
        if screen is None:
            continue
        for area in screen.areas:
            if area.type == "VIEW_3D":
                area.tag_redraw()


def _handle_worker_events(now: float) -> None:
    while True:
        try:
            generation, event_type, payload = _runtime.events.get_nowait()
        except queue.Empty:
            break
        if generation != _runtime.generation:
            continue

        if event_type == "status":
            _runtime.status, _runtime.message = payload
        elif event_type == "connected":
            _runtime.message = "Connected; waiting for the first FTMS signal"
        elif event_type == "sample":
            sample_time, sample = payload
            _runtime.last_sample_time = sample_time
            if sample.speed_kmh is not None:
                _runtime.speed_kmh = max(0.0, sample.speed_kmh)
            if sample.cadence_rpm is not None:
                _runtime.cadence_rpm = max(0.0, sample.cadence_rpm)
            if sample.power_w is not None:
                _runtime.power_w = max(0, sample.power_w)
            if not _runtime.signal_received:
                _runtime.signal_received = True
                _runtime.status = "RIDING"
                _runtime.message = "T2 signal received; ride straight to the course end"
                _runtime.last_tick_time = now
                _play_start_sound()
        elif event_type == "error":
            _runtime.status = "ERROR"
            _runtime.message = str(payload)
            _runtime.speed_kmh = 0.0
            if _runtime.stop_event is not None:
                _runtime.stop_event.set()
        elif event_type == "worker_stopped":
            if _runtime.status == "STOPPING":
                _runtime.status = "IDLE"
                _runtime.message = "Trainer stopped"


def _advance_straight_course(context: bpy.types.Context, now: float) -> None:
    if _runtime.status != "RIDING":
        _runtime.last_tick_time = now
        return

    elapsed = max(0.0, min(now - _runtime.last_tick_time, 0.25))
    _runtime.last_tick_time = now
    speed_kmh = _runtime.speed_kmh
    if now - _runtime.last_sample_time > SAMPLE_STALE_SECONDS:
        speed_kmh = 0.0

    remaining = max(0.0, _runtime.course_length_m - _runtime.distance_m)
    advance = min(speed_kmh / 3.6 * elapsed, remaining)
    if advance > 0.0:
        _runtime.distance_m += advance
        start_x, start_y = _runtime.start_position
        direction_x, direction_y = _runtime.direction
        context.scene.arrietty_position = (
            start_x + direction_x * _runtime.distance_m,
            start_y + direction_y * _runtime.distance_m,
        )
        navigation.apply_base_pose(context, reset_running=False)

    if remaining <= 1.0e-6 or _runtime.distance_m >= _runtime.course_length_m - 1.0e-6:
        _runtime.distance_m = _runtime.course_length_m
        _runtime.status = "FINISHED"
        _runtime.message = "Course end reached"
        _runtime.speed_kmh = 0.0
        if _runtime.stop_event is not None:
            _runtime.stop_event.set()
        _play_finish_sound()


def _timer_tick():
    """Drain worker events and update Blender data on the main thread."""
    now = time.monotonic()
    _handle_worker_events(now)
    _advance_straight_course(bpy.context, now)
    _tag_view3d_redraw()

    thread_alive = _runtime.thread is not None and _runtime.thread.is_alive()
    if thread_alive or _runtime.active:
        return TIMER_INTERVAL_SECONDS

    _runtime.timer_registered = False
    return None


def _ensure_timer() -> None:
    if _runtime.timer_registered:
        return
    bpy.app.timers.register(_timer_tick, first_interval=0.0)
    _runtime.timer_registered = True


def start_trainer(context: bpy.types.Context, direction: Vector) -> None:
    """Start a straight ride using a direction captured from the HMD."""
    _runtime.generation += 1
    generation = _runtime.generation
    while True:
        try:
            _runtime.events.get_nowait()
        except queue.Empty:
            break

    _runtime.status = "SEARCHING"
    _runtime.message = "Searching for CYCPLUS T2"
    _runtime.speed_kmh = 0.0
    _runtime.cadence_rpm = 0.0
    _runtime.power_w = 0
    _runtime.distance_m = 0.0
    _runtime.course_length_m = context.scene.arrietty_course_length
    _runtime.start_position = tuple(context.scene.arrietty_position)
    _runtime.direction = (direction.x, direction.y)
    _runtime.last_sample_time = 0.0
    _runtime.last_tick_time = time.monotonic()
    _runtime.signal_received = False
    _runtime.stop_event = threading.Event()
    _runtime.thread = threading.Thread(
        target=_ble_worker,
        args=(generation, _runtime.stop_event),
        name="ArriettyT2BLE",
        daemon=True,
    )
    _ensure_timer()
    _runtime.thread.start()


def stop_trainer() -> None:
    """Request a non-blocking trainer disconnect."""
    if _runtime.stop_event is not None:
        _runtime.stop_event.set()
    if _runtime.active:
        _runtime.status = "STOPPING"
        _runtime.message = "Stopping trainer"
        _ensure_timer()


def get_runtime() -> _TrainerRuntime:
    """Expose read-only-by-convention runtime values to the UI."""
    return _runtime


class ARRIETTY_OT_toggle_trainer(Operator):
    """Start or stop receiving the CYCPLUS T2 trainer."""

    bl_idname = "arrietty.toggle_trainer"
    bl_label = "Start or Stop CYCPLUS T2"
    bl_description = "Connect to the T2 and ride straight, or stop the active ride"

    def execute(self, context: bpy.types.Context) -> set[str]:
        if _runtime.active:
            stop_trainer()
            return {"FINISHED"}

        if sys.platform != "win32":
            self.report({"ERROR"}, "CYCPLUS T2 support currently requires Windows")
            return {"CANCELLED"}
        if abs(context.scene.unit_settings.scale_length - 1.0) > 1.0e-6:
            self.report({"ERROR"}, "Scene unit scale must be 1.0 so one Blender Unit is one meter")
            return {"CANCELLED"}
        if not navigation._is_vr_session_running(context):
            self.report({"ERROR"}, "Start the VR session before pressing Numpad 0")
            return {"CANCELLED"}

        direction = navigation.get_hmd_forward(context)
        if direction is None:
            self.report({"ERROR"}, "The HMD forward direction is not available yet")
            return {"CANCELLED"}

        start_trainer(context, direction)
        return {"FINISHED"}


_CLASSES = (ARRIETTY_OT_toggle_trainer,)


def _register_properties() -> None:
    bpy.types.Scene.arrietty_course_length = FloatProperty(
        name="Course Length",
        description="Straight-line distance from the start to the course end",
        default=DEFAULT_COURSE_LENGTH_M,
        min=1.0,
        soft_max=10000.0,
        unit="LENGTH",
    )


def _unregister_properties() -> None:
    del bpy.types.Scene.arrietty_course_length


def _register_keymaps() -> None:
    key_config = bpy.context.window_manager.keyconfigs.addon
    if key_config is None:
        return
    keymap = key_config.keymaps.new(name="3D View", space_type="VIEW_3D")
    item = keymap.keymap_items.new(
        ARRIETTY_OT_toggle_trainer.bl_idname,
        type="NUMPAD_0",
        value="PRESS",
    )
    _addon_keymaps.append((keymap, item))


def _unregister_keymaps() -> None:
    for keymap, item in reversed(_addon_keymaps):
        keymap.keymap_items.remove(item)
    _addon_keymaps.clear()


def register() -> None:
    """Register the trainer operator, course property, and Numpad 0 event."""
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    _register_properties()
    _register_keymaps()


def unregister() -> None:
    """Stop BLE work and unregister trainer resources."""
    stop_trainer()
    if bpy.app.timers.is_registered(_timer_tick):
        bpy.app.timers.unregister(_timer_tick)
    _runtime.timer_registered = False
    thread = _runtime.thread
    if thread is not None and thread.is_alive():
        thread.join(timeout=2.0)
    _unregister_keymaps()
    _unregister_properties()
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
