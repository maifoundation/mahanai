from __future__ import annotations

import base64
import unittest
from unittest.mock import patch

from PIL import Image
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.document import Document

from mahanai import agent


class ClipboardImageTests(unittest.TestCase):
    def setUp(self) -> None:
        agent._ACTIVE_CLIPBOARD_IMAGES.clear()

    def test_linux_warns_when_no_clipboard_image_helper_exists(self) -> None:
        with (
            patch.object(agent.sys, "platform", "linux"),
            patch.object(agent.shutil, "which", return_value=None),
        ):
            warning = agent._clipboard_image_warning()

        self.assertIn("wl-paste", warning or "")
        self.assertIn("xclip", warning or "")

    def test_linux_accepts_either_clipboard_image_helper(self) -> None:
        with (
            patch.object(agent.sys, "platform", "linux"),
            patch.object(
                agent.shutil,
                "which",
                side_effect=lambda command: "/usr/bin/wl-paste" if command == "wl-paste" else None,
            ),
        ):
            self.assertIsNone(agent._clipboard_image_warning())

    def test_clipboard_bitmap_is_encoded_as_png_data_url(self) -> None:
        image = Image.new("RGB", (2, 2), "red")

        with patch("PIL.ImageGrab.grabclipboard", return_value=image):
            captured = agent._capture_clipboard_image()

        self.assertIsNotNone(captured)
        assert captured is not None
        self.assertEqual("clipboard.png", captured["name"])
        prefix, encoded = captured["url"].split(",", 1)
        self.assertEqual("data:image/png;base64", prefix)
        self.assertTrue(base64.b64decode(encoded).startswith(b"\x89PNG\r\n\x1a\n"))

    def test_multiple_clipboard_images_render_and_extract_in_order(self) -> None:
        buffer = Buffer()
        first = {"name": "clipboard.png", "url": "data:image/png;base64,first"}
        second = {"name": "clipboard.png", "url": "data:image/png;base64,second"}

        agent._insert_clipboard_image_token(buffer, first)
        agent._insert_clipboard_image_token(buffer, second)
        rendered = agent._render_clipboard_image_tokens(buffer.text)
        clean_text, images = agent._extract_clipboard_images("describe " + buffer.text)

        self.assertEqual("▣ Image 1 ▣ Image 2", rendered)
        self.assertEqual("describe", clean_text)
        self.assertEqual([first["url"], second["url"]], [image["url"] for image in images])

    def test_backspace_deletes_one_clipboard_image_atomically(self) -> None:
        buffer = Buffer()
        first = {"name": "clipboard.png", "url": "data:image/png;base64,first"}
        second = {"name": "clipboard.png", "url": "data:image/png;base64,second"}
        agent._insert_clipboard_image_token(buffer, first)
        agent._insert_clipboard_image_token(buffer, second)
        buffer.document = Document(buffer.text, cursor_position=len(buffer.text))

        deleted = agent._delete_clipboard_image_before_cursor(buffer)
        rendered = agent._render_clipboard_image_tokens(buffer.text)

        self.assertTrue(deleted)
        self.assertEqual("▣ Image 1", rendered)
        self.assertEqual(1, len(agent._ACTIVE_CLIPBOARD_IMAGES))

    def test_new_image_number_is_not_reused_after_deletion(self) -> None:
        buffer = Buffer()
        image = {"name": "clipboard.png", "url": "data:image/png;base64,image"}
        agent._insert_clipboard_image_token(buffer, image)
        agent._insert_clipboard_image_token(buffer, image)
        first_match = next(agent._CLIPBOARD_IMAGE_TOKEN_RE.finditer(buffer.text))
        buffer.document = Document(buffer.text, cursor_position=first_match.end())
        agent._delete_clipboard_image_before_cursor(buffer)
        buffer.cursor_position = len(buffer.text)

        agent._insert_clipboard_image_token(buffer, image)

        rendered = agent._render_clipboard_image_tokens(buffer.text)
        self.assertIn("▣ Image 2", rendered)
        self.assertIn("▣ Image 3", rendered)

    def test_multiple_images_are_added_to_payload_before_original_text(self) -> None:
        images = [
            {"url": "data:image/png;base64,first"},
            {"url": "data:image/png;base64,second"},
        ]

        content = agent._user_content_with_images("compare these", images)

        self.assertEqual(
            [
                {"type": "image_url", "image_url": {"url": images[0]["url"]}},
                {"type": "image_url", "image_url": {"url": images[1]["url"]}},
                {"type": "text", "text": "compare these"},
            ],
            content,
        )

    def test_text_without_images_keeps_string_payload(self) -> None:
        self.assertEqual("hello", agent._user_content_with_images("hello", []))

    def test_codex_converts_chat_images_to_responses_input_images(self) -> None:
        content = [
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,image"}},
            {"type": "text", "text": "what do you see"},
        ]

        converted = agent._responses_api_content("user", content)

        self.assertEqual(
            [
                {"type": "input_image", "image_url": "data:image/png;base64,image"},
                {"type": "input_text", "text": "what do you see"},
            ],
            converted,
        )


if __name__ == "__main__":
    unittest.main()
