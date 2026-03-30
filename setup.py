#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: © 2026-present Fabius Dieciscudi
# SPDX-License-Identifier: MIT

from setuptools import setup, find_packages

setup(
    name="comfyui-client",
    version="1.0",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
)