from __future__ import annotations

import unittest

from mahanai import agent


class CodexLoginPageTests(unittest.TestCase):
    def test_success_page_uses_logedin_html(self) -> None:
        body = agent._codex_login_success_bytes().decode("utf-8")

        self.assertIn("<title>Codex Connected</title>", body)
        self.assertIn("Your Codex account has been linked successfully.", body)

    def test_success_page_embeds_icon_before_oauth_server_stops(self) -> None:
        body = agent._codex_login_success_bytes().decode("utf-8")

        self.assertIn('src="data:image/png;base64,', body)
        self.assertNotIn('src="./icons/icon.png"', body)


if __name__ == "__main__":
    unittest.main()
