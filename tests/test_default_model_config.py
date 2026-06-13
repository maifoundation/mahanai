from __future__ import annotations

import sys
import types
import unittest

dotenv = types.ModuleType("dotenv")
dotenv.load_dotenv = lambda *args, **kwargs: None
sys.modules.setdefault("dotenv", dotenv)

from mahanai.config import clear_default_model, load_default_model, save_default_model


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


if __name__ == "__main__":
    unittest.main()
