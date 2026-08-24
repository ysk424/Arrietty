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
from Arrietty import navigation, trainer  # noqa: E402


Arrietty.register()
original_apply_base_pose = navigation.apply_base_pose
original_finish_sound = trainer._play_finish_sound
try:
    navigation.apply_base_pose = lambda _context, **_kwargs: None
    trainer._play_finish_sound = lambda: None

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
    runtime.stop_event = threading.Event()

    now = time.monotonic()
    runtime.last_sample_time = now
    runtime.last_tick_time = now - 0.1
    trainer._advance_straight_course(bpy.context, now)
    assert math.isclose(runtime.distance_m, 1.0, abs_tol=1.0e-5)
    assert math.isclose(scene.arrietty_position[0], 0.0, abs_tol=1.0e-5)
    assert math.isclose(scene.arrietty_position[1], 1.0, abs_tol=1.0e-5)

    runtime.status = "RIDING"
    runtime.distance_m = 99.0
    runtime.start_position = (1.0, 2.0)
    runtime.direction = (1.0, 0.0)
    runtime.last_sample_time = now
    runtime.last_tick_time = now - 0.2
    trainer._advance_straight_course(bpy.context, now)
    assert runtime.status == "FINISHED"
    assert runtime.distance_m == 100.0
    assert tuple(scene.arrietty_position) == (101.0, 2.0)
    assert runtime.stop_event.is_set()
finally:
    navigation.apply_base_pose = original_apply_base_pose
    trainer._play_finish_sound = original_finish_sound
    runtime = trainer.get_runtime()
    runtime.status = "IDLE"
    runtime.stop_event = None
    Arrietty.unregister()

print("Arrietty trainer simulation passed")
