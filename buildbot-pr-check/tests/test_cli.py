"""End-to-end tests for the CLI.

These drive the real ``cli.main`` with the Buildbot HTTP layer stubbed via the
shared fixture router (see ``test_buildbot_api``), and the forge layer stubbed
directly.
"""

from __future__ import annotations

import json

import pytest

from buildbot_pr_check import cli, github_api
from buildbot_pr_check.buildbot_api import BuildbotClient

from .test_buildbot_api import fake_get

PR_URL = "https://github.com/TUM-DSE/doctor-cluster-config/pull/1133"
HEAD_SHA = "280478056c6614a0cdbf7dc4a4b92fbdc2527807"
EVAL_WEB_URL = "https://buildbot.dse.in.tum.de/#/builders/18/builds/3394"


@pytest.fixture
def stub_http(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(BuildbotClient, "_get", fake_get)
    monkeypatch.setattr(github_api, "get_pr_head_sha", lambda *a, **k: HEAD_SHA)
    monkeypatch.setattr(github_api, "get_buildbot_urls_from_github", lambda *a, **k: [EVAL_WEB_URL])


def _run(argv: list[str]) -> int:
    with pytest.raises(SystemExit) as exc:
        cli.main(argv)
    assert isinstance(exc.value.code, int)
    return exc.value.code


def test_cmd_pr_failures_json(stub_http: None, capsys: pytest.CaptureFixture[str]) -> None:
    """Forge status → eval build → sub-build traversal → log tail."""
    code = _run([PR_URL, "--failures", "--json", "--log-tail", "80"])
    assert code == 1

    out = json.loads(capsys.readouterr().out)
    assert out["pr"] == "TUM-DSE/doctor-cluster-config#1133"
    assert out["status"] == "FAILURE"
    assert out["eval_build"] == EVAL_WEB_URL
    assert len(out["failures"]) == 1
    fail = out["failures"][0]
    assert fail["attr"] == "x86_64-linux.nixos-jamie"
    assert fail["status"] == "FAILURE"
    assert fail["log_url"].endswith("/api/v2/logs/230713/raw_inline")
    assert "program finished with exit code 1" in fail["log_tail"]


def test_cmd_pr_json_full_table(stub_http: None, capsys: pytest.CaptureFixture[str]) -> None:
    code = _run([PR_URL, "--json"])
    assert code == 1

    out = json.loads(capsys.readouterr().out)
    ev = out["eval_build"]
    assert ev["url"] == EVAL_WEB_URL
    assert ev["status"] == "FAILURE"
    assert len(ev["sub_builds"]) == 31
    by_attr = {s["attr"]: s for s in ev["sub_builds"]}
    assert by_attr["x86_64-linux.nixos-jamie"]["status"] == "FAILURE"
    assert sum(1 for s in ev["sub_builds"] if s["status"] == "SUCCESS") == 30


def test_cmd_pr_text_output_is_structured(
    stub_http: None, capsys: pytest.CaptureFixture[str]
) -> None:
    code = _run([PR_URL])
    assert code == 1
    out = capsys.readouterr().out
    assert "\x1b[" not in out  # no ANSI noise for the agent
    assert "status: FAILURE" in out
    assert "x86_64-linux.nixos-jamie" in out


def test_discovery_error_when_nothing_found(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(github_api, "get_pr_head_sha", lambda *a, **k: HEAD_SHA)
    monkeypatch.setattr(github_api, "get_buildbot_urls_from_github", lambda *a, **k: [])
    code = _run([PR_URL, "--json"])
    assert code == 1
    err = capsys.readouterr().err
    assert "No buildbot status found" in err
