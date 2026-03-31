#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: © 2026-present Fabius Dieciscudi
# SPDX-License-Identifier: MIT

from comfyui_client import COMMANDS
from .SetMetadataCommand import SetMetadataCommand
COMMANDS.append(SetMetadataCommand())