#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: © 2026-present Fabius Dieciscudi
# SPDX-License-Identifier: MIT

from comfyui_client.Commons import _r_int, _r_float, _r_name

W2_DEFAULTS = {
    "seed":             "56234532624987",
    "steps":            "30",
    "width":            "896",
    "height":           "1152",
    "cfg":              "4.0",
    "denoise":          "1.0",
    "sampler_name":     "dpmpp_2m",
    "scheduler":        "karras",
    "checkpoint":       "cyberrealisticXL_v90.safetensors",
    # "lora_name_01":     "None",
    # "lora_strength_01": "0.0",
    # "lora_name_02":     "None",
    # "lora_strength_02": "0.0",
    # "lora_name_03":     "None",
    # "lora_strength_03": "0.0",
    # "lora_name_04":     "None",
    # "lora_strength_04": "0.0",
    "up_steps":         "25",
    "up_width":         "0",     # 0 means "not set" (up_present will be false)
    "up_height":        "0",
    "up_cfg":           "1.0",
    "up_denoise":       "0.4",
    # "up_sampler_name":  "dpmpp_2m_sde",
    # "up_scheduler":     "karras",
    # "up_model_name":    "4x_NickelbackFS_72000_G.pth",
    "aspect":           "",      # empty means no aspect forcing
}
W2_TAG_PATTERNS = {
    "seed":             _r_int("w2.seed"),
    "steps":            _r_int("w2.steps"),
    "width":            _r_int("w2.width"),
    "height":           _r_int("w2.height"),
    "cfg":              _r_float("w2.cfg"),
    "denoise":          _r_float("w2.denoise"),
    "sampler_name":     _r_name("w2.sampler_name"),
    "scheduler":        _r_name("w2.scheduler"),
    "checkpoint":       _r_name("w2.checkpoint"),
    # "lora_name_01":     _r_name("w2.lora_name_01"),
    # "lora_strength_01": _r_float("w2.lora_strength_01"),
    # "lora_name_02":     _r_name("w2.lora_name_02"),
    # "lora_strength_02": _r_float("w2.lora_strength_02"),
    # "lora_name_03":     _r_name("w2.lora_name_03"),
    # "lora_strength_03": _r_float("w2.lora_strength_03"),
    # "lora_name_04":     _r_name("w2.lora_name_04"),
    # "lora_strength_04": _r_float("w2.lora_strength_04"),
    "up_steps":         _r_int("w2.up_steps"),
    "up_width":         _r_int("w2.up_width"),
    "up_height":        _r_int("w2.up_height"),
    "up_cfg":           _r_float("w2.up_cfg"),
    "up_denoise":       _r_float("w2.up_denoise"),
    # "up_sampler_name":  _r_name("w2.up_sampler_name"),
    # "up_scheduler":     _r_name("w2.up_scheduler"),
    # "up_model":         _r_name("w2.up_model"),
    "aspect":           r"@aspect:([0-9]*\.?[0-9]+(?::[0-9]*\.?[0-9]+)?)",
}
