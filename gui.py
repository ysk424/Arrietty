# SPDX-FileCopyrightText: 2026 ysk424
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Arrietty controls in the 3D Viewport sidebar."""

import bpy
from bpy.types import Operator, Panel


VERSION = "0.1.0"


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
