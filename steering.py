# SPDX-FileCopyrightText: 2026 ysk424
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Right VIVE controller pose source for bicycle steering.

OpenVR pose reads run only while a trainer ride is active.  The first valid
controller orientation after Numpad 0 becomes the straight-ahead reference.
All shared values are plain Python data guarded by a lock; this module never
touches Blender data from its worker thread. The OpenVR client is retained for
the Blender process lifetime so stopping a ride cannot tear down SteamVR while
Blender's OpenXR session is still using it.
"""

from dataclasses import dataclass
import math
import threading
import time


RIGHT_CONTROLLER_SERIAL = "LHR-9EFF8645"
POLL_RATE_HZ = 60.0
STEERING_GAIN = 0.50
STEERING_DEADZONE_DEGREES = 1.5
MAX_EFFECTIVE_STEERING_DEGREES = 15.0
TRACKING_STALE_SECONDS = 0.5


@dataclass(frozen=True)
class SteeringSnapshot:
    """Thread-safe copy of the current steering state."""

    status: str
    message: str
    tracking: bool
    serial: str
    model: str
    raw_angle_degrees: float
    effective_angle_degrees: float
    sample_count: int
    last_pose_time: float


class _SteeringRuntime:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.status = "IDLE"
        self.message = "Right controller steering is stopped"
        self.tracking = False
        self.model = ""
        self.raw_angle_degrees = 0.0
        self.effective_angle_degrees = 0.0
        self.sample_count = 0
        self.last_pose_time = 0.0
        self.stop_event: threading.Event | None = None
        self.thread: threading.Thread | None = None


_runtime = _SteeringRuntime()
_openvr_init_lock = threading.Lock()


def _get_openvr_system(openvr):
    """Initialize OpenVR once and reuse it across sequential rides."""
    with _openvr_init_lock:
        vr = getattr(openvr, "_arrietty_vr_system", None)
        if vr is None:
            vr = openvr.init(openvr.VRApplication_Background)
            openvr._arrietty_vr_system = vr
        return vr


def _world_yaw_from_delta(current, baseline) -> float:
    """Return signed SteamVR world-Y rotation from ``baseline`` to ``current``.

    OpenVR matrices transform device-local coordinates into SteamVR world
    coordinates.  ``current @ baseline.T`` therefore removes any arbitrary
    controller mounting rotation and leaves the physical steering motion in
    world space.  Positive is left and negative is right in the tested setup.
    """
    delta_00 = sum(current[0][k] * baseline[0][k] for k in range(3))
    delta_02 = sum(current[0][k] * baseline[2][k] for k in range(3))
    return math.atan2(delta_02, delta_00)


def _effective_angle(raw_angle: float) -> float:
    """Apply the provisional dead zone, gain, and safety clamp."""
    deadzone = math.radians(STEERING_DEADZONE_DEGREES)
    magnitude = max(0.0, abs(raw_angle) - deadzone)
    effective = math.copysign(magnitude * STEERING_GAIN, raw_angle)
    limit = math.radians(MAX_EFFECTIVE_STEERING_DEGREES)
    return max(-limit, min(limit, effective))


def _rotation_tuple(matrix) -> tuple[tuple[float, float, float], ...]:
    return tuple(
        tuple(float(matrix[row][column]) for column in range(3))
        for row in range(3)
    )


def _publish(
    *,
    status: str | None = None,
    message: str | None = None,
    tracking: bool | None = None,
    model: str | None = None,
    raw_angle: float | None = None,
    effective_angle: float | None = None,
    sample_received: bool = False,
) -> None:
    with _runtime.lock:
        if status is not None:
            _runtime.status = status
        if message is not None:
            _runtime.message = message
        if tracking is not None:
            _runtime.tracking = tracking
        if model is not None:
            _runtime.model = model
        if raw_angle is not None:
            _runtime.raw_angle_degrees = math.degrees(raw_angle)
        if effective_angle is not None:
            _runtime.effective_angle_degrees = math.degrees(effective_angle)
        if sample_received:
            _runtime.sample_count += 1
            _runtime.last_pose_time = time.monotonic()


def _worker(stop_event: threading.Event) -> None:
    import openvr

    vr = None
    baseline = None
    filtered_angle = 0.0
    device_index = None
    period = 1.0 / POLL_RATE_HZ
    try:
        vr = _get_openvr_system(openvr)
        _publish(
            status="SEARCHING",
            message="Searching for the right VIVE controller",
            tracking=False,
        )

        while not stop_event.is_set():
            started = time.perf_counter()
            poses = vr.getDeviceToAbsoluteTrackingPose(
                openvr.TrackingUniverseStanding,
                0.0,
                openvr.k_unMaxTrackedDeviceCount,
            )

            if device_index is not None:
                pose = poses[device_index]
                if not pose.bDeviceIsConnected:
                    device_index = None

            if device_index is None:
                for index, pose in enumerate(poses):
                    if not pose.bDeviceIsConnected:
                        continue
                    try:
                        serial = vr.getStringTrackedDeviceProperty(
                            index, openvr.Prop_SerialNumber_String
                        )
                    except Exception:
                        continue
                    if serial == RIGHT_CONTROLLER_SERIAL:
                        device_index = index
                        try:
                            model = vr.getStringTrackedDeviceProperty(
                                index, openvr.Prop_ModelNumber_String
                            )
                        except Exception:
                            model = "VIVE Controller"
                        _publish(model=model)
                        break

            valid = False
            if device_index is not None:
                pose = poses[device_index]
                valid = bool(pose.bDeviceIsConnected and pose.bPoseIsValid)

            if valid:
                current = _rotation_tuple(pose.mDeviceToAbsoluteTracking)
                if baseline is None:
                    baseline = current
                    filtered_angle = 0.0
                    raw_angle = 0.0
                else:
                    raw_angle = _world_yaw_from_delta(current, baseline)
                    filtered_angle += 0.25 * (raw_angle - filtered_angle)
                effective = _effective_angle(filtered_angle)
                _publish(
                    status="TRACKING",
                    message="Right controller steering is ready",
                    tracking=True,
                    raw_angle=filtered_angle,
                    effective_angle=effective,
                    sample_received=True,
                )
            else:
                _publish(
                    status="LOST" if baseline is not None else "SEARCHING",
                    message=(
                        "Right controller tracking was lost"
                        if baseline is not None
                        else "Searching for the right VIVE controller"
                    ),
                    tracking=False,
                    raw_angle=0.0,
                    effective_angle=0.0,
                )

            elapsed = time.perf_counter() - started
            if elapsed < period:
                stop_event.wait(period - elapsed)
    except Exception as error:  # OpenVR reports runtime/device failures here.
        _publish(
            status="ERROR",
            message=f"Right controller error: {error}",
            tracking=False,
            raw_angle=0.0,
            effective_angle=0.0,
        )
    finally:
        # Do not call openvr.shutdown() here. SteamVR's vrclient_x64.dll is
        # shared with Blender's active OpenXR session and tearing it down at a
        # course boundary can crash Blender. The OS releases it on process exit.
        if stop_event.is_set():
            _publish(
                status="IDLE",
                message="Right controller steering is stopped",
                tracking=False,
                raw_angle=0.0,
                effective_angle=0.0,
            )


def start() -> None:
    """Start controller tracking and use its first pose as straight ahead."""
    stop(timeout=0.5)
    stop_event = threading.Event()
    with _runtime.lock:
        _runtime.status = "STARTING"
        _runtime.message = "Starting right controller steering; keep it centered"
        _runtime.tracking = False
        _runtime.model = ""
        _runtime.raw_angle_degrees = 0.0
        _runtime.effective_angle_degrees = 0.0
        _runtime.sample_count = 0
        _runtime.last_pose_time = 0.0
        _runtime.stop_event = stop_event
        _runtime.thread = threading.Thread(
            target=_worker,
            args=(stop_event,),
            name="ArriettyOpenVRSteering",
            daemon=True,
        )
        thread = _runtime.thread
    thread.start()


def request_stop() -> None:
    """Ask the OpenVR worker to stop without blocking Blender's UI thread."""
    with _runtime.lock:
        stop_event = _runtime.stop_event
    if stop_event is not None:
        stop_event.set()


def stop(timeout: float = 1.0) -> None:
    """Stop and briefly join the OpenVR worker."""
    request_stop()
    with _runtime.lock:
        thread = _runtime.thread
    if thread is not None and thread.is_alive():
        thread.join(timeout=timeout)
    with _runtime.lock:
        if _runtime.thread is thread and (thread is None or not thread.is_alive()):
            _runtime.thread = None
            _runtime.stop_event = None


def snapshot() -> SteeringSnapshot:
    """Return a consistent read-only copy for Blender's main thread and UI."""
    with _runtime.lock:
        tracking = _runtime.tracking
        last_pose_time = _runtime.last_pose_time
        if tracking and time.monotonic() - last_pose_time > TRACKING_STALE_SECONDS:
            tracking = False
        return SteeringSnapshot(
            status=_runtime.status,
            message=_runtime.message,
            tracking=tracking,
            serial=RIGHT_CONTROLLER_SERIAL,
            model=_runtime.model,
            raw_angle_degrees=_runtime.raw_angle_degrees,
            effective_angle_degrees=_runtime.effective_angle_degrees,
            sample_count=_runtime.sample_count,
            last_pose_time=last_pose_time,
        )


def is_tracking() -> bool:
    return snapshot().tracking


def get_effective_angle_radians() -> float:
    state = snapshot()
    if not state.tracking:
        return 0.0
    return math.radians(state.effective_angle_degrees)
