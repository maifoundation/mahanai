from __future__ import annotations

import sys
import os
import tempfile
import types
import unittest
from unittest.mock import patch

dotenv = types.ModuleType("dotenv")
dotenv.load_dotenv = lambda *args, **kwargs: None
sys.modules.setdefault("dotenv", dotenv)

from mahanai.config import clear_default_model, load_default_model, save_default_model
from mahanai import agent


class DefaultModelConfigTests(unittest.TestCase):
    def test_default_model_round_trip(self) -> None:
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            old = os.environ.get("MAHANAI_CONFIG_DIR")
            os.environ["MAHANAI_CONFIG_DIR"] = td
            try:
                self.assertIsNone(load_default_model())

                save_default_model("claude-sonnet-4-6")
                self.assertEqual(load_default_model(), "claude-sonnet-4-6")

                clear_default_model()
                self.assertIsNone(load_default_model())
            finally:
                if old is None:
                    os.environ.pop("MAHANAI_CONFIG_DIR", None)
                else:
                    os.environ["MAHANAI_CONFIG_DIR"] = old

    def test_set_default_model_selector_persists_choice(self) -> None:
        selected_idx = agent._model_index_for_name("gpt-5.4-indirect")
        assert selected_idx is not None

        with tempfile.TemporaryDirectory() as td, patch.dict(
            os.environ, {"MAHANAI_CONFIG_DIR": td}
        ), patch.object(agent, "_model_selector", return_value=selected_idx):
            chosen = agent._select_and_save_default_model()

            self.assertEqual("gpt-5.4-indirect", load_default_model())
            self.assertEqual("gpt-5.4-indirect", chosen["name"] if chosen else None)

    def test_set_default_model_selector_cancel_keeps_saved_default(self) -> None:
        with tempfile.TemporaryDirectory() as td, patch.dict(
            os.environ, {"MAHANAI_CONFIG_DIR": td}
        ):
            save_default_model("claude-sonnet-4-6")
            with patch.object(agent, "_model_selector", return_value=None):
                chosen = agent._select_and_save_default_model()

            self.assertIsNone(chosen)
            self.assertEqual("claude-sonnet-4-6", load_default_model())


if __name__ == "__main__":
    unittest.main()
