from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from mahanai.mai_parser import parse_mai_text
from mahanai.mmd_parser import parse_mmd_file


class MmdParserTests(unittest.TestCase):
    def test_embedded_default_theme_is_parsed(self) -> None:
        plugin_text = """
plugin.name = "Theme Plugin"

newdeftheme(
theme.name = neon
theme.pretty.name = Neon Nights
ink = #00ffcc
message.ai.color = color("ink")
)
"""
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "theme-plugin.mmd"
            path.write_text(plugin_text, encoding="utf-8")

            plugin = parse_mmd_file(path)

        self.assertEqual(len(plugin.default_themes), 1)
        parsed_theme = parse_mai_text(plugin.default_themes[0].source, name="embedded")
        self.assertEqual(parsed_theme.slug(), "neon")
        self.assertEqual(parsed_theme.display(), "Neon Nights")
        self.assertEqual(parsed_theme.ai_color, "#00ffcc")

    def test_pytknwd_action_is_attached_to_command(self) -> None:
        plugin_text = """
plugin.name = "Tk Plugin"

add command("/window"){
    pytknwd(
root = tk.Tk()
root.title("Plugin Window")
label = tk.Label(root, text="Hello")
label.pack()
root.mainloop()
    )
}
"""
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "tk-plugin.mmd"
            path.write_text(plugin_text, encoding="utf-8")

            plugin = parse_mmd_file(path)

        self.assertEqual(plugin.commands[0].trigger, "/window")
        self.assertEqual(plugin.commands[0].actions[-1].type, "tk-window")
        self.assertIn('root.title("Plugin Window")', plugin.commands[0].actions[-1].value)


if __name__ == "__main__":
    unittest.main()
