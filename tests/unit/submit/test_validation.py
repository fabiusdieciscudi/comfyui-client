#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: © 2026-present Fabius Dieciscudi
# SPDX-License-Identifier: MIT
"""
Unit tests for SubmitCommand.fetch_available_options and
SubmitCommand.validate_resolved_tags.

fetch_available_options makes HTTP requests to a live ComfyUI instance; all
network calls are replaced by pytest-mock so no server is needed.

validate_resolved_tags is pure logic and needs no mocking.

Run with:
    pytest tests/unit/test_validation.py -v
"""

import pytest
import requests
from unittest.mock import MagicMock, patch
from comfyui_client.submit.SubmitCommand import SubmitCommand, DEFAULTS


BASE_URL = "http://127.0.0.1:8000"

# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

# Minimal valid KSampler object_info response
KSAMPLER_RESPONSE = {
    "KSampler": {
        "input": {
            "required": {
                "sampler_name": [["ddim", "euler", "dpmpp_2m_sde"]],
                "scheduler":    [["sgm_uniform", "karras", "simple"]],
            }
        }
    }
}

# Minimal model lists
DIFFUSION_MODELS = ["z_image_turbo_bf16.safetensors", "flux2_dev_fp8mixed.safetensors"]
CLIP_NAMES       = ["qwen_3_4b.safetensors", "mistral_3_small_flux2_bf16.safetensors"]
VAE_NAMES        = ["ae.safetensors", "flux2-vae.safetensors"]
LORA_NAMES       = ["portrait_v2.safetensors", "style_ink.safetensors"]

FULL_AVAILABLE = {
    "sampler_name":    ["ddim", "euler", "dpmpp_2m_sde"],
    "scheduler":       ["sgm_uniform", "karras", "simple"],
    "diffusion_model": DIFFUSION_MODELS,
    "clip_name":       CLIP_NAMES,
    "vae_name":        VAE_NAMES,
    "lora_name":       LORA_NAMES,
}


def make_response(json_data, status_code=200):
    """Build a mock requests.Response."""
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = json_data
    mock.raise_for_status = MagicMock()
    if status_code >= 400:
        mock.raise_for_status.side_effect = requests.HTTPError(
            f"HTTP {status_code}"
        )
    return mock


def make_side_effect(ksampler=None, diffusion=None, clip=None, vae=None, lora=None):
    """
    Return a side_effect callable for requests.get that dispatches on URL.
    Any argument left as None uses the module-level defaults.
    """
    responses = {
        "/object_info":             make_response(ksampler  or KSAMPLER_RESPONSE),
        "/models/diffusion_models": make_response(diffusion or DIFFUSION_MODELS),
        "/models/text_encoders":    make_response(clip      or CLIP_NAMES),
        "/models/vae":              make_response(vae       or VAE_NAMES),
        "/models/loras":            make_response(lora      or LORA_NAMES),
    }

    def side_effect(url, **kwargs):
        for fragment, mock_resp in responses.items():
            if fragment in url:
                return mock_resp
        raise ValueError(f"Unexpected URL in test: {url}")

    return side_effect


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def cmd():
    return SubmitCommand()


@pytest.fixture
def all_defaults():
    """A resolved dict where every value is the documented default."""
    return dict(DEFAULTS)


# ===========================================================================
# fetch_available_options
# ===========================================================================

class TestFetchAvailableOptionsSuccess:

    def test_returns_sampler_name_list(self, cmd):
        # given
        with patch("requests.get", side_effect=make_side_effect()):
            # when
            result = cmd.fetch_available_options(BASE_URL)
        # then
        assert result["sampler_name"] == ["ddim", "euler", "dpmpp_2m_sde"]

    def test_returns_scheduler_list(self, cmd):
        # given
        with patch("requests.get", side_effect=make_side_effect()):
            # when
            result = cmd.fetch_available_options(BASE_URL)
        # then
        assert result["scheduler"] == ["sgm_uniform", "karras", "simple"]

    def test_returns_diffusion_model_list(self, cmd):
        # given
        with patch("requests.get", side_effect=make_side_effect()):
            # when
            result = cmd.fetch_available_options(BASE_URL)
        # then
        assert result["diffusion_model"] == DIFFUSION_MODELS

    def test_returns_clip_name_list(self, cmd):
        # given
        with patch("requests.get", side_effect=make_side_effect()):
            # when
            result = cmd.fetch_available_options(BASE_URL)
        # then
        assert result["clip_name"] == CLIP_NAMES

    def test_returns_vae_name_list(self, cmd):
        # given
        with patch("requests.get", side_effect=make_side_effect()):
            # when
            result = cmd.fetch_available_options(BASE_URL)
        # then
        assert result["vae_name"] == VAE_NAMES

    def test_returns_lora_name_list(self, cmd):
        # given
        with patch("requests.get", side_effect=make_side_effect()):
            # when
            result = cmd.fetch_available_options(BASE_URL)
        # then
        assert result["lora_name"] == LORA_NAMES

    def test_all_six_keys_present(self, cmd):
        # given
        with patch("requests.get", side_effect=make_side_effect()):
            # when
            result = cmd.fetch_available_options(BASE_URL)
        # then
        expected_keys = {
            "sampler_name", "scheduler",
            "diffusion_model", "clip_name", "vae_name", "lora_name",
        }
        assert expected_keys == set(result.keys())

    def test_uses_base_url_for_all_requests(self, cmd):
        # given
        calls = []
        original_side_effect = make_side_effect()

        def recording_side_effect(url, **kwargs):
            calls.append(url)
            return original_side_effect(url, **kwargs)

        with patch("requests.get", side_effect=recording_side_effect):
            # when
            cmd.fetch_available_options(BASE_URL)

        # then: every request uses the correct base URL
        assert all(url.startswith(BASE_URL) for url in calls)

    def test_makes_five_requests(self, cmd):
        # given: one for KSampler, four for model types
        calls = []
        original_side_effect = make_side_effect()

        def recording_side_effect(url, **kwargs):
            calls.append(url)
            return original_side_effect(url, **kwargs)

        with patch("requests.get", side_effect=recording_side_effect):
            # when
            cmd.fetch_available_options(BASE_URL)

        # then
        assert len(calls) == 5


class TestFetchAvailableOptionsFailures:

    def test_ksampler_request_failure_raises_runtime_error(self, cmd):
        # given: the KSampler endpoint times out
        def side_effect(url, **kwargs):
            if "object_info" in url:
                raise requests.ConnectionError("timed out")
            return make_response([])

        with patch("requests.get", side_effect=side_effect):
            # when / then
            with pytest.raises(RuntimeError, match="sampler"):
                cmd.fetch_available_options(BASE_URL)

    def test_ksampler_http_error_raises_runtime_error(self, cmd):
        # given: the KSampler endpoint returns 500
        def side_effect(url, **kwargs):
            if "object_info" in url:
                return make_response({}, status_code=500)
            return make_response([])

        with patch("requests.get", side_effect=side_effect):
            with pytest.raises(RuntimeError, match="sampler"):
                cmd.fetch_available_options(BASE_URL)

    def test_ksampler_missing_key_raises_runtime_error(self, cmd):
        # given: the response is valid JSON but lacks the expected structure
        bad_response = {"KSampler": {"input": {"required": {}}}}

        def side_effect(url, **kwargs):
            if "object_info" in url:
                return make_response(bad_response)
            return make_response([])

        with patch("requests.get", side_effect=side_effect):
            with pytest.raises(RuntimeError, match="sampler"):
                cmd.fetch_available_options(BASE_URL)

    @pytest.mark.parametrize("failing_endpoint,expected_key", [
        ("diffusion_models", "diffusion_model"),
        ("text_encoders",    "clip_name"),
        ("vae",              "vae_name"),
        ("loras",            "lora_name"),
    ])
    def test_model_endpoint_failure_raises_runtime_error(
            self, cmd, failing_endpoint, expected_key
    ):
        # given: one of the /models/* endpoints fails
        def side_effect(url, **kwargs):
            if "object_info" in url:
                return make_response(KSAMPLER_RESPONSE)
            if failing_endpoint in url:
                raise requests.ConnectionError("refused")
            return make_response([])

        with patch("requests.get", side_effect=side_effect):
            # when / then: error message mentions the tag key
            with pytest.raises(RuntimeError, match=expected_key):
                cmd.fetch_available_options(BASE_URL)


# ===========================================================================
# validate_resolved_tags
# ===========================================================================

class TestValidateNoErrors:

    def test_all_defaults_against_full_available_returns_no_errors(
            self, cmd, all_defaults
    ):
        # given: defaults are all present in FULL_AVAILABLE
        # when
        errors = cmd.validate_resolved_tags(all_defaults, FULL_AVAILABLE)
        # then
        assert errors == []

    def test_empty_available_dict_returns_no_errors(self, cmd, all_defaults):
        # given: available is empty — nothing to check against
        # when
        errors = cmd.validate_resolved_tags(all_defaults, {})
        # then: no errors because there are no constraints
        assert errors == []

    def test_empty_available_list_for_a_key_skips_that_check(self, cmd):
        # given: diffusion_model list is empty (endpoint returned [])
        available = {**FULL_AVAILABLE, "diffusion_model": []}
        resolved = {**DEFAULTS, "diffusion_model": "any_model.safetensors"}
        # when
        errors = cmd.validate_resolved_tags(resolved, available)
        # then: no error raised for diffusion_model
        assert not any("diffusion_model" in e for e in errors)


class TestValidateSingleTagFailures:

    @pytest.mark.parametrize("tag_key,avail_key,bad_value", [
        ("sampler_name",    "sampler_name",    "bogus_sampler"),
        ("scheduler",       "scheduler",       "bogus_scheduler"),
        ("diffusion_model", "diffusion_model", "nonexistent.safetensors"),
        ("clip_name",       "clip_name",       "missing_clip.safetensors"),
        ("vae_name",        "vae_name",        "missing_vae.safetensors"),
    ])
    def test_unsupported_value_produces_one_error(
            self, cmd, tag_key, avail_key, bad_value
    ):
        # given
        resolved = {**DEFAULTS, tag_key: bad_value}
        # when
        errors = cmd.validate_resolved_tags(resolved, FULL_AVAILABLE)
        # then: exactly one error mentioning the tag and the bad value
        assert len(errors) == 1
        assert tag_key   in errors[0]
        assert bad_value in errors[0]

    @pytest.mark.parametrize("tag_key,avail_key,bad_value", [
        ("sampler_name",    "sampler_name",    "bogus_sampler"),
        ("scheduler",       "scheduler",       "bogus_scheduler"),
        ("diffusion_model", "diffusion_model", "nonexistent.safetensors"),
        ("clip_name",       "clip_name",       "missing_clip.safetensors"),
        ("vae_name",        "vae_name",        "missing_vae.safetensors"),
    ])
    def test_error_message_lists_available_options(
            self, cmd, tag_key, avail_key, bad_value
    ):
        # given
        resolved = {**DEFAULTS, tag_key: bad_value}
        # when
        errors = cmd.validate_resolved_tags(resolved, FULL_AVAILABLE)
        # then: the error message names at least one of the valid options
        valid_options = FULL_AVAILABLE[avail_key]
        assert any(opt in errors[0] for opt in valid_options)


class TestValidateLoraSlots:

    def test_active_lora_slot_with_valid_name_produces_no_error(self, cmd):
        # given
        resolved = {**DEFAULTS, "lora_name_01": "portrait_v2.safetensors"}
        # when
        errors = cmd.validate_resolved_tags(resolved, FULL_AVAILABLE)
        # then
        assert errors == []

    def test_active_lora_slot_with_invalid_name_produces_error(self, cmd):
        # given
        resolved = {**DEFAULTS, "lora_name_01": "ghost_lora.safetensors"}
        # when
        errors = cmd.validate_resolved_tags(resolved, FULL_AVAILABLE)
        # then
        assert len(errors) == 1
        assert "lora_name_01"         in errors[0]
        assert "ghost_lora.safetensors" in errors[0]

    def test_none_lora_slot_is_skipped(self, cmd):
        # given: default value for an unused slot
        resolved = {**DEFAULTS, "lora_name_01": "None"}
        # when
        errors = cmd.validate_resolved_tags(resolved, FULL_AVAILABLE)
        # then: no error for the inactive slot
        assert errors == []

    def test_empty_string_lora_slot_is_skipped(self, cmd):
        # given
        resolved = {**DEFAULTS, "lora_name_02": ""}
        # when
        errors = cmd.validate_resolved_tags(resolved, FULL_AVAILABLE)
        # then
        assert errors == []

    def test_lora_slot_case_insensitive_none_is_skipped(self, cmd):
        # given: "none" in lowercase should also be treated as inactive
        resolved = {**DEFAULTS, "lora_name_03": "none"}
        # when
        errors = cmd.validate_resolved_tags(resolved, FULL_AVAILABLE)
        # then
        assert errors == []

    def test_all_four_lora_slots_validated_independently(self, cmd):
        # given: slots 01 and 03 are bad; 02 and 04 are fine / inactive
        resolved = {
            **DEFAULTS,
            "lora_name_01": "bad_lora_a.safetensors",
            "lora_name_02": "portrait_v2.safetensors",   # valid
            "lora_name_03": "bad_lora_b.safetensors",
            "lora_name_04": "None",                       # inactive
        }
        # when
        errors = cmd.validate_resolved_tags(resolved, FULL_AVAILABLE)
        # then: exactly two errors, one per bad slot
        assert len(errors) == 2
        assert any("lora_name_01" in e for e in errors)
        assert any("lora_name_03" in e for e in errors)

    def test_empty_lora_name_list_skips_lora_validation(self, cmd):
        # given: the server returned an empty lora list
        available = {**FULL_AVAILABLE, "lora_name": []}
        resolved  = {**DEFAULTS, "lora_name_01": "any_lora.safetensors"}
        # when
        errors = cmd.validate_resolved_tags(resolved, available)
        # then: no error because there are no constraints
        assert errors == []


class TestValidateMultipleErrors:

    def test_two_bad_values_produce_two_errors(self, cmd):
        # given
        resolved = {
            **DEFAULTS,
            "sampler_name": "bogus_sampler",
            "scheduler":    "bogus_scheduler",
        }
        # when
        errors = cmd.validate_resolved_tags(resolved, FULL_AVAILABLE)
        # then
        assert len(errors) == 2

    def test_all_single_tags_bad_produces_five_errors(self, cmd):
        # given: every single-value tag is wrong
        resolved = {
            **DEFAULTS,
            "sampler_name":    "bad_sampler",
            "scheduler":       "bad_scheduler",
            "diffusion_model": "bad_model.safetensors",
            "clip_name":       "bad_clip.safetensors",
            "vae_name":        "bad_vae.safetensors",
        }
        # when
        errors = cmd.validate_resolved_tags(resolved, FULL_AVAILABLE)
        # then
        assert len(errors) == 5

    def test_each_error_identifies_its_own_tag(self, cmd):
        # given
        resolved = {
            **DEFAULTS,
            "sampler_name":    "bad_sampler",
            "diffusion_model": "bad_model.safetensors",
        }
        # when
        errors = cmd.validate_resolved_tags(resolved, FULL_AVAILABLE)
        # then: each error clearly names the offending tag
        assert any("sampler_name"    in e for e in errors)
        assert any("diffusion_model" in e for e in errors)