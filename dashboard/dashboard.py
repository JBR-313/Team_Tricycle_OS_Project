"""
LLM Sched Copilot — GUI Observability Dashboard
Run: streamlit run dashboard/dashboard.py
"""

import json
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from pathlib import Path

ROOT    = Path(__file__).parent.parent
DEMO    = ROOT / "outputs" / "demo"
OUTPUTS = ROOT / "outputs"

ALGOS = ["RR", "FCFS", "Priority", "MLFQ", "SJF", "SRTF"]
ALGO_TRACE = {
    "RR":       "trace_rr.jsonl",
    "FCFS":     "trace_fcfs.jsonl",
    "Priority": "trace_priority.jsonl",
    "MLFQ":     "trace_mlfq.jsonl",
    "SJF":      "trace_sjf.jsonl",
    "SRTF":     "trace_srtf.jsonl",
}
ALGO_HEX = {
    "RR": "#6366f1", "FCFS": "#f43f5e", "Priority": "#10b981",
    "MLFQ": "#8b5cf6", "SJF": "#f59e0b", "SRTF": "#0ea5e9",
}
PROC_HEX = {
    1: "#6366f1", 2: "#f43f5e", 3: "#10b981",
    4: "#8b5cf6", 5: "#f59e0b", 6: "#0ea5e9",
}

# ── card heights (px) — fills 992px per column (88..1080) ────────────────────
H_REC      = 175   # left col: 175+90+195+517+15gaps = 992
H_GUARD    = 90
H_EVAL     = 195
H_EXPL     = 517

H_TIMELINE = 280   # center col: 280+200+502+10gaps = 992
H_STATE    = 200
H_TRACE    = 502

H_LIVE     = 160   # right col: 160+160+400+257+15gaps = 992
H_WL       = 160
H_CMP      = 400
H_BAR      = 257

# ── columns ───────────────────────────────────────────────────────────────────
COMPACT_COLS = [
    "avg_response_time", "avg_waiting_time", "avg_turnaround_time",
    "throughput", "preemption_count", "starvation_occurred", "judgment",
]
COMPACT_LABELS = {
    "avg_response_time":   "Avg RT",
    "avg_waiting_time":    "Avg WT",
    "avg_turnaround_time": "Avg TAT",
    "throughput":          "Throughput",
    "preemption_count":    "Preempt",
    "starvation_occurred": "Starv",
    "judgment":            "Judge",
}
ALL_COLS = [
    "avg_response_time", "avg_waiting_time", "avg_turnaround_time",
    "throughput", "max_waiting_time", "preemption_count",
    "starvation_occurred", "burst_prediction_error", "judgment",
]
ALL_LABELS = {
    "avg_response_time":      "Avg RT",
    "avg_waiting_time":       "Avg WT",
    "avg_turnaround_time":    "Avg TAT",
    "throughput":             "Throughput",
    "max_waiting_time":       "Max WT",
    "preemption_count":       "Preempt",
    "starvation_occurred":    "Starv",
    "burst_prediction_error": "Burst Err",
    "judgment":               "Judge",
}
BAR_METRIC_MAP = {
    "Average Response Time":   "avg_response_time",
    "Average Waiting Time":    "avg_waiting_time",
    "Average Turnaround Time": "avg_turnaround_time",
    "Throughput":              "throughput",
    "Max Waiting Time":        "max_waiting_time",
    "Preemption Count":        "preemption_count",
}
BAR_METRIC_NAMES = list(BAR_METRIC_MAP.keys())


# ── helpers ───────────────────────────────────────────────────────────────────
def _load_json(filename: str):
    for base in [DEMO, OUTPUTS]:        # demo data takes priority
        p = base / filename
        if p.exists():
            try:
                return json.load(open(p))
            except Exception:
                pass
    return None

def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in open(path):
        s = line.strip()
        if s:
            try:
                rows.append(json.loads(s))
            except Exception:
                pass
    return rows

def get_trace(algo: str) -> list[dict]:
    fname = ALGO_TRACE.get(algo, "")
    for base in [OUTPUTS, DEMO]:
        p = base / fname
        if p.exists():
            return _load_jsonl(p)
    return []

def lbl(text: str, color: str = "#5e6e8a"):
    return (
        f'<p style="font-size:0.63rem;font-weight:700;color:{color};'
        f'letter-spacing:0.07em;text-transform:uppercase;margin:0 0 6px 0;">'
        f'{text}</p>'
    )

def pill(text: str, bg: str = "#eff6ff", fg: str = "#1d4ed8",
         size: str = "0.68rem", bold: bool = True):
    bw = "700" if bold else "500"
    return (
        f'<span style="display:inline-flex;align-items:center;padding:2px 9px;'
        f'border-radius:999px;background:{bg};color:{fg};font-size:{size};'
        f'font-weight:{bw};margin:2px 3px 2px 0;white-space:nowrap;">{text}</span>'
    )

def circle(pid: int, sz: int = 27):
    bg = PROC_HEX.get(pid, "#94a3b8")
    return (
        f'<span style="display:inline-flex;align-items:center;justify-content:center;'
        f'width:{sz}px;height:{sz}px;border-radius:50%;background:{bg};'
        f'font-size:0.59rem;font-weight:700;color:#fff;margin:2px;'
        f'box-shadow:0 1px 3px rgba(0,0,0,0.18);">P{pid}</span>'
    )

def _fmt_val(v, col: str) -> str:
    if isinstance(v, bool):
        return "Yes" if v else "No"
    if isinstance(v, float):
        return f"{v:.2f}"
    if v is None:
        return "—"
    return str(v)

def _build_segs(events: list[dict], cap_tick: int) -> list[dict]:
    dmap: dict[int, int] = {}
    segs: list[dict] = []
    for ev in events:
        tick = ev.get("tick", 0)
        pid  = ev.get("pid", -1)
        et   = ev.get("event", "")
        if et == "DISPATCH":
            dmap[pid] = tick
        elif et in ("PREEMPT", "SLEEP", "EXIT") and pid in dmap:
            segs.append({"pid": pid, "start": dmap.pop(pid), "end": tick})
    for pid, start in dmap.items():
        segs.append({"pid": pid, "start": start, "end": cap_tick})
    return segs


# ── page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="LLM Sched Copilot",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

/* ── background ── */
.stApp, [data-testid="stAppViewContainer"] {
    background: linear-gradient(135deg,
        #bde3ff 0%,
        #d4dbff 42%,
        #ffd1ec 100%
    ) !important;
    height: 100vh !important;
    overflow: hidden !important;
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display",
                 "Segoe UI", Roboto, Helvetica, Arial, sans-serif !important;
}
[data-testid="stMain"] { overflow: hidden !important; }

/* ── layout ── */
[data-testid="stMainBlockContainer"], .block-container {
    padding: 6px 10px 4px 10px !important;
    max-width: 100% !important;
}
[data-testid="stVerticalBlock"]    { gap: 5px !important; }
[data-testid="stElementContainer"] { margin: 0 !important; }
[data-testid="column"] > div > div { gap: 5px !important; }

/* ── chrome ── */
[data-testid="stHeader"], [data-testid="stDecoration"] {
    height: 0 !important;
    background: transparent !important;
    pointer-events: none !important;
    overflow: hidden !important;
}
[data-testid="stToolbar"], #MainMenu, footer { display: none !important; }

/* ── header bar ── */
.st-key-header_bar [data-testid="stVerticalBlockBorderWrapper"] {
    background: rgba(255,255,255,0.97) !important;
    border: 1px solid rgba(110,130,190,0.28) !important;
    border-radius: 16px !important;
    box-shadow: 0 3px 14px rgba(70,90,150,0.12) !important;
    overflow: hidden !important;
}
.st-key-header_bar [data-testid="stVerticalBlockBorderWrapper"] > div {
    padding: 8px 12px 7px 12px !important;
}

/* ── content cards: target all st-key-card_* ── */
[class*="st-key-card_"] [data-testid="stVerticalBlockBorderWrapper"] {
    background: rgba(255,255,255,0.97) !important;
    border: 1px solid rgba(110,130,190,0.28) !important;
    border-radius: 18px !important;
    box-shadow: 0 6px 24px rgba(70,90,150,0.14),
                0 1px 6px rgba(70,90,150,0.08) !important;
    overflow: hidden !important;
}
[class*="st-key-card_"] [data-testid="stVerticalBlockBorderWrapper"] > div {
    padding: 10px 14px 9px 14px !important;
}

/* ── scrollbar ── */
::-webkit-scrollbar { width: 3px; height: 3px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: rgba(100,116,139,0.25); border-radius: 99px; }

/* ── st.metric ── */
[data-testid="stMetricValue"] {
    font-size: 1.00rem !important; font-weight: 700 !important;
    color: #1e293b !important; line-height: 1.2 !important;
}
[data-testid="stMetricLabel"] {
    font-size: 0.55rem !important; color: #64748b !important;
    text-transform: uppercase; letter-spacing: 0.07em;
}
[data-testid="stMetric"]      { padding: 1px 0 !important; }
[data-testid="stMetricDelta"] { display: none !important; }

/* ── selectbox ── */
[data-testid="stSelectbox"] label { display: none !important; }
[data-baseweb="select"] > div {
    background: rgba(255,255,255,0.90) !important;
    border: 1px solid rgba(100,120,170,0.20) !important;
    border-radius: 8px !important;
    min-height: 28px !important;
}
[data-baseweb="select"] span, [data-baseweb="select"] div {
    color: #1e293b !important; font-size: 0.76rem !important;
}
[data-baseweb="popover"] {
    background: #ffffff !important;
    border: 1px solid rgba(100,120,170,0.20) !important;
    border-radius: 10px !important;
}
[data-baseweb="menu"] li { color: #334155 !important; font-size: 0.74rem !important; }
[data-baseweb="menu"] li:hover { background: rgba(99,102,241,0.07) !important; }

/* ── slider ── */
[data-testid="stSlider"] label { display: none !important; }
[data-testid="stSlider"] [role="slider"] {
    background: #6366f1 !important;
    box-shadow: 0 0 0 3px rgba(99,102,241,0.20) !important;
}
[data-testid="stSlider"] [data-baseweb="slider"] > div:first-child {
    background: rgba(99,102,241,0.15) !important;
}

/* ── expander ── */
[data-testid="stExpander"] {
    background: rgba(240,244,255,0.60) !important;
    border: 1px solid rgba(100,120,170,0.15) !important;
    border-radius: 8px !important;
}
[data-testid="stExpander"] summary {
    font-size: 0.62rem !important; color: #64748b !important;
    padding: 3px 8px !important;
}
[data-testid="stExpander"] summary:hover { color: #334155 !important; }

/* ── inner scroll ── */
.iscroll {
    overflow-y: auto; color: #334155;
    font-size: 0.70rem; line-height: 1.50; padding-right: 2px;
}

/* ── divider ── */
.div { border:none; border-top:1px solid rgba(100,120,170,0.12); margin: 5px 0; }

/* ── process lane card ── */
.lane-card {
    border-radius: 12px; padding: 8px 6px 10px 6px;
    min-height: 148px; text-align: center;
    border: 1px solid rgba(100,120,170,0.14);
}
.lane-title {
    font-size: 0.60rem; font-weight: 700;
    letter-spacing: 0.07em; text-transform: uppercase; margin-bottom: 8px;
}

/* ════════════════════════════════════════════════
   iPhone-style stacked notification cards
   ════════════════════════════════════════════════ */
.notif-stack {
    position: relative;
    padding-bottom: 4px;
}
.notif-card {
    background: rgba(255,255,255,0.97);
    border-radius: 13px;
    padding: 7px 12px 6px 10px;
    border-left: 3px solid #6366f1;
    position: relative;
}
.notif-card .nc-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    line-height: 1.3;
}
.notif-card .nc-title {
    font-size: 0.78rem;
    font-weight: 700;
}
.notif-card .nc-tick {
    font-size: 0.60rem;
    color: #94a3b8;
    white-space: nowrap;
    margin-left: 8px;
}
.notif-card .nc-body {
    font-size: 0.65rem;
    color: #64748b;
    margin-top: 3px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 100%;
}
/* Depth 0 = newest, most prominent */
.notif-card.depth-0 {
    z-index: 10;
    box-shadow: 0 4px 16px rgba(80,100,160,0.18);
    margin-bottom: 4px;
    padding: 9px 14px 8px 12px;
}
/* Depth 1..4: progressively recede — stronger iOS stacking */
.notif-card.depth-1 {
    z-index: 9;
    margin-top: -16px;
    opacity: 0.85;
    transform: scale(0.96) translateY(2px);
    transform-origin: top center;
    box-shadow: 0 2px 8px rgba(80,100,160,0.08);
}
.notif-card.depth-2 {
    z-index: 8;
    margin-top: -14px;
    opacity: 0.68;
    transform: scale(0.92) translateY(4px);
    transform-origin: top center;
    box-shadow: 0 1px 4px rgba(80,100,160,0.05);
}
.notif-card.depth-3 {
    z-index: 7;
    margin-top: -12px;
    opacity: 0.48;
    transform: scale(0.88) translateY(6px);
    transform-origin: top center;
    box-shadow: none;
}
.notif-card.depth-4 {
    z-index: 6;
    margin-top: -12px;
    opacity: 0.28;
    transform: scale(0.84) translateY(8px);
    transform-origin: top center;
    box-shadow: none;
}
/* Event type accent colors */
.notif-card.ev-preempt    { border-left-color: #f43f5e; }
.notif-card.ev-exit       { border-left-color: #10b981; }
.notif-card.ev-arrive     { border-left-color: #8b5cf6; }
.notif-card.ev-correction { border-left-color: #f59e0b; }
.notif-card.ev-wakeup     { border-left-color: #0ea5e9; }
</style>
""", unsafe_allow_html=True)

# ── data ──────────────────────────────────────────────────────────────────────
workload_summary  = _load_json("workload_summary.json")  or {}
recommendation    = _load_json("recommendation.json")    or {}
guard_decision    = _load_json("guard_decision.json")    or {}
metrics           = _load_json("metrics.json")           or {}
trace_explanation = _load_json("trace_explanation.json") or {}


# ── header ────────────────────────────────────────────────────────────────────
with st.container(border=True, key="header_bar"):
    h1, h2, h3 = st.columns([2.0, 0.9, 3.7], gap="medium")
    h1.markdown(
        '<div style="display:flex;align-items:center;gap:9px;">'
        '<div style="width:8px;height:8px;border-radius:50%;background:#6366f1;'
        'box-shadow:0 0 8px rgba(99,102,241,0.50);flex-shrink:0;"></div>'
        '<div>'
        '<span style="font-size:1.04rem;font-weight:800;color:#1e293b;'
        'letter-spacing:-0.4px;">LLM Sched Copilot</span><br>'
        '<span style="font-size:0.57rem;color:#64748b;">'
        'LLM suggests · Guard validates · xv6 executes · Metrics verify · Dashboard explains'
        '</span></div></div>',
        unsafe_allow_html=True,
    )
    sel_algo = h2.selectbox(
        "algo", ALGOS, index=3, key="algo_sel",
        label_visibility="collapsed",
    )
    trace_events = get_trace(sel_algo)
    max_tick     = max((e.get("tick", 0) for e in trace_events), default=60)
    default_tick = int(max_tick * 0.55)

    with h3:
        hl, hs = st.columns([1, 4])
        cur_tick = st.session_state.get("tick_s", default_tick)
        hl.markdown(
            f'<div style="padding-top:3px;">'
            f'<p style="font-size:0.53rem;color:#64748b;margin:0;'
            f'letter-spacing:0.05em;text-transform:uppercase;font-weight:600;">Replay Tick</p>'
            f'<p style="font-size:0.88rem;font-weight:800;color:#1e293b;margin:1px 0 0;">'
            f'{cur_tick}'
            f'<span style="font-size:0.59rem;font-weight:400;color:#94a3b8;margin-left:3px;">'
            f'/ {max_tick}</span></p></div>',
            unsafe_allow_html=True,
        )
        with hs:
            replay_tick = st.slider(
                "tick", 0, max(max_tick, 1),
                value=default_tick, step=1,
                key="tick_s", label_visibility="collapsed",
            )

visible = [e for e in trace_events if e.get("tick", 0) <= replay_tick]

# ── three equal columns ───────────────────────────────────────────────────────
left, center, right = st.columns([1, 1, 1], gap="medium")


# ═══════════════════════════════════════════════════════════════════════════════
# LEFT COLUMN
# ═══════════════════════════════════════════════════════════════════════════════
with left:

    # ── LLM Recommendation ───────────────────────────────────────────────────
    with st.container(height=H_REC, border=False, key="card_llm_recommendation"):
        st.markdown(lbl("LLM Recommendation"), unsafe_allow_html=True)
        if recommendation:
            rec_algo_name = recommendation.get("recommended_scheduling_algorithm", "—")
            target_m      = recommendation.get("target_metric", "—")
            params        = recommendation.get("params", {})
            reason        = recommendation.get("reason", "")
            risks         = recommendation.get("risks", [])

            top = pill(rec_algo_name, "#ede9fe", "#6d28d9", "0.76rem")
            top += pill(f"↳ {target_m}", "#dbeafe", "#1d4ed8")
            for r in risks:
                top += pill(r, "#fef3c7", "#b45309", "0.62rem")
            st.markdown(top, unsafe_allow_html=True)
            if params:
                pstr = " · ".join(f"{k}={v}" for k, v in params.items())
                st.markdown(
                    f'<p style="font-size:0.59rem;color:#64748b;margin:3px 0;">{pstr}</p>',
                    unsafe_allow_html=True,
                )
            st.markdown(
                f'<div class="iscroll" style="max-height:42px;">{reason}</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown('<div class="iscroll">recommendation.json not found</div>', unsafe_allow_html=True)

    # ── Algorithm Guard ──────────────────────────────────────────────────────
    with st.container(height=H_GUARD, border=False, key="card_algorithm_guard"):
        st.markdown(lbl("Algorithm Guard"), unsafe_allow_html=True)
        if guard_decision:
            gr  = guard_decision.get("guard_result", "—")
            fb  = guard_decision.get("fallback_used", False)
            gbg, gfg = ("#d1fae5", "#059669") if gr == "accepted" else ("#fee2e2", "#dc2626")
            row = pill(f"● {gr.upper()}", gbg, gfg, "0.73rem")
            if fb:
                row += pill("fallback used", "#fef3c7", "#b45309", "0.62rem")
            st.markdown(row, unsafe_allow_html=True)
            st.markdown(
                f'<div class="iscroll" style="max-height:20px;">'
                f'{guard_decision.get("reason", "")}</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown('<div class="iscroll">guard_decision.json not found</div>', unsafe_allow_html=True)

    # ── Evaluation Result ────────────────────────────────────────────────────
    with st.container(height=H_EVAL, border=False, key="card_evaluation_result"):
        st.markdown(lbl("Evaluation Result"), unsafe_allow_html=True)
        if metrics:
            jdg    = metrics.get("judgment", "—")
            regret = metrics.get("regret_score")
            starv  = metrics.get("starvation_occurred", False)
            rec_nm = recommendation.get("recommended_scheduling_algorithm", "—") if recommendation else "—"
            tgt_m  = recommendation.get("target_metric", "avg_response_time") if recommendation else "avg_response_time"

            cmp = metrics.get("comparison", {})
            best_algo, best_val = "—", float("inf")
            for a, v in cmp.items():
                val = v.get(tgt_m)
                if isinstance(val, (int, float)) and val < best_val:
                    best_val, best_algo = val, a

            jbg = {"SUCCESS":"#d1fae5","NEAR-SUCCESS":"#dbeafe","FAIL":"#fee2e2"}.get(jdg,"#f1f5f9")
            jfg = {"SUCCESS":"#059669","NEAR-SUCCESS":"#1d4ed8","FAIL":"#dc2626"}.get(jdg,"#64748b")

            top = pill(jdg, jbg, jfg, "0.78rem")
            if regret is not None:
                top += pill(f"regret {regret:.2f}", "#f1f5f9", "#64748b", "0.62rem")
            top += pill(
                "Starv!" if starv else "No Starvation",
                "#fee2e2" if starv else "#d1fae5",
                "#dc2626" if starv else "#059669", "0.62rem",
            )
            st.markdown(top, unsafe_allow_html=True)
            st.markdown("<hr class='div'>", unsafe_allow_html=True)

            tgt_pretty   = tgt_m.replace("_", " ").title()
            rec_rt       = cmp.get(rec_nm, {}).get(tgt_m)
            rec_rt_str   = f"{rec_rt:.2f}" if isinstance(rec_rt, (int, float)) else "—"
            best_val_str = f"{best_val:.2f}" if best_val != float("inf") else "—"

            st.markdown(
                '<div style="display:grid;grid-template-columns:1fr 1fr;gap:4px 10px;margin-top:3px;">'
                f'<div><p style="font-size:0.53rem;color:#94a3b8;text-transform:uppercase;'
                f'letter-spacing:0.05em;margin:0;">Target</p>'
                f'<p style="font-size:0.69rem;color:#334155;margin:1px 0;">{tgt_pretty}</p></div>'
                f'<div><p style="font-size:0.53rem;color:#94a3b8;text-transform:uppercase;'
                f'letter-spacing:0.05em;margin:0;">Best Algo</p>'
                f'<p style="font-size:0.69rem;color:#059669;font-weight:700;margin:1px 0;">{best_algo}</p></div>'
                f'<div><p style="font-size:0.53rem;color:#94a3b8;text-transform:uppercase;'
                f'letter-spacing:0.05em;margin:0;">LLM Selected</p>'
                f'<p style="font-size:0.69rem;color:#7c3aed;font-weight:700;margin:1px 0;">{rec_nm}</p></div>'
                f'<div><p style="font-size:0.53rem;color:#94a3b8;text-transform:uppercase;'
                f'letter-spacing:0.05em;margin:0;">LLM → Best</p>'
                f'<p style="font-size:0.69rem;color:#334155;margin:1px 0;">{rec_rt_str} → {best_val_str}</p></div>'
                '</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown('<div class="iscroll">metrics.json not found</div>', unsafe_allow_html=True)

    # ── LLM Explanation ──────────────────────────────────────────────────────
    with st.container(height=H_EXPL, border=False, key="card_llm_explanation"):
        st.markdown(lbl("LLM Explanation"), unsafe_allow_html=True)
        if trace_explanation:
            pattern = trace_explanation.get("detected_pattern", "—")
            summary = trace_explanation.get("summary", "")
            mreason = trace_explanation.get("main_reason", "")
            evidence = trace_explanation.get("evidence", [])
            sugg    = trace_explanation.get("suggestion", "")
            applied = trace_explanation.get("runtime_corrections_applied", 0)

            top = pill(pattern, "#ede9fe", "#6d28d9")
            if applied:
                top += pill(f"⚡ {applied} fix(es)", "#fef3c7", "#b45309", "0.62rem")
            st.markdown(top, unsafe_allow_html=True)

            body = ""
            if summary:
                body += (
                    f'<b style="font-size:0.60rem;color:#64748b;text-transform:uppercase;'
                    f'letter-spacing:0.05em;">Summary</b><br>'
                    f'<span style="color:#334155;">{summary}</span><br><br>'
                )
            if mreason:
                body += (
                    f'<b style="font-size:0.60rem;color:#64748b;text-transform:uppercase;'
                    f'letter-spacing:0.05em;">Reason</b><br>'
                    f'<span style="color:#334155;">{mreason}</span><br><br>'
                )
            if evidence:
                lis = "".join(
                    f'<li style="margin-bottom:2px;color:#475569;">{e}</li>'
                    for e in evidence[:3]
                )
                body += (
                    f'<b style="font-size:0.60rem;color:#64748b;text-transform:uppercase;'
                    f'letter-spacing:0.05em;">Evidence</b>'
                    f'<ul style="margin:2px 0 3px -14px;padding:0;">{lis}</ul>'
                )
            if sugg:
                body += (
                    f'<span style="color:#1d4ed8;font-size:0.65rem;">'
                    f'<b>Suggestion:</b> {sugg}</span>'
                )
            st.markdown(
                f'<div class="iscroll" style="max-height:400px;">{body}</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown('<div class="iscroll">trace_explanation.json not found</div>', unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# CENTER COLUMN
# ═══════════════════════════════════════════════════════════════════════════════

def build_timeline(events: list[dict]) -> go.Figure:
    """Single horizontal segmented bar: [ P1 ][ P2 ][ P1 ][ P3 ]..."""
    segs = sorted(_build_segs(events, replay_tick), key=lambda s: s["start"])
    fig  = go.Figure()

    if not segs:
        fig.add_annotation(
            text="No trace data — move the tick slider →",
            x=0.5, y=0.5, xref="paper", yref="paper",
            showarrow=False, font=dict(color="#94a3b8", size=11),
        )

    seen: set = set()
    for seg in segs:
        pid = seg["pid"]
        dur = seg["end"] - seg["start"]
        if dur <= 0:
            continue
        clr = PROC_HEX.get(pid, "#94a3b8")
        fig.add_trace(go.Bar(
            x=[dur], y=["CPU"],
            base=[seg["start"]],
            orientation="h",
            marker_color=clr,
            marker_line_color="rgba(255,255,255,0.88)",
            marker_line_width=2,
            marker_opacity=0.90,
            showlegend=pid not in seen,
            name=f"P{pid}",
            legendgroup=f"P{pid}",
            text=f"P{pid}" if dur >= 3 else "",
            textposition="inside",
            insidetextanchor="middle",
            hovertemplate=(
                f"<b>P{pid}</b>  tick {seg['start']}→{seg['end']}"
                f"  ({dur} ticks)<extra></extra>"
            ),
        ))
        seen.add(pid)

    fig.add_vline(
        x=replay_tick, line_dash="dot",
        line_color="rgba(99,102,241,0.65)", line_width=2,
    )
    fig.update_layout(
        barmode="overlay",
        height=H_TIMELINE - 52,
        margin=dict(l=0, r=4, t=2, b=20),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(255,255,255,0.60)",
        font=dict(size=10, color="#5e6e8a"),
        uniformtext=dict(mode="hide", minsize=8),
        xaxis=dict(
            title="Tick", title_font=dict(size=10, color="#5e6e8a"),
            showgrid=True, gridcolor="rgba(100,116,139,0.10)",
            color="#5e6e8a", tickfont=dict(size=10), zeroline=False,
        ),
        yaxis=dict(
            showgrid=False, color="#5e6e8a", tickfont=dict(size=10),
        ),
        legend=dict(
            orientation="h", y=1.30, x=0,
            font=dict(size=9, color="#5e6e8a"),
            bgcolor="rgba(0,0,0,0)", borderwidth=0,
        ),
    )
    return fig


def build_live_lanes(events: list[dict]) -> go.Figure:
    """Compact per-process lane chart (right column)."""
    segs = _build_segs(events, replay_tick)
    fig  = go.Figure()

    if not segs:
        fig.add_annotation(
            text="No data", x=0.5, y=0.5, xref="paper", yref="paper",
            showarrow=False, font=dict(color="#94a3b8", size=10),
        )

    seen: set = set()
    for seg in sorted(segs, key=lambda s: s["pid"]):
        pid = seg["pid"]
        clr = PROC_HEX.get(pid, "#94a3b8")
        fig.add_trace(go.Bar(
            x=[seg["end"] - seg["start"]], y=[f"P{pid}"],
            base=[seg["start"]],
            orientation="h",
            marker_color=clr,
            marker_line_color="rgba(255,255,255,0.40)",
            marker_line_width=0.5,
            marker_opacity=0.85,
            showlegend=False,
            name=f"P{pid}",
            hovertemplate=f"<b>P{pid}</b> {seg['start']}→{seg['end']}<extra></extra>",
        ))
        seen.add(pid)

    fig.add_vline(
        x=replay_tick, line_dash="dot",
        line_color="rgba(99,102,241,0.55)", line_width=1.5,
    )
    fig.update_layout(
        barmode="overlay",
        height=H_LIVE - 46,
        margin=dict(l=0, r=2, t=2, b=14),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(255,255,255,0.60)",
        font=dict(size=9, color="#5e6e8a"),
        xaxis=dict(
            showgrid=True, gridcolor="rgba(100,116,139,0.10)",
            color="#5e6e8a", tickfont=dict(size=9), zeroline=False, title="",
        ),
        yaxis=dict(
            showgrid=False, autorange="reversed",
            color="#5e6e8a", tickfont=dict(size=9),
        ),
    )
    return fig


def proc_states_at(events: list[dict]) -> dict[int, str]:
    st_map: dict[int, str] = {}
    for ev in events:
        pid = ev.get("pid", -1)
        et  = ev.get("event", "")
        if pid < 0:
            continue
        if et in ("ARRIVE", "PREEMPT", "WAKEUP"):
            st_map[pid] = "Ready"
        elif et == "DISPATCH":
            st_map[pid] = "Running"
        elif et == "SLEEP":
            st_map[pid] = "Waiting"
        elif et == "EXIT":
            st_map[pid] = "Terminated"
    return st_map


def render_trace_notifications(events: list[dict]) -> str:
    """iPhone-style stacked notification cards + compact event log."""
    ET_ICON = {
        "DISPATCH": "▶", "PREEMPT": "⏸", "EXIT": "✓",
        "ARRIVE": "→", "WAKEUP": "↑",
        "QUEUE_CHANGE": "⇄", "CORRECTION_APPLIED": "⚡",
        "SLEEP": "💤",
    }
    ET_CLS = {
        "PREEMPT": "ev-preempt", "EXIT": "ev-exit",
        "ARRIVE": "ev-arrive", "CORRECTION_APPLIED": "ev-correction",
        "WAKEUP": "ev-wakeup",
    }
    ET_CLR = {
        "DISPATCH": "#6366f1", "PREEMPT": "#f43f5e", "EXIT": "#10b981",
        "ARRIVE": "#8b5cf6", "WAKEUP": "#0ea5e9",
        "QUEUE_CHANGE": "#f59e0b", "CORRECTION_APPLIED": "#f59e0b",
    }

    sorted_ev = sorted(events, key=lambda e: e.get("tick", 0), reverse=True)
    recent    = sorted_ev[:5]

    if not recent:
        return '<p style="font-size:0.65rem;color:#94a3b8;padding:4px 0;">No events yet — move the slider.</p>'

    # ── iPhone notification stack ──────────────────────────────────────────
    cards_html = ""
    for i, ev in enumerate(recent):
        depth  = min(i, 4)
        et     = ev.get("event", "?")
        pid    = ev.get("pid", "?")
        tk     = ev.get("tick", "?")
        state  = ev.get("state") or ""
        reason = ev.get("reason") or ""
        detail = " · ".join(filter(None, [state, reason]))
        icon   = ET_ICON.get(et, "·")
        pid_s  = f"P{pid}" if isinstance(pid, int) and pid > 0 else "SYS"
        clr    = PROC_HEX.get(pid if isinstance(pid, int) else -1, "#64748b")
        ev_cls = ET_CLS.get(et, "")

        cards_html += (
            f'<div class="notif-card depth-{depth} {ev_cls}">'
            f'<div class="nc-header">'
            f'<span class="nc-title" style="color:{clr};">{icon} {pid_s} — {et}</span>'
            f'<span class="nc-tick">tick {tk}</span>'
            f'</div>'
        )
        if i == 0 and detail:
            cards_html += f'<div class="nc-body">{detail}</div>'
        cards_html += '</div>'

    # ── Compact event log (all visible events, newest first) ───────────────
    log_rows = ""
    for ev in sorted_ev[:30]:
        et    = ev.get("event", "?")
        pid   = ev.get("pid", "?")
        tk    = ev.get("tick", "?")
        icon  = ET_ICON.get(et, "·")
        pid_s = f"P{pid}" if isinstance(pid, int) and pid > 0 else "SYS"
        pclr  = PROC_HEX.get(pid if isinstance(pid, int) else -1, "#94a3b8")
        eclr  = ET_CLR.get(et, "#64748b")
        log_rows += (
            f'<div style="display:flex;align-items:center;gap:6px;'
            f'padding:2px 0;border-bottom:1px solid rgba(100,120,170,0.06);">'
            f'<span style="color:{pclr};font-size:0.59rem;font-weight:700;'
            f'min-width:22px;">{pid_s}</span>'
            f'<span style="color:{eclr};font-size:0.58rem;flex:1;">{icon} {et}</span>'
            f'<span style="color:#b0b8cc;font-size:0.55rem;white-space:nowrap;">t{tk}</span>'
            f'</div>'
        )

    log_html = (
        f'<div class="iscroll" style="max-height:250px;margin-top:6px;">'
        f'{log_rows}'
        f'</div>'
    )

    return (
        f'<div class="notif-stack">{cards_html}</div>'
        f'<hr class="div">'
        f'{log_html}'
    )


with center:
    # ── Main Execution Timeline ───────────────────────────────────────────────
    with st.container(height=H_TIMELINE, border=False, key="card_main_gantt"):
        st.markdown(
            lbl(f"Gantt Chart · {sel_algo}")
            + f'<span style="font-size:0.57rem;color:#94a3b8;margin-left:5px;">'
            f'tick ≤ {replay_tick}</span>',
            unsafe_allow_html=True,
        )
        st.plotly_chart(
            build_timeline(visible),
            use_container_width=True,
            config={"displayModeBar": False},
        )

    # ── Process State ─────────────────────────────────────────────────────────
    with st.container(height=H_STATE, border=False, key="card_process_state"):
        st.markdown(lbl("Process State"), unsafe_allow_html=True)
        pstates = proc_states_at(visible)

        LANE_STYLE = {
            "Running":    ("rgba(219,234,254,0.82)", "#1d4ed8"),
            "Ready":      ("rgba(237,233,254,0.82)", "#7c3aed"),
            "Waiting":    ("rgba(254,243,199,0.82)", "#b45309"),
            "Terminated": ("rgba(241,245,249,0.82)", "#64748b"),
        }
        lanes = {k: [] for k in LANE_STYLE}
        for pid, sv in pstates.items():
            lanes.get(sv, lanes["Ready"]).append(pid)

        cols = st.columns(4)
        for idx, (lane_name, pids) in enumerate(lanes.items()):
            bg, fg = LANE_STYLE[lane_name]
            n = len(pids)
            count_html = (
                f'<div style="font-size:1.35rem;font-weight:800;color:{fg};'
                f'line-height:1;margin-bottom:6px;">{n}</div>'
            )
            circles_html = (
                "".join(circle(p, sz=26) for p in sorted(pids))
                if pids else
                '<span style="font-size:0.60rem;color:#94a3b8;font-style:italic;">empty</span>'
            )
            cols[idx].markdown(
                f'<div class="lane-card" style="background:{bg};">'
                f'<div class="lane-title" style="color:{fg};">{lane_name}</div>'
                f'{count_html}'
                f'{circles_html}</div>',
                unsafe_allow_html=True,
            )

    # ── Trace Events ──────────────────────────────────────────────────────────
    with st.container(height=H_TRACE, border=False, key="card_trace"):
        st.markdown(lbl("Trace Events · Latest 5"), unsafe_allow_html=True)
        st.markdown(render_trace_notifications(visible), unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# RIGHT COLUMN
# ═══════════════════════════════════════════════════════════════════════════════
comparison  = metrics.get("comparison", {}) if metrics else {}
rec_algo_nm = recommendation.get("recommended_scheduling_algorithm", "") if recommendation else ""
tgt_metric  = recommendation.get("target_metric", "avg_response_time") if recommendation else "avg_response_time"
tgt_compact = COMPACT_LABELS.get(tgt_metric, tgt_metric)


def make_df(col_list: list[str], label_map: dict[str, str]) -> pd.DataFrame:
    if not comparison:
        return pd.DataFrame()
    rows = []
    for algo, vals in comparison.items():
        row = {"Algo": algo}
        for col in col_list:
            row[label_map[col]] = _fmt_val(vals.get(col), col)
        rows.append(row)
    return pd.DataFrame(rows).astype(str)

df_compact = make_df(COMPACT_COLS, COMPACT_LABELS)
df_full    = make_df(ALL_COLS,     ALL_LABELS)


def render_table(df: pd.DataFrame, tgt_col: str) -> str:
    if df.empty:
        return '<p style="font-size:0.67rem;color:#64748b;">No data.</p>'
    th = ""
    for c in df.columns:
        hi = "background:rgba(99,102,241,0.09);" if c == tgt_col else ""
        th += (
            f'<th style="background:rgba(0,0,0,0.04);color:#5e6e8a;'
            f'font-size:0.54rem;font-weight:700;letter-spacing:0.06em;'
            f'text-transform:uppercase;padding:4px 7px;'
            f'border-bottom:1px solid rgba(100,120,170,0.12);'
            f'white-space:nowrap;{hi}">{c}</th>'
        )
    rows_html = ""
    for _, row in df.iterrows():
        is_rec = row["Algo"] == rec_algo_nm
        row_bg = "background:rgba(139,92,246,0.06);" if is_rec else ""
        cells  = ""
        for c in df.columns:
            val     = row[c]
            cell_bg = "background:rgba(99,102,241,0.05);" if (c == tgt_col and not is_rec) else ""
            color   = ""
            if c == "Judge":
                color = {
                    "SUCCESS":      "color:#059669;font-weight:700;",
                    "NEAR-SUCCESS": "color:#1d4ed8;",
                    "FAIL":         "color:#dc2626;",
                }.get(str(val), "")
            elif c == "Algo" and is_rec:
                color = "color:#7c3aed;font-weight:700;"
            elif c == "Starv":
                color = "color:#dc2626;" if val == "Yes" else "color:#059669;"
            cells += (
                f'<td style="padding:4px 7px;border-bottom:1px solid rgba(100,120,170,0.08);'
                f'font-size:0.64rem;color:#334155;{cell_bg}{color}white-space:nowrap;">'
                f'{val}</td>'
            )
        rows_html += f'<tr style="{row_bg}">{cells}</tr>'
    return (
        '<div style="overflow:auto;">'
        '<table style="width:100%;border-collapse:collapse;">'
        f'<thead><tr>{th}</tr></thead>'
        f'<tbody>{rows_html}</tbody>'
        '</table></div>'
    )


with right:
    # ── Live Process Lanes ────────────────────────────────────────────────────
    with st.container(height=H_LIVE, border=False, key="card_live_lanes"):
        st.markdown(
            lbl(f"Process Lanes · {sel_algo}")
            + f'<span style="font-size:0.55rem;color:#94a3b8;margin-left:5px;">'
            f'tick ≤ {replay_tick}</span>',
            unsafe_allow_html=True,
        )
        st.plotly_chart(
            build_live_lanes(visible),
            use_container_width=True,
            config={"displayModeBar": False},
        )

    # ── Workload Summary ──────────────────────────────────────────────────────
    with st.container(height=H_WL, border=False, key="card_workload_summary"):
        st.markdown(lbl("Workload Summary"), unsafe_allow_html=True)
        wl = workload_summary
        if wl:
            wl_type = wl.get("workload_type", "mixed")
            n_procs = wl.get("process_count", 5)
            tgt     = wl.get("target_metric", "avg_response_time")
            cpu_r   = wl.get("cpu_bound_ratio")
            ia_r    = wl.get("interactive_ratio")
            total_w = wl.get("total_cpu_work", "—")
            sr      = wl.get("has_starvation_risk", False)
            risks   = wl.get("main_risks", [])

            cpu_cnt = round(cpu_r * n_procs) if cpu_r is not None else None
            ia_cnt  = round(ia_r  * n_procs) if ia_r  is not None else None

            top = pill(wl_type.replace("_", " ").title(), "#ede9fe", "#6d28d9", "0.69rem")
            top += pill(f"{n_procs} procs", "#dbeafe", "#1d4ed8")
            top += pill(f"↳ {tgt.replace('_', ' ')}", "#d1fae5", "#059669")
            for r in risks:
                top += pill(r.replace("_", " "), "#fef3c7", "#b45309", "0.61rem")
            st.markdown(top, unsafe_allow_html=True)
            st.markdown("<hr class='div'>", unsafe_allow_html=True)

            wc1, wc2, wc3 = st.columns(3)
            wc1.metric(
                "CPU-bound",
                f"{cpu_cnt}p" if cpu_cnt is not None
                else (f"{cpu_r*100:.0f}%" if cpu_r is not None else "—"),
            )
            wc2.metric(
                "Interactive",
                f"{ia_cnt}p" if ia_cnt is not None
                else (f"{ia_r*100:.0f}%" if ia_r is not None else "—"),
            )
            wc3.metric("Total Work", f"{total_w}t" if total_w != "—" else "—")

            stav_clr = "#dc2626" if sr else "#059669"
            st.markdown(
                f'<p style="font-size:0.61rem;color:{stav_clr};margin:3px 0 0 0;">'
                f'{"⚠ Starvation Risk" if sr else "✓ No Starvation Risk"}</p>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown('<div class="iscroll">workload_summary.json not found</div>', unsafe_allow_html=True)

    # ── Algorithm Comparison ──────────────────────────────────────────────────
    with st.container(height=H_CMP, border=False, key="card_algorithm_comparison"):
        st.markdown(lbl("Algorithm Comparison"), unsafe_allow_html=True)
        if not df_compact.empty:
            st.markdown(render_table(df_compact, tgt_compact), unsafe_allow_html=True)
            st.markdown("<hr class='div'>", unsafe_allow_html=True)
            st.markdown(
                lbl("Full Metrics", "#94a3b8"),
                unsafe_allow_html=True,
            )
            st.markdown(
                render_table(df_full, ALL_LABELS.get(tgt_metric, tgt_metric)),
                unsafe_allow_html=True,
            )
        else:
            st.markdown('<div class="iscroll">No comparison data in metrics.json</div>', unsafe_allow_html=True)

    # ── Metric Visualization ──────────────────────────────────────────────────
    with st.container(height=H_BAR, border=False, key="card_metric_visualization"):
        st.markdown(lbl("Metric Visualization"), unsafe_allow_html=True)
        if not df_full.empty and comparison:
            sel_name = st.selectbox(
                "metric", BAR_METRIC_NAMES,
                index=BAR_METRIC_NAMES.index("Average Response Time"),
                key="bar_m", label_visibility="collapsed",
            )
            sel_key = BAR_METRIC_MAP[sel_name]
            sel_col = ALL_LABELS.get(sel_key, sel_key)

            bdf = df_full[["Algo", sel_col]].copy()
            bdf = bdf[bdf[sel_col] != "—"]
            bdf[sel_col] = pd.to_numeric(bdf[sel_col], errors="coerce")
            bdf = bdf.dropna(subset=[sel_col])

            bar = px.bar(
                bdf, x="Algo", y=sel_col,
                color="Algo",
                color_discrete_map={a: ALGO_HEX.get(a, "#94a3b8") for a in bdf["Algo"]},
                text=sel_col,
            )
            bar.update_traces(
                texttemplate="%{text:.2f}",
                textposition="outside",
                cliponaxis=False,
                marker_line_width=0,
                marker_opacity=0.88,
            )
            for trace in bar.data:
                if trace.name == rec_algo_nm:
                    trace.marker.opacity = 1.0
                    trace.marker.line.color = "#1e293b"
                    trace.marker.line.width = 1.8
            bar.update_layout(
                showlegend=False,
                height=H_BAR - 70,
                margin=dict(l=0, r=0, t=16, b=6),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(255,255,255,0.60)",
                font=dict(size=9, color="#5e6e8a"),
                yaxis=dict(
                    showgrid=True, gridcolor="rgba(100,116,139,0.10)",
                    title="", color="#5e6e8a", tickfont=dict(size=9), zeroline=False,
                ),
                xaxis=dict(
                    showgrid=False, title="",
                    color="#5e6e8a", tickfont=dict(size=9),
                ),
            )
            st.plotly_chart(bar, use_container_width=True,
                            config={"displayModeBar": False})
        else:
            st.markdown('<div class="iscroll">No comparison data.</div>', unsafe_allow_html=True)
