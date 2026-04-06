# ComfyUI Client — `set-metadata` Command

The `set-metadata` command reads AI generation parameters embedded in ComfyUI output images and writes them as standard photo metadata — XMP Subject, IPTC Keywords, XMP hierarchical subjects, and/or XMP/IPTC description fields. This makes generation parameters searchable and browsable in any photo management application that supports keyword hierarchies (Lightroom, Capture One, digiKam, etc.).

- [How It Works](#how-it-works)
- [Operations](#operations)
- [Keyword Structure](#keyword-structure)
- [User Keywords](#user-keywords)
- [Prompt-to-Description](#prompt-to-description)
- [Supported Formats](#supported-formats)
- [Command-Line Reference](#command-line-reference)
- [Requirements](#requirements)

---

## How It Works

ComfyUI embeds generation metadata directly into output image files. The `set-metadata` command reads this metadata, extracts the relevant nodes that were resolved during generation, and writes the requested information back into the image as structured photo metadata.

Two metadata formats are supported:

- **Prompt format** (current): the `Prompt` EXIF field contains a JSON object mapping node IDs to node definitions. This is the format produced by the W1 workflow.
- **Workflow format** (legacy): the `Workflow` EXIF field contains the full ComfyUI UI workflow JSON. Supported for retro-compatibility with older images.

The command processes a single file or an entire directory tree recursively. Files are modified in place; originals are not kept.

At least one operation flag must be supplied. Without any flag the command exits immediately with a usage message.

---

## Operations

The command is controlled by four flags. Multiple flags can be combined freely; `--all` is a convenience shorthand for all three explicit flags.

| Flag                      | Description                                                                           |
|---------------------------|---------------------------------------------------------------------------------------|
| `--tags`                  | Write AI generation parameters (`Tag: w1.*` nodes) as XMP/IPTC keyword hierarchies    |
| `--keywords`              | Write user-supplied keywords (from the `Keywords` workflow node) as XMP/IPTC keywords |
| `--prompt-to-description` | Copy the generation prompt to `XMP:Description` and `IPTC:Caption-Abstract`           |
| `--all`                   | Enable `--tags`, `--keywords`, and `--prompt-to-description`                          |

All three operations that are enabled share a single `exiftool` call per file, so the file is only written once regardless of how many flags are set.

---

## Keyword Structure

Each `Tag: w1.<param>` node found in the image metadata produces two flat keywords and one hierarchical subject (only when `--tags` is active).

Given a tag `w1.steps` with value `9`:

| Type                 | Value                                                                 |
|----------------------|-----------------------------------------------------------------------|
| Flat parent keyword  | `ai:parameters:w1.steps`                                              |
| Flat child keyword   | `ai:parameters:w1.steps#9`                                            |
| Hierarchical subject | `AI\|ai:parameters\|ai:parameters:w1.steps\|ai:parameters:w1.steps#9` |

The hierarchical subject creates a four-level tree in applications that display keyword hierarchies:

```
AI
└── ai:parameters
    └── ai:parameters:w1.steps
        └── ai:parameters:w1.steps#9
```

Both the parent and child flat keywords are written, allowing filtering either by parameter name alone (all images that have a `steps` tag, regardless of value) or by exact value.

All three forms are written to:
- `XMP:Subject`
- `IPTC:Keywords`
- `XMP-lr:HierarchicalSubject`

---

## User Keywords

When `--keywords` is active, the `Keywords` node in the workflow can carry user-supplied keywords set via the `--keyword` option of the `submit` command.

User keywords are written as-is if they contain no `|` character, or as hierarchical subjects if they do:

| Keyword value           | Written as                                         |
|-------------------------|----------------------------------------------------|
| `portrait`              | flat keyword in XMP:Subject and IPTC:Keywords      |
| `Style\|painterly\|oil` | hierarchical subject in XMP-lr:HierarchicalSubject |

This allows user keywords to participate in the same hierarchy tree as AI parameter keywords.

---

## Prompt-to-Description

When `--prompt-to-description` is active, the text from the `Prompt` workflow node is written to:
- `XMP:Description`
- `IPTC:Caption-Abstract`

`@tag` directives (e.g. `@w1.steps:9`) are stripped from the text before writing, so the description contains only the human-readable prompt. Excess blank lines are collapsed.

If no prompt node is found in the image metadata, this operation is skipped with a warning; other enabled operations still proceed normally.

---

## Supported Formats

| Extension        | Supported        |
|------------------|------------------|
| `.png`           | Yes              |
| `.jpg` / `.jpeg` | Yes              |
| All others       | Skipped silently |

---

## Command-Line Reference

```
ComfyUIClient set-metadata [--tags] [--keywords] [--prompt-to-description] [--all] [target]
```

### Arguments

| Argument | Default                 | Description                        |
|----------|-------------------------|------------------------------------|
| `target` | `.` (current directory) | Image file or directory to process |

When `target` is a directory, all files are processed recursively in sorted order. Non-image files are skipped silently.

### Options

| Option                    | Description                                                         |
|---------------------------|---------------------------------------------------------------------|
| `--tags`                  | Write AI generation parameters as XMP/IPTC keyword hierarchies      |
| `--keywords`              | Write user-supplied keywords as XMP/IPTC keywords                   |
| `--prompt-to-description` | Copy the prompt to XMP:Description and IPTC:Caption-Abstract        |
| `--all`                   | Enable all three operations above                                   |
| `--debug`                 | Enable verbose logging, including the full `exiftool` command lines |

At least one of `--tags`, `--keywords`, `--prompt-to-description`, or `--all` must be specified.

### Examples

Write only AI parameter keywords for a single image:

```bash
ComfyUIClient set-metadata --tags 'build/output/2026-04-02/2026-04-02 14-32-00001.png'
```

Write user keywords and copy the prompt to the description for all images in a folder:

```bash
ComfyUIClient set-metadata --keywords --prompt-to-description build/output/2026-04-02/
```

Do everything in one pass across the full output tree:

```bash
ComfyUIClient set-metadata --all build/output/
```

---

## Requirements

The `set-metadata` command shells out to `exiftool` for all metadata reading and writing. It must be installed and available on `PATH`.

On macOS:

```bash
brew install exiftool
```

On Debian/Ubuntu:

```bash
apt install libimage-exiftool-perl
```