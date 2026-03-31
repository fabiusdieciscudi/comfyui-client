# ComfyUI Client — `set-metadata` Command

The `set-metadata` command reads AI generation parameters embedded in ComfyUI output images and writes them as standard photo metadata — XMP Subject, IPTC Keywords, and XMP hierarchical subjects. This makes generation parameters searchable and browsable in any photo management application that supports keyword hierarchies (Lightroom, Capture One, digiKam, etc.).

- [How It Works](#how-it-works)
- [Keyword Structure](#keyword-structure)
- [User Keywords](#user-keywords)
- [Supported Formats](#supported-formats)
- [Command-Line Reference](#command-line-reference)
- [Requirements](#requirements)

---

## How It Works

ComfyUI embeds generation metadata directly into output image files. The `set-metadata` command reads this metadata, extracts the `Tag: w1.*` nodes that were resolved during generation, and writes them back into the image as structured photo keywords.

Two metadata formats are supported:

- **Prompt format** (current): the `Prompt` EXIF field contains a JSON object mapping node IDs to node definitions. This is the format produced by the W1 workflow.
- **Workflow format** (legacy): the `Workflow` EXIF field contains the full ComfyUI UI workflow JSON. Supported for retro-compatibility with older images.

The command processes a single file or an entire directory tree recursively. Files are modified in place; originals are not kept.

---

## Keyword Structure

Each `Tag: w1.<param>` node found in the image metadata produces two flat keywords and one hierarchical subject.

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

In addition to the automatically generated `Tag: w1.*` keywords, the `Keywords` node in the workflow can carry user-supplied keywords set via the `--keyword` option of the `submit` command.

User keywords are written as-is if they contain no `|` character, or as hierarchical subjects if they do:

| Keyword value           | Written as                                         |
|-------------------------|----------------------------------------------------|
| `portrait`              | flat keyword in XMP:Subject and IPTC:Keywords      |
| `Style\|painterly\|oil` | hierarchical subject in XMP-lr:HierarchicalSubject |

This allows user keywords to participate in the same hierarchy tree as AI parameter keywords.

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
ComfyUIClient set-metadata [target]
```

### Arguments

| Argument | Default                 | Description                        |
|----------|-------------------------|------------------------------------|
| `target` | `.` (current directory) | Image file or directory to process |

When `target` is a directory, all files are processed recursively in sorted order. Non-image files are skipped silently.

### Examples

Process a single image:

```bash
./ComfyUIClient set-metadata build/output/2026-04-02/W1\ 2026-04-02\ 14-32F00001.png
```

Process all images in a dated output folder:

```bash
./ComfyUIClient set-metadata build/output/2026-04-02/
```

Process everything in the output tree:

```bash
./ComfyUIClient set-metadata build/output/
```

### Options

| Option    | Description                                                         |
|-----------|---------------------------------------------------------------------|
| `--debug` | Enable verbose logging, including the full `exiftool` command lines |

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