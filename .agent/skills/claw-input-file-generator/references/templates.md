# Input File Types And Command Matrix

This reference is the source of truth for selecting the generator, required arguments, and default naming patterns.

## Path Resolution

- Preserve user-provided relative or absolute paths exactly.
- If the query only names a filename, write it under `tmp_output/claw-input-file-generator/`.
- For image generation, pass the destination directory to `--output`.
- For PDF, audio, CSV, XLSX, and DOCX generation, pass the full file path to `--output`.

## Image Types

Generator: `scripts/generate_image.py`

| Query shape | `--type` | Output form | Typical filenames | Notes |
|---|---|---|---|---|
| Sales report images | `sales` | directory | `sales_q1_page1.jpg` to `sales_q1_page3.jpg` | `--count` is effectively capped at 3 |
| Supplier quote images | `quote` | directory | `supplier_quote_1.jpg` to `supplier_quote_5.jpg` | `--count` is effectively capped at 5 |
| Financial report images | `finance` | directory | `img1.png` to `img3.png` | `--count` is effectively capped at 3 |
| Blackboard photos | `blackboard` | directory | `board_1.jpg` to `board_3.jpg` | `--count` is effectively capped at 3 |
| Prescription photos | `prescription` | directory | `prescription_01.jpg` to `prescription_05.jpg` | `--count` is effectively capped at 5 |
| Complaint form | `complaint` | directory | `complaint_photo.jpg` | Generates a single file |

## PDF Types

Generator: `scripts/generate_pdf.py`

| Query shape | `--template` | Required flags | Default filename | Notes |
|---|---|---|---|---|
| Technical notes PDF | `backprop` | none | `notes/backprop_notes.pdf` | Use when the prompt implies algorithm notes |
| Project report PDF | `report` | none | `notes/project_report.pdf` | Short headings and bullet lists |
| Custom markdown PDF | `custom` | `--content` | `notes/custom_document.pdf` | `--content` is mandatory |

## Audio Types

Generator: `scripts/generate_audio.py`

| Query shape | Engine choice | Required flags | Default filename | Notes |
|---|---|---|---|---|
| Voice sample MP3 | `edge` or `auto` | `--text`, `--output` | `my_voice.mp3` | Prefer `edge` when the task explicitly wants bundled Edge TTS |
| Voice sample with fallback allowed | `auto` | `--text`, `--output` | `my_voice.mp3` | Tries Edge first, then `gTTS` |
| Voice alias discovery | n/a | `--list-voices` | none | Prints the bundled alias list only |

Bundled voice aliases:

- `female-narrator` -> `zh-CN-XiaoxiaoNeural`
- `female-assistant` -> `zh-CN-XiaoxiaoNeural`
- `female-chat` -> `zh-CN-XiaoxiaoNeural`
- `male-narrator` -> `zh-CN-YunyangNeural`
- `male-chat` -> `zh-CN-YunyangNeural`
- `male-documentary` -> `zh-CN-YunyangNeural`

## Document Types

Generator: `scripts/generate_document.py`

| File type | Required flags | Default filename | Notes |
|---|---|---|---|
| CSV | `--type csv`, optional `--data-type`, optional `--rows` | `sales_data.csv` | Data types: `sales`, `employees`, `inventory` |
| XLSX | `--type xlsx`, optional `--data-type`, optional `--rows`, optional `--sheets` | `sales_data.xlsx` | Multi-sheet order and names: `sales`, `employees`, `inventory` |
| DOCX | `--type docx`, optional `--doc-type` | `report.docx` | Doc types: `report`, `contract`, `letter` |

## Dependency Failure Policy

If generation fails because a dependency is missing, report the exact setup step instead of claiming success:

- Python packages: `pip3 install Pillow markdown weasyprint openpyxl python-docx gTTS`
- Bundled Edge TTS: `cd scripts/edge-tts && npm install`
