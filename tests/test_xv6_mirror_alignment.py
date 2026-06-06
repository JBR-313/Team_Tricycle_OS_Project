"""xv6 mirror-alignment regression — the curated schedtest.c WORKLOADS tables
and their workloads/xv6_*.json mirrors must agree process-for-process.

For the xv6 backend the LLM analyzes the mirror JSON while the kernel forks the
C table, and burst priors are aligned BY FORK INDEX. If the two ever diverge,
priors land on the wrong process silently. This test parses the C table and
asserts each mirror matches it exactly (order, arrival, burst, priority, label).
Offline; no API key, no QEMU.
"""
import json
import re

from conftest import ROOT, WORKLOADS_DIR

SCHEDTEST_C = ROOT / "xv6-riscv" / "user" / "schedtest.c"

# C profile name -> mirror JSON stem.
MIRROR_FOR = {
    "interactive":        "xv6_interactive",
    "cpu_bound":          "xv6_cpu_bound",
    "mixed":              "xv6_mixed",
    "priority_sensitive": "xv6_priority_sensitive",
    "interactive_storm":  "xv6_interactive_storm",
    "batch_convoy":       "xv6_batch_convoy",
}

_HEADER_RE = re.compile(r'\{\s*"([A-Za-z_][A-Za-z0-9_]*)"\s*,\s*(\d+)\s*,\s*\{')
_PROC_RE = re.compile(
    r'\{\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*"([^"]+)"\s*\}')


def _parse_c_workloads():
    """Return {profile_name: [(arrival, cpu_burst, priority, label), ...]}."""
    text = SCHEDTEST_C.read_text()
    start = text.index("WORKLOADS[] = {")
    end = text.index("\n};", start)
    region = text[start:end]

    headers = [(m.start(), m.group(1), int(m.group(2)))
               for m in _HEADER_RE.finditer(region)]
    procs = [(m.start(), int(m.group(1)), int(m.group(2)),
              int(m.group(3)), m.group(4))
             for m in _PROC_RE.finditer(region)]

    out = {}
    for i, (hpos, name, n) in enumerate(headers):
        next_pos = headers[i + 1][0] if i + 1 < len(headers) else len(region)
        block = [p[1:] for p in procs if hpos < p[0] < next_pos]
        assert len(block) == n, \
            f"profile {name}: header says {n} procs, parsed {len(block)}"
        out[name] = block
    return out


def test_c_table_parses():
    wl = _parse_c_workloads()
    # All known profiles present (guards against a rename breaking the parser).
    for name in MIRROR_FOR:
        assert name in wl, f"profile {name} not found in schedtest.c"


def test_every_c_profile_has_a_mirror():
    wl = _parse_c_workloads()
    for name in wl:
        assert name in MIRROR_FOR, \
            f"schedtest.c profile {name!r} has no registered mirror JSON"


def test_mirror_matches_c_table():
    wl = _parse_c_workloads()
    for name, procdefs in wl.items():
        stem = MIRROR_FOR[name]
        mirror_path = WORKLOADS_DIR / f"{stem}.json"
        assert mirror_path.is_file(), f"missing mirror {mirror_path.name}"
        doc = json.loads(mirror_path.read_text())
        procs = doc["processes"]
        assert len(procs) == len(procdefs), (
            f"{stem}: {len(procs)} procs vs C table {len(procdefs)}")
        for idx, ((arrival, cpu, prio, label), p) in enumerate(
                zip(procdefs, procs)):
            assert p["arrival_time"] == arrival, \
                f"{stem}[{idx}] arrival {p['arrival_time']} != C {arrival}"
            assert p["cpu_bursts"] == [cpu], \
                f"{stem}[{idx}] cpu_bursts {p['cpu_bursts']} != C [{cpu}]"
            # actual_bursts (ground truth) must mirror the single burst too.
            assert p.get("actual_bursts") == [cpu], \
                f"{stem}[{idx}] actual_bursts {p.get('actual_bursts')} != C [{cpu}]"
            assert p["priority"] == prio, \
                f"{stem}[{idx}] priority {p['priority']} != C {prio}"
            assert p.get("label") == label, \
                f"{stem}[{idx}] label {p.get('label')!r} != C {label!r}"
