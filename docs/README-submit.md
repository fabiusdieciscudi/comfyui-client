# ComfyUI Client — `submit` Command

The `submit` command sends a generation job to a running ComfyUI instance. It reads a prompt, resolves all `@` tags embedded in it, patches the target workflow accordingly, and posts it to the ComfyUI API.

- [The `@` Tag Mechanism](#the--tag-mechanism)
- [W1 Workflow Tags (`@w1.*`)](#w1-workflow-tags-w1)
- [Aspect Ratio Tag (`@aspect`)](#aspect-ratio-tag-aspect)
- [Fragment Library (`--prompt-path`)](#fragment-library---prompt-path)
- [Config Files](#config-files)
- [Workflows](#workflows)
- [Command-Line Reference](#command-line-reference)
- [Makefile Shortcuts](#makefile-shortcuts)

---

## The `@` Tag Mechanism

Tags are inline directives embedded directly in prompt text. They control workflow parameters without requiring any changes to the workflow file itself. Tags are stripped from the prompt before it is sent to the text encoder, so they never appear in the generated image's conditioning.

### Syntax

```
@namespace.parameter:value
```

Tags can appear anywhere in the prompt text, on their own line or inline. They can also appear in config files loaded via `--prompt-file`. Lines beginning with `#` are treated as comments and ignored entirely; `#` also starts an inline comment to the end of the line.

```
A cat sitting on a sofa, smoking a pipe   # the subject

@w1.width:1024 @w1.height:1536
@w1.steps:9
@w1.seed:123456
```

When the same tag appears more than once, the last occurrence wins.

---

## W1 Workflow Tags (`@w1.*`)

The W1 workflow (`workflows/api/W1 (diffusion based).json`) supports the following tags. All have default values and are optional.

### Image dimensions

| Tag          | Default | Description                   |
|--------------|---------|-------------------------------|
| `@w1.width`  | `1024`  | Output image width in pixels  |
| `@w1.height` | `1600`  | Output image height in pixels |

### Sampling

| Tag                | Default          | Description                                             |
|--------------------|------------------|---------------------------------------------------------|
| `@w1.seed`         | `56234532624987` | Random seed. Use a fixed value for reproducibility      |
| `@w1.steps`        | `9`              | Number of sampling steps                                |
| `@w1.cfg`          | `1.0`            | Classifier-free guidance scale                          |
| `@w1.denoise`      | `1.0`            | Denoising strength (1.0 = full generation from noise)   |
| `@w1.sampler_name` | `ddim`           | Sampler algorithm (e.g. `ddim`, `euler`, `dpmpp_sde`)   |
| `@w1.scheduler`    | `sgm_uniform`    | Noise schedule (e.g. `sgm_uniform`, `simple`, `karras`) |

### Model selection

| Tag                   | Default                          | Description                                                |
|-----------------------|----------------------------------|------------------------------------------------------------|
| `@w1.diffusion_model` | `z_image_turbo_bf16.safetensors` | Diffusion model filename (from `models/diffusion_models/`) |
| `@w1.clip_name`       | `qwen_3_4b.safetensors`          | Text encoder filename (from `models/text_encoders/`)       |
| `@w1.clip_type`       | `qwen_image`                     | Text encoder type, passed to `CLIPLoader`                  |
| `@w1.vae_name`        | `ae.safetensors`                 | VAE filename (from `models/vae/`)                          |

### LoRA

| Tag | Default | Description |
|-----|---------|-------------|
| `@w1.lora_name` | *(empty)* | LoRA filename (from `models/loras/`). If absent or empty, LoRA is skipped entirely |
| `@w1.lora_strength` | `1.0` | LoRA model weight strength |

When `@w1.lora_name` is not set, the LoRA loader is bypassed automatically via an internal switch node; no LoRA is applied.

### Upscaling

| Tag                   | Default                       | Description                                            |
|-----------------------|-------------------------------|--------------------------------------------------------|
| `@w1.up_width`        | `0`                           | Upscale target width in pixels. `0` disables upscaling |
| `@w1.up_height`       | `0`                           | Upscale target height in pixels                        |
| `@w1.up_steps`        | `25`                          | Sampling steps for the upscale pass                    |
| `@w1.up_cfg`          | `1.0`                         | CFG scale for the upscale pass                         |
| `@w1.up_denoise`      | `0.4`                         | Denoising strength for the upscale pass                |
| `@w1.up_sampler_name` | `dpmpp_2m_sde`                | Sampler algorithm for the upscale pass                 |
| `@w1.up_scheduler`    | `karras`                      | Noise schedule for the upscale pass                    |
| `@w1.up_model`        | `4x_NickelbackFS_72000_G.pth` | Upscale model filename (from `models/upscale_models/`) |

When `@w1.up_width` is `0` (the default), the upscale pass is bypassed automatically. These tags can be set directly in a prompt or config file, but the recommended way to enable upscaling is via the `--upscale` command-line option, which computes `@w1.up_width` and `@w1.up_height` automatically from the base image dimensions.

---

## Aspect Ratio Tag (`@aspect`)

The `@aspect` tag enforces a specific width-to-height ratio while keeping the total number of pixels constant.

### Syntax

The value is a decimal or an integer ratio (width ÷ height).

```
@aspect:1.5
@aspect:16:9
```

### How it works

`@w1.width` and `@w1.height` set the starting canvas. `@aspect` then redistributes those pixels into the requested ratio:

- The total pixel count (`width × height`) is preserved.
- Width and height are recomputed so that `new_width / new_height ≈ aspect` and `new_width × new_height ≈ width × height`.

Neither dimension is treated as a hard cap — both may grow or shrink relative to the starting values, as long as the product stays the same.

### Example

```
@w1.width:1600 @w1.height:900   # 1_440_000 px total
@aspect:1.0                     # square
```

Result: `1200 × 1200` (same 1 440 000 px, redistributed into a 1:1 ratio).

```
@w1.width:1024 @w1.height:1024  # 1_048_576 px total
@aspect:16:9
```

Result: `1365 × 768` (same pixel count, landscape 16:9).

`@aspect` interacts with `--scale`: the aspect ratio is resolved first, then `--scale` is applied to the result.

---

## Fragment Library (`--prompt-path`)

Large projects accumulate reusable prompt snippets — lighting descriptions, style recipes, character details, negative quality terms — that are tedious to copy-paste across prompt files. The `--prompt-path` option lets you maintain these as a library of plain text files and include them by name.

### Setting up a library

Point `--prompt-path` at a directory. Every `.txt` file in that directory (recursively) becomes a fragment. The key used to reference a fragment is:

```
<directory-name>/<path-relative-to-directory-without-.txt>
```

For example, given this layout:

```
prompts/fragments/
    lighting/golden-hour.txt
    lighting/overcast.txt
    style/painterly.txt
    apparel/glasses.txt
```

Loading with `--prompt-path prompts/fragments` produces these keys:

| Key                              | File                                         |
|----------------------------------|----------------------------------------------|
| `fragments/lighting/golden-hour` | `prompts/fragments/lighting/golden-hour.txt` |
| `fragments/lighting/overcast`    | `prompts/fragments/lighting/overcast.txt`    |
| `fragments/style/painterly`      | `prompts/fragments/style/painterly.txt`      |
| `fragments/apparel/glasses`      | `prompts/fragments/apparel/glasses.txt`      |

### Including fragments in a prompt

A line whose first non-whitespace character is `:` is treated as a fragment inclusion. The rest of the line (after the colon, trimmed) is the key:

```
A portrait of a woman.

:fragments/apparel/glasses
:fragments/lighting/golden-hour
:fragments/style/painterly
```

Each inclusion line is replaced in its entirety by the contents of the referenced fragment. The result is then passed through tag extraction and all other processing exactly as if you had written the fragment text inline.

Referencing an unknown key is a fatal error — the run stops immediately rather than silently dropping content.

### Fragments including other fragments

Fragment files can themselves contain `:key` inclusion lines. Expansion is recursive, so a high-level `scene/indoor-portrait` fragment can pull in sub-fragments for lighting, background, and mood without duplicating their text. Circular references are detected and produce an error (the depth limit is 16 levels).

### Multiple libraries

`--prompt-path` can be repeated. All directories are merged into a single library. When the same key appears in more than one directory, the last directory on the command line wins — consistent with the last-wins convention used for `@` tags.

```bash
./ComfyUIClient submit \
    --prompt-path prompts/fragments \
    --prompt-path ~/shared/company-fragments \
    --prompt-file prompts/moonlight.txt
```

### Comments and fragment lines

Comment stripping (`#`) happens before fragment expansion. A line like:

```
# :fragments/style/painterly
```

is removed as a comment and never triggers an inclusion.

---

## Config Files

Model-specific defaults are kept in `prompts/configs/` and loaded via `--prompt-file`. The config file is just a text file containing `@w1.*` tags (and optionally comments). It is concatenated with any style or subject files before tag extraction.

Available configs:

| File                                        | Model                                     |
|---------------------------------------------|-------------------------------------------|
| `prompts/configs/w1-z_image_turbo_bf16.txt` | Z-Image Turbo BF16 — fast, few steps      |
| `prompts/configs/w1-z_image_bf16.txt`       | Z-Image BF16 — higher quality, more steps |
| `prompts/configs/w1-flux2_dev_fp8.txt`      | FLUX.2 Dev FP8 mixed                      |

---

## Workflows

### W1 — Diffusion Based

The only workflow currently available. It supports any single-stream diffusion model (Flux-family, Z-Image, etc.) with a separately loaded CLIP encoder and VAE. Key features:

- All parameters are driven by `@w1.*` tags in the prompt
- Optional LoRA support with an automatic bypass switch when no LoRA is specified
- Optional upscale pass with an automatic bypass switch when `@w1.up_width` is `0`
- Saves output as PNG with full generation metadata embedded, in a dated folder (`YYYY-MM-DD/`)
- Also saves the latent alongside the image

Invoked via `--w1` shortcut.

### Required node packs

All nodes used in `workflows/api/W1 (diffusion based).json` fall into two categories: built-in ComfyUI nodes and nodes from four custom packs. Install all four via **ComfyUI Manager** (search by name).

#### pythongosssss / ComfyUI-Custom-Scripts

**Manager search name:** `ComfyUI-Custom-Scripts`
**GitHub:** https://github.com/pythongosssss/ComfyUI-Custom-Scripts

| Node                      | Purpose in W1                                                   |
|---------------------------|-----------------------------------------------------------------|
| `ShowText\|pysssss`       | Displays and embeds each resolved tag value into image metadata |
| `StringFunction\|pysssss` | Merges the config, style, and subject prompt parts              |
| `LoadText\|pysssss`       | Loads prompt text files from disk                               |

This is the most heavily used pack in the workflow. Every `Tag: w1.*` node in the metadata pipeline is a `ShowText|pysssss` node, making this pack essential — without it no tags appear in the saved image metadata.

#### Suzie1 / ComfyUI_Comfyroll_CustomNodes

**Manager search name:** `Comfyroll Studio`
**GitHub:** https://github.com/Suzie1/ComfyUI_Comfyroll_CustomNodes

| Node                   | Purpose in W1                                                                                          |
|------------------------|--------------------------------------------------------------------------------------------------------|
| `CR String To Number`  | Casts extracted string values to integer or float for the sampler inputs                               |
| `CR String To Combo`   | Converts a string (e.g. `"ddim"`) into a combo-box value for `sampler_name` and `scheduler`            |
| `CR String To Boolean` | Converts the `"true"`/`"false"` string from the upscale-present tag to a boolean for `ComfySwitchNode` |

#### rgthree / rgthree-comfy

**Manager search name:** `rgthree's ComfyUI Nodes`
**GitHub:** https://github.com/rgthree/rgthree-comfy

| Node                          | Purpose in W1                                                                     |
|-------------------------------|-----------------------------------------------------------------------------------|
| `Lora Loader Stack (rgthree)` | Loads up to four LoRAs simultaneously and applies them to both the model and CLIP |

#### bash-j / mikey_nodes

**Manager search name:** `Mikey Nodes`
**GitHub:** https://github.com/bash-j/mikey_nodes

| Node                | Purpose in W1                                                                  |
|---------------------|--------------------------------------------------------------------------------|
| `FileNamePrefix`    | Generates a date-based directory and filename prefix for saved images          |
| `RegexReplace`      | Reformats the prefix string into the `YYYY-MM-DD/W1 YYYY-MM-DD HH-MMF` pattern |
| `SaveImageExtended` | Saves the output PNG with full generation metadata embedded                    |

#### Also used in the UI workflow (not needed for the client)

The nodes `DF_Text` and `DF_String_Replace` from **Derfuu_ComfyUI_ModdedNodes** appear in the subgraph definitions inside `workflows/W1 (diffusion based).json` (the UI workflow) but not in the API workflow that the client submits. The client bypasses that internal tag-extraction processing by hardwiring values directly via `PrimitiveString` nodes. They are therefore not required when running the workflow via ComfyUI Client.

#### Installation

There are no interdependencies between the four packs. Install them in any order via ComfyUI Manager, then restart ComfyUI once:

```
ComfyUI-Custom-Scripts      (pythongosssss)
Comfyroll Studio            (Suzie1)
rgthree's ComfyUI Nodes     (rgthree)
Mikey Nodes                 (bash-j)
```

---

## Command-Line Reference

```
ComfyUIClient submit [options]
```

### Input

| Option               | Description                                                             |
|----------------------|-------------------------------------------------------------------------|
| `--prompt-file PATH` | Path to a prompt text file. Repeatable; files are concatenated in order |
| `--prompt TEXT`      | Inline prompt text. Repeatable; appended after `--prompt-file` content  |
| `--prompt-path DIR`  | Directory of prompt fragments. Repeatable; see [Fragment Library](#fragment-library---prompt-path) |

At least one of `--prompt-file` or `--prompt` is required. Typical usage loads a config file first, then provides the actual prompt:

```bash
ComfyUIClient submit --w1 --model z_image_turbo_bf16 --prompt "A cat sitting on a sofa, smoking a pipe"
ComfyUIClient submit --w1 --model z_image_turbo_bf16 --prompt-file prompts/portrait.txt
```

### Workflow

| Option            | Default                | Description                                              |
|-------------------|------------------------|----------------------------------------------------------|
| `--workflow PATH` | `w1_workflow_api.json` | Path to the API-format workflow JSON                     |
| `--w1`            | —                      | Shorthand: automatically selects the bundled W1 workflow |

### Connection

| Option          | Default                 | Description                      |
|-----------------|-------------------------|----------------------------------|
| `--comfyui URL` | `http://127.0.0.1:8000` | Base URL of the ComfyUI instance |

### Image sizing

| Option           | Default  | Description                                                                 |
|------------------|----------|-----------------------------------------------------------------------------|
| `--scale FACTOR` | `1.0`    | Multiply both width and height by this factor. Applied after tag resolution |

Example: generate a quick preview at half resolution:

```bash
./ComfyUIClient submit ... --scale 0.5
```

### Upscaling

| Option            | Description                                           |
|-------------------|-------------------------------------------------------|
| `--upscale VALUE` | Enable the upscale pass and set its target dimensions |

`--upscale` computes `@w1.up_width` and `@w1.up_height` from the final base dimensions (after `--scale` and `@aspect` are applied) and appends them to the prompt. The original aspect ratio is always preserved; only the total pixel count changes.

`VALUE` accepts three syntaxes:

| Syntax           | Example        | Behaviour                                                   |
|------------------|----------------|-------------------------------------------------------------|
| Multiplier       | `2.5`          | Multiply both base dimensions by the given factor           |
| Megapixel target | `4mp`, `1.5mp` | Scale to the given number of megapixels                     |
| Named shortcut   | `4k`, `8k`     | Scale to a standard pixel count (4k ≈ 8.3 MP, 8k ≈ 33.2 MP) |

```bash
# Upscale to 2× the base resolution
./ComfyUIClient submit ... --upscale 2

# Upscale to 4 megapixels
./ComfyUIClient submit ... --upscale 4mp

# Upscale to 4K pixel count
./ComfyUIClient submit ... --upscale 4k
```

The upscale pass parameters (`up_steps`, `up_cfg`, `up_denoise`) can be tuned independently via their `@w1.up_*` tags in the prompt or a config file.

### Parameter sweeps

| Option                  | Description                                                              |
|-------------------------|--------------------------------------------------------------------------|
| `--range TAG=V1,V2,...` | Sweep one or more tag values. Repeatable; all combinations are submitted |

The `--range` option overrides tag values extracted from the prompt, generating one job per combination. The `@w1.` prefix is optional.

```bash
# Submit 6 jobs: 2 seeds × 3 step counts
./ComfyUIClient submit \
   --model z_image_turbo_bf16 \
    --prompt "A moonlit forest" \
    --range w1.seed=111,222 \
    --range w1.steps=5,9,15
```

### Metadata

| Option         | Description                                                   |
|----------------|---------------------------------------------------------------|
| `--keyword KW` | Keyword to embed in the image's XMP/IPTC metadata. Repeatable |

Keywords are written into the workflow's `Keywords` node and later extracted by the `set-metadata` command.

### Job control

| Option         | Description                                                                 |
|----------------|-----------------------------------------------------------------------------|
| `--wait`       | Block until each job completes before submitting the next                   |
| `--output DIR` | Download completed images into *DIR* (implies `--wait`)                     |
| `--dry-run`    | Resolve and print all tags and the final prompt without submitting anything |

**`--output`**

When `--output` is given, the client polls ComfyUI until each job finishes and then downloads every output image via the `/view` endpoint into the specified directory, preserving the subfolder structure that ComfyUI generates (e.g. `2026-04-02/2026-04-02 14-32 00001.png`). The destination directory is created automatically if it does not exist. Only images of type `png` are downloaded; preview and temporary files are ignored.

`--output` implies `--wait`: jobs are always submitted one at a time and the next job does not start until the previous one has been downloaded. Specifying `--wait` explicitly alongside `--output` has no additional effect.

```bash
# Download all images from a sweep into a local folder
./ComfyUIClient submit \
    --w1 \
   --model z_image_turbo_bf16 \
    --prompt "A moonlit forest" \
    --range w1.seed=111,222,333 \
    --output build/output
```

**`--dry-run`**

`--dry-run` is useful for verifying tag resolution — including fragment expansion — before committing to a long sweep:

```bash
./ComfyUIClient submit \
    --w1 \
    --prompt-path prompts/fragments \
   --model z_image_turbo_bf16 \
    --prompt "A moonlit forest @w1.steps:5" \
    --upscale 4mp \
    --dry-run
```

### Debugging

| Option    | Description                                                              |
|-----------|--------------------------------------------------------------------------|
| `--debug` | Enable verbose logging, including the list of loaded fragment files      |

---

## Makefile Shortcuts

The `Makefile` provides convenience targets that wrap common `submit` invocations.

| Target                     | Description                                              |
|----------------------------|----------------------------------------------------------|
| `make cat`                 | Submit a built-in test prompt (cat on a sofa)            |
| `make cat-upscale`         | Submit a built-in test prompt (cat on a sofa)            |
| `make moonlight`           | Submit `prompts/moonlight.txt`                           |
| `make prompt PROMPT="..."` | Submit an inline prompt                                  |
| `make ... fast`            | Add `--scale 0.5 --range w1.steps=2` for a quick preview |
| `make ... dry-run`         | Add `--dry-run`                                          |

Example:

```bash
make prompt PROMPT="A stormy sea at night" fast dry-run
```