// predtest — exercises the predicted SJF/SRTF Scheduling Algorithms and the
// burst predictor (setpredictor/getpredictor).
//
// Each child alternates a CPU burst with a short sleep.  Sleeping ends a CPU
// burst, so the kernel folds the observed burst length into the prediction via
// exponential averaging.  The child prints its evolving predicted burst, which
// should converge toward its real (but never disclosed) burst length.
//
// The test never tells the kernel a future burst — it only reads back the
// prediction the kernel computed from already-observed CPU usage.

#include "kernel/types.h"
#include "user/user.h"

#define SCHED_RR   0
#define SCHED_SJF  4
#define SCHED_SRTF 5

#define NCHILD  3
#define ROUNDS  3

// CPU burst whose length scales with `weight`; child 0 is short, child 2 long.
// The loop is sized so a burst spans several xv6 ticks (~0.1s each); otherwise
// the timer never samples the running process and no CPU usage is observed.
static void
cpu_burst(int weight)
{
  volatile int x = 0;
  for(int w = 0; w < weight; w++)
    for(int i = 0; i < 20000000; i++)
      x += i;
  (void)x;
}

static void
run_children(const char *tag)
{
  for(int i = 0; i < NCHILD; i++){
    int pid = fork();
    if(pid < 0){
      printf("predtest: fork failed\n");
      exit(1);
    }
    if(pid == 0){
      int mypid = getpid();
      int weight = i + 1;
      for(int r = 0; r < ROUNDS; r++){
        cpu_burst(weight);
        pause(2);  // ends the CPU burst -> predictor update in kernel
        printf("predtest[%s]: pid=%d round=%d predicted_burst=%d\n",
               tag, mypid, r, getpredictor(mypid));
      }
      exit(0);
    }
  }
  for(int i = 0; i < NCHILD; i++)
    wait(0);
}

int
main(int argc, char *argv[])
{
  // 1) Parameter validation: bad values must be rejected.
  if(setpredictor(150, 10, 1, 100) == 0){
    printf("predtest: FAIL bad alpha accepted\n");
    exit(1);
  }
  if(setpredictor(50, 10, 5, 2) == 0){
    printf("predtest: FAIL min>max accepted\n");
    exit(1);
  }

  // 2) Apply LLM-style recommended predictor parameters.
  if(setpredictor(50, 10, 1, 100) < 0){
    printf("predtest: FAIL valid params rejected\n");
    exit(1);
  }
  printf("predtest: predictor params set (alpha=50 init=10 min=1 max=100)\n");

  // 3) Run the same workload under SJF then SRTF.
  printf("predtest: --- SJF ---\n");
  if(setscheduler(SCHED_SJF) < 0){
    printf("predtest: setscheduler(SJF) failed\n");
    exit(1);
  }
  run_children("sjf");

  printf("predtest: --- SRTF ---\n");
  if(setscheduler(SCHED_SRTF) < 0){
    printf("predtest: setscheduler(SRTF) failed\n");
    exit(1);
  }
  run_children("srtf");

  setscheduler(SCHED_RR);  // restore default so the shell stays responsive
  printf("predtest: done\n");
  (void)argc; (void)argv;
  exit(0);
}
