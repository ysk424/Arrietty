# SPDX-FileCopyrightText: 2026 ysk424
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Arrietty Blender Extension entry point."""

from . import gui, navigation, steering, trainer


def register() -> None:
    """Register the extension."""
    navigation.register()
    trainer.register()
    gui.register()


def unregister() -> None:
    """Unregister the extension."""
    gui.unregister()
    trainer.unregister()
    navigation.unregister()
