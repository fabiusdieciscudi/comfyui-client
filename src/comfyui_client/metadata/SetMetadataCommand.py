#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: © 2026-present Fabius Dieciscudi
# SPDX-License-Identifier: MIT
"""
FixAIKeywords — read AI generation tags from ComfyUI image metadata
and write them as XMP Subject, IPTC Keywords, and XMP-lr:HierarchicalSubject.

"""

import argparse
import filecmp
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from comfyui_client.CommandBase import CommandBase
from comfyui_client.Commons import log, debug

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}

# Tags that should be suppressed when the upscale pass did not run.
_UP_TAG_PREFIX = "Tag: w1.up_"

# Tags that should be suppressed when no LoRA was applied.
_LORA_TAG_PREFIX = "Tag: w1.lora_"

# Derived boolean tags that are never useful as keywords.
_DERIVED_TAGS = {
    "Tag: w1.lora_present",
    "Tag: w1.up_width_present", # legacy
    "Tag: w1.up_present",
}


class SetMetadataCommand(CommandBase):

    def name(self) -> str:
        return "set-metadata"

    def process_args(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("target", nargs="?", default=".", help="Image file or directory to process (default: current directory).")
        parser.add_argument("--tags", action="store_true", default=False, help="Write AI generation parameters as XMP/IPTC keyword hierarchies.")
        parser.add_argument("--keywords", action="store_true", default=False, help="Write user-supplied keywords as XMP/IPTC keywords.")
        parser.add_argument("--prompt-to-description", action="store_true", default=False, help="Copy the generation prompt to XMP:Description and IPTC:Caption-Abstract.")
        parser.add_argument("--all", action="store_true", default=False, help="Enable --tags, --keywords, and --prompt-to-description.")

    def _run(self, args) -> None:
        if args.all:
            args.tags = True
            args.keywords = True
            args.prompt_to_description = True

        if not args.tags and not args.keywords and not args.prompt_to_description:
            log("Nothing to do. Specify at least one of --tags, --keywords, --prompt-to-description, or --all.")
            sys.exit(1)

        self.set_metadata(args)

    # --- exiftool helpers -----------------------------------------------------

    def exiftool_read(self, path: Path) -> dict[str, str]:
        """Return a flat dict of all EXIF fields for *path* (string values)."""
        debug(f"exiftool -j {str(path)}")
        result = subprocess.run(["exiftool", "-j", str(path)], capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        return data[0] if data else {}

    def exiftool_write(self, path: Path, keywords: list[str], hierarchicals: list[str], title: str, description: str) -> None:
        """Write keywords, hierarchical subjects, title, and description in a
        single exiftool call.

        Keyword and hierarchical subject fields are written with remove-then-add
        pairs to avoid duplicates while preserving any values already present
        that are not being touched.

        Title is written to XMP:Title and IPTC:Headline.
        Description is written to XMP:Description and IPTC:Caption-Abstract.
        Empty title or description values are skipped.
        """
        args = ["exiftool", "-overwrite_original", "-m"]

        for kw in keywords:
            args += [f"-XMP:Subject-={kw}", f"-XMP:Subject+={kw}"]
            args += [f"-IPTC:Keywords-={kw}", f"-IPTC:Keywords+={kw}"]

        for h in hierarchicals:
            args += [f"-XMP-lr:HierarchicalSubject-={h}", f"-XMP-lr:HierarchicalSubject+={h}"]

        if title:
            args += [f"-XMP:Title={title}", f"-IPTC:Headline={title}"]

        if description:
            args += [f"-XMP:Description={description}", f"-IPTC:Caption-Abstract={description}"]

        tmp_path = None

        try:
            fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".exiftool.tmp", prefix=path.name)
            os.close(fd)
            shutil.copyfile(str(path), tmp_path)
            args.append(str(tmp_path))
            debug(f"{args}")
            subprocess.run(args, capture_output=True, check=True)

            if not filecmp.cmp(str(path), tmp_path, shallow=False):
                shutil.copyfile(tmp_path, str(path))
            else:
                log(f"No changes for {path}")
        finally:
            if tmp_path:
                os.unlink(tmp_path)

    # --- Tag extraction -------------------------------------------------------

    def extract_info_from_prompt(self, prompt_json: dict) -> tuple[list[tuple[str, str]], list[str], str, str]:
        """
        New format: the Prompt JSON is a flat dict of node_id → node.
        Find all ShowText|pysssss nodes whose _meta.title starts with "Tag:"
        and return:
          - [(title, value), ...] for AI parameter tags
          - [keyword, ...]        for user keywords from the "Keywords" node
          - str                   for the image title from the "Title" node
          - str                   for the image description from the "Description" node
        """
        tags = []
        user_keywords = []
        title = ""
        description = ""

        for node in prompt_json.values():
            if isinstance(node, dict):
                node_title = node.get("_meta", {}).get("title", "")
                if node_title.startswith("Tag:"):
                    value = node.get("inputs", {}).get("text_0", "n/a")
                    tags.append((node_title, str(value)))
                elif node_title == "Keywords":
                    # text_0 is legacy
                    keywords_text = node.get("inputs", {}).get("Text", node.get("inputs", {}).get("text_0", ""))
                    user_keywords = [k.strip() for k in keywords_text.split("\n") if k.strip()]
                elif node_title == "Title":
                    # text_0 is legacy
                    title = node.get("inputs", {}).get("Text", node.get("inputs", {}).get("text_0", ""))
                elif node_title == "Description":
                    # text_0 is legacy
                    description = node.get("inputs", {}).get("Text", node.get("inputs", {}).get("text_0", ""))

        return sorted(tags), user_keywords, title, description

    def extract_info_from_workflow(self, workflow_json: dict) -> tuple[list[tuple[str, str]], list[str], str, str]:
        """
        Old format: the Workflow JSON has a nested structure.
        Walk it recursively looking for ShowText|pysssss nodes with a Tag: title,
        a Keywords title, a Title title, or a Description title.
        """
        tags = []
        user_keywords = []
        title = ""
        description = ""

        def walk(obj):
            nonlocal title, description
            if isinstance(obj, dict):
                node_title = obj.get("title", "")
                if node_title.startswith("Tag:"):
                    values = obj.get("widgets_values", [])
                    if values:
                        tags.append((node_title, str(values[0])))
                elif node_title == "Keywords":
                    values = obj.get("widgets_values", [])
                    if values:
                        user_keywords.extend(k.strip() for k in str(values[0]).split("\n") if k.strip())
                elif node_title == "Title":
                    values = obj.get("widgets_values", [])
                    if values:
                        title = str(values[0]).strip()
                elif node_title == "Description":
                    values = obj.get("widgets_values", [])
                    if values:
                        description = str(values[0]).strip()
                for v in obj.values():
                    walk(v)
            elif isinstance(obj, list):
                for item in obj:
                    walk(item)

        walk(workflow_json)
        return sorted(tags), user_keywords, title, description

    def tags_to_keywords(self, tags: list[tuple[str, str]]) -> list[tuple[str, str, str]]:
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
            debug(f"  {title} = {value} → {hier}")
            result.append((parent, child, hier))
        return result

    def extract_prompt_text_from_prompt(self, prompt_json: dict) -> str:
        """Return the text from the 'Prompt' ShowText node in a Prompt-format JSON."""
        for node in prompt_json.values():
            if isinstance(node, dict) and node.get("_meta", {}).get("title", "") == "Prompt":
                return node.get("inputs", {}).get("text_0", "")
        return ""

    def extract_prompt_text_from_workflow(self, workflow_json: dict) -> str:
        """Return the text from the 'Prompt' ShowText node in a Workflow-format JSON."""
        result = []

        def walk(obj):
            if isinstance(obj, dict):
                if obj.get("title", "") == "Prompt":
                    values = obj.get("widgets_values", [])
                    if values:
                        result.append(str(values[0]))
                for v in obj.values():
                    walk(v)
            elif isinstance(obj, list):
                for item in obj:
                    walk(item)

        walk(workflow_json)
        return result[0] if result else ""

    # --- Per-file processing --------------------------------------------------

    def _lora_is_active(self, tags: list[tuple[str, str]]) -> bool:
        """Return True if at least one LoRA slot is populated.

        Checks both the legacy "Tag: w1.lora_name" key (old workflow format)
        and the current "Tag: w1.lora_name_01" key (new numbered format).
        A slot is considered active when its value is non-empty and not "None".
        """
        _INACTIVE = {"", "none"}

        # Legacy single-slot tag (old workflow format).
        legacy = next((v for t, v in tags if t == "Tag: w1.lora_name"), None)
        if legacy is not None and legacy.strip().lower() not in _INACTIVE:
            return True

        # Current numbered slots: lora_name_01 … lora_name_04.
        for tag_title, value in tags:
            if tag_title.startswith("Tag: w1.lora_name_"):
                return value.strip().lower() not in _INACTIVE

        return False

    def process_file(self, path: Path, args) -> None:
        if path.suffix.lower() not in IMAGE_SUFFIXES:
            return

        log(f"=== {path} ===")

        try:
            meta = self.exiftool_read(path)
        except subprocess.CalledProcessError as e:
            log(f"[ERROR] exiftool read failed for {path}: {e}")
            return

        # Prefer new Prompt-based format; fall back to old Workflow format
        tags = []
        user_keywords = []
        title = ""
        description = ""
        prompt_raw   = meta.get("Prompt")
        workflow_raw = meta.get("Workflow")

        if not workflow_raw and prompt_raw:
            try:
                tags, user_keywords, title, description = self.extract_info_from_prompt(json.loads(prompt_raw))
            except (json.JSONDecodeError, AttributeError) as e:
                log(f"[ERROR] Failed to parse Prompt JSON in {path}: {e}")
                return
        elif workflow_raw:
            try:
                tags, user_keywords, title, description = self.extract_info_from_workflow(json.loads(workflow_raw))
            except (json.JSONDecodeError, AttributeError) as e:
                log(f"[ERROR] Failed to parse Workflow JSON in {path}: {e}")
                return
        else:
            return  # no metadata to process

        if not tags and not user_keywords and not title and not description:
            log("  (no tags, keywords, title, or description found)")
            log("")
            return

        # Determine whether the upscale pass ran and whether a LoRA was applied.
        up_present_value = next((v for t, v in tags if t == "Tag: w1.up_present"), "false")
        up_present = up_present_value.strip().lower() == "true"

        lora_active = self._lora_is_active(tags)

        # Filter tags:
        # - always drop derived boolean tags (lora_present, up_present, up_width_present)
        # - drop all w1.lora_* tags when no LoRA was applied
        # - drop all w1.up_* tags when the upscale pass did not run
        filtered_tags = []
        for tag_title, value in tags:
            if tag_title in _DERIVED_TAGS:
                continue
            if tag_title.startswith(_LORA_TAG_PREFIX) and not lora_active:
                continue
            if tag_title.startswith(_UP_TAG_PREFIX) and not up_present:
                continue
            filtered_tags.append((tag_title, value))

        ai_keywords   = self.tags_to_keywords(filtered_tags)
        flat_keywords = [kw for parent, child, _ in ai_keywords for kw in (parent, child)]
        hierarchicals = [hier for _, _, hier in ai_keywords]

        flat_user = [kw for kw in user_keywords if "|" not in kw]
        hier_user = [kw for kw in user_keywords if "|" in kw]

        if args.tags:
            for parent, child, hier in ai_keywords:
                debug(f"  + Hierarchy: {hier}")

        if args.keywords:
            for kw in flat_user:
                debug(f"  + Keyword:   {kw}")
            for kw in hier_user:
                debug(f"  + Hierarchy: {kw}")

        if title:
            debug(f"  + Title:     {title}")
        if description:
            debug(f"  + Desc:      {description}")

        write_keywords      = (flat_keywords if args.tags else []) + (flat_user if args.keywords else [])
        write_hierarchicals = (hierarchicals if args.tags else []) + (hier_user if args.keywords else [])

        # --prompt-to-description: overwrite description with the prompt text
        write_description = description
        if args.prompt_to_description:
            if prompt_raw:
                prompt_text = self.extract_prompt_text_from_prompt(json.loads(prompt_raw))
            elif workflow_raw:
                prompt_text = self.extract_prompt_text_from_workflow(json.loads(workflow_raw))
            else:
                prompt_text = ""

            prompt_text = "\n".join(line for line in prompt_text.splitlines() if line.strip())

            if prompt_text:
                write_description = prompt_text
                debug(f"  + Description: {prompt_text[:80].replace(chr(10), ' ')}{'…' if len(prompt_text) > 80 else ''}")
            else:
                warning("  (no prompt found; skipping --prompt-to-description)")

        try:
            self.exiftool_write(path, write_keywords, write_hierarchicals, title, write_description)
        except subprocess.CalledProcessError as e:
            log(f"[ERROR] exiftool write failed for {path}: {e}")

        log("")

    def set_metadata(self, args) -> None:
        target = Path(args.target)

        if target.is_file():
            self.process_file(target, args)
        elif target.is_dir():
            for path in sorted(target.rglob("*")):
                if path.is_file():
                    self.process_file(path, args)
        else:
            log(f"Error: '{target}' is neither a file nor a directory.")
            sys.exit(1)