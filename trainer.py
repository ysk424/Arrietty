# SPDX-FileCopyrightText: 2026 ysk424
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""CYCPLUS T2 BLE notifications and controller-steered movement."""

import asyncio
from dataclasses import dataclass
import math
from pathlib import Path
import queue
import struct
import sys
import threading
import time

import bpy
from bpy.props import FloatProperty, IntProperty
from bpy.types import Operator

from . import flight, navigation, ride_log, steering


FTMS_INDOOR_BIKE_DATA = "00002ad2-0000-1000-8000-00805f9b34fb"
FTMS_CONTROL_POINT = "00002ad9-0000-1000-8000-00805f9b34fb"
CSC_MEASUREMENT = "00002a5b-0000-1000-8000-00805f9b34fb"
FTMS_REQUEST_CONTROL = 0x00
FTMS_SET_INDOOR_BIKE_SIMULATION = 0x11
FTMS_RESPONSE_CODE = 0x80
FTMS_RESULT_SUCCESS = 0x01
FTMS_CONTROL_TIMEOUT_SECONDS = 5.0
FLAT_WIND_SPEED_MPS = 0.0
FLAT_GRADE_PERCENT = 0.0
FLAT_WIND_RESISTANCE_KG_M = 0.51
T2_NAME_FRAGMENT = "t2"
OVAL_LAP_LENGTH_M = 143.0
DEFAULT_COURSE_LENGTH_M = OVAL_LAP_LENGTH_M
TIMER_INTERVAL_SECONDS = 0.05
SAMPLE_STALE_SECONDS = 1.25
COAST_STOP_SPEED_KMH = 5.0
DEFAULT_WHEEL_STOP_SECONDS = 1.5
MIN_WHEEL_STOP_SECONDS = 0.75
MAX_WHEEL_STOP_SECONDS = 4.0
PROVISIONAL_WHEELBASE_M = 1.05


@dataclass(frozen=True)
class TrainerSample:
    """Values decoded from one FTMS Indoor Bike Data notification."""

    speed_kmh: float | None
    cadence_rpm: float | None
    power_w: int | None


@dataclass(frozen=True)
class CscSample:
    """Wheel and crank events decoded from CSC Measurement 0x2A5B."""

    wheel_revolutions: int | None
    wheel_event_time_ticks: int | None
    crank_revolutions: int | None
    crank_event_time_ticks: int | None


@dataclass(frozen=True)
class ControlPreset:
    """One flat-road rolling-resistance value used for live comparison."""

    index: int
    numpad_key: str | None
    label: str
    rolling_resistance: float


CONTROL_PRESETS = (
    ControlPreset(1, "NUMPAD_1", "Race", 0.0040),
    ControlPreset(2, "NUMPAD_3", "Road", 0.0080),
    ControlPreset(3, "NUMPAD_5", "Firm", 0.0120),
    ControlPreset(4, "NUMPAD_9", "Strong", 0.0160),
    ControlPreset(5, None, "Road Default", 0.0200),
    ControlPreset(6, None, "Bicycle", 0.0240),
    ControlPreset(7, None, "FTMS Limit", 0.0255),
)


class _TrainerRuntime:
    """Main-thread-owned runtime state; workers communicate through events."""

    def __init__(self) -> None:
        self.status = "IDLE"
        self.message = "Press Numpad 0 when the T2 is awake"
        self.speed_kmh = 0.0
        self.ftms_speed_kmh = 0.0
        self.cadence_rpm = 0.0
        self.power_w = 0
        self.distance_m = 0.0
        self.course_length_m = DEFAULT_COURSE_LENGTH_M
        self.start_position = (0.0, 0.0)
        self.direction = (0.0, 1.0)
        self.travel_heading = 0.0
        self.accumulated_turn = 0.0
        self.last_sample_time = 0.0
        self.last_tick_time = 0.0
        self.wheel_signal_received = False
        self.wheel_revolutions: int | None = None
        self.wheel_event_time_ticks: int | None = None
        self.last_wheel_motion_time = 0.0
        self.wheel_period_seconds = 0.0
        self.control_status = "IDLE"
        self.control_message = "T2 flat-road control is idle"
        self.selected_control_preset = 5
        self.applied_control_preset: int | None = None
        self.control_requests = queue.SimpleQueue()
        self.signal_received = False
        self.generation = 0
        self.events = queue.SimpleQueue()
        self.stop_event: threading.Event | None = None
        self.thread: threading.Thread | None = None
        self.timer_registered = False

    @property
    def active(self) -> bool:
        return self.status in {
            "SEARCHING", "CONNECTING", "WAITING_STEERING", "RIDING", "STOPPING"
        }


_runtime = _TrainerRuntime()
_addon_keymaps = []


def completed_laps(distance_m: float, lap_length_m: float) -> int:
    """Return the number of completed distance-based laps."""
    return max(0, int(distance_m / max(1.0, lap_length_m)))


def _ride_log_directory() -> Path:
    if bpy.data.filepath:
        return Path(bpy.data.filepath).parent
    return Path(bpy.app.tempdir)


def _record_telemetry(context: bpy.types.Context, event: str = "SAMPLE") -> None:
    flight_state = flight.snapshot()
    target_altitude_m = (
        flight.altitude_for_speed(_runtime.speed_kmh)
        if flight_state.enabled
        else 0.0
    )
    xr_base_z_m, xr_navigation_z_m, xr_viewer_z_m = navigation.get_xr_heights(
        context
    )
    x, y = context.scene.arrietty_position
    ride_log.record(
        event=event,
        speed_kmh=_runtime.speed_kmh,
        ftms_speed_kmh=_runtime.ftms_speed_kmh,
        cadence_rpm=_runtime.cadence_rpm,
        power_w=_runtime.power_w,
        distance_m=_runtime.distance_m,
        laps_completed=completed_laps(
            _runtime.distance_m,
            _runtime.course_length_m,
        ),
        flight_mode=flight_state.enabled,
        altitude_m=flight_state.altitude_m,
        target_altitude_m=target_altitude_m,
        xr_base_z_m=xr_base_z_m,
        xr_navigation_z_m=xr_navigation_z_m,
        xr_viewer_z_m=xr_viewer_z_m,
        x_m=x,
        y_m=y,
        heading_degrees=math.degrees(_runtime.travel_heading),
        csc_wheel_revolutions=_runtime.wheel_revolutions,
        csc_wheel_event_time_ticks=_runtime.wheel_event_time_ticks,
        csc_wheel_stopped=_wheel_is_stopped(time.monotonic()),
        low_speed_coast_stopped=_low_speed_coast_is_stopped(),
        t2_control_status=_runtime.control_status,
        t2_control_preset=_runtime.applied_control_preset,
    )


def _stop_ride_log(context: bpy.types.Context, event: str) -> None:
    if not ride_log.is_active():
        return
    _record_telemetry(context, event=event)
    ride_log.stop(event=None)


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


def _parse_csc_measurement(data: bytes | bytearray) -> CscSample | None:
    """Decode cumulative wheel/crank events from CSC characteristic 0x2A5B."""
    if len(data) < 1:
        return None
    flags = data[0]
    offset = 1
    wheel_revolutions = None
    wheel_event_time_ticks = None
    crank_revolutions = None
    crank_event_time_ticks = None

    if flags & 0x01:
        wheel_revolutions, offset = _take_unsigned(data, offset, 4)
        wheel_event_time_ticks, offset = _take_unsigned(data, offset, 2)
        if wheel_revolutions is None or wheel_event_time_ticks is None:
            return None
    if flags & 0x02:
        crank_revolutions, offset = _take_unsigned(data, offset, 2)
        crank_event_time_ticks, offset = _take_unsigned(data, offset, 2)
        if crank_revolutions is None or crank_event_time_ticks is None:
            return None
    return CscSample(
        wheel_revolutions,
        wheel_event_time_ticks,
        crank_revolutions,
        crank_event_time_ticks,
    )


def _wheel_stop_timeout_seconds() -> float:
    if _runtime.wheel_period_seconds <= 0.0:
        return DEFAULT_WHEEL_STOP_SECONDS
    return max(
        MIN_WHEEL_STOP_SECONDS,
        min(
            MAX_WHEEL_STOP_SECONDS,
            _runtime.wheel_period_seconds * 1.5 + 0.25,
        ),
    )


def _wheel_is_stopped(now: float) -> bool:
    return bool(
        _runtime.wheel_signal_received
        and now - _runtime.last_wheel_motion_time > _wheel_stop_timeout_seconds()
    )


def _low_speed_coast_is_stopped() -> bool:
    """Stop the virtual tail while still allowing deliberate low-speed pedaling."""
    return bool(
        0.0 < _runtime.ftms_speed_kmh <= COAST_STOP_SPEED_KMH
        and _runtime.cadence_rpm <= 0.0
    )


def _effective_speed_kmh(now: float) -> float:
    if now - _runtime.last_sample_time > SAMPLE_STALE_SECONDS:
        return 0.0
    if _wheel_is_stopped(now):
        return 0.0
    if _low_speed_coast_is_stopped():
        return 0.0
    return _runtime.ftms_speed_kmh


def _handle_csc_sample(sample_time: float, sample: CscSample) -> None:
    if sample.wheel_revolutions is None or sample.wheel_event_time_ticks is None:
        return
    previous_revolutions = _runtime.wheel_revolutions
    previous_event_time = _runtime.wheel_event_time_ticks
    _runtime.wheel_signal_received = True
    _runtime.wheel_revolutions = sample.wheel_revolutions
    _runtime.wheel_event_time_ticks = sample.wheel_event_time_ticks

    if previous_revolutions is None or previous_event_time is None:
        _runtime.last_wheel_motion_time = sample_time
        return
    revolution_delta = (sample.wheel_revolutions - previous_revolutions) & 0xFFFFFFFF
    if revolution_delta == 0:
        return
    event_delta = (sample.wheel_event_time_ticks - previous_event_time) & 0xFFFF
    if event_delta > 0 and revolution_delta < 1000:
        period = event_delta / 1024.0 / revolution_delta
        if 0.01 <= period <= 30.0:
            _runtime.wheel_period_seconds = period
    _runtime.last_wheel_motion_time = sample_time


def _control_preset(preset_index: int) -> ControlPreset:
    for preset in CONTROL_PRESETS:
        if preset.index == preset_index:
            return preset
    raise ValueError(f"Unknown T2 control preset P{preset_index}")


def _control_description(preset: ControlPreset) -> str:
    return (
        f"P{preset.index} {preset.label}: grade 0%; "
        f"Crr {preset.rolling_resistance:.4f}; Cw 0.51 kg/m"
    )


def _flat_road_control_command(preset_index: int = 1) -> bytes:
    """Encode flat-road FTMS simulation parameters using assigned resolutions."""
    preset = _control_preset(preset_index)
    wind_speed = round(FLAT_WIND_SPEED_MPS / 0.001)
    grade = round(FLAT_GRADE_PERCENT / 0.01)
    rolling_resistance = round(preset.rolling_resistance / 0.0001)
    wind_resistance = round(FLAT_WIND_RESISTANCE_KG_M / 0.01)
    return struct.pack(
        "<BhhBB",
        FTMS_SET_INDOOR_BIKE_SIMULATION,
        wind_speed,
        grade,
        rolling_resistance,
        wind_resistance,
    )


def _control_result_name(result_code: int) -> str:
    return {
        0x01: "success",
        0x02: "not supported",
        0x03: "invalid parameter",
        0x04: "operation failed",
        0x05: "control not permitted",
    }.get(result_code, f"unknown result 0x{result_code:02x}")


def _parse_control_response(
    data: bytes | bytearray,
    requested_opcode: int,
) -> int | None:
    if (
        len(data) < 3
        or data[0] != FTMS_RESPONSE_CODE
        or data[1] != requested_opcode
    ):
        return None
    return data[2]


async def _send_control_command(client, responses: asyncio.Queue, command: bytes) -> None:
    requested_opcode = command[0]
    await client.write_gatt_char(FTMS_CONTROL_POINT, command, response=True)
    event_loop = asyncio.get_running_loop()
    deadline = event_loop.time() + FTMS_CONTROL_TIMEOUT_SECONDS
    while True:
        remaining = deadline - event_loop.time()
        if remaining <= 0.0:
            raise RuntimeError(
                f"T2 did not answer FTMS control opcode 0x{requested_opcode:02x}"
            )
        try:
            response = await asyncio.wait_for(responses.get(), timeout=remaining)
        except TimeoutError as error:
            raise RuntimeError(
                f"T2 did not answer FTMS control opcode 0x{requested_opcode:02x}"
            ) from error
        result_code = _parse_control_response(response, requested_opcode)
        if result_code is None:
            continue
        if result_code != FTMS_RESULT_SUCCESS:
            raise RuntimeError(
                f"T2 rejected FTMS control opcode 0x{requested_opcode:02x}: "
                f"{_control_result_name(result_code)}"
            )
        return


def _queue_event(generation: int, event_type: str, payload=None) -> None:
    _runtime.events.put((generation, event_type, payload))


async def _ble_session(
    generation: int,
    stop_event: threading.Event,
    initial_preset_index: int,
) -> None:
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
        control_responses = asyncio.Queue()

        def on_notification(_sender, data: bytearray) -> None:
            sample = _parse_indoor_bike_data(data)
            if sample is not None:
                _queue_event(generation, "sample", (time.monotonic(), sample))

        def on_csc_notification(_sender, data: bytearray) -> None:
            sample = _parse_csc_measurement(data)
            if sample is not None:
                _queue_event(generation, "csc_sample", (time.monotonic(), sample))

        def on_control_indication(_sender, data: bytearray) -> None:
            control_responses.put_nowait(bytes(data))

        await client.start_notify(FTMS_CONTROL_POINT, on_control_indication)
        await _send_control_command(
            client,
            control_responses,
            bytes((FTMS_REQUEST_CONTROL,)),
        )
        await _send_control_command(
            client,
            control_responses,
            _flat_road_control_command(initial_preset_index),
        )
        initial_preset = _control_preset(initial_preset_index)
        _queue_event(
            generation,
            "control_ready",
            (initial_preset.index, _control_description(initial_preset)),
        )

        await client.start_notify(FTMS_INDOOR_BIKE_DATA, on_notification)
        csc_enabled = False
        try:
            await client.start_notify(CSC_MEASUREMENT, on_csc_notification)
            csc_enabled = True
        except Exception as error:
            _queue_event(generation, "csc_unavailable", str(error))
        _queue_event(generation, "connected", None)

        while not stop_event.is_set() and not disconnected.is_set():
            requested_preset_index = None
            while True:
                try:
                    request_generation, preset_index = (
                        _runtime.control_requests.get_nowait()
                    )
                except queue.Empty:
                    break
                if request_generation == generation:
                    requested_preset_index = preset_index
            if requested_preset_index is not None:
                preset = _control_preset(requested_preset_index)
                await _send_control_command(
                    client,
                    control_responses,
                    _flat_road_control_command(preset.index),
                )
                _queue_event(
                    generation,
                    "control_ready",
                    (preset.index, _control_description(preset)),
                )
            await asyncio.sleep(0.1)

        if client.is_connected:
            if csc_enabled:
                await client.stop_notify(CSC_MEASUREMENT)
            await client.stop_notify(FTMS_INDOOR_BIKE_DATA)
            await client.stop_notify(FTMS_CONTROL_POINT)

    if disconnected.is_set() and not stop_event.is_set():
        raise RuntimeError("The T2 Bluetooth connection was lost")


def _ble_worker(
    generation: int,
    stop_event: threading.Event,
    initial_preset_index: int,
) -> None:
    """Run Bleak in its own thread and never touch Blender data."""
    try:
        asyncio.run(_ble_session(generation, stop_event, initial_preset_index))
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


def _tag_view3d_redraw() -> None:
    for window in bpy.context.window_manager.windows:
        screen = window.screen
        if screen is None:
            continue
        for area in screen.areas:
            if area.type == "VIEW_3D":
                area.tag_redraw()


def _begin_riding(now: float) -> None:
    _runtime.status = "RIDING"
    _runtime.message = "T2 and right controller received; steering is active"
    _runtime.last_tick_time = now
    _play_start_sound()


def _handle_worker_events(context: bpy.types.Context, now: float) -> None:
    record_sample = False
    while True:
        try:
            generation, event_type, payload = _runtime.events.get_nowait()
        except queue.Empty:
            break
        if generation != _runtime.generation:
            continue

        if event_type == "status":
            _runtime.status, _runtime.message = payload
        elif event_type == "control_ready":
            preset_index, description = payload
            _runtime.applied_control_preset = preset_index
            _runtime.control_status = f"FLAT P{preset_index}"
            _runtime.control_message = description
        elif event_type == "connected":
            _runtime.message = "T2 flat-road control active; waiting for FTMS"
        elif event_type == "sample":
            sample_time, sample = payload
            _runtime.last_sample_time = sample_time
            if sample.speed_kmh is not None:
                _runtime.ftms_speed_kmh = max(0.0, sample.speed_kmh)
            if sample.cadence_rpm is not None:
                _runtime.cadence_rpm = max(0.0, sample.cadence_rpm)
            if sample.power_w is not None:
                _runtime.power_w = max(0, sample.power_w)
            if not _runtime.signal_received:
                _runtime.signal_received = True
                if steering.is_tracking():
                    _begin_riding(now)
                else:
                    _runtime.status = "WAITING_STEERING"
                    _runtime.message = "T2 received; waiting for the right controller"
            record_sample = True
        elif event_type == "csc_sample":
            sample_time, sample = payload
            _handle_csc_sample(sample_time, sample)
        elif event_type == "csc_unavailable":
            _runtime.message = "CSC wheel rotation unavailable; using FTMS speed only"
        elif event_type == "error":
            _runtime.status = "ERROR"
            _runtime.message = str(payload)
            _runtime.speed_kmh = 0.0
            _runtime.ftms_speed_kmh = 0.0
            _runtime.control_status = "ERROR"
            _runtime.control_message = str(payload)
            _runtime.applied_control_preset = None
            if _runtime.stop_event is not None:
                _runtime.stop_event.set()
            steering.request_stop()
            _stop_ride_log(context, "ERROR")
            if flight.reset(context):
                navigation.apply_base_pose(context, reset_running=False)
        elif event_type == "worker_stopped":
            if _runtime.status == "STOPPING":
                _runtime.status = "IDLE"
                _runtime.message = "Trainer stopped"
                _runtime.control_status = "IDLE"
                _runtime.control_message = (
                    f"P{_runtime.selected_control_preset} selected for the next ride"
                )
                _runtime.applied_control_preset = None

    _runtime.speed_kmh = _effective_speed_kmh(now)
    if record_sample:
        _record_telemetry(context)

    if _runtime.status == "WAITING_STEERING":
        steering_state = steering.snapshot()
        if steering_state.tracking:
            _begin_riding(now)
        elif steering_state.status == "ERROR":
            _runtime.status = "ERROR"
            _runtime.message = steering_state.message
            if _runtime.stop_event is not None:
                _runtime.stop_event.set()
            _stop_ride_log(context, "STEERING_ERROR")
            if flight.reset(context):
                navigation.apply_base_pose(context, reset_running=False)


def _advance_course(context: bpy.types.Context, now: float) -> None:
    if _runtime.status != "RIDING":
        _runtime.last_tick_time = now
        return

    elapsed = max(0.0, min(now - _runtime.last_tick_time, 0.25))
    _runtime.last_tick_time = now
    speed_kmh = _effective_speed_kmh(now)
    _runtime.speed_kmh = speed_kmh

    steering_state = steering.snapshot()
    if not steering_state.tracking:
        _runtime.last_tick_time = now
        _runtime.message = "Ride paused; right controller tracking was lost"
        return
    if _runtime.message.startswith("Ride paused; right controller"):
        _runtime.message = "Right controller recovered; steering is active"

    if _wheel_is_stopped(now) and _runtime.ftms_speed_kmh > 0.0:
        _runtime.message = "Stopped; CSC wheel rotation is stationary"
    elif _low_speed_coast_is_stopped():
        _runtime.message = (
            f"Stopped; coasting at or below {COAST_STOP_SPEED_KMH:.1f} km/h"
        )
    elif (
        speed_kmh > 0.0
        and _runtime.message.startswith("Stopped;")
    ):
        _runtime.message = "Trainer motion received; steering is active"

    altitude_changed = flight.update_altitude(context, speed_kmh)

    advance = speed_kmh / 3.6 * elapsed
    if advance > 0.0:
        steering_angle = steering.get_effective_angle_radians()
        turn = advance / PROVISIONAL_WHEELBASE_M * math.tan(steering_angle)
        midpoint_heading = _runtime.travel_heading + turn * 0.5
        x, y = context.scene.arrietty_position
        next_position = (
            x + math.cos(midpoint_heading) * advance,
            y + math.sin(midpoint_heading) * advance,
        )
        if (
            navigation.scene_uses_ride_surfaces(context)
            and navigation.ride_surface_height(context, *next_position) is None
        ):
            _runtime.message = "Ride paused; no ride surface under the bicycle"
            if altitude_changed:
                navigation.apply_base_pose(context, reset_running=False)
            return
        if _runtime.message.startswith("Ride paused; no ride surface"):
            _runtime.message = "Ride surface recovered; steering is active"
        context.scene.arrietty_position = next_position
        _runtime.distance_m += advance
        _runtime.travel_heading = navigation._normalized_angle(
            _runtime.travel_heading + turn
        )
        _runtime.accumulated_turn += turn
        _runtime.direction = _direction_from_heading(_runtime.travel_heading)
        context.scene.arrietty_heading = navigation._normalized_angle(
            context.scene.arrietty_heading + turn
        )
    if advance > 0.0 or altitude_changed:
        navigation.apply_base_pose(context, reset_running=False)


def _timer_tick():
    """Drain worker events and update Blender data on the main thread."""
    now = time.monotonic()
    _handle_worker_events(bpy.context, now)
    _advance_course(bpy.context, now)
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


def _direction_from_heading(heading: float) -> tuple[float, float]:
    """Return the XY vector for a standard Blender Z-axis heading."""
    return (math.cos(heading), math.sin(heading))


def _initialize_travel_state(context: bpy.types.Context) -> None:
    """Initialize bicycle travel from the stored pose, never from HMD gaze."""
    _runtime.start_position = tuple(context.scene.arrietty_position)
    _runtime.travel_heading = navigation._normalized_angle(
        context.scene.arrietty_heading
    )
    _runtime.direction = _direction_from_heading(_runtime.travel_heading)


def start_trainer(context: bpy.types.Context) -> None:
    """Start a ride using the stored bicycle heading, independent of HMD view."""
    ride_log.start(_ride_log_directory())
    _runtime.generation += 1
    generation = _runtime.generation
    while True:
        try:
            _runtime.events.get_nowait()
        except queue.Empty:
            break
    while True:
        try:
            _runtime.control_requests.get_nowait()
        except queue.Empty:
            break

    _runtime.status = "SEARCHING"
    _runtime.message = "Searching for CYCPLUS T2"
    _runtime.speed_kmh = 0.0
    _runtime.ftms_speed_kmh = 0.0
    _runtime.cadence_rpm = 0.0
    _runtime.power_w = 0
    _runtime.distance_m = 0.0
    _runtime.course_length_m = context.scene.arrietty_course_length
    _initialize_travel_state(context)
    _runtime.accumulated_turn = 0.0
    _runtime.last_sample_time = 0.0
    _runtime.last_tick_time = time.monotonic()
    _runtime.wheel_signal_received = False
    _runtime.wheel_revolutions = None
    _runtime.wheel_event_time_ticks = None
    _runtime.last_wheel_motion_time = 0.0
    _runtime.wheel_period_seconds = 0.0
    initial_preset_index = _runtime.selected_control_preset
    _runtime.applied_control_preset = None
    _runtime.control_status = f"REQUESTING P{initial_preset_index}"
    _runtime.control_message = (
        f"Requesting T2 control and preset P{initial_preset_index}"
    )
    _runtime.signal_received = False
    flight.reset(context)
    _runtime.stop_event = threading.Event()
    _runtime.thread = threading.Thread(
        target=_ble_worker,
        args=(generation, _runtime.stop_event, initial_preset_index),
        name="ArriettyT2BLE",
        daemon=True,
    )
    steering.start()
    _ensure_timer()
    _runtime.thread.start()


def stop_trainer(
    context: bpy.types.Context | None = None,
    *,
    log_event: str = "STOP",
) -> None:
    """Request a non-blocking trainer disconnect."""
    if _runtime.stop_event is not None:
        _runtime.stop_event.set()
    steering.request_stop()
    if _runtime.active:
        _runtime.status = "STOPPING"
        _runtime.message = "Stopping trainer"
        _ensure_timer()
    if context is not None:
        _stop_ride_log(context, log_event)
        if flight.reset(context):
            navigation.apply_base_pose(context, reset_running=False)
    else:
        ride_log.stop(event=log_event)


def get_runtime() -> _TrainerRuntime:
    """Expose read-only-by-convention runtime values to the UI."""
    return _runtime


def select_control_preset(preset_index: int) -> ControlPreset:
    """Select or asynchronously apply one live T2 resistance preset."""
    preset = _control_preset(preset_index)
    _runtime.selected_control_preset = preset.index
    if _runtime.status in {
        "SEARCHING", "CONNECTING", "WAITING_STEERING", "RIDING"
    }:
        _runtime.control_requests.put((_runtime.generation, preset.index))
        _runtime.control_status = f"SETTING P{preset.index}"
        _runtime.control_message = _control_description(preset)
    else:
        _runtime.control_status = f"SELECTED P{preset.index}"
        _runtime.control_message = (
            f"{_control_description(preset)}; applies on the next ride"
        )
    return preset


def step_control_preset(step: int) -> ControlPreset:
    """Move one preset up or down, clamping at the tested FTMS range."""
    current = _runtime.selected_control_preset
    target = max(1, min(len(CONTROL_PRESETS), current + step))
    if target == current:
        return _control_preset(current)
    return select_control_preset(target)


class ARRIETTY_OT_toggle_trainer(Operator):
    """Start receiving the CYCPLUS T2 trainer for the active VR visit."""

    bl_idname = "arrietty.toggle_trainer"
    bl_label = "Start CYCPLUS T2 Ride"
    bl_description = "Connect the T2 and right controller until Back to Real World"

    def execute(self, context: bpy.types.Context) -> set[str]:
        if _runtime.active:
            _runtime.message = "Ride continues until Back to Real World"
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

        try:
            start_trainer(context)
        except OSError as error:
            self.report({"ERROR"}, f"Could not start ride log: {error}")
            return {"CANCELLED"}
        return {"FINISHED"}


class ARRIETTY_OT_set_trainer_preset(Operator):
    """Select a flat-road rolling-resistance preset for the CYCPLUS T2."""

    bl_idname = "arrietty.set_trainer_preset"
    bl_label = "Set T2 Resistance Preset"
    bl_description = "Set one flat-road rolling-resistance test preset"

    preset: IntProperty(options={"SKIP_SAVE"}, min=1, max=len(CONTROL_PRESETS))

    def execute(self, _context: bpy.types.Context) -> set[str]:
        try:
            preset = select_control_preset(self.preset)
        except ValueError as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        self.report(
            {"INFO"},
            f"T2 P{preset.index}: Crr {preset.rolling_resistance:.4f}",
        )
        return {"FINISHED"}


class ARRIETTY_OT_step_trainer_preset(Operator):
    """Step the CYCPLUS T2 rolling resistance up or down."""

    bl_idname = "arrietty.step_trainer_preset"
    bl_label = "Step T2 Resistance Preset"
    bl_description = "Step the flat-road rolling-resistance preset up or down"

    step: IntProperty(options={"SKIP_SAVE"}, min=-1, max=1)

    def execute(self, _context: bpy.types.Context) -> set[str]:
        preset = step_control_preset(self.step)
        self.report(
            {"INFO"},
            f"T2 P{preset.index}: Crr {preset.rolling_resistance:.4f}",
        )
        return {"FINISHED"}


_CLASSES = (
    ARRIETTY_OT_toggle_trainer,
    ARRIETTY_OT_set_trainer_preset,
    ARRIETTY_OT_step_trainer_preset,
)


def _register_properties() -> None:
    bpy.types.Scene.arrietty_course_length = FloatProperty(
        name="Lap Length",
        description="Distance used for the completed-lap counter",
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
    for preset in CONTROL_PRESETS:
        if preset.numpad_key is None:
            continue
        item = keymap.keymap_items.new(
            ARRIETTY_OT_set_trainer_preset.bl_idname,
            type=preset.numpad_key,
            value="PRESS",
        )
        item.properties.preset = preset.index
        _addon_keymaps.append((keymap, item))
    for event_type, step in (("NUMPAD_PLUS", 1), ("NUMPAD_MINUS", -1)):
        item = keymap.keymap_items.new(
            ARRIETTY_OT_step_trainer_preset.bl_idname,
            type=event_type,
            value="PRESS",
        )
        item.properties.step = step
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
    stop_trainer(bpy.context)
    if bpy.app.timers.is_registered(_timer_tick):
        bpy.app.timers.unregister(_timer_tick)
    _runtime.timer_registered = False
    thread = _runtime.thread
    if thread is not None and thread.is_alive():
        thread.join(timeout=2.0)
    steering.stop(timeout=2.0)
    _unregister_keymaps()
    _unregister_properties()
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
