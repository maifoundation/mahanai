from __future__ import annotations

import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

_CONFIG_DIR = tempfile.TemporaryDirectory()
_HOME_DIR = tempfile.TemporaryDirectory()
os.environ["MAHANAI_CONFIG_DIR"] = _CONFIG_DIR.name
os.environ["USERPROFILE"] = _HOME_DIR.name
os.environ["HOME"] = _HOME_DIR.name

from mahanai import agent


class ApiCliTests(unittest.TestCase):
    def test_api_mode_requires_explicit_model(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()

        exit_code = agent._run_api_mode(
            model_name=None,
            query="hello",
            small=False,
            stream=False,
            workspace=Path("."),
            stdout=stdout,
            stderr=stderr,
        )

        self.assertNotEqual(exit_code, 0)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("--model", stderr.getvalue())

    def test_api_mode_rejects_unknown_model(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()

        exit_code = agent._run_api_mode(
            model_name="not-a-real-model",
            query="hello",
            small=False,
            stream=False,
            workspace=Path("."),
            stdout=stdout,
            stderr=stderr,
        )

        self.assertNotEqual(exit_code, 0)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("Unknown model", stderr.getvalue())

    def test_api_mode_prints_only_answer_text_on_success(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()

        with patch("mahanai.agent._run_api_request", return_value="plain answer") as run_mock:
            exit_code = agent._run_api_mode(
                model_name="meta/llama-3.3-70b-instruct",
                query="hello",
                small=False,
                stream=False,
                workspace=Path("."),
                stdout=stdout,
                stderr=stderr,
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout.getvalue(), "plain answer")
        self.assertEqual(stderr.getvalue(), "")
        run_mock.assert_called_once()

    def test_api_mode_small_adds_concise_instruction(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()

        with patch("mahanai.agent._run_api_request", return_value="tiny answer") as run_mock:
            exit_code = agent._run_api_mode(
                model_name="meta/llama-3.3-70b-instruct",
                query="hello",
                small=True,
                stream=False,
                workspace=Path("."),
                stdout=stdout,
                stderr=stderr,
            )

        self.assertEqual(exit_code, 0)
        prompt = run_mock.call_args.kwargs["prompt"]
        self.assertIn("Keep the answer very short", prompt)
        self.assertTrue(prompt.endswith("hello"))

    def test_api_mode_streaming_writes_to_stdout_without_extra_text(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()

        def fake_run_api_request(**kwargs: object) -> str:
            out = kwargs["stdout"]
            assert isinstance(out, io.StringIO)
            out.write("streamed ")
            out.write("answer")
            return "streamed answer"

        with patch("mahanai.agent._run_api_request", side_effect=fake_run_api_request) as run_mock:
            exit_code = agent._run_api_mode(
                model_name="meta/llama-3.3-70b-instruct",
                query="hello",
                small=False,
                stream=True,
                workspace=Path("."),
                stdout=stdout,
                stderr=stderr,
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout.getvalue(), "streamed answer")
        self.assertEqual(stderr.getvalue(), "")
        self.assertTrue(run_mock.call_args.kwargs["stream"])


if __name__ == "__main__":
    unittest.main()
