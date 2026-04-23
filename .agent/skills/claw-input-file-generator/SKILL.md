---
name: claw-input-file-generator
description: "Generate input files for benchmark or tool-use queries. Use when Codex needs to create pre-existing files for OCR, extraction, recognition, speech, spreadsheet, Word, or PDF workflows, especially when the query assumes files already exist at concrete paths such as `workspace里的xxx.jpg`, `./notes/xxx.pdf`, `sales_data.csv`, or `my_voice.mp3`."
---

# Claw Input File Generator

Generate the input artifacts a query expects to already exist.

## Required Workflow

Follow this sequence every time:

1. Extract every required file path, filename, extension, and count from the query.
2. Choose the generator from the target file class, not from the downstream task.
3. Prefer explicit output paths. Preserve user-provided relative paths exactly when present.
4. If the query does not specify a path, write under `tmp_output/` in the workspace.
5. Run the generator with explicit `--output` values instead of relying on script defaults.
6. Verify the expected files exist on disk before declaring success.
7. If generation is blocked by missing dependencies, report the exact missing prerequisite and the exact setup command below. Do not claim the file was created.

## Set Up

Check runtimes:

```bash
python3 --version
node --version
npm --version
```

Install Python packages:

```bash
pip3 install Pillow markdown weasyprint openpyxl python-docx gTTS
```

Install bundled Edge TTS dependencies:

```bash
cd scripts/edge-tts && npm install
```

`weasyprint` may also require system libraries and fonts.

## Choose The Generator

Map the requested file class to the generator deterministically:

- Image OCR-style inputs like `.jpg` or `.png` -> `scripts/generate_image.py`
- `.pdf` -> `scripts/generate_pdf.py`
- `.mp3` or voice sample inputs -> `scripts/generate_audio.py`
- `.csv`, `.xlsx`, `.docx` -> `scripts/generate_document.py`

Read [references/templates.md](references/templates.md) for the supported types, required flags, and naming patterns.

## Path Rules

- If the query names a concrete path like `./notes/project_report.pdf`, preserve it.
- If the query names only a filename like `my_voice.mp3`, place it under `tmp_output/` unless the surrounding prompt establishes another directory.
- For image generation, pass the containing directory to `--output`, because the script writes one or more fixed filenames inside that directory.
- For single-file generators, always pass the full output file path with `--output`.
- Treat script defaults as fallback only. Do not rely on them when you can provide an explicit path.

## Command Patterns

Use commands shaped like these:

```bash
python3 scripts/generate_image.py --type complaint --output /path/to/workspace/tmp_output/claw-input-file-generator
python3 scripts/generate_image.py --type sales --count 3 --output /path/to/workspace/tmp_output/claw-input-file-generator
python3 scripts/generate_pdf.py --template report --output /path/to/workspace/tmp_output/claw-input-file-generator/notes/project_report.pdf
python3 scripts/generate_pdf.py --template custom --content "# Title" --output /path/to/workspace/tmp_output/claw-input-file-generator/notes/custom_document.pdf
python3 scripts/generate_audio.py --text "这是我的声音样本" --engine edge --output /path/to/workspace/tmp_output/claw-input-file-generator/my_voice.mp3
python3 scripts/generate_document.py --type csv --data-type sales --rows 50 --output /path/to/workspace/tmp_output/claw-input-file-generator/sales_data.csv
python3 scripts/generate_document.py --type xlsx --data-type sales --rows 100 --sheets 3 --output /path/to/workspace/tmp_output/claw-input-file-generator/report.xlsx
python3 scripts/generate_document.py --type docx --doc-type report --output /path/to/workspace/tmp_output/claw-input-file-generator/report.docx
```

## Important Behavior

- `generate_pdf.py --template custom` requires `--content`.
- `generate_document.py --type xlsx --sheets N` uses the fixed sheet order and sheet names `sales`, `employees`, `inventory`.
- `generate_audio.py --engine edge` is strict. If Edge TTS is unavailable, treat it as a failure.
- `generate_audio.py --engine auto` tries bundled Edge TTS first and only then falls back to `gTTS`.
- `generate_audio.py --list-voices` prints the skill's bundled alias list, not the full Edge catalog.
- Generated files are inputs only. This skill does not perform downstream analysis.

## Verification

Confirm the expected file or files exist at the exact paths implied by the query:

- For image batches, check the required filenames inside the requested directory.
- For single-file outputs, check the exact `--output` path.
- Do not trust stdout alone. Success means the file exists on disk.

If verification fails, report the missing path and stop.
