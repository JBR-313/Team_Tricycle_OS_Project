# tools/ — LLM Scheduling Advisor

[한국어](#---llm-스케줄링-어드바이저) | [English](#---llm-scheduling-advisor-1)

---

## 🇬🇧 — LLM Scheduling Advisor

The **tools** package is the decision layer of the Visual Scheduler system. It analyzes workload characteristics and recommends the optimal scheduling algorithm using Upstage Solar Pro 3 LLM.

```
workload_summary.json  ──►  llm_advisor.py  ──►  recommendation.json
                                  │  ▲
                                  │  └── prompt_feedback_rules.md (optional)
                                  ▼
                            solar_client.py  ──►  Upstage Solar Pro 3 API
```

**Key principle:** The LLM only *advises* — it never controls the scheduler directly. The recommendation is validated downstream before execution.

### Files

| File | Purpose |
|------|---------|
| `llm_advisor.py` | Entry point. Reads workload, calls LLM, outputs recommendation. |
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
python3 tools/llm_advisor.py
```

Optional arguments:
```bash
python3 tools/llm_advisor.py \
    --in workload_summary.json \
    --out recommendation.json \
    --feedback prompt_feedback_rules.md
```

### Output Format

```json
{
  "algorithm": "RR",
  "reason": "Mixed CPU/IO workload benefits from time-sharing",
  "target_metric": "response_time",
  "confidence": 0.85,
  "_meta": {
    "source": "tools/llm_advisor.py",
    "model": "solar-pro3",
    "generated_at": "2026-05-19T10:30:00Z",
    "workload_summary": "workload_summary.json"
  }
}
```

### Supported Algorithms

- **FCFS** (First-Come-First-Served)
- **RR** (Round-Robin)
- **Priority**
- **MLFQ** (Multi-Level Feedback Queue)

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
                                  │  └── prompt_feedback_rules.md (선택사항)
                                  ▼
                            solar_client.py  ──►  Upstage Solar Pro 3 API
```

**핵심 원칙:** LLM은 오직 *조언만* 제공합니다. 스케줄러를 직접 제어하지 않습니다. 추천 사항은 실행 전에 검증됩니다.

### 파일 구조

| 파일 | 역할 |
|------|------|
| `llm_advisor.py` | 진입점. 워크로드를 읽고 LLM을 호출하여 추천사항을 출력합니다. |
| `solar_client.py` | Upstage Solar Pro 3 API와의 통신을 담당합니다. |
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
python3 tools/llm_advisor.py
```

선택사항:
```bash
python3 tools/llm_advisor.py \
    --in workload_summary.json \
    --out recommendation.json \
    --feedback prompt_feedback_rules.md
```

### 출력 형식

```json
{
  "algorithm": "RR",
  "reason": "혼합 CPU/IO 워크로드는 시간 공유 방식의 이점을 가집니다",
  "target_metric": "response_time",
  "confidence": 0.85,
  "_meta": {
    "source": "tools/llm_advisor.py",
    "model": "solar-pro3",
    "generated_at": "2026-05-19T10:30:00Z",
    "workload_summary": "workload_summary.json"
  }
}
```

### 지원 알고리즘

- **FCFS** (First-Come-First-Served, 먼저 온 순서대로)
- **RR** (Round-Robin, 시간 할당량)
- **Priority** (우선순위)
- **MLFQ** (다단계 피드백 큐)

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

**Last updated:** 2026-05-19
