#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: © 2026-present Fabius Dieciscudi
# SPDX-License-Identifier: MIT
"""
FixAIKeywords — read AI generation tags from ComfyUI image metadata
and write them as XMP Subject, IPTC Keywords, and XMP-lr:HierarchicalSubject.

Supports both the new Prompt-based format and the old Workflow format
(retro-compatibility).

Usage:
    FixAIKeywords.py <file.png|jpg>
    FixAIKeywords.py <directory>
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}


# ---------------------------------------------------------------------------
# exiftool helpers
# ---------------------------------------------------------------------------

def exiftool_read(path: Path) -> dict[str, str]:
    """Return a flat dict of all EXIF fields for *path* (string values)."""
    result = subprocess.run(
        ["exiftool", "-j", str(path)],
        capture_output=True, text=True, check=True,
    )
    data = json.loads(result.stdout)
    return data[0] if data else {}


def exiftool_write(path: Path, keywords: list[str], hierarchicals: list[str]) -> None:
    """Write all keywords and hierarchical subjects in a single exiftool call."""
    args = ["exiftool", "-overwrite_original", "-m"]

    for kw in keywords:
        args += [f"-XMP:Subject-={kw}", f"-XMP:Subject+={kw}"]
        args += [f"-IPTC:Keywords-={kw}", f"-IPTC:Keywords+={kw}"]

    for h in hierarchicals:
        args += [f"-XMP-lr:HierarchicalSubject-={h}", f"-XMP-lr:HierarchicalSubject+={h}"]

    args.append(str(path))
    print(args)
    subprocess.run(args, capture_output=True, check=True)


# ---------------------------------------------------------------------------
# Tag extraction
# ---------------------------------------------------------------------------

def extract_tags_from_prompt(prompt_json: dict) -> list[tuple[str, str]]:
    """
    New format: the Prompt JSON is a flat dict of node_id → node.
    Find all ShowText|pysssss nodes whose _meta.title starts with "Tag:"
    and return [(title, value), ...].
    """
    tags = []
    for node in prompt_json.values():
        if isinstance(node, dict) and node.get("class_type") == "ShowText|pysssss":
            title = node.get("_meta", {}).get("title", "")
            if title.startswith("Tag:"):
                value = node.get("inputs", {}).get("text_0", "n/a")
                tags.append((title, str(value)))
    return sorted(tags)


def extract_tags_from_workflow(workflow_json: dict) -> list[tuple[str, str]]:
    """
    Old format: the Workflow JSON has a nested structure.
    Walk it recursively looking for ShowText|pysssss nodes with a Tag: title.
    """
    tags = []

    def walk(obj):
        if isinstance(obj, dict):
            node_type  = obj.get("type", "")
            node_title = obj.get("title", "")
            if node_type == "ShowText|pysssss" and node_title.startswith("Tag:"):
                values = obj.get("widgets_values", [])
                if values:
                    tags.append((node_title, str(values[0])))
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    walk(workflow_json)
    return sorted(tags)


def tags_to_keywords(tags: list[tuple[str, str]]) -> list[tuple[str, str, str]]:
    """
    Convert [(title, value), ...] to [(flat_parent, flat_child, hierarchical), ...]
    where:
        flat_parent  = "ai:parameters:w1.steps"
        flat_child   = "ai:parameters:w1.steps#5"
        hierarchical = "AI|ai:parameters|ai:parameters:w1.steps|ai:parameters:w1.steps#5"
    """
    result = []
    for title, value in tags:
        # "Tag: w1.steps" → "ai:parameters:w1.steps"
        param  = title.removeprefix("Tag:").strip()
        parent = f"ai:parameters:{param}"
        child  = f"{parent}#{value}"
        hier   = f"AI|ai:parameters|{parent}|{child}"
        result.append((parent, child, hier))
    return result


# ---------------------------------------------------------------------------
# Per-file processing
# ---------------------------------------------------------------------------

def process_file(path: Path) -> None:
    if path.suffix.lower() not in IMAGE_SUFFIXES:
        return

    try:
        meta = exiftool_read(path)
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] exiftool read failed for {path}: {e}", file=sys.stderr)
        return

    # Prefer new Prompt-based format; fall back to old Workflow format
    tags = []
    prompt_raw   = meta.get("Prompt")
    workflow_raw = meta.get("Workflow")

    if not workflow_raw and prompt_raw:
        try:
            tags = extract_tags_from_prompt(json.loads(prompt_raw))
        except (json.JSONDecodeError, AttributeError) as e:
            print(f"[ERROR] Failed to parse Prompt JSON in {path}: {e}", file=sys.stderr)
            return
    elif workflow_raw:
        try:
            tags = extract_tags_from_workflow(json.loads(workflow_raw))
        except (json.JSONDecodeError, AttributeError) as e:
            print(f"[ERROR] Failed to parse Workflow JSON in {path}: {e}", file=sys.stderr)
            return
    else:
        return  # no metadata to process

    if not tags:
        print(f"=== {path} ===")
        print("  (no tags found)")
        print()
        return

    keywords = tags_to_keywords(tags)

    flat_keywords   = [kw  for parent, child, _ in keywords for kw in (parent, child)]
    hierarchicals   = [hier for _, _, hier in keywords]

    print(f"=== {path} ===")
    for parent, child, hier in keywords:
        print(f"  + Hierarchy: {hier}")

    try:
        exiftool_write(path, flat_keywords, hierarchicals)
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] exiftool write failed for {path}: {e}", file=sys.stderr)

    print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Write ComfyUI AI generation tags as photo library keywords."
    )
    parser.add_argument("target", help="Image file or directory to process.")
    args = parser.parse_args()

    target = Path(args.target)

    if target.is_file():
        process_file(target)
    elif target.is_dir():
        for path in sorted(target.rglob("*")):
            if path.is_file():
                process_file(path)
    else:
        print(f"Error: '{target}' is neither a file nor a directory.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()