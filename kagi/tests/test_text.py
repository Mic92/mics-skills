"""Tests for the shared HTML/Markdown -> plain-text helpers."""

import unittest

from kagi._text import html_to_text, markdown_to_text


class MarkdownToText(unittest.TestCase):
    def test_strips_bold_and_italic(self) -> None:
        self.assertEqual(markdown_to_text("**bold** and *italic*"), "bold and italic")

    def test_strips_headers(self) -> None:
        self.assertEqual(markdown_to_text("# Title\n\nbody"), "Title\n\nbody")

    def test_link_becomes_text_and_url(self) -> None:
        self.assertEqual(markdown_to_text("[Kagi](https://kagi.com)"), "Kagi (https://kagi.com)")

    def test_image_is_removed(self) -> None:
        self.assertEqual(markdown_to_text("![alt](https://x/y.png) caption"), "caption")

    def test_inline_code(self) -> None:
        self.assertEqual(markdown_to_text("use `kagi search`"), "use kagi search")

    def test_plain_text_passes_through(self) -> None:
        self.assertEqual(markdown_to_text("just words"), "just words")


class HtmlToText(unittest.TestCase):
    def test_paragraphs_and_list_items(self) -> None:
        out = html_to_text("<p>one</p><ul><li>a</li><li>b</li></ul>")
        self.assertIn("one", out)
        self.assertIn("- a", out)
        self.assertIn("- b", out)


if __name__ == "__main__":
    unittest.main()
