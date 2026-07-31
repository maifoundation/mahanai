from __future__ import annotations

import unittest

from mahanai import server


class ServerBehaviorTests(unittest.TestCase):
    def test_root_serves_embedded_web_ui(self) -> None:
        body = server._webui_bytes().decode("utf-8")

        self.assertIn("<title>MahanAI Max 3.0</title>", body)
        self.assertIn("MODEL_LABELS", body)

    def test_models_endpoint_uses_indirect_codex_suffixes(self) -> None:
        model_ids = {item["id"] for item in server._openai_model_data(None)}

        self.assertIn("gpt-5.4-indirect", model_ids)
        self.assertIn("gpt-5.2-codex-indirect", model_ids)
        self.assertNotIn("gpt-5.4", model_ids)
        self.assertNotIn("gpt-5.2-codex", model_ids)

    def test_models_endpoint_exposes_new_openai_models_indirectly(self) -> None:
        model_ids = {item["id"] for item in server._openai_model_data(None)}

        for model_id in (
            "gpt-5.5",
            "gpt-5.6-luna",
            "gpt-5.6-terra",
            "gpt-5.6-sol",
        ):
            indirect_id = f"{model_id}-indirect"
            self.assertIn(indirect_id, model_ids)
            self.assertEqual(("codex_direct", model_id), server._ROUTES[indirect_id])


if __name__ == "__main__":
    unittest.main()
