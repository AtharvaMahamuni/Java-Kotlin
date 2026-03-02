# Phase J6 — Concurrency Fundamentals

Java concurrency is one of the most tested and most misunderstood areas of the language. The questions in this phase build the mental model required to reason correctly about multi-threaded programs: what states a thread can be in, how the JVM enforces mutual exclusion, what the Java Memory Model actually guarantees, and how threads communicate through wait/notify. These four questions form the foundation for understanding everything in `java.util.concurrent` (Phase J7). Every senior Java interview will probe this material — usually in the form of "what's wrong with this code?" questions where the defect is a subtle race condition, a visibility bug, or a misuse of wait/notify.

---

## J6.1 — Thread Lifecycle

> **Connects to:** [J6.2 — synchronized & Monitor Locks](J6_concurrency_fundamentals.md#j62--synchronized--monitor-locks) · [J6.3 — volatile & Java Memory Model](J6_concurrency_fundamentals.md#j63--volatile--java-memory-model)

### The Concrete Picture

Start: you call `thread.start()` on a freshly constructed thread:

```
new Thread(task)   ──► state = NEW  (Java object exists; no OS thread yet)
thread.start()     ──► OS thread created; state = RUNNABLE

RUNNABLE thread hits synchronized(lock) but lock is held:
  state = RUNNABLE ──► BLOCKED
  thread dump shows: "waiting to lock <0x...> held by Thread-0"

BLOCKED thread acquires lock:
  state = BLOCKED ──► RUNNABLE  (resumes execution)

Thread calls obj.wait() inside synchronized block:
  lock RELEASED atomically; state = RUNNABLE ──► WAITING
  thread dump shows: "in Object.wait()"

obj.notify() called by another thread:
  WAITING ──► BLOCKED (re-competing for the lock) ──► RUNNABLE

Thread calls Thread.sleep(5000):
  state = RUNNABLE ──► TIMED_WAITING  (lock NOT released)
  thread dump shows: "sleeping"

run() returns or throws unchecked exception:
  state ──► TERMINATED  (OS thread destroyed; Thread object still on heap)
  thread.start() again ──► IllegalThreadStateException
```

### WHY This Matters

Understanding thread states is not academic — it is the primary tool for debugging live production issues. When a system freezes, hangs, or becomes unresponsive, you attach a profiler or run `jstack <pid>` to get a thread dump. That thread dump tells you the state of every thread in the JVM. If you can read those states, you can immediately distinguish a deadlock (threads permanently BLOCKED on each other's locks), a livelock (threads repeatedly transitioning between RUNNABLE states without making progress), starvation (a thread perpetually BLOCKED because higher-priority threads always win the lock), and a simple slow operation (a thread legitimately TIMED_WAITING on I/O or a sleep). Without this knowledge, a thread dump is noise. With it, it is a complete diagnostic map of your system's behavior at a point in time.

### The 6 States in `Thread.State`

Java defines exactly six thread states in the `java.lang.Thread.State` enum. The JVM guarantees that any thread is in exactly one of these states at any moment:

```
  NEW
   │
   │  thread.start()
   ▼
RUNNABLE ◄──────────────────────────────┐
   │                                    │
   ├──── waiting for monitor lock ──► BLOCKED ─────► RUNNABLE (lock acquired)
   │
   ├──── wait() / join() / park() ──► WAITING ──────► RUNNABLE (notified/joined/unparked)
   │
   ├──── sleep(ms) / wait(ms) /     ► TIMED_WAITING ► RUNNABLE (timeout or signal)
   │     join(ms) / parkNanos(ns)
   │
   └──── run() returns or throws ──► TERMINATED
```

This transition graph is the complete picture. A thread cannot skip states arbitrarily. A TERMINATED thread can never restart — calling `start()` on a terminated thread throws `IllegalThreadStateException`.

### NEW: Created but Not Yet Started

A thread enters the NEW state the moment you construct it, before calling `start()`. The JVM has allocated the `Thread` object on the heap and initialized its metadata, but no native OS thread has been created yet. There is nothing running.

```java
Thread t = new Thread(() -> System.out.println("Hello"));
// t.getState() == Thread.State.NEW
// No OS thread exists yet. Just a Java object.
t.start();
// Now an OS thread is created and scheduled.
```

The transition from NEW to RUNNABLE is triggered by exactly one thing: calling `start()`. You cannot force a thread from NEW into any other state. Calling `run()` directly does not change the state — it runs the runnable code on the current thread synchronously, leaving the Thread object permanently in NEW (and never actually starting the thread).

### RUNNABLE: Running or Ready to Run

Once `start()` is called, the thread transitions to RUNNABLE. This state name is deliberately inclusive: it covers both "currently executing on a CPU core" and "ready to execute, waiting for the OS scheduler to give it a CPU time slice." Java makes no distinction between these two sub-states because the JVM cannot portably query the OS scheduler's internal queue state.

This means you cannot tell from `Thread.State` alone whether a RUNNABLE thread is actually burning CPU right now or sitting in the OS run queue. This is by design: the OS preempts threads many thousands of times per second, and the thread's Java-level state stays RUNNABLE throughout. From the JMM's perspective, RUNNABLE means "nothing is blocking this thread from executing."

```java
Thread t = new Thread(() -> {
    long sum = 0;
    for (long i = 0; i < Long.MAX_VALUE; i++) sum += i;  // CPU-bound loop
});
t.start();
Thread.sleep(100);
System.out.println(t.getState());  // RUNNABLE — even when OS time-sliced off CPU
```

### BLOCKED: Waiting for a Monitor Lock

A thread enters BLOCKED when it attempts to enter a `synchronized` block or method but the monitor lock is already held by another thread. This is not voluntary — the thread has not asked to wait; it has simply been stopped in its tracks by the synchronization mechanism.

BLOCKED is different from WAITING. A BLOCKED thread is actively competing for a resource. The moment the lock becomes available, one of the BLOCKED threads (OS/JVM choice, not guaranteed FIFO) transitions to RUNNABLE and acquires the lock.

```java
Object lock = new Object();

Thread t1 = new Thread(() -> {
    synchronized (lock) {
        Thread.sleep(5000);  // holds lock for 5 seconds (note: sleep doesn't release it)
    }
});

Thread t2 = new Thread(() -> {
    synchronized (lock) {   // t2 blocks here while t1 holds the lock
        System.out.println("t2 got the lock");
    }
});

t1.start();
Thread.sleep(100);  // let t1 acquire the lock first
t2.start();
Thread.sleep(100);  // let t2 try to acquire
System.out.println(t2.getState());  // BLOCKED
```

In a thread dump, a BLOCKED thread shows:
```
"Thread-1" #12 prio=5 os_prio=0 tid=0x00007f... nid=0x... waiting for monitor entry [0x...]
   java.lang.Thread.State: BLOCKED (on object monitor)
        at com.example.MyClass.doWork(MyClass.java:42)
        - waiting to lock <0x000000076b4b2f10> (a java.lang.Object)
        - locked by "Thread-0" (id=11)
```

Notice the thread dump tells you not just that t2 is BLOCKED, but precisely which lock it is waiting for (`0x000000076b4b2f10`) and which thread currently holds that lock (`Thread-0`). This is how you diagnose deadlocks from production thread dumps.

### WAITING: Voluntarily Suspended, Awaiting a Signal

A thread enters WAITING when it voluntarily suspends itself, releasing control until another thread explicitly wakes it up. There is no timeout — it will wait indefinitely. Three mechanisms cause this transition:

1. `Object.wait()` — called inside a `synchronized` block; atomically releases the lock and suspends. Woken by `notify()` or `notifyAll()` on the same object.
2. `Thread.join()` — calling thread suspends until the target thread finishes (`TERMINATED`).
3. `LockSupport.park()` — low-level primitive used internally by `java.util.concurrent`. Woken by `LockSupport.unpark(thread)`.

```java
Object condition = new Object();

Thread waiter = new Thread(() -> {
    synchronized (condition) {
        condition.wait();   // enters WAITING, releases lock
        System.out.println("Woken up!");
    }
});

waiter.start();
Thread.sleep(100);
System.out.println(waiter.getState());  // WAITING

synchronized (condition) {
    condition.notify();  // waiter moves from WAITING → BLOCKED → RUNNABLE
}
```

### TIMED_WAITING: Same as WAITING but with a Timeout

TIMED_WAITING is functionally identical to WAITING, except the thread will automatically return to RUNNABLE after a specified duration, even without an explicit signal. The mechanisms:

| Method | Woken by |
|--------|----------|
| `Thread.sleep(ms)` | Timeout expiration or `interrupt()` |
| `Object.wait(ms)` | `notify()`, `notifyAll()`, timeout, or `interrupt()` |
| `Thread.join(ms)` | Target thread termination, timeout, or `interrupt()` |
| `LockSupport.parkNanos(ns)` | `unpark()`, timeout |
| `LockSupport.parkUntil(deadline)` | `unpark()`, deadline |

```java
Thread t = new Thread(() -> Thread.sleep(10_000));
t.start();
Thread.sleep(100);
System.out.println(t.getState());  // TIMED_WAITING
```

A thread in TIMED_WAITING appears in thread dumps with its remaining timeout. In profiling tools, a high number of TIMED_WAITING threads often indicates excessive `Thread.sleep()` usage in application logic — a design smell.

### TERMINATED: Finished Execution

A thread enters TERMINATED when its `run()` method returns normally or propagates an unchecked exception. The native OS thread is destroyed. The Java `Thread` object still exists on the heap (until GC collects it), but calling `start()` on it throws `IllegalThreadStateException`. There is no resurrection.

```java
Thread t = new Thread(() -> System.out.println("Done"));
t.start();
t.join();  // wait for t to finish
System.out.println(t.getState());  // TERMINATED
t.start();  // throws IllegalThreadStateException!
```

### Daemon Threads

Every thread is either a daemon or a non-daemon (user) thread. The distinction affects JVM shutdown: **the JVM exits when all non-daemon threads have terminated**, even if daemon threads are still running. Daemon threads are automatically killed when the JVM shuts down.

```java
Thread daemon = new Thread(() -> {
    while (true) {
        System.out.println("Daemon working...");
        Thread.sleep(1000);
    }
});
daemon.setDaemon(true);  // MUST be called before start()
daemon.start();

// When main() returns, JVM exits immediately.
// The daemon thread is killed mid-execution without cleanup.
```

Use daemon threads for background housekeeping tasks (cache eviction, monitoring, heartbeats) that should not prevent the application from shutting down. Never use them for tasks that need to complete cleanly (database writes, file flushes). `setDaemon()` after `start()` throws `IllegalThreadStateException`.

### Thread Priority

Priorities range from 1 (`Thread.MIN_PRIORITY`) to 10 (`Thread.MAX_PRIORITY`), with default 5 (`Thread.NORM_PRIORITY`). The JVM passes priorities as hints to the OS scheduler, but the OS is free to ignore them entirely. On Linux (where most Java servers run), thread priorities map to OS nice values, and the scheduler does attempt to honor them — but it is not guaranteed.

**Do not use thread priorities for correctness.** Never write code that requires one thread to run before another based on priority alone. Use synchronization primitives for that. Thread priorities are a performance hint only.

### Reading Thread Dumps

```bash
jstack <pid>             # attach to running JVM
jstack -l <pid>          # include lock information
kill -3 <pid>            # also dumps to stderr on Unix
```

A thread dump looks like:

```
"main" #1 prio=5 os_prio=0 tid=0x00007f cpu_id=3 nid=0x1a2b runnable [0x00007fff...]
   java.lang.Thread.State: RUNNABLE
        at java.net.SocketInputStream.socketRead0(Native Method)
        at java.net.SocketInputStream.read(SocketInputStream.java:152)

"pool-1-thread-1" #10 prio=5 os_prio=0 tid=0x00007f... nid=0x1a2c waiting on condition [...]
   java.lang.Thread.State: TIMED_WAITING (sleeping)
        at java.lang.Thread.sleep(Native Method)
        at com.example.Worker.run(Worker.java:23)

"pool-1-thread-2" #11 prio=5 os_prio=0 tid=0x00007f... nid=0x1a2d waiting for monitor entry
   java.lang.Thread.State: BLOCKED (on object monitor)
        at com.example.Service.process(Service.java:45)
        - waiting to lock <0x000000076b4b2f10> (a com.example.Service)
        - locked by "pool-1-thread-3" (id=12)
```

### Interview Trap

The single most common interview trap on this topic: **BLOCKED and WAITING are completely different states with completely different causes.**

- **BLOCKED**: the thread tried to enter a `synchronized` block but someone else holds the lock. The thread is not cooperating — it was stopped. No lock is released. The thread competes with other BLOCKED threads for the lock when it becomes free.
- **WAITING**: the thread deliberately called `wait()`, `join()`, or `park()`. It has released any monitor it held. It is cooperating — it will not proceed until explicitly notified. It is not competing for anything; it is passively waiting for a signal.

A deadlocked thread is BLOCKED (stuck waiting for a lock that will never be released because the holder is also BLOCKED). A thread waiting on a `BlockingQueue.take()` is WAITING (deliberately suspended, will be woken when an item is added). These are not the same thing, and diagnosing them requires recognizing the difference in a thread dump.

### Memory Trick

```
6 states: NEW → RUNNABLE → BLOCKED / WAITING / TIMED_WAITING → TERMINATED
BLOCKED  = involuntary stop at synchronized door (no lock release)
WAITING  = voluntary suspend via wait()/join()/park() (lock IS released)
TIMED_WAITING = same as WAITING but with an automatic timeout
sleep() → TIMED_WAITING, lock NOT released
wait()  → WAITING, lock IS released
TERMINATED: no restart — start() throws IllegalThreadStateException
Daemon thread: JVM exits when all non-daemon threads finish, daemons killed
jstack: "BLOCKED (on object monitor)" vs "in Object.wait()" = key distinction
```

---

## J6.2 — synchronized & Monitor Locks

> **Builds on:** [J6.1 — Thread Lifecycle](J6_concurrency_fundamentals.md#j61--thread-lifecycle)
> **Connects to:** [J6.3 — volatile & Java Memory Model](J6_concurrency_fundamentals.md#j63--volatile--java-memory-model) · [J6.4 — wait/notify/notifyAll](J6_concurrency_fundamentals.md#j64--waitnotifynotifyall)

### The Concrete Picture

Two threads increment a shared counter without synchronization — what goes wrong:

```
int count = 0;  // shared field

Thread1 reads count  ──► gets 5 (in register)
Thread2 reads count  ──► gets 5 (in register)  ← both read SAME value
Thread1 adds 1       ──► 6
Thread2 adds 1       ──► 6
Thread1 writes 6     ──► count = 6
Thread2 writes 6     ──► count = 6  ← one increment LOST

Add synchronized:
  synchronized(this) {
    count++;              ← MONITORENTER before; MONITOREXIT after
  }                       ← implicit try-finally: lock released even on exception

Thread1 acquires monitor ──► Thread2 hits MONITORENTER ──► state = BLOCKED
Thread1 increments, releases ──► Thread2 unblocks, increments
Result: count goes 5 → 6 → 7 (correct)

Lock escalation path (Java 21+):
  thin lock (CAS on mark word) ──► fat lock (OS mutex, threads parked)
  fat lock stays fat for object's lifetime — no downgrade
```

### WHY This Matters

The fundamental problem in concurrent programming is shared mutable state. When two threads read and write the same variable without coordination, you get a data race. Data races produce results that are impossible to predict or reproduce: corrupted data structures, incorrect counter values, partially initialized objects seen by other threads, and behaviors that change depending on thread scheduling, JIT optimization, and CPU core topology. `synchronized` is Java's primary built-in mechanism for eliminating data races. It does two things simultaneously: it ensures mutual exclusion (only one thread executes the protected code at a time) and it ensures memory visibility (a thread that acquires a lock sees all writes made by any previous holder of the same lock). Both guarantees together are necessary for correct concurrent code.

### Every Object Has a Monitor

In Java, every object — every single instance on the heap, regardless of type — has a hidden monitor built into its object header. This monitor is a mutex: at any moment, at most one thread can own it. This design decision (monitors built into every object) is what makes `synchronized` on any object possible, but it also means every object carries overhead for concurrency even when you never use it concurrently.

The `synchronized` keyword acquires this monitor before executing the guarded code and releases it after — unconditionally, even if an exception is thrown.

### Synchronized Instance Method

```java
class Counter {
    private int count = 0;

    public synchronized void increment() {
        count++;          // read-modify-write, NOT atomic without synchronization
    }

    public synchronized int get() {
        return count;     // read also needs synchronization for visibility
    }
}
```

`synchronized` on an instance method is syntactic sugar for `synchronized(this)`. It acquires the monitor of the object on which the method is invoked. Two threads calling `increment()` on the SAME `Counter` instance will serialize. Two threads calling `increment()` on DIFFERENT `Counter` instances will not interfere — different monitors.

### Synchronized Static Method

```java
class Registry {
    private static int instanceCount = 0;

    public static synchronized void register() {
        instanceCount++;
    }
}
```

`synchronized` on a static method acquires the `Class` object's monitor — specifically `Registry.class`. This is a different monitor than any instance of `Registry`. You can have a thread holding `Registry.class` lock and another thread simultaneously holding a `Registry` instance lock — they do not interfere with each other. This is a common source of bugs: protecting a static field with `synchronized` on an instance method protects it only per-instance, not globally.

### Synchronized Block

```java
class Cache {
    private final Object lock = new Object();  // dedicated lock object
    private final Map<String, Object> map = new HashMap<>();

    public Object get(String key) {
        synchronized (lock) {             // only lock what's necessary
            return map.get(key);
        }
        // code here runs without the lock — shorter lock duration
    }
}
```

A synchronized block gives you control over exactly which monitor to acquire and exactly how long to hold it. Prefer synchronized blocks over synchronized methods when:
- You want a dedicated, private lock object (prevents external code from interfering with your lock)
- The method does work that doesn't require the lock, and you want to minimize contention by locking only the critical section

### MONITORENTER / MONITOREXIT Bytecodes

When `javac` compiles a `synchronized` block, it generates two bytecodes: `MONITORENTER` at the start and `MONITOREXIT` at the end. Crucially, the compiler wraps the entire block in an implicit try-finally to ensure `MONITOREXIT` runs even if the body throws an exception. Without this guarantee, an exception inside a synchronized block would leave the lock permanently held — a guaranteed deadlock.

```bytecode
; synchronized (obj) { body; }
; compiles to:

ALOAD obj              ; push the lock object onto the operand stack
DUP                    ; duplicate — one copy for MONITORENTER, one stored for finally
ASTORE _lock_ref       ; store reference for use in the finally/exception handler
MONITORENTER           ; acquire the monitor. Blocks if another thread holds it.

; === normal execution path ===
; ... body bytecodes ...
ALOAD _lock_ref
MONITOREXIT            ; release monitor on normal exit

; === exception handler (implicit finally) ===
; (if body throws any Throwable:)
ALOAD _lock_ref
MONITOREXIT            ; release monitor on exception path
ATHROW                 ; rethrow the exception
```

You can verify this with `javap -c -verbose YourClass.class`. Every synchronized block will have exactly two `MONITOREXIT` instructions — one for the happy path, one for the exception path. This is why synchronized blocks cannot leak locks even when exceptions occur.

### Object Header: The Mark Word and Lock States

The monitor is not a separate object — it is encoded in the object's header. Every object header starts with an 8-byte "mark word" that stores multiple things depending on the object's current state:

```
Mark Word (64-bit JVM):
┌──────────────────────────────────────────────────────────────────┐
│  Bits 0-1: lock state                                            │
│   00 = thin lock (lightweight, CAS-based)                        │
│   01 = biased lock OR unlocked                                   │
│   10 = fat lock (inflated, OS mutex)                             │
│   11 = marked for GC                                             │
│                                                                  │
│  Remaining bits: GC age, identity hash code, or lock owner ptr  │
└──────────────────────────────────────────────────────────────────┘
```

The JVM implements a locking strategy that escalates from cheap to expensive based on contention. The exact tiers depend on JVM version:

> **Version note:** Biased locking was deprecated in Java 15 (JEP 374) and **fully removed in Java 21**. On Java 21+, the monitor starts in thin (stack-lock / CAS) state directly — there is no biased lock tier.

**Pre-Java 21 (three-tier):**

```
  Biased Lock (cheapest) — REMOVED in Java 21
  ─────────────────────
  Object "biased" toward first thread that locks it.
  Re-acquisition by same thread = just check thread ID in mark word.
  No atomic operation needed at all on re-acquisition.
  Cost: single thread ID check.
  Trigger: first acquisition.

         │ another thread tries to acquire
         ▼

  Thin Lock (lightweight)
  ───────────────────────
  CAS (compare-and-swap) to write thread ID into mark word.
  Brief spin loop if CAS fails (busy-wait for lock holder to finish).
  No OS involvement — pure user-space.
  Cost: CAS instruction(s) + possible spin.
  Trigger: second thread competes.

         │ contention too high (spin count exceeded)
         ▼

  Fat Lock / Inflated (heaviest)
  ──────────────────────────────
  JVM creates a real OS mutex (e.g., pthread_mutex on Linux).
  Threads that cannot acquire the lock are parked in the OS (descheduled).
  Context switch overhead: microseconds per transition.
  Cost: OS syscall for park/unpark.
  Trigger: high contention or wait() called.
```

**Java 21+ (two-tier — biased locking removed):**

```
  Thin Lock (stack-lock / CAS) — starting state
  ───────────────────────────────────────────────
  CAS to write thread ID into mark word on first acquisition.
  No biased lock phase. Modern hardware's CAS is cheap enough
  that biased locking's revocation cost outweighs its benefit.

         │ contention too high
         ▼

  Fat Lock / Inflated (OS mutex)
```

Lock inflation is one-way for fat locks: once a lock inflates to fat, it stays fat for the object's lifetime. Biased lock revocation was expensive (it required stopping the world briefly) — the primary reason biased locking was removed in Java 21.

### Reentrancy

`synchronized` in Java is reentrant: if a thread already holds a monitor, it can acquire the same monitor again without deadlocking. The JVM tracks a count of how many times the current owner thread has acquired the monitor. The lock is only truly released when the count reaches zero.

```java
class Tree {
    synchronized void traverse() {
        // ... visit root ...
        traverseChildren();  // calls another synchronized method
    }

    synchronized void traverseChildren() {
        // This works! Same thread re-acquires the same monitor.
        // Acquisition depth counter increments to 2.
        // When traverseChildren() returns: depth goes back to 1.
        // When traverse() returns: depth goes to 0 → lock released.
    }
}
```

Without reentrancy, calling one `synchronized` method from another `synchronized` method on the same object would immediately deadlock — the thread would block on its own lock. Reentrancy prevents this. It also means subclass `synchronized` methods can safely call `super.synchronizedMethod()` without deadlock.

### Memory Visibility Guarantee

`synchronized` does not only provide mutual exclusion. It also provides a happens-before memory visibility guarantee. When thread A releases a monitor, all writes made by thread A before the release are guaranteed to be visible to any thread B that subsequently acquires the same monitor. This is the Java Memory Model's monitor rule.

```java
class SharedData {
    private int value = 0;
    private boolean ready = false;
    private final Object lock = new Object();

    // Thread A:
    public void publish(int v) {
        synchronized (lock) {
            value = v;
            ready = true;
        }  // MONITOREXIT here: all writes flushed, visible to next lock acquirer
    }

    // Thread B:
    public int consume() {
        synchronized (lock) {  // MONITORENTER here: sees all writes from last releaser
            if (ready) return value;
            return -1;
        }
    }
}
```

Without synchronized (or volatile), thread B might see `ready == true` but `value == 0` due to CPU cache and compiler reordering. With synchronized, the happens-before guarantee ensures B sees both writes exactly as A performed them.

### synchronized Block vs Method: Preferred Usage

```java
// Less preferred: locks 'this' for the entire method
// External code can also synchronize on 'this', interfering with you
public synchronized void updateAndLog() {
    update();    // needs lock
    log();       // does NOT need lock — but holds it anyway
}

// Preferred: private lock, shorter duration
private final Object stateLock = new Object();

public void updateAndLog() {
    synchronized (stateLock) {
        update();   // only this needs the lock
    }
    log();          // runs without holding the lock — reduces contention
}
```

Using a dedicated `private final Object lock` has two advantages: (1) external code cannot interfere with your synchronization because they have no access to the lock object, and (2) you can have multiple independent locks for different parts of the object's state, allowing finer-grained concurrency.

### Interview Trap

The most dangerous mistake interviewers test: **using different lock objects for the same shared state provides NO protection.**

```java
class BrokenCounter {
    private int count = 0;
    private final Object lockA = new Object();
    private final Object lockB = new Object();

    public void incrementWithA() {
        synchronized (lockA) { count++; }  // acquires lockA monitor
    }

    public void incrementWithB() {
        synchronized (lockB) { count++; }  // acquires lockB monitor — DIFFERENT MONITOR!
    }
}
```

Thread 1 calling `incrementWithA()` and Thread 2 calling `incrementWithB()` are NOT mutually exclusive. They hold different monitors. Both can execute `count++` simultaneously — a data race. Protection only works when all threads competing for the same state acquire the same monitor.

Similarly, `synchronized(this)` and `synchronized(myPrivateLock)` are different monitors. You cannot mix them. Decide on one lock per piece of state and use it consistently everywhere.

### Memory Trick

```
Every object has a monitor encoded in its mark word (first 8 bytes of header)
MONITORENTER = lock; MONITOREXIT = unlock (compiler adds implicit try-finally)
synchronized(this) = instance lock; synchronized(Foo.class) = class lock
Reentrant: same thread can re-enter; depth counter, released when hits 0
Lock upgrade: thin (CAS) ──► fat (OS mutex) — one-way, fat stays fat (Java 21+)
Biased locking REMOVED in Java 21 (revocation was too expensive)
Memory visibility: unlock hb next lock (all writes visible to next acquirer)
Trap: lockA + lockB on same field = ZERO mutual exclusion
```

---

## J6.3 — volatile & Java Memory Model

> **Builds on:** [J6.2 — synchronized & Monitor Locks](J6_concurrency_fundamentals.md#j62--synchronized--monitor-locks)
> **Connects to:** [J6.4 — wait/notify/notifyAll](J6_concurrency_fundamentals.md#j64--waitnotifynotifyall)

### The Concrete Picture

Without `volatile`, Thread2 may never see Thread1's write:

```
Core0 (Thread1)                     Core1 (Thread2)
  L1 cache:  running = false          L1 cache: running = false
  JIT hoists loop check out of loop

Thread1:  running = true              Thread2:  while (running) { ... }
          └──► write to Core0 L1               └──► reads from Core1 L1 cache
               NOT yet in main mem              └──► sees running = false FOREVER

Add volatile:
  volatile boolean running;

Thread1:  running = true              Thread2:  while (running) { ... }
          └──► StoreStore barrier               └──► LoadLoad barrier
               flush to main memory             └──► forced read from main memory
               invalidate other caches          └──► sees true ──► loop exits

Double-checked locking — why volatile is MANDATORY:
  new Singleton() compiles to 3 steps:
    1. allocate memory  ──► get ref
    2. initialize fields (call constructor)
    3. assign ref to `instance`
  CPU/JIT may reorder: steps 3 before 2
  Thread2: reads instance != null ──► accesses UNINITIALIZED fields!
  volatile instance: StoreStore barrier ──► step 2 always before step 3
```

### WHY This Matters

Modern CPUs are fast. Main memory (DRAM) is not. To bridge the gap, every CPU core has multiple levels of private cache (L1, L2) and shared cache (L3). When a core writes a value, it writes to its L1 cache first — the write may not propagate to main memory or to other cores' caches for an arbitrary amount of time. Additionally, compilers and CPUs reorder instructions for performance (loads, stores, and arithmetic can execute out of program order as long as the result within a single thread is the same). For single-threaded programs, this is invisible and correct. For multi-threaded programs, it means one thread's writes may be invisible to another thread entirely, and operations may appear to execute in a different order than you wrote them.

The Java Memory Model (JMM), defined in Chapter 17 of the Java Language Specification, is the formal contract between Java programs and the JVM/CPU. It defines exactly when one thread's writes become visible to another thread. The `volatile` keyword is one of the primary mechanisms for establishing the visibility and ordering guarantees that the JMM provides.

### The Java Memory Model: Happens-Before

The JMM uses the "happens-before" (hb) relationship to define visibility. If action A happens-before action B, then all effects of A are visible to B. Happens-before is not about clock time — it is about the guarantees the JVM is required to provide. The formal rules:

```
1. PROGRAM ORDER RULE
   Within a single thread, every action happens-before the next action
   in program order. (Single-threaded code appears sequential.)

2. MONITOR LOCK RULE
   Unlocking a monitor happens-before every subsequent locking of
   that same monitor. (synchronized provides visibility.)

3. VOLATILE VARIABLE RULE
   A write to a volatile field happens-before every subsequent read
   of that same volatile field. (volatile provides visibility.)

4. THREAD START RULE
   A call to Thread.start() on a thread T happens-before any action
   in thread T. (Starter's writes visible to started thread.)

5. THREAD TERMINATION RULE
   Any action in thread T happens-before any other thread detects
   T's termination (via T.join() or T.isAlive() returning false).

6. INTERRUPTION RULE
   A call to thread.interrupt() happens-before the interrupted thread
   detects the interruption.

7. TRANSITIVITY
   If A hb B and B hb C, then A hb C.
   (Chains of hb relationships extend visibility.)
```

**Happens-before as a directed graph:**

Each edge below means "all writes before this point are visible after this point."

```
   THREAD A                          THREAD B
   ────────                          ────────
   write x = 1        ─────────────────────────────────────────────────────────
   write y = 2             hb via                 hb via              hb via
                           monitor unlock         volatile write       Thread.start()
   synchronized(lock) {                                   │                 │
     unlock  ─────────────────►  lock  ──────────────────┤                 │
   }                          (Thread B)                  │                 │
                                                          │                 │
   volatile flag = true ──────────────────────────────────►  read flag      │
                                                             sees x=1, y=2  │
                                                                             │
   Thread.start(T)  ──────────────────────────────────────────────────────► │
   (all A's writes                                                           │ first action
    before start)                                                            ▼ in T sees them
```

**Transitivity example — the publication idiom:**

```
  Thread A (publisher):                       Thread B (reader):

  object.field = value;  ──►(prog. order hb)──► volatile flag = true
                                                        │
                                                        │ (volatile write hb volatile read)
                                                        ▼
                                                  read volatile flag
                                                        │
                                                        │ (prog. order hb)
                                                        ▼
                                                  read object.field → sees value
```

By transitivity: `write object.field` hb `write flag` hb `read flag` hb `read object.field`. Thread B is guaranteed to see the correct value — WITHOUT making `object.field` itself volatile.

Without any of these relationships, there is no guarantee of visibility. A thread reading a plain field written by another thread may see stale data indefinitely.

### CPU Cache and Memory Visibility: ASCII Diagram

```
  Core 0 (Thread 1)              Core 1 (Thread 2)
  ┌─────────────────┐            ┌─────────────────┐
  │   L1 Cache      │            │   L1 Cache      │
  │   x = 1  ◄──┐  │            │   x = 0  ◄──┐  │
  └─────────────│──┘            └─────────────│──┘
                │                             │
  ┌─────────────│──┐            ┌─────────────│──┐
  │   L2 Cache  │  │            │   L2 Cache  │  │
  └─────────────│──┘            └─────────────│──┘
                │                             │
  ─────────────────────────────────────────────────
                    L3 Cache (shared)
  ─────────────────────────────────────────────────
                         │
                    Main Memory
                    ┌──────────┐
                    │  x = ?   │   ← may or may not have 1 yet
                    └──────────┘

  WITHOUT volatile:
    Thread 1 writes x = 1 → sits in Core 0's L1 cache
    Thread 2 reads x       → reads from Core 1's L1 cache → gets 0
    Result: Thread 2 sees stale value. Undefined behavior per JMM.

  WITH volatile:
    Thread 1 writes x = 1 → memory barrier: write flushed to main memory,
                             all caches invalidated
    Thread 2 reads x       → memory barrier: forced read from main memory
    Result: Thread 2 guaranteed to see 1.
```

### `volatile` Guarantees

`volatile` provides exactly two guarantees:

**1. Visibility:** A write to a `volatile` variable is immediately flushed to main memory. A read of a `volatile` variable always reads from main memory (never from a CPU-local cache). This ensures that a write by one thread is visible to all other threads as soon as they read the same variable.

**2. Ordering (memory barrier):** The JVM inserts a memory barrier around every `volatile` access. A `volatile` write acts as a StoreStore barrier before it (no prior write can be reordered past it) and a StoreLoad barrier after it (the write cannot be delayed past subsequent reads). A `volatile` read acts as a LoadLoad barrier after it (no subsequent read can be reordered before it). The practical effect: instructions before a `volatile` write stay before it, and instructions after a `volatile` read stay after it.

**What `volatile` does NOT provide:** Atomicity for compound operations. `volatile int x` makes individual reads and writes atomic (on most platforms, int reads and writes are already atomic, but `volatile` makes this a JMM guarantee). But `x++` is not a single operation — it is read-x, increment, write-x. Even with `volatile`, two threads can both read the same value, both increment, and both write the same result — losing one increment. For that, you need `AtomicInteger` or `synchronized`.

### volatile for a Stop Flag

The canonical correct use of `volatile` — a flag checked by one thread and set by another:

```java
public class Worker implements Runnable {
    private volatile boolean running = true;  // volatile: must be visible across threads

    public void stop() {
        running = false;       // volatile write: immediately visible to reader
    }

    @Override
    public void run() {
        while (running) {      // volatile read: always reads from main memory
            doWork();
        }
        System.out.println("Worker stopped.");
    }

    private void doWork() { /* ... */ }
}
```

Without `volatile`, the JIT compiler might observe that `running` is never written within `run()` and optimize the loop to `while (true)` — hoisting the read out of the loop. This is a legal optimization for non-volatile variables because, within the thread, `running` never changes. `volatile` tells the JIT: this variable can change externally; do not cache it. Every iteration must re-read from main memory.

### Double-Checked Locking: The Classic volatile Pattern

Double-checked locking is a pattern for lazy singleton initialization that avoids the overhead of acquiring a lock on every call, while still being safe for concurrent initialization:

```java
public class Singleton {
    // volatile is MANDATORY here. Without it, this pattern is broken.
    private volatile static Singleton instance;

    private Singleton() {
        // expensive initialization...
    }

    public static Singleton getInstance() {
        if (instance == null) {              // First check: no lock needed
            synchronized (Singleton.class) { // Lock only for initialization
                if (instance == null) {      // Second check: inside the lock
                    instance = new Singleton();
                }
            }
        }
        return instance;                     // Fast path: no lock
    }
}
```

Why is `volatile` mandatory? Object construction (`new Singleton()`) is not atomic. At the bytecode level, it is:
1. Allocate memory, get a reference
2. Initialize the object fields (call constructor body)
3. Assign the reference to `instance`

Without `volatile`, the JIT/CPU is free to reorder steps 2 and 3. Another thread can observe `instance != null` (step 3 completed) but then access an incompletely initialized object (step 2 not yet visible). This is not hypothetical — it was an actual bug in Java programs before the JMM was clarified in Java 5.

With `volatile`, the assignment to `instance` is a volatile write, which acts as a StoreStore barrier — steps 2 must complete before step 3. Any thread that reads `instance != null` (a volatile read, LoadLoad barrier) is guaranteed to see the fully constructed object.

```
  Thread A (initializing)          Thread B (reading)
  ─────────────────────────        ─────────────────────────
  allocate Singleton memory
  initialize fields                if (instance == null)  ← volatile read
  instance = ref  ← volatile       → sees null? → done, returns null
                    write          → sees ref? → guaranteed fields visible!
  StoreStore barrier
  ensures fields visible
  before ref assigned
```

### `volatile long` and `volatile double`

On 32-bit JVMs, reads and writes of `long` (64-bit) and `double` (64-bit) are not guaranteed to be atomic. The JVM can perform them as two 32-bit operations, which means another thread can see a "torn" value — the high 32 bits from one write and the low 32 bits from another. Declaring them `volatile` guarantees atomic 64-bit reads and writes. On 64-bit JVMs (which is essentially everything modern), longs and doubles are already written atomically, but the JMM guarantee only applies with `volatile`. If you have a `long` or `double` field that is accessed by multiple threads, make it `volatile` or protect it with `synchronized`.

### Instruction Reordering: Why `volatile` Ordering Matters

Consider this example without `volatile`:

```java
// Thread A:
result = compute();    // step 1
ready = true;          // step 2

// Thread B:
if (ready) {           // step 3
    use(result);       // step 4
}
```

Even if Thread A executes step 1 before step 2 in A's own thread (which is guaranteed by the program order rule for A), the CPU and compiler are free to reorder the writes to main memory. Thread B might observe `ready == true` (from main memory) before `result` has been flushed. Thread B then calls `use(result)` with a stale value.

With `volatile boolean ready`:
- The volatile write to `ready = true` (step 2) acts as a StoreStore barrier: `result = compute()` (step 1) cannot be reordered after it.
- The volatile read of `ready` (step 3) acts as a LoadLoad barrier: `use(result)` (step 4) cannot be reordered before it.
- The volatile variable rule establishes happens-before: step 2 hb step 3, and by transitivity (program order: 1 hb 2, 3 hb 4), we get 1 hb 4. Thread B is guaranteed to see the correct `result`.

```java
// CORRECT with volatile:
volatile boolean ready = false;
int result = 0;  // does NOT need to be volatile — covered by hb transitivity

// Thread A:
result = compute();   // hb: write result
ready = true;         // volatile write: flushes everything before it

// Thread B:
if (ready) {          // volatile read: sees everything before volatile write
    use(result);      // guaranteed to see compute()'s result
}
```

### Interview Trap

The most common `volatile` interview mistake: **`volatile` does not fix `i++`.**

```java
class BrokenCounter {
    volatile int count = 0;

    void increment() {
        count++;  // READ count, ADD 1, WRITE count — three steps, not atomic!
    }
}
```

Two threads calling `increment()` simultaneously:
- Thread 1 reads `count = 5` (volatile read from main memory)
- Thread 2 reads `count = 5` (volatile read from main memory)
- Thread 1 writes `count = 6` (volatile write to main memory)
- Thread 2 writes `count = 6` (volatile write to main memory — overwrites Thread 1's result!)

Net effect: two increments happened, but count went from 5 to 6, not 5 to 7. One increment was lost. The solution is `AtomicInteger.incrementAndGet()` (uses `LOCK CMPXCHG` CPU instruction — a single atomic compare-and-swap) or `synchronized void increment() { count++; }`.

Second trap: **`volatile` makes `non-volatile` fields visible through the happens-before chain.** If you correctly use `volatile` as a publication flag (like the `ready` example above), you do NOT need to make every field `volatile`. The happens-before transitivity ensures that all writes before the `volatile` write become visible to threads that read the `volatile` variable. This is a performance feature: you don't need to declare every field of a published object `volatile` — just the reference/flag used to publish it.

### Memory Trick

```
volatile = visibility (main memory) + ordering (memory barriers)
volatile does NOT = atomicity for compound ops (i++ is still 3 steps)
volatile write ──► StoreStore + StoreLoad barriers (nothing reordered past it)
volatile read  ──► LoadLoad + LoadStore barriers (nothing reordered before it)
Happens-before chain: volatile write hb volatile read (by transitivity)
Publication idiom: write fields, THEN write volatile flag → reader sees all fields
DCL pattern: volatile instance = MANDATORY (prevents seeing half-constructed object)
volatile long/double: guarantees atomic 64-bit read/write (needed on 32-bit JVMs)
```

---

## J6.4 — wait/notify/notifyAll

> **Builds on:** [J6.2 — synchronized & Monitor Locks](J6_concurrency_fundamentals.md#j62--synchronized--monitor-locks) · [J6.3 — volatile & Java Memory Model](J6_concurrency_fundamentals.md#j63--volatile--java-memory-model)
> **Connects to:** [J6.1 — Thread Lifecycle](J6_concurrency_fundamentals.md#j61--thread-lifecycle)

### The Concrete Picture

Producer-consumer with a bounded buffer of capacity 1:

```
Initial state: buffer empty, consumer waiting

Consumer thread:
  synchronized(lock) {
    while (buffer.isEmpty()) {      ← check condition
      lock.wait();                  ← ATOMICALLY: release lock + suspend (WAITING)
    }                               ← woken up, re-checks while (not if!)
    item = buffer.poll();
    lock.notifyAll();               ← wake sleeping producers
  }

Producer thread:
  synchronized(lock) {              ← acquires lock (consumer released it via wait())
    buffer.add(item);               ← buffer now has 1 item
    lock.notifyAll();               ← moves consumer from WAITING ──► BLOCKED
  }                                 ← releases lock

Consumer reacquires lock:
  BLOCKED ──► RUNNABLE ──► while(!isEmpty) is false ──► poll() executes

Why while (not if):
  notifyAll() wakes ALL waiters → 2 consumers both wake → 1st takes item
  2nd consumer: re-checks → buffer empty → wait() again (correct)
  if statement: 2nd consumer skips check → buffer.poll() on empty → BUG
```

### WHY This Matters

`synchronized` solves mutual exclusion: only one thread in the critical section at a time. But many concurrent problems require threads to coordinate based on application-level conditions, not just lock availability. A consumer thread needs to wait until a producer has produced something. A bounded buffer needs producers to pause when full and resume when space is available. A resource pool needs requesters to wait until a resource is free. These are condition-based waits, not lock-based waits. `wait()`, `notify()`, and `notifyAll()` are the low-level primitives for implementing condition-based waiting on top of Java's monitor system. Understanding them is essential both for using them correctly and for understanding how higher-level abstractions like `java.util.concurrent.locks.Condition` and `BlockingQueue` work under the hood.

### The Monitor Must Be Held

`wait()`, `notify()`, and `notifyAll()` are all methods on `Object`. They can only be called from within a `synchronized` block or method on the same object. Violating this rule throws `IllegalMonitorStateException` at runtime:

```java
Object obj = new Object();

// WRONG — not synchronized:
obj.wait();    // throws IllegalMonitorStateException

// CORRECT:
synchronized (obj) {
    obj.wait();  // OK — current thread holds obj's monitor
}
```

The reason this rule exists is fundamental: the monitor and the condition variable are one unified mechanism. The condition check ("is the queue non-empty?") and the act of waiting must be atomic with respect to each other. If you could check the condition and then call `wait()` without holding the lock, another thread could signal between the check and the wait — and the signal would be lost. Holding the monitor prevents this race.

### `wait()`: Atomically Release and Suspend

Calling `wait()` on an object does three things atomically:
1. Releases the monitor (as if `MONITOREXIT` was called)
2. Suspends the current thread (transitions to WAITING state)
3. Places the thread in the object's wait set (a list of threads waiting on this object)

When the thread is later woken (by `notify()`, `notifyAll()`, or `interrupt()`), it:
1. Leaves the wait set
2. Reacquires the monitor (transitions to BLOCKED until it gets the lock, then RUNNABLE)
3. Returns from `wait()`

The atomicity of "release lock and suspend" is critical. If these were two separate operations, a signal could be sent between them — the lock is released but the thread hasn't suspended yet — and the signal would be lost.

```
Thread A (waiter):                    Thread B (notifier):
─────────────────────────────────     ─────────────────────────────────
synchronized (obj) {
  while (!condition) {
    obj.wait();
    │
    ├─ releases monitor                   synchronized (obj) {
    ├─ suspends self (WAITING)   ─────►     condition = true;
    │                                       obj.notify();
    │  ◄─────────────────────────────────   // puts A back in contention
    │                                     }
    ├─ reacquires monitor (BLOCKED then RUNNABLE)
    └─ returns from wait()
  }
  doWork();  // condition is now true
}
```

### Spurious Wakeups: Always Use `while`, Never `if`

The JVM specification explicitly allows threads to wake up from `wait()` without being notified. This is called a spurious wakeup, and it is not a Java-specific quirk — it is a consequence of how condition variables are implemented at the POSIX thread level on most operating systems. Linux's `pthread_cond_wait` can return spuriously due to signals and certain kernel scheduler behaviors.

Because of spurious wakeups, you must always re-check the condition after `wait()` returns. The correct pattern is a `while` loop:

```java
// CORRECT: while loop
synchronized (lock) {
    while (!conditionMet()) {    // re-check condition every time we wake
        lock.wait();
    }
    // here, condition is GUARANTEED to be true
    doWork();
}

// WRONG: if statement
synchronized (lock) {
    if (!conditionMet()) {       // checked only once!
        lock.wait();
    }
    // condition might NOT be true here (spurious wakeup, or wrong thread woke up)
    doWork();  // DEFECT: may execute when condition is false
}
```

The `while` pattern is also correct for a second reason: when `notifyAll()` wakes multiple waiting threads, only one at a time can reacquire the monitor. By the time the second waiter gets the lock, the first waiter may have already consumed the condition (e.g., taken the only item from the queue). The second waiter must re-check and wait again.

### Producer-Consumer with Bounded Buffer

The classic application of wait/notify. A bounded buffer allows producers to add items and consumers to take items, with blocking when the buffer is full or empty:

```java
public class BoundedBuffer<T> {
    private final Queue<T> queue;
    private final int capacity;
    private final Object lock = new Object();

    public BoundedBuffer(int capacity) {
        this.capacity = capacity;
        this.queue = new LinkedList<>();
    }

    public void put(T item) throws InterruptedException {
        synchronized (lock) {
            while (queue.size() == capacity) {  // full — wait for consumers
                lock.wait();                    // releases lock, suspends producer
            }
            queue.add(item);
            lock.notifyAll();                   // wake sleeping consumers (and producers)
        }
    }

    public T take() throws InterruptedException {
        synchronized (lock) {
            while (queue.isEmpty()) {           // empty — wait for producers
                lock.wait();                    // releases lock, suspends consumer
            }
            T item = queue.poll();
            lock.notifyAll();                   // wake sleeping producers (and consumers)
            return item;
        }
    }

    public int size() {
        synchronized (lock) {
            return queue.size();
        }
    }
}
```

Walk through a scenario:
- Producer puts item 1: queue was empty, adds item, calls `notifyAll()` to wake any waiting consumers.
- Consumer takes item 1: queue is empty again, calls `notifyAll()` to wake any waiting producers.
- Second consumer calls `take()`: queue is empty, enters `while` loop, calls `wait()`, suspends and releases lock.
- Producer calls `put()`: acquires lock, adds item, calls `notifyAll()`. Second consumer wakes, reacquires lock, re-checks `queue.isEmpty()` (now false), proceeds to poll and return the item.

The `while` loop is essential: `notifyAll()` wakes all waiters, but only one can proceed at a time. Each waker must re-check the condition because the state may have changed while they waited for the lock.

### `notify()` vs `notifyAll()`: When to Use Which

```
notify()
─────────
Wakes exactly ONE thread from the wait set.
Which thread is woken is unspecified (JVM/OS choice, not FIFO).
Fast: only one thread transitions from WAITING to BLOCKED.
Risk: if the wrong thread is woken and goes back to wait(),
      the notification is wasted. Progress may stop.

Safe to use only when ALL of these are true:
1. All waiting threads are waiting for the same single condition
   (one type of waiter, not "waiting for empty" AND "waiting for full")
2. Any one of the waiting threads can correctly handle the condition
   (they are fungible — it doesn't matter which one wakes up)
3. Only one condition is possible (not multiple types of conditions
   mixed in the same wait set)

notifyAll()
──────────
Wakes ALL threads in the wait set.
All transition from WAITING to BLOCKED; compete for the lock.
Slower: thundering herd — many threads wake up, but only one proceeds.
Safe: at least one correct thread will always proceed.
Required when: multiple types of waiters use the same lock
               (producers AND consumers on the same lock).

DEFAULT RULE: use notifyAll() unless you can prove notify() is safe.
```

In the `BoundedBuffer` above, `notifyAll()` is required because both producers (waiting when full) and consumers (waiting when empty) use the same lock. If we used `notify()` when adding an item, we might accidentally wake a producer instead of a consumer — the producer re-checks `queue.size() == capacity` (false, there's now one item), re-waits... but no consumer was woken. The system may deadlock.

### `wait(long timeout)` and Interruption

`wait(ms)` and `wait(ms, ns)` provide timed waiting. The thread wakes when signaled, interrupted, or the timeout expires. There is no way to determine from `wait()`'s return which of these occurred — you must re-check the condition.

`wait()` throws `InterruptedException` when the thread is interrupted while waiting. When this happens, the interrupted status flag is cleared. You should either re-interrupt (restore the flag) or let the `InterruptedException` propagate:

```java
synchronized (lock) {
    while (!condition) {
        try {
            lock.wait();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();  // restore interrupted flag
            return;  // or throw, depending on your design
        }
    }
    doWork();
}
```

### Thread State Transitions in wait/notify

```
Thread A (calling wait()):
  RUNNABLE
     │ calls obj.wait() while holding obj's monitor
     ▼
  [releases monitor]
     │
     ▼
  WAITING (in obj's wait set)
     │ another thread calls obj.notify()/notifyAll()
     ▼
  BLOCKED (trying to reacquire obj's monitor)
     │ monitor becomes available
     ▼
  RUNNABLE (wait() returns, monitor held again)

Thread B (calling notify()):
  RUNNABLE (holds obj's monitor)
     │ calls obj.notify()
     │ — moves one thread from wait set to blocked set
     │ — Thread B continues holding the monitor until it exits synchronized
     ▼
  [exits synchronized block — releases monitor]
  RUNNABLE
     │ Thread A can now reacquire
```

The key insight: `notify()` does not immediately transfer the lock. Thread B keeps the lock until it exits the synchronized block. Only then can Thread A reacquire the lock and return from `wait()`. This means Thread B can safely do additional work after `notify()` — the notified thread will not interfere until B releases the lock.

### The Critical Difference: `wait()` vs `Thread.sleep()`

This is one of the most common interview questions in this space:

```
Thread.sleep(ms)                      Object.wait()
──────────────────────────            ─────────────────────────────────
DOES NOT release any locks held.      DOES release the monitor (the lock
                                      on which wait() is called).

All other threads blocked on          Other threads CAN acquire the
the same lock remain blocked          monitor and proceed while this
while this thread sleeps.             thread is waiting.

Woken by: timeout expiration          Woken by: notify(), notifyAll(),
          or interrupt().             timeout (if wait(ms)), or interrupt().

Used for: time delays, rate           Used for: condition-based waiting.
          limiting, retry backoff.    Thread suspends until a condition
                                      becomes true.

Called on: Thread (static method)     Called on: any Object (instance method)
                                      while holding that object's monitor.
```

```java
// Sleeping thread BLOCKS other threads:
synchronized (lock) {
    Thread.sleep(5000);  // holds lock for 5 seconds
                         // all other threads trying to synchronized(lock) are BLOCKED
}

// Waiting thread RELEASES lock:
synchronized (lock) {
    lock.wait(5000);     // releases lock immediately
                         // other threads CAN acquire lock during this 5 seconds
                         // this thread reacquires lock before returning
}
```

### Interview Trap

Two traps examiners use:

**Trap 1: `if` instead of `while`.** Showing code with `if (!empty) obj.wait()` and asking "what's wrong?" The answer is spurious wakeups and the missed-notification race. The fix is `while (!empty) obj.wait()`. Always.

**Trap 2: `notify()` without holding the lock.** Code that calls `obj.notify()` outside a `synchronized(obj)` block. This throws `IllegalMonitorStateException`. But more subtly, even if you try to "fix" it by removing the condition check (perhaps using a flag instead), you create a missed-notification race: the waiter checks the flag (false), the notifier sets the flag and calls `notify()`, the waiter calls `wait()` — and the notification has already been sent. The waiter waits forever. This is why the lock must be held for both the condition check AND the wait/notify. Holding the lock is what makes the check-then-act atomic.

### Memory Trick

```
wait/notify/notifyAll: MUST be called while holding the monitor (else IllegalMonitorStateException)
wait(): atomically releases lock + suspends (WAITING); returns when signalled + re-acquires lock
ALWAYS use while loop: spurious wakeups + notifyAll wakes wrong-condition threads
notify()    = wakes ONE (unspecified) thread; safe only if all waiters are fungible
notifyAll() = wakes ALL; default choice; thundering herd but always correct
sleep() ≠ wait(): sleep holds lock; wait releases lock
missed signal: check flag THEN wait — must be inside same synchronized block
```

---

## Master Summary

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    J6 — Concurrency Fundamentals                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  1. THREAD LIFECYCLE (Thread.State — 6 states)                              │
│     NEW → RUNNABLE → BLOCKED (waiting for monitor lock)                     │
│                    → WAITING (wait/join/park — voluntarily suspended)       │
│                    → TIMED_WAITING (sleep/wait(ms)/join(ms)/parkNanos)      │
│                    → TERMINATED (run() returned or threw, no restart)       │
│                                                                             │
│     BLOCKED ≠ WAITING. BLOCKED = competing for a lock involuntarily.       │
│     WAITING = released lock, waiting for explicit signal. Read              │
│     thread dumps: "BLOCKED (on object monitor)" vs "in Object.wait()".     │
│     Daemon threads die when all non-daemon threads finish.                  │
│                                                                             │
│  2. SYNCHRONIZED & MONITOR LOCKS                                            │
│     Every object has a monitor. synchronized acquires it via               │
│     MONITORENTER/MONITOREXIT bytecodes (implicit try-finally guarantees    │
│     MONITOREXIT even on exception — no lock leaks).                         │
│                                                                             │
│     Reentrant: same thread can re-acquire the same monitor (depth          │
│     counter). Lock upgrade: biased → thin (CAS) → fat (OS mutex).         │
│     Memory visibility: unlock happens-before next lock (monitor rule).     │
│                                                                             │
│     TRAP: synchronized(this) and synchronized(privateObj) are              │
│     DIFFERENT monitors. Mixing them provides zero mutual exclusion.        │
│                                                                             │
│  3. VOLATILE & JAVA MEMORY MODEL                                            │
│     JMM happens-before rules determine visibility. volatile provides:      │
│     (a) Visibility: writes flushed to main memory; reads bypass cache.     │
│     (b) Ordering: memory barrier prevents instruction reordering.          │
│     (c) Atomic 64-bit reads/writes for long and double.                    │
│                                                                             │
│     volatile does NOT provide atomicity for compound ops.                  │
│     volatile i++ is still read-increment-write (3 steps, not atomic).     │
│     Use AtomicInteger for atomic compound operations.                       │
│                                                                             │
│     Double-checked locking requires volatile on the instance field.        │
│     Without it, the reference can be seen non-null before object fields    │
│     are initialized (JIT/CPU reordering of constructor + assignment).      │
│                                                                             │
│  4. WAIT / NOTIFY / NOTIFYALL                                               │
│     Must hold the monitor: calling without synchronized →                  │
│     IllegalMonitorStateException.                                           │
│                                                                             │
│     wait(): atomically releases lock AND suspends (WAITING).               │
│     notify(): wakes ONE thread from wait set (which one: unspecified).     │
│     notifyAll(): wakes ALL threads from wait set (safer, use by default).  │
│                                                                             │
│     ALWAYS use while loop (not if) for condition check — spurious          │
│     wakeups are real, and notifyAll() can wake wrong-condition threads.    │
│                                                                             │
│     TRAP: Thread.sleep() does NOT release the lock. wait() DOES.           │
│     A sleeping thread blocks all other threads on the same monitor.        │
│     A waiting thread lets other threads acquire the monitor and proceed.   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

*← [Phase J5 — Collections](J5_collections.md) | [Phase J7 — java.util.concurrent →](J7_concurrent_utilities.md)*
