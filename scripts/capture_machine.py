#!/usr/bin/env python3
"""Capture machine/toolchain facts into JSON for benchmark reproducibility.

Fields: cpu_model, cpu_cores_physical, cpu_cores_logical, ram_gb, compiler,
cmake_flags, os, timestamp_iso. Any field that cannot be captured is null and a
top-level ``notes`` entry explains why.
"""
from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CMAKE_CACHE = REPO_ROOT / "core" / "build" / "CMakeCache.txt"
CMAKE_FLAG_PREFIXES = (
    "CMAKE_BUILD_TYPE:",
    "CMAKE_CXX_FLAGS:",
    "CMAKE_CXX_FLAGS_RELEASE:",
    "CMAKE_CXX_FLAGS_DEBUG:",
    "TRACKBENCH_",
)
COMPILER_CANDIDATES = ("c++", "clang", "gcc")


def run(cmd: list[str]) -> str | None:
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout


def capture_machine() -> dict:
    is_mac = sys.platform == "darwin"
    notes: list[str] = []

    cpu_model = None
    if is_mac:
        out = run(["sysctl", "-n", "machdep.cpu.brand_string"])
        cpu_model = out.strip() if out else None
    else:
        out = run(["grep", "-m1", "model name", "/proc/cpuinfo"])
        if out:
            cpu_model = out.split(":", 1)[1].strip()
    if cpu_model is None:
        notes.append("cpu_model: could not read CPU model")

    cpu_cores_physical = None
    if is_mac:
        out = run(["sysctl", "-n", "hw.physicalcpu"])
        if out:
            try:
                cpu_cores_physical = int(out.strip())
            except ValueError:
                notes.append("cpu_cores_physical: unparseable sysctl output")
    else:
        out = run(["lscpu", "-p"])
        if out:
            count = sum(1 for line in out.splitlines() if line and line[0].isdigit())
            cpu_cores_physical = count or None
    if cpu_cores_physical is None:
        notes.append("cpu_cores_physical: could not determine physical core count")

    cpu_cores_logical = None
    if is_mac:
        out = run(["sysctl", "-n", "hw.logicalcpu"])
        if out:
            try:
                cpu_cores_logical = int(out.strip())
            except ValueError:
                notes.append("cpu_cores_logical: unparseable sysctl output")
    else:
        out = run(["nproc"])
        if out:
            try:
                cpu_cores_logical = int(out.strip())
            except ValueError:
                notes.append("cpu_cores_logical: unparseable nproc output")
    if cpu_cores_logical is None:
        notes.append("cpu_cores_logical: could not determine logical core count")

    ram_gb = None
    if is_mac:
        out = run(["sysctl", "-n", "hw.memsize"])
        if out:
            try:
                ram_gb = int(out.strip()) / 1e9
            except ValueError:
                notes.append("ram_gb: unparseable sysctl memsize output")
    else:
        out = run(["grep", "MemTotal", "/proc/meminfo"])
        if out:
            try:
                kb = int(out.split(":")[1].split()[0])
                ram_gb = kb / 1e6
            except (ValueError, IndexError):
                notes.append("ram_gb: unparseable MemTotal output")
    if ram_gb is None:
        notes.append("ram_gb: could not determine total RAM")

    compiler = None
    for name in COMPILER_CANDIDATES:
        out = run([name, "--version"])
        if out:
            first = out.strip().splitlines()
            compiler = first[0] if first else None
            if compiler:
                break
    if compiler is None:
        notes.append("compiler: no c++/clang/gcc --version available")

    cmake_flags: dict[str, str] = {}
    if CMAKE_CACHE.is_file():
        for raw in CMAKE_CACHE.read_text(encoding="utf-8", errors="replace").splitlines():
            stripped = raw.strip()
            if not stripped.startswith(CMAKE_FLAG_PREFIXES):
                continue
            if "=" not in stripped:
                continue
            name, _, value = stripped.partition("=")
            name = name.split(":", 1)[0]
            cmake_flags[name] = value
    else:
        notes.append(
            f"cmake_flags: {CMAKE_CACHE} not found; no CMake flags captured"
        )

    return {
        "cpu_model": cpu_model,
        "cpu_cores_physical": cpu_cores_physical,
        "cpu_cores_logical": cpu_cores_logical,
        "ram_gb": ram_gb,
        "compiler": compiler,
        "cmake_flags": cmake_flags,
        "os": platform.platform(),
        "timestamp_iso": datetime.now().isoformat(),
        "notes": notes,
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Capture machine/toolchain facts into JSON for benchmark reproducibility"
    )
    ap.add_argument("out", nargs="?", metavar="OUT", help="optional output file")
    ap.add_argument(
        "--out", dest="out_opt", metavar="PATH", help="optional output file"
    )
    args = ap.parse_args()

    out_path = args.out_opt or args.out
    payload = json.dumps(capture_machine(), indent=2) + "\n"

    if out_path:
        Path(out_path).expanduser().write_text(payload, encoding="utf-8")
        print(f"wrote machine.json to {out_path}", file=sys.stderr)
    else:
        sys.stdout.write(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
