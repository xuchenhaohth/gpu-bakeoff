#!/usr/bin/env python3
"""Unit tests for orchestrator fail-closed helpers."""

from __future__ import annotations

import unittest

from lib.matrix_poll import format_progress_line, status_is_blank
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
            '"Execute command only avail on stopped instances. Use ssh to run commands on running instances."}'
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


if __name__ == "__main__":
    unittest.main()
