#!/usr/bin/env python3
"""Serve _site/ on a port and rebuild on source file change.

Watches all .md / .yml / .html / .css / .py under src/ (skipping _site/ and
__pycache__/). On any change, runs build.py. The http.server runs in a child
process so the watch loop can stay in the foreground.

Usage: python3 _build/serve.py [port]   (default 8000)
"""
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent
BUILD = SRC / "_build" / "build.py"
SUFFIXES = {".md", ".yml", ".html", ".css", ".py"}
SKIP_DIRS = {"_site", "__pycache__", ".git"}


def collect_mtimes() -> dict[Path, float]:
    out: dict[Path, float] = {}
    for root, dirs, files in os.walk(SRC):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            if Path(name).suffix in SUFFIXES:
                p = Path(root) / name
                try:
                    out[p] = p.stat().st_mtime
                except OSError:
                    pass
    return out


def build() -> None:
    subprocess.run([sys.executable, str(BUILD)], cwd=SRC, check=False)


def port_is_free(port: int) -> bool:
    """True if we can bind to the port (matches http.server's reuse behavior)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("", port))
            return True
        except OSError:
            return False


def pick_port(preferred: int, tries: int = 20) -> int:
    """Return `preferred` if free, else the next open port. Warn on fallback."""
    for port in range(preferred, preferred + tries):
        if port_is_free(port):
            if port != preferred:
                print(
                    f"⚠ port {preferred} is in use — using {port} instead",
                    flush=True,
                )
                print(
                    f"  (to free {preferred}:  lsof -ti :{preferred} | xargs kill)",
                    flush=True,
                )
            return port
    sys.exit(
        f"✗ no free port in {preferred}–{preferred + tries - 1}; "
        f"free one with:  lsof -ti :{preferred} | xargs kill"
    )


def watch_loop() -> None:
    last = collect_mtimes()
    print(f"→ watching {len(last)} files (Ctrl-C to stop)", flush=True)
    while True:
        time.sleep(1)
        curr = collect_mtimes()
        changed = sorted(
            {p for p in curr if last.get(p) != curr.get(p)}
            | {p for p in last if p not in curr}
        )
        if changed:
            for p in changed[:5]:
                rel = p.relative_to(SRC) if p.exists() else p.name
                print(f"  · {rel}", flush=True)
            if len(changed) > 5:
                print(f"  · (+{len(changed) - 5} more)", flush=True)
            build()
            last = collect_mtimes()


def main() -> None:
    requested = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    port = pick_port(requested)

    print("→ initial build…", flush=True)
    build()

    print(f"→ serving http://localhost:{port}/", flush=True)
    server = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(port), "-d", str(SRC / "_site")]
    )

    try:
        watch_loop()
    except KeyboardInterrupt:
        print("\n→ stopping…", flush=True)
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()


if __name__ == "__main__":
    main()
