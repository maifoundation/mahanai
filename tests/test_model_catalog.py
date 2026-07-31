from __future__ import annotations

import unittest

from mahanai import agent


class ModelCatalogTests(unittest.TestCase):
    def test_new_openai_models_are_available_directly_and_indirectly(self) -> None:
        models = {item["name"]: item for item in agent.AVAILABLE_MODELS}

        for model_id in (
            "gpt-5.5",
            "gpt-5.6-luna",
            "gpt-5.6-terra",
            "gpt-5.6-sol",
        ):
            self.assertEqual("codex_direct", models[model_id]["mode"])
            self.assertEqual("OpenAI Codex (Direct)", models[model_id]["group"])

            indirect_id = f"{model_id}-indirect"
            self.assertEqual("codex_indirect", models[indirect_id]["mode"])
            self.assertEqual("OpenAI Codex (Indirect)", models[indirect_id]["group"])


if __name__ == "__main__":
    unittest.main()
