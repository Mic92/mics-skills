#!/usr/bin/env python3
"""Cross-platform screenshot CLI for macOS and KDE Wayland."""

import argparse
import os
import platform
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def capture_macos(mode: str, output: str, delay: int, screen: int | None) -> None:
    args = ["screencapture"]
    if mode == "window":
        args.append("-w")
    elif mode == "region":
        args.append("-i")
    if delay > 0:
        args.extend(["-T", str(delay)])
    if screen is not None:
        args.extend(["-D", str(screen + 1)])
    args.append(output)
    run(args)


def capture_spectacle(mode: str, output: str, delay: int) -> None:
    args = ["spectacle", "-b", "-n", "-o", output]
    mode_flags = {"fullscreen": "-f", "window": "-a", "region": "-r"}
    args.append(mode_flags[mode])
    if delay > 0:
        args.extend(["-d", str(delay)])
    run(args)


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
    elif mode == "region":
        if not shutil.which("slurp"):
            raise RuntimeError("Region capture with grim requires slurp")
        geom = subprocess.run(["slurp"], capture_output=True, text=True, check=True).stdout.strip()
        run(["grim", "-g", geom, output])


BACKENDS: dict[str, tuple[str, ...]] = {
    "macos": ("screencapture",),
    "spectacle": ("spectacle",),
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
        if not backends:
            print(
                "Error: No screenshot backend found. Install spectacle (KDE) or grim (Wayland).",
                file=sys.stderr,
            )
            sys.exit(1)
        return backends
    print(f"Error: Unsupported platform: {system}", file=sys.stderr)
    sys.exit(1)


def capture(backend: str, mode: str, output: str, delay: int, screen: int | None) -> None:
    if backend == "macos":
        capture_macos(mode, output, delay, screen)
    elif backend == "spectacle":
        capture_spectacle(mode, output, delay)
    elif backend == "grim":
        capture_grim(mode, output, delay)
    else:
        raise ValueError(f"Unknown backend: {backend}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Take a screenshot")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("-f", "--fullscreen", action="store_const", const="fullscreen", dest="mode")
    group.add_argument("-w", "--window", action="store_const", const="window", dest="mode")
    group.add_argument("-r", "--region", action="store_const", const="region", dest="mode")
    parser.add_argument("-d", "--delay", type=int, default=0)
    parser.add_argument("-s", "--screen", type=int, default=None)
    parser.add_argument("output", nargs="?", default=None)
    args = parser.parse_args()

    mode = args.mode or "fullscreen"
    output = args.output
    if not output:
        outdir = Path.home() / ".claude" / "outputs"
        outdir.mkdir(parents=True, exist_ok=True)
        output = str(outdir / f"screenshot-{datetime.now().strftime('%Y%m%d-%H%M%S')}.png")
    Path(output).parent.mkdir(parents=True, exist_ok=True)

    last_err = ""
    for backend in get_backends():
        try:
            capture(backend, mode, output, args.delay, args.screen)
            if Path(output).is_file():
                print(output)
                return
        except Exception as e:
            last_err = str(e)
            Path(output).unlink(missing_ok=True)
            print(f"Warning: {backend} failed, trying next backend...", file=sys.stderr)

    print("Error: All screenshot backends failed", file=sys.stderr)
    if last_err:
        print(last_err, file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
