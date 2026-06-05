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

// One planned process in a curated workload.
struct procdef {
  int arrival;        // tick (relative to RUN_BEGIN) at which the parent forks this process
  int cpu_burst;      // CPU time to consume, in ticks
  int priority;       // scheduling priority (lower number = higher priority)
  const char *label;  // workload label
};

struct workload {
  const char *name;
  int n;
  struct procdef procs[MAXPROC];
};

// Fixed curated workload tables, one per profile.  No JSON parsing inside xv6
// and no random generation yet: the workload is deterministic by profile name.
// The seed argument is parsed and logged for reproducibility but does not yet
// alter the workload (random generation is a later phase).
static struct workload WORKLOADS[] = {
  { "interactive", 5, {
      {0,  3, 5, "interactive"},
      {2,  1, 2, "interactive"},
      {5,  2, 3, "interactive"},
      {10, 4, 7, "cpu"},
      {15, 1, 4, "interactive"},
  }},
  { "cpu_bound", 4, {
      {0, 8, 5, "cpu"},
      {1, 6, 4, "cpu"},
      {2, 7, 6, "cpu"},
      {3, 5, 5, "cpu"},
  }},
  { "mixed", 5, {
      {0, 5, 4, "cpu"},
      {2, 2, 2, "interactive"},
      {4, 6, 6, "cpu"},
      {6, 1, 3, "interactive"},
      {8, 4, 5, "mixed"},
  }},
  { "priority_sensitive", 5, {
      {0, 6, 8, "cpu"},
      {1, 4, 1, "interactive"},
      {2, 5, 9, "cpu"},
      {3, 3, 2, "interactive"},
      {4, 4, 5, "mixed"},
  }},
};
#define NWORKLOADS (sizeof(WORKLOADS) / sizeof(WORKLOADS[0]))

// LLM-generated predictor configuration, supplied on the command line by the
// Orchestrator (already validated/clamped by Algorithm Guard).  These are
// predictor *parameters* and *initial burst priors* derived from visible
// workload features — never true future bursts.  g_alpha < 0 means "not
// supplied"; the kernel then keeps its built-in predictor defaults.
static int g_alpha = -1, g_initial = -1, g_min = -1, g_max = -1;
static int g_hints[MAXPROC];
static int g_nhints = 0;

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

static struct workload*
find_workload(const char *name)
{
  for(int i = 0; i < (int)NWORKLOADS; i++)
    if(strcmp(WORKLOADS[i].name, name) == 0)
      return &WORKLOADS[i];
  return 0;
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

  // Apply the LLM/Guard predictor parameters once per run.  Only SJF/SRTF
  // consult the burst predictor, so this is a no-op for the other algorithms.
  if((mode == SCHED_SJF || mode == SCHED_SRTF) && g_alpha >= 0){
    if(setpredictor(g_alpha, g_initial, g_min, g_max) == 0)
      printf("[SCHEDTEST] event=PREDICTOR_PARAMS algo=%s alpha=%d initial=%d min=%d max=%d\n",
             algo, g_alpha, g_initial, g_min, g_max);
    else
      printf("[SCHEDTEST] event=PREDICTOR_PARAMS_REJECTED algo=%s alpha=%d initial=%d min=%d max=%d\n",
             algo, g_alpha, g_initial, g_min, g_max);
  }

  // Reference tick captured before any fork. The parent gates fork() itself
  // on planned arrival so each child is *first made RUNNABLE* exactly at its
  // declared arrival. (A previous attempt slept in the child after fork, but
  // the child still got DISPATCHED briefly before calling pause, which marked
  // first_run earlier than arrival and produced negative response_time.)
  int t0 = uptime();

  for(int i = 0; i < wl->n; i++){
    struct procdef *d = &wl->procs[i];

    int need = d->arrival - (uptime() - t0);
    if(need > 0)
      pause(need);

    int pid = fork();
    if(pid < 0){
      printf("schedtest: fork failed\n");
      break;
    }
    if(pid == 0){
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

    // Parent: seed this child's SJF/SRTF prediction with the LLM-generated
    // initial prior (aligned to fork order).  Done before the parent pauses for
    // the next arrival, so the prior lands before the child is heavily
    // scheduled.  The kernel later refines it via EMA from observed CPU only.
    if((mode == SCHED_SJF || mode == SCHED_SRTF) && i < g_nhints && g_hints[i] > 0){
      if(setbursthint(pid, g_hints[i]) == 0)
        printf("[SCHEDTEST] event=BURST_HINT_APPLIED pid=%d index=%d predicted_burst=%d\n",
               pid, i, g_hints[i]);
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
    printf("usage: schedtest <algorithm> <seed> <profile> [alpha initial min max] [hint0 hint1 ...]\n");
    printf("  algorithm : rr|fcfs|priority|mlfq|sjf|srtf | all\n");
    printf("  seed      : integer (default 1)\n");
    printf("  profile   : interactive|cpu_bound|mixed|priority_sensitive (default mixed)\n");
    printf("  alpha..max: predictor params (SJF/SRTF); LLM/Guard validated\n");
    printf("  hintN     : per-process initial burst priors, aligned to fork order\n");
    exit(1);
  }

  int seed = (argc >= 3) ? atoi(argv[2]) : 1;
  const char *profile = (argc >= 4) ? argv[3] : "mixed";

  // Optional predictor configuration for SJF/SRTF (ignored by other algos):
  //   argv[4..7] = alpha initial min max  (Guard-validated predictor params)
  //   argv[8..]  = per-process initial burst priors, aligned to fork order.
  // These come from the LLM via the Orchestrator and never carry true future
  // bursts; the kernel re-clamps them and refines via EMA on observed CPU.
  if(argc >= 8){
    g_alpha   = atoi(argv[4]);
    g_initial = atoi(argv[5]);
    g_min     = atoi(argv[6]);
    g_max     = atoi(argv[7]);
    for(int i = 8; i < argc && g_nhints < MAXPROC; i++)
      g_hints[g_nhints++] = atoi(argv[i]);
  }

  struct workload *wl = find_workload(profile);
  if(wl == 0){
    printf("schedtest: unknown profile: %s\n", profile);
    exit(1);
  }

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
