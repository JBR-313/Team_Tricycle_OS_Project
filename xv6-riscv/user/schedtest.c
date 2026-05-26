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
