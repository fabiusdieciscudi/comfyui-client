# ComfyUI Client

A command-line client for submitting image generation jobs to a [ComfyUI](https://github.com/comfyanonymous/ComfyUI) instance and managing the metadata of the generated images.

- [Overview](#overview)
- [Requirements](#requirements)
- [Installation](#installation)
- [Commands](#commands)
- [Quick Start](#quick-start)

---

## Overview

ComfyUI Client wraps the ComfyUI API with a prompt-centric workflow. Instead of editing workflow JSON files or using the ComfyUI web interface, you write plain text prompts and embed generation parameters directly in them as `@tags`. The client resolves the tags, patches the workflow, and submits the job.

After generation, a companion command reads the AI parameters that ComfyUI embeds in the output images and writes them as standard XMP/IPTC keywords, making every generation parameter — model, sampler, steps, seed, LoRA — searchable and browsable in any photo management application.

---

## Requirements

- Python 3.13
- `pip-tools` (installed automatically during setup)
- A running ComfyUI instance (local or remote)
- `exiftool` — required by the `set-metadata` command

On macOS:

```bash
brew install exiftool
```

On Debian/Ubuntu:

```bash
apt install libimage-exiftool-perl
```

---

## Installation

All setup is handled by the `Makefile`.

### First-time setup

Create the virtual environment, install dependencies, and install the package in editable mode:

```bash
make venv-prepare
```

This runs the following steps in order:

| Target              | Description                                                                |
|---------------------|----------------------------------------------------------------------------|
| `venv-clean`        | Remove any existing `.venv` directory                                      |
| `venv-init`         | Create a fresh virtual environment with `python3 -m venv`                  |
| `pip-install-tools` | Upgrade `pip` and install `pip-tools` and `pip-audit`                      |
| `pip-install`       | Install pinned dependencies from `requirements.txt` and the package itself |

### Updating dependencies

If you change `requirements.in`, regenerate the pinned lockfile:

```bash
make pip-compile
```

Then re-run installation:

```bash
make pip-install
```

### Security audit

Check all installed packages for known vulnerabilities:

```bash
make pip-audit
```

### Running a shell inside the virtual environment

```bash
make venv-bash
```

---

## Commands

| Command        | Description                                         | Documentation                                              |
|----------------|-----------------------------------------------------|------------------------------------------------------------|
| `submit`       | Submit a generation job to ComfyUI                  | [docs/README-submit.md](docs/README-submit.md)             |
| `set-metadata` | Write AI generation parameters as XMP/IPTC keywords | [docs/README-set-metadata.md](docs/README-set-metadata.md) |

Commands are invoked via the `ComfyUIClient` wrapper script, which activates the virtual environment automatically:

```bash
./ComfyUIClient <command> [options]
```

---

## Quick Start

**1. Submit a test image:**

```bash
./ComfyUIClient submit --w1 --prompt-file prompts/configs/w1-z_image_turbo_bf16.txt --prompt "A cat sitting on a sofa, smoking a pipe"
```

Or use the Makefile shortcut:

```bash
make cat
```

**2. Do a quick dry run to verify tag resolution before submitting:**

```bash
./ComfyUIClient submit --w1 --prompt-file prompts/configs/w1-z_image_turbo_bf16.txt --prompt "A moonlit forest @w1.steps:5" --dry-run
```

**3. Write metadata keywords to all images in today's output folder:**

```bash
./ComfyUIClient set-metadata build/output/2026-04-02/
```