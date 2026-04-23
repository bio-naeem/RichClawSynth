#!/usr/bin/env python3
import pathlib
import subprocess
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[3]
SKILL_DIR = ROOT / "skills" / "claw-input-file-generator"
SCRIPTS_DIR = SKILL_DIR / "scripts"


class SkillContractTests(unittest.TestCase):
    def test_openai_prompt_mentions_explicit_outputs_and_verification(self):
        content = (SKILL_DIR / "agents" / "openai.yaml").read_text(encoding="utf-8")
        self.assertIn("explicit --output", content)
        self.assertIn("verify the files exist on disk", content)
        self.assertIn("tmp_output/", content)

    def test_skill_doc_mentions_tmp_output_and_dependency_reporting(self):
        content = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("tmp_output/", content)
        self.assertIn("report the exact missing prerequisite", content)
        self.assertIn("always pass the full output file path", content)

    def test_templates_doc_mentions_xlsx_sheet_names(self):
        content = (SKILL_DIR / "references" / "templates.md").read_text(encoding="utf-8")
        self.assertIn("sales`, `employees`, `inventory`", content)
        self.assertIn("cd scripts/edge-tts && npm install", content)

    def test_document_script_help_surface(self):
        result = subprocess.run(
            ["python3", str(SCRIPTS_DIR / "generate_document.py"), "--help"],
            capture_output=True,
            text=True,
            check=True,
            cwd=ROOT,
        )
        self.assertIn("{csv,xlsx,docx}", result.stdout)

    def test_pdf_script_help_surface(self):
        result = subprocess.run(
            ["python3", str(SCRIPTS_DIR / "generate_pdf.py"), "--help"],
            capture_output=True,
            text=True,
            check=True,
            cwd=ROOT,
        )
        self.assertIn("{backprop,report,custom}", result.stdout)

    def test_audio_script_help_surface(self):
        result = subprocess.run(
            ["python3", str(SCRIPTS_DIR / "generate_audio.py"), "--help"],
            capture_output=True,
            text=True,
            check=True,
            cwd=ROOT,
        )
        self.assertIn("{edge,gtts,auto}", result.stdout)

    def test_workspace_defaults_point_to_tmp_output(self):
        root_fragment = "tmp_output', 'claw-input-file-generator'"
        for script_name in [
            "generate_image.py",
            "generate_pdf.py",
            "generate_audio.py",
            "generate_document.py",
        ]:
            content = (SCRIPTS_DIR / script_name).read_text(encoding="utf-8")
            self.assertIn(root_fragment, content)

    def test_audio_engine_semantics_are_documented_in_code(self):
        content = (SCRIPTS_DIR / "generate_audio.py").read_text(encoding="utf-8")
        self.assertIn("Falling back to gTTS because --engine auto was requested.", content)
        self.assertNotIn('print("Falling back to gTTS...")', content)


if __name__ == "__main__":
    unittest.main()
