# SPDX-FileCopyrightText: 2026 ysk424
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Arrietty Blender Extension entry point."""

from . import gui


def register() -> None:
    """Register the extension."""
    gui.register()


def unregister() -> None:
    """Unregister the extension."""
    gui.unregister()
