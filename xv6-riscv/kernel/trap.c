#include "types.h"
#include "param.h"
#include "memlayout.h"
#include "riscv.h"
#include "spinlock.h"
#include "proc.h"
#include "defs.h"

struct spinlock tickslock;
uint ticks;

extern char trampoline[], uservec[];

// in kernelvec.S, calls kerneltrap().
void kernelvec();

extern int devintr();

void
trapinit(void)
{
  initlock(&tickslock, "time");
}

// Handle timer tick for the current process based on scheduler mode.
// For MLFQ: track ticks_in_level and demote when quantum is exhausted.
// For FCFS: never preempt.
// For RR / Priority: always preempt.
//
// NOTE: ticks_in_level and queue_level are modified without p->lock here.
// This is safe on CPUS=1 because the scheduler (the only other writer) runs
// with interrupts disabled.  On CPUS>1 this would require a lock.
void
timer_yield_or_tick(struct proc *p)
{
  int mode = get_sched_mode();

  // Track observed CPU usage for the running process.  This records only
  // already-consumed CPU time; it never references the true future burst.
  // SJF/SRTF predictions are derived solely from cur_burst_run.
  p->cur_burst_run++;
  p->rtime++;

  if(mode == SCHED_FCFS || mode == SCHED_SJF){
    // non-preemptive: run until the process blocks or exits
    return;
  }

  if(mode == SCHED_RR){
    // RR: preempt only after the configured quantum expires.  The quantum is
    // dynamic config (proc.c rr_quantum) applied per run via setrrquantum();
    // ticks_in_level counts ticks in the current slice and is reset on dispatch
    // in sched_rr().  A quantum of 1 reproduces the original every-tick RR.
    p->ticks_in_level++;
    if(p->ticks_in_level >= get_rr_quantum()){
      p->ticks_in_level = 0;
      sched_trace(SCHED_RR, "PREEMPT", p->pid, "RUNNABLE",
                  p->queue_level, p->priority, "quantum_expired");
      yield();
    }
    return;
  }

  if(mode == SCHED_MLFQ){
    // MLFQ quanta and queue count are dynamic config (proc.c mlfq_cfg) applied
    // per run via setmlfqparams().  Demote at most to the lowest active queue.
    p->ticks_in_level++;
    int maxq = get_mlfq_queues() - 1;
    int ql = p->queue_level < maxq ? p->queue_level : maxq;
    if(p->ticks_in_level >= get_mlfq_quantum(ql)){
      // Quantum exhausted: demote if not already at the lowest level.
      int from_q = p->queue_level;
      if(p->queue_level < maxq)
        p->queue_level++;
      p->ticks_in_level = 0;
      if(p->queue_level != from_q)
        sched_trace_queue(SCHED_MLFQ, p->pid, from_q, p->queue_level, "demotion");
      sched_trace(SCHED_MLFQ, "PREEMPT", p->pid, "RUNNABLE",
                  p->queue_level, p->priority, "quantum_expired");
      yield();
    }
    // else: quantum not exhausted, keep running
    return;
  }

  // SCHED_PRIORITY, SCHED_SRTF: preempt on every timer tick.
  // For SRTF every timer tick is a scheduling point, so the scheduler
  // re-selects the smallest predicted_remaining process each tick.
  sched_trace(mode, "PREEMPT", p->pid, "RUNNABLE",
              p->queue_level, p->priority, "timer_tick");
  yield();
}

// set up to take exceptions and traps while in the kernel.
void
trapinithart(void)
{
  w_stvec((uint64)kernelvec);
}

//
// handle an interrupt, exception, or system call from user space.
// called from, and returns to, trampoline.S
// return value is user satp for trampoline.S to switch to.
//
uint64
usertrap(void)
{
  int which_dev = 0;

  if((r_sstatus() & SSTATUS_SPP) != 0)
    panic("usertrap: not from user mode");

  // send interrupts and exceptions to kerneltrap(),
  // since we're now in the kernel.
  w_stvec((uint64)kernelvec);  //DOC: kernelvec

  struct proc *p = myproc();
  
  // save user program counter.
  p->trapframe->epc = r_sepc();
  
  if(r_scause() == 8){
    // system call

    if(killed(p))
      kexit(-1);

    // sepc points to the ecall instruction,
    // but we want to return to the next instruction.
    p->trapframe->epc += 4;

    // an interrupt will change sepc, scause, and sstatus,
    // so enable only now that we're done with those registers.
    intr_on();

    syscall();
  } else if((which_dev = devintr()) != 0){
    // ok
  } else if((r_scause() == 15 || r_scause() == 13) &&
            vmfault(p->pagetable, r_stval(), (r_scause() == 13)? 1 : 0) != 0) {
    // page fault on lazily-allocated page
  } else {
    printf("usertrap(): unexpected scause 0x%lx pid=%d\n", r_scause(), p->pid);
    printf("            sepc=0x%lx stval=0x%lx\n", r_sepc(), r_stval());
    setkilled(p);
  }

  if(killed(p))
    kexit(-1);

  // give up the CPU if this is a timer interrupt (mode-aware).
  if(which_dev == 2)
    timer_yield_or_tick(p);

  prepare_return();

  // the user page table to switch to, for trampoline.S
  uint64 satp = MAKE_SATP(p->pagetable);

  // return to trampoline.S; satp value in a0.
  return satp;
}

//
// set up trapframe and control registers for a return to user space
//
void
prepare_return(void)
{
  struct proc *p = myproc();

  // we're about to switch the destination of traps from
  // kerneltrap() to usertrap(). because a trap from kernel
  // code to usertrap would be a disaster, turn off interrupts.
  intr_off();

  // send syscalls, interrupts, and exceptions to uservec in trampoline.S
  uint64 trampoline_uservec = TRAMPOLINE + (uservec - trampoline);
  w_stvec(trampoline_uservec);

  // set up trapframe values that uservec will need when
  // the process next traps into the kernel.
  p->trapframe->kernel_satp = r_satp();         // kernel page table
  p->trapframe->kernel_sp = p->kstack + PGSIZE; // process's kernel stack
  p->trapframe->kernel_trap = (uint64)usertrap;
  p->trapframe->kernel_hartid = r_tp();         // hartid for cpuid()

  // set up the registers that trampoline.S's sret will use
  // to get to user space.
  
  // set S Previous Privilege mode to User.
  unsigned long x = r_sstatus();
  x &= ~SSTATUS_SPP; // clear SPP to 0 for user mode
  x |= SSTATUS_SPIE; // enable interrupts in user mode
  w_sstatus(x);

  // set S Exception Program Counter to the saved user pc.
  w_sepc(p->trapframe->epc);
}

// interrupts and exceptions from kernel code go here via kernelvec,
// on whatever the current kernel stack is.
void 
kerneltrap()
{
  int which_dev = 0;
  uint64 sepc = r_sepc();
  uint64 sstatus = r_sstatus();
  uint64 scause = r_scause();
  
  if((sstatus & SSTATUS_SPP) == 0)
    panic("kerneltrap: not from supervisor mode");
  if(intr_get() != 0)
    panic("kerneltrap: interrupts enabled");

  if((which_dev = devintr()) == 0){
    // interrupt or trap from an unknown source
    printf("scause=0x%lx sepc=0x%lx stval=0x%lx\n", scause, r_sepc(), r_stval());
    panic("kerneltrap");
  }

  // give up the CPU if this is a timer interrupt (mode-aware).
  if(which_dev == 2 && myproc() != 0)
    timer_yield_or_tick(myproc());

  // the yield() may have caused some traps to occur,
  // so restore trap registers for use by kernelvec.S's sepc instruction.
  w_sepc(sepc);
  w_sstatus(sstatus);
}

void
clockintr()
{
  if(cpuid() == 0){
    acquire(&tickslock);
    ticks++;
    wakeup(&ticks);
    release(&tickslock);
  }

  // ask for the next timer interrupt. this also clears
  // the interrupt request. 1000000 is about a tenth
  // of a second.
  w_stimecmp(r_time() + 1000000);
}

// check if it's an external interrupt or software interrupt,
// and handle it.
// returns 2 if timer interrupt,
// 1 if other device,
// 0 if not recognized.
int
devintr()
{
  uint64 scause = r_scause();

  if(scause == 0x8000000000000009L){
    // this is a supervisor external interrupt, via PLIC.

    // irq indicates which device interrupted.
    int irq = plic_claim();

    if(irq == UART0_IRQ){
      uartintr();
    } else if(irq == VIRTIO0_IRQ){
      virtio_disk_intr();
    } else if(irq){
      printf("unexpected interrupt irq=%d\n", irq);
    }

    // the PLIC allows each device to raise at most one
    // interrupt at a time; tell the PLIC the device is
    // now allowed to interrupt again.
    if(irq)
      plic_complete(irq);

    return 1;
  } else if(scause == 0x8000000000000005L){
    // timer interrupt.
    clockintr();
    return 2;
  } else {
    return 0;
  }
}

