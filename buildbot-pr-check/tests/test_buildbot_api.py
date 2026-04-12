"""Unit tests for buildbot_api traversal using recorded fixtures.

Fixtures were captured from https://buildbot.dse.in.tum.de against build 104395
(TUM-DSE/doctor-cluster-config PR #1133, head SHA 28047805…); the HTTP layer is
stubbed so no network is hit.
"""

from __future__ import annotations

import json
import urllib.parse
from pathlib import Path
from typing import Any

import pytest

from buildbot_pr_check.build_status import BuildStatus
from buildbot_pr_check.buildbot_api import Build, BuildbotClient

FIXTURES = Path(__file__).parent / "fixtures"

ROUTES: dict[str, str] = {
    "builders/18/builds/3394": "builder18_build3394.json",
    "builds/104395/steps": "build_104395_steps.json",
    "builds/104417/steps": "build_104417_steps.json",
    "steps/525471/logs": "step_525471_logs.json",
    "logs/230713/contents?offset=141907&limit=80": "log_230713_tail.json",
}


def load_fixture(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text())


def fake_get(self: BuildbotClient, path: str, params: dict[str, Any] | None = None) -> Any:
    key = path.lstrip("/")
    if params:
        parts: list[tuple[str, str]] = []
        for k, v in params.items():
            if isinstance(v, list):
                parts.extend((k, str(x)) for x in v)
            else:
                parts.append((k, str(v)))
        key = f"{key}?{urllib.parse.urlencode(parts)}"
    if key in ROUTES:
        return load_fixture(ROUTES[key])
    # buildrequests/<id>/builds?property=... → individual fixture or synthesised success
    if key.startswith("buildrequests/") and "/builds" in key:
        br = key.split("/")[1]
        f = FIXTURES / f"br_{br}_builds.json"
        if f.exists():
            return json.loads(f.read_text())
        # All other sub-builds in build 104395 succeeded; synthesise one so the
        # full eval-build resolution can run without 31 fixture files.
        return {
            "builds": [
                {
                    "buildid": 900000 + int(br),
                    "builderid": 111,
                    "number": int(br),
                    "results": 0,
                    "complete": True,
                    "state_string": "build successful",
                    "properties": {"attr": [f"x86_64-linux.synth-{br}", "nix-eval-nix"]},
                }
            ]
        }
    msg = f"no fixture for {key!r}"
    raise AssertionError(msg)


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> BuildbotClient:
    monkeypatch.setattr(BuildbotClient, "_get", fake_get)
    return BuildbotClient("https://buildbot.dse.in.tum.de")


def test_build_status_mapping() -> None:
    b = Build(buildid=1, builderid=1, number=1, results=2, state_string="", complete=True)
    assert b.status is BuildStatus.FAILURE
    assert b.status.is_bad
    running = Build(buildid=1, builderid=1, number=1, results=None, state_string="", complete=False)
    assert running.status_str == "RUNNING"


def test_load_eval_build_extracts_buildrequests(client: BuildbotClient) -> None:
    b = client.get_build_by_number(18, 3394)
    ev = client.load_eval_build(b)
    assert 103834 in ev.buildrequest_ids
    assert len(ev.buildrequest_ids) == 31
    assert ev.web_url == "https://buildbot.dse.in.tum.de/#/builders/18/builds/3394"


def test_resolve_sub_build_and_log_tail(client: BuildbotClient) -> None:
    sub = client.resolve_sub_build(103834)
    assert sub.build is not None
    assert sub.attr == "x86_64-linux.nixos-jamie"
    assert sub.build.status == BuildStatus.FAILURE

    client.attach_failure_log(sub, tail=80)
    assert sub.log_url == "https://buildbot.dse.in.tum.de/api/v2/logs/230713/raw_inline"
    assert sub.log_tail is not None
    assert "program finished with exit code 1" in sub.log_tail
    # stream-code prefix (h/e/o) is stripped from each line
    assert "helapsedTime" not in sub.log_tail
    assert "elapsedTime" in sub.log_tail
