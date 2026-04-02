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
from CommandBase import CommandBase

from comfyui_client.Commons import log, debug

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}


# ---------------------------------------------------------------------------
# exiftool helpers
# ---------------------------------------------------------------------------

def exiftool_read(path: Path) -> dict[str, str]:
    """Return a flat dict of all EXIF fields for *path* (string values)."""
    debug(f"exiftool -j {str(path)}")
    result = subprocess.run(["exiftool", "-j", str(path)], capture_output=True, text=True, check=True)
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
    debug(args)
    subprocess.run(args, capture_output=True, check=True)


# ---------------------------------------------------------------------------
# Tag extraction
# ---------------------------------------------------------------------------

def extract_tags_from_prompt(prompt_json: dict) -> tuple[list[tuple[str, str]], list[str]]:
    """
    New format: the Prompt JSON is a flat dict of node_id → node.
    Find all ShowText|pysssss nodes whose _meta.title starts with "Tag:"
    and return:
      - [(title, value), ...] for AI parameter tags
      - [keyword, ...] for user keywords from the "Keywords" node
    """
    tags = []
    user_keywords = []

    for node in prompt_json.values():
        if isinstance(node, dict) and node.get("class_type") == "ShowText|pysssss":
            title = node.get("_meta", {}).get("title", "")
            if title.startswith("Tag:"):
                value = node.get("inputs", {}).get("text_0", "n/a")
                tags.append((title, str(value)))
            elif title == "Keywords":
                keywords_text = node.get("inputs", {}).get("text_0", "")
                user_keywords = [k.strip() for k in keywords_text.split("\n") if k.strip()]

    return sorted(tags), user_keywords


def extract_tags_from_workflow(workflow_json: dict) -> tuple[list[tuple[str, str]], list[str]]:
    """
    Old format: the Workflow JSON has a nested structure.
    Walk it recursively looking for ShowText|pysssss nodes with a Tag: title
    or a Keywords title.
    """
    tags = []
    user_keywords = []

    def walk(obj):
        if isinstance(obj, dict):
            node_type  = obj.get("type", "")
            node_title = obj.get("title", "")
            if node_type == "ShowText|pysssss":
                if node_title.startswith("Tag:"):
                    values = obj.get("widgets_values", [])
                    if values:
                        tags.append((node_title, str(values[0])))
                elif node_title == "Keywords":
                    values = obj.get("widgets_values", [])
                    if values:
                        user_keywords.extend(
                            k.strip() for k in str(values[0]).split("\n") if k.strip()
                        )
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    walk(workflow_json)
    return sorted(tags), user_keywords


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

    log(f"=== {path} ===")

    try:
        meta = exiftool_read(path)
    except subprocess.CalledProcessError as e:
        log(f"[ERROR] exiftool read failed for {path}: {e}")
        return

    # Prefer new Prompt-based format; fall back to old Workflow format
    tags = []
    user_keywords = []
    prompt_raw   = meta.get("Prompt")
    workflow_raw = meta.get("Workflow")

    if not workflow_raw and prompt_raw:
        try:
            tags, user_keywords = extract_tags_from_prompt(json.loads(prompt_raw))
        except (json.JSONDecodeError, AttributeError) as e:
            log(f"[ERROR] Failed to parse Prompt JSON in {path}: {e}")
            return
    elif workflow_raw:
        try:
            tags, user_keywords = extract_tags_from_workflow(json.loads(workflow_raw))
        except (json.JSONDecodeError, AttributeError) as e:
            log(f"[ERROR] Failed to parse Workflow JSON in {path}: {e}")
            return
    else:
        return  # no metadata to process

    if not tags and not user_keywords:
        log("  (no tags or keywords found)")
        log("")
        return

    # Filter tags: drop lora_present always; drop lora_name and lora_strength
    # when lora_name has no value (empty string after #).
    lora_name_value = next((v for t, v in tags if t == "Tag: w1.lora_name"), "")
    filtered_tags = [
        (title, value) for title, value in tags
        if title != "Tag: w1.lora_present"
           and not (title in ("Tag: w1.lora_name", "Tag: w1.lora_strength") and not lora_name_value)
    ]

    ai_keywords   = tags_to_keywords(filtered_tags)
    flat_keywords = [kw for parent, child, _ in ai_keywords for kw in (parent, child)]
    hierarchicals = [hier for _, _, hier in ai_keywords]

    flat_user = [kw for kw in user_keywords if "|" not in kw]
    hier_user = [kw for kw in user_keywords if "|" in kw]
    flat_keywords += flat_user
    hierarchicals += hier_user

    for parent, child, hier in ai_keywords:
        log(f"  + Hierarchy: {hier}")
    for kw in flat_user:
        log(f"  + Keyword:   {kw}")
    for kw in hier_user:
        log(f"  + Hierarchy: {kw}")

    try:
        exiftool_write(path, flat_keywords, hierarchicals)
    except subprocess.CalledProcessError as e:
        log(f"[ERROR] exiftool write failed for {path}: {e}")

    log("")


def set_metadata(args) -> None:
    target = Path(args.target)

    if target.is_file():
        process_file(target)
    elif target.is_dir():
        for path in sorted(target.rglob("*")):
            if path.is_file():
                process_file(path)
    else:
        log(f"Error: '{target}' is neither a file nor a directory.")
        sys.exit(1)


class SetMetadata(CommandBase):

    def name(self) -> str:
        return "set-metadata"

    def process_args(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("target", nargs="?", default=".", help="Image file or directory to process (default: current directory).")

    def _run(self, args) -> None:
        set_metadata(args)