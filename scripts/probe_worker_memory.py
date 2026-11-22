"""Container-only probe for RLIMIT_AS versus pandas/pyarrow memory use."""

from __future__ import annotations

import resource
import sys
from pathlib import Path

import pandas as pd


def vm_size_kb() -> int | None:
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith("VmSize:"):
            return int(line.split()[1])
    return None


def main() -> None:
    path = sys.argv[1]
    print(f"vm_before_kb={vm_size_kb()}")
    limit = 1024 * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
    print(f"limit_bytes={limit}")
    try:
        frame = pd.read_parquet(path)
        print(f"parquet_ok rows={len(frame)}")
    except Exception as exc:
        print(f"parquet_failed={type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()
