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

DEFAULT_WORKFLOW_PATH = "w1_workflow_api.json"
W1_WORKFLOW_PATH = Path(__file__).parent.parent / "workflows" / "api" / "W1 (diffusion based).json"
POLL_INTERVAL = 3    # seconds between /history polls
POLL_TIMEOUT  = 600  # seconds before giving up on a job


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
    "lora_name":       "",
    "lora_strength":   "1.0",   # sic — matches the typo in the workflow
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
    "aspect":          r"@aspect:([0-9]*\.[0-9]+)",
}


def strip_comments(text: str) -> str:
    """Mirror the two-pass comment stripping of nodes 37:70 and 37:66."""
    text = re.sub(r"^\s*#.*\n", "", text, flags=re.MULTILINE)  # node 37:70: full comment lines
    text = re.sub(r"#.*$",      "", text, flags=re.MULTILINE)  # node 37:66: inline comments
    return text


def extract_tags(text: str) -> dict:
    clean = strip_comments(text)
    resolved = {}

    for tag, pattern in TAG_PATTERNS.items():
        matches = re.findall(pattern, clean)
        resolved[tag] = matches[-1] if matches else DEFAULTS[tag]

    return resolved


# --- Workflow helpers ----------------------------------------------------------

def load_workflow(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def find_merger_node(workflow: dict) -> str:
    for node_id, node in workflow.items():
        if node.get("_meta", {}).get("title") == "Prompt merger":
            return node_id
    raise RuntimeError("'Prompt merger' node not found in workflow.")


def find_node_by_title(wf: dict, title: str) -> dict:
    for node in wf.values():
        if node.get("_meta", {}).get("title", "") == title:
            return node
    raise RuntimeError(f"Node '{title}' not found in workflow.")

def patch_workflow(workflow: dict, prompt: str, resolved: dict, merger_node_id: str, keywords: list[str]) -> dict:
    wf = json.loads(json.dumps(workflow))  # deep copy

    # Patch 1: prompt text
    node = wf[merger_node_id]
    node["inputs"]["text_a"] = prompt
    node["inputs"]["text_b"] = ""
    node["inputs"]["text_c"] = ""

    # Patch 2: resolved tag values → ShowText nodes
    for tag, title in TAG_NODE_TITLES.items():
        find_node_by_title(wf, title)["inputs"]["text_0"] = resolved[tag]

    # Patch 3: clean prompt → Prompt node
    find_node_by_title(wf, "Prompt")["inputs"]["text_0"] = re.sub(
        r"@[^:\s]+(:[^,\s]+)*\s*[,]*", "", strip_comments(prompt)
    )

    # Patch 4: keywords → Keywords node
    find_node_by_title(wf, "Keywords")["inputs"]["text_0"] = "\n".join(keywords)

    return wf


# --- ComfyUI API --------------------------------------------------------------

def submit_prompt(base_url: str, workflow: dict) -> str:
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


def wait_for_completion(base_url: str, prompt_id: str) -> bool:
    """Poll /history until the job finishes or times out."""
    deadline = time.time() + POLL_TIMEOUT
    while time.time() < deadline:
        try:
            r = requests.get(f"{base_url}/history/{prompt_id}", timeout=10)
            if r.status_code == 200:
                data = r.json()
                if prompt_id in data:
                    status = data[prompt_id].get("status", {})
                    if status.get("status_str") == "error":
                        print(f"  [ERROR] Job failed: {status}")
                        return False
                    if data[prompt_id].get("outputs"):
                        return True
        except Exception as e:
            print(f"  [WARN] Poll error: {e}")
        time.sleep(POLL_INTERVAL)
    print(f"  [TIMEOUT] {prompt_id}")
    return False


# --- CLI ----------------------------------------------------------------------

def parse_range_arg(arg: str):
    key, values = arg.split('=', 1)
    key = key.strip().lstrip('@')   # tolerate leading @
    value_list = [v.strip() for v in values.split(',')]
    return key, value_list

def apply_aspect(width: int, height: int, aspect: float) -> tuple[int, int]:
    """Force aspect ratio choosing the option that keeps both dims <= originals."""
    # Option A: keep width, compute height
    h_from_w = int(width / aspect)
    # Option B: keep height, compute width
    w_from_h = int(height * aspect)

    if h_from_w <= height:
        return width, h_from_w
    else:
        return w_from_h, height

def submit(args):
    # --w1 injects the bundled config as an implicit leading prompt file
    if args.w1:
        if not hasattr(args, 'workflow') or args.workflow == DEFAULT_WORKFLOW_PATH:
            args.workflow = str(W1_WORKFLOW_PATH)

    if not args.prompt_file and not args.prompt:
        raise RuntimeError("Specify at least --prompt-file or --prompt.")
    prompt_parts = []
    for p in args.prompt_file:
        if not Path(p).is_file():
            raise RuntimeError(f"Prompt file not found: {p}")
        prompt_parts.append(Path(p).read_text(encoding="utf-8").rstrip())
    prompt_parts.extend(s.rstrip() for s in args.prompt)
    full_prompt = "\n\n".join(prompt_parts).strip()

    ranges = {}
    for r in args.range:
        key, values = parse_range_arg(r)
        ranges[key] = values

    combinations = list(product(*ranges.values())) if ranges else [()]

    workflow_template = None
    merger_node_id    = None

    if not args.dry_run:
        workflow_template = load_workflow(args.workflow)
        merger_node_id    = find_merger_node(workflow_template)

    base_url = args.comfyui.rstrip('/')

    for i, combo in enumerate(combinations, 1):
        combo_dict   = dict(zip(ranges.keys(), combo)) if combo else {}

        extra_lines  = "\n".join(f"@{k}:{v}" for k, v in combo_dict.items())
        current_prompt = full_prompt + ("\n\n" + extra_lines if extra_lines else "")

        print(f"\n--- Combination {i}/{len(combinations)} ---")
        for k, v in combo_dict.items():
            print(f"  @{k}:{v}")

        resolved = extract_tags(current_prompt)

        if resolved["aspect"]:
            aspect = float(resolved["aspect"])
            new_width, new_height = apply_aspect(int(resolved["width"]), int(resolved["height"]), aspect)
            print(f"Adjusting size for aspect {aspect}: {new_width} x {new_height}")
            resolved["width"]  = str(new_width)
            resolved["height"] = str(new_height)

        new_width  = str(int(int(resolved["width"])  * args.scale))
        new_height = str(int(int(resolved["height"]) * args.scale))

        if args.scale != 1:
            print(f"Adjusting size for scale {args.scale}: {new_width} x {new_height}")
        if args.scale != 1 or resolved["aspect"]:
            current_prompt += f"\n\n@w1.width:{new_width} @w1.height:{new_height}"

        if args.dry_run:
            print("\nResolved tags:")
            for k, v in resolved.items():
                print(f"  {k}: {v}")
            if args.keyword:
                print("\nKeywords:")
                for kw in args.keyword:
                    print(f"  {kw}")
            print("\nFull prompt:\n")
            print(current_prompt)
            print("-" * 80)
            continue

        wf = patch_workflow(workflow_template, current_prompt, resolved, merger_node_id, args.keyword)

        prompt_id = submit_prompt(base_url, wf)
        print(f"  [OK] Prompt ID: {prompt_id}")

        if not args.no_wait:
            print("  Waiting for completion...", end="", flush=True)
            ok = wait_for_completion(base_url, prompt_id)
            print(" done." if ok else " FAILED.")

    print("\n=== BATCH COMPLETE ===")

class SubmitCommand(CommandBase):

    def name(self) -> str:
        return "submit"

    def process_args(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--prompt-file",  action="append", default=[], help="Path to a prompt text file (repeatable, concatenated).")
        parser.add_argument("--prompt",       action="append", default=[], help="Additional inline prompt text (repeatable, concatenated after --prompt-file content).")
        parser.add_argument("--range",        action="append", default=[], help="Tag sweep, e.g. w1.seed=123,456 or @w1.steps=5,8")
        parser.add_argument("--workflow",     default=DEFAULT_WORKFLOW_PATH)
        parser.add_argument("--w1",           action="store_true", help="Use the built-in W1 workflow and its default config file.")
        parser.add_argument("--comfyui",      default="http://127.0.0.1:8000")
        parser.add_argument("--scale",        type=float, default=1.0, help="Multiply width and height by this factor")
        parser.add_argument("--title",        default="", help="Title info to embed in the image")
        parser.add_argument("--keyword",      action="append", default=[], help="Keyword to embed in the image (repeatable).")
        parser.add_argument("--no-wait",      action="store_true", help="Don't wait for each job to finish before submitting the next")

    def _run(self, args) -> None:
        submit(args)