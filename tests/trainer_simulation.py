# SPDX-FileCopyrightText: 2026 ysk424
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Synthetic straight-course test executed with Blender in background mode."""

import math
from pathlib import Path
import sys
import threading
import time

import bpy


REPOSITORY_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_DIR.parent))

import Arrietty  # noqa: E402
from Arrietty import flight, navigation, steering, trainer  # noqa: E402


Arrietty.register()
original_apply_base_pose = navigation.apply_base_pose
original_is_tracking = steering.is_tracking
original_get_effective_angle = steering.get_effective_angle_radians
original_steering_snapshot = steering.snapshot
try:
    navigation.apply_base_pose = lambda _context, **_kwargs: None
    steering.is_tracking = lambda: True
    steering.get_effective_angle_radians = lambda: 0.0
    steering.snapshot = lambda: steering.SteeringSnapshot(
        status="TRACKING",
        message="test",
        tracking=True,
        serial=steering.RIGHT_CONTROLLER_SERIAL,
        model="test",
        raw_angle_degrees=0.0,
        effective_angle_degrees=0.0,
        sample_count=1,
        last_pose_time=time.monotonic(),
    )

    scene = bpy.context.scene
    scene.unit_settings.scale_length = 1.0
    scene.arrietty_position = (0.0, 0.0)
    scene.arrietty_altitude = 0.0
    scene.arrietty_course_length = 100.0

    runtime = trainer.get_runtime()

    # Trainer travel follows the stored bicycle heading, not the rider's gaze.
    scene.arrietty_position = (2.0, 3.0)
    scene.arrietty_heading = math.pi
    trainer._initialize_travel_state(bpy.context)
    assert runtime.start_position == (2.0, 3.0)
    assert math.isclose(abs(runtime.travel_heading), math.pi, abs_tol=1.0e-6)
    assert math.isclose(runtime.direction[0], -1.0, abs_tol=1.0e-6)
    assert math.isclose(runtime.direction[1], 0.0, abs_tol=1.0e-6)

    scene.arrietty_position = (0.0, 0.0)
    scene.arrietty_heading = 0.0
    runtime.status = "RIDING"
    runtime.speed_kmh = 36.0
    runtime.distance_m = 0.0
    runtime.course_length_m = 100.0
    runtime.start_position = (0.0, 0.0)
    runtime.direction = (1.0, 0.0)
    runtime.travel_heading = 0.0
    runtime.accumulated_turn = 0.0
    runtime.stop_event = threading.Event()

    now = time.monotonic()
    runtime.last_sample_time = now
    runtime.last_tick_time = now - 0.1
    trainer._advance_course(bpy.context, now)
    assert math.isclose(runtime.distance_m, 1.0, abs_tol=1.0e-5)
    assert math.isclose(scene.arrietty_position[0], 1.0, abs_tol=1.0e-5)
    assert math.isclose(scene.arrietty_position[1], 0.0, abs_tol=1.0e-5)

    # A completed lap is only a checkpoint; it never stops the ride.
    runtime.status = "RIDING"
    runtime.speed_kmh = 36.0
    runtime.distance_m = 142.5
    runtime.course_length_m = 143.0
    runtime.direction = (1.0, 0.0)
    runtime.travel_heading = 0.0
    runtime.stop_event = threading.Event()
    scene.arrietty_position = (0.0, 0.0)
    scene.arrietty_heading = 0.0
    now = time.monotonic()
    runtime.last_sample_time = now
    runtime.last_tick_time = now - 0.1
    trainer._advance_course(bpy.context, now)
    assert runtime.status == "RIDING"
    assert runtime.distance_m > trainer.OVAL_LAP_LENGTH_M
    assert not runtime.stop_event.is_set()
    assert trainer.completed_laps(runtime.distance_m, 143.0) == 1

    # Crossing the configured lap distance also keeps moving without capping.
    runtime.status = "RIDING"
    runtime.speed_kmh = 36.0
    runtime.distance_m = 99.0
    runtime.course_length_m = 100.0
    runtime.start_position = (1.0, 2.0)
    runtime.direction = (0.0, 1.0)
    runtime.travel_heading = math.pi / 2.0
    scene.arrietty_position = (2.0, 100.0)
    runtime.last_sample_time = now
    runtime.last_tick_time = now - 0.2
    trainer._advance_course(bpy.context, now)
    assert runtime.status == "RIDING"
    assert math.isclose(runtime.distance_m, 101.0, abs_tol=1.0e-5)
    assert math.isclose(scene.arrietty_position[0], 2.0, abs_tol=1.0e-5)
    assert math.isclose(scene.arrietty_position[1], 102.0, abs_tol=1.0e-5)
    assert not runtime.stop_event.is_set()
    assert trainer.completed_laps(runtime.distance_m, 100.0) == 1

    # A positive (left) steering angle must curve toward +Y from +X.
    runtime.status = "RIDING"
    runtime.speed_kmh = 36.0
    runtime.distance_m = 0.0
    runtime.course_length_m = 100.0
    runtime.start_position = (0.0, 0.0)
    runtime.direction = (1.0, 0.0)
    runtime.travel_heading = 0.0
    runtime.accumulated_turn = 0.0
    runtime.stop_event = threading.Event()
    scene.arrietty_position = (0.0, 0.0)
    scene.arrietty_heading = 0.0
    steering.get_effective_angle_radians = lambda: math.radians(6.0)
    now = time.monotonic()
    runtime.last_sample_time = now
    runtime.last_tick_time = now - 0.1
    trainer._advance_course(bpy.context, now)
    assert scene.arrietty_position[0] > 0.0
    assert scene.arrietty_position[1] > 0.0
    assert runtime.travel_heading > 0.0
    assert scene.arrietty_heading > 0.0

    # Regression: a bicycle heading of -X must move along -X, not -Y.
    runtime.status = "RIDING"
    runtime.speed_kmh = 36.0
    runtime.distance_m = 0.0
    runtime.course_length_m = 100.0
    runtime.direction = (-1.0, 0.0)
    runtime.travel_heading = math.pi
    runtime.accumulated_turn = 0.0
    runtime.stop_event = threading.Event()
    scene.arrietty_position = (0.0, 0.0)
    scene.arrietty_heading = math.pi
    steering.get_effective_angle_radians = lambda: 0.0
    now = time.monotonic()
    runtime.last_sample_time = now
    runtime.last_tick_time = now - 0.1
    trainer._advance_course(bpy.context, now)
    assert math.isclose(scene.arrietty_position[0], -1.0, abs_tol=1.0e-5)
    assert math.isclose(scene.arrietty_position[1], 0.0, abs_tol=1.0e-5)

    # Flight altitude is ground-relative: 10 km/h stays grounded and every
    # additional km/h adds one meter.
    runtime.status = "RIDING"
    runtime.speed_kmh = 20.0
    runtime.distance_m = 0.0
    runtime.course_length_m = 100.0
    runtime.travel_heading = 0.0
    scene.arrietty_position = (0.0, 0.0)
    steering.get_effective_angle_radians = lambda: 0.0
    assert bpy.ops.arrietty.toggle_flight_mode() == {"FINISHED"}
    now = time.monotonic()
    runtime.last_sample_time = now
    runtime.last_tick_time = now - 0.1
    trainer._advance_course(bpy.context, now)
    assert flight.snapshot().enabled
    assert flight.snapshot().altitude_m == 10.0
    assert scene.arrietty_altitude == 10.0

    runtime.speed_kmh = 10.0
    now = time.monotonic()
    runtime.last_sample_time = now
    runtime.last_tick_time = now - 0.1
    trainer._advance_course(bpy.context, now)
    assert flight.snapshot().altitude_m == 0.0
    assert scene.arrietty_altitude == 0.0
finally:
    navigation.apply_base_pose = original_apply_base_pose
    steering.is_tracking = original_is_tracking
    steering.get_effective_angle_radians = original_get_effective_angle
    steering.snapshot = original_steering_snapshot
    runtime = trainer.get_runtime()
    runtime.status = "IDLE"
    runtime.stop_event = None
    Arrietty.unregister()

print("Arrietty trainer simulation passed")
