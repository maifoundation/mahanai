from __future__ import annotations

import sys
import types
import unittest

dotenv = types.ModuleType("dotenv")
dotenv.load_dotenv = lambda *args, **kwargs: None
sys.modules.setdefault("dotenv", dotenv)

from mahanai.config import (
    load_interact_always_allow,
    load_interact_enabled,
    save_interact_always_allow,
    save_interact_enabled,
)


class InteractConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self._old_dir = sys.modules.get("mahanai.config")

    def test_interact_flag_round_trip(self) -> None:
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as td:
            import os

            old = os.environ.get("MAHANAI_CONFIG_DIR")
            os.environ["MAHANAI_CONFIG_DIR"] = td
            try:
                self.assertFalse(load_interact_enabled())
                save_interact_enabled(True)
                self.assertTrue(load_interact_enabled())
                self.assertFalse(load_interact_always_allow())
                save_interact_always_allow(True)
                self.assertTrue(load_interact_always_allow())
                save_interact_enabled(False)
                save_interact_always_allow(False)
                self.assertFalse(load_interact_enabled())
                self.assertFalse(load_interact_always_allow())
            finally:
                if old is None:
                    os.environ.pop("MAHANAI_CONFIG_DIR", None)
                else:
                    os.environ["MAHANAI_CONFIG_DIR"] = old


if __name__ == "__main__":
    unittest.main()
