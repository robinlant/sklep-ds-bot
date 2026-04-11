from __future__ import annotations

from voice_tracker import appcommands


def test_register_commands_rejects_empty_catalog() -> None:
    prev = appcommands.command_catalog
    appcommands.command_catalog = lambda: []
    try:
        try:
            appcommands.register_commands(None, object(), "app", "guild")
        except ValueError:
            pass
        else:
            raise AssertionError("expected empty catalog error")
    finally:
        appcommands.command_catalog = prev


def test_register_commands_rejects_malformed_catalog() -> None:
    prev = appcommands.command_catalog
    appcommands.command_catalog = lambda: [{}]
    try:
        try:
            appcommands.register_commands(None, object(), "app", "guild")
        except ValueError:
            pass
        else:
            raise AssertionError("expected malformed catalog error")
    finally:
        appcommands.command_catalog = prev


def test_register_commands_rejects_none_command() -> None:
    prev = appcommands.command_catalog
    appcommands.command_catalog = lambda: [None]
    try:
        try:
            appcommands.register_commands(None, object(), "app", "guild")
        except ValueError:
            pass
        else:
            raise AssertionError("expected nil command error")
    finally:
        appcommands.command_catalog = prev


def test_register_commands_rejects_duplicate_names() -> None:
    prev = appcommands.command_catalog
    appcommands.command_catalog = lambda: [{"name": "dup"}, {"name": "dup"}]
    try:
        try:
            appcommands.register_commands(None, object(), "app", "guild")
        except ValueError:
            pass
        else:
            raise AssertionError("expected duplicate name error")
    finally:
        appcommands.command_catalog = prev
