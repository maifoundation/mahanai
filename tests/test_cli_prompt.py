from __future__ import annotations

import contextlib
import io
import unittest
from pathlib import Path
from unittest.mock import patch

from mahanai import agent
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.document import Document
from prompt_toolkit.formatted_text import fragment_list_to_text
from prompt_toolkit.input.defaults import create_pipe_input
from prompt_toolkit.output import DummyOutput


class CliPromptTests(unittest.TestCase):
    def test_input_bar_has_blank_rows_above_and_below_editable_row(self) -> None:
        fragments = agent._input_bar_prompt_fragments("› ")
        with create_pipe_input() as pipe_input:
            session = agent._create_cli_prompt_session(
                input=pipe_input,
                output=DummyOutput(),
            )

            self.assertEqual("\n› ", fragment_list_to_text(fragments))
            height = session._get_default_buffer_control_height()
            self.assertEqual(2, height.min)
            self.assertEqual(2, height.preferred)
            self.assertEqual(2, height.max)

    def test_status_line_uses_terminal_default_background(self) -> None:
        rules = dict(agent._CLI_PROMPT_STYLE.style_rules)

        self.assertIn("bg:default", rules["bottom-toolbar"])
        self.assertIn("bg:default", rules["status-model"])

    def test_editable_middle_row_uses_input_bar_background(self) -> None:
        with create_pipe_input() as pipe_input:
            session = agent._create_cli_prompt_session(
                input=pipe_input,
                output=DummyOutput(),
            )

            self.assertEqual("class:input-bar", session.layout.current_window.style)

    def test_prompt_status_shows_model_effort_and_compact_workspace(self) -> None:
        status = agent._prompt_status_fragments(
            "gpt-5.4",
            "medium",
            Path("/home/mahan/mahanai"),
            home=Path("/home/mahan"),
        )

        self.assertEqual(
            "gpt-5.4  medium  ·  ~/mahanai",
            fragment_list_to_text(status),
        )

    def test_workspace_outside_home_keeps_absolute_path(self) -> None:
        compact = agent._compact_workspace_path(
            Path("/work/project"),
            home=Path("/home/mahan"),
        )

        self.assertEqual("/work/project", compact)

    def test_read_cli_input_registers_visible_prompt_with_readline(self) -> None:
        output = io.StringIO()

        with patch("sys.stdin", io.StringIO("hello\n")), contextlib.redirect_stdout(output):
            result = agent._read_cli_input("You: ")

        self.assertEqual("hello", result)
        self.assertEqual("You: ", output.getvalue())

    def test_github_repositories_render_as_compact_tokens(self) -> None:
        cases = {
            "example/repo": "◉ example/repo",
            "github.com/example/repo": "◉ example/repo",
            "https://github.com/example/repo": "◉ example/repo",
            "review https://github.com/example/repo please": "review ◉ example/repo please",
        }

        for source, expected in cases.items():
            with self.subTest(source=source):
                self.assertEqual(expected, agent._render_github_repositories(source))

    def test_repository_rendering_preserves_original_source(self) -> None:
        source = "review https://github.com/example/repo please"

        agent._render_github_repositories(source)

        self.assertEqual("review https://github.com/example/repo please", source)

    def test_non_github_host_path_is_not_rendered_as_repository(self) -> None:
        source = "https://gitlab.com/example/repo"

        self.assertEqual(source, agent._render_github_repositories(source))

    def test_backspace_deletes_entire_repository_reference(self) -> None:
        source = "review https://github.com/example/repo"
        buffer = Buffer(document=Document(source, cursor_position=len(source)))

        deleted = agent._delete_github_repository_before_cursor(buffer)

        self.assertTrue(deleted)
        self.assertEqual("review ", buffer.text)

    def test_cursor_moves_across_repository_as_one_token(self) -> None:
        source = "https://github.com/example/repo"
        buffer = Buffer(document=Document(source, cursor_position=len(source)))

        moved_left = agent._move_across_github_repository(buffer, direction=-1)
        moved_right = agent._move_across_github_repository(buffer, direction=1)

        self.assertTrue(moved_left)
        self.assertTrue(moved_right)
        self.assertEqual(len(source), buffer.cursor_position)

    def test_prompt_session_submits_original_repository_url(self) -> None:
        source = "https://github.com/example/repo"

        with create_pipe_input() as pipe_input:
            session = agent._create_cli_prompt_session(
                input=pipe_input,
                output=DummyOutput(),
            )
            pipe_input.send_text(source + "\r")

            result = agent._read_cli_input("You: ", session=session)

        self.assertEqual(source, result)


if __name__ == "__main__":
    unittest.main()
