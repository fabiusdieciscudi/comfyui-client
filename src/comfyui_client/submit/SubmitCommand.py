#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: © 2026-present Fabius Dieciscudi
# SPDX-License-Identifier: MIT

import argparse
import json
import re
import time
import requests
from pathlib import Path
from itertools import product
from CommandBase import CommandBase
from comfyui_client.Commons import log, count_words, debug

DEFAULT_WORKFLOW_PATH       = "w1_workflow_api.json"
W1_WORKFLOW_PATH = Path(__file__).parent.parent.parent.parent / "workflows" / "api" / "W1 (diffusion based).json"
POLL_INTERVAL = 3           # seconds between /history polls
POLL_TIMEOUT  = 600         # seconds before giving up on a job
_MAX_INCLUDE_DEPTH = 16     # Maximum fragment-inclusion depth (guards against circular references).


# --- Tag extraction -----------------------------------------------------------

DEFAULTS = {
    "seed":            "56234532624987",
    "steps":           "9",
    "width":           "1024",
    "height":          "1600",
    "cfg":             "1.0",
    "denoise":         "1.0",
    "sampler_name":    "ddim",
    "scheduler":       "sgm_uniform",
    "diffusion_model": "z_image_turbo_bf16.safetensors",
    "clip_name":       "qwen_3_4b.safetensors",
    "clip_type":       "qwen_image",
    "vae_name":        "ae.safetensors",
    "lora_name":       "",
    "lora_strength":   "1.0",
    "up_steps":        "25",
    "up_width":        "0",     # 0 means "not set" (up_present will be false)
    "up_height":       "0",
    "up_cfg":          "1.0",
    "up_denoise":      "0.4",
    "up_sampler_name": "dpmpp_2m_sde",
    "up_scheduler":    "karras",
    "up_model":        "4x_NickelbackFS_72000_G.pth",
    "aspect":          "",      # empty means no aspect forcing
}

# Maps tag name → ShowText node title in the workflow
TAG_NODE_TITLES = {
    "seed":            "Tag: w1.seed",
    "steps":           "Tag: w1.steps",
    "width":           "Tag: w1.width",
    "height":          "Tag: w1.height",
    "cfg":             "Tag: w1.cfg",
    "denoise":         "Tag: w1.denoise",
    "sampler_name":    "Tag: w1.sampler_name",
    "scheduler":       "Tag: w1.scheduler",
    "diffusion_model": "Tag: w1.diffusion_model",
    "clip_name":       "Tag: w1.clip_name",
    "clip_type":       "Tag: w1.clip_type",
    "vae_name":        "Tag: w1.vae_name",
    "lora_name":       "Tag: w1.lora_name",
    "lora_strength":   "Tag: w1.lora_strength",
    "up_steps":        "Tag: w1.up_steps",
    "up_width":        "Tag: w1.up_width",
    "up_height":       "Tag: w1.up_height",
    "up_cfg":          "Tag: w1.up_cfg",
    "up_denoise":      "Tag: w1.up_denoise",
    "up_sampler_name": "Tag: w1.up_sampler_name",
    "up_scheduler":    "Tag: w1.up_scheduler",
    "up_model":        "Tag: w1.up_model",
}

TAG_PATTERNS = {
    "seed":            r"@w1\.seed:([0-9]+)",
    "steps":           r"@w1\.steps:([0-9]+)",
    "width":           r"@w1\.width:([0-9]+)",
    "height":          r"@w1\.height:([0-9]+)",
    "cfg":             r"@w1\.cfg:([0-9]*\.[0-9]+)",
    "denoise":         r"@w1\.denoise:([0-9]*\.[0-9]+)",
    "sampler_name":    r"@w1\.sampler_name:([0-9A-Za-z_\.-]+)",
    "scheduler":       r"@w1\.scheduler:([0-9A-Za-z_\.]+)",
    "diffusion_model": r"@w1\.diffusion_model:([0-9A-Za-z_\.-]+)",
    "clip_name":       r"@w1\.clip_name:([0-9A-Za-z_\.-]+)",
    "clip_type":       r"@w1\.clip_type:([0-9A-Za-z_\.-]+)",
    "vae_name":        r"@w1\.vae_name:([0-9A-Za-z_\.-]+)",
    "lora_name":       r"@w1\.lora_name:([0-9A-Za-z_\.-]+)",
    "lora_strength":   r"@w1\.lora_strength:([0-9]*\.[0-9]+)",
    "up_steps":        r"@w1\.up_steps:([0-9]+)",
    "up_width":        r"@w1\.up_width:([0-9]+)",
    "up_height":       r"@w1\.up_height:([0-9]+)",
    "up_cfg":          r"@w1\.up_cfg:([0-9]*\.[0-9]+)",
    "up_denoise":      r"@w1\.up_denoise:([0-9]*\.[0-9]+)",
    "up_sampler_name": r"@w1\.up_sampler_name:([0-9A-Za-z_\.-]+)",
    "up_scheduler":    r"@w1\.up_scheduler:([0-9A-Za-z_\.]+)",
    "up_model":        r"@w1\.up_model:([0-9A-Za-z_\.-]+)",
    "aspect":          r"@aspect:([0-9]*\.?[0-9]+(?::[0-9]*\.?[0-9]+)?)",
}

# Line-oriented tags: value is everything after the colon to end of line.
# @keyword is multi-valued; @title and @description are last-wins.
_LINE_TAG_PATTERN = re.compile(r"^@(keyword|title|description):(.+)$", re.MULTILINE)


# Named pixel-count shortcuts in megapixels
_NAMED_PIXELS = {
    "4k": 3840 * 2160,
    "8k": 7680 * 4320
}

_MP_PATTERN = re.compile(r"^([0-9]*\.?[0-9]+)mp$")


class SubmitCommand(CommandBase):

    def name(self) -> str:
        return "submit"

    def process_args(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--prompt-file",  action="append", default=[], help="Path to a prompt text file (repeatable, concatenated).")
        parser.add_argument("--prompt",       action="append", default=[], help="Additional inline prompt text (repeatable, concatenated after --prompt-file content).")
        parser.add_argument("--prompt-path",  action="append", default=[], metavar="DIR", help="Directory of prompt fragments (repeatable). ")
        parser.add_argument("--range",        action="append", default=[], help="Tag sweep, e.g. w1.seed=123,456 or @w1.steps=5,8")
        parser.add_argument("--workflow",     default=DEFAULT_WORKFLOW_PATH)
        parser.add_argument("--w1",           action="store_true", help="Use the built-in W1 workflow and its default config file.")
        parser.add_argument("--comfyui",      default="http://127.0.0.1:8000")
        parser.add_argument("--scale",        type=float, default=1.0, help="Multiply width and height by this factor")
        parser.add_argument("--upscale",      default=None, metavar="VALUE", help="Upscale target: (e.g. 2.5 or a named pixel count target: 4k, 8k, 4mp).")
        parser.add_argument("--title",        default="", help="Title to embed in the image metadata.")
        parser.add_argument("--description",  default="", help="Description to embed in the image metadata.")
        parser.add_argument("--keyword",      action="append", default=[], help="Keyword to embed in the image (repeatable).")
        parser.add_argument("--wait",         action="store_true", help="Wait for each job to finish before submitting the next")
        parser.add_argument("--output",       default=None, metavar="DIR", help="Download generated images into this directory (implies --wait).")

    def _run(self, args) -> None:
        self.submit(args)

    # --- Fragment library -----------------------------------------------------

    def load_fragment_library(self, prompt_paths: list[str]) -> dict[str, str]:
        """Build a key→text map from one or more fragment directories.

        For each directory in *prompt_paths* every ``*.txt`` file is read
        recursively.  The map key is the file's path relative to that
        directory, with the ``.txt`` suffix removed (e.g. a file at
        ``frags/apparel/glasses.txt`` loaded from root ``frags/`` produces
        the key ``apparel/glasses``).

        When the same key appears in multiple directories the last directory
        on the command line wins, matching the general last-wins convention
        used elsewhere in this command.
        """
        library: dict[str, str] = {}

        for root_str in prompt_paths:
            root = Path(root_str)
            if not root.is_dir():
                raise RuntimeError(f"--prompt-path '{root_str}' is not an existing directory.")
            for txt_file in sorted(root.rglob("*.txt")):
                key = root.name + "/" + txt_file.relative_to(root).with_suffix("").as_posix()
                library[key] = txt_file.read_text(encoding="utf-8")
                debug(f"  [fragment] loaded '{key}' from {txt_file}")

        return library

    def expand_fragments(self, text: str, library: dict[str, str], _depth: int = 0) -> str:
        """Replace ``:key`` lines with the corresponding fragment text.

        A line is a candidate for expansion when, after stripping leading and
        trailing whitespace, it starts with ``:``.  The remainder of the line
        (after the colon, stripped) is looked up in *library*.

        Fragment bodies are themselves passed through ``expand_fragments``
        recursively so that fragments may include other fragments.
        ``_MAX_INCLUDE_DEPTH`` guards against circular references.

        Lines whose key is not found in the library are left unchanged and a
        warning is emitted, so that a typo never silently drops content.
        """
        if _depth > _MAX_INCLUDE_DEPTH:
            raise RuntimeError(f"Fragment inclusion depth exceeded {_MAX_INCLUDE_DEPTH}. Check for circular references in your prompt fragments.")

        result_lines: list[str] = []

        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith(":"):
                key = stripped[1:].strip()
                if key in library:
                    # Recursively expand the fragment body, then splice it in.
                    expanded = self.expand_fragments(library[key], library, _depth + 1)
                    result_lines.append(expanded.rstrip("\n"))
                else:
                    raise RuntimeError(f"Fragment key '{key}' not found in library.")
            else:
                result_lines.append(line)

        return "\n".join(result_lines)

    # --- Tag extraction -------------------------------------------------------

    def strip_comments(self, text: str) -> str:
        """Mirror the two-pass comment stripping of nodes 37:70 and 37:66."""
        text = re.sub(r"^\s*#.*\n", "", text, flags=re.MULTILINE)  # node 37:70: full comment lines
        text = re.sub(r"#.*$",      "", text, flags=re.MULTILINE)  # node 37:66: inline comments
        return text

    def extract_line_tags(self, text: str) -> tuple[list[str], str, str]:
        """Extract line-oriented @keyword, @title, and @description tags.

        These tags differ from @w1.* tags in that their value is the entire
        remainder of the line after the colon (including spaces, commas, and
        additional colons), making them suitable for free-form text.

        Must be called on comment-stripped text so that commented-out tags
        are not picked up.

        Returns:
            keywords    – list of all @keyword values found (preserves order)
            title       – value of the last @title tag, or "" if absent
            description – value of the last @description tag, or "" if absent
        """
        keywords: list[str] = []
        title = ""
        description = ""

        for match in _LINE_TAG_PATTERN.finditer(text):
            tag_name = match.group(1)
            value    = match.group(2).strip()
            if tag_name == "keyword":
                keywords.append(value)
            elif tag_name == "title":
                title = value
            elif tag_name == "description":
                description = value

        return keywords, title, description

    def extract_tags(self, text: str) -> dict:
        clean = self.strip_comments(text)
        resolved = {}

        for tag, pattern in TAG_PATTERNS.items():
            matches = re.findall(pattern, clean)
            resolved[tag] = matches[-1] if matches else DEFAULTS.get(tag, "")

        return resolved

    # --- Workflow helpers -----------------------------------------------------

    def load_workflow(self, path: str) -> dict:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def find_merger_node(self, workflow: dict) -> str:
        for node_id, node in workflow.items():
            if node.get("_meta", {}).get("title") == "Prompt merger":
                return node_id
        raise RuntimeError("'Prompt merger' node not found in workflow.")

    def find_node_by_title(self, wf: dict, title: str) -> dict:
        for node in wf.values():
            if node.get("_meta", {}).get("title", "") == title:
                return node
        raise RuntimeError(f"Node '{title}' not found in workflow.")

    def patch_workflow(self, workflow: dict, prompt: str, resolved: dict, merger_node_id: str, keywords: list[str], title: str, description: str) -> dict:
        wf = json.loads(json.dumps(workflow))  # deep copy

        # Patch 1: prompt text
        node = wf[merger_node_id]
        node["inputs"]["text_a"] = prompt
        node["inputs"]["text_b"] = ""
        node["inputs"]["text_c"] = ""

        # Patch 2: resolved tag values → ShowText nodes
        for tag, title_ in TAG_NODE_TITLES.items():
            self.find_node_by_title(wf, title_)["inputs"]["text_0"] = resolved[tag]

        # Patch 3: clean prompt → Prompt node
        clean_prompt = self.strip_comments(prompt)
        log(f"Words in prompt: {count_words(clean_prompt)}")
        self.find_node_by_title(wf, "Prompt")["inputs"]["text_0"] = re.sub(r"@[^:\s]+(:[^,\s]+)*\s*[,]*", "", clean_prompt)

        # Patch 4: keywords → Keywords node
        self.find_node_by_title(wf, "Keywords")["inputs"]["Text"] = "\n".join(keywords)

        # Patch 5: title and description → their respective placeholder nodes.
        # SetMetadataCommand reads these back from the embedded Prompt JSON and
        # writes them to XMP/IPTC fields via exiftool.
        self.find_node_by_title(wf, "Title")["inputs"]["Text"] = title
        self.find_node_by_title(wf, "Description")["inputs"]["Text"] = description

        return wf

    # --- ComfyUI API ----------------------------------------------------------

    def submit_prompt(self, base_url: str, workflow: dict) -> str:
        response = requests.post(
            f"{base_url}/prompt",
            json={"prompt": workflow},
            timeout=60,
        )
        if response.status_code == 200:
            prompt_id = response.json().get("prompt_id")
            if prompt_id is None:
                raise RuntimeError("HTTP 200 from /prompt but 'prompt_id' missing.")
            return prompt_id
        raise RuntimeError(f"HTTP {response.status_code} from /prompt: {response.text[:400]}")

    def wait_for_completion(self, base_url: str, prompt_id: str) -> dict | None:
        """Poll /history until the job finishes or times out.

        Returns the outputs dict on success, or None on failure/timeout.
        """
        deadline = time.time() + POLL_TIMEOUT
        while time.time() < deadline:
            try:
                r = requests.get(f"{base_url}/history/{prompt_id}", timeout=10)
                if r.status_code == 200:
                    data = r.json()
                    if prompt_id in data:
                        status = data[prompt_id].get("status", {})
                        if status.get("status_str") == "error":
                            log(f"  [ERROR] Job failed: {status}")
                            return None
                        outputs = data[prompt_id].get("outputs")
                        if outputs:
                            return outputs
            except Exception as e:
                log(f"  [WARN] Poll error: {e}")
            time.sleep(POLL_INTERVAL)
        log(f"  [TIMEOUT] {prompt_id}")
        return None

    def collect_output_images(self, outputs: dict) -> list[dict]:
        """Extract image file descriptors from a job's outputs dict.

        Each descriptor is a dict with keys: filename, subfolder, type.
        Only 'output' type images are collected (not previews/temp).
        """
        images = []
        for node_output in outputs.values():
            for img in node_output.get("images", []):
                if img.get("type") == "output":
                    images.append(img)
        return images

    def download_images(self, base_url: str, images: list[dict], output_dir: Path) -> list[Path]:
        """Download *images* from the ComfyUI /view endpoint into *output_dir*.

        Files are saved with their original filenames, preserving the subfolder
        structure emitted by ComfyUI (e.g. 2026-04-02/W1 2026-04-02 14-32F00001.png).

        Returns a list of the local paths written.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        saved = []

        for img in images:
            filename  = img["filename"]
            subfolder = img.get("subfolder", "")
            img_type  = img.get("type", "output")

            params = {"filename": filename, "type": img_type}
            if subfolder:
                params["subfolder"] = subfolder

            try:
                r = requests.get(f"{base_url}/view", params=params, timeout=120, stream=True)
                r.raise_for_status()
            except requests.RequestException as e:
                log(f"  [ERROR] Failed to download {filename}: {e}")
                continue

            # Preserve the subfolder hierarchy within output_dir
            if subfolder:
                dest_dir = output_dir / subfolder
                dest_dir.mkdir(parents=True, exist_ok=True)
            else:
                dest_dir = output_dir

            dest = dest_dir / filename
            with open(dest, "wb") as f:
                for chunk in r.iter_content(chunk_size=65536):
                    f.write(chunk)

            log(f"  [SAVED] {dest}")
            saved.append(dest)

        return saved

    # --- Upscale helpers ------------------------------------------------------

    def parse_upscale(self, value: str, base_width: int, base_height: int) -> tuple[int, int]:
        """Compute (up_width, up_height) from an --upscale argument.

        Supported syntaxes:
          "2.5"    — multiply both dimensions by 2.5
          "4k"     — scale to ~8.3 megapixels, preserving aspect ratio
          "8k"     — scale to ~33.2 megapixels, preserving aspect ratio
          "4mp"    — scale to exactly 4 megapixels, preserving aspect ratio
          "1.5mp"  — scale to 1.5 megapixels, preserving aspect ratio

        For pixel-count targets the original aspect ratio (base_width / base_height)
        is always preserved: only total pixel count changes.
        """
        v = value.strip().lower()

        target_pixels = None

        if v in _NAMED_PIXELS:
            target_pixels = _NAMED_PIXELS[v]
        else:
            m = _MP_PATTERN.match(v)
            if m:
                target_pixels = float(m.group(1)) * 1_000_000

        if target_pixels is not None:
            if target_pixels <= 0:
                raise ValueError(f"--upscale pixel count must be positive, got {value}.")
            upscale = (target_pixels / (base_width * base_height)) ** 0.5
            new_w = round(base_width * upscale)
            new_h = round(base_height * upscale)
            return new_w, new_h

        try:
            factor = float(v)
        except ValueError:
            raise ValueError(
                f"Invalid --upscale value '{value}'. "
                f"Expected a multiplier (e.g. 2.5), a named resolution ({', '.join(_NAMED_PIXELS)}), "
                f"or a megapixel target (e.g. 4mp, 1.5mp)."
            )

        if factor <= 0:
            raise ValueError(f"--upscale factor must be positive, got {factor}.")

        return round(base_width * factor), round(base_height * factor)

    # --- CLI ------------------------------------------------------------------

    def parse_range_arg(self, arg: str):
        key, values = arg.split('=', 1)
        key = key.strip().lstrip('@')   # tolerate leading @
        value_list = [v.strip() for v in values.split(',')]
        return key, value_list

    def apply_aspect(self, width: int, height: int, aspect_str: str) -> tuple[int, int]:
        """Resize to the given aspect ratio while preserving total pixel count.

        Accepts either a decimal ratio ("1.7778") or a colon-separated pair
        ("16:9").  The result satisfies new_w / new_h ≈ aspect and
        new_w * new_h ≈ width * height (rounded to the nearest integer).
        """
        if ":" in aspect_str:
            a, b = aspect_str.split(":", 1)
            aspect = float(a) / float(b)
        else:
            aspect = float(aspect_str)

        total_pixels = width * height
        # new_w = aspect * new_h  →  aspect * new_h² = total_pixels
        new_h = round((total_pixels / aspect) ** 0.5)
        new_w = round(total_pixels / new_h)
        return new_w, new_h

    def submit(self, args):
        # --w1 injects the bundled config as an implicit leading prompt file
        if args.w1:
            if not hasattr(args, 'workflow') or args.workflow == DEFAULT_WORKFLOW_PATH:
                args.workflow = str(W1_WORKFLOW_PATH)

        if not args.prompt_file and not args.prompt:
            raise RuntimeError("Specify at least --prompt-file or --prompt.")

        # Load fragment library from all --prompt-path directories (once).
        fragment_library: dict[str, str] = {}
        if args.prompt_path:
            fragment_library = self.load_fragment_library(args.prompt_path)

        prompt_parts = []
        for p in args.prompt_file:
            if not Path(p).is_file():
                raise RuntimeError(f"Prompt file not found: {p}")
            prompt_parts.append(Path(p).read_text(encoding="utf-8").rstrip())
        prompt_parts.extend(s.rstrip() for s in args.prompt)
        raw_prompt = "\n\n".join(prompt_parts).strip()

        # Strip comments first, then expand fragment inclusions.
        # Order matters: a comment like  # :some/key  must not trigger expansion.
        comment_stripped = self.strip_comments(raw_prompt)
        if fragment_library:
            full_prompt = self.expand_fragments(comment_stripped, fragment_library)
        else:
            full_prompt = comment_stripped

        # Extract line-oriented tags from the fully expanded, comment-stripped prompt.
        # These are merged with values supplied via CLI arguments (CLI wins on
        # title/description; CLI keywords are appended after prompt keywords).
        prompt_keywords, prompt_title, prompt_description = self.extract_line_tags(full_prompt)

        # CLI --title / --description override prompt tags (last-wins convention).
        title       = args.title       if args.title       else prompt_title
        description = args.description if args.description else prompt_description

        # Keywords: prompt tags first, then --keyword arguments.
        all_keywords = prompt_keywords + args.keyword

        ranges = {}
        for r in args.range:
            key, values = self.parse_range_arg(r)
            ranges[key] = values

        combinations = list(product(*ranges.values())) if ranges else [()]

        workflow_template = None
        merger_node_id    = None

        if not args.dry_run:
            workflow_template = self.load_workflow(args.workflow)
            merger_node_id    = self.find_merger_node(workflow_template)

        base_url = args.comfyui.rstrip('/')

        # --output forces blocking mode; warn if --wait was not also passed
        output_dir = Path(args.output) if args.output else None
        blocking = args.wait or output_dir is not None

        for i, combo in enumerate(combinations, 1):
            combo_dict   = dict(zip(ranges.keys(), combo)) if combo else {}

            extra_lines  = "\n".join(f"@{k}:{v}" for k, v in combo_dict.items())
            current_prompt = full_prompt + ("\n\n" + extra_lines if extra_lines else "")

            log(f"\n--- Combination {i}/{len(combinations)} ---")
            for k, v in combo_dict.items():
                log(f"  @{k}:{v}")

            resolved = self.extract_tags(current_prompt)
            has_scale = args.scale != 1.0
            has_aspect = resolved["aspect"]

            if has_aspect:
                new_width, new_height = self.apply_aspect(int(resolved["width"]), int(resolved["height"]), has_aspect)
                log(f"Adjusting size for aspect {resolved['aspect']}: {new_width} x {new_height}")
                resolved["width"]  = str(new_width)
                resolved["height"] = str(new_height)

            new_width  = str(int(int(resolved["width"])  * args.scale))
            new_height = str(int(int(resolved["height"]) * args.scale))

            if has_scale:
                log(f"Adjusting size for scale {args.scale}: {new_width} x {new_height}")

            if has_scale or has_aspect:
                current_prompt += f"\n\n@w1.width:{new_width} @w1.height:{new_height}"

            # --upscale: compute up_width / up_height from the final base dimensions
            # and append them to the prompt so the workflow picks them up.
            if args.upscale:
                base_w = int(new_width)
                base_h = int(new_height)
                up_w, up_h = self.parse_upscale(args.upscale, base_w, base_h)
                log(f"Upscale target ({args.upscale}): {up_w} x {up_h}")
                current_prompt += f"\n\n@w1.up_width:{up_w} @w1.up_height:{up_h}"
                # Re-extract so that resolved reflects the newly appended tags.
                resolved = self.extract_tags(current_prompt)

            if args.dry_run:
                log("\nResolved tags:")
                for k, v in resolved.items():
                    log(f"  {k}: {v}")
                if args.upscale:
                    # up_present is derived, not a prompt tag — show it explicitly
                    up_present = resolved["up_width"] != "0" and resolved["up_width"] != ""
                    log(f"  up_present: {str(up_present).lower()}")
                if all_keywords:
                    log("\nKeywords:")
                    for kw in all_keywords:
                        log(f"  {kw}")
                if title:
                    log(f"\nTitle:       {title}")
                if description:
                    log(f"Description: {description}")
                log("\nFull prompt:\n")
                log(current_prompt)
                log("-" * 80)
                continue

            wf = self.patch_workflow(workflow_template, current_prompt, resolved, merger_node_id, all_keywords, title, description)

            prompt_id = self.submit_prompt(base_url, wf)
            log(f"  [OK] Prompt ID: {prompt_id}")

            if blocking:
                log("  Waiting for completion...")
                outputs = self.wait_for_completion(base_url, prompt_id)
                if outputs is None:
                    log(" FAILED.")
                    continue
                log(" done.")

                if output_dir is not None:
                    images = self.collect_output_images(outputs)
                    if images:
                        self.download_images(base_url, images, output_dir)
                    else:
                        log("  [WARN] No output images found in job history.")

        log("\n=== BATCH COMPLETE ===")