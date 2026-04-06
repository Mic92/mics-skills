"""Tests for screenshot_cli argument construction.

These don't capture screenshots — they verify the argv we hand to
backends and the upfront validation that runs before we touch them.
Backend selection isn't tested here: it depends on the real desktop
environment and mocking shutil.which + platform + env just encodes the
fix without catching the bug.
"""

from unittest import mock

import pytest

import screenshot_cli as sc


def test_spectacle_delay_passed_as_milliseconds() -> None:
    # Regression: spectacle -d takes milliseconds. Passing the user's
    # seconds value raw meant `-d 3` slept 3ms — indistinguishable from
    # no delay at all.
    with mock.patch.object(sc, "run") as m:
        sc.capture_spectacle("fullscreen", "/tmp/x.png", delay=3)
    argv = m.call_args[0][0]
    assert argv[argv.index("-d") + 1] == "3000"


def test_spectacle_zero_delay_omits_flag() -> None:
    with mock.patch.object(sc, "run") as m:
        sc.capture_spectacle("fullscreen", "/tmp/x.png", delay=0)
    assert "-d" not in m.call_args[0][0]


def test_screen_flag_rejected_without_macos_backend() -> None:
    # `-s` was a macOS-only flag that grim/spectacle silently ignored.
    # On a multi-monitor box that's a footgun: you ask for monitor 1
    # and get all monitors stitched together with no warning.
    with pytest.raises(SystemExit):
        sc.validate_args(mode="fullscreen", screen=1, backends=["grim"])


def test_screen_flag_accepted_with_macos_backend() -> None:
    sc.validate_args(mode="fullscreen", screen=1, backends=["macos"])


def test_screen_flag_unset_is_always_fine() -> None:
    sc.validate_args(mode="fullscreen", screen=None, backends=["grim"])


def test_macos_window_mode_refuses_with_hint() -> None:
    # screencapture -w blocks on a mouse click; macOS has no fallback
    # backend so this must fail loudly rather than hang or silently skip.
    with pytest.raises(SystemExit, match="-g"):
        sc.capture_macos("window", "/tmp/x.png", delay=0, screen=None)


def test_geometry_parse_grim_format() -> None:
    # Same format grim -g consumes, so the string passes straight through
    # on Linux without translation.
    assert sc.parse_geometry("10,20 300x400") == (10, 20, 300, 400)


def test_geometry_parse_rejects_garbage() -> None:
    with pytest.raises(SystemExit):
        sc.parse_geometry("10,20,300,400")
