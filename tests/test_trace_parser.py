"""Trace parser regression tests — line parsing and malformed-line safety.

The parser turns raw xv6 serial console lines into normalized event dicts. It
must parse well-formed [SCHED]/[SCHEDTEST] lines, ignore unrelated lines, and
never crash on truncated/garbage input. Offline; no API key.
"""
import trace_parser as TP


def test_parse_dispatch_line():
    ev = TP.parse_line("[SCHED] tick=5 algo=rr event=DISPATCH pid=3 state=RUNNING")
    assert ev is not None
    assert ev["tick"] == 5
    assert ev["algo"] == "RR"          # canonicalized to uppercase
    assert ev["event"] == "DISPATCH"
    assert ev["pid"] == 3
    assert ev["source"] == "xv6"


def test_parse_preempt_with_reason():
    ev = TP.parse_line(
        "[SCHED] tick=12 algo=mlfq event=PREEMPT pid=2 reason=quantum_expired"
    )
    assert ev["event"] == "PREEMPT"
    assert ev["reason"] == "quantum_expired"
    assert ev["algo"] == "MLFQ"


def test_default_algo_applied_when_missing():
    ev = TP.parse_line("[SCHED] tick=1 event=DISPATCH pid=1", algo="srtf")
    assert ev["algo"] == "SRTF"


def test_non_sched_line_ignored():
    assert TP.parse_line("xv6 kernel is booting") is None
    assert TP.parse_line("init: starting sh") is None
    assert TP.parse_line("") is None


def test_recognized_line_without_event_has_no_event_key():
    # A [SCHED] line with no event= token parses but carries event=None, which
    # the file-level parser treats as a parse error (not a usable event).
    ev = TP.parse_line("[SCHED] tick=3 algo=rr pid=1")
    assert ev is not None
    assert ev.get("event") is None


def test_garbage_tokens_do_not_crash():
    # tokens without '=' and stray text must be tolerated.
    ev = TP.parse_line("[SCHEDTEST] event=RUN_BEGIN garbage ==== pid=1 algo=fcfs")
    assert ev is not None
    assert ev["event"] == "RUN_BEGIN"
    assert ev["pid"] == 1


def test_parse_file_recovers_and_counts_errors(tmp_path):
    log = tmp_path / "raw.log"
    log.write_text(
        "booting...\n"
        "[SCHED] tick=0 algo=rr event=DISPATCH pid=1 state=RUNNING\n"
        "[SCHED] tick=1 algo=rr pid=1\n"           # recognized but no event -> error
        "random noise line\n"
        "[SCHED] tick=2 algo=rr event=EXIT pid=1 state=ZOMBIE\n"
    )
    events, errors = TP.parse_file(log, algo="rr")
    got = [e["event"] for e in events]
    assert got == ["DISPATCH", "EXIT"]
    assert errors == 1


def test_events_sorted_by_tick(tmp_path):
    log = tmp_path / "raw.log"
    log.write_text(
        "[SCHED] tick=9 algo=rr event=EXIT pid=1\n"
        "[SCHED] tick=0 algo=rr event=DISPATCH pid=1\n"
        "[SCHED] tick=4 algo=rr event=PREEMPT pid=1\n"
    )
    events, _ = TP.parse_file(log, algo="rr")
    ticks = [e["tick"] for e in events]
    assert ticks == sorted(ticks)
