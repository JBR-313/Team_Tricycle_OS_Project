#!/usr/bin/env bash
# Deterministic validation harness for xv6 scheduler implementation.
# Run from repository root:  bash scripts/check_xv6_scheduler.sh
# Enable boot test:          BOOT_TEST=1 bash scripts/check_xv6_scheduler.sh
set -euo pipefail

# ── paths ────────────────────────────────────────────────────────────────────
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
XV6_DIR="$REPO_ROOT/xv6-riscv"
KERNEL_DIR="$XV6_DIR/kernel"
LOG_DIR="$REPO_ROOT/outputs"
TS="$(date +%Y%m%d_%H%M%S)"
LOG_FILE="$LOG_DIR/check_xv6_scheduler_${TS}.log"

BOOT_TEST="${BOOT_TEST:-0}"
BOOT_TIMEOUT="${BOOT_TIMEOUT:-30}"

# ── helpers ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

_log() { echo "[$(date +%T)] $*" >> "$LOG_FILE"; }
ok()   { echo -e "${GREEN}[OK]${NC}   $1"; _log "OK:   $1"; }
info() { echo -e "${YELLOW}[INFO]${NC} $1"; _log "INFO: $1"; }
fail() {
    echo -e "${RED}[FAIL]${NC} $1" >&2
    _log "FAIL: $1"
    echo >&2
    echo "Log: $LOG_FILE" >&2
    exit 1
}

# ── init ─────────────────────────────────────────────────────────────────────
mkdir -p "$LOG_DIR"
_log "=== check_xv6_scheduler started ==="
echo "=== xv6 Scheduler Validation Harness ==="
echo "Repo : $REPO_ROOT"
echo "Log  : $LOG_FILE"
echo

# ── [1/6] repo root ──────────────────────────────────────────────────────────
echo "--- [1/6] Repo root ---"
[[ -d "$XV6_DIR" ]]          || fail "xv6-riscv/ not found — run from repository root"
[[ -f "$XV6_DIR/Makefile" ]] || fail "xv6-riscv/Makefile missing"
ok "Running from repo root: $REPO_ROOT"

# ── [2/6] required source files ──────────────────────────────────────────────
echo "--- [2/6] Required source files ---"
REQUIRED=(
    "$KERNEL_DIR/proc.c"
    "$KERNEL_DIR/proc.h"
    "$KERNEL_DIR/syscall.c"
    "$KERNEL_DIR/syscall.h"
    "$KERNEL_DIR/sysproc.c"
    "$KERNEL_DIR/defs.h"
    "$KERNEL_DIR/param.h"
)
for f in "${REQUIRED[@]}"; do
    [[ -f "$f" ]] || fail "Required file missing: $f"
    ok "Found $(basename "$f")"
done

# ── [3/6] toolchain ──────────────────────────────────────────────────────────
echo "--- [3/6] RISC-V toolchain ---"
command -v riscv64-unknown-elf-gcc &>/dev/null \
    || fail "riscv64-unknown-elf-gcc not in PATH — install RISC-V toolchain"
command -v qemu-system-riscv64 &>/dev/null \
    || fail "qemu-system-riscv64 not in PATH — install QEMU"
ok "riscv64-unknown-elf-gcc: $(riscv64-unknown-elf-gcc --version | head -1)"
ok "qemu-system-riscv64: $(qemu-system-riscv64 --version | head -1)"

# ── [4/6] scheduler syscall symbols (post-implementation check) ──────────────
echo "--- [4/6] Scheduler syscall symbols ---"

_check_grep() {
    local symbol="$1" file="$2"
    if grep -q "$symbol" "$file"; then
        ok "$symbol  →  $(basename "$file")"
    else
        fail "'$symbol' not found in $(basename "$file") — scheduler syscalls not yet implemented"
    fi
}

# syscall numbers defined in syscall.h
_check_grep "SYS_setscheduler" "$KERNEL_DIR/syscall.h"
_check_grep "SYS_getscheduler" "$KERNEL_DIR/syscall.h"
_check_grep "SYS_setpriority"  "$KERNEL_DIR/syscall.h"
_check_grep "SYS_getpriority"  "$KERNEL_DIR/syscall.h"

# dispatch table entries in syscall.c
_check_grep "sys_setscheduler" "$KERNEL_DIR/syscall.c"
_check_grep "sys_getscheduler" "$KERNEL_DIR/syscall.c"
_check_grep "sys_setpriority"  "$KERNEL_DIR/syscall.c"
_check_grep "sys_getpriority"  "$KERNEL_DIR/syscall.c"

# handler implementations in sysproc.c
_check_grep "sys_setscheduler" "$KERNEL_DIR/sysproc.c"
_check_grep "sys_getscheduler" "$KERNEL_DIR/sysproc.c"
_check_grep "sys_setpriority"  "$KERNEL_DIR/sysproc.c"
_check_grep "sys_getpriority"  "$KERNEL_DIR/sysproc.c"

# ── [5/6] build ──────────────────────────────────────────────────────────────
echo "--- [5/6] Build xv6 (CPUS=1) ---"
BUILD_LOG="$LOG_DIR/build_${TS}.log"
info "make clean && make CPUS=1  (log: $BUILD_LOG)"

if ! (cd "$XV6_DIR" && make clean && make CPUS=1) >"$BUILD_LOG" 2>&1; then
    echo "--- last 30 lines of build log ---" >&2
    tail -30 "$BUILD_LOG" >&2
    fail "Build failed — see $BUILD_LOG"
fi

[[ -f "$XV6_DIR/kernel/kernel" ]] || fail "Build exited 0 but kernel/kernel binary not found"
ok "Build succeeded"

# binary symbol check via nm
for sym in sys_setscheduler sys_getscheduler sys_setpriority sys_getpriority; do
    if riscv64-unknown-elf-nm "$XV6_DIR/kernel/kernel" 2>/dev/null | grep -q " [Tt] ${sym}$"; then
        ok "kernel symbol: $sym"
    else
        fail "Symbol '$sym' absent from compiled kernel — check linker / function visibility"
    fi
done

# ── [6/6] boot test (optional) ───────────────────────────────────────────────
echo "--- [6/6] Boot test (BOOT_TEST=${BOOT_TEST}) ---"

if [[ "$BOOT_TEST" == "1" ]]; then
    BOOT_LOG="$LOG_DIR/boot_${TS}.log"
    info "Booting xv6 (timeout ${BOOT_TIMEOUT}s)  →  $BOOT_LOG"

    [[ -f "$XV6_DIR/fs.img" ]] || fail "fs.img not found — run 'make' in xv6-riscv first"

    qemu-system-riscv64 \
        -machine virt -bios none \
        -kernel "$XV6_DIR/kernel/kernel" \
        -m 128M -smp 1 -nographic \
        -global virtio-mmio.force-legacy=false \
        -drive file="$XV6_DIR/fs.img",if=none,format=raw,id=x0 \
        -device virtio-blk-device,drive=x0,bus=virtio-mmio-bus.0 \
        >"$BOOT_LOG" 2>&1 &
    QEMU_PID=$!

    ELAPSED=0
    BOOTED=0
    while [[ $ELAPSED -lt $BOOT_TIMEOUT ]]; do
        if grep -q "init: starting sh" "$BOOT_LOG" 2>/dev/null; then
            BOOTED=1
            break
        fi
        sleep 1
        ELAPSED=$((ELAPSED + 1))
    done

    kill "$QEMU_PID" 2>/dev/null || true
    wait "$QEMU_PID" 2>/dev/null || true

    if [[ $BOOTED -eq 1 ]]; then
        ok "xv6 booted and reached shell (${ELAPSED}s)"
    elif grep -q "xv6 kernel" "$BOOT_LOG" 2>/dev/null; then
        info "Kernel started but shell not reached within ${BOOT_TIMEOUT}s — see $BOOT_LOG"
    else
        fail "No kernel output during boot — see $BOOT_LOG"
    fi
else
    info "Boot test skipped. Run with BOOT_TEST=1 to enable."
fi

# ── result ───────────────────────────────────────────────────────────────────
echo
_log "=== PASS ==="
echo -e "${GREEN}=== PASS ===${NC}  All checks passed."
echo "Log: $LOG_FILE"
