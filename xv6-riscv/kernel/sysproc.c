#include "types.h"
#include "riscv.h"
#include "defs.h"
#include "param.h"
#include "memlayout.h"
#include "spinlock.h"
#include "proc.h"
#include "vm.h"

uint64
sys_exit(void)
{
  int n;
  argint(0, &n);
  kexit(n);
  return 0;  // not reached
}

uint64
sys_getpid(void)
{
  return myproc()->pid;
}

uint64
sys_fork(void)
{
  return kfork();
}

uint64
sys_wait(void)
{
  uint64 p;
  argaddr(0, &p);
  return kwait(p);
}

uint64
sys_sbrk(void)
{
  uint64 addr;
  int t;
  int n;

  argint(0, &n);
  argint(1, &t);
  addr = myproc()->sz;

  if(t == SBRK_EAGER || n < 0) {
    if(growproc(n) < 0) {
      return -1;
    }
  } else {
    // Lazily allocate memory for this process: increase its memory
    // size but don't allocate memory. If the processes uses the
    // memory, vmfault() will allocate it.
    if(addr + n < addr)
      return -1;
    if(addr + n > TRAPFRAME)
      return -1;
    myproc()->sz += n;
  }
  return addr;
}

uint64
sys_pause(void)
{
  int n;
  uint ticks0;

  argint(0, &n);
  if(n < 0)
    n = 0;
  acquire(&tickslock);
  ticks0 = ticks;
  while(ticks - ticks0 < n){
    if(killed(myproc())){
      release(&tickslock);
      return -1;
    }
    sleep(&ticks, &tickslock);
  }
  release(&tickslock);
  return 0;
}

uint64
sys_kill(void)
{
  int pid;

  argint(0, &pid);
  return kkill(pid);
}

// return how many clock tick interrupts have occurred
// since start.
uint64
sys_uptime(void)
{
  uint xticks;

  acquire(&tickslock);
  xticks = ticks;
  release(&tickslock);
  return xticks;
}

// Set the global scheduling algorithm.
// mode: SCHED_RR=0, SCHED_FCFS=1, SCHED_PRIORITY=2, SCHED_MLFQ=3,
//       SCHED_SJF=4, SCHED_SRTF=5
uint64
sys_setscheduler(void)
{
  int mode;
  argint(0, &mode);
  if(mode < SCHED_RR || mode > SCHED_SRTF)
    return -1;
  set_sched_mode(mode);
  return 0;
}

// Return the current scheduling algorithm.
uint64
sys_getscheduler(void)
{
  return get_sched_mode();
}

// Set the scheduling priority of a process.
// Lower number = higher priority.  Valid range: 0–20.
uint64
sys_setpriority(void)
{
  int pid, priority;
  argint(0, &pid);
  argint(1, &priority);
  if(priority < 0 || priority > 20)
    return -1;
  return set_proc_priority(pid, priority);
}

// Return the scheduling priority of a process, or -1 if not found.
uint64
sys_getpriority(void)
{
  int pid;
  argint(0, &pid);
  return get_proc_priority(pid);
}

// Set the global burst-predictor parameters for SJF/SRTF.
// args: alpha_percent, initial_predicted_burst, min_predicted_burst,
//       max_predicted_burst.  Returns 0 on success, -1 if out of range.
// These are predictor parameters only; no actual future CPU burst is accepted.
uint64
sys_setpredictor(void)
{
  int alpha, initial, min_b, max_b;
  argint(0, &alpha);
  argint(1, &initial);
  argint(2, &min_b);
  argint(3, &max_b);

  // Validate ranges before applying (Algorithm Guard mirror at the kernel edge).
  if(alpha < 0 || alpha > 100)
    return -1;
  if(min_b < 1 || max_b < min_b || max_b > 100000)
    return -1;
  if(initial < 1)
    return -1;

  return set_predictor_params(alpha, initial, min_b, max_b);
}

// Return the current predicted next-burst length for a pid, or -1 if not found.
// This is a prediction, never the true future burst.
uint64
sys_getpredictor(void)
{
  int pid;
  argint(0, &pid);
  return get_predicted_burst(pid);
}
