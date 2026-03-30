#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: © 2026-present Fabius Dieciscudi
# SPDX-License-Identifier: MIT

import argparse
import importlib
from pathlib import Path
import comfyui_client
from CommandBase import CommandBase
from Commons import set_debug, error
from Version import __version__


def _load_commands() -> None:
    """Import every direct subpackage of comfyui_client.

    Each subpackage __init__.py is responsible for appending its own
    command instance to CommandBase.COMMANDS.
    """
    pkg_path = Path(comfyui_client.__file__).parent
    for sub in sorted(pkg_path.iterdir()):
        if sub.is_dir() and (sub / "__init__.py").exists():
            importlib.import_module(f"comfyui_client.{sub.name}")


if __name__ == '__main__':
    _load_commands()
    command_map: dict[str, CommandBase] = {cmd.name(): cmd for cmd in comfyui_client.COMMANDS}
    parser = argparse.ArgumentParser(description="ComfyUIClient")
    parser.add_argument("command", choices=list(command_map), help="Command to run.")
    parser.add_argument("--version", action="version", version=f"BookAssistant {__version__}")
    parser.add_argument("--debug", action="store_true", default=False, help="Verbose logging.")
    parser.add_argument("--dry-run", action="store_true", default=False, help="Validate without time-expensive operations.")

    for command in command_map.values():
        command.process_args(parser)

    args = parser.parse_args()
    set_debug(args.debug)
    command_map[args.command].run(args)