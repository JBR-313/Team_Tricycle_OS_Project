#include "kernel/types.h"
#include "user/user.h"

#define SCHED_RR       0
#define SCHED_FCFS     1
#define SCHED_PRIORITY 2
#define SCHED_MLFQ     3
#define SCHED_SJF      4
#define SCHED_SRTF     5

static const char *ALGO_NAMES[] = {"RR", "FCFS", "PRIORITY", "MLFQ", "SJF", "SRTF"};
#define NALGO (sizeof(ALGO_NAMES) / sizeof(ALGO_NAMES[0]))

#define MAXPROC 8

// One generated process in the workload.
struct procdef {
  int arrival;        // arrival tick (forks are immediate, so ~0 / metadata)
  int cpu_burst;      // CPU time to consume, in ticks
  int priority;       // scheduling priority (lower number = higher priority)
  const char *label;  // workload label
};

struct workload {
  const char *name;
  int n;
  struct procdef procs[MAXPROC];
};

// Per-profile generation "shape": the seed draws concrete values from these
// ranges, so (seed, profile) deterministically produces ONE workload.  The same
// seed yields an identical workload for every algorithm => fair comparison; a
// different seed yields a different (but reproducible) workload.
struct profile_shape {
  const char *name;
  int nmin, nmax;            // process count range
  int burst_min, burst_max;  // CPU burst (ticks) range
  int prio_min, prio_max;    // priority range
  const char *label;
};

static struct profile_shape SHAPES[] = {
  { "interactive",        4, 6, 1, 4, 1, 8, "interactive" },
  { "cpu_bound",          3, 5, 5, 9, 3, 7, "cpu" },
  { "mixed",              4, 6, 1, 7, 1, 9, "mixed" },
  { "priority_sensitive", 4, 6, 2, 6, 0, 9, "priority" },
};
#define NSHAPES (sizeof(SHAPES) / sizeof(SHAPES[0]))

static int
algo_mode(const char *s)
{
  if(strcmp(s, "rr") == 0)       return SCHED_RR;
  if(strcmp(s, "fcfs") == 0)     return SCHED_FCFS;
  if(strcmp(s, "priority") == 0) return SCHED_PRIORITY;
  if(strcmp(s, "mlfq") == 0)     return SCHED_MLFQ;
  if(strcmp(s, "sjf") == 0)      return SCHED_SJF;
  if(strcmp(s, "srtf") == 0)     return SCHED_SRTF;
  return -1;
}

static int
find_shape(const char *name)
{
  for(int i = 0; i < (int)NSHAPES; i++)
    if(strcmp(SHAPES[i].name, name) == 0)
      return i;
  return -1;
}

// Deterministic LCG, seeded from (seed, profile) so each profile differs even
// under the same numeric seed.
static uint rng_state = 1;

static void
seed_rng(int seed, int profile_idx)
{
  rng_state = ((uint)seed * 2654435761u) ^ ((uint)(profile_idx + 1) * 40503u);
  if(rng_state == 0)
    rng_state = 1;
}

static int
rand_range(int lo, int hi)
{
  rng_state = rng_state * 1103515245u + 12345u;
  int span = hi - lo + 1;
  if(span <= 0)
    return lo;
  return lo + (int)((rng_state >> 16) % (uint)span);
}

// Generate a deterministic workload for (shape, seed) into `out`.
static void
generate_workload(int shape_idx, int seed, struct workload *out)
{
  struct profile_shape *s = &SHAPES[shape_idx];
  seed_rng(seed, shape_idx);
  int n = rand_range(s->nmin, s->nmax);
  if(n > MAXPROC)
    n = MAXPROC;
  out->name = s->name;
  out->n = n;
  for(int i = 0; i < n; i++){
    out->procs[i].arrival   = 0;
    out->procs[i].cpu_burst = rand_range(s->burst_min, s->burst_max);
    out->procs[i].priority  = rand_range(s->prio_min, s->prio_max);
    out->procs[i].label     = s->label;
  }
}

// Consume approximately ticks_to_run ticks of CPU time.  uptime() returns the
// kernel tick counter; we spin doing small chunks of work between checks so the
// timer interrupt can drive real scheduling decisions while we run.
static void
run_burst(int ticks_to_run)
{
  int start = uptime();
  volatile int x = 0;
  while(uptime() - start < ticks_to_run){
    for(int i = 0; i < 20000; i++)
      x += i;
  }
  (void)x;
}

// Run one algorithm over the curated workload.  Forks all children, each of
// which consumes its burst, then waits for them.  Emits parseable [SCHEDTEST]
// metadata; the kernel emits [SCHED] scheduling events while they run.
static void
run_one(const char *algo, int mode, int seed, struct workload *wl)
{
  printf("[SCHEDTEST] event=RUN_BEGIN algo=%s seed=%d profile=%s nproc=%d\n",
         algo, seed, wl->name, wl->n);

  if(setscheduler(mode) < 0){
    printf("schedtest: setscheduler failed\n");
    exit(1);
  }

  for(int i = 0; i < wl->n; i++){
    int pid = fork();
    if(pid < 0){
      printf("schedtest: fork failed\n");
      break;
    }
    if(pid == 0){
      struct procdef *d = &wl->procs[i];
      int mypid = getpid();
      if(mode == SCHED_PRIORITY)
        setpriority(mypid, d->priority);
      printf("[SCHEDTEST] event=PROC_DEF pid=%d arrival=%d cpu_burst=%d priority=%d label=%s\n",
             mypid, d->arrival, d->cpu_burst, getpriority(mypid), d->label);
      printf("[SCHEDTEST] event=CHILD_START pid=%d priority=%d\n",
             mypid, getpriority(mypid));
      run_burst(d->cpu_burst);
      printf("[SCHEDTEST] event=CHILD_EXIT pid=%d\n", mypid);
      exit(0);
    }
  }

  for(int i = 0; i < wl->n; i++)
    wait(0);

  printf("[SCHEDTEST] event=RUN_END algo=%s seed=%d profile=%s\n",
         algo, seed, wl->name);

  // Restore default scheduler so the shell keeps working normally.
  setscheduler(SCHED_RR);
}

int
main(int argc, char *argv[])
{
  if(argc < 2){
    printf("usage: schedtest <algorithm> <seed> <profile>\n");
    printf("  algorithm : rr|fcfs|priority|mlfq|sjf|srtf | all\n");
    printf("  seed      : integer (default 1)\n");
    printf("  profile   : interactive|cpu_bound|mixed|priority_sensitive (default mixed)\n");
    exit(1);
  }

  int seed = (argc >= 3) ? atoi(argv[2]) : 1;
  const char *profile = (argc >= 4) ? argv[3] : "mixed";

  int shape_idx = find_shape(profile);
  if(shape_idx < 0){
    printf("schedtest: unknown profile: %s\n", profile);
    exit(1);
  }

  // Generate ONCE so every algorithm (including `all`) runs the identical
  // (seed, profile) workload — required for a fair comparison.
  struct workload wlbuf;
  generate_workload(shape_idx, seed, &wlbuf);
  struct workload *wl = &wlbuf;

  // Developer convenience: run every algorithm over the SAME workload/profile,
  // sequentially (LLM-selected-first ordering is the Orchestrator's job; here we
  // just run all six for clean per-algorithm trace separation).
  if(strcmp(argv[1], "all") == 0){
    for(int m = 0; m < (int)NALGO; m++)
      run_one(ALGO_NAMES[m], m, seed, wl);
    exit(0);
  }

  int mode = algo_mode(argv[1]);
  if(mode < 0){
    printf("schedtest: unknown algo: %s\n", argv[1]);
    exit(1);
  }

  run_one(ALGO_NAMES[mode], mode, seed, wl);
  exit(0);
}
