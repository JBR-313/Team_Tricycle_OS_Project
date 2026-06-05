#include "types.h"
#include "param.h"
#include "memlayout.h"
#include "riscv.h"
#include "spinlock.h"
#include "proc.h"
#include "defs.h"

struct cpu cpus[NCPU];

struct proc proc[NPROC];

struct proc *initproc;

int nextpid = 1;
struct spinlock pid_lock;

extern void forkret(void);
static void freeproc(struct proc *p);

extern char trampoline[]; // trampoline.S

// helps ensure that wakeups of wait()ing
// parents are not lost. helps obey the
// memory model when using p->parent.
// must be acquired before any p->lock.
struct spinlock wait_lock;

// Global scheduler mode; write via set_sched_mode(), read without lock (safe
// on CPUS=1; a slightly stale read on multi-CPU is non-catastrophic here).
int sched_mode = SCHED_RR;
struct spinlock sched_lock;

// Global burst-predictor parameters for SJF/SRTF.  The LLM recommends these
// before execution; they are applied via set_predictor_params() (validated in
// the syscall layer).  Only predictions are derived from these values — actual
// future CPU bursts are never stored or consulted.  Written under sched_lock;
// read without a lock following the same convention as sched_mode above.
struct predictor_params {
  int alpha_percent;            // exponential-averaging weight, 0..100
  int initial_predicted_burst;  // prediction assigned to a brand-new process
  int min_predicted_burst;      // lower clamp for predictions
  int max_predicted_burst;      // upper clamp for predictions
};
struct predictor_params pred = {50, 10, 1, 100};

// ── Dynamic scheduler parameters (RR / Priority / MLFQ) ─────────────────────
// The LLM recommends these before execution; Algorithm Guard validates/clamps
// them; user/schedtest.c applies them via syscalls BEFORE the workload starts.
// Unlike the burst predictor they steer real dispatch decisions, but they are
// still plain configuration applied once per run — the LLM never runs in the
// scheduler hot path and never picks the next process. Written under sched_lock,
// read locklessly (CPUS=1 convention, same as sched_mode above).
int rr_quantum = 1;                 // RR: timer ticks per round (1..100)
int priority_aging_threshold = 10;  // Priority: rounds waiting before aging

#define MLFQ_MAX_QUEUES 5
struct mlfq_config {
  int queues;                       // active queue count (2..MLFQ_MAX_QUEUES)
  int quantum[MLFQ_MAX_QUEUES];     // per-level time slice in ticks
  int boost_interval;               // rounds waiting before promotion to Q0
};
// Default preserves the historical fixed behavior exactly: 3 queues, quanta
// {2,4,8}, boost every 20 rounds.  Unused high slots stay valid (>=1).
struct mlfq_config mlfq_cfg = {3, {2, 4, 8, 8, 8}, 20};

// Allocate a page for each process's kernel stack.
// Map it high in memory, followed by an invalid
// guard page.
void
proc_mapstacks(pagetable_t kpgtbl)
{
  struct proc *p;

  for(p = proc; p < &proc[NPROC]; p++) {
    char *pa = kalloc();
    if(pa == 0)
      panic("kalloc");
    uint64 va = KSTACK((int) (p - proc));
    kvmmap(kpgtbl, va, (uint64)pa, PGSIZE, PTE_R | PTE_W);
  }
}

// initialize the proc table.
void
procinit(void)
{
  struct proc *p;

  initlock(&pid_lock, "nextpid");
  initlock(&wait_lock, "wait_lock");
  initlock(&sched_lock, "sched");
  for(p = proc; p < &proc[NPROC]; p++) {
      initlock(&p->lock, "proc");
      p->state = UNUSED;
      p->kstack = KSTACK((int) (p - proc));
  }
}

// Must be called with interrupts disabled,
// to prevent race with process being moved
// to a different CPU.
int
cpuid()
{
  int id = r_tp();
  return id;
}

// Return this CPU's cpu struct.
// Interrupts must be disabled.
struct cpu*
mycpu(void)
{
  int id = cpuid();
  struct cpu *c = &cpus[id];
  return c;
}

// Return the current struct proc *, or zero if none.
struct proc*
myproc(void)
{
  push_off();
  struct cpu *c = mycpu();
  struct proc *p = c->proc;
  pop_off();
  return p;
}

int
allocpid()
{
  int pid;

  acquire(&pid_lock);
  pid = nextpid;
  nextpid = nextpid + 1;
  release(&pid_lock);

  return pid;
}

// Look in the process table for an UNUSED proc.
// If found, initialize state required to run in the kernel,
// and return with p->lock held.
// If there are no free procs, or a memory allocation fails, return 0.
static struct proc*
allocproc(void)
{
  struct proc *p;

  for(p = proc; p < &proc[NPROC]; p++) {
    acquire(&p->lock);
    if(p->state == UNUSED) {
      goto found;
    } else {
      release(&p->lock);
    }
  }
  return 0;

found:
  p->pid = allocpid();
  p->state = USED;

  // Initialize scheduler fields.
  p->priority     = 10;
  p->ctime        = (int)ticks;
  p->rtime        = 0;
  p->queue_level  = 0;
  p->ticks_in_level = 0;
  p->wait_ticks   = 0;

  // Initialize burst-prediction fields.  A new process starts with the
  // configured initial prediction; nothing about its true future burst is known.
  p->predicted_burst  = pred.initial_predicted_burst;
  if(p->predicted_burst < pred.min_predicted_burst)
    p->predicted_burst = pred.min_predicted_burst;
  if(p->predicted_burst > pred.max_predicted_burst)
    p->predicted_burst = pred.max_predicted_burst;
  p->cur_burst_run    = 0;
  p->ready_since_tick = (int)ticks;

  // Allocate a trapframe page.
  if((p->trapframe = (struct trapframe *)kalloc()) == 0){
    freeproc(p);
    release(&p->lock);
    return 0;
  }

  // An empty user page table.
  p->pagetable = proc_pagetable(p);
  if(p->pagetable == 0){
    freeproc(p);
    release(&p->lock);
    return 0;
  }

  // Set up new context to start executing at forkret,
  // which returns to user space.
  memset(&p->context, 0, sizeof(p->context));
  p->context.ra = (uint64)forkret;
  p->context.sp = p->kstack + PGSIZE;

  return p;
}

// free a proc structure and the data hanging from it,
// including user pages.
// p->lock must be held.
static void
freeproc(struct proc *p)
{
  if(p->trapframe)
    kfree((void*)p->trapframe);
  p->trapframe = 0;
  if(p->pagetable)
    proc_freepagetable(p->pagetable, p->sz);
  p->pagetable = 0;
  p->sz = 0;
  p->pid = 0;
  p->parent = 0;
  p->name[0] = 0;
  p->chan = 0;
  p->killed = 0;
  p->xstate = 0;
  p->state = UNUSED;
  // reset scheduler fields
  p->priority     = 0;
  p->ctime        = 0;
  p->rtime        = 0;
  p->queue_level  = 0;
  p->ticks_in_level = 0;
  p->wait_ticks   = 0;
  p->predicted_burst  = 0;
  p->cur_burst_run    = 0;
  p->ready_since_tick = 0;
}

// Create a user page table for a given process, with no user memory,
// but with trampoline and trapframe pages.
pagetable_t
proc_pagetable(struct proc *p)
{
  pagetable_t pagetable;

  // An empty page table.
  pagetable = uvmcreate();
  if(pagetable == 0)
    return 0;

  // map the trampoline code (for system call return)
  // at the highest user virtual address.
  // only the supervisor uses it, on the way
  // to/from user space, so not PTE_U.
  if(mappages(pagetable, TRAMPOLINE, PGSIZE,
              (uint64)trampoline, PTE_R | PTE_X) < 0){
    uvmfree(pagetable, 0);
    return 0;
  }

  // map the trapframe page just below the trampoline page, for
  // trampoline.S.
  if(mappages(pagetable, TRAPFRAME, PGSIZE,
              (uint64)(p->trapframe), PTE_R | PTE_W) < 0){
    uvmunmap(pagetable, TRAMPOLINE, 1, 0);
    uvmfree(pagetable, 0);
    return 0;
  }

  return pagetable;
}

// Free a process's page table, and free the
// physical memory it refers to.
void
proc_freepagetable(pagetable_t pagetable, uint64 sz)
{
  uvmunmap(pagetable, TRAMPOLINE, 1, 0);
  uvmunmap(pagetable, TRAPFRAME, 1, 0);
  uvmfree(pagetable, sz);
}

// Set up first user process.
void
userinit(void)
{
  struct proc *p;

  p = allocproc();
  initproc = p;

  p->cwd = namei("/");

  p->state = RUNNABLE;

  release(&p->lock);
}

// Grow or shrink user memory by n bytes.
// Return 0 on success, -1 on failure.
int
growproc(int n)
{
  uint64 sz;
  struct proc *p = myproc();

  sz = p->sz;
  if(n > 0){
    if(sz + n > TRAPFRAME) {
      return -1;
    }
    if((sz = uvmalloc(p->pagetable, sz, sz + n, PTE_W)) == 0) {
      return -1;
    }
  } else if(n < 0){
    sz = uvmdealloc(p->pagetable, sz, sz + n);
  }
  p->sz = sz;
  return 0;
}

// Create a new process, copying the parent.
// Sets up child kernel stack to return as if from fork() system call.
int
kfork(void)
{
  int i, pid;
  struct proc *np;
  struct proc *p = myproc();

  // Allocate process.
  if((np = allocproc()) == 0){
    return -1;
  }

  // Copy user memory from parent to child.
  if(uvmcopy(p->pagetable, np->pagetable, p->sz) < 0){
    freeproc(np);
    release(&np->lock);
    return -1;
  }
  np->sz = p->sz;

  // copy saved user registers.
  *(np->trapframe) = *(p->trapframe);

  // Cause fork to return 0 in the child.
  np->trapframe->a0 = 0;

  // increment reference counts on open file descriptors.
  for(i = 0; i < NOFILE; i++)
    if(p->ofile[i])
      np->ofile[i] = filedup(p->ofile[i]);
  np->cwd = idup(p->cwd);

  safestrcpy(np->name, p->name, sizeof(p->name));

  // Child inherits parent priority.
  np->priority = p->priority;

  pid = np->pid;

  release(&np->lock);

  acquire(&wait_lock);
  np->parent = p;
  release(&wait_lock);

  acquire(&np->lock);
  np->state = RUNNABLE;
  release(&np->lock);

  return pid;
}

// Pass p's abandoned children to init.
// Caller must hold wait_lock.
void
reparent(struct proc *p)
{
  struct proc *pp;

  for(pp = proc; pp < &proc[NPROC]; pp++){
    if(pp->parent == p){
      pp->parent = initproc;
      wakeup(initproc);
    }
  }
}

// Exit the current process.  Does not return.
// An exited process remains in the zombie state
// until its parent calls wait().
void
kexit(int status)
{
  struct proc *p = myproc();

  if(p == initproc)
    panic("init exiting");

  // Close all open files.
  for(int fd = 0; fd < NOFILE; fd++){
    if(p->ofile[fd]){
      struct file *f = p->ofile[fd];
      fileclose(f);
      p->ofile[fd] = 0;
    }
  }

  begin_op();
  iput(p->cwd);
  end_op();
  p->cwd = 0;

  acquire(&wait_lock);

  // Give any children to init.
  reparent(p);

  // Parent might be sleeping in wait().
  wakeup(p->parent);

  acquire(&p->lock);

  // Emit a parseable EXIT event (sched_mode is read locklessly, as in scheduler()).
  sched_trace(sched_mode, "EXIT", p->pid, "ZOMBIE", p->queue_level, p->priority, 0);

  p->xstate = status;
  p->state = ZOMBIE;

  release(&wait_lock);

  // Jump into the scheduler, never to return.
  sched();
  panic("zombie exit");
}

// Wait for a child process to exit and return its pid.
// Return -1 if this process has no children.
int
kwait(uint64 addr)
{
  struct proc *pp;
  int havekids, pid;
  struct proc *p = myproc();

  acquire(&wait_lock);

  for(;;){
    // Scan through table looking for exited children.
    havekids = 0;
    for(pp = proc; pp < &proc[NPROC]; pp++){
      if(pp->parent == p){
        // make sure the child isn't still in exit() or swtch().
        acquire(&pp->lock);

        havekids = 1;
        if(pp->state == ZOMBIE){
          // Found one.
          pid = pp->pid;
          if(addr != 0 && copyout(p->pagetable, addr, (char *)&pp->xstate,
                                  sizeof(pp->xstate)) < 0) {
            release(&pp->lock);
            release(&wait_lock);
            return -1;
          }
          freeproc(pp);
          release(&pp->lock);
          release(&wait_lock);
          return pid;
        }
        release(&pp->lock);
      }
    }

    // No point waiting if we don't have any children.
    if(!havekids || killed(p)){
      release(&wait_lock);
      return -1;
    }

    // Wait for a child to exit.
    sleep(p, &wait_lock);  //DOC: wait-sleep
  }
}

// ── Scheduler public API ──────────────────────────────────────────────────────

int
get_sched_mode(void)
{
  return sched_mode;
}

void
set_sched_mode(int mode)
{
  acquire(&sched_lock);
  sched_mode = mode;
  release(&sched_lock);
}

// ── Dynamic scheduler-parameter API (RR / Priority / MLFQ) ──────────────────
// All setters validate ranges (mirroring Algorithm Guard) and return 0 on
// success, -1 on rejection.  Getters read locklessly (CPUS=1 convention).

int
get_rr_quantum(void)
{
  return rr_quantum;
}

int
set_rr_quantum(int quantum)
{
  if(quantum < 1 || quantum > 100)
    return -1;
  acquire(&sched_lock);
  rr_quantum = quantum;
  release(&sched_lock);
  return 0;
}

int
get_priority_aging_threshold(void)
{
  return priority_aging_threshold;
}

int
set_priority_aging_threshold(int threshold)
{
  if(threshold < 1 || threshold > 10000)
    return -1;
  acquire(&sched_lock);
  priority_aging_threshold = threshold;
  release(&sched_lock);
  return 0;
}

int
get_mlfq_queues(void)
{
  return mlfq_cfg.queues;
}

// Quantum for a given queue level; clamps out-of-range levels to the lowest
// active queue so trap.c can call it without bounds-checking first.
int
get_mlfq_quantum(int level)
{
  if(level < 0)
    level = 0;
  if(level >= mlfq_cfg.queues)
    level = mlfq_cfg.queues - 1;
  return mlfq_cfg.quantum[level];
}

int
get_mlfq_boost_interval(void)
{
  return mlfq_cfg.boost_interval;
}

// Configure the MLFQ queue structure.  Up to MLFQ_MAX_QUEUES (5) levels are
// supported with one int per quantum so the syscall stays within xv6's 6-arg
// limit.  Only the first `queues` quanta are used; the rest are kept valid.
int
set_mlfq_params(int queues, int q0, int q1, int q2, int q3, int q4)
{
  if(queues < 2 || queues > MLFQ_MAX_QUEUES)
    return -1;
  int q[MLFQ_MAX_QUEUES] = {q0, q1, q2, q3, q4};
  for(int i = 0; i < queues; i++)
    if(q[i] < 1 || q[i] > 100)
      return -1;
  acquire(&sched_lock);
  mlfq_cfg.queues = queues;
  for(int i = 0; i < MLFQ_MAX_QUEUES; i++)
    mlfq_cfg.quantum[i] = (i < queues) ? q[i] : q[queues - 1];
  release(&sched_lock);
  return 0;
}

int
set_mlfq_boost(int boost_interval)
{
  if(boost_interval < 1 || boost_interval > 10000)
    return -1;
  acquire(&sched_lock);
  mlfq_cfg.boost_interval = boost_interval;
  release(&sched_lock);
  return 0;
}

int
get_proc_priority(int pid)
{
  struct proc *p;
  for(p = proc; p < &proc[NPROC]; p++){
    acquire(&p->lock);
    if(p->pid == pid){
      int pri = p->priority;
      release(&p->lock);
      return pri;
    }
    release(&p->lock);
  }
  return -1;
}

int
set_proc_priority(int pid, int priority)
{
  struct proc *p;
  for(p = proc; p < &proc[NPROC]; p++){
    acquire(&p->lock);
    if(p->pid == pid){
      p->priority = priority;
      release(&p->lock);
      return 0;
    }
    release(&p->lock);
  }
  return -1;
}

// ── Burst predictor API (SJF/SRTF) ─────────────────────────────────────────────

// Apply LLM-recommended predictor parameters.  Arguments are assumed already
// range-validated by the syscall layer (Algorithm Guard / sys_setpredictor).
// Returns 0 on success, -1 if the ranges are inconsistent.
int
set_predictor_params(int alpha_percent, int initial, int min_b, int max_b)
{
  if(alpha_percent < 0 || alpha_percent > 100)
    return -1;
  if(min_b < 1 || max_b < min_b)
    return -1;
  if(initial < min_b) initial = min_b;
  if(initial > max_b) initial = max_b;

  acquire(&sched_lock);
  pred.alpha_percent           = alpha_percent;
  pred.initial_predicted_burst = initial;
  pred.min_predicted_burst     = min_b;
  pred.max_predicted_burst     = max_b;
  release(&sched_lock);
  return 0;
}

// Return the current predicted next-burst length for a pid, or -1 if not found.
// This is a prediction (an observable quantity), never the true future burst.
int
get_predicted_burst(int pid)
{
  struct proc *p;
  for(p = proc; p < &proc[NPROC]; p++){
    acquire(&p->lock);
    if(p->pid == pid){
      int pb = p->predicted_burst;
      release(&p->lock);
      return pb;
    }
    release(&p->lock);
  }
  return -1;
}

// Apply an LLM-generated INITIAL burst prior to a specific process (SJF/SRTF).
// Used by the schedtest demo path: the parent calls this right after fork, so
// the child's first SJF/SRTF decision uses the hint instead of the generic
// initial prediction.  The value is clamped into the predictor's [min,max]; the
// true future burst is never read or stored.  Returns 0 on success, -1 if the
// pid is not found or predicted_burst < 1.
int
set_burst_hint(int pid, int predicted_burst)
{
  if(predicted_burst < 1)
    return -1;

  acquire(&sched_lock);
  int lo = pred.min_predicted_burst;
  int hi = pred.max_predicted_burst;
  release(&sched_lock);
  if(predicted_burst < lo) predicted_burst = lo;
  if(predicted_burst > hi) predicted_burst = hi;

  struct proc *p;
  for(p = proc; p < &proc[NPROC]; p++){
    acquire(&p->lock);
    if(p->pid == pid){
      p->predicted_burst = predicted_burst;  // initial prior only; no future burst
      release(&p->lock);
      return 0;
    }
    release(&p->lock);
  }
  return -1;
}

// Update a process's burst prediction at the end of an observed CPU burst,
// using integer exponential averaging:
//   new = (alpha*observed + (100-alpha)*old) / 100
// Only the already-observed burst length (cur_burst_run) feeds the update; the
// true future burst is never used.  Caller must hold p->lock.
static void
update_burst_prediction(struct proc *p)
{
  int observed = p->cur_burst_run;
  if(observed <= 0)
    return;  // no CPU was actually consumed; keep the prior prediction

  int a   = pred.alpha_percent;
  int lo  = pred.min_predicted_burst;
  int hi  = pred.max_predicted_burst;
  int old = p->predicted_burst;
  int np  = (a * observed + (100 - a) * old) / 100;
  if(np < lo) np = lo;
  if(np > hi) np = hi;

  p->predicted_burst = np;
  p->cur_burst_run   = 0;

  // Observability for the predictor demo.  `observed` is already-consumed CPU
  // time, never a future burst, so emitting it leaks nothing.  Limited to the
  // predictor schedulers to keep the other algorithms' traces clean.
  if(sched_mode == SCHED_SJF || sched_mode == SCHED_SRTF)
    printf("[SCHED] tick=%d algo=%s event=PRED_UPDATE pid=%d observed=%d "
           "predicted_prev=%d predicted_next=%d alpha=%d\n",
           ticks, (sched_mode == SCHED_SRTF) ? "SRTF" : "SJF",
           p->pid, observed, old, np, a);
}

// ── Scheduling helpers ────────────────────────────────────────────────────────

// Priority aging and MLFQ boost thresholds are now DYNAMIC configuration
// (proc.c globals priority_aging_threshold / mlfq_cfg.boost_interval), applied
// per run via setpriorityaging() / setmlfqboost().  Their defaults (10 and 20)
// preserve the historical fixed behavior when no LLM/Guard value is supplied.

static const char * const sched_algo_name[] = {
  "RR", "FCFS", "PRIORITY", "MLFQ", "SJF", "SRTF"
};

// Emit one parseable scheduler trace line.  Format consumed by
// tools/trace_parser.py:
//   [SCHED] tick=N algo=ALGO event=EVENT pid=N state=STATE queue=N priority=N reason=TEXT
// No CPU-burst value is ever emitted, so future bursts cannot leak via traces.
// Safe to call with interrupts off and/or while holding p->lock (CPUS=1): the
// existing dispatch trace already prints under chosen->lock.
void
sched_trace(int mode, const char *event, int pid, const char *state,
            int queue, int priority, const char *reason)
{
  if(mode < 0 || mode >= (int)NELEM(sched_algo_name)) mode = 0;
  printf("[SCHED] tick=%d algo=%s event=%s pid=%d", ticks,
         sched_algo_name[mode], event, pid);
  if(state)
    printf(" state=%s", state);
  printf(" queue=%d priority=%d", queue, priority);
  if(reason)
    printf(" reason=%s", reason);
  printf("\n");
}

// MLFQ queue-level transition (demotion / promotion).
void
sched_trace_queue(int mode, int pid, int from_q, int to_q, const char *reason)
{
  if(mode < 0 || mode >= (int)NELEM(sched_algo_name)) mode = 0;
  printf("[SCHED] tick=%d algo=%s event=QUEUE_CHANGE pid=%d from_queue=%d to_queue=%d reason=%s\n",
         ticks, sched_algo_name[mode], pid, from_q, to_q, reason);
}

// Trace one DISPATCH per scheduling decision (no throttling, so the host-side
// parser/metrics can reconstruct dashboard-grade timelines).
static void
sched_debug(struct proc *p, int mode)
{
  sched_trace(mode, "DISPATCH", p->pid, "RUNNING", p->queue_level, p->priority, 0);
}

// Round-Robin: preserves original xv6 behavior (iterate table in order).
static int
sched_rr(struct cpu *c)
{
  struct proc *p;
  int found = 0;
  for(p = proc; p < &proc[NPROC]; p++){
    acquire(&p->lock);
    if(p->state == RUNNABLE){
      p->state = RUNNING;
      p->wait_ticks = 0;
      // Reset the per-dispatch quantum counter so trap.c counts RR ticks from
      // zero for this slice (ticks_in_level is reused for the RR quantum here;
      // RR and MLFQ never run at the same time, so there is no conflict).
      p->ticks_in_level = 0;
      c->proc = p;
      sched_debug(p, SCHED_RR);
      swtch(&c->context, &p->context);
      c->proc = 0;
      found = 1;
    }
    release(&p->lock);
  }
  return found;
}

// FCFS: non-preemptive; pick the RUNNABLE process with the smallest ctime,
// breaking ties by pid.  Two-phase to avoid holding multiple proc locks.
static int
sched_fcfs(struct cpu *c)
{
  struct proc *p, *chosen = 0;
  int best_ctime = 0, best_pid = 0;

  // Phase 1: find best candidate (lock acquired then released per process).
  for(p = proc; p < &proc[NPROC]; p++){
    acquire(&p->lock);
    if(p->state == RUNNABLE){
      if(chosen == 0 ||
         p->ctime < best_ctime ||
         (p->ctime == best_ctime && p->pid < best_pid)){
        chosen     = p;
        best_ctime = p->ctime;
        best_pid   = p->pid;
      }
    }
    release(&p->lock);
  }
  if(!chosen) return 0;

  // Phase 2: re-acquire and run (re-check state in case it changed).
  acquire(&chosen->lock);
  if(chosen->state == RUNNABLE){
    chosen->wait_ticks = 0;
    chosen->state = RUNNING;
    c->proc = chosen;
    sched_debug(chosen, SCHED_FCFS);
    swtch(&c->context, &chosen->context);
    c->proc = 0;
    release(&chosen->lock);
    return 1;
  }
  release(&chosen->lock);
  return 0;
}

// Priority: preemptive; pick the RUNNABLE process with the smallest priority
// number (= highest priority).  Tie-break: smallest ctime, then smallest pid.
// Simple aging: every AGE_THRESHOLD scheduler rounds waiting, reduce priority
// number by 1 (floor 0), giving long-waiting processes a better chance.
static int
sched_priority(struct cpu *c)
{
  struct proc *p, *chosen = 0;
  int best_pri = 0, best_ctime = 0, best_pid = 0;

  // Phase 1: scan, apply aging, select best.
  for(p = proc; p < &proc[NPROC]; p++){
    acquire(&p->lock);
    if(p->state == RUNNABLE){
      p->wait_ticks++;
      if(p->wait_ticks >= priority_aging_threshold && p->priority > 0){
        p->priority--;
        p->wait_ticks = 0;
      }
      if(chosen == 0 ||
         p->priority < best_pri ||
         (p->priority == best_pri && p->ctime < best_ctime) ||
         (p->priority == best_pri && p->ctime == best_ctime && p->pid < best_pid)){
        chosen     = p;
        best_pri   = p->priority;
        best_ctime = p->ctime;
        best_pid   = p->pid;
      }
    }
    release(&p->lock);
  }
  if(!chosen) return 0;

  // Phase 2: run chosen.
  acquire(&chosen->lock);
  if(chosen->state == RUNNABLE){
    chosen->wait_ticks = 0;
    chosen->state = RUNNING;
    c->proc = chosen;
    sched_debug(chosen, SCHED_PRIORITY);
    swtch(&c->context, &chosen->context);
    c->proc = 0;
    release(&chosen->lock);
    return 1;
  }
  release(&chosen->lock);
  return 0;
}

// MLFQ: 3 queues (0=highest, 2=lowest).
// Quanta: Q0=2 ticks, Q1=4 ticks, Q2=8 ticks.
// Demotion on quantum exhaustion is handled in trap.c.
// Promotion: if a process waits >= MLFQ_BOOST_THRESHOLD rounds, move to Q0.
// Within a level, tie-break by ctime then pid (FCFS).
static int
sched_mlfq(struct cpu *c)
{
  struct proc *p, *chosen = 0;
  // best_level must start above the highest possible queue index
  // (MLFQ_MAX_QUEUES-1), so a process sitting in the lowest active queue is
  // still selectable when it is the only RUNNABLE one.
  int best_level = MLFQ_MAX_QUEUES + 1, best_ctime = 0, best_pid = 0;

  // Phase 1: scan, boost stale processes, select best.
  for(p = proc; p < &proc[NPROC]; p++){
    acquire(&p->lock);
    if(p->state == RUNNABLE){
      p->wait_ticks++;
      if(p->wait_ticks >= mlfq_cfg.boost_interval && p->queue_level > 0){
        int from_q = p->queue_level;
        p->queue_level    = 0;
        p->ticks_in_level = 0;
        p->wait_ticks     = 0;
        sched_trace_queue(SCHED_MLFQ, p->pid, from_q, 0, "promotion");
      }
      int ql = p->queue_level;
      if(chosen == 0 ||
         ql < best_level ||
         (ql == best_level && p->ctime < best_ctime) ||
         (ql == best_level && p->ctime == best_ctime && p->pid < best_pid)){
        chosen     = p;
        best_level = ql;
        best_ctime = p->ctime;
        best_pid   = p->pid;
      }
    }
    release(&p->lock);
  }
  if(!chosen) return 0;

  // Phase 2: run chosen; reset quantum counter so trap.c tracks from zero.
  acquire(&chosen->lock);
  if(chosen->state == RUNNABLE){
    chosen->wait_ticks    = 0;
    chosen->ticks_in_level = 0;
    chosen->state = RUNNING;
    c->proc = chosen;
    sched_debug(chosen, SCHED_MLFQ);
    swtch(&c->context, &chosen->context);
    c->proc = 0;
    release(&chosen->lock);
    return 1;
  }
  release(&chosen->lock);
  return 0;
}

// Predicted remaining CPU time for SRTF: prediction for the burst minus what
// has already been observed to run.  Floored at min_predicted_burst so a
// process that overruns its prediction still has a positive, comparable key.
// Uses only predicted and observed values — never the true future burst.
static int
predicted_remaining(struct proc *p)
{
  int rem = p->predicted_burst - p->cur_burst_run;
  if(rem < pred.min_predicted_burst)
    rem = pred.min_predicted_burst;
  return rem;
}

// Predicted SJF: nonpreemptive.  Pick the RUNNABLE process with the smallest
// predicted_burst.  Tie-break: earlier ready_since_tick, then smaller pid.
// Two-phase to avoid holding multiple proc locks (mirrors sched_fcfs).
static int
sched_sjf(struct cpu *c)
{
  struct proc *p, *chosen = 0;
  int best_burst = 0, best_ready = 0, best_pid = 0;

  // Phase 1: find best candidate.
  for(p = proc; p < &proc[NPROC]; p++){
    acquire(&p->lock);
    if(p->state == RUNNABLE){
      if(chosen == 0 ||
         p->predicted_burst < best_burst ||
         (p->predicted_burst == best_burst && p->ready_since_tick < best_ready) ||
         (p->predicted_burst == best_burst && p->ready_since_tick == best_ready &&
          p->pid < best_pid)){
        chosen     = p;
        best_burst = p->predicted_burst;
        best_ready = p->ready_since_tick;
        best_pid   = p->pid;
      }
    }
    release(&p->lock);
  }
  if(!chosen) return 0;

  // Phase 2: re-acquire and run (re-check state in case it changed).
  acquire(&chosen->lock);
  if(chosen->state == RUNNABLE){
    chosen->wait_ticks = 0;
    chosen->state = RUNNING;
    c->proc = chosen;
    sched_debug(chosen, SCHED_SJF);
    swtch(&c->context, &chosen->context);
    c->proc = 0;
    release(&chosen->lock);
    return 1;
  }
  release(&chosen->lock);
  return 0;
}

// Predicted SRTF: preemptive at scheduling points.  Pick the RUNNABLE process
// with the smallest predicted_remaining.  Tie-break: earlier ready_since_tick,
// then smaller pid.  Preemption itself happens in trap.c, which yields every
// timer tick under SRTF so the scheduler re-selects on each scheduling point.
static int
sched_srtf(struct cpu *c)
{
  struct proc *p, *chosen = 0;
  int best_rem = 0, best_ready = 0, best_pid = 0;

  // Phase 1: find best candidate by predicted remaining time.
  for(p = proc; p < &proc[NPROC]; p++){
    acquire(&p->lock);
    if(p->state == RUNNABLE){
      int rem = predicted_remaining(p);
      if(chosen == 0 ||
         rem < best_rem ||
         (rem == best_rem && p->ready_since_tick < best_ready) ||
         (rem == best_rem && p->ready_since_tick == best_ready &&
          p->pid < best_pid)){
        chosen     = p;
        best_rem   = rem;
        best_ready = p->ready_since_tick;
        best_pid   = p->pid;
      }
    }
    release(&p->lock);
  }
  if(!chosen) return 0;

  // Phase 2: run chosen.
  acquire(&chosen->lock);
  if(chosen->state == RUNNABLE){
    chosen->wait_ticks = 0;
    chosen->state = RUNNING;
    c->proc = chosen;
    sched_debug(chosen, SCHED_SRTF);
    swtch(&c->context, &chosen->context);
    c->proc = 0;
    release(&chosen->lock);
    return 1;
  }
  release(&chosen->lock);
  return 0;
}

// Per-CPU process scheduler.
// Each CPU calls scheduler() after setting itself up.
// Scheduler never returns.
void
scheduler(void)
{
  struct cpu *c = mycpu();
  c->proc = 0;

  for(;;){
    // Enable interrupts briefly so we don't deadlock if all processes are
    // sleeping, then disable before scanning the run queue.
    intr_on();
    intr_off();

    int found = 0;
    switch(sched_mode){
    case SCHED_FCFS:
      found = sched_fcfs(c);
      break;
    case SCHED_PRIORITY:
      found = sched_priority(c);
      break;
    case SCHED_MLFQ:
      found = sched_mlfq(c);
      break;
    case SCHED_SJF:
      found = sched_sjf(c);
      break;
    case SCHED_SRTF:
      found = sched_srtf(c);
      break;
    default:          // SCHED_RR and any unknown mode
      found = sched_rr(c);
      break;
    }

    if(found == 0)
      asm volatile("wfi");
  }
}

// Switch to scheduler.  Must hold only p->lock
// and have changed proc->state. Saves and restores
// intena because intena is a property of this
// kernel thread, not this CPU. It should
// be proc->intena and proc->noff, but that would
// break in the few places where a lock is held but
// there's no process.
void
sched(void)
{
  int intena;
  struct proc *p = myproc();

  if(!holding(&p->lock))
    panic("sched p->lock");
  if(mycpu()->noff != 1)
    panic("sched locks");
  if(p->state == RUNNING)
    panic("sched RUNNING");
  if(intr_get())
    panic("sched interruptible");

  intena = mycpu()->intena;
  swtch(&p->context, &mycpu()->context);
  mycpu()->intena = intena;
}

// Give up the CPU for one scheduling round.
void
yield(void)
{
  struct proc *p = myproc();
  acquire(&p->lock);
  p->state = RUNNABLE;
  p->ready_since_tick = (int)ticks;  // re-entered ready queue (SJF/SRTF tie-break)
  sched();
  release(&p->lock);
}

// A fork child's very first scheduling by scheduler()
// will swtch to forkret.
void
forkret(void)
{
  extern char userret[];
  static int first = 1;
  struct proc *p = myproc();

  // Still holding p->lock from scheduler.
  release(&p->lock);

  if (first) {
    // File system initialization must be run in the context of a
    // regular process (e.g., because it calls sleep), and thus cannot
    // be run from main().
    fsinit(ROOTDEV);

    first = 0;
    // ensure other cores see first=0.
    __sync_synchronize();

    // We can invoke kexec() now that file system is initialized.
    // Put the return value (argc) of kexec into a0.
    p->trapframe->a0 = kexec("/init", (char *[]){ "/init", 0 });
    if (p->trapframe->a0 == -1) {
      panic("exec");
    }
  }

  // return to user space, mimicing usertrap()'s return.
  prepare_return();
  uint64 satp = MAKE_SATP(p->pagetable);
  uint64 trampoline_userret = TRAMPOLINE + (userret - trampoline);
  ((void (*)(uint64))trampoline_userret)(satp);
}

// Sleep on channel chan, releasing condition lock lk.
// Re-acquires lk when awakened.
void
sleep(void *chan, struct spinlock *lk)
{
  struct proc *p = myproc();

  // Must acquire p->lock in order to
  // change p->state and then call sched.
  // Once we hold p->lock, we can be
  // guaranteed that we won't miss any wakeup
  // (wakeup locks p->lock),
  // so it's okay to release lk.

  acquire(&p->lock);  //DOC: sleeplock1
  release(lk);

  // Blocking on I/O ends the current CPU burst: fold the observed burst length
  // into the prediction for this process's next burst (SJF/SRTF).
  update_burst_prediction(p);

  // Go to sleep.
  p->chan = chan;
  p->state = SLEEPING;

  sched();

  // Tidy up.
  p->chan = 0;

  // Reacquire original lock.
  release(&p->lock);
  acquire(lk);
}

// Wake up all processes sleeping on channel chan.
// Caller should hold the condition lock.
void
wakeup(void *chan)
{
  struct proc *p;

  for(p = proc; p < &proc[NPROC]; p++) {
    if(p != myproc()){
      acquire(&p->lock);
      if(p->state == SLEEPING && p->chan == chan) {
        p->state = RUNNABLE;
        p->ready_since_tick = (int)ticks;  // I/O completion: re-entered ready queue
      }
      release(&p->lock);
    }
  }
}

// Kill the process with the given pid.
// The victim won't exit until it tries to return
// to user space (see usertrap() in trap.c).
int
kkill(int pid)
{
  struct proc *p;

  for(p = proc; p < &proc[NPROC]; p++){
    acquire(&p->lock);
    if(p->pid == pid){
      p->killed = 1;
      if(p->state == SLEEPING){
        // Wake process from sleep().
        p->state = RUNNABLE;
      }
      release(&p->lock);
      return 0;
    }
    release(&p->lock);
  }
  return -1;
}

void
setkilled(struct proc *p)
{
  acquire(&p->lock);
  p->killed = 1;
  release(&p->lock);
}

int
killed(struct proc *p)
{
  int k;

  acquire(&p->lock);
  k = p->killed;
  release(&p->lock);
  return k;
}

// Copy to either a user address, or kernel address,
// depending on usr_dst.
// Returns 0 on success, -1 on error.
int
either_copyout(int user_dst, uint64 dst, void *src, uint64 len)
{
  struct proc *p = myproc();
  if(user_dst){
    return copyout(p->pagetable, dst, src, len);
  } else {
    memmove((char *)dst, src, len);
    return 0;
  }
}

// Copy from either a user address, or kernel address,
// depending on usr_src.
// Returns 0 on success, -1 on error.
int
either_copyin(void *dst, int user_src, uint64 src, uint64 len)
{
  struct proc *p = myproc();
  if(user_src){
    return copyin(p->pagetable, dst, src, len);
  } else {
    memmove(dst, (char*)src, len);
    return 0;
  }
}

// Print a process listing to console.  For debugging.
// Runs when user types ^P on console.
// No lock to avoid wedging a stuck machine further.
void
procdump(void)
{
  static char *states[] = {
  [UNUSED]    "unused",
  [USED]      "used",
  [SLEEPING]  "sleep ",
  [RUNNABLE]  "runble",
  [RUNNING]   "run   ",
  [ZOMBIE]    "zombie"
  };
  struct proc *p;
  char *state;

  printf("\n");
  for(p = proc; p < &proc[NPROC]; p++){
    if(p->state == UNUSED)
      continue;
    if(p->state >= 0 && p->state < NELEM(states) && states[p->state])
      state = states[p->state];
    else
      state = "???";
    printf("%d %s %s", p->pid, state, p->name);
    printf("\n");
  }
}
