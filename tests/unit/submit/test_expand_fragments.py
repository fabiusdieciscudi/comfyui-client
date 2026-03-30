#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: © 2026-present Fabius Dieciscudi
# SPDX-License-Identifier: MIT
"""
Unit tests for SubmitCommand.expand_fragments.

expand_fragments replaces ':key' lines in prompt text with the contents of
the matching fragment from the library dict, recursively.  Key rules:

- A line whose first non-whitespace character is ':' is an inclusion.
- The key is everything after the leading ':', stripped.
- Expansion is recursive (fragments may include other fragments).
- Depth is capped at _MAX_INCLUDE_DEPTH (16); exceeding it raises RuntimeError.
- An unknown key raises RuntimeError immediately.
- Non-inclusion lines pass through unchanged.

Run with:
    pytest tests/unit/test_expand_fragments.py -v
"""

import pytest
from comfyui_client.submit.SubmitCommand import SubmitCommand, _MAX_INCLUDE_DEPTH


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def cmd():
    """A bare SubmitCommand instance (no CLI args needed for pure methods)."""
    return SubmitCommand()


def expand(cmd, text, library):
    """Thin wrapper so tests read naturally."""
    return cmd.expand_fragments(text, library)


# ---------------------------------------------------------------------------
# Empty / trivial input
# ---------------------------------------------------------------------------

class TestEmptyInput:

    def test_empty_text_returns_empty_string(self, cmd):
        # given
        text = ""
        library = {}
        # when
        result = expand(cmd, text, library)
        # then
        assert result == ""

    def test_plain_prose_is_returned_unchanged(self, cmd):
        # given: no inclusion lines at all
        text = "A nocturnal landscape in late romanticism style."
        library = {}
        # when
        result = expand(cmd, text, library)
        # then
        assert result == text

    def test_empty_library_with_no_inclusions_is_fine(self, cmd):
        # given: multi-line prose, no ':' lines, empty library
        text = "Line one.\nLine two.\nLine three."
        library = {}
        # when
        result = expand(cmd, text, library)
        # then: text comes back intact
        assert result == text


# ---------------------------------------------------------------------------
# Basic inclusion
# ---------------------------------------------------------------------------

class TestBasicInclusion:

    def test_single_inclusion_is_replaced(self, cmd):
        # given
        library = {"style/painterly": "in the style of oil painting"}
        text = ":style/painterly"
        # when
        result = expand(cmd, text, library)
        # then: the inclusion line is replaced by the fragment body
        assert "in the style of oil painting" in result
        assert ":style/painterly" not in result

    def test_inclusion_line_surrounded_by_prose(self, cmd):
        # given
        library = {"lighting/golden": "warm golden light at dusk"}
        text = "A portrait of a woman.\n:lighting/golden\nStudio background."
        # when
        result = expand(cmd, text, library)
        # then: surrounding prose is preserved; inclusion is replaced
        assert "A portrait of a woman." in result
        assert "warm golden light at dusk" in result
        assert "Studio background." in result
        assert ":lighting/golden" not in result

    def test_multiple_inclusions_all_replaced(self, cmd):
        # given
        library = {
            "style/painterly": "oil painting style",
            "lighting/soft":   "soft diffused light",
        }
        text = ":style/painterly\n:lighting/soft"
        # when
        result = expand(cmd, text, library)
        # then: both are replaced
        assert "oil painting style"  in result
        assert "soft diffused light" in result

    def test_inclusion_line_with_leading_whitespace(self, cmd):
        # given: the ':' is the first non-whitespace character on the line
        library = {"frag/a": "fragment content"}
        text = "   :frag/a"
        # when
        result = expand(cmd, text, library)
        # then: leading whitespace does not prevent expansion
        assert "fragment content" in result
        assert ":frag/a" not in result

    def test_inclusion_value_is_stripped(self, cmd):
        # given: the key has trailing whitespace after it
        library = {"frag/b": "body text"}
        text = ":frag/b   "
        # when
        result = expand(cmd, text, library)
        # then: trailing whitespace on the key is ignored
        assert "body text" in result

    def test_colon_not_at_start_of_line_is_not_an_inclusion(self, cmd):
        # given: a colon in the middle of a line (e.g. a tag value)
        library = {"w1.steps": "should not appear"}
        text = "@w1.steps:9"
        # when
        result = expand(cmd, text, library)
        # then: the line is treated as prose, not an inclusion
        assert result == text
        assert "should not appear" not in result

    def test_prose_line_starting_with_colon_in_value_position_not_expanded(self, cmd):
        # given: a URL-like string that starts mid-line with ://
        library = {}
        text = "See https://example.com for more."
        # when
        result = expand(cmd, text, library)
        # then: unchanged
        assert result == text


# ---------------------------------------------------------------------------
# Recursive expansion
# ---------------------------------------------------------------------------

class TestRecursiveExpansion:

    def test_fragment_including_another_fragment(self, cmd):
        # given: 'scene' includes 'lighting'
        library = {
            "lighting/golden": "warm golden light",
            "scene/outdoor":   "An outdoor scene.\n:lighting/golden",
        }
        text = ":scene/outdoor"
        # when
        result = expand(cmd, text, library)
        # then: both levels of content appear in the output
        assert "An outdoor scene."  in result
        assert "warm golden light"  in result

    def test_three_level_deep_chain_is_expanded(self, cmd):
        # given: a → b → c
        library = {
            "a": "level-a\n:b",
            "b": "level-b\n:c",
            "c": "level-c",
        }
        text = ":a"
        # when
        result = expand(cmd, text, library)
        # then: all three levels appear
        assert "level-a" in result
        assert "level-b" in result
        assert "level-c" in result

    def test_same_fragment_included_twice_from_different_parents(self, cmd):
        # given: two parents both include the same leaf
        library = {
            "leaf":    "shared leaf content",
            "parent1": "Parent 1.\n:leaf",
            "parent2": "Parent 2.\n:leaf",
        }
        text = ":parent1\n:parent2"
        # when
        result = expand(cmd, text, library)
        # then: the leaf content appears twice (once per inclusion)
        assert result.count("shared leaf content") == 2

    def test_prose_in_fragment_body_is_preserved(self, cmd):
        # given: the fragment body has multiple lines of prose
        library = {"detail/hair": "flowing auburn hair\nwith subtle highlights"}
        text = "A portrait.\n:detail/hair\nEnd."
        # when
        result = expand(cmd, text, library)
        # then: both lines of the fragment body are present
        assert "flowing auburn hair"      in result
        assert "with subtle highlights"   in result


# ---------------------------------------------------------------------------
# Unknown key handling
# ---------------------------------------------------------------------------

class TestUnknownKey:

    def test_unknown_key_raises_runtime_error(self, cmd):
        # given: an inclusion that references a key not in the library
        library = {}
        text = ":nonexistent/fragment"
        # when / then
        with pytest.raises(RuntimeError, match="nonexistent/fragment"):
            expand(cmd, text, library)

    def test_unknown_key_in_nested_fragment_raises(self, cmd):
        # given: the top-level fragment exists but references a missing key
        library = {"parent": "Some text.\n:missing/child"}
        text = ":parent"
        # when / then
        with pytest.raises(RuntimeError, match="missing/child"):
            expand(cmd, text, library)

    def test_valid_key_after_unknown_key_does_not_suppress_error(self, cmd):
        # given: first inclusion is bad, second would be fine
        library = {"good/frag": "good content"}
        text = ":bad/frag\n:good/frag"
        # when / then: the bad key is hit first and raises immediately
        with pytest.raises(RuntimeError, match="bad/frag"):
            expand(cmd, text, library)


# ---------------------------------------------------------------------------
# Depth limit / circular reference detection
# ---------------------------------------------------------------------------

class TestDepthLimit:

    def test_chain_at_max_depth_succeeds(self, cmd):
        # given: a linear chain exactly _MAX_INCLUDE_DEPTH levels deep
        # (depth starts at 0, so a chain of length MAX_INCLUDE_DEPTH is allowed)
        library = {}
        for i in range(_MAX_INCLUDE_DEPTH):
            key      = f"frag/{i}"
            next_key = f"frag/{i + 1}"
            library[key] = f"level {i}\n:{next_key}"
        # leaf node (no further inclusion)
        library[f"frag/{_MAX_INCLUDE_DEPTH}"] = f"level {_MAX_INCLUDE_DEPTH}"
        text = ":frag/0"
        # when: should not raise
        result = expand(cmd, text, library)
        # then: all levels are present
        for i in range(_MAX_INCLUDE_DEPTH + 1):
            assert f"level {i}" in result

    def test_chain_exceeding_max_depth_raises(self, cmd):
        # given: a chain one step longer than _MAX_INCLUDE_DEPTH
        library = {}
        depth = _MAX_INCLUDE_DEPTH + 1
        for i in range(depth):
            library[f"frag/{i}"] = f"level {i}\n:frag/{i + 1}"
        library[f"frag/{depth}"] = f"level {depth}"
        text = ":frag/0"
        # when / then
        with pytest.raises(RuntimeError, match="depth"):
            expand(cmd, text, library)

    def test_circular_reference_raises(self, cmd):
        # given: a → b → a (cycle)
        library = {
            "cycle/a": "a content\n:cycle/b",
            "cycle/b": "b content\n:cycle/a",
        }
        text = ":cycle/a"
        # when / then: circular reference hits the depth limit
        with pytest.raises(RuntimeError):
            expand(cmd, text, library)

    def test_self_referencing_fragment_raises(self, cmd):
        # given: a fragment that includes itself
        library = {"self/ref": "content\n:self/ref"}
        text = ":self/ref"
        # when / then
        with pytest.raises(RuntimeError):
            expand(cmd, text, library)


# ---------------------------------------------------------------------------
# Output structure
# ---------------------------------------------------------------------------

class TestOutputStructure:

    def test_non_inclusion_lines_are_never_modified(self, cmd):
        # given: a mix of tags, prose, and one inclusion
        library = {"frag/style": "painterly"}
        text = "@w1.steps:9\nA cat on a sofa.\n:frag/style\n@w1.seed:42"
        # when
        result = expand(cmd, text, library)
        # then: non-inclusion lines pass through verbatim
        assert "@w1.steps:9"       in result
        assert "A cat on a sofa."  in result
        assert "@w1.seed:42"       in result

    def test_fragment_trailing_newline_is_trimmed(self, cmd):
        # given: the fragment body ends with a newline (common for file reads)
        library = {"frag/x": "content line\n"}
        text = ":frag/x\nnext line"
        # when
        result = expand(cmd, text, library)
        # then: 'next line' is on its own line, not run together with content
        assert "next line" in result
        # and there is no double-blank between the fragment and the next line
        assert "\n\n\n" not in result

    def test_inclusion_replaced_not_prepended(self, cmd):
        # given
        library = {"frag/y": "replacement"}
        text = ":frag/y"
        # when
        result = expand(cmd, text, library)
        # then: the inclusion marker itself does not appear in the output
        assert ":frag/y" not in result
        assert "replacement" in result