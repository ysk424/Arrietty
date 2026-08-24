# SPDX-FileCopyrightText: 2026 ysk424
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Arrietty controls in the 3D Viewport sidebar."""

import math

import bpy
from bpy.types import Operator, Panel

from . import navigation, steering, trainer


VERSION = "0.5.0"


def _has_openxr_support() -> bool:
    """Return whether this Blender build includes OpenXR support."""
    return bool(getattr(bpy.app.build_options, "xr_openxr", False))


def _is_vr_session_running(context: bpy.types.Context) -> bool:
    """Return the Blender OpenXR session state without raising in non-XR builds."""
    if not _has_openxr_support():
        return False

    try:
        return bpy.types.XrSessionState.is_running(context)
    except (AttributeError, RuntimeError):
        return False


def _toggle_xr_session() -> set[str]:
    """Invoke Blender's native OpenXR session toggle."""
    return bpy.ops.wm.xr_session_toggle()


class ARRIETTY_OT_toggle_vr_session(Operator):
    """Start or stop Blender's OpenXR session."""

    bl_idname = "arrietty.toggle_vr_session"
    bl_label = "Toggle VR Session"
    bl_description = "Start or stop the Blender OpenXR session"

    def execute(self, context: bpy.types.Context) -> set[str]:
        if not _has_openxr_support():
            self.report(
                {"ERROR"},
                "OpenXR support is unavailable in this Blender build",
            )
            return {"CANCELLED"}

        was_running = _is_vr_session_running(context)

        if not was_running:
            navigation.apply_base_pose(context, reset_running=False)

        try:
            result = _toggle_xr_session()
        except (AttributeError, RuntimeError) as error:
            action = "stop" if was_running else "start"
            self.report(
                {"ERROR"},
                f"Could not {action} the VR session: {error}",
            )
            return {"CANCELLED"}

        if "CANCELLED" in result:
            if was_running:
                message = "Could not stop the VR session"
            else:
                message = (
                    "Could not start VR. Start SteamVR, set it as the active "
                    "OpenXR runtime, and connect the HMD"
                )
            self.report({"ERROR"}, message)
            return {"CANCELLED"}

        return {"FINISHED"}


class ARRIETTY_PT_vr_session(Panel):
    """Show the single Arrietty VR session control."""

    bl_idname = "ARRIETTY_PT_vr_session"
    bl_label = "Arrietty"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Arrietty"

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout

        layout.label(text=f"Version v{VERSION}")
        layout.separator()

        is_running = _is_vr_session_running(context)
        text = "Back to Real World" if is_running else "Dive into Secret World"
        icon = "CANCEL" if is_running else "PLAY"
        layout.operator(
            ARRIETTY_OT_toggle_vr_session.bl_idname,
            text=text,
            icon=icon,
            depress=is_running,
        )

        layout.separator()
        layout.label(text="Start Pose")
        x, y = context.scene.arrietty_position
        heading = math.degrees(context.scene.arrietty_heading)
        layout.label(text=f"X {x:.2f} m   Y {y:.2f} m   Z {navigation.EYE_HEIGHT_M:.2f} m")
        layout.label(text=f"Direction {heading:.1f} degrees")

        row = layout.row(align=True)
        row.prop(context.scene, "arrietty_move_step", text="Move")
        row.prop(context.scene, "arrietty_turn_step", text="Turn")

        controls = layout.box()
        controls.label(text="Numpad 8 / 2: Forward / Back")
        controls.label(text="Numpad 4 / 6: Turn Left / Right")
        controls.label(text="Forward follows the current HMD view")

        hmd_forward = navigation.get_hmd_forward(context)
        if hmd_forward is not None:
            controls.label(text=f"HMD Forward X {hmd_forward.x:.3f}  Y {hmd_forward.y:.3f}")

        layout.separator()
        runtime = trainer.get_runtime()
        trainer_box = layout.box()
        trainer_box.label(text="CYCPLUS T2")
        trainer_box.prop(context.scene, "arrietty_course_length", text="Course")
        trainer_box.operator(
            trainer.ARRIETTY_OT_toggle_trainer.bl_idname,
            text="Stop Ride" if runtime.active else "Start Ride (Numpad 0)",
            icon="CANCEL" if runtime.active else "PLAY",
            depress=runtime.active,
        )
        trainer_box.label(text=f"Status: {runtime.status}")
        trainer_box.label(text=runtime.message)
        trainer_box.label(
            text=(
                f"{runtime.speed_kmh:.2f} km/h   "
                f"{runtime.cadence_rpm:.0f} rpm   {runtime.power_w} W"
            )
        )
        trainer_box.label(
            text=f"Distance {runtime.distance_m:.1f} / {runtime.course_length_m:.1f} m"
        )

        steering_state = steering.snapshot()
        steering_box = layout.box()
        steering_box.label(text="Right Controller Steering")
        steering_box.label(text=f"Status: {steering_state.status}")
        steering_box.label(text=steering_state.message)
        steering_box.label(
            text=(
                f"Raw {steering_state.raw_angle_degrees:+.1f} degrees   "
                f"Applied {steering_state.effective_angle_degrees:+.1f} degrees"
            )
        )
        steering_box.label(text=f"ID: {steering_state.serial}")

        if not _has_openxr_support():
            error_box = layout.box()
            error_box.label(text="OpenXR is unavailable", icon="ERROR")
            error_box.label(text="in this Blender build")


_CLASSES = (
    ARRIETTY_OT_toggle_vr_session,
    ARRIETTY_PT_vr_session,
)


def register() -> None:
    """Register Arrietty UI classes."""
    for cls in _CLASSES:
        bpy.utils.register_class(cls)


def unregister() -> None:
    """Unregister Arrietty UI classes."""
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
