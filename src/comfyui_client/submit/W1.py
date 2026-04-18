#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: © 2026-present Fabius Dieciscudi
# SPDX-License-Identifier: MIT

from comfyui_client.Commons import _r_int, _r_float, _r_name

W1_DEFAULTS = {
    "seed":             "56234532624987",
    "steps":            "9",
    "width":            "1024",
    "height":           "1600",
    "cfg":              "1.0",
    "denoise":          "1.0",
    "sampler_name":     "ddim",
    "scheduler":        "sgm_uniform",
    "diffusion_model":  "z_image_turbo_bf16.safetensors",
    "clip_name":        "qwen_3_4b.safetensors",
    "clip_type":        "qwen_image",
    "vae_name":         "ae.safetensors",
    "lora_name_01":     "None",
    "lora_strength_01": "0.0",
    "lora_name_02":     "None",
    "lora_strength_02": "0.0",
    "lora_name_03":     "None",
    "lora_strength_03": "0.0",
    "lora_name_04":     "None",
    "lora_strength_04": "0.0",
    "up_steps":         "25",
    "up_width":         "0",     # 0 means "not set" (up_present will be false)
    "up_height":        "0",
    "up_cfg":           "1.0",
    "up_denoise":       "0.4",
    "up_sampler_name":  "dpmpp_2m_sde",
    "up_scheduler":     "karras",
    "up_model_name":    "4x_NickelbackFS_72000_G.pth",
    "aspect":           "",      # empty means no aspect forcing
}
W1_TAG_PATTERNS = {
    "seed":             _r_int("w1.seed"),
    "steps":            _r_int("w1.steps"),
    "width":            _r_int("w1.width"),
    "height":           _r_int("w1.height"),
    "cfg":              _r_float("w1.cfg"),
    "denoise":          _r_float("w1.denoise"),
    "sampler_name":     _r_name("w1.sampler_name"),
    "scheduler":        _r_name("w1.scheduler"),
    "diffusion_model":  _r_name("w1.diffusion_model"),
    "clip_name":        _r_name("w1.clip_name"),
    "clip_type":        _r_name("w1.clip_type"),
    "vae_name":         _r_name("w1.vae_name"),
    "lora_name_01":     _r_name("w1.lora_name_01"),
    "lora_strength_01": _r_float("w1.lora_strength_01"),
    "lora_name_02":     _r_name("w1.lora_name_02"),
    "lora_strength_02": _r_float("w1.lora_strength_02"),
    "lora_name_03":     _r_name("w1.lora_name_03"),
    "lora_strength_03": _r_float("w1.lora_strength_03"),
    "lora_name_04":     _r_name("w1.lora_name_04"),
    "lora_strength_04": _r_float("w1.lora_strength_04"),
    "up_steps":         _r_int("w1.up_steps"),
    "up_width":         _r_int("w1.up_width"),
    "up_height":        _r_int("w1.up_height"),
    "up_cfg":           _r_float("w1.up_cfg"),
    "up_denoise":       _r_float("w1.up_denoise"),
    "up_sampler_name":  _r_name("w1.up_sampler_name"),
    "up_scheduler":     _r_name("w1.up_scheduler"),
    "up_model_name":    _r_name("w1.up_model_name"),
    "aspect":           r"@aspect:([0-9]*\.?[0-9]+(?::[0-9]*\.?[0-9]+)?)",
}
