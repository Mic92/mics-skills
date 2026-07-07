"""Tests for `kagi search` output shaping: the -j JSON contract and --text.

Network is mocked, so these exercise run()'s rendering paths without hitting
Kagi. The JSON-shape test is a regression guard for the backward-compatible
`raw_text` alias in the `-j` output.
"""

import argparse
import contextlib
import io
import json
import unittest
from unittest import mock

from kagi import search
from kagi.search import QuickAnswer

_QA = QuickAnswer(
    html="<p>Two plus two is four</p>",
    markdown="Two plus two is **four** [^1]",
    references=[{"title": "Math", "url": "https://example.com", "contribution": "50%"}],
)


def _args(fmt: str) -> argparse.Namespace:
    return argparse.Namespace(
        query="q",
        num_results=3,
        links=False,
        token="t",  # non-empty -> run() skips config/session-token loading
        config=None,
        debug=False,
        format=fmt,
    )


@contextlib.contextmanager
def _mocked_run(fmt: str):
    with (
        mock.patch.object(search, "build_opener_authed", return_value=None),
        mock.patch.object(search.KagiSearch, "quick_answer", return_value=_QA),
        mock.patch.object(search.KagiSearch, "search", return_value=[]),
    ):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = search.run(_args(fmt))
        yield rc, buf.getvalue()


class JsonContract(unittest.TestCase):
    def test_quick_answer_shape_keeps_raw_text_alias(self) -> None:
        with _mocked_run("json") as (rc, out):
            self.assertEqual(rc, 0)
            payload = json.loads(out)
        qa = payload["quick_answer"]
        self.assertEqual(set(qa), {"markdown", "raw_text", "references"})
        # Backward-compat: raw_text is kept as an alias of markdown.
        self.assertEqual(qa["raw_text"], qa["markdown"])


class TextFlag(unittest.TestCase):
    def test_text_strips_markdown_markup(self) -> None:
        with _mocked_run("text") as (_rc, out):
            self.assertNotIn("**", out)

    def test_markdown_keeps_markup(self) -> None:
        with _mocked_run("markdown") as (_rc, out):
            self.assertIn("**", out)


if __name__ == "__main__":
    unittest.main()
