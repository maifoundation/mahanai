from __future__ import annotations

import os
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

dotenv = types.ModuleType("dotenv")
dotenv.load_dotenv = lambda *args, **kwargs: None
sys.modules.setdefault("dotenv", dotenv)

openai = types.ModuleType("openai")
openai.APIStatusError = RuntimeError
openai.OpenAI = object
sys.modules.setdefault("openai", openai)

from mahanai import agent, store


class StoreAuthTests(unittest.TestCase):
    def test_github_client_id_reads_environment(self) -> None:
        with patch.dict(os.environ, {"MAHANAI_GITHUB_CLIENT_ID": "abc123"}, clear=False):
            self.assertEqual(store.github_client_id(), "abc123")

    def test_github_device_login_saves_token_and_returns_username(self) -> None:
        with patch.dict(os.environ, {"MAHANAI_GITHUB_CLIENT_ID": "abc123"}, clear=False), \
             patch.object(store, "_request_device_code", return_value={
                 "device_code": "device-code",
                 "user_code": "USER-CODE",
                 "verification_uri": "https://github.com/login/device",
                 "verification_uri_complete": "https://github.com/login/device?user_code=USER-CODE",
                 "interval": 1,
             }), \
             patch.object(store, "_poll_device_access_token", return_value="gho_test_token"), \
             patch.object(store, "whoami", return_value="mahan"), \
             patch.object(store.webbrowser, "open") as open_browser:
            with tempfile.TemporaryDirectory() as td:
                with patch.dict(os.environ, {"MAHANAI_CONFIG_DIR": td}, clear=False):
                    username = store.github_device_login()
                    self.assertEqual(username, "mahan")
                    self.assertEqual(store.get_store_token(), "gho_test_token")
                    open_browser.assert_called_once()

    def test_onboarding_wizard_recommends_github_auth_with_default_yes(self) -> None:
        prompts = iter(["1", ""])
        with tempfile.TemporaryDirectory() as td:
            with patch.dict(os.environ, {"MAHANAI_CONFIG_DIR": td}, clear=False), \
                 patch.object(agent, "input", side_effect=lambda _: next(prompts)), \
                 patch.object(agent, "_run_github_store_login", return_value="mahan") as github_login:
                agent._run_onboarding_wizard()

        github_login.assert_called_once_with()

    def test_github_store_login_falls_back_to_pat_when_oauth_not_configured(self) -> None:
        prompts = iter(["ghp_test_token"])
        with tempfile.TemporaryDirectory() as td:
            with patch.dict(os.environ, {"MAHANAI_CONFIG_DIR": td}, clear=False), \
                 patch.dict(os.environ, {"MAHANAI_GITHUB_CLIENT_ID": ""}, clear=False), \
                 patch.object(agent, "input", side_effect=lambda _: next(prompts)), \
                 patch.object(store, "whoami", return_value="mahan"):
                username = agent._run_github_store_login()
                saved_token = store.get_store_token()

        self.assertEqual(username, "mahan")
        self.assertEqual(saved_token, "ghp_test_token")


if __name__ == "__main__":
    unittest.main()
