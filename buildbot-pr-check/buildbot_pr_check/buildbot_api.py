"""Thin typed client for the Buildbot REST API (stdlib urllib only).

This encapsulates the buildbot-nix data model so the subcommands don't have to
hand-roll URL math::

    eval build (builder ".../nix-eval")
      └─ step "build flake"
           └─ urls[]: each → /#/buildrequests/<id>
                 GET /api/v2/buildrequests/<id>/builds → builds[0].buildid
                   GET /api/v2/builds/<bid>?property=attr&property=error
                   GET /api/v2/builds/<bid>/steps → steps[].stepid, results
                   GET /api/v2/steps/<sid>/logs   → logs[].logid
                   GET /api/v2/logs/<logid>/raw_inline → raw text
"""

from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any

from .build_status import BuildStatus, get_build_status, status_name
from .exceptions import BuildbotAPIError

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# data classes
# --------------------------------------------------------------------------- #


@dataclass
class Build:
    buildid: int
    builderid: int
    number: int
    results: int | None
    state_string: str
    complete: bool
    properties: dict[str, Any] = field(default_factory=dict)

    @property
    def status(self) -> BuildStatus | None:
        return get_build_status(self.results)

    @property
    def status_str(self) -> str:
        return status_name(self.results)

    def prop(self, name: str) -> Any:
        v = self.properties.get(name)
        # buildbot returns [value, source]
        if isinstance(v, list) and v:
            return v[0]
        return v

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> Build:
        return cls(
            buildid=d["buildid"],
            builderid=d["builderid"],
            number=d["number"],
            results=d.get("results"),
            state_string=d.get("state_string", ""),
            complete=bool(d.get("complete")),
            properties=d.get("properties") or {},
        )


@dataclass
class Step:
    stepid: int
    number: int
    name: str
    results: int | None
    state_string: str
    urls: list[dict[str, str]] = field(default_factory=list)

    @property
    def status(self) -> BuildStatus | None:
        return get_build_status(self.results)

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> Step:
        return cls(
            stepid=d["stepid"],
            number=d["number"],
            name=d.get("name", ""),
            results=d.get("results"),
            state_string=d.get("state_string", ""),
            urls=list(d.get("urls") or []),
        )


@dataclass
class Log:
    logid: int
    name: str
    slug: str
    num_lines: int

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> Log:
        return cls(
            logid=d["logid"],
            name=d.get("name", "stdio"),
            slug=d.get("slug", "stdio"),
            num_lines=d.get("num_lines", 0),
        )


@dataclass
class SubBuild:
    """Result of resolving one buildrequest → build (a single flake attr build)."""

    buildrequest_id: int
    build: Build | None
    attr: str | None
    error: str | None
    log_url: str | None = None
    log_tail: str | None = None

    @property
    def results(self) -> int | None:
        return self.build.results if self.build else None

    @property
    def status_str(self) -> str:
        return status_name(self.results)

    def to_json(self) -> dict[str, Any]:
        return {
            "buildrequest_id": self.buildrequest_id,
            "build_id": self.build.buildid if self.build else None,
            "results": self.results,
            "status": self.status_str,
            "state_string": self.build.state_string if self.build else None,
            "attr": self.attr,
            "error": self.error,
            "log_url": self.log_url,
            "log_tail": self.log_tail,
        }


@dataclass
class EvalBuild:
    """Top-level nix-eval build plus its triggered sub-builds."""

    base_url: str
    build: Build
    buildrequest_ids: list[int]
    sub_builds: list[SubBuild] = field(default_factory=list)

    @property
    def web_url(self) -> str:
        return f"{self.base_url}/#/builders/{self.build.builderid}/builds/{self.build.number}"

    def to_json(self) -> dict[str, Any]:
        return {
            "url": self.web_url,
            "build_id": self.build.buildid,
            "builder_id": self.build.builderid,
            "number": self.build.number,
            "results": self.build.results,
            "status": self.build.status_str,
            "state_string": self.build.state_string,
            "complete": self.build.complete,
            "sub_builds": [s.to_json() for s in self.sub_builds],
        }


# --------------------------------------------------------------------------- #
# client
# --------------------------------------------------------------------------- #


class BuildbotClient:
    """Minimal Buildbot REST client.

    All methods raise :class:`BuildbotAPIError` on transport/JSON errors so
    callers can present a single error message.
    """

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    # -- raw ---------------------------------------------------------------- #

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        url = f"{self.base_url}/api/v2/{path.lstrip('/')}"
        if params:
            # buildbot accepts repeated ?property=… so build manually
            parts: list[tuple[str, str]] = []
            for k, v in params.items():
                if isinstance(v, list):
                    parts.extend((k, str(x)) for x in v)
                else:
                    parts.append((k, str(v)))
            url = f"{url}?{urllib.parse.urlencode(parts)}"
        logger.debug("GET %s", url)
        try:
            with urllib.request.urlopen(url) as resp:  # noqa: S310
                return json.loads(resp.read())
        except (urllib.error.URLError, urllib.error.HTTPError) as e:
            msg = f"Buildbot request failed: {url}: {e}"
            raise BuildbotAPIError(msg) from e
        except json.JSONDecodeError as e:
            msg = f"Buildbot returned invalid JSON: {url}: {e}"
            raise BuildbotAPIError(msg) from e

    # -- typed wrappers ---------------------------------------------------- #

    def get_build_by_number(
        self, builder_id: int, number: int, *, props: list[str] | None = None
    ) -> Build:
        params = {"property": props} if props else None
        d = self._get(f"builders/{builder_id}/builds/{number}", params)
        return Build.from_json(d["builds"][0])

    def get_steps(self, build_id: int) -> list[Step]:
        d = self._get(f"builds/{build_id}/steps")
        return [Step.from_json(s) for s in d.get("steps", [])]

    def get_step_logs(self, step_id: int) -> list[Log]:
        d = self._get(f"steps/{step_id}/logs")
        return [Log.from_json(log) for log in d.get("logs", [])]

    def raw_log_url(self, log_id: int) -> str:
        return f"{self.base_url}/api/v2/logs/{log_id}/raw_inline"

    def get_log_tail(self, log: Log, *, tail: int) -> str:
        """Fetch the last ``tail`` lines of a log via the ``contents`` endpoint."""
        offset = max(0, log.num_lines - tail)
        d = self._get(f"logs/{log.logid}/contents", {"offset": offset, "limit": tail})
        chunks = d.get("logchunks", [])
        text = "".join(c.get("content", "") for c in chunks)
        # buildbot stdio logs prefix each line with a one-char stream code
        return "\n".join(line[1:] if len(line) > 1 else line for line in text.splitlines())

    def get_buildrequest_build(self, br_id: int, *, props: list[str] | None = None) -> Build | None:
        params = {"property": props} if props else None
        d = self._get(f"buildrequests/{br_id}/builds", params)
        builds = d.get("builds", [])
        if not builds:
            return None
        # Prefer the most recent build for this request.
        return Build.from_json(builds[-1])

    # -- buildbot-nix traversal ------------------------------------------- #

    def extract_buildrequest_ids(self, steps: list[Step]) -> list[int]:
        """Collect ``/#/buildrequests/<id>`` IDs from the trigger step's URL list."""
        ids: list[int] = []
        for step in steps:
            for u in step.urls:
                m = re.search(r"buildrequests/(\d+)", u.get("url", ""))
                if m:
                    ids.append(int(m.group(1)))
        return sorted(set(ids))

    def load_eval_build(self, build: Build) -> EvalBuild:
        steps = self.get_steps(build.buildid)
        br_ids = self.extract_buildrequest_ids(steps)
        return EvalBuild(base_url=self.base_url, build=build, buildrequest_ids=br_ids)

    def resolve_sub_build(self, br_id: int) -> SubBuild:
        b = self.get_buildrequest_build(br_id, props=["attr", "error", "virtual_builder_name"])
        attr = None
        error = None
        if b:
            attr = b.prop("attr") or b.prop("virtual_builder_name")
            error = b.prop("error")
        return SubBuild(buildrequest_id=br_id, build=b, attr=attr, error=error)

    def resolve_sub_builds(self, br_ids: list[int], *, max_workers: int = 16) -> list[SubBuild]:
        if not br_ids:
            return []
        out: dict[int, SubBuild] = {}
        with ThreadPoolExecutor(max_workers=min(max_workers, len(br_ids))) as ex:
            futs = {ex.submit(self.resolve_sub_build, i): i for i in br_ids}
            for fut in as_completed(futs):
                br = futs[fut]
                try:
                    out[br] = fut.result()
                except BuildbotAPIError as e:
                    logger.warning("buildrequest %s: %s", br, e)
                    out[br] = SubBuild(buildrequest_id=br, build=None, attr=None, error=str(e))
        return [out[i] for i in br_ids]

    def attach_failure_log(self, sub: SubBuild, *, tail: int) -> None:
        """Populate ``sub.log_url`` / ``sub.log_tail`` from the failing step's stdio log."""
        if sub.build is None:
            return
        try:
            steps = self.get_steps(sub.build.buildid)
        except BuildbotAPIError:
            return
        bad = [s for s in steps if s.status is not None and s.status.is_bad]
        target = bad[-1] if bad else (steps[-1] if steps else None)
        if target is None:
            return
        try:
            logs = self.get_step_logs(target.stepid)
        except BuildbotAPIError:
            return
        if not logs:
            return
        log = next((log for log in logs if log.slug == "stdio"), logs[0])
        sub.log_url = self.raw_log_url(log.logid)
        if tail > 0:
            try:
                sub.log_tail = self.get_log_tail(log, tail=tail)
            except BuildbotAPIError:
                sub.log_tail = None
