from __future__ import annotations

import io
import unittest
from unittest.mock import patch

from rich.console import Console

from mahanai import agent


class StartupBannerTests(unittest.TestCase):
    def _render_banner(self, *, compact: bool) -> str:
        output = io.StringIO()
        console = Console(file=output, force_terminal=False, color_system=None, width=100)
        with patch.object(agent, "console", console):
            agent.print_startup_banner("Claude Sonnet 4.6", compact=compact)
        return output.getvalue()

    def test_full_banner_only_keeps_version_and_model_metadata(self) -> None:
        output = self._render_banner(compact=False)

        self.assertIn("Max 3.0", output)
        self.assertIn("Claude Sonnet 4.6", output)
        self.assertNotIn("/api-key", output)
        self.assertNotIn("Replies stream", output)
        self.assertNotIn("/help", output)

    def test_metadata_line_centers_separator_with_balanced_padding(self) -> None:
        line = agent._banner_metadata_line("Claude Sonnet 4.6", 64)

        self.assertEqual(64, len(line))
        self.assertEqual(
            "Max 3.0" + (" " * 19) + "|" + (" " * 20) + "Claude Sonnet 4.6",
            line,
        )

    def test_compact_banner_only_keeps_version_and_model_metadata(self) -> None:
        output = self._render_banner(compact=True)

        self.assertIn("Max 3.0", output)
        self.assertIn("Claude Sonnet 4.6", output)
        self.assertNotIn("/help", output)

    def test_missing_linux_clipboard_helper_warning_is_below_metadata(self) -> None:
        output = io.StringIO()
        console = Console(file=output, force_terminal=False, color_system=None, width=100)
        warning = "⚠ Clipboard image paste needs wl-paste or xclip"
        with (
            patch.object(agent, "console", console),
            patch.object(agent, "_clipboard_image_warning", return_value=warning),
        ):
            agent.print_startup_banner("Claude Sonnet 4.6", compact=False)

        lines = output.getvalue().splitlines()
        metadata_index = next(i for i, line in enumerate(lines) if "Max 3.0" in line)
        self.assertEqual(warning, lines[metadata_index + 1])


if __name__ == "__main__":
    unittest.main()
