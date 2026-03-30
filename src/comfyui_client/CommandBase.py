#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: © 2026-present Fabius Dieciscudi
# SPDX-License-Identifier: MIT

"""
CommandBase.py — Abstract base class and global registry for BookAssistant commands.
"""
import time
from abc import ABC, abstractmethod
from argparse import ArgumentParser
from pathlib import Path
from Commons import error, log


class CommandBase(ABC):

    def __init__(self):
        self._start = None

    @abstractmethod
    def name(self) -> str:
        """Return the command name as it appears on the CLI (e.g. 'spellcheck')."""

    def process_args(self, parser: ArgumentParser) -> None:
        """Register this command's CLI arguments on *parser*."""
        pass

    def _prepare(self) -> None:
        self._start = time.perf_counter_ns()

    @abstractmethod
    def _run(self, args) -> None:
        """Execute the command for a single resolved *path*.

        :param args:    parsed command-line arguments
        """

    def _finish(self) -> None:
        self._duration = time.perf_counter_ns() - self._start
        log(f"Command performed in {self._duration / 1_000_000_000:.1f} sec.")

    def run(self, args) -> None:
        try:
            self._prepare()
            self._run(args)
        finally:
            self._finish()
