# CLAUDE.md

## Project

EncodeLab is a lightweight GUI video converter built on ffmpeg.

## Rules

- Use Python with type hints
- GUI must use PySide6
- Keep UI and core logic separated
- Avoid monolithic files
- Prefer small, testable functions
- Windows is the primary target
- Safety is critical: never overwrite original files by default

## Architecture

- src/encode_lab/ui: GUI code
- src/encode_lab/core: ffmpeg / ffprobe logic
- src/encode_lab/workers: background processing
- presets/: JSON-based presets
- docs/: planning and notes

## Coding Style

- Clear naming
- Minimal but useful comments
- Dataclasses for simple configuration models
- subprocess-compatible ffmpeg command generation