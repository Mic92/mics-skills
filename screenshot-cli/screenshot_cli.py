#!/usr/bin/env python3
"""Non-interactive screenshot CLI for agent use on macOS and Linux Wayland.

Every mode runs to completion without human input. Interactive
selection (click-a-window, drag-a-box) was removed: an agent has no
pointer, so those paths were indefinite hangs in disguise.
"""

import argparse
import os
import platform
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# -g coords are logical (pre-scale). On a 1.5x display, '0,0 100x100'
# yields a 150x150 PNG. If you're reading pixel offsets from a previous
# screenshot, divide by your scale factor first.
GEOMETRY_HELP = "Capture region 'X,Y WxH' in logical (pre-scale) coords"


class BackendUnsuitable(Exception):
    """Raised when a backend can't handle the requested mode by design.

    Distinct from a runtime failure so the fallback loop can skip silently
    instead of printing 'Warning: X failed' for an expected non-match.
    """


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


screen_geom_override: str = ""  # set from main() when -g is used


def parse_geometry(spec: str) -> tuple[int, int, int, int]:
    """Parse 'X,Y WxH' → (x, y, w, h). Same format grim -g consumes."""
    try:
        pos, size = spec.split(" ")
        x, y = (int(v) for v in pos.split(","))
        w, h = (int(v) for v in size.split("x"))
    except ValueError as e:
        raise SystemExit(f"Error: invalid geometry {spec!r}, want 'X,Y WxH': {e}") from None
    return x, y, w, h


def capture_macos(mode: str, output: str, delay: int, screen: int | None) -> None:
    args = ["screencapture"]
    if mode == "window":
        # screencapture -w is click-to-select; -l<id> is non-interactive but
        # mapping the frontmost NSWindow to a CGWindowID without third-party
        # tooling is more code than it's worth. macOS has only one backend
        # so BackendUnsuitable would dead-end — fail with a useful hint.
        raise SystemExit(
            "Error: -w on macOS would block on a mouse click. "
            "Use -g 'X,Y WxH' for a region, or -f for the whole screen."
        )
    elif mode == "geometry":
        # screencapture -R takes x,y,w,h
        x, y, w, h = parse_geometry(screen_geom_override)
        args.extend(["-R", f"{x},{y},{w},{h}"])
    if delay > 0:
        args.extend(["-T", str(delay)])
    if screen is not None:
        args.extend(["-D", str(screen + 1)])
    args.append(output)
    run(args)


def capture_spectacle(mode: str, output: str, delay: int) -> None:
    args = ["spectacle", "-b", "-n", "-o", output]
    # spectacle -a grabs the window under the cursor at invocation — no
    # click required, so it qualifies as non-interactive (the cursor is
    # wherever it happens to be, which on a headless agent run is usually
    # the focused window anyway).
    mode_flags = {"fullscreen": "-f", "window": "-a"}
    if mode not in mode_flags:
        raise BackendUnsuitable(f"spectacle does not support mode {mode!r}")
    args.append(mode_flags[mode])
    if delay > 0:
        # spectacle takes milliseconds, our API is seconds
        args.extend(["-d", str(delay * 1000)])
    run(args)


def capture_niri(mode: str, output: str, delay: int) -> None:
    if delay > 0:
        time.sleep(delay)
    # niri's IPC doesn't expose absolute window geometry for grim -g, but it
    # has a native screenshot action that knows where its own windows are.
    # The action is async (returns before the file lands, ~100-200ms on a
    # warm compositor) so we poll for the file.
    actions = {
        "fullscreen": "screenshot-screen",
        "window": "screenshot-window",
    }
    if mode not in actions:
        # Geometry goes through grim; niri has no -g equivalent.
        raise BackendUnsuitable(f"niri backend does not support mode {mode!r}")
    # niri claims to require absolute paths; in practice it resolves relative
    # ones against the client's cwd, but pin it down anyway.
    abs_output = str(Path(output).resolve())
    Path(abs_output).unlink(missing_ok=True)
    run(["niri", "msg", "action", actions[mode], "--path", abs_output])
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if Path(abs_output).is_file():
            return
        time.sleep(0.02)
    raise RuntimeError("niri screenshot action returned but file never appeared")


def capture_grim(mode: str, output: str, delay: int) -> None:
    if delay > 0:
        time.sleep(delay)
    if mode == "fullscreen":
        run(["grim", output])
    elif mode == "window":
        geom = None
        if shutil.which("swaymsg"):
            try:
                tree = subprocess.run(
                    ["swaymsg", "-t", "get_tree"], capture_output=True, text=True, check=True
                )
                jq = subprocess.run(
                    [
                        "jq",
                        "-r",
                        r'.. | select(.focused?) | .rect | "\(.x),\(.y) \(.width)x\(.height)"',
                    ],
                    input=tree.stdout,
                    capture_output=True,
                    text=True,
                    check=True,
                )
                geom = jq.stdout.strip().split("\n")[0]
            except subprocess.CalledProcessError:
                pass
        if geom:
            run(["grim", "-g", geom, output])
        else:
            print(
                "Warning: Cannot get focused window geometry, capturing fullscreen", file=sys.stderr
            )
            run(["grim", output])
    elif mode == "geometry":
        # Validate before exec so the user gets our error, not grim's.
        parse_geometry(screen_geom_override)
        run(["grim", "-g", screen_geom_override, output])


BACKENDS: dict[str, tuple[str, ...]] = {
    "macos": ("screencapture",),
    "spectacle": ("spectacle",),
    "niri": ("niri",),
    "grim": ("grim",),
}


def get_backends() -> list[str]:
    forced = os.environ.get("SCREENSHOT_BACKEND")
    if forced:
        return [forced]
    system = platform.system()
    if system == "Darwin":
        return ["macos"]
    if system == "Linux":
        backends = [name for name, cmds in BACKENDS.items() if all(shutil.which(c) for c in cmds)]
        # macos backend never applies on Linux
        backends = [b for b in backends if b != "macos"]
        # The nix wrapper bundles spectacle so it's always on PATH, but on
        # non-KDE compositors it fails and prints a warning before grim runs.
        # Try the desktop's native tool first.
        desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
        if "kde" in desktop:
            prefer = "spectacle"
        elif "niri" in desktop or os.environ.get("NIRI_SOCKET"):
            prefer = "niri"
        else:
            prefer = "grim"
        backends.sort(key=lambda b: b != prefer)
        # niri only handles fullscreen+window; keep grim around for -g.
        # Don't try niri at all on other desktops where the binary might be
        # on PATH from the nix wrapper without a running compositor.
        if prefer != "niri":
            backends = [b for b in backends if b != "niri"]
        if not backends:
            print(
                "Error: No screenshot backend found. Install spectacle (KDE) or grim (Wayland).",
                file=sys.stderr,
            )
            sys.exit(1)
        return backends
    print(f"Error: Unsupported platform: {system}", file=sys.stderr)
    sys.exit(1)


def validate_args(*, mode: str, screen: int | None, backends: list[str]) -> None:
    _ = mode
    if screen is not None and "macos" not in backends:
        # grim and spectacle don't take a monitor index; before this check
        # the flag was silently dropped and you got all monitors stitched.
        print(
            "Error: -s/--screen is only supported on macOS. "
            "Use -g 'X,Y WxH' with the monitor's offset instead.",
            file=sys.stderr,
        )
        sys.exit(1)


def capture(backend: str, mode: str, output: str, delay: int, screen: int | None) -> None:
    if backend == "macos":
        capture_macos(mode, output, delay, screen)
    elif backend == "spectacle":
        capture_spectacle(mode, output, delay)
    elif backend == "niri":
        capture_niri(mode, output, delay)
    elif backend == "grim":
        capture_grim(mode, output, delay)
    else:
        raise ValueError(f"Unknown backend: {backend}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Take a screenshot")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("-f", "--fullscreen", action="store_const", const="fullscreen", dest="mode")
    group.add_argument(
        "-w",
        "--window",
        action="store_const",
        const="window",
        dest="mode",
        help="Focused window (Linux only; macOS has no non-interactive equivalent)",
    )
    group.add_argument("-g", "--geometry", metavar="'X,Y WxH'", help=GEOMETRY_HELP)
    parser.add_argument("-d", "--delay", type=int, default=0)
    parser.add_argument("-s", "--screen", type=int, default=None)
    parser.add_argument("output", nargs="?", default=None)
    args = parser.parse_args()

    if args.geometry:
        global screen_geom_override  # noqa: PLW0603
        screen_geom_override = args.geometry
        mode = "geometry"
    else:
        mode = args.mode or "fullscreen"
    output = args.output
    if not output:
        outdir = Path.home() / ".claude" / "outputs"
        outdir.mkdir(parents=True, exist_ok=True)
        # Include microseconds: niri actions complete in ~150ms so two calls
        # easily land in the same wall-clock second and clobber each other.
        ts = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        output = str(outdir / f"screenshot-{ts}.png")
    Path(output).parent.mkdir(parents=True, exist_ok=True)

    backends = get_backends()
    validate_args(mode=mode, screen=args.screen, backends=backends)

    last_err = ""
    for backend in backends:
        try:
            capture(backend, mode, output, args.delay, args.screen)
            if Path(output).is_file():
                print(output)
                return
        except BackendUnsuitable:
            continue
        except Exception as e:  # noqa: BLE001
            last_err = str(e)
            Path(output).unlink(missing_ok=True)
            print(f"Warning: {backend} failed, trying next backend...", file=sys.stderr)

    print("Error: All screenshot backends failed", file=sys.stderr)
    if last_err:
        print(last_err, file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
