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
    "cadence_rpm",
    "power_w",
    "distance_m",
    "laps_completed",
    "flight_mode",
    "altitude_m",
    "x_m",
    "y_m",
    "heading_degrees",
)


class _RideLogRuntime:
    def __init__(self) -> None:
        self.file = None
        self.writer = None
        self.path: Path | None = None
        self.started_at = 0.0


_runtime = _RideLogRuntime()


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
    cadence_rpm: float = 0.0,
    power_w: int = 0,
    distance_m: float = 0.0,
    laps_completed: int = 0,
    flight_mode: bool = False,
    altitude_m: float = 0.0,
    x_m: float = 0.0,
    y_m: float = 0.0,
    heading_degrees: float = 0.0,
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
            "cadence_rpm": f"{cadence_rpm:.1f}",
            "power_w": power_w,
            "distance_m": f"{distance_m:.3f}",
            "laps_completed": laps_completed,
            "flight_mode": int(flight_mode),
            "altitude_m": f"{altitude_m:.3f}",
            "x_m": f"{x_m:.3f}",
            "y_m": f"{y_m:.3f}",
            "heading_degrees": f"{heading_degrees:.3f}",
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
