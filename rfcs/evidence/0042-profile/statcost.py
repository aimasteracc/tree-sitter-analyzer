"""Raw per-call cost of os.stat / os.path.realpath on this machine: python -I statcost.py <repo>"""
import os
import sys
import time
from pathlib import Path

repo = Path(sys.argv[1])
files = [str(p) for p in repo.rglob("*.py") if ".ast-cache" not in p.parts]
for _ in range(2):
    t0 = time.perf_counter()
    for f in files:
        os.stat(f)
    st = (time.perf_counter() - t0) / len(files)
t0 = time.perf_counter()
for f in files:
    os.path.realpath(f)
rp = (time.perf_counter() - t0) / len(files)
t0 = time.perf_counter()
n = 0
for d, _dirs, _fs in os.walk(repo):
    n += 1
wk = time.perf_counter() - t0
print(f"files {len(files)} stat_us {st*1e6:.1f} realpath_us {rp*1e6:.1f} walk_ms {wk*1e3:.1f} dirs {n}")
