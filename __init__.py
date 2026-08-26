# SPDX-FileCopyrightText: 2026 ysk424
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Arrietty Blender Extension entry point."""

from . import flight, gui, instrument_panel, navigation, ride_log, steering, trainer


def register() -> None:
    """Register the extension."""
    navigation.register()
    flight.register()
    trainer.register()
    instrument_panel.register()
    gui.register()


def unregister() -> None:
    """Unregister the extension."""
    gui.unregister()
    instrument_panel.unregister()
    trainer.unregister()
    flight.unregister()
    navigation.unregister()
