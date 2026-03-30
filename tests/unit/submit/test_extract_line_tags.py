#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: © 2026-present Fabius Dieciscudi
# SPDX-License-Identifier: MIT
"""
Unit tests for SubmitCommand.extract_line_tags.

extract_line_tags expects comment-stripped text as input — comment interaction
is therefore out of scope here (that belongs to test_extract_tags.py, which
exercises strip_comments in combination with extract_tags).

The method returns a 3-tuple: (keywords: list[str], title: str, description: str).
- @keyword  tags accumulate into the list (all occurrences kept, in order).
- @title    is last-wins (only one title is meaningful).
- @description is last-wins.
- Values are stripped of leading/trailing whitespace.
- \# escape sequences are unescaped to # in the returned value.

Run with:
    pytest tests/unit/test_extract_line_tags.py -v
"""

import pytest
from comfyui_client.submit.SubmitCommand import SubmitCommand

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def cmd():
    """A bare SubmitCommand instance (no CLI args needed for pure methods)."""
    return SubmitCommand()


def line_tags(cmd, text):
    """Thin wrapper so tests read naturally."""
    return cmd.extract_line_tags(text)


# ---------------------------------------------------------------------------
# Return type and empty input
# ---------------------------------------------------------------------------

class TestReturnShape:

    def test_empty_string_returns_correct_types(self, cmd):
        # given
        text = ""
        # when
        keywords, title, description = line_tags(cmd, text)
        # then: always a list and two strings, never None
        assert isinstance(keywords, list)
        assert isinstance(title, str)
        assert isinstance(description, str)

    def test_empty_string_returns_empty_values(self, cmd):
        # given
        text = ""
        # when
        keywords, title, description = line_tags(cmd, text)
        # then
        assert keywords    == []
        assert title       == ""
        assert description == ""

    def test_plain_prose_returns_empty_values(self, cmd):
        # given: text with no line tags at all
        text = "A cat sitting on a sofa, smoking a pipe"
        # when
        keywords, title, description = line_tags(cmd, text)
        # then
        assert keywords    == []
        assert title       == ""
        assert description == ""


# ---------------------------------------------------------------------------
# @keyword tag
# ---------------------------------------------------------------------------

class TestKeywordTag:

    def test_single_keyword_extracted(self, cmd):
        # given
        text = "@keyword:portrait"
        # when
        keywords, _, _ = line_tags(cmd, text)
        # then
        assert keywords == ["portrait"]

    def test_multiple_keywords_all_collected(self, cmd):
        # given: multiple @keyword lines — all must be kept in order
        text = "@keyword:portrait\n@keyword:oil painting\n@keyword:studio lighting"
        # when
        keywords, _, _ = line_tags(cmd, text)
        # then
        assert keywords == ["portrait", "oil painting", "studio lighting"]

    def test_keyword_order_preserved(self, cmd):
        # given: keywords interspersed with other content
        text = "@keyword:first\nSome prose.\n@keyword:second\n@keyword:third"
        # when
        keywords, _, _ = line_tags(cmd, text)
        # then: order must match document order, not alphabetical
        assert keywords == ["first", "second", "third"]

    def test_keyword_with_hierarchical_pipe_value(self, cmd):
        # given: a hierarchical keyword using | as separator (used for XMP hierarchies)
        text = "@keyword:AI|ai:generator|generator:ComfyUI#W1"
        # when
        keywords, _, _ = line_tags(cmd, text)
        # then: the full value including pipes is preserved as-is
        assert keywords == ["AI|ai:generator|generator:ComfyUI#W1"]

    def test_keyword_value_is_stripped(self, cmd):
        # given: extra whitespace around the value
        text = "@keyword:   portrait   "
        # when
        keywords, _, _ = line_tags(cmd, text)
        # then
        assert keywords == ["portrait"]

    def test_keyword_does_not_span_lines(self, cmd):
        # given: a keyword value followed immediately by a newline and more text
        text = "@keyword:portrait\ncontinued on next line"
        # when
        keywords, _, _ = line_tags(cmd, text)
        # then: only the first line is the keyword value
        assert keywords == ["portrait"]

    def test_keyword_with_escaped_hash(self, cmd):
        # given: a \# sequence that must be unescaped to # in the output
        text = r"@keyword:ComfyUI\#W1"
        # when
        keywords, _, _ = line_tags(cmd, text)
        # then
        assert keywords == ["ComfyUI#W1"]

    def test_keyword_with_colon_in_value(self, cmd):
        # given: colons inside the value (after the tag-name colon)
        text = "@keyword:ai:parameters:w1.steps"
        # when
        keywords, _, _ = line_tags(cmd, text)
        # then: everything after the first colon is the value
        assert keywords == ["ai:parameters:w1.steps"]


# ---------------------------------------------------------------------------
# @title tag
# ---------------------------------------------------------------------------

class TestTitleTag:

    def test_single_title_extracted(self, cmd):
        # given
        text = "@title:Moonlit Forest"
        # when
        _, title, _ = line_tags(cmd, text)
        # then
        assert title == "Moonlit Forest"

    def test_title_value_is_stripped(self, cmd):
        # given: extra whitespace around the value
        text = "@title:   Moonlit Forest   "
        # when
        _, title, _ = line_tags(cmd, text)
        # then
        assert title == "Moonlit Forest"

    def test_last_title_wins(self, cmd):
        # given: two @title tags; only the last one should be kept
        text = "@title:First Title\n@title:Second Title"
        # when
        _, title, _ = line_tags(cmd, text)
        # then
        assert title == "Second Title"

    def test_title_with_escaped_hash(self, cmd):
        # given
        text = r"@title:Portrait \#3"
        # when
        _, title, _ = line_tags(cmd, text)
        # then
        assert title == "Portrait #3"

    def test_title_with_colon_in_value(self, cmd):
        # given: colons are valid inside the title value
        text = "@title:Ritratto di Claire: studio"
        # when
        _, title, _ = line_tags(cmd, text)
        # then
        assert title == "Ritratto di Claire: studio"

    def test_no_title_tag_returns_empty_string(self, cmd):
        # given: text with keywords but no title
        text = "@keyword:portrait"
        # when
        _, title, _ = line_tags(cmd, text)
        # then
        assert title == ""


# ---------------------------------------------------------------------------
# @description tag
# ---------------------------------------------------------------------------

class TestDescriptionTag:

    def test_single_description_extracted(self, cmd):
        # given
        text = "@description:A nocturnal landscape in late romanticism style."
        # when
        _, _, description = line_tags(cmd, text)
        # then
        assert description == "A nocturnal landscape in late romanticism style."

    def test_description_value_is_stripped(self, cmd):
        # given
        text = "@description:   Some description.   "
        # when
        _, _, description = line_tags(cmd, text)
        # then
        assert description == "Some description."

    def test_last_description_wins(self, cmd):
        # given: two @description tags; only the last one should be kept
        text = "@description:First.\n@description:Second."
        # when
        _, _, description = line_tags(cmd, text)
        # then
        assert description == "Second."

    def test_description_with_escaped_hash(self, cmd):
        # given
        text = r"@description:Version \#2 of the prompt."
        # when
        _, _, description = line_tags(cmd, text)
        # then
        assert description == "Version #2 of the prompt."

    def test_description_does_not_span_lines(self, cmd):
        # given: description value is on one line; next line is separate content
        text = "@description:First line only.\nThis is not part of the description."
        # when
        _, _, description = line_tags(cmd, text)
        # then
        assert description == "First line only."

    def test_no_description_tag_returns_empty_string(self, cmd):
        # given: text with a title but no description
        text = "@title:My Title"
        # when
        _, _, description = line_tags(cmd, text)
        # then
        assert description == ""


# ---------------------------------------------------------------------------
# All three tags together
# ---------------------------------------------------------------------------

class TestMixedTags:

    def test_all_three_tags_in_one_prompt(self, cmd):
        # given: a realistic prompt block with all three tag types
        text = (
            "@title:Moonlit Forest\n"
            "@description:A nocturnal scene in late romanticism style.\n"
            "@keyword:landscape\n"
            "@keyword:nocturnal\n"
            "@keyword:romanticism\n"
        )
        # when
        keywords, title, description = line_tags(cmd, text)
        # then
        assert title       == "Moonlit Forest"
        assert description == "A nocturnal scene in late romanticism style."
        assert keywords    == ["landscape", "nocturnal", "romanticism"]

    def test_line_tags_coexist_with_w1_tags(self, cmd):
        # given: a realistic mixed prompt (already comment-stripped)
        text = (
            "@w1.steps:9\n"
            "@title:Portrait Study\n"
            "@keyword:portrait\n"
            "@w1.width:1024\n"
            "@keyword:AI|ai:generator|generator:ComfyUI\\#W1\n"
        )
        # when
        keywords, title, description = line_tags(cmd, text)
        # then: only line tags are extracted; @w1.* tags are ignored by this method
        assert title    == "Portrait Study"
        assert keywords == ["portrait", "AI|ai:generator|generator:ComfyUI#W1"]
        assert description == ""

    def test_prose_between_tags_is_ignored(self, cmd):
        # given: tags interspersed with plain text lines
        text = (
            "A painting of a forest at night.\n"
            "@keyword:forest\n"
            "With a full moon and heavy clouds.\n"
            "@keyword:nocturnal\n"
            "@title:Forest at Night\n"
        )
        # when
        keywords, title, description = line_tags(cmd, text)
        # then
        assert keywords == ["forest", "nocturnal"]
        assert title    == "Forest at Night"

    def test_w1_tags_are_not_mistaken_for_line_tags(self, cmd):
        # given: only @w1.* tags, no @keyword / @title / @description
        text = "@w1.steps:9\n@w1.width:1024\n@w1.cfg:1.0"
        # when
        keywords, title, description = line_tags(cmd, text)
        # then: all three outputs are empty
        assert keywords    == []
        assert title       == ""
        assert description == ""