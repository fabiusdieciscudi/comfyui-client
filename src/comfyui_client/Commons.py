#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: © 2026-present Fabius Dieciscudi
# SPDX-License-Identifier: MIT

"""
Commons.py — Shared utilities for ComfyUI Client.
"""

import sys
import time
from typing import Any, Tuple, Callable

# When True, debug() calls emit output; set via set_debug().
debugging = False

# When True, info() calls emit output; set via set_verbose().
verbose = False

# ANSI colour codes
RED     = "\033[31m"
YELLOW  = "\033[93m"
GREEN   = "\033[32m"
MAGENTA = "\033[35m"
CYAN    = "\033[36m"
BLUE    = "\033[34m"
RESET   = "\033[0m"   # Resets all attributes back to the terminal default.

def coloured(line: str, start_pos: int, end_pos: int, colour: str) -> str:
    """Wrap a substring of *line* in an ANSI colour code.

    Characters outside [start_pos, end_pos) are left unchanged.

    :param line:        the full string to colourise
    :param start_pos:   inclusive start index of the coloured range
    :param end_pos:     exclusive end index of the coloured range
    :param colour:      an ANSI escape sequence (e.g. RED, YELLOW …)
    :return:            the string with the chosen range wrapped in colour codes
    """
    return f"{line[:start_pos]}{colour}{line[start_pos:end_pos]}{RESET}{line[end_pos:]}"

def red2(line: str, start_pos: int, end_pos: int) -> str:
    """Colour a substring of *line* in red."""
    return coloured(line, start_pos, end_pos, RED)

def red(line: str) -> str:
    """Colour the entire *line* in red."""
    return red2(line, 0, len(line))

def yellow2(line: str, start_pos: int, end_pos: int) -> str:
    """Colour a substring of *line* in yellow."""
    return coloured(line, start_pos, end_pos, YELLOW)

def yellow(line: str) -> str:
    """Colour the entire *line* in yellow."""
    return yellow2(line, 0, len(line))

def green2(line: str, start_pos: int, end_pos: int) -> str:
    """Colour a substring of *line* in green."""
    return coloured(line, start_pos, end_pos, GREEN)

def green(line: str) -> str:
    """Colour the entire *line* in green."""
    return green2(line, 0, len(line))

def magenta2(line: str, start_pos: int, end_pos: int) -> str:
    """Colour a substring of *line* in magenta."""
    return coloured(line, start_pos, end_pos, MAGENTA)

def magenta(line: str) -> str:
    """Colour the entire *line* in magenta."""
    return magenta2(line, 0, len(line))

def cyan2(line: str, start_pos: int, end_pos: int) -> str:
    """Colour a substring of *line* in cyan."""
    return coloured(line, start_pos, end_pos, CYAN)

def cyan(line: str) -> str:
    """Colour the entire *line* in cyan."""
    return cyan2(line, 0, len(line))

def blue2(line: str, start_pos: int, end_pos: int) -> str:
    """Colour a substring of *line* in blue."""
    return coloured(line, start_pos, end_pos, BLUE)

def blue(line: str) -> str:
    """Colour the entire *line* in blue."""
    return blue2(line, 0, len(line))

def count_words(text: str) -> int:
    """Return the number of whitespace-delimited tokens in *text*.

    Returns 0 for empty or None-like input (the falsy guard handles both
    an empty string and a None value passed by mistake).

    :param text:    the string to count words in
    :return:        word count
    """
    return len(text.split()) if text else 0

def log(message: str, new_line: bool = True) -> None:
    """Write *message* to stderr.

    When *new_line* is False the line ends with a carriage return and an
    ANSI erase-to-end-of-line sequence (\033[K) instead of a newline,
    producing an in-place progress indicator that overwrites itself on the
    next call.

    :param message:     text to print
    :param new_line:    if True (default) append \\n; if False overwrite the
                        current terminal line (used for progress display)
    """
    print(message + ("" if new_line else "\033[K"), file=sys.stderr, end="\n" if new_line else "\r")

def error(message: str) -> None:
    """Log *message* in red to stderr.

    Intended for non-fatal user-facing errors such as missing files or
    unsupported language tags.

    :param message:     error description
    """
    log(red(f"ERROR: {message}"))

def warning(message: str) -> None:
    """Log *message* in yellow to stderr.

    Intended for warnings.

    :param message:     warning description
    """
    log(yellow(f"WARNING: {message}"))

def info(message: str) -> None:
    """Log *message* in blue to stderr, but only when verbose mode is enabled.

    No-op unless set_verbose(True) has been called.  Intended for
    higher-level operational messages that are more user-facing than
    debug() output but still optional in normal use — for example,
    resolved tag values, fragment expansion steps, or validation results.

    :param message:     informational text
    """
    if verbose:
        log(blue(f"{message}"))

def debug(message: str) -> None:
    """Log *message* in magenta to stderr, but only when debugging is enabled.

    No-op unless set_debug(True) has been called. Use for internal
    diagnostics that would be too noisy in normal operation (e.g.
    LanguageTool initialisation times, per-file tracing).

    :param message:     diagnostic text
    """
    if debugging:
        log(magenta(message))

def set_verbose(_verbose: bool) -> None:
    """Enable or disable informational logging globally.

    Flips the module-level *verbose* flag consulted by info().
    Called once at startup from the CLI argument parser.

    :param _verbose:    True to enable info output, False to suppress it
    """
    global verbose
    verbose = _verbose

def is_verbose() -> bool:
    return verbose

def set_debug(_debug: bool) -> None:
    """Enable or disable verbose debug logging globally.

    Flips the module-level *debugging* flag consulted by debug().
    Called once at startup from the CLI argument parser.

    :param _debug:  True to enable debug output, False to suppress it
    """
    global debugging
    debugging = _debug

def is_debug() -> bool:
    return debugging

def measure_time(func: Callable[[], Any]) -> Tuple[Any, float]:
    """Call *func*, measure its wall-clock duration, and return both.

    :param func:    a zero-argument callable to time
    :return:        a (result, elapsed_seconds) tuple where *result* is whatever *func* returned and *elapsed_seconds* is a float
    """
    start = time.perf_counter_ns()
    result = func()
    end = time.perf_counter_ns()
    return result, (end - start) / 1_000_000_000