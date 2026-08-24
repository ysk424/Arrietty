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
from Arrietty import navigation, steering, trainer  # noqa: E402


Arrietty.register()
original_apply_base_pose = navigation.apply_base_pose
original_finish_sound = trainer._play_finish_sound
original_is_tracking = steering.is_tracking
original_get_effective_angle = steering.get_effective_angle_radians
original_steering_snapshot = steering.snapshot
try:
    navigation.apply_base_pose = lambda _context, **_kwargs: None
    trainer._play_finish_sound = lambda: None
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
    scene.arrietty_course_length = 100.0

    runtime = trainer.get_runtime()
    runtime.status = "RIDING"
    runtime.speed_kmh = 36.0
    runtime.distance_m = 0.0
    runtime.course_length_m = 100.0
    runtime.start_position = (0.0, 0.0)
    runtime.direction = (0.0, 1.0)
    runtime.travel_heading = 0.0
    runtime.accumulated_turn = 0.0
    runtime.stop_event = threading.Event()

    now = time.monotonic()
    runtime.last_sample_time = now
    runtime.last_tick_time = now - 0.1
    trainer._advance_course(bpy.context, now)
    assert math.isclose(runtime.distance_m, 1.0, abs_tol=1.0e-5)
    assert math.isclose(scene.arrietty_position[0], 0.0, abs_tol=1.0e-5)
    assert math.isclose(scene.arrietty_position[1], 1.0, abs_tol=1.0e-5)

    runtime.status = "RIDING"
    runtime.distance_m = 99.0
    runtime.start_position = (1.0, 2.0)
    runtime.direction = (1.0, 0.0)
    runtime.travel_heading = -math.pi / 2.0
    scene.arrietty_position = (100.0, 2.0)
    runtime.last_sample_time = now
    runtime.last_tick_time = now - 0.2
    trainer._advance_course(bpy.context, now)
    assert runtime.status == "FINISHED"
    assert runtime.distance_m == 100.0
    assert tuple(scene.arrietty_position) == (101.0, 2.0)
    assert runtime.stop_event.is_set()

    # A positive (left) steering angle must curve left while travelling +Y.
    runtime.status = "RIDING"
    runtime.speed_kmh = 36.0
    runtime.distance_m = 0.0
    runtime.course_length_m = 100.0
    runtime.start_position = (0.0, 0.0)
    runtime.direction = (0.0, 1.0)
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
    assert scene.arrietty_position[0] < 0.0
    assert scene.arrietty_position[1] > 0.0
    assert runtime.travel_heading > 0.0
    assert scene.arrietty_heading > 0.0
finally:
    navigation.apply_base_pose = original_apply_base_pose
    trainer._play_finish_sound = original_finish_sound
    steering.is_tracking = original_is_tracking
    steering.get_effective_angle_radians = original_get_effective_angle
    steering.snapshot = original_steering_snapshot
    runtime = trainer.get_runtime()
    runtime.status = "IDLE"
    runtime.stop_event = None
    Arrietty.unregister()

print("Arrietty trainer simulation passed")
