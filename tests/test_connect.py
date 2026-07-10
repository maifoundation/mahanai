from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mahanai.config import _read_config, _write_config


class ConfigDirMixin:
    def with_config_dir(self):
        return tempfile.TemporaryDirectory()

    def set_config_dir(self, path: str) -> str | None:
        old = os.environ.get("MAHANAI_CONFIG_DIR")
        os.environ["MAHANAI_CONFIG_DIR"] = path
        return old

    def restore_config_dir(self, old: str | None) -> None:
        if old is None:
            os.environ.pop("MAHANAI_CONFIG_DIR", None)
        else:
            os.environ["MAHANAI_CONFIG_DIR"] = old


class ConnectConfigTests(ConfigDirMixin, unittest.TestCase):
    def test_config_view_hides_secret_fields(self) -> None:
        from mahanai.connect import get_config_view

        with self.with_config_dir() as td:
            old = self.set_config_dir(td)
            try:
                _write_config(
                    {
                        "api_key": "sk-secret",
                        "nvidia_api_key": "nv-secret",
                        "codex_token": {"access_token": "codex-secret"},
                        "store_token": "store-secret",
                        "theme": "midnight",
                        "custom_endpoint": {
                            "url": "http://localhost:11434/v1",
                            "model": "local-model",
                            "api_key": "custom-secret",
                        },
                        "ollama_providers": {
                            "local": {
                                "name": "local",
                                "address": "localhost",
                                "port": 11434,
                                "api_key": "ollama-secret",
                            }
                        },
                    }
                )

                view = get_config_view()

                self.assertNotIn("api_key", view["config"])
                self.assertNotIn("nvidia_api_key", view["config"])
                self.assertNotIn("codex_token", view["config"])
                self.assertNotIn("store_token", view["config"])
                self.assertEqual(view["config"]["theme"], "midnight")
                self.assertEqual(
                    view["config"]["custom_endpoint"],
                    {"url": "http://localhost:11434/v1", "model": "local-model"},
                )
                self.assertEqual(
                    view["config"]["ollama_providers"]["local"],
                    {"name": "local", "address": "localhost", "port": 11434},
                )
            finally:
                self.restore_config_dir(old)

    def test_secret_mutation_is_rejected_before_approval(self) -> None:
        from mahanai.connect import request_config_change

        called = False

        def approve(_summary: dict) -> str:
            nonlocal called
            called = True
            return "allow-once"

        result = request_config_change({"api_key": "new-secret"}, approve=approve)

        self.assertEqual(result["error"], "blocked_config_field")
        self.assertEqual(result["blocked_fields"], ["api_key"])
        self.assertFalse(called)

    def test_allowed_non_secret_mutation_writes_after_approval(self) -> None:
        from mahanai.connect import request_config_change

        with self.with_config_dir() as td:
            old = self.set_config_dir(td)
            try:
                _write_config({"theme": "midnight"})

                result = request_config_change({"theme": "light"}, approve=lambda _summary: "allow-once")

                self.assertEqual(result, {"ok": True, "applied": ["theme"], "session_granted": False})
                self.assertEqual(_read_config()["theme"], "light")
            finally:
                self.restore_config_dir(old)

    def test_custom_endpoint_non_secret_change_preserves_existing_api_key(self) -> None:
        from mahanai.connect import request_config_change

        with self.with_config_dir() as td:
            old = self.set_config_dir(td)
            try:
                _write_config(
                    {
                        "custom_endpoint": {
                            "url": "https://old.example/v1",
                            "model": "old-model",
                            "api_key": "keep-secret",
                        }
                    }
                )

                result = request_config_change(
                    {"custom_endpoint": {"url": "https://new.example/v1", "model": "new-model"}},
                    approve=lambda _summary: "allow-once",
                )

                self.assertTrue(result["ok"])
                self.assertEqual(_read_config()["custom_endpoint"]["api_key"], "keep-secret")
                self.assertEqual(_read_config()["custom_endpoint"]["url"], "https://new.example/v1")
            finally:
                self.restore_config_dir(old)

    def test_unknown_config_fields_are_denied(self) -> None:
        from mahanai.connect import request_config_change

        result = request_config_change({"future_field": True}, approve=lambda _summary: "allow-once")

        self.assertEqual(result["error"], "blocked_config_field")
        self.assertEqual(result["blocked_fields"], ["future_field"])

    def test_nested_ollama_provider_secret_mutation_is_denied(self) -> None:
        from mahanai.connect import request_config_change

        result = request_config_change(
            {"ollama_providers": {"local": {"api_key": "new-secret"}}},
            approve=lambda _summary: "allow-once",
        )

        self.assertEqual(result["error"], "blocked_config_field")
        self.assertEqual(result["blocked_fields"], ["ollama_providers.local.api_key"])


class ConnectCommandTests(unittest.TestCase):
    def test_connect_command_denial_returns_user_denied(self) -> None:
        from mahanai.connect import clear_session_grants, run_user_command

        clear_session_grants()

        result = run_user_command(Path("."), {"command": "echo hello"}, approve=lambda _summary: "deny")

        self.assertEqual(result["error"], "user_denied")
        self.assertEqual(result["command"], "echo hello")

    def test_session_grant_bypasses_reapproval_for_safe_command(self) -> None:
        from mahanai.connect import clear_session_grants, grant_command_session, run_user_command

        clear_session_grants()
        grant_command_session()
        with patch("mahanai.connect.subprocess.run") as run_mock:
            run_mock.return_value.returncode = 0
            run_mock.return_value.stdout = "ok\n"
            run_mock.return_value.stderr = ""

            result = run_user_command(
                Path("."),
                {"command": "echo hello"},
                approve=lambda _summary: (_ for _ in ()).throw(AssertionError("approval should not run")),
            )

        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(result["stdout"], "ok\n")

    def test_pwd_returns_resolved_cwd_without_shelling_out(self) -> None:
        from mahanai.connect import clear_session_grants, run_user_command

        clear_session_grants()
        with patch("mahanai.connect.subprocess.run") as run_mock:
            result = run_user_command(
                Path("."),
                {"command": "pwd", "cwd": "tests"},
                approve=lambda _summary: (_ for _ in ()).throw(AssertionError("approval should not run")),
            )

        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(result["stdout"], f"{Path('tests').resolve()}\n")
        run_mock.assert_not_called()

    def test_high_risk_command_still_requires_per_action_approval(self) -> None:
        from mahanai.connect import clear_session_grants, grant_command_session, run_user_command

        clear_session_grants()
        grant_command_session()

        result = run_user_command(Path("."), {"command": "rm -rf /tmp/example"}, approve=lambda _summary: "deny")

        self.assertEqual(result["error"], "user_denied")
        self.assertTrue(result["high_risk"])


class ConnectToolTests(ConfigDirMixin, unittest.TestCase):
    def test_connect_tools_are_registered(self) -> None:
        from mahanai.tools import get_tools

        names = {tool["function"]["name"] for tool in get_tools()}

        self.assertTrue(
            {
                "connect_get_config_view",
                "connect_request_config_change",
                "connect_run_user_command",
                "connect_request_rerun",
            }.issubset(names)
        )

    def test_connect_get_config_view_dispatches(self) -> None:
        from mahanai.tools import execute_tool

        with self.with_config_dir() as td:
            old = self.set_config_dir(td)
            try:
                _write_config({"api_key": "secret", "theme": "light"})

                result = json.loads(execute_tool("connect_get_config_view", "{}", Path(".")))

                self.assertNotIn("api_key", result["config"])
                self.assertEqual(result["config"]["theme"], "light")
            finally:
                self.restore_config_dir(old)


class ConnectUiTests(unittest.TestCase):
    def test_rerun_payload_contains_reason_and_command(self) -> None:
        from mahanai.connect import request_rerun

        payload = request_rerun(
            {
                "reason": "need a new environment",
                "suggested_command": "mahanai --connect",
            }
        )

        self.assertEqual(payload["reason"], "need a new environment")
        self.assertIn("mahanai --connect", payload["message"])


if __name__ == "__main__":
    unittest.main()
