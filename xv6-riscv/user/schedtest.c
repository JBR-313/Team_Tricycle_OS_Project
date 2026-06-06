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

#define MAXPROC 12

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
  // Larger profiles (8 procs) exercise the scheduler at more than ~5 jobs and
  // isolate two phenomena.  interactive_storm: a burst of tiny interactive jobs
  // racing two CPU hogs — RR/MLFQ keep response time low.  batch_convoy: a long
  // head job followed by short jobs — the classic convoy effect SJF/SRTF undo.
  { "interactive_storm", 8, {
      {0,  1, 3, "interactive"},
      {1,  2, 4, "interactive"},
      {2,  1, 2, "interactive"},
      {3,  8, 6, "cpu"},
      {4,  1, 3, "interactive"},
      {6,  2, 4, "interactive"},
      {8,  7, 7, "cpu"},
      {10, 1, 2, "interactive"},
  }},
  { "batch_convoy", 8, {
      {0, 12, 5, "cpu"},
      {1,  2, 5, "cpu"},
      {2,  3, 5, "cpu"},
      {2,  1, 5, "interactive"},
      {3,  2, 5, "cpu"},
      {4,  1, 5, "interactive"},
      {5,  3, 5, "cpu"},
      {6,  2, 5, "cpu"},
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

// LLM/Guard-validated DYNAMIC scheduler parameters (RR / Priority / MLFQ),
// also supplied on the command line.  A value of -1 (or a zero count) means
// "not supplied" and the kernel keeps its compile-time default for that
// algorithm.  These steer real dispatch decisions but are applied once per run
// — schedtest never runs the scheduler and the LLM never picks a process.
static int g_rr_quantum = -1;        // RR: ticks per round
static int g_aging      = -1;        // Priority: rounds before aging
static int g_mlfq_queues = -1;       // MLFQ: queue count
static int g_mlfq_quantum[5];        // MLFQ: per-level quanta
static int g_mlfq_nquantum = 0;
static int g_mlfq_boost = -1;        // MLFQ: boost interval

// Parse a comma-separated list of non-negative ints into out[], up to max.
// Returns the count parsed.  Tolerates a trailing comma and stray spaces.
static int
parse_int_csv(const char *s, int *out, int max)
{
  int n = 0, val = 0, have = 0;
  for(; *s && n < max; s++){
    if(*s >= '0' && *s <= '9'){
      val = val * 10 + (*s - '0');
      have = 1;
    } else if(*s == ','){
      if(have){ out[n++] = val; val = 0; have = 0; }
    }
  }
  if(have && n < max)
    out[n++] = val;
  return n;
}

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

  // Apply the LLM/Guard-validated DYNAMIC scheduler parameters for this run,
  // once, before any child is forked, so the whole workload is scheduled under
  // them.  Each block is a no-op unless its flag was supplied on the command
  // line; the matching [SCHEDTEST] event=*_PARAMS line is the trace evidence
  // that the value actually reached and was accepted by xv6.
  if(mode == SCHED_RR && g_rr_quantum > 0){
    if(setrrquantum(g_rr_quantum) == 0)
      printf("[SCHEDTEST] event=RR_PARAMS algo=%s quantum=%d source=llm_guard\n",
             algo, g_rr_quantum);
    else
      printf("[SCHEDTEST] event=RR_PARAMS_REJECTED algo=%s quantum=%d\n",
             algo, g_rr_quantum);
  }
  if(mode == SCHED_PRIORITY && g_aging > 0){
    if(setpriorityaging(g_aging) == 0)
      printf("[SCHEDTEST] event=PRIORITY_PARAMS algo=%s aging_threshold=%d source=llm_guard\n",
             algo, g_aging);
    else
      printf("[SCHEDTEST] event=PRIORITY_PARAMS_REJECTED algo=%s aging_threshold=%d\n",
             algo, g_aging);
  }
  if(mode == SCHED_MLFQ && g_mlfq_queues > 0 && g_mlfq_nquantum > 0){
    // Pad the quantum list to 5 slots (kernel uses only the first `queues`).
    int q[5];
    for(int k = 0; k < 5; k++)
      q[k] = (k < g_mlfq_nquantum) ? g_mlfq_quantum[k]
                                   : g_mlfq_quantum[g_mlfq_nquantum - 1];
    if(setmlfqparams(g_mlfq_queues, q[0], q[1], q[2], q[3], q[4]) == 0){
      int boost_ok = (g_mlfq_boost > 0 && setmlfqboost(g_mlfq_boost) == 0);
      // Emit one MLFQ_PARAMS line carrying the applied queues, quantum list,
      // and (when supplied) boost interval.  quantum is a single comma-joined
      // token so the host parser keeps it intact.
      printf("[SCHEDTEST] event=MLFQ_PARAMS algo=%s queues=%d quantum=",
             algo, g_mlfq_queues);
      for(int k = 0; k < g_mlfq_queues; k++)
        printf("%s%d", k ? "," : "", q[k]);
      if(boost_ok)
        printf(" boost_interval=%d", g_mlfq_boost);
      printf(" source=llm_guard\n");
    } else {
      printf("[SCHEDTEST] event=MLFQ_PARAMS_REJECTED algo=%s queues=%d\n",
             algo, g_mlfq_queues);
    }
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

    // Start barrier: a one-byte pipe the child blocks on immediately after fork.
    // The parent applies all scheduling metadata (priority and/or SJF/SRTF burst
    // hint) to the child's runtime pid, THEN releases it.  This makes the
    // "metadata is in place before the child runs any CPU workload" ordering
    // race-free: without it a timer tick could dispatch the child between fork()
    // and the parent's setpriority()/setbursthint(), letting one quantum run
    // under stale defaults (and, for PRIORITY, letting the first dispatch be
    // chosen on the wrong priority).
    int gate[2];
    if(pipe(gate) < 0){
      printf("schedtest: pipe failed\n");
      break;
    }

    int pid = fork();
    if(pid < 0){
      printf("schedtest: fork failed\n");
      close(gate[0]);
      close(gate[1]);
      break;
    }
    if(pid == 0){
      // Child: wait at the barrier until the parent has applied our metadata.
      close(gate[1]);
      char b;
      read(gate[0], &b, 1);
      close(gate[0]);
      int mypid = getpid();
      printf("[SCHEDTEST] event=PROC_DEF pid=%d arrival=%d cpu_burst=%d priority=%d label=%s\n",
             mypid, d->arrival, d->cpu_burst, getpriority(mypid), d->label);
      printf("[SCHEDTEST] event=CHILD_START pid=%d priority=%d\n",
             mypid, getpriority(mypid));
      run_burst(d->cpu_burst);
      printf("[SCHEDTEST] event=CHILD_EXIT pid=%d\n", mypid);
      exit(0);
    }

    // Parent: apply this child's scheduling metadata to its runtime pid BEFORE
    // releasing it through the barrier.
    close(gate[0]);

    // Priority is applied from the PARENT (not the child) so it is in place
    // before the child is ever schedulable for real work.  Emitting the runtime
    // pid + logical index makes the apply auditable in the raw log.
    if(mode == SCHED_PRIORITY){
      setpriority(pid, d->priority);
      printf("[SCHEDTEST] event=PRIORITY_APPLIED pid=%d index=%d priority=%d source=schedtest_profile\n",
             pid, i, d->priority);
    }

    // Seed this child's SJF/SRTF prediction with the LLM-generated initial prior
    // (aligned to fork order).  The kernel later refines it via EMA from observed
    // CPU only; the true future burst is never supplied here.
    if((mode == SCHED_SJF || mode == SCHED_SRTF) && i < g_nhints && g_hints[i] > 0){
      if(setbursthint(pid, g_hints[i]) == 0)
        printf("[SCHEDTEST] event=BURST_HINT_APPLIED pid=%d index=%d predicted_burst=%d\n",
               pid, i, g_hints[i]);
    }

    // Release the child: it now runs CHILD_START + run_burst with metadata set.
    write(gate[1], "x", 1);
    close(gate[1]);
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
    printf("usage: schedtest <algorithm> <seed> <profile> [flags...]\n");
    printf("  algorithm : rr|fcfs|priority|mlfq|sjf|srtf | all\n");
    printf("  seed      : integer (default 1)\n");
    printf("  profile   : interactive|cpu_bound|mixed|priority_sensitive|interactive_storm|batch_convoy (default mixed)\n");
    printf("  flags (all LLM/Guard validated; each algorithm reads only its own):\n");
    printf("    --rr-quantum <int>            RR ticks per round\n");
    printf("    --aging <int>                 Priority aging threshold\n");
    printf("    --mlfq-queues <int>           MLFQ queue count (2-5)\n");
    printf("    --mlfq-quantum <c,s,v>        MLFQ per-level quanta (CSV)\n");
    printf("    --mlfq-boost <int>            MLFQ boost interval\n");
    printf("    --alpha/--initial/--min/--max <int>   SJF/SRTF predictor params\n");
    printf("    --hints <c,s,v>               SJF/SRTF per-process burst priors (CSV, fork order)\n");
    exit(1);
  }

  int seed = (argc >= 3) ? atoi(argv[2]) : 1;
  const char *profile = (argc >= 4) ? argv[3] : "mixed";

  // Flag-style options (argv[4..]).  Flags keep the argument count low (CSV
  // lists collapse multi-value params into one token), so MLFQ's full config
  // fits comfortably under the xv6 shell argument limit.  Each algorithm only
  // consults the flags relevant to it; the values come from the LLM via the
  // Orchestrator (Algorithm Guard validated) and never carry true future
  // bursts.  Unknown flags are ignored.
  for(int i = 4; i < argc; i++){
    if(strcmp(argv[i], "--rr-quantum") == 0 && i + 1 < argc){
      g_rr_quantum = atoi(argv[++i]);
    } else if(strcmp(argv[i], "--aging") == 0 && i + 1 < argc){
      g_aging = atoi(argv[++i]);
    } else if(strcmp(argv[i], "--mlfq-queues") == 0 && i + 1 < argc){
      g_mlfq_queues = atoi(argv[++i]);
    } else if(strcmp(argv[i], "--mlfq-quantum") == 0 && i + 1 < argc){
      g_mlfq_nquantum = parse_int_csv(argv[++i], g_mlfq_quantum, 5);
    } else if(strcmp(argv[i], "--mlfq-boost") == 0 && i + 1 < argc){
      g_mlfq_boost = atoi(argv[++i]);
    } else if(strcmp(argv[i], "--alpha") == 0 && i + 1 < argc){
      g_alpha = atoi(argv[++i]);
    } else if(strcmp(argv[i], "--initial") == 0 && i + 1 < argc){
      g_initial = atoi(argv[++i]);
    } else if(strcmp(argv[i], "--min") == 0 && i + 1 < argc){
      g_min = atoi(argv[++i]);
    } else if(strcmp(argv[i], "--max") == 0 && i + 1 < argc){
      g_max = atoi(argv[++i]);
    } else if(strcmp(argv[i], "--hints") == 0 && i + 1 < argc){
      g_nhints = parse_int_csv(argv[++i], g_hints, MAXPROC);
    }
    // else: unknown token ignored (keeps forward/backward compat tolerant)
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
