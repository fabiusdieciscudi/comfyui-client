#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: © 2026-present Fabius Dieciscudi
# SPDX-License-Identifier: MIT
"""
Unit tests for SubmitCommand.extract_tags.

extract_tags calls strip_comments internally, so comment-stripping behaviour
is tested here in combination with tag extraction. Line-oriented tags
(@keyword, @title, @description) are NOT handled by this method and are
therefore out of scope.

Run with:
    pytest tests/unit/test_extract_tags.py -v
"""

import pytest
from comfyui_client.submit.SubmitCommand import SubmitCommand, W1_DEFAULTS

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def cmd():
    """A bare SubmitCommand instance (no CLI args needed for pure methods)."""
    return SubmitCommand()


def extract(cmd, prompt):
    """Thin wrapper so tests read naturally."""
    return cmd.extract_tags(prompt, "w1")


def assert_defaults(result, except_for=None):
    """Assert that every key matches W1_DEFAULTS, optionally skipping some."""
    except_for = except_for or {}
    for key, default_value in W1_DEFAULTS.items():
        if key in except_for:
            assert result[key] == except_for[key], \
                f"Expected {key}={except_for[key]!r}, got {result[key]!r}"
        else:
            assert result[key] == default_value, \
                f"Expected {key} to be default {default_value!r}, got {result[key]!r}"


# ---------------------------------------------------------------------------
# Empty / trivial input
# ---------------------------------------------------------------------------

class TestEmptyInput:

    def test_empty_string_returns_all_defaults(self, cmd):
        # given
        prompt = ""
        # when
        result = extract(cmd, prompt)
        # then
        assert_defaults(result)

    def test_whitespace_only_returns_all_defaults(self, cmd):
        # given
        prompt = "   \n\t\n  "
        # when
        result = extract(cmd, prompt)
        # then
        assert_defaults(result)

    def test_plain_prompt_no_tags_returns_all_defaults(self, cmd):
        # given
        prompt = "A cat sitting on a sofa, smoking a pipe"
        # when
        result = extract(cmd, prompt)
        # then
        assert_defaults(result)


# ---------------------------------------------------------------------------
# Comment stripping
# ---------------------------------------------------------------------------

class TestCommentStripping:

    def test_full_line_comment_is_ignored(self, cmd):
        # given: a tag that appears only inside a full-line comment
        prompt = "# @w1.steps:99\nA cat"
        # when
        result = extract(cmd, prompt)
        # then: the tag is not extracted; steps falls back to its default
        assert result["steps"] == W1_DEFAULTS["steps"]

    def test_inline_comment_is_ignored(self, cmd):
        # given: a tag that appears only after an inline # comment marker
        prompt = "A cat  # @w1.steps:99"
        # when
        result = extract(cmd, prompt)
        # then: the tag is not extracted; steps falls back to its default
        assert result["steps"] == W1_DEFAULTS["steps"]

    def test_tag_before_inline_comment_is_extracted(self, cmd):
        # given: a valid tag followed by an inline comment on the same line
        prompt = "@w1.steps:15  # this is a comment"
        # when
        result = extract(cmd, prompt)
        # then: the tag value is captured; the comment is discarded
        assert result["steps"] == "15"

    def test_escaped_hash_is_not_treated_as_comment(self, cmd):
        # given: a \# escape sequence that must survive stripping, plus a real tag
        prompt = "Some text \\# not a comment\n@w1.steps:7"
        # when
        result = extract(cmd, prompt)
        # then: the tag after the escaped hash is still extracted normally
        assert result["steps"] == "7"


# ---------------------------------------------------------------------------
# Integer tags
# ---------------------------------------------------------------------------

class TestIntegerTags:

    # Parametrized: given a prompt containing a single integer tag,
    # when extracted, then that tag's value matches exactly.
    @pytest.mark.parametrize("tag,value", [
        ("steps",    "1"),
        ("steps",    "9"),
        ("steps",    "100"),
        ("seed",     "0"),
        ("seed",     "56234532624987"),
        ("seed",     "999999999999999"),
        ("width",    "512"),
        ("width",    "1024"),
        ("width",    "2048"),
        ("height",   "512"),
        ("height",   "1600"),
        ("up_steps", "1"),
        ("up_steps", "25"),
        ("up_width", "0"),
        ("up_width", "3840"),
        ("up_height","0"),
        ("up_height","2160"),
    ])
    def test_integer_tag_extracted(self, cmd, tag, value):
        prompt = f"@w1.{tag}:{value}"
        result = extract(cmd, prompt)
        assert result[tag] == value

    def test_last_occurrence_wins_for_steps(self, cmd):
        # given: steps appears three times with different values
        prompt = "@w1.steps:5\n@w1.steps:20\n@w1.steps:3"
        # when / then
        assert extract(cmd, prompt)["steps"] == "3"

    def test_last_occurrence_wins_for_seed(self, cmd):
        # given: seed appears twice
        prompt = "@w1.seed:111\n@w1.seed:222"
        # when / then
        assert extract(cmd, prompt)["seed"] == "222"

    def test_last_occurrence_wins_for_width(self, cmd):
        # given: width appears twice, as happens when --scale appends a new value
        prompt = "@w1.width:512\n@w1.width:1024"
        # when / then
        assert extract(cmd, prompt)["width"] == "1024"


# ---------------------------------------------------------------------------
# Float tags
# ---------------------------------------------------------------------------

class TestFloatTags:

    # Parametrized: given a prompt containing a single float tag,
    # when extracted, then that tag's value matches exactly.
    @pytest.mark.parametrize("tag,value", [
        ("cfg",              "1.0"),
        ("cfg",              "4.5"),
        ("cfg",              "7.5"),
        ("denoise",          "1.0"),
        ("denoise",          "0.5"),
        ("denoise",          "0.75"),
        ("up_cfg",           "1.0"),
        ("up_cfg",           "2.5"),
        ("up_denoise",       "0.4"),
        ("up_denoise",       "0.75"),
        ("lora_strength_01", "1.0"),
        ("lora_strength_01", "0.5"),
        ("lora_strength_02", "1.0"),
        ("lora_strength_03", "0.8"),
        ("lora_strength_04", "1.5"),
    ])
    def test_float_tag_extracted(self, cmd, tag, value):
        prompt = f"@w1.{tag}:{value}"
        result = extract(cmd, prompt)
        assert result[tag] == value

    # def test_float_without_leading_zero_not_matched(self, cmd):
    #     # given: a float value with no leading digit (".5"), which the
    #     # pattern [0-9]*\.[0-9]+ does not match when nothing precedes the dot
    #     prompt = "@w1.cfg:.5"
    #     # when
    #     result = extract(cmd, prompt)
    #     # then: the tag is not extracted; cfg falls back to its default
    #     assert result["cfg"] == W1_DEFAULTS["cfg"]

    def test_integer_value_for_float_tag_not_matched(self, cmd):
        # given: a bare integer where a float (with dot) is required by the pattern
        prompt = "@w1.cfg:1"
        # when
        result = extract(cmd, prompt)
        # then: the tag is not extracted; cfg falls back to its default
        assert result["cfg"] == W1_DEFAULTS["cfg"]


# ---------------------------------------------------------------------------
# String / combo tags
# ---------------------------------------------------------------------------

class TestStringTags:

    # Parametrized: given a prompt containing a single string tag,
    # when extracted, then that tag's value matches exactly.
    @pytest.mark.parametrize("tag,value", [
        ("sampler_name",    "ddim"),
        ("sampler_name",    "euler"),
        ("sampler_name",    "dpmpp_2m_sde"),
        ("scheduler",       "sgm_uniform"),
        ("scheduler",       "karras"),
        ("scheduler",       "simple"),
        ("diffusion_model", "z_image_turbo_bf16.safetensors"),
        ("diffusion_model", "flux2_dev_fp8mixed.safetensors"),
        ("clip_name",       "qwen_3_4b.safetensors"),
        ("clip_name",       "mistral_3_small_flux2_bf16.safetensors"),
        ("clip_type",       "qwen_image"),
        ("clip_type",       "flux2"),
        ("vae_name",        "ae.safetensors"),
        ("vae_name",        "flux2-vae.safetensors"),
        ("lora_name_01",    "my_lora.safetensors"),
        ("lora_name_02",    "style-v2.safetensors"),
        ("lora_name_03",    "detail_enhancer.safetensors"),
        ("lora_name_04",    "face_fix.safetensors"),
        ("up_sampler_name", "dpmpp_2m_sde"),
        ("up_scheduler",    "karras"),
        ("up_model_name",   "4x_NickelbackFS_72000_G.pth"),
    ])
    def test_string_tag_extracted(self, cmd, tag, value):
        prompt = f"@w1.{tag}:{value}"
        result = extract(cmd, prompt)
        assert result[tag] == value


# ---------------------------------------------------------------------------
# Aspect tag
# ---------------------------------------------------------------------------

class TestAspectTag:

    # Parametrized: given a decimal @aspect value,
    # when extracted, then the value is returned as-is.
    @pytest.mark.parametrize("value", [
        "1.0",
        "1.5",
        "0.75",
        "16",
    ])
    def test_aspect_decimal_extracted(self, cmd, value):
        prompt = f"@aspect:{value}"
        assert extract(cmd, prompt)["aspect"] == value

    # Parametrized: given a ratio @aspect value (W:H form),
    # when extracted, then the full ratio string is returned.
    @pytest.mark.parametrize("value", [
        "16:9",
        "4:3",
        "1:1",
        "3:2",
    ])
    def test_aspect_ratio_extracted(self, cmd, value):
        prompt = f"@aspect:{value}"
        assert extract(cmd, prompt)["aspect"] == value

    def test_no_aspect_tag_returns_empty_string(self, cmd):
        # given: a prompt with no @aspect tag
        # when / then
        result = extract(cmd, "A plain prompt")
        assert result["aspect"] == ""

    def test_last_aspect_wins(self, cmd):
        # given: two @aspect tags; the second should override the first
        prompt = "@aspect:1.0\n@aspect:16:9"
        # when / then
        assert extract(cmd, prompt)["aspect"] == "16:9"


# ---------------------------------------------------------------------------
# Multiple tags in a single prompt
# ---------------------------------------------------------------------------

class TestMultipleTags:

    def test_typical_config_file_content(self, cmd):
        # given: a realistic config file with all common w1 tags
        prompt = """\
@w1.diffusion_model:z_image_turbo_bf16.safetensors
@w1.width:1024 @w1.height:1024
@w1.steps:9
@w1.cfg:1.0
@w1.denoise:1.0
@w1.clip_name:qwen_3_4b.safetensors
@w1.clip_type:qwen_image
@w1.vae_name:ae.safetensors
@w1.sampler_name:ddim
@w1.scheduler:sgm_uniform
"""
        # when
        result = extract(cmd, prompt)
        # then: every tag is extracted with the correct value
        assert result["diffusion_model"] == "z_image_turbo_bf16.safetensors"
        assert result["width"]           == "1024"
        assert result["height"]          == "1024"
        assert result["steps"]           == "9"
        assert result["cfg"]             == "1.0"
        assert result["denoise"]         == "1.0"
        assert result["clip_name"]       == "qwen_3_4b.safetensors"
        assert result["clip_type"]       == "qwen_image"
        assert result["vae_name"]        == "ae.safetensors"
        assert result["sampler_name"]    == "ddim"
        assert result["scheduler"]       == "sgm_uniform"

    def test_inline_tags_on_same_line(self, cmd):
        # given: two tags on the same line separated by a space
        prompt = "@w1.width:1600 @w1.height:900"
        # when
        result = extract(cmd, prompt)
        # then
        assert result["width"]  == "1600"
        assert result["height"] == "900"

    def test_tags_mixed_with_prose(self, cmd):
        # given: a realistic user prompt where tags are interspersed with text
        prompt = """\
Painting of a nocturnal landscape, in the style of late romanticism.

@w1.width:1600, @w1.height:1024, @w1.steps:5
@w1.seed:268876620348332
"""
        # when
        result = extract(cmd, prompt)
        # then
        assert result["width"]  == "1600"
        assert result["height"] == "1024"
        assert result["steps"]  == "5"
        assert result["seed"]   == "268876620348332"

    def test_non_w1_tags_do_not_pollute_results(self, cmd):
        # given: a mix of @keyword, @aspect, and a real @w1 tag
        prompt = "@keyword:portrait\n@aspect:1.5\n@w1.steps:7"
        # when
        result = extract(cmd, prompt)
        # then: @w1 tag is extracted, @aspect is extracted, @keyword is absent
        assert result["steps"]   == "7"
        assert result["aspect"]  == "1.5"
        assert "keyword" not in result


# ---------------------------------------------------------------------------
# Defaults fall-through
# ---------------------------------------------------------------------------

class TestDefaults:

    # Parametrized: given a prompt with no tags at all,
    # when extracted, then every key returns its documented default.
    @pytest.mark.parametrize("tag,expected_default", [
        ("seed",             "56234532624987"),
        ("steps",            "9"),
        ("width",            "1024"),
        ("height",           "1600"),
        ("cfg",              "1.0"),
        ("denoise",          "1.0"),
        ("sampler_name",     "ddim"),
        ("scheduler",        "sgm_uniform"),
        ("diffusion_model",  "z_image_turbo_bf16.safetensors"),
        ("clip_name",        "qwen_3_4b.safetensors"),
        ("clip_type",        "qwen_image"),
        ("vae_name",         "ae.safetensors"),
        ("lora_name_01",     "None"),
        ("lora_strength_01", "0.0"),
        ("lora_name_02",     "None"),
        ("lora_strength_02", "0.0"),
        ("lora_name_03",     "None"),
        ("lora_strength_03", "0.0"),
        ("lora_name_04",     "None"),
        ("lora_strength_04", "0.0"),
        ("up_steps",         "25"),
        ("up_width",         "0"),
        ("up_height",        "0"),
        ("up_cfg",           "1.0"),
        ("up_denoise",       "0.4"),
        ("up_sampler_name",  "dpmpp_2m_sde"),
        ("up_scheduler",     "karras"),
        ("up_model_name",    "4x_NickelbackFS_72000_G.pth"),
        ("aspect",           ""),
    ])
    def test_missing_tag_falls_back_to_default(self, cmd, tag, expected_default):
        result = extract(cmd, "A plain prompt with no tags")
        assert result[tag] == expected_default

    def test_unknown_tag_in_prompt_does_not_raise(self, cmd):
        # given: a prompt containing an unrecognised @w1.* tag alongside a valid one
        prompt = "@w1.nonexistent:somevalue\n@w1.steps:3"
        # when
        result = extract(cmd, prompt)
        # then: the valid tag is extracted and the unknown one is silently ignored
        assert result["steps"] == "3"
        assert "nonexistent" not in result