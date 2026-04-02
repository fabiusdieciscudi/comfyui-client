# ComfyUI Client — `submit` Command

The `submit` command sends a generation job to a running ComfyUI instance. It reads a prompt, resolves all `@` tags embedded in it, patches the target workflow accordingly, and posts it to the ComfyUI API.

- [The `@` Tag Mechanism](#the--tag-mechanism)
- [W1 Workflow Tags (`@w1.*`)](#w1-workflow-tags-w1)
- [Aspect Ratio Tag (`@aspect`)](#aspect-ratio-tag-aspect)
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

| Tag | Default | Description |
|-----|---------|-------------|
| `@w1.width` | `1024` | Output image width in pixels |
| `@w1.height` | `1600` | Output image height in pixels |

### Sampling

| Tag | Default | Description |
|-----|---------|-------------|
| `@w1.seed` | `56234532624987` | Random seed. Use a fixed value for reproducibility |
| `@w1.steps` | `9` | Number of sampling steps |
| `@w1.cfg` | `1.0` | Classifier-free guidance scale |
| `@w1.denoise` | `1.0` | Denoising strength (1.0 = full generation from noise) |
| `@w1.sampler_name` | `ddim` | Sampler algorithm (e.g. `ddim`, `euler`, `dpmpp_sde`) |
| `@w1.scheduler` | `sgm_uniform` | Noise schedule (e.g. `sgm_uniform`, `simple`, `karras`) |

### Model selection

| Tag | Default | Description |
|-----|---------|-------------|
| `@w1.diffusion_model` | `z_image_turbo_bf16.safetensors` | Diffusion model filename (from `models/diffusion_models/`) |
| `@w1.clip_name` | `qwen_3_4b.safetensors` | Text encoder filename (from `models/text_encoders/`) |
| `@w1.clip_type` | `qwen_image` | Text encoder type, passed to `CLIPLoader` |
| `@w1.vae_name` | `ae.safetensors` | VAE filename (from `models/vae/`) |

### LoRA

| Tag | Default | Description |
|-----|---------|-------------|
| `@w1.lora_name` | *(empty)* | LoRA filename (from `models/loras/`). If absent or empty, LoRA is skipped entirely |
| `@w1.lora_strength` | `1.0` | LoRA model weight strength |

When `@w1.lora_name` is not set, the LoRA loader is bypassed automatically via an internal switch node; no LoRA is applied.

---

## Aspect Ratio Tag (`@aspect`)

The `@aspect` tag forces a specific width-to-height ratio while keeping both dimensions within the bounds set by `@w1.width` and `@w1.height`.

### Syntax

```
@aspect:1.7778
```

The value is a decimal ratio (width ÷ height). For example, 16:9 = `1.7778`, 4:3 = `1.3333`, 2:3 = `0.6667`.

### How it works

The `@w1.width` and `@w1.height` values are treated as maximum bounds. The aspect ratio is enforced by choosing whichever dimension fits within both constraints:

- If the target height derived from the given width fits within `@w1.height`, the width is kept and height is adjusted.
- Otherwise, the height is kept and width is adjusted.

This guarantees neither dimension exceeds its configured maximum. The adjusted values are appended to the prompt as new `@w1.width` / `@w1.height` tags, overriding the originals.

### Example

```
@w1.width:1600 @w1.height:1600
@aspect:1.7778
```

Result: `1600 × 900` (landscape 16:9, width kept, height reduced).

```
@w1.width:1024 @w1.height:1024
@aspect:0.6667
```

Result: `683 × 1024` (portrait 2:3, height kept, width reduced).

`@aspect` interacts with `--scale`: the aspect ratio is resolved first, then `--scale` is applied to the result.

---

## Config Files

Model-specific defaults are kept in `prompts/configs/` and loaded via `--prompt-file`. The config file is just a text file containing `@w1.*` tags (and optionally comments). It is concatenated with any style or subject files before tag extraction.

Available configs:

| File | Model |
|------|-------|
| `prompts/configs/w1-z_image_turbo_bf16.txt` | Z-Image Turbo BF16 — fast, few steps |
| `prompts/configs/w1-z_image_bf16.txt` | Z-Image BF16 — higher quality, more steps |
| `prompts/configs/w1-flux2_dev_fp8.txt` | FLUX.2 Dev FP8 mixed |

---

## Workflows

### W1 — Diffusion Based

The only workflow currently available. It supports any single-stream diffusion model (Flux-family, Z-Image, etc.) with a separately loaded CLIP encoder and VAE. Key features:

- All parameters are driven by `@w1.*` tags in the prompt
- Optional LoRA support with an automatic bypass switch when no LoRA is specified
- Saves output as PNG with full generation metadata embedded, in a dated folder (`YYYY-MM-DD/`)
- Also saves the latent alongside the image

Invoked automatically via `--workflow` or `--w1`.

---

## Command-Line Reference

```
ComfyUIClient submit [options]
```

### Input

| Option | Description |
|--------|-------------|
| `--prompt-file PATH` | Path to a prompt text file. Repeatable; files are concatenated in order |
| `--prompt TEXT` | Inline prompt text. Repeatable; appended after `--prompt-file` content |

At least one of `--prompt-file` or `--prompt` is required. Typical usage loads a config file first, then provides the actual prompt:

```bash
./ComfyUIClient submit \
    --workflow workflows/api/W1\ \(diffusion\ based\).json \
    --prompt-file prompts/configs/w1-z_image_turbo_bf16.txt \
    --prompt "A cat sitting on a sofa, smoking a pipe"
```

### Workflow

| Option | Default | Description |
|--------|---------|-------------|
| `--workflow PATH` | `w1_workflow_api.json` | Path to the API-format workflow JSON |
| `--w1` | — | Shorthand: automatically selects the bundled W1 workflow |

### Connection

| Option | Default | Description |
|--------|---------|-------------|
| `--comfyui URL` | `http://127.0.0.1:8000` | Base URL of the ComfyUI instance |

### Image sizing

| Option | Default | Description |
|--------|---------|-------------|
| `--scale FACTOR` | `1.0` | Multiply both width and height by this factor. Applied after tag resolution |

Example: generate a quick preview at half resolution:

```bash
./ComfyUIClient submit ... --scale 0.5
```

### Parameter sweeps

| Option | Description |
|--------|-------------|
| `--range TAG=V1,V2,...` | Sweep one or more tag values. Repeatable; all combinations are submitted |

The `--range` option overrides tag values extracted from the prompt, generating one job per combination. The `@w1.` prefix is optional.

```bash
# Submit 6 jobs: 2 seeds × 3 step counts
./ComfyUIClient submit \
    --prompt-file prompts/configs/w1-z_image_turbo_bf16.txt \
    --prompt "A moonlit forest" \
    --range w1.seed=111,222 \
    --range w1.steps=5,9,15
```

### Metadata

| Option | Description |
|--------|-------------|
| `--keyword KW` | Keyword to embed in the image's XMP/IPTC metadata. Repeatable |

Keywords are written into the workflow's `Keywords` node and later extracted by the `set-metadata` command.

### Job control

| Option | Description |
|--------|-------------|
| `--no-wait` | Submit jobs without waiting for each to complete before sending the next |
| `--dry-run` | Resolve and print all tags and the final prompt without submitting anything |

`--dry-run` is useful for verifying tag resolution before committing to a long sweep:

```bash
./ComfyUIClient submit \
    --prompt-file prompts/configs/w1-z_image_turbo_bf16.txt \
    --prompt "A moonlit forest @w1.steps:5" \
    --dry-run
```

### Debugging

| Option | Description |
|--------|-------------|
| `--debug` | Enable verbose logging |

---

## Makefile Shortcuts

The `Makefile` provides convenience targets that wrap common `submit` invocations.

| Target | Description |
|--------|-------------|
| `make cat` | Submit a built-in test prompt (cat on a sofa) |
| `make moonlight` | Submit `prompts/moonlight.txt` |
| `make prompt PROMPT="..."` | Submit an inline prompt |
| `make ... fast` | Add `--scale 0.5 --range w1.steps=2` for a quick preview |
| `make ... dry-run` | Add `--dry-run` |

Example:

```bash
make prompt PROMPT="A stormy sea at night" fast dry-run
```