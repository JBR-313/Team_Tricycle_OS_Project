# LLM Sched Copilot — developer commands.
# These wrap the everyday checks so a new contributor doesn't have to memorize
# long invocations. The xv6 kernel has its OWN Makefile under xv6-riscv/.

PY      ?= python3
LIVE    := dashboard_live/public/live-data

.PHONY: help check test compile contract dashboard-build \
        demo-sim demo-xv6 final-demo-check check-secrets clean

help:  ## Show available commands
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

compile:  ## py_compile all Python modules + tests
	$(PY) -m py_compile tools/*.py scripts/*.py tests/*.py
	@echo "compile OK"

test:  ## Run the offline unit tests (needs pytest; no API key)
	$(PY) -m pytest tests/ -q

contract:  ## Strict dashboard data-contract validation on committed live-data
	$(PY) tools/validate_dashboard_contract.py --strict --dir $(LIVE)

dashboard-build:  ## Build the dashboard (production bundle)
	cd dashboard_live && npm run build

check: compile contract  ## Fast checks: compile + contract (no build, no xv6, no unit tests)
	@echo "check OK (unit tests NOT run — use 'make test'; full pre-demo gate: 'make final-demo-check')"

demo-sim:  ## Simulator pipeline smoke (offline fixture; no API key)
	$(PY) scripts/orchestrator.py --backend simulator --seed 42 \
	  --workload interactive --run-all --offline-fixture

demo-xv6:  ## Real xv6-under-QEMU pipeline (needs qemu + RISC-V toolchain + key)
	$(PY) scripts/orchestrator.py --backend xv6 --seed 42 \
	  --workload interactive --run-all

final-demo-check:  ## One-shot pre-demo PASS/FAIL health summary
	$(PY) scripts/final_demo_check.py

check-secrets:  ## Fail if a likely API key / .env is tracked by git
	@if git ls-files --error-unmatch .env >/dev/null 2>&1; then \
	  echo "ERROR: .env is tracked by git"; exit 1; fi
	@if git grep -nIE 'up_[A-Za-z0-9]{30,}' \
	   -- . ':!*.example' ':!*.md' >/dev/null 2>&1; then \
	  echo "ERROR: a possible Upstage API key (up_...) is committed"; \
	  git grep -nIE 'up_[A-Za-z0-9]{30,}' -- . ':!*.example' ':!*.md'; exit 1; \
	fi
	@echo "no committed secrets found"

clean:  ## Remove Python caches
	find . -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
	@echo "clean OK"
