#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: © 2026-present Fabius Dieciscudi
# SPDX-License-Identifier: MIT
"""
Unit tests for SubmitCommand.load_fragment_library.

load_fragment_library builds a key→text map from one or more fragment
directories.  Keys are formed as <dir_name>/<relative_path_without_.txt>.
When the same key appears in multiple directories the last directory wins.

Run with:
    pytest tests/unit/test_load_fragment_library.py -v
"""

import pytest
from pathlib import Path
from comfyui_client.submit.SubmitCommand import SubmitCommand


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def cmd():
    """A bare SubmitCommand instance (no CLI args needed for pure methods)."""
    return SubmitCommand()


def load(cmd, prompt_paths):
    """Thin wrapper so tests read naturally."""
    return cmd.load_fragment_library(prompt_paths)


# ---------------------------------------------------------------------------
# Empty / trivial input
# ---------------------------------------------------------------------------

class TestEmptyInput:

    def test_empty_list_returns_empty_dict(self, cmd):
        # given
        prompt_paths = []
        # when
        result = load(cmd, prompt_paths)
        # then
        assert result == {}

    def test_empty_directory_returns_empty_dict(self, cmd, tmp_path):
        # given: a directory with no .txt files
        empty_dir = tmp_path / "fragments"
        empty_dir.mkdir()
        # when
        result = load(cmd, [str(empty_dir)])
        # then
        assert result == {}

    def test_nonexistent_directory_raises(self, cmd, tmp_path):
        # given: a path that does not exist
        missing = tmp_path / "no_such_dir"
        # when / then
        with pytest.raises(RuntimeError, match="not an existing directory"):
            load(cmd, [str(missing)])


# ---------------------------------------------------------------------------
# Key construction
# ---------------------------------------------------------------------------

class TestKeyConstruction:

    def test_key_includes_directory_name(self, cmd, tmp_path):
        # given: a single .txt file directly inside the fragment root
        root = tmp_path / "frags"
        root.mkdir()
        (root / "greeting.txt").write_text("Hello!")
        # when
        result = load(cmd, [str(root)])
        # then: key starts with the directory name "frags"
        assert "frags/greeting" in result

    def test_key_strips_txt_suffix(self, cmd, tmp_path):
        # given
        root = tmp_path / "fragments"
        root.mkdir()
        (root / "poem.txt").write_text("Roses are red.")
        # when
        result = load(cmd, [str(root)])
        # then: the key has no .txt extension
        assert "fragments/poem" in result
        assert "fragments/poem.txt" not in result

    def test_key_preserves_subdirectory_structure(self, cmd, tmp_path):
        # given: a .txt file nested under a subdirectory
        root = tmp_path / "fragments"
        subdir = root / "lighting"
        subdir.mkdir(parents=True)
        (subdir / "golden-hour.txt").write_text("Warm golden light.")
        # when
        result = load(cmd, [str(root)])
        # then: the key includes the subdirectory path
        assert "fragments/lighting/golden-hour" in result

    def test_key_preserves_deeply_nested_path(self, cmd, tmp_path):
        # given: a .txt file two levels deep
        root = tmp_path / "lib"
        deep = root / "a" / "b"
        deep.mkdir(parents=True)
        (deep / "deep.txt").write_text("Deep content.")
        # when
        result = load(cmd, [str(root)])
        # then
        assert "lib/a/b/deep" in result


# ---------------------------------------------------------------------------
# Content loading
# ---------------------------------------------------------------------------

class TestContentLoading:

    def test_content_matches_file_text(self, cmd, tmp_path):
        # given
        root = tmp_path / "frags"
        root.mkdir()
        content = "A soft warm glow at dusk."
        (root / "scene.txt").write_text(content)
        # when
        result = load(cmd, [str(root)])
        # then
        assert result["frags/scene"] == content

    def test_multiple_files_all_loaded(self, cmd, tmp_path):
        # given: three .txt files in the same directory
        root = tmp_path / "fragments"
        root.mkdir()
        (root / "alpha.txt").write_text("Alpha content.")
        (root / "beta.txt").write_text("Beta content.")
        (root / "gamma.txt").write_text("Gamma content.")
        # when
        result = load(cmd, [str(root)])
        # then: all three are present
        assert "fragments/alpha" in result
        assert "fragments/beta"  in result
        assert "fragments/gamma" in result
        assert len(result) == 3

    def test_non_txt_files_are_ignored(self, cmd, tmp_path):
        # given: a mix of .txt and non-.txt files
        root = tmp_path / "frags"
        root.mkdir()
        (root / "keep.txt").write_text("Keep me.")
        (root / "ignore.md").write_text("Ignore me.")
        (root / "also_ignore.py").write_text("# code")
        # when
        result = load(cmd, [str(root)])
        # then: only the .txt file is loaded
        assert len(result) == 1
        assert "frags/keep" in result

    def test_multiline_content_preserved(self, cmd, tmp_path):
        # given: a file with multiple lines
        root = tmp_path / "frags"
        root.mkdir()
        content = "Line one.\nLine two.\nLine three.\n"
        (root / "multi.txt").write_text(content)
        # when
        result = load(cmd, [str(root)])
        # then: newlines are preserved exactly
        assert result["frags/multi"] == content


# ---------------------------------------------------------------------------
# Multiple directories
# ---------------------------------------------------------------------------

class TestMultipleDirectories:

    def test_fragments_from_both_directories_are_loaded(self, cmd, tmp_path):
        # given: two directories each with one unique fragment
        dir_a = tmp_path / "lib_a"
        dir_b = tmp_path / "lib_b"
        dir_a.mkdir()
        dir_b.mkdir()
        (dir_a / "from_a.txt").write_text("Content A.")
        (dir_b / "from_b.txt").write_text("Content B.")
        # when
        result = load(cmd, [str(dir_a), str(dir_b)])
        # then: both fragments are present under their respective roots
        assert "lib_a/from_a" in result
        assert "lib_b/from_b" in result
        assert len(result) == 2

    def test_last_directory_wins_on_key_collision(self, cmd, tmp_path):
        # given: two directories with identically named fragment files
        dir_first  = tmp_path / "first"
        dir_second = tmp_path / "second"
        dir_first.mkdir()
        dir_second.mkdir()
        (dir_first  / "shared.txt").write_text("First version.")
        (dir_second / "shared.txt").write_text("Second version.")
        # when: dir_second is passed last
        result = load(cmd, [str(dir_first), str(dir_second)])
        # then: the value from dir_second wins
        assert result["second/shared"] == "Second version."
        # and the first directory's key is replaced
        assert result.get("first/shared") == "First version."

    def test_collision_first_wins_when_reversed(self, cmd, tmp_path):
        # given: same setup but order reversed
        dir_first  = tmp_path / "first"
        dir_second = tmp_path / "second"
        dir_first.mkdir()
        dir_second.mkdir()
        (dir_first  / "shared.txt").write_text("First version.")
        (dir_second / "shared.txt").write_text("Second version.")
        # when: dir_first is passed last
        result = load(cmd, [str(dir_second), str(dir_first)])
        # then: dir_first's value is loaded last, so it is present
        assert result["first/shared"] == "First version."

    def test_three_directories_merged(self, cmd, tmp_path):
        # given: three directories, each with a unique fragment
        dirs = []
        for name in ("alpha", "beta", "gamma"):
            d = tmp_path / name
            d.mkdir()
            (d / f"{name}.txt").write_text(f"{name} content.")
            dirs.append(str(d))
        # when
        result = load(cmd, dirs)
        # then: all three fragments are present
        assert "alpha/alpha" in result
        assert "beta/beta"   in result
        assert "gamma/gamma" in result


# ---------------------------------------------------------------------------
# Recursive discovery
# ---------------------------------------------------------------------------

class TestRecursiveDiscovery:

    def test_nested_files_discovered_recursively(self, cmd, tmp_path):
        # given: .txt files at multiple depth levels
        root = tmp_path / "frags"
        (root / "sub1" / "sub2").mkdir(parents=True)
        (root / "top.txt").write_text("Top.")
        (root / "sub1" / "mid.txt").write_text("Mid.")
        (root / "sub1" / "sub2" / "deep.txt").write_text("Deep.")
        # when
        result = load(cmd, [str(root)])
        # then: all three files are present
        assert "frags/top"          in result
        assert "frags/sub1/mid"     in result
        assert "frags/sub1/sub2/deep" in result
        assert len(result) == 3