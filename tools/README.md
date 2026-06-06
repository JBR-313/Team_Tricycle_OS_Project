# tools/ — LLM Scheduling Advisor

[한국어](#---llm-스케줄링-어드바이저) | [English](#---llm-scheduling-advisor-1)

---

## 🇬🇧 — LLM Scheduling Advisor

The **tools** package is the decision layer of the Visual Scheduler system. It analyzes workload characteristics and recommends the optimal scheduling algorithm using Upstage Solar Pro 3 LLM.

```
workload_summary.json  ──►  llm_advisor.py  ──►  recommendation.json
                                  │  ▲
                                  │  └── feedback_rules.md (opt-in: --feedback only)
                                  ▼
                            solar_client.py  ──►  Upstage Solar Pro 3 API
```

**Key principle:** The LLM only *advises* — it never controls the scheduler directly. The recommendation is validated downstream before execution.

### Files

| File | Purpose |
|------|---------|
| `llm_advisor.py` | Entry point. Two modes: **advise** (workload → recommendation) and **feedback** (evaluation results → prompt rules). |
| `algorithm_guard.py` | Validates recommendation: algorithm, target metric, algorithm-metric compatibility, confidence, and parameter ranges. Outputs `guard_decision.json`. |
| `trace_explainer.py` | Explains a finished run in natural language: reads `trace.jsonl` + `metrics.json`, outputs `trace_explanation.json` (dashboard §7). |
| `solar_client.py` | Handles API communication with Upstage Solar Pro 3. |
| `__init__.py` | Package exports: `SolarClient`, `SolarError`, `load_env`. |
| `.env.example` | Template for `UPSTAGE_API_KEY` and optional settings. |

### Setup

```bash
cp tools/.env.example tools/.env
# Edit tools/.env and add your UPSTAGE_API_KEY
```

⚠️ `.env` is git-ignored — never commit your API key.

### Usage

```bash
# advise mode (default): outputs/workload_summary.json → outputs/recommendation.json
python3 tools/llm_advisor.py

# feedback mode: outputs/metrics.json → outputs/live/feedback_rules.md (only on judgment=FAIL)
python3 tools/llm_advisor.py --mode feedback
```

Optional arguments:
```bash
python3 tools/llm_advisor.py \
    --mode advise \
    --in outputs/workload_summary.json \
    --out outputs/recommendation.json \
    --feedback outputs/live/feedback_rules.md

python3 tools/llm_advisor.py \
    --mode feedback \
    --metrics outputs/metrics.json \
    --rec outputs/recommendation.json \
    --feedback outputs/live/feedback_rules.md
```

### Algorithm Guard

Validates LLM recommendations before scheduler execution:

```bash
python3 tools/algorithm_guard.py
```

Optional arguments:
```bash
python3 tools/algorithm_guard.py \
    --in recommendation.json \
    --out guard_decision.json
```

**What it validates:**
- Algorithm is in supported list: **FCFS, RR, PRIORITY, MLFQ, SJF, SRTF** (matches xv6 implementation scope)
- Metric is valid (`response_time`, `turnaround_time`, `waiting_time`, `throughput`, `starvation`, `fairness`). Unknown metrics are **not** rejected — the compatibility check is skipped with a warning so a sound recommendation is never sunk by an unrecognized metric word.
- Algorithm-metric pair is OS-theoretically sound (compatibility matrix)
- Parameters are in valid ranges per algorithm; out-of-range values are silently replaced with safe defaults (+ warning). For SJF/SRTF the predictor's `min`/`max`/`initial` cross-field rules are enforced too.

**Decision rules:**
- `compatibility_score < 0.4` → **rejected** (fallback to a safer algorithm for the target metric)
- `confidence < 0.3` → **rejected**
- `compatibility_score < 0.6` or `confidence < 0.5` → **accepted_with_warning**
- otherwise → **accepted**

**Outputs `guard_decision.json`:**
```json
{
  "guard_result": "accepted | accepted_with_warning | rejected",
  "algorithm": "MLFQ",
  "params": { "queues": 3, "quantum": [2, 4, 8], "aging_threshold": 100, "boost_interval": 100 },
  "target_metric": "response_time",
  "compatibility_score": 0.95,
  "confidence_score": 0.85,
  "reason": "Accepted: MLFQ is suitable for response_time (compat=0.95, confidence=0.85).",
  "fallback_algorithm": "MLFQ",
  "warnings": ["..."],
  "_meta": { ... }
}
```

`fallback_algorithm` and `warnings` appear only when relevant. When rejected, `params` is replaced with the fallback algorithm's defaults so downstream consumers (xv6, scheduler simulator) always receive a runnable configuration.

### Prompt Feedback Loop (feedback mode)

Reads `outputs/metrics.json` (produced by Role A's `metrics.py`). The `judgment` field decides whether a feedback rule is generated:

- `SUCCESS` / `NEAR-SUCCESS` → no action (rules file untouched)
- `FAIL` → query the LLM and overwrite `outputs/live/feedback_rules.md`

`FAIL` is set by Role A when `regret_score > 0.25` or `starvation_occurred = true` — see [`docs/evaluation_plan.md`](../docs/evaluation_plan.md) for the full criteria.

**`metrics.json` fields consumed**:
- `scheduling_algorithm`, `judgment`, `regret_score`, `starvation_occurred`
- `avg_response_time`, `avg_turnaround_time`, `avg_waiting_time`, `throughput`
- `max_waiting_time`, `preemption_count`

**`recommendation.json` (optional context)**:
If `outputs/recommendation.json` is present, its `target_metric`, `reason`, and `params` are added to the LLM prompt for richer rule generation. Absent file is non-fatal.

**Output** `outputs/live/feedback_rules.md` (canonical path) is overwritten with a flat Markdown bullet list plus a metadata header comment. This is **generation** only. The rules are injected into a future `advise` prompt **only when consumption is opted in** — i.e. when a `--feedback <path>` argument is passed (the orchestrator does this solely under its `--use-feedback` flag). Default runs pass no `--feedback`, so generated rules never affect the recommendation automatically.

### Trace Explainer

Explains a finished run in natural language for the dashboard.

```bash
python3 tools/trace_explainer.py \
    --trace outputs/trace.jsonl \
    --metrics outputs/metrics.json \
    --out outputs/trace_explanation.json
```

Reads the trace (compresses it to a per-process timeline + event counts) and, when present, `metrics.json` and `recommendation.json` for richer context. `metrics.json`/`recommendation.json` are optional — the trace alone is enough.

**Output `trace_explanation.json`** (schema in [`docs/dashboard_data_contract.md`](../docs/dashboard_data_contract.md) §7):
```json
{
  "scheduling_algorithm": "PRIORITY",
  "detected_pattern": "convoy_effect",
  "summary": "...",
  "main_reason": "...",
  "evidence": ["...", "..."],
  "suggestion": "...",
  "runtime_corrections_applied": 0
}
```

`runtime_corrections_applied` is taken from the trace (count of `CORRECTION_APPLIED` events), not the model.

### Recommendation Output Format (`recommendation.json`)

```json
{
  "algorithm": "MLFQ",
  "params": {
    "queues": 3,
    "quantum": [2, 4, 8],
    "aging_threshold": 50,
    "boost_interval": 100
  },
  "reason": "Mixed CPU/IO workload benefits from queue demotion plus aging.",
  "target_metric": "response_time",
  "confidence": 0.85,
  "_meta": {
    "source": "tools/llm_advisor.py",
    "model": "solar-pro3",
    "generated_at": "2026-05-21T00:00:00Z",
    "workload_summary": "workload_summary.json"
  }
}
```

### Supported Algorithms and Parameters

| Algorithm | Params schema | Notes |
|---|---|---|
| **FCFS** | `{}` (no params) | First-come-first-served, non-preemptive |
| **RR** | `{ "quantum": int [1, 100] }` | Round Robin baseline (default quantum = 10) |
| **PRIORITY** | `{ "aging_threshold": int [1, 10000] }` | With aging to mitigate starvation |
| **MLFQ** | `{ "queues": int [2, 5], "quantum": [int, ...] (length = queues, each [1, 100]), "aging_threshold": int [1, 10000], "boost_interval": int [10, 10000] }` | Multi-level feedback queue |
| **SJF** | `{ "alpha_percent": int [0, 100], "initial": int >=1, "min": int >=1, "max": int (>=min, <=100000) }` | Prediction-based, non-preemptive (exponential-averaging predictor) |
| **SRTF** | same as SJF | Prediction-based, preemptive variant of SJF |

SJF/SRTF use an exponential-averaging burst predictor — the LLM tunes only the predictor params, never the real future bursts (the kernel updates predictions from observed CPU usage only). The predictor's cross-field rules (`min <= max`, `initial` clamped into `[min, max]`) are enforced by the guard.

### Using SolarClient Directly

```python
from tools import SolarClient

client = SolarClient()  # reads UPSTAGE_API_KEY from .env

# Single response
answer = client.complete("Explain Priority Scheduling starvation.")

# Structured JSON response
recommendation = client.complete_json(
    prompt="...",
    system="Return only JSON with algorithm and reason."
)
```

### Smoke Test

```bash
python3 tools/solar_client.py
```

---

## 🇰🇷 — LLM 스케줄링 어드바이저

**tools** 패키지는 Visual Scheduler 시스템의 의사결정 계층입니다. Upstage Solar Pro 3 LLM을 사용하여 워크로드를 분석하고 최적의 스케줄링 알고리즘을 추천합니다.

```
workload_summary.json  ──►  llm_advisor.py  ──►  recommendation.json
                                  │  ▲
                                  │  └── feedback_rules.md (opt-in: --feedback 전달 시에만)
                                  ▼
                            solar_client.py  ──►  Upstage Solar Pro 3 API
```

**핵심 원칙:** LLM은 오직 *조언만* 제공합니다. 스케줄러를 직접 제어하지 않습니다. 추천 사항은 실행 전에 검증됩니다.

### 파일 구조

| 파일 | 역할 |
|------|------|
| `llm_advisor.py` | 진입점. 두 가지 모드: **advise** (워크로드 → 추천) 와 **feedback** (평가 결과 → 프롬프트 규칙). |
| `algorithm_guard.py` | 추천 검증. 알고리즘, 메트릭, 호환성, 신뢰도, 파라미터 범위를 검사하여 `guard_decision.json` 출력. |
| `trace_explainer.py` | 끝난 실행을 자연어로 설명. `trace.jsonl` + `metrics.json`을 읽어 `trace_explanation.json` 출력 (대시보드 §7). |
| `solar_client.py` | Upstage Solar Pro 3 API 통신 담당. |
| `__init__.py` | 패키지 공개: `SolarClient`, `SolarError`, `load_env`. |
| `.env.example` | `UPSTAGE_API_KEY` 및 선택사항 설정 템플릿. |

### 설정

```bash
cp tools/.env.example tools/.env
# tools/.env를 편집하여 UPSTAGE_API_KEY 추가
```

⚠️ `.env`는 git에서 무시됩니다 — API 키를 절대 커밋하지 마세요.

### 실행

```bash
# advise 모드 (기본): outputs/workload_summary.json → outputs/recommendation.json
python3 tools/llm_advisor.py

# feedback 모드: outputs/metrics.json → outputs/live/feedback_rules.md (judgment=FAIL일 때만)
python3 tools/llm_advisor.py --mode feedback
```

선택사항:
```bash
python3 tools/llm_advisor.py \
    --mode advise \
    --in outputs/workload_summary.json \
    --out outputs/recommendation.json \
    --feedback outputs/live/feedback_rules.md

python3 tools/llm_advisor.py \
    --mode feedback \
    --metrics outputs/metrics.json \
    --rec outputs/recommendation.json \
    --feedback outputs/live/feedback_rules.md
```

### Algorithm Guard

LLM 추천을 스케줄러 실행 전에 검증합니다.

```bash
python3 tools/algorithm_guard.py
```

**검증 항목:**
- 지원 알고리즘 목록에 있는지: **FCFS, RR, PRIORITY, MLFQ, SJF, SRTF** (xv6 구현 범위와 일치)
- 메트릭 유효성 (`response_time`, `turnaround_time`, `waiting_time`, `throughput`, `starvation`, `fairness`). 모르는 메트릭은 **거부하지 않고** 호환성 검사만 건너뜀(+경고) — 인식 못 하는 메트릭 단어 하나 때문에 멀쩡한 추천이 떨어지지 않도록.
- 알고리즘×메트릭 호환성 (OS 이론 기반 매트릭스)
- 알고리즘별 파라미터 범위 — 범위 밖이면 **기본값으로 자동 교체** + 경고. SJF/SRTF는 predictor의 `min`/`max`/`initial` 교차 검증도 수행

**판정 규칙:**
- `호환성 < 0.4` → **rejected** (메트릭에 더 적합한 알고리즘으로 fallback)
- `신뢰도 < 0.3` → **rejected**
- `호환성 < 0.6` 또는 `신뢰도 < 0.5` → **accepted_with_warning**
- 그 외 → **accepted**

reject 시에는 `params`도 fallback 알고리즘의 기본값으로 교체되어, 다운스트림 (xv6 / 시뮬레이터)이 항상 실행 가능한 설정을 받습니다.

### 프롬프트 피드백 루프 (feedback 모드)

`outputs/metrics.json` (Role A의 `metrics.py`가 생성)의 `judgment` 필드로 발동 여부를 결정합니다.

- `SUCCESS` / `NEAR-SUCCESS` → 아무 동작 안 함 (규칙 파일 그대로)
- `FAIL` → LLM에게 규칙 작성 요청 → `outputs/live/feedback_rules.md` 덮어쓰기

`FAIL` 조건은 `regret_score > 0.25` 또는 `starvation_occurred = true` (전체 기준은 [`docs/evaluation_plan.md`](../docs/evaluation_plan.md) 참고).

**`metrics.json`에서 읽는 필드**:
- `scheduling_algorithm`, `judgment`, `regret_score`, `starvation_occurred`
- `avg_response_time`, `avg_turnaround_time`, `avg_waiting_time`, `throughput`
- `max_waiting_time`, `preemption_count`

**`recommendation.json` (선택적 컨텍스트)**:
`outputs/recommendation.json`이 있으면 `target_metric`, `reason`, `params`도 LLM 프롬프트에 추가되어 더 정확한 규칙이 생성됩니다. 없어도 동작은 합니다.

**출력** `outputs/live/feedback_rules.md`(정규 경로)는 LLM이 생성한 마크다운 불릿 규칙 목록 + 메타데이터 헤더로 덮어쓰기 됩니다. 이는 **생성(generation)**일 뿐입니다. 규칙이 이후 advise 프롬프트에 주입되는 것은 **소비(consumption)를 명시적으로 켰을 때만** — 즉 `--feedback <경로>` 인자가 전달될 때만 일어납니다(오케스트레이터는 `--use-feedback` 플래그에서만 이 인자를 전달). 기본 실행은 `--feedback`을 전달하지 않으므로 생성된 규칙이 추천에 자동으로 영향을 주지 않습니다.

### Trace Explainer

끝난 실행을 대시보드용 자연어로 설명합니다.

```bash
python3 tools/trace_explainer.py \
    --trace outputs/trace.jsonl \
    --metrics outputs/metrics.json \
    --out outputs/trace_explanation.json
```

트레이스를 프로세스별 타임라인 + 이벤트 카운트로 압축하고, 있으면 `metrics.json`/`recommendation.json`을 컨텍스트로 추가합니다. 둘 다 선택사항 — 트레이스만 있어도 동작합니다.

**출력 `trace_explanation.json`** (스키마는 [`docs/dashboard_data_contract.md`](../docs/dashboard_data_contract.md) §7):
```json
{
  "scheduling_algorithm": "PRIORITY",
  "detected_pattern": "convoy_effect",
  "summary": "...",
  "main_reason": "...",
  "evidence": ["...", "..."],
  "suggestion": "...",
  "runtime_corrections_applied": 0
}
```

`runtime_corrections_applied`는 모델이 아니라 트레이스의 `CORRECTION_APPLIED` 이벤트 수에서 가져옵니다.

### 추천 출력 형식 (`recommendation.json`)

```json
{
  "algorithm": "MLFQ",
  "params": {
    "queues": 3,
    "quantum": [2, 4, 8],
    "aging_threshold": 50,
    "boost_interval": 100
  },
  "reason": "혼합 CPU/IO 워크로드는 큐 강등 + 에이징으로 이득을 봅니다.",
  "target_metric": "response_time",
  "confidence": 0.85,
  "_meta": {
    "source": "tools/llm_advisor.py",
    "model": "solar-pro3",
    "generated_at": "2026-05-21T00:00:00Z",
    "workload_summary": "workload_summary.json"
  }
}
```

### 지원 알고리즘 및 파라미터

| 알고리즘 | params 스키마 | 비고 |
|---|---|---|
| **FCFS** | `{}` (파라미터 없음) | 비선점, 도착 순서대로 |
| **RR** | `{ "quantum": int [1, 100] }` | 베이스라인 (기본 quantum = 10) |
| **PRIORITY** | `{ "aging_threshold": int [1, 10000] }` | 에이징으로 기아 완화 |
| **MLFQ** | `{ "queues": int [2, 5], "quantum": [int, ...] (길이 = queues, 각 [1, 100]), "aging_threshold": int [1, 10000], "boost_interval": int [10, 10000] }` | 다단계 피드백 큐 |
| **SJF** | `{ "alpha_percent": int [0, 100], "initial": int >=1, "min": int >=1, "max": int (>=min, <=100000) }` | 예측 기반, 비선점 (지수 평균 predictor) |
| **SRTF** | SJF와 동일 | 예측 기반, SJF의 선점 버전 |

SJF/SRTF는 지수 평균 버스트 predictor를 사용합니다 — LLM은 predictor 파라미터만 추천하고, 실제 미래 버스트는 절대 받지 않습니다 (커널이 관측된 CPU 사용량으로만 예측 갱신). predictor의 교차 검증(`min <= max`, `initial`을 `[min, max]`로 clamp)은 guard가 수행합니다.

### SolarClient 직접 사용

```python
from tools import SolarClient

client = SolarClient()  # .env에서 UPSTAGE_API_KEY 읽기

# 텍스트 응답
answer = client.complete("Priority Scheduling의 기아 현상을 설명하세요.")

# 구조화된 JSON 응답
recommendation = client.complete_json(
    prompt="...",
    system="algorithm과 reason만 포함한 JSON을 반환하세요."
)
```

### 동작 확인

```bash
python3 tools/solar_client.py
```

---

**Last updated:** 2026-05-24
