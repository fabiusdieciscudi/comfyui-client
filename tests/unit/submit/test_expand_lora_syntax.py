#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: © 2026-present Fabius Dieciscudi
# SPDX-License-Identifier: MIT
"""
Unit tests for SubmitCommand.expand_lora_syntax and an integration suite
that chains expand_fragments → expand_lora_syntax, matching the order used
by the real submit flow.

expand_lora_syntax rules:
- Matches <lora:name:strength> where name is [\\w.-]+ and strength is a
  numeric value (integer or float).
- Replaces each match with a pair of @w1 tags:
      @w1.lora_name_NN:name.safetensors
      @w1.lora_strength_NN:strength
  where NN is a zero-padded two-digit counter starting at 01.
- Text outside the <lora:…> tokens is preserved verbatim.
- Returns the input unchanged when no tokens are present.
- Raises RuntimeError when a matched token has an empty name.

Run with:
    pytest tests/unit/test_expand_lora_syntax.py -v
"""

import pytest
import re
from comfyui_client.submit.SubmitCommand import SubmitCommand


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def cmd():
    """A bare SubmitCommand instance (no CLI args needed for pure methods)."""
    return SubmitCommand()


def lora(cmd, text):
    """Thin wrapper for expand_lora_syntax."""
    return cmd.expand_lora_syntax(text, "w1")


def expand(cmd, text, library):
    """Thin wrapper for expand_fragments."""
    return cmd.expand_fragments(text, library)


# ===========================================================================
# expand_lora_syntax
# ===========================================================================

# ---------------------------------------------------------------------------
# No-op cases
# ---------------------------------------------------------------------------

class TestLoraNoOp:

    def test_empty_string_returns_empty_string(self, cmd):
        # given / when / then
        assert lora(cmd, "") == ""

    def test_plain_prose_returned_unchanged(self, cmd):
        # given
        text = "A cat sitting on a sofa, smoking a pipe."
        # when / then
        assert lora(cmd, text) == text

    def test_w1_tags_returned_unchanged(self, cmd):
        # given: already-expanded tags should not be touched
        text = "@w1.steps:9\n@w1.width:1024"
        # when / then
        assert lora(cmd, text) == text

    def test_angle_brackets_without_lora_prefix_returned_unchanged(self, cmd):
        # given: angle-bracket content that does not match <lora:…> pattern
        text = "Some text <not_a_lora> more text"
        # when / then
        assert lora(cmd, text) == text

    def test_incomplete_lora_token_returned_unchanged(self, cmd):
        # given: missing closing bracket
        text = "<lora:my_model:1.0"
        # when / then
        assert lora(cmd, text) == text


# ---------------------------------------------------------------------------
# Single token replacement
# ---------------------------------------------------------------------------

class TestLoraSingleToken:

    def test_single_token_produces_name_tag(self, cmd):
        # given
        text = "<lora:my_model:1.0>"
        # when
        result = lora(cmd, text)
        # then: name tag is present with .safetensors appended
        assert "@w1.lora_name_01:my_model.safetensors" in result

    def test_single_token_produces_strength_tag(self, cmd):
        # given
        text = "<lora:my_model:1.0>"
        # when
        result = lora(cmd, text)
        # then: strength tag is present
        assert "@w1.lora_strength_01:1.0" in result

    def test_token_is_removed_from_output(self, cmd):
        # given
        text = "<lora:my_model:1.0>"
        # when
        result = lora(cmd, text)
        # then: the original token is gone
        assert "<lora:" not in result

    def test_integer_strength_accepted(self, cmd):
        # given: strength without a decimal point
        text = "<lora:style_lora:2>"
        # when
        result = lora(cmd, text)
        # then
        assert "@w1.lora_name_01:style_lora.safetensors" in result
        assert "@w1.lora_strength_01:2" in result

    def test_zero_strength_accepted(self, cmd):
        # given
        text = "<lora:disabled_lora:0>"
        # when
        result = lora(cmd, text)
        # then
        assert "@w1.lora_strength_01:0" in result

    def test_fractional_strength_accepted(self, cmd):
        # given
        text = "<lora:subtle:0.35>"
        # when
        result = lora(cmd, text)
        # then
        assert "@w1.lora_strength_01:0.35" in result

    def test_name_with_hyphens_and_dots(self, cmd):
        # given: name contains characters matched by [\w.-]+
        text = "<lora:face-fix.v2:1.0>"
        # when
        result = lora(cmd, text)
        # then: name is preserved exactly (plus .safetensors)
        assert "@w1.lora_name_01:face-fix.v2.safetensors" in result

    def test_prose_before_token_is_preserved(self, cmd):
        # given
        text = "A portrait of a woman. <lora:style:0.8>"
        # when
        result = lora(cmd, text)
        # then: preceding prose survives
        assert "A portrait of a woman." in result

    def test_prose_after_token_is_preserved(self, cmd):
        # given
        text = "<lora:style:0.8> with studio lighting."
        # when
        result = lora(cmd, text)
        # then: following prose survives
        assert "with studio lighting." in result


# ---------------------------------------------------------------------------
# Multiple token replacement and numbering
# ---------------------------------------------------------------------------

class TestLoraMultipleTokens:

    def test_two_tokens_numbered_01_and_02(self, cmd):
        # given
        text = "<lora:lora_a:1.0> <lora:lora_b:0.5>"
        # when
        result = lora(cmd, text)
        # then: slots are assigned in document order
        assert "@w1.lora_name_01:lora_a.safetensors" in result
        assert "@w1.lora_name_02:lora_b.safetensors" in result

    def test_two_tokens_strengths_assigned_to_correct_slots(self, cmd):
        # given
        text = "<lora:lora_a:1.0> <lora:lora_b:0.5>"
        # when
        result = lora(cmd, text)
        # then: strengths follow the same numbering order
        assert "@w1.lora_strength_01:1.0" in result
        assert "@w1.lora_strength_02:0.5" in result

    def test_four_tokens_all_numbered(self, cmd):
        # given: maximum four LoRAs (per the TODO note in the codebase)
        tokens = " ".join(f"<lora:lora_{i}:1.0>" for i in range(1, 5))
        # when
        result = lora(cmd, tokens)
        # then: slots 01–04 are all present
        for n in range(1, 5):
            assert f"@w1.lora_name_{n:02d}:lora_{n}.safetensors" in result
            assert f"@w1.lora_strength_{n:02d}:1.0" in result

    def test_numbering_is_document_order_not_alphabetical(self, cmd):
        # given: tokens in reverse-alphabetical name order
        text = "<lora:zzz:1.0> <lora:aaa:0.5>"
        # when
        result = lora(cmd, text)
        # then: 'zzz' gets slot 01 because it appears first
        assert "@w1.lora_name_01:zzz.safetensors" in result
        assert "@w1.lora_name_02:aaa.safetensors" in result

    def test_tokens_on_separate_lines(self, cmd):
        # given
        text = "<lora:lora_a:1.0>\n<lora:lora_b:0.7>"
        # when
        result = lora(cmd, text)
        # then: both are expanded regardless of being on different lines
        assert "@w1.lora_name_01:lora_a.safetensors" in result
        assert "@w1.lora_name_02:lora_b.safetensors" in result

    def test_prose_between_tokens_is_preserved(self, cmd):
        # given
        text = "Before. <lora:a:1.0> Middle text. <lora:b:0.5> After."
        # when
        result = lora(cmd, text)
        # then: prose between the tokens survives
        assert "Before."      in result
        assert "Middle text." in result
        assert "After."       in result

    def test_mixed_with_w1_tags(self, cmd):
        # given: a realistic prompt fragment mixing @tags and <lora:…>
        text = "@w1.steps:9\n<lora:portrait_v2:0.8>\nA woman in a studio."
        # when
        result = lora(cmd, text)
        # then: the @w1 tag and prose are unaffected; the LoRA is expanded
        assert "@w1.steps:9"                           in result
        assert "A woman in a studio."                  in result
        assert "@w1.lora_name_01:portrait_v2.safetensors" in result


# ---------------------------------------------------------------------------
# Safetensors suffix
# ---------------------------------------------------------------------------

class TestLoraSafetensorsSuffix:

    def test_safetensors_suffix_appended_to_name(self, cmd):
        # given
        text = "<lora:my_lora:1.0>"
        # when
        result = lora(cmd, text)
        # then
        assert "@w1.lora_name_01:my_lora.safetensors" in result

    def test_name_already_ending_in_safetensors_gets_second_suffix(self, cmd):
        # given: the regex matches [\w.-]+ so .safetensors in the name is valid;
        # the code unconditionally appends .safetensors — document actual behaviour.
        text = "<lora:my_lora.safetensors:1.0>"
        # when
        result = lora(cmd, text)
        # then: .safetensors is appended a second time (current implementation)
        assert "@w1.lora_name_01:my_lora.safetensors.safetensors" in result


# ===========================================================================
# Integration: expand_fragments → expand_lora_syntax
# ===========================================================================

class TestExpandIntegration:
    """
    Chains expand_fragments then expand_lora_syntax, matching the order used
    in SubmitCommand.submit():

        full_prompt = expand_fragments(full_prompt, fragment_library)
        full_prompt = expand_lora_syntax(full_prompt)
    """

    def test_lora_token_inside_fragment_is_expanded(self, cmd):
        # given: a fragment whose body contains a <lora:…> token
        library = {"style/lora_style": "painterly style\n<lora:painterly_v1:0.8>"}
        text = ":style/lora_style"
        # when
        after_fragments = expand(cmd, text, library)
        result = lora(cmd, after_fragments)
        # then: both the prose and the lora tag are present
        assert "painterly style"                           in result
        assert "@w1.lora_name_01:painterly_v1.safetensors" in result
        assert "@w1.lora_strength_01:0.8"                  in result

    def test_lora_token_in_prompt_alongside_fragment_inclusion(self, cmd):
        # given: the top-level prompt has both a fragment inclusion and a direct token
        library = {"lighting/golden": "warm golden light"}
        text = ":lighting/golden\n<lora:face_fix:0.5>"
        # when
        after_fragments = expand(cmd, text, library)
        result = lora(cmd, after_fragments)
        # then: the fragment text and the lora expansion are both present
        assert "warm golden light"                       in result
        assert "@w1.lora_name_01:face_fix.safetensors"  in result
        assert "@w1.lora_strength_01:0.5"               in result

    def test_multiple_fragments_each_with_a_lora_token(self, cmd):
        # given: two fragments each contributing one <lora:…>
        library = {
            "char/hero":  "heroic character\n<lora:hero_v1:1.0>",
            "style/ink":  "ink wash style\n<lora:ink_style:0.6>",
        }
        text = ":char/hero\n:style/ink"
        # when
        after_fragments = expand(cmd, text, library)
        result = lora(cmd, after_fragments)
        # then: both LoRAs are assigned sequential slots
        assert "@w1.lora_name_01:hero_v1.safetensors"   in result
        assert "@w1.lora_name_02:ink_style.safetensors" in result

    def test_fragment_inclusions_and_lora_tokens_number_independently(self, cmd):
        # given: fragments produce content; lora tokens produce numbered tags
        library = {"mood/dark": "dark and moody atmosphere"}
        text = ":mood/dark\n<lora:shadow_lora:0.9>\nA forest at night."
        # when
        after_fragments = expand(cmd, text, library)
        result = lora(cmd, after_fragments)
        # then: all parts present and lora numbered from 01
        assert "dark and moody atmosphere"               in result
        assert "@w1.lora_name_01:shadow_lora.safetensors" in result
        assert "A forest at night."                      in result

    def test_no_lora_tokens_in_expanded_prompt_leaves_text_unchanged(self, cmd):
        # given: fragments contain no LoRA tokens
        library = {"desc/sky": "a clear blue sky"}
        text = ":desc/sky\n@w1.steps:9"
        # when
        after_fragments = expand(cmd, text, library)
        result = lora(cmd, after_fragments)
        # then: expand_lora_syntax is a no-op; all content survives
        assert "a clear blue sky" in result
        assert "@w1.steps:9"      in result
        assert "<lora:"           not in result
        assert "lora_name"        not in result

    def test_recursive_fragment_with_lora_token_at_leaf(self, cmd):
        # given: outer → inner → lora token in the leaf fragment
        library = {
            "leaf":  "leaf text\n<lora:detail_lora:0.7>",
            "inner": "inner text\n:leaf",
            "outer": "outer text\n:inner",
        }
        text = ":outer"
        # when
        after_fragments = expand(cmd, text, library)
        result = lora(cmd, after_fragments)
        # then: the full chain is resolved and the LoRA is expanded
        assert "outer text"                               in result
        assert "inner text"                               in result
        assert "leaf text"                                in result
        assert "@w1.lora_name_01:detail_lora.safetensors" in result