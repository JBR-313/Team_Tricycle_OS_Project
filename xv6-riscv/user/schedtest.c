#include "kernel/types.h"
#include "user/user.h"

#define SCHED_RR       0
#define SCHED_FCFS     1
#define SCHED_PRIORITY 2
#define SCHED_MLFQ     3

#define NCHILD 3

// CPU-bound busy loop so children produce visible scheduling events.
static void
busywork(void)
{
  volatile int x = 0;
  for(int i = 0; i < 500000; i++)
    x += i;
  (void)x;
}

int
main(int argc, char *argv[])
{
  int mode;

  if(argc < 2){
    printf("usage: schedtest rr|fcfs|priority|mlfq\n");
    exit(1);
  }

  if(strcmp(argv[1], "rr") == 0)
    mode = SCHED_RR;
  else if(strcmp(argv[1], "fcfs") == 0)
    mode = SCHED_FCFS;
  else if(strcmp(argv[1], "priority") == 0)
    mode = SCHED_PRIORITY;
  else if(strcmp(argv[1], "mlfq") == 0)
    mode = SCHED_MLFQ;
  else {
    printf("schedtest: unknown algo: %s\n", argv[1]);
    exit(1);
  }

  printf("schedtest: start mode=%s\n", argv[1]);

  if(setscheduler(mode) < 0){
    printf("schedtest: setscheduler failed\n");
    exit(1);
  }

  for(int i = 0; i < NCHILD; i++){
    int pid = fork();
    if(pid < 0){
      printf("schedtest: fork failed\n");
      exit(1);
    }
    if(pid == 0){
      int mypid = getpid();
      int pri = (i + 1) * 3;   // children get priorities 3, 6, 9
      if(mode == SCHED_PRIORITY)
        setpriority(mypid, pri);
      printf("schedtest: child %d pid=%d pri=%d start\n",
             i, mypid, getpriority(mypid));
      busywork();
      printf("schedtest: child %d pid=%d done\n", i, mypid);
      exit(0);
    }
    // parent loops to fork next child
  }

  for(int i = 0; i < NCHILD; i++)
    wait(0);

  printf("schedtest: end mode=%s\n", argv[1]);

  // Restore default scheduler so the shell keeps working normally.
  setscheduler(SCHED_RR);
  exit(0);
}
