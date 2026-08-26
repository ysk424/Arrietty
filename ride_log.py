# SPDX-FileCopyrightText: 2026 ysk424
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Ride telemetry logging using one fixed, overwritten CSV filename."""

import csv
from datetime import datetime
from pathlib import Path
import time


LOG_FILENAME = "arrietty_ride.csv"
_FIELDNAMES = (
    "timestamp",
    "elapsed_s",
    "event",
    "speed_kmh",
    "ftms_speed_kmh",
    "cadence_rpm",
    "power_w",
    "distance_m",
    "laps_completed",
    "flight_mode",
    "altitude_m",
    "target_altitude_m",
    "xr_base_z_m",
    "xr_navigation_z_m",
    "xr_viewer_z_m",
    "x_m",
    "y_m",
    "heading_degrees",
    "csc_wheel_revolutions",
    "csc_wheel_event_time_ticks",
    "csc_wheel_stopped",
    "low_speed_coast_stopped",
    "t2_control_status",
    "t2_control_preset",
)


class _RideLogRuntime:
    def __init__(self) -> None:
        self.file = None
        self.writer = None
        self.path: Path | None = None
        self.started_at = 0.0


_runtime = _RideLogRuntime()


def _optional_float(value: float | None, digits: int = 3) -> str:
    return "" if value is None else f"{value:.{digits}f}"


def start(directory: Path) -> Path:
    """Overwrite the fixed ride log and begin a new logging session."""
    stop()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / LOG_FILENAME
    log_file = path.open("w", encoding="utf-8", newline="")
    writer = csv.DictWriter(log_file, fieldnames=_FIELDNAMES)
    writer.writeheader()
    log_file.flush()
    _runtime.file = log_file
    _runtime.writer = writer
    _runtime.path = path
    _runtime.started_at = time.monotonic()
    record(event="START")
    return path


def record(
    *,
    event: str = "SAMPLE",
    speed_kmh: float = 0.0,
    ftms_speed_kmh: float = 0.0,
    cadence_rpm: float = 0.0,
    power_w: int = 0,
    distance_m: float = 0.0,
    laps_completed: int = 0,
    flight_mode: bool = False,
    altitude_m: float = 0.0,
    target_altitude_m: float = 0.0,
    xr_base_z_m: float = 0.0,
    xr_navigation_z_m: float | None = None,
    xr_viewer_z_m: float | None = None,
    x_m: float = 0.0,
    y_m: float = 0.0,
    heading_degrees: float = 0.0,
    csc_wheel_revolutions: int | None = None,
    csc_wheel_event_time_ticks: int | None = None,
    csc_wheel_stopped: bool = False,
    low_speed_coast_stopped: bool = False,
    t2_control_status: str = "",
    t2_control_preset: int | None = None,
) -> None:
    """Append and flush one telemetry row when logging is active."""
    if _runtime.writer is None or _runtime.file is None:
        return
    _runtime.writer.writerow(
        {
            "timestamp": datetime.now().astimezone().isoformat(timespec="milliseconds"),
            "elapsed_s": f"{time.monotonic() - _runtime.started_at:.3f}",
            "event": event,
            "speed_kmh": f"{speed_kmh:.2f}",
            "ftms_speed_kmh": f"{ftms_speed_kmh:.2f}",
            "cadence_rpm": f"{cadence_rpm:.1f}",
            "power_w": power_w,
            "distance_m": f"{distance_m:.3f}",
            "laps_completed": laps_completed,
            "flight_mode": int(flight_mode),
            "altitude_m": f"{altitude_m:.3f}",
            "target_altitude_m": f"{target_altitude_m:.3f}",
            "xr_base_z_m": f"{xr_base_z_m:.3f}",
            "xr_navigation_z_m": _optional_float(xr_navigation_z_m),
            "xr_viewer_z_m": _optional_float(xr_viewer_z_m),
            "x_m": f"{x_m:.3f}",
            "y_m": f"{y_m:.3f}",
            "heading_degrees": f"{heading_degrees:.3f}",
            "csc_wheel_revolutions": (
                "" if csc_wheel_revolutions is None else csc_wheel_revolutions
            ),
            "csc_wheel_event_time_ticks": (
                "" if csc_wheel_event_time_ticks is None
                else csc_wheel_event_time_ticks
            ),
            "csc_wheel_stopped": int(csc_wheel_stopped),
            "low_speed_coast_stopped": int(low_speed_coast_stopped),
            "t2_control_status": t2_control_status,
            "t2_control_preset": (
                "" if t2_control_preset is None else t2_control_preset
            ),
        }
    )
    _runtime.file.flush()


def stop(event: str | None = "STOP") -> None:
    """Write the final event and close the active CSV, if any."""
    if _runtime.file is None:
        return
    if event is not None:
        record(event=event)
    _runtime.file.close()
    _runtime.file = None
    _runtime.writer = None
    _runtime.started_at = 0.0


def current_path() -> Path | None:
    return _runtime.path


def is_active() -> bool:
    return _runtime.file is not None
