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
from lib.ssh_remote import (
    HARNESS_ROOT,
    HARNESS_RUN_MATRIX,
    HARNESS_START_SCRIPT,
    SshNotReadyError,
    is_ssh_auth_denied,
    is_ssh_retryable,
    parse_ssh_url,
    prepare_local_file_dest,
)
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


class SshRetryTests(unittest.TestCase):
    def test_retryable_auth_errors(self) -> None:
        self.assertTrue(is_ssh_retryable("root@host: Permission denied (publickey)."))
        self.assertTrue(is_ssh_retryable("ssh 48627407 failed: ssh exit 255"))
        self.assertTrue(is_ssh_retryable("Connection refused"))

    def test_non_retryable(self) -> None:
        self.assertFalse(is_ssh_retryable("bash: onstart.sh: No such file or directory"))

    def test_auth_denied_detection(self) -> None:
        self.assertTrue(is_ssh_auth_denied("root@host: Permission denied (publickey)."))
        self.assertFalse(is_ssh_auth_denied("Connection refused"))

    def test_ssh_not_ready_error(self) -> None:
        err = SshNotReadyError(12345, "ssh failed", auth_denied=True)
        self.assertEqual(err.instance_id, 12345)
        self.assertTrue(err.auth_denied)

    def test_harness_paths(self) -> None:
        self.assertEqual(HARNESS_ROOT, "/workspace/bakeoff")
        self.assertTrue(HARNESS_START_SCRIPT.endswith("start_matrix.sh"))
        self.assertTrue(HARNESS_RUN_MATRIX.endswith("run_matrix.py"))

    def test_verify_harness_raises_when_missing(self) -> None:
        from unittest.mock import patch

        from lib.ssh_remote import verify_harness

        with patch(
            "lib.ssh_remote.ssh_probe",
            return_value=(False, "", "ssh failed"),
        ):
            with self.assertRaises(RuntimeError) as ctx:
                verify_harness(99)
            self.assertIn("harness verify", str(ctx.exception))

    def test_verify_harness_ok(self) -> None:
        from unittest.mock import patch

        from lib.ssh_remote import verify_harness

        with patch(
            "lib.ssh_remote.ssh_probe",
            return_value=(True, "verified", ""),
        ):
            verify_harness(99)


class StartMatrixScriptTests(unittest.TestCase):
    def test_foreground_start_no_background_chmod(self) -> None:
        script = (Path(__file__).resolve().parent / "remote" / "start_matrix.sh").read_text()
        self.assertIn("nohup bash --noprofile --norc", script)
        self.assertIn("kill -0", script)
        self.assertIn("load_hf_env.sh", script)
        self.assertNotIn("setsid", script)
        self.assertNotIn("bash -lc", script)
        # chmod/mkdir must not be backgrounded (no "&" on those lines)
        for line in script.splitlines():
            stripped = line.strip()
            if stripped.startswith("chmod") or stripped.startswith("mkdir"):
                self.assertNotIn("&", stripped)


class HfEnvTests(unittest.TestCase):
    def test_remote_hf_env_requires_token(self) -> None:
        from unittest.mock import patch

        from lib.hf_env import remote_hf_env_bytes

        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(RuntimeError):
                remote_hf_env_bytes()

    def test_remote_hf_env_contents(self) -> None:
        from unittest.mock import patch

        from lib.hf_env import remote_hf_env_bytes

        with patch.dict(
            "os.environ",
            {"HF_TOKEN": "hf_test", "HF_RESULTS_REPO": "user/gpu-bakeoff-results"},
            clear=True,
        ):
            body = remote_hf_env_bytes().decode()
        self.assertIn("HF_TOKEN=hf_test", body)
        self.assertIn("HUGGING_FACE_HUB_TOKEN=hf_test", body)
        self.assertIn("HF_RESULTS_REPO=user/gpu-bakeoff-results", body)

    def test_remote_hf_auth_login_without_token(self) -> None:
        import sys
        from unittest.mock import patch

        remote = Path(__file__).resolve().parent / "remote"
        sys.path.insert(0, str(remote))
        try:
            import hf_auth

            with patch.dict("os.environ", {}, clear=True):
                self.assertFalse(hf_auth.login())
        finally:
            sys.path.remove(str(remote))


class PushHarnessTests(unittest.TestCase):
    def test_push_hf_env_requires_token(self) -> None:
        from unittest.mock import patch

        from lib.push_and_run import push_hf_env

        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(RuntimeError):
                push_hf_env(1)


class HarnessPresentTests(unittest.TestCase):
    def test_ssh_harness_cmd_checks_pid_and_progress(self) -> None:
        from unittest.mock import patch

        from lib.matrix_poll import (
            DONE_PATH,
            HARNESS_PID_PATH,
            PROGRESS_PATH,
            harness_present,
        )

        with (
            patch("lib.matrix_poll.use_onstart_transport", return_value=False),
            patch("lib.ssh_remote.ssh_run", return_value="no") as mock_ssh,
        ):
            self.assertFalse(harness_present(1))
            mock_ssh.assert_called_once()
            cmd = mock_ssh.call_args[0][1]
            self.assertIn(DONE_PATH, cmd)
            self.assertIn(PROGRESS_PATH, cmd)
            self.assertIn(HARNESS_PID_PATH, cmd)
            self.assertIn("kill -0", cmd)


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
            csv_path = sku_dir / "matrix.csv"
            import lib.pull_results as pr  # noqa: PLC0415

            pr.RESULTS = root

            with csv_path.open("w", newline="") as f:
                w = csv.DictWriter(
                    f,
                    fieldnames=["layer", "fit_status", "sku", "model", "runtime", "decode_tps"],
                )
                w.writeheader()
                w.writerow(
                    {
                        "layer": "A",
                        "fit_status": "Stub",
                        "sku": "rtx5090_1x",
                        "model": "qwen38_27b",
                        "runtime": "vllm",
                        "decode_tps": "0",
                    }
                )
            self.assertFalse(sku_has_results("rtx5090_1x"))

            with csv_path.open("w", newline="") as f:
                w = csv.DictWriter(
                    f,
                    fieldnames=["layer", "fit_status", "sku", "model", "runtime", "decode_tps"],
                )
                w.writeheader()
                w.writerow(
                    {
                        "layer": "A",
                        "fit_status": "No",
                        "sku": "rtx5090_1x",
                        "model": "qwen38_27b",
                        "runtime": "vllm",
                        "decode_tps": "0",
                    }
                )
            self.assertFalse(sku_has_results("rtx5090_1x"))

            with csv_path.open("w", newline="") as f:
                w = csv.DictWriter(
                    f,
                    fieldnames=["layer", "fit_status", "sku", "model", "runtime", "decode_tps"],
                )
                w.writeheader()
                w.writerow(
                    {
                        "layer": "A",
                        "fit_status": "Native",
                        "sku": "rtx5090_1x",
                        "model": "qwen38_27b",
                        "runtime": "vllm",
                        "decode_tps": "12.5",
                    }
                )
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


class SamplerSmiTests(unittest.TestCase):
    def test_na_fields_parse_as_zero(self) -> None:
        import sys

        remote = Path(__file__).resolve().parent / "remote"
        sys.path.insert(0, str(remote))
        from sampler import _parse_gpu_smi_row, _smi_float  # noqa: PLC0415

        self.assertEqual(_smi_float("[N/A]"), 0.0)
        self.assertEqual(_smi_float("N/A"), 0.0)
        self.assertEqual(_smi_float("[Not Supported]"), 0.0)
        row = _parse_gpu_smi_row(["0", "[N/A]", "N/A", "N/A"])
        assert row is not None
        self.assertEqual(row["vram_mib"], 0.0)
        self.assertEqual(row["power_w"], 0.0)
        self.assertEqual(row["temp_c"], 0.0)


class PrepareLocalFileDestTests(unittest.TestCase):
    def test_replaces_directory_with_file_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "run.log"
            dest.mkdir()
            prepared = prepare_local_file_dest(dest)
            self.assertFalse(prepared.is_dir())
            prepared.write_bytes(b"log")
            self.assertTrue(prepared.is_file())
            self.assertEqual(prepared.read_bytes(), b"log")


class ModelSpecTests(unittest.TestCase):
    def test_resolve_spark_gguf_vs_5090_vllm(self) -> None:
        import sys

        remote = Path(__file__).resolve().parent / "remote"
        sys.path.insert(0, str(remote))
        from model_spec import resolve_model_spec  # noqa: PLC0415

        base = {
            "runtime": "vllm",
            "hf_id": "Qwen/Qwen3.8-27B",
            "layer_a": {"precision": "nvfp4", "checkpoint": "RadixArk/Qwen3.8-27B-NVFP4"},
            "sku_layers": {
                "dgx_spark_gb10": {
                    "runtime": "llama_cpp",
                    "hf_id": "bowmanslayer/Qwen3.8-27B-GGUF",
                    "layer_a": {
                        "precision": "q4_k_m",
                        "file_hint": "Qwen3.8-27B-Text-Only-Q4_K_M.gguf",
                    },
                },
            },
        }
        spark = resolve_model_spec(base, "dgx_spark_gb10")
        rtx = resolve_model_spec(base, "rtx5090_1x")
        self.assertEqual(spark["runtime"], "llama_cpp")
        self.assertEqual(spark["layer_a"]["file_hint"], "Qwen3.8-27B-Text-Only-Q4_K_M.gguf")
        self.assertEqual(rtx["runtime"], "vllm")
        self.assertEqual(rtx["layer_a"]["checkpoint"], "RadixArk/Qwen3.8-27B-NVFP4")

    def test_bakeoff_models_filter_job_total(self) -> None:
        import os
        import sys

        remote = Path(__file__).resolve().parent / "remote"
        sys.path.insert(0, str(remote))
        from model_spec import compute_job_total  # noqa: PLC0415

        os.environ["BAKEOFF_MODELS"] = "qwen38_27b"
        matrix = {
            "prompts": {
                "image": [{"id": "img01"}],
                "video": [{"id": "vid01"}],
                "llm": {"short": {"id": "llm_short"}, "long": {"id": "llm_long"}},
            },
        }
        models = {
            "qwen38_27b": {"runtime": "vllm", "hf_id": "Qwen/Qwen3.8-27B", "layer_a": {"precision": "nvfp4"}},
        }
        self.assertEqual(compute_job_total(models, matrix, "rtx5090_1x"), 2)
        del os.environ["BAKEOFF_MODELS"]


class PresetEnvTests(unittest.TestCase):
    def test_preset_overwrites_env(self) -> None:
        import os

        from lib.presets import apply_preset

        os.environ["MIN_CREDIT_USD"] = "50"
        os.environ["MATRIX_TIMEOUT_SEC"] = "28800"
        preset = apply_preset("qwen-spark-5090")
        for key, val in preset.get("env", {}).items():
            os.environ[key] = val
        self.assertEqual(os.environ["MIN_CREDIT_USD"], "15")
        self.assertEqual(os.environ["MATRIX_TIMEOUT_SEC"], "7200")
        self.assertEqual(os.environ.get("INSTALL_LLAMA_TIMEOUT_SEC"), "1800")
        self.assertIn("qwen38_27b", preset["only_model"])


class MatrixEvidenceTests(unittest.TestCase):
    def test_has_evidence_and_stub_only(self) -> None:
        from lib.matrix_evidence import has_evidence, is_stub_only, read_matrix_rows

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "matrix.csv"
            with path.open("w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["layer", "fit_status"])
                w.writeheader()
                w.writerow({"layer": "A", "fit_status": "Stub"})
                w.writerow({"layer": "A", "fit_status": "Stub"})
            rows = read_matrix_rows(path)
            self.assertFalse(has_evidence(rows))
            self.assertTrue(is_stub_only(rows))

            with path.open("w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["layer", "fit_status"])
                w.writeheader()
                w.writerow({"layer": "A", "fit_status": "Native"})
            rows = read_matrix_rows(path)
            self.assertTrue(has_evidence(rows))
            self.assertFalse(is_stub_only(rows))

    def test_success_vs_no_rows(self) -> None:
        from lib.matrix_evidence import (
            has_evidence,
            has_success_evidence,
            read_matrix_rows,
            verify_sku_success,
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sku_dir = root / "rtx5090_1x"
            sku_dir.mkdir()
            path = sku_dir / "matrix.csv"
            with path.open("w", newline="") as f:
                w = csv.DictWriter(
                    f,
                    fieldnames=["layer", "fit_status", "runtime", "decode_tps"],
                )
                w.writeheader()
                w.writerow(
                    {
                        "layer": "A",
                        "fit_status": "No",
                        "runtime": "vllm",
                        "decode_tps": "0",
                    }
                )
            rows = read_matrix_rows(path)
            self.assertTrue(has_evidence(rows))
            self.assertFalse(has_success_evidence(rows))
            self.assertFalse(verify_sku_success(root, "rtx5090_1x"))

            with path.open("w", newline="") as f:
                w = csv.DictWriter(
                    f,
                    fieldnames=["layer", "fit_status", "runtime", "decode_tps"],
                )
                w.writeheader()
                w.writerow(
                    {
                        "layer": "A",
                        "fit_status": "Native",
                        "runtime": "vllm",
                        "decode_tps": "8.2",
                    }
                )
            self.assertTrue(verify_sku_success(root, "rtx5090_1x"))


class ComfyFailFastTests(unittest.TestCase):
    def test_comfy_timeout_returns_error_not_stub(self) -> None:
        import sys

        remote = Path(__file__).resolve().parent / "remote"
        sys.path.insert(0, str(remote))
        from comfy_client import _comfy_start_error  # noqa: PLC0415

        result = _comfy_start_error("flux2_dev", 42)
        self.assertEqual(result["status"], "error")
        self.assertFalse(result.get("pass", True))
        self.assertNotEqual(result.get("mode"), "gpu_stub")

    def test_classify_fit_maps_error_to_no(self) -> None:
        import sys

        remote = Path(__file__).resolve().parent / "remote"
        sys.path.insert(0, str(remote))
        from run_matrix import classify_fit  # noqa: PLC0415

        self.assertEqual(classify_fit("error", {}, {}, "image", {}), "No")


class LlmClientTests(unittest.TestCase):
    def test_vllm_start_failure_returns_error(self) -> None:
        import sys
        from unittest.mock import patch

        remote = Path(__file__).resolve().parent / "remote"
        sys.path.insert(0, str(remote))
        from llm_client import run_llm_job  # noqa: PLC0415

        with patch("llm_client.start_vllm", return_value=False):
            out = run_llm_job("vllm", "model", "sys", "user", max_tokens=32)
        self.assertFalse(out["pass"])
        self.assertEqual(out["status"], "error")


class ResumeMatrixTests(unittest.TestCase):
    def test_resume_matrix_triggers_push_and_run(self) -> None:
        from unittest.mock import patch

        from lib.bakeoff import run_one_sku

        rec = {"instance_id": 99999, "sku_id": "rtx5090_1x"}
        offers: dict = {"skus": {}}
        sku_meta: dict = {}

        with (
            patch("lib.bakeoff.use_onstart_transport", return_value=False),
            patch("lib.bakeoff.wait_for_matrix", return_value="done"),
            patch("lib.bakeoff.pull_sku"),
            patch("lib.bakeoff.verify_sku_success", return_value=True),
            patch("lib.bakeoff.destroy_instance") as destroy,
            patch("lib.bakeoff.push_and_run") as push,
        ):
            ok, _ = run_one_sku(
                "rtx5090_1x",
                rec,
                offers,
                sku_meta,
                mode="resume_matrix",
            )
        self.assertTrue(ok)
        push.assert_called_once_with(99999, "rtx5090_1x", force=False)
        destroy.assert_called_once()

    def test_stub_only_matrix_keeps_instance(self) -> None:
        from unittest.mock import patch

        from lib.bakeoff import run_one_sku

        rec = {"instance_id": 99999, "sku_id": "rtx5090_1x"}
        offers: dict = {"skus": {}}
        sku_meta: dict = {}

        with (
            patch("lib.bakeoff.use_onstart_transport", return_value=False),
            patch("lib.bakeoff.push_and_run"),
            patch("lib.bakeoff.wait_for_matrix", return_value="done"),
            patch("lib.bakeoff.pull_sku"),
            patch("lib.bakeoff.verify_sku_success", return_value=False),
            patch("lib.bakeoff.sku_failure_reason", return_value="all jobs failed (fit_status=No)"),
            patch("lib.bakeoff.pull_service_logs_best_effort"),
            patch("lib.bakeoff.destroy_instance") as destroy,
        ):
            ok, out = run_one_sku(
                "rtx5090_1x",
                rec,
                offers,
                sku_meta,
                mode="push_and_run",
            )
        self.assertFalse(ok)
        self.assertIn("failed", out.get("error", ""))
        destroy.assert_not_called()


if __name__ == "__main__":
    unittest.main()
