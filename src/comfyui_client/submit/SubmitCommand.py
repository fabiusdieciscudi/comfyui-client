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
from comfyui_client.CommandBase import CommandBase
from comfyui_client.Commons import log, count_words, debug, error, warning, info

DEFAULT_WORKFLOW_PATH       = "w1_workflow_api.json"
W1_WORKFLOW_PATH = Path(__file__).parent.parent.parent.parent / "workflows" / "api" / "W1 (diffusion based).json"
CONFIGS_PATH     = Path(__file__).parent.parent.parent.parent / "prompts" / "configs"

# Maps workflow flag name → config filename prefix (e.g. "w1" → "w1-foobar.txt").
WORKFLOW_PREFIXES = {
    "w1": "w1",
}

POLL_INTERVAL = 3           # seconds between /history polls
POLL_TIMEOUT  = 600         # seconds before giving up on a job
_MAX_INCLUDE_DEPTH = 16     # Maximum fragment-inclusion depth (guards against circular references).


# --- Tag extraction -----------------------------------------------------------

DEFAULTS = {
    "seed":             "56234532624987",
    "steps":            "9",
    "width":            "1024",
    "height":           "1600",
    "cfg":              "1.0",
    "denoise":          "1.0",
    "sampler_name":     "ddim",
    "scheduler":        "sgm_uniform",
    "diffusion_model":  "z_image_turbo_bf16.safetensors",
    "clip_name":        "qwen_3_4b.safetensors",
    "clip_type":        "qwen_image",
    "vae_name":         "ae.safetensors",
    "lora_name_01":     "None",
    "lora_strength_01": "0.0",
    "lora_name_02":     "None",
    "lora_strength_02": "0.0",
    "lora_name_03":     "None",
    "lora_strength_03": "0.0",
    "lora_name_04":     "None",
    "lora_strength_04": "0.0",
    "up_steps":         "25",
    "up_width":         "0",     # 0 means "not set" (up_present will be false)
    "up_height":        "0",
    "up_cfg":           "1.0",
    "up_denoise":       "0.4",
    "up_sampler_name":  "dpmpp_2m_sde",
    "up_scheduler":     "karras",
    "up_model":         "4x_NickelbackFS_72000_G.pth",
    "aspect":           "",      # empty means no aspect forcing
}


def _r_int(tag: str) -> str:
    """Regex pattern capturing an integer value for the given @w1.<tag>."""
    return rf"@w1\.{tag}:([0-9]+)"


def _r_float(tag: str) -> str:
    """Regex pattern capturing a float value (requires decimal point) for the given @w1.<tag>."""
    return rf"@w1\.{tag}:([0-9]*\.[0-9]+)"


def _r_name(tag: str) -> str:
    """Regex pattern capturing an identifier value for the given @w1.<tag>.

    Allows alphanumeric characters, spaces, underscores, dots, and hyphens.
    """
    return rf"@w1\.{tag}:([0-9A-Za-z _\.-]+)"


TAG_PATTERNS = {
    "seed":             _r_int("seed"),
    "steps":            _r_int("steps"),
    "width":            _r_int("width"),
    "height":           _r_int("height"),
    "cfg":              _r_float("cfg"),
    "denoise":          _r_float("denoise"),
    "sampler_name":     _r_name("sampler_name"),
    "scheduler":        _r_name("scheduler"),
    "diffusion_model":  _r_name("diffusion_model"),
    "clip_name":        _r_name("clip_name"),
    "clip_type":        _r_name("clip_type"),
    "vae_name":         _r_name("vae_name"),
    "lora_name_01":     _r_name("lora_name_01"),
    "lora_strength_01": _r_float("lora_strength_01"),
    "lora_name_02":     _r_name("lora_name_02"),
    "lora_strength_02": _r_float("lora_strength_02"),
    "lora_name_03":     _r_name("lora_name_03"),
    "lora_strength_03": _r_float("lora_strength_03"),
    "lora_name_04":     _r_name("lora_name_04"),
    "lora_strength_04": _r_float("lora_strength_04"),
    "up_steps":         _r_int("up_steps"),
    "up_width":         _r_int("up_width"),
    "up_height":        _r_int("up_height"),
    "up_cfg":           _r_float("up_cfg"),
    "up_denoise":       _r_float("up_denoise"),
    "up_sampler_name":  _r_name("up_sampler_name"),
    "up_scheduler":     _r_name("up_scheduler"),
    "up_model":         _r_name("up_model"),
    "aspect":           r"@aspect:([0-9]*\.?[0-9]+(?::[0-9]*\.?[0-9]+)?)",
}

# Line-oriented tags: value is everything after the colon to end of line.
# @keyword is multi-valued; @title and @description are last-wins.
_LINE_TAG_PATTERN = re.compile(r"@(keyword|title|description):(.+)$", re.MULTILINE)

# Regex used to strip @tags from the prompt text before sending to the text
# encoder. Matches @namespace.param:value where value runs to the next @ or
# end of line, correctly handling multi-word values such as:
#   @title:Ritratto di Claire
_STRIP_TAGS_RE = re.compile(r"@\S+:[^@\n]*")

# Named pixel-count shortcuts in megapixels
_NAMED_PIXELS = {
    "4k": 3840 * 2160,
    "8k": 7680 * 4320
}

_MP_PATTERN = re.compile(r"^([0-9]*\.?[0-9]+)mp$")

# Matches the <lora:name:strength> shorthand
_LORA_SYNTAX_RE = re.compile(r"<lora:([\w.-]+):([0-9]*\.?[0-9]+)>")

# Maximum number of <lora:…> tokens accepted in a single prompt.
_MAX_LORA_COUNT = 4

# Maximum recommended word count for the cleaned prompt, keyed by --model name
# (i.e. the stem passed to --model, without a path or .safetensors suffix).
# A warning is issued when the word count exceeds the limit; submission still
# proceeds, because the encoder may silently truncate rather than error out.
MODEL_MAX_WORDS: dict[str, int] = {
    "z_image_turbo_bf16": 300,
    "z_image_bf16":       300,
    "flux2_dev_fp8":      500,
}


class SubmitCommand(CommandBase):

    def name(self) -> str:
        return "submit"

    def process_args(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--prompt-file",  action="append", default=[], help="Path to a prompt text file (repeatable, concatenated).")
        parser.add_argument("--prompt",       action="append", default=[], help="Additional inline prompt text (repeatable, concatenated after --prompt-file content).")
        parser.add_argument("--prompt-path",  action="append", default=[], metavar="DIR", help="Directory of prompt fragments (repeatable). ")
        parser.add_argument("--model",        default=None, metavar="NAME", help="Configures the model to use. Requires --w1.")
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

    # --- Model config resolution ----------------------------------------------

    def resolve_model_config(self, model_name: str, args) -> Path:
        """Resolve --model NAME to a config file path.

        The workflow prefix is derived from whichever workflow flag is active
        (currently only --w1, giving prefix "w1"). Fails with a clear message
        if no workflow flag was passed or if the config file does not exist,
        listing the available options from the configs directory.

        :param model_name:  the value passed to --model
        :param args:        parsed command-line arguments
        :return:            resolved Path to the config file
        """
        # Determine the active workflow prefix.
        prefix = None

        if args.w1:
            prefix = WORKFLOW_PREFIXES["w1"]

        if prefix is None:
            raise RuntimeError("--model requires a workflow flag (e.g. --w1) to determine the config prefix.")

        config_path = CONFIGS_PATH / f"{prefix}-{model_name}.txt"

        if config_path.is_file():
            return config_path

        # Config not found — enumerate available options for this prefix.
        available = sorted(p.stem.removeprefix(f"{prefix}-") for p in CONFIGS_PATH.glob(f"{prefix}-*.txt"))

        if available:
            options = ", ".join(available)
            raise RuntimeError(f"Model config 'Available options for --model: {options}")
        else:
            raise RuntimeError(f"Model config 'No configs with prefix '{prefix}-' are available.")

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
                debug(f"[fragment] loaded '{key}' from {txt_file}")

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
                    info(f"Expanding: {key}...")
                    expanded = self.expand_fragments(library[key], library, _depth + 1)
                    result_lines.append(expanded.rstrip("\n"))
                else:
                    raise RuntimeError(f"Fragment key '{key}' not found in library.")
            else:
                result_lines.append(line)

        return "\n".join(result_lines)

    # --- Tag extraction -------------------------------------------------------

    def strip_comments(self, text: str) -> str:
        text = re.sub(r'\\#', '__ESCAPED_HASH__', text)
        text = re.sub(r"^\s*#.*\n", "", text, flags=re.MULTILINE)
        text = re.sub(r"#.*$",      "", text, flags=re.MULTILINE)
        text = text.replace('__ESCAPED_HASH__', '#')
        return text

    def expand_lora_syntax(self, text: str) -> str:
        """Replace <name,strength> shorthands with numbered @w1.lora_* tags.

        Each occurrence of ``<filename, strength>`` in *text* is replaced by a
        pair of tags:

            @w1.lora_name_01:filename
            @w1.lora_strength_01:strength

        The index is a zero-padded two-digit counter that starts at 01 and
        increments for each successive LoRA found in document order.

        Must be called on comment-stripped text so that occurrences inside
        comments are not expanded.

        Raises RuntimeError for any malformed ``<...>`` token whose content
        looks like a LoRA spec but is invalid (non-numeric strength, empty
        name).  Unrelated angle-bracket usage in the prompt is not affected
        because the regex requires the exact ``<name,float>`` shape.

        :param text:    comment-stripped prompt text
        :return:        prompt text with all LoRA shorthands replaced
        """

        matches = list(_LORA_SYNTAX_RE.finditer(text))

        if not matches:
            return text

        if len(matches) > _MAX_LORA_COUNT:
            raise RuntimeError(
                f"Too many LoRA tokens: found {len(matches)}, "
                f"maximum is {_MAX_LORA_COUNT}. "
                "Remove some <lora:…> entries from your prompt."
            )

        result = []
        prev_end = 0

        for idx, m in enumerate(matches, start=1):
            lora_name     = m.group(1).strip()
            lora_strength = m.group(2).strip()

            if not lora_name:
                raise RuntimeError(f"Malformed LoRA syntax at position {m.start()}: name is empty." )

            nn = f"{idx:02d}"
            replacement = (
                f"@w1.lora_name_{nn}:{lora_name}.safetensors\n"
                f"@w1.lora_strength_{nn}:{lora_strength}\n"
            )

            result.append(text[prev_end:m.start()])
            result.append(replacement)
            prev_end = m.end()
            info(f"Adding:\n{replacement}")

        result.append(text[prev_end:])
        return "".join(result)

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
            value    = match.group(2).strip().replace("\#", "#")    # FIXME: unescaping hashes should be unneeded
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
            resolved[tag] = matches[-1].strip() if matches else DEFAULTS.get(tag, "")

        return resolved

    # --- Workflow helpers -----------------------------------------------------

    def load_workflow(self, path: str) -> dict:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def find_node_by_title(self, wf: dict, title: str) -> dict:
        for node in wf.values():
            if node.get("_meta", {}).get("title", "") == title:
                return node
        raise RuntimeError(f"Node '{title}' not found in workflow.")

    def patch_workflow(self, workflow: dict, prompt: str, resolved: dict, keywords: list[str], title: str, description: str) -> dict:
        clean_prompt = self.strip_comments(prompt)
        info("Patching workflow...")
        wf = json.loads(json.dumps(workflow))  # deep copy
        self.set_node_inputs(wf, "Prompt merger", ["text_a", "text_b", "text_c"], [prompt, "", ""])
        current_node_id = 10000
        #
        # Recap of the situation.
        # The workflow exported in the API version comes with a full-fledged workflow that can be directly run in ComfyUI.
        # It contains a prompt parser that extracts @tags with the same logic of this command.
        # Each tag is processed with a pipeline like this:
        # + a regex node that extracts the value, if present, or an empty string
        # + a regex node that replaces the empty string with a default value
        # + a ShowText node used to embed the value of the tag so it can be retrieved from the generated image metadata
        # + possibly a cast to integer/float or a converter to combo
        #
        # Since ComfyUI embeds the prompt _at the beginning of the workflow_, it can't capture the actual values of tags.
        # But stopping and running it again is a feasible workaround when running from the ComfyUI user interface.
        # This is not feasible with this tool, so the workflow needs to be patched:
        # + At the input of any ShowText node a new dynamic PrimitiveString node is created with the proper value
        # + A text_0 input field is embedded in any ShowText node (this is at this point redundant, but it's needed for retro-compatibility with metadata).
        # This ensures that the data captured into metadata are actually the data fed to the processing nodes.
        for tag in (t for t in DEFAULTS if t != "aspect"):
            node_title = f"Tag: w1.{tag}"
            wf[str(current_node_id)] = {
                "inputs": {
                    "value": resolved[tag]
                },
                "class_type": "PrimitiveString",
                "_meta": {
                    "title": f"Hardwired value for {tag}"
                }
            }
            debug(f"  Created hardwired node PrimitiveString '{current_node_id}' with value '{resolved[tag]}'")
            self.set_node_inputs(wf, node_title, ["text", "text_0"], [[str(current_node_id), 0], resolved[tag]])
            current_node_id = current_node_id + 1

        log(f"Words in prompt: {count_words(clean_prompt)}")
        self.set_node_inputs(wf, "Prompt",      ["text_0"], [_STRIP_TAGS_RE.sub("", clean_prompt).strip()])
        # FIXME: aggiorna SetMedatadaCommand in modo da leggere sia da text_0 che da Text per questi nodi.
        # These node are not howText|pysssss, they are detached
        self.set_node_inputs(wf, "Keywords",    ["Text"], ["\n".join(keywords)])
        self.set_node_inputs(wf, "Title",       ["Text"], [title])
        self.set_node_inputs(wf, "Description", ["Text"], [description])

        # log(f"{wf}")

        return wf

    def set_node_inputs(self, wf, node_title: str, input_names: list[str], input_values: list) -> None:
        node = self.find_node_by_title(wf, node_title)
        inputs = node["inputs"]

        for name, value in zip(input_names, input_values):
            #            if name not in inputs and node_title not in relax_nodes:
            #                raise RuntimeError(f"Missing input '{name}' in {node_title}")
            debug(f"  {node_title}[\"inputs\"][\"{name}\"]: {value}")
            inputs[name] = value

    # --- ComfyUI option validation --------------------------------------------

    def fetch_available_options(self, base_url: str) -> dict[str, list[str]]:
        """Fetch available model, sampler, scheduler, CLIP, and VAE names
        from the running ComfyUI instance.

        Makes five HTTP requests:
          - GET /object_info?node=KSampler   → sampler_name and scheduler lists
          - GET /models/diffusion_models      → diffusion model filenames
          - GET /models/text_encoders         → CLIP model filenames
          - GET /models/vae                   → VAE filenames
          - GET /models/loras                 → LoRA filenames

        Returns a dict with these keys:
          "sampler_name"    – list of valid sampler identifiers
          "scheduler"       – list of valid scheduler identifiers
          "diffusion_model" – list of filenames in models/diffusion_models/
          "clip_name"       – list of filenames in models/text_encoders/
          "vae_name"        – list of filenames in models/vae/
          "lora_name"       – list of filenames in models/loras/

        Raises RuntimeError if any request fails or returns unexpected JSON.
        """
        available: dict[str, list[str]] = {}

        # Samplers and schedulers from KSampler object_info
        try:
            r = requests.get(f"{base_url}/object_info?node=KSampler", timeout=10)
            r.raise_for_status()
            data = r.json()
            ksampler = data["KSampler"]["input"]["required"]
            available["sampler_name"] = ksampler["sampler_name"][0]
            available["scheduler"]    = ksampler["scheduler"][0]
        except (requests.RequestException, KeyError) as e:
            raise RuntimeError(f"Failed to fetch sampler/scheduler options from ComfyUI: {e}")

        # Asset types: (resolved tag key, ComfyUI /models/<endpoint> path)
        asset_endpoints = [
            ("diffusion_model", "diffusion_models"),
            ("clip_name",       "text_encoders"),
            ("vae_name",        "vae"),
            ("lora_name",       "loras"),
        ]

        for tag_key, endpoint in asset_endpoints:
            try:
                r = requests.get(f"{base_url}/models/{endpoint}", timeout=10)
                r.raise_for_status()
                available[tag_key] = r.json()
            except (requests.RequestException, ValueError) as e:
                raise RuntimeError(
                    f"Failed to fetch {tag_key} options from ComfyUI "
                    f"(/models/{endpoint}): {e}"
                )

        return available

    def validate_resolved_tags(self,  resolved: dict, available: dict[str, list[str]]) -> list[str]:
        """Check that the values in *resolved* are present in *available*.

        Returns a (possibly empty) list of human-readable error strings, one
        per unsupported value.  The caller decides whether to abort or warn.

        Checked tags:
          sampler_name, scheduler, diffusion_model, clip_name, vae_name,
          lora_name_01 … lora_name_04 (each non-"None" slot is checked).
        """
        errors: list[str] = []

        # Single-value tags
        single_checks = [
            ("sampler_name",    "sampler_name"),
            ("scheduler",       "scheduler"),
            ("diffusion_model", "diffusion_model"),
            ("clip_name",       "clip_name"),
            ("vae_name",        "vae_name"),
        ]

        for tag_key, avail_key in single_checks:
            value = resolved.get(tag_key, "")
            options = available.get(avail_key, [])
            if value and options and value not in options:
                errors.append(
                    f"Unsupported {tag_key} '{value}'. "
                    f"Available: {', '.join(sorted(options))}"
                )

        # LoRA slots — only validate non-empty, non-"None" slots
        _INACTIVE = {"", "none"}
        lora_options = available.get("lora_name", [])
        for slot in range(1, 5):
            tag_key = f"lora_name_{slot:02d}"
            value = resolved.get(tag_key, "None")
            if value.strip().lower() in _INACTIVE:
                continue
            if lora_options and value not in lora_options:
                errors.append(
                    f"Unsupported {tag_key} '{value}'. "
                    f"Available: {', '.join(sorted(lora_options))}"
                )

        return errors

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
                            error(f"  [ERROR] Job failed: {status}")
                            return None
                        outputs = data[prompt_id].get("outputs")
                        if outputs:
                            return outputs
            except Exception as e:
                warning(f"  [WARN] Poll error: {e}")
            time.sleep(POLL_INTERVAL)
        error(f"  [TIMEOUT] {prompt_id}")
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
                error(f"  [ERROR] Failed to download {filename}: {e}")
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

        # --model resolves to a config file and prepends it to --prompt-file.
        # Resolution depends on the active workflow flag, so it must happen
        # after --w1 has been handled above.
        if args.model is not None:
            config_path = self.resolve_model_config(args.model, args)
            args.prompt_file.insert(0, str(config_path))
            debug(f"--model '{args.model}' resolved to {config_path}")

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
        full_prompt = self.strip_comments(raw_prompt)

        if fragment_library:
            full_prompt = self.expand_fragments(full_prompt, fragment_library)

        # AFTER expanding fragments
        full_prompt = self.expand_lora_syntax(full_prompt)
        # Extract line-oriented tags from the fully expanded, comment-stripped prompt.
        # These are merged with values supplied via CLI arguments (CLI wins on
        # title/description; CLI keywords are appended after prompt keywords).
        prompt_keywords, prompt_title, prompt_description = self.extract_line_tags(full_prompt)

        # CLI --title / --description override prompt tags (last-wins convention).
        title       = args.title       if args.title       else prompt_title
        description = args.description if args.description else prompt_description

        # Keywords: prompt tags first, then --keyword arguments.
        all_keywords = prompt_keywords + args.keyword

        # Word-count check: warn if the cleaned prompt exceeds the recommended
        # limit for the selected model.  The count is performed on the prompt
        # with all @tags stripped, matching what actually reaches the encoder.
        if args.model is not None and args.model in MODEL_MAX_WORDS:
            clean_for_count = _STRIP_TAGS_RE.sub("", full_prompt).strip()
            word_count = count_words(clean_for_count)
            max_words  = MODEL_MAX_WORDS[args.model]
            if word_count > max_words:
                warning(f"Prompt has {word_count} words, which exceeds the recommended maximum of {max_words} for model '{args.model}'.")

        ranges = {}
        for r in args.range:
            key, values = self.parse_range_arg(r)
            ranges[key] = values

        combinations = list(product(*ranges.values())) if ranges else [()]

        workflow_template = None

        if not args.dry_run:
            workflow_template = self.load_workflow(args.workflow)

        base_url = args.comfyui.rstrip('/')

        # --output forces blocking mode; warn if --wait was not also passed
        output_dir = Path(args.output) if args.output else None
        blocking = args.wait or output_dir is not None

        for i, combo in enumerate(combinations, 1):
            combo_dict   = dict(zip(ranges.keys(), combo)) if combo else {}

            extra_lines  = "\n".join(f"@{k}:{v}" for k, v in combo_dict.items())
            current_prompt = full_prompt + ("\n\n" + extra_lines if extra_lines else "")

            if len(combinations) > 1:
                log(f"\n--- Combination {i}/{len(combinations)} ---")

            for k, v in combo_dict.items():
                info(f"  @{k}:{v}")

            resolved = self.extract_tags(current_prompt)
            has_scale = args.scale != 1.0
            has_aspect = resolved["aspect"]

            if has_aspect:
                new_width, new_height = self.apply_aspect(int(resolved["width"]), int(resolved["height"]), has_aspect)
                info(f"Adjusting size for aspect {resolved['aspect']}: {new_width} x {new_height}")
                resolved["width"]  = str(new_width)
                resolved["height"] = str(new_height)

            new_width  = str(int(int(resolved["width"])  * args.scale))
            new_height = str(int(int(resolved["height"]) * args.scale))

            if has_scale:
                info(f"Adjusting size for scale {args.scale}: {new_width} x {new_height}")

            if has_scale or has_aspect:
                current_prompt += f"\n\n@w1.width:{new_width} @w1.height:{new_height}"

            # --upscale: compute up_width / up_height from the final base dimensions
            # and append them to the prompt so the workflow picks them up.
            if args.upscale:
                base_w = int(new_width)
                base_h = int(new_height)
                up_w, up_h = self.parse_upscale(args.upscale, base_w, base_h)
                info(f"Upscale target ({args.upscale}): {up_w} x {up_h}")
                current_prompt += f"\n\n@w1.up_width:{up_w} @w1.up_height:{up_h}"

            if has_scale or has_aspect or args.upscale:
                # Re-extract so that resolved reflects the newly appended tags.
                resolved = self.extract_tags(current_prompt)

            if args.dry_run:
                info("\nResolved tags:")
                for k, v in resolved.items():
                    info(f"  {k}: {v}")
                if args.upscale:
                    # up_present is derived, not a prompt tag — show it explicitly
                    up_present = resolved["up_width"] != "0" and resolved["up_width"] != ""
                    info(f"  up_present: {str(up_present).lower()}")
                if all_keywords:
                    info("\nKeywords:")
                    for kw in all_keywords:
                        info(f"  {kw}")
                if title:
                    info(f"\nTitle:       {title}")
                if description:
                    info(f"Description: {description}")
                info("\nFull prompt:\n")
                info(current_prompt)
                info("-" * 80)
                continue

            # Validate resolved tag values against the live ComfyUI instance
            # before spending time patching the workflow.
            try:
                available = self.fetch_available_options(base_url)
                validation_errors = self.validate_resolved_tags(resolved, available)
                if validation_errors:
                    for msg in validation_errors:
                        error(msg)
                    raise RuntimeError(
                        f"Aborting: {len(validation_errors)} unsupported value(s). "
                        "Fix the prompt or check your ComfyUI model files."
                    )
            except RuntimeError:
                raise
            except Exception as e:
                warning(f"Could not validate options against ComfyUI: {e}")

            wf = self.patch_workflow(workflow_template, current_prompt, resolved, all_keywords, title, description)

            prompt_id = self.submit_prompt(base_url, wf)
            log(f"[OK] Prompt ID: {prompt_id}")

            if blocking:
                log("  Waiting for completion...")
                outputs = self.wait_for_completion(base_url, prompt_id)
                if outputs is None:
                    error(" FAILED.")
                    continue
                log(" done.")

                if output_dir is not None:
                    images = self.collect_output_images(outputs)
                    if images:
                        self.download_images(base_url, images, output_dir)
                    else:
                        log("  [WARN] No output images found in job history.")

        log("\n=== BATCH COMPLETE ===")