#!/usr/bin/env python3
"""Unit tests for orchestrator fail-closed helpers."""

from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from lib.matrix_poll import (
    _job_index_from_raw,
    _should_live_pull,
    format_progress_line,
    parse_log_hint,
    parse_logs_detail,
    parse_logs_status,
    status_is_blank,
)
from lib.pull_results import sku_has_results
from lib.ssh_remote import parse_ssh_url
from lib.vast import vast_cli_error


class VastCliErrorTests(unittest.TestCase):
    def test_raw_json_stderr(self) -> None:
        err = '{"error": true, "status_code": 400, "msg": "Invalid command given."}'
        self.assertIn("Invalid command", vast_cli_error("", err) or "")

    def test_human_stderr(self) -> None:
        err = "Failed with error 400: Team SSH keys are not supported."
        self.assertEqual(vast_cli_error("", err), err)

    def test_stopped_instance_stdout_json(self) -> None:
        out = (
            '{"success": false, "msg": '
            '"Execute command only avail on stopped instances. Use ssh to run commands on running VMs."}'
        )
        self.assertIn("stopped instances", vast_cli_error(out, "") or "")

    def test_progress_json_is_not_error(self) -> None:
        out = '{"phase": "onstart", "message": "bootstrap"}'
        self.assertIsNone(vast_cli_error(out, ""))

    def test_empty_is_not_error(self) -> None:
        self.assertIsNone(vast_cli_error("", ""))


class SshUrlTests(unittest.TestCase):
    def test_parse(self) -> None:
        user, host, port = parse_ssh_url("ssh://root@ssh9.vast.ai:15232")
        self.assertEqual((user, host, port), ("root", "ssh9.vast.ai", 15232))

    def test_rejects_http(self) -> None:
        with self.assertRaises(ValueError):
            parse_ssh_url("https://example.com")


class ProgressLineTests(unittest.TestCase):
    def test_blank_is_waiting(self) -> None:
        self.assertTrue(status_is_blank(""))
        self.assertTrue(status_is_blank("{}"))
        line = format_progress_line(1, "", 0, 100)
        self.assertIn("waiting", line)

    def test_progress_json(self) -> None:
        raw = '{"phase": "onstart", "message": "bootstrap"}'
        self.assertFalse(status_is_blank(raw))
        line = format_progress_line(1, raw, 12, 100)
        self.assertIn("onstart", line)
        self.assertIn("bootstrap", line)

    def test_unchanged_suffix(self) -> None:
        line = format_progress_line(
            1,
            "log=install pip_vllm",
            720,
            100,
            unchanged_sec=360,
        )
        self.assertIn("unchanged", line)
        self.assertIn("6m", line)

    def test_parse_logs_progress(self) -> None:
        logs = (
            "== bakeoff bootstrap ==\n"
            "[progress] onstart bootstrap\n"
            "[progress] matrix 2/14 flux2_dev/img01 timed\n"
            "BAKEOFF_DONE exit=0\n"
        )
        self.assertEqual(parse_logs_status(logs), "DONE:0")
        partial = parse_logs_status("[progress] prefetch 1/6 ideogram_4\n")
        self.assertTrue(partial.startswith("log="))
        self.assertIn("prefetch", partial)

    def test_parse_logs_detail_hint(self) -> None:
        logs = (
            "[progress] install pip_vllm\n"
            "  cloning ComfyUI-HunyuanImage-3\n"
            "  WARN: failed to clone ComfyUI-HunyuanImage-3\n"
        )
        status, hint = parse_logs_detail(logs)
        self.assertEqual(status, "log=install pip_vllm")
        self.assertIn("WARN", hint)

    def test_parse_log_hint(self) -> None:
        logs = "Cloning into '/workspace/ComfyUI'...\n"
        self.assertIn("Cloning", parse_log_hint(logs))

    def test_job_index_from_json(self) -> None:
        raw = '{"phase": "matrix", "job_index": 3, "stage": "done"}'
        self.assertEqual(_job_index_from_raw(raw), 3)

    def test_job_index_from_log(self) -> None:
        self.assertEqual(_job_index_from_raw("log=matrix 2/14 ideogram_4/img01 done"), 2)

    def test_should_live_pull_on_done(self) -> None:
        raw = '{"phase": "matrix", "job_index": 2, "stage": "done"}'
        should, new_idx = _should_live_pull(raw, 1)
        self.assertTrue(should)
        self.assertEqual(new_idx, 2)


class ArtifactTests(unittest.TestCase):
    def test_write_transcript(self) -> None:
        import sys

        remote = Path(__file__).resolve().parent / "remote"
        sys.path.insert(0, str(remote))
        import artifacts  # noqa: PLC0415
        from artifacts import write_transcript  # noqa: PLC0415

        with tempfile.TemporaryDirectory() as tmp:
            artifacts.ARTIFACTS_DIR = Path(tmp) / "artifacts"
            artifacts.REMOTE_ROOT = Path(tmp)
            rel = write_transcript("qwen38_27b", "llm_short", "hello world", None)
            self.assertTrue(rel.endswith("llm_short.txt"))
            self.assertTrue((Path(tmp) / rel).is_file())

    def test_sku_has_results(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sku_dir = root / "rtx5090_1x"
            sku_dir.mkdir()
            (sku_dir / "matrix.csv").write_text("a\n")
            import lib.pull_results as pr  # noqa: PLC0415

            pr.RESULTS = root
            self.assertTrue(sku_has_results("rtx5090_1x"))


class ReportGalleryTests(unittest.TestCase):
    def test_gallery_embeds_transcript(self) -> None:
        import sys

        remote = Path(__file__).resolve().parent / "remote"
        sys.path.insert(0, str(remote))
        from report import build_html  # noqa: PLC0415

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sku = root / "rtx5090_1x"
            art = sku / "artifacts" / "qwen38_27b"
            art.mkdir(parents=True)
            transcript = art / "llm_short.txt"
            transcript.write_text("stub response")
            csv_path = sku / "matrix.csv"
            with csv_path.open("w", newline="") as f:
                w = csv.DictWriter(
                    f,
                    fieldnames=["sku", "model", "prompt_id", "layer", "fit_status", "transcript_path"],
                )
                w.writeheader()
                w.writerow(
                    {
                        "sku": "rtx5090_1x",
                        "model": "qwen38_27b",
                        "prompt_id": "llm_short",
                        "layer": "A",
                        "fit_status": "Stub",
                        "transcript_path": "artifacts/qwen38_27b/llm_short.txt",
                    }
                )
            html_path = root / "report.html"
            with csv_path.open(newline="") as f:
                rows = list(csv.DictReader(f))
            build_html(rows, html_path, csv_path, root)
            text = html_path.read_text()
            self.assertIn("stub response", text)


class UploadPathTests(unittest.TestCase):
    def test_path_in_repo_strips_results_prefix(self) -> None:
        import sys

        remote = Path(__file__).resolve().parent / "remote"
        sys.path.insert(0, str(remote))
        from upload_results import MATRIX_CSV, path_in_repo  # noqa: PLC0415

        self.assertEqual(path_in_repo("rtx5090_1x", MATRIX_CSV), "rtx5090_1x/matrix.csv")


if __name__ == "__main__":
    unittest.main()
