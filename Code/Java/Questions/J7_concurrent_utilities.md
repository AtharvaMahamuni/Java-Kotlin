# Phase J7 — java.util.concurrent

Phase J6 built the foundational mental model: thread states, monitor locks, the Java Memory Model, and wait/notify. Phase J7 is about the higher-level toolkit that the JDK provides on top of that foundation. `java.util.concurrent` (JUC) was introduced in Java 5 to replace the error-prone, low-level synchronized/wait/notify patterns with composable, well-tested abstractions. Senior interviews expect you to know when to use each tool, why it outperforms the naive alternative, and what the internal implementation looks like. These questions appear in nearly every systems-focused Java interview at top-tier companies.

---

## J7.1 — Executor Framework & ThreadPoolExecutor

> **Builds on:** [J6.1 — Thread Lifecycle](J6_concurrency_fundamentals.md#j61--thread-lifecycle)
> **Connects to:** [J7.6 — CompletableFuture](J7_concurrent_utilities.md#j76--completablefuture)

### The Concrete Picture

Start: `ThreadPoolExecutor(core=2, max=4, queue=ArrayBlockingQueue(3))`, submit 8 tasks:

```
T1 submitted ──► running threads (0) < core (2) ──► start Thread-1, run T1
T2 submitted ──► running threads (1) < core (2) ──► start Thread-2, run T2
T3 submitted ──► running = core = 2; queue.offer(T3) succeeds ──► queued [T3]
T4 submitted ──► queue.offer(T4) succeeds ──► queued [T3, T4]
T5 submitted ──► queue.offer(T5) succeeds ──► queued [T3, T4, T5]
T6 submitted ──► queue FULL; running (2) < max (4) ──► start Thread-3, run T6
T7 submitted ──► queue FULL; running (3) < max (4) ──► start Thread-4, run T7
T8 submitted ──► queue FULL; running = max = 4 ──► RejectedExecutionHandler!

newFixedThreadPool(4):  uses LinkedBlockingQueue (UNBOUNDED)
  ──► T6, T7, T8 all queue (never reach max) ──► queue grows without bound!
  ──► Under load: queue fills heap ──► OutOfMemoryError
```

### WHY This Matters

Before `java.util.concurrent`, developers managed threads directly: `new Thread(task).start()`. This is fine for one or two threads but catastrophic at scale. Thread creation is expensive — each thread allocates a stack (512 KB to 1 MB by default), registers with the OS scheduler, and has a teardown cost. Creating one thread per incoming request in a server under load produces thousands of threads, exhausting heap memory and causing the OS scheduler to spend more time context-switching than executing work.

The Executor framework solves this by decoupling task submission from task execution. You submit a `Runnable` or `Callable`; the framework decides which thread runs it, when, and how. The pool reuses threads rather than creating new ones per task. This is the standard approach for all server-side Java — Spring, Vert.x, Netty all use thread pools internally.

### The Executor Hierarchy

```
Executor (interface)
  └─ ExecutorService (interface) — adds shutdown(), submit(), invokeAll(), invokeAny()
       ├─ ThreadPoolExecutor (class) — the core, all pools are wrappers around this
       ├─ ScheduledExecutorService (interface) — schedule, scheduleAtFixedRate
       │    └─ ScheduledThreadPoolExecutor (class)
       └─ ForkJoinPool (class) — work-stealing pool for divide-and-conquer tasks
```

`Executors` (factory class) provides convenience factory methods:

```java
ExecutorService fixed  = Executors.newFixedThreadPool(4);       // 4 threads, unbounded queue
ExecutorService cached = Executors.newCachedThreadPool();        // 0-∞ threads, 60s keepalive
ExecutorService single = Executors.newSingleThreadExecutor();    // 1 thread, sequential order
ScheduledExecutorService sched = Executors.newScheduledThreadPool(2);
```

### ThreadPoolExecutor: The 7 Parameters

All the factory methods ultimately create a `ThreadPoolExecutor`. Understanding its constructor parameters is essential:

```java
new ThreadPoolExecutor(
    int corePoolSize,         // threads always kept alive (even idle)
    int maximumPoolSize,      // maximum threads allowed at peak load
    long keepAliveTime,       // how long idle threads > core survive before dying
    TimeUnit unit,            // time unit for keepAliveTime
    BlockingQueue<Runnable> workQueue,  // holds tasks when all core threads are busy
    ThreadFactory threadFactory,        // customizes thread creation (name, daemon, priority)
    RejectedExecutionHandler handler    // what to do when queue is full AND at maximumPoolSize
);
```

### Task Dispatch Logic: The Critical Mental Model

This is the most important part — how `ThreadPoolExecutor` decides what to do when you submit a task:

```
Submit task
     │
     ▼
Is (running threads) < corePoolSize?
  YES → start a new thread (even if idle threads exist)
  NO  ─────────────────────────────────────────┐
                                               ▼
                                   Is workQueue.offer(task) successful?
                                     YES → task queued, existing thread picks it up
                                     NO (queue full) ──────────────────────────────┐
                                                                                   ▼
                                                               Is (running) < maximumPoolSize?
                                                                 YES → start a new thread
                                                                 NO → RejectedExecutionHandler
```

Key insight: **the pool does NOT grow beyond corePoolSize until the queue is full.** With an unbounded `LinkedBlockingQueue` (what `Executors.newFixedThreadPool` uses), the pool never exceeds corePoolSize because the queue never fills up. With a bounded queue, the pool can grow to `maximumPoolSize` when the queue fills.

> **PRODUCTION TRAP:** `newFixedThreadPool` uses an **unbounded** `LinkedBlockingQueue`. Under sustained overload, the queue grows without bound → `OutOfMemoryError`. For bounded backpressure, construct `ThreadPoolExecutor` directly with a bounded queue and a `CallerRunsPolicy`:
> ```java
> ExecutorService pool = new ThreadPoolExecutor(
>     4, 4, 0L, TimeUnit.MILLISECONDS,
>     new ArrayBlockingQueue<>(1000),         // bounded queue
>     new ThreadPoolExecutor.CallerRunsPolicy() // slow caller down instead of OOM
> );
> ```

```
Example: corePoolSize=2, maximumPoolSize=4, queue capacity=3

  Tasks:  T1  T2  T3  T4  T5  T6  T7
          │   │   │   │   │   │   │
          ▼   ▼   ▼   ▼   ▼   ▼   ▼
  T1 → start thread 1 (0 < 2)
  T2 → start thread 2 (1 < 2)
  T3 → queue (threads = core = 2; offer → queue[0])
  T4 → queue (queue[1])
  T5 → queue (queue[2])
  T6 → queue full! start thread 3 (2 < 4)
  T7 → queue full! start thread 4 (3 < 4)
  T8 → queue full, at max! → RejectedExecutionHandler
```

### Rejection Policies (RejectedExecutionHandler)

| Policy | Behavior |
|--------|----------|
| `AbortPolicy` (default) | Throws `RejectedExecutionException` |
| `CallerRunsPolicy` | The calling thread runs the task itself (natural backpressure) |
| `DiscardPolicy` | Silently drops the task |
| `DiscardOldestPolicy` | Drops the oldest queued task, retries submit |

`CallerRunsPolicy` is often the right default for batch-processing systems — it slows down the producer naturally when the pool is saturated, rather than losing work or crashing.

### Future and Callable

`Runnable` cannot return a result or throw a checked exception. `Callable<T>` solves both:

```java
ExecutorService pool = Executors.newFixedThreadPool(4);

// submit returns a Future<T>
Future<Integer> future = pool.submit(() -> {
    // compute something expensive
    return 42;
});

// Do other work here...

try {
    Integer result = future.get();         // blocks until done
    Integer result2 = future.get(1, TimeUnit.SECONDS); // blocks up to 1s, then TimeoutException
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();    // restore interrupted status
} catch (ExecutionException e) {
    Throwable cause = e.getCause();        // the exception thrown inside the Callable
}
```

```
Future states:
  PENDING ──(computation finishes)──► DONE (success: get() returns result)
         └──(exception thrown)──────► DONE (failure: get() throws ExecutionException)
         └──(future.cancel(true))───► CANCELLED (get() throws CancellationException)
```

### invokeAll and invokeAny

```java
List<Callable<String>> tasks = List.of(
    () -> "task1",
    () -> "task2",
    () -> "task3"
);

// invokeAll: submits all, blocks until ALL complete, returns List<Future>
List<Future<String>> results = pool.invokeAll(tasks);
// All futures are done when invokeAll returns

// invokeAny: submits all, returns result of FIRST to complete, cancels rest
String first = pool.invokeAny(tasks);
```

### Proper Shutdown

```java
pool.shutdown();                      // no new tasks; existing tasks complete
pool.awaitTermination(30, TimeUnit.SECONDS);  // wait up to 30s
if (!pool.isTerminated()) {
    pool.shutdownNow();               // interrupt running tasks; returns queued tasks
}
```

Never call `System.exit()` without shutting down pools — daemon threads die but non-daemon pool threads keep the JVM alive.

### Interview Trap: Executors.newCachedThreadPool() in a Server

```java
// DANGEROUS under load:
ExecutorService cached = Executors.newCachedThreadPool();
// Uses SynchronousQueue (capacity 0) — every submitted task spawns a thread if no idle ones
// Under sudden load spike: 10,000 requests → 10,000 threads → OOM
```

For servers, always use a bounded pool with a bounded queue and an explicit rejection handler. `newCachedThreadPool()` is appropriate for tasks that are numerous, short-lived, and whose arrival rate is bounded (e.g., internal async callbacks).

---

## J7.2 — Concurrent Collections

> **Builds on:** [J5 — Collections](J5_collections.md) · [J6.2 — synchronized & Monitor Locks](J6_concurrency_fundamentals.md#j62--synchronized--monitor-locks)
> **Connects to:** [J7.1 — Executor Framework](J7_concurrent_utilities.md#j71--executor-framework--threadpoolexecutor)

### WHY Not Just Use synchronized Collections?

`Collections.synchronizedMap(new HashMap<>())` wraps every method in `synchronized(this)`. Every operation — `get`, `put`, `containsKey` — acquires the same lock on the entire map. This means:

1. Only one thread can access the map at a time — no concurrency benefit for reads.
2. Iteration requires external synchronization (the wrapper does NOT synchronize iteration).
3. Compound operations like "check if key exists, then put" are NOT atomic without additional external synchronization.

`java.util.concurrent` provides purpose-built data structures that solve all three problems.

### ConcurrentHashMap

The most important concurrent collection. Replaces `Hashtable` and `synchronizedMap` in all new code.

**Segment-based locking (Java 7):** The map was divided into 16 segments (by default), each independently locked. Reads on different segments were concurrent.

**Node-level locking (Java 8+):** This is the current implementation. The internal array of buckets uses lock-free reads via `volatile` and CAS operations. Writes lock only the specific bucket head node (`synchronized` on that node). This means:
- Reads: always lock-free (reads `volatile` fields directly)
- Writes: lock one bucket at a time (not the whole map)
- Up to `n` (number of buckets) write operations can proceed concurrently

```
ConcurrentHashMap internal (Java 8+):
  table[] (volatile array)
  ┌───┬───┬───┬───┬───┬───┬───┬───┐
  │ N │ N │ N │ N │ N │ N │ N │ N │  ← bucket heads (Node objects)
  └───┴───┴───┴───┴───┴───┴───┴───┘
    │               │
    ▼               ▼
  Node(k1,v1)   Node(k3,v3)     ← linked list per bucket (or TreeNode when >8 entries)
    │
  Node(k2,v2)

  Read: load table[hash] via volatile → traverse chain (NO lock)
  Write: synchronized(table[hash]) → modify chain (lock ONE bucket)
```

**Atomic compound operations:**

```java
ConcurrentHashMap<String, Integer> map = new ConcurrentHashMap<>();

// These are all atomic (single method = single synchronized block on the bucket):
map.putIfAbsent("key", 1);                          // put only if absent
map.computeIfAbsent("key", k -> expensive(k));      // compute + put if absent
map.computeIfPresent("key", (k, v) -> v + 1);       // compute only if present
map.compute("key", (k, v) -> v == null ? 1 : v + 1); // always compute
map.merge("key", 1, Integer::sum);                  // merge with existing value

// This is NOT atomic (two separate operations):
if (!map.containsKey("key")) {    // ← another thread can insert here
    map.put("key", 1);            // ← race condition!
}
// Use putIfAbsent() instead.
```

**Size is approximate:** `map.size()` in `ConcurrentHashMap` is an estimate (uses a `LongAdder`-like striped counter). It's not guaranteed to be exact under concurrent modification. `mappingCount()` is preferred in Java 8+.

### CopyOnWriteArrayList

Designed for read-heavy workloads with infrequent writes.

**Mechanism:** On every mutation (`add`, `remove`, `set`), the entire backing array is copied to a new array, modified, and the reference atomically updated:

```java
// Simplified implementation of CopyOnWriteArrayList.add():
public boolean add(E e) {
    synchronized (lock) {
        Object[] elements = getArray();
        int len = elements.length;
        Object[] newElements = Arrays.copyOf(elements, len + 1);  // copy entire array
        newElements[len] = e;
        setArray(newElements);  // atomic reference swap
        return true;
    }
}
```

**Reads are lock-free:** Reads see a snapshot of the array at the moment the read started. A concurrent write creates a new array — the reader's reference still points to the old array. This is safe because arrays are never modified after being set as the backing array.

```
Initial state:  array → [A, B, C]   ← reader holds this reference
Writer starts:          [A, B, C] (copy)
Writer modifies: new_array → [A, B, C, D]
Writer swaps:   array → [A, B, C, D]  (reader is unaffected, still seeing old snapshot)
```

**When to use CopyOnWriteArrayList:**
- Listeners/observers list (many reads, rare add/remove)
- Configuration that updates occasionally but is read constantly
- When iteration must not throw `ConcurrentModificationException`

**When NOT to use:** Any write-heavy workload. Each write copies the entire array — O(n) per write.

### BlockingQueue

`BlockingQueue<E>` extends `Queue` with blocking operations for producer-consumer patterns:

| Method | Behavior on empty (consumer) | Behavior on full (producer) |
|--------|------------------------------|----------------------------|
| `add(e)` / `remove()` | throws `NoSuchElementException` | throws `IllegalStateException` |
| `offer(e)` / `poll()` | returns `null` | returns `false` |
| `put(e)` / `take()` | **blocks** indefinitely | **blocks** indefinitely |
| `offer(e, t, u)` / `poll(t, u)` | **blocks** up to timeout | **blocks** up to timeout |

**Key implementations:**

```java
// LinkedBlockingQueue: optionally bounded, linked nodes, separate lock for head/tail
BlockingQueue<Task> queue = new LinkedBlockingQueue<>(1000); // bounded capacity

// ArrayBlockingQueue: bounded, backed by array, single lock
BlockingQueue<Task> queue = new ArrayBlockingQueue<>(1000);

// PriorityBlockingQueue: unbounded, priority ordering (Comparable or Comparator)
BlockingQueue<Task> queue = new PriorityBlockingQueue<>();

// SynchronousQueue: no internal capacity — each put() blocks until a take() matches
// Used by Executors.newCachedThreadPool()
BlockingQueue<Runnable> handoff = new SynchronousQueue<>();

// DelayQueue: elements become available only after their delay expires
// Used for scheduled task execution
BlockingQueue<Delayed> delayed = new DelayQueue<>();
```

**Producer-consumer with BlockingQueue:**

```java
BlockingQueue<String> queue = new LinkedBlockingQueue<>(100);

// Producer thread:
while (true) {
    String item = produce();
    queue.put(item);   // blocks if queue is full — natural backpressure
}

// Consumer thread:
while (true) {
    String item = queue.take();   // blocks if queue is empty
    consume(item);
}
```

This is cleaner and safer than implementing the same pattern with `wait()/notify()`.

### LinkedBlockingQueue vs ArrayBlockingQueue

| Feature | LinkedBlockingQueue | ArrayBlockingQueue |
|---------|--------------------|--------------------|
| Backing structure | Linked nodes | Array |
| Capacity | Optionally bounded (default: `Integer.MAX_VALUE`) | Always bounded |
| Lock | Two locks: putLock + takeLock (higher concurrency) | One lock |
| Memory | Higher per-element (node allocation) | Fixed array (lower overhead) |
| Use when | High throughput, mixed producers/consumers | Bounded, predictable memory |

`LinkedBlockingQueue`'s two-lock design means a producer and consumer can operate concurrently (producer acquires `putLock`, consumer acquires `takeLock`), which doubles throughput under high contention vs `ArrayBlockingQueue`.

---

## J7.3 — ReentrantLock & ReadWriteLock

> **Builds on:** [J6.2 — synchronized & Monitor Locks](J6_concurrency_fundamentals.md#j62--synchronized--monitor-locks)

### WHY ReentrantLock Over synchronized?

`synchronized` is always a blocking, non-timed, non-interruptible lock acquisition. `ReentrantLock` provides everything `synchronized` does plus:

1. **Timed lock acquisition:** try to acquire, give up after a timeout
2. **Interruptible acquisition:** another thread can interrupt a waiting thread
3. **Non-blocking try:** `tryLock()` returns immediately with `false` if lock is unavailable
4. **Fairness option:** threads acquire in order of waiting (prevents starvation, at cost of throughput)
5. **Multiple condition variables:** `newCondition()` replaces wait/notify with named conditions

```java
ReentrantLock lock = new ReentrantLock();     // non-fair (default)
ReentrantLock fairLock = new ReentrantLock(true);  // fair (FIFO ordering)

// Basic usage — ALWAYS use try-finally to guarantee unlock
lock.lock();
try {
    // critical section
} finally {
    lock.unlock();   // must be in finally — otherwise lock leaked on exception
}

// Timed acquisition:
boolean acquired = lock.tryLock(500, TimeUnit.MILLISECONDS);
if (acquired) {
    try {
        // critical section
    } finally {
        lock.unlock();
    }
} else {
    // handle lock not acquired (timeout)
}

// Non-blocking try:
if (lock.tryLock()) {
    try { /* ... */ } finally { lock.unlock(); }
} else {
    // do something else
}

// Interruptible acquisition (throws InterruptedException if interrupted while waiting):
lock.lockInterruptibly();
```

### Condition Variables: Replacing wait/notify

`synchronized` gives you one wait-set per object. `ReentrantLock` lets you create multiple `Condition` objects — separate wait-sets for different conditions:

```java
ReentrantLock lock = new ReentrantLock();
Condition notFull  = lock.newCondition();   // wait here when buffer is full
Condition notEmpty = lock.newCondition();   // wait here when buffer is empty

// Producer:
lock.lock();
try {
    while (buffer.isFull()) notFull.await();   // releases lock, waits
    buffer.add(item);
    notEmpty.signal();   // wake one consumer (not all — we know exactly who to wake)
} finally {
    lock.unlock();
}

// Consumer:
lock.lock();
try {
    while (buffer.isEmpty()) notEmpty.await();
    T item = buffer.remove();
    notFull.signal();    // wake one producer
} finally {
    lock.unlock();
}
```

With `synchronized` and `Object.wait()`, calling `notifyAll()` would wake BOTH producers AND consumers, causing spurious competition. With named Conditions, you signal exactly the right waiting threads.

### ReadWriteLock: Concurrent Reads

`ReadWriteLock` (implemented by `ReentrantReadWriteLock`) allows multiple simultaneous readers OR one exclusive writer:

```
Lock states:
  No lock held           → any thread can acquire read or write lock
  Read lock(s) held      → other readers CAN acquire (concurrent reads)
                          → writers CANNOT acquire (blocked)
  Write lock held        → all readers BLOCKED
                          → all other writers BLOCKED (exclusive)
```

```java
ReentrantReadWriteLock rwLock = new ReentrantReadWriteLock();
ReadWriteLock.ReadLock  readLock  = rwLock.readLock();
ReadWriteLock.WriteLock writeLock = rwLock.writeLock();

// Reading (multiple threads can do this simultaneously):
readLock.lock();
try {
    return cache.get(key);
} finally {
    readLock.unlock();
}

// Writing (exclusive):
writeLock.lock();
try {
    cache.put(key, value);
} finally {
    writeLock.unlock();
}
```

**When ReadWriteLock is faster than synchronized:**
- Read operations are long or frequent
- Writes are rare (e.g., configuration updates, cache invalidations)
- Readers outnumber writers significantly

**When ReadWriteLock is SLOWER than synchronized:**
- Under write-heavy workloads: lock acquisition overhead exceeds benefit
- Under high contention with many threads: fairness + bookkeeping is expensive

### StampedLock (Java 8+): Optimistic Reads

`StampedLock` adds a third mode on top of read/write: **optimistic read**. An optimistic read does NOT acquire any lock — it simply reads a stamp (version number), reads the data, then validates that the stamp is still current (no write occurred):

```java
StampedLock sl = new StampedLock();

// Optimistic read (no lock acquired):
long stamp = sl.tryOptimisticRead();
int x = point.x;              // read without lock
int y = point.y;              // read without lock
if (!sl.validate(stamp)) {    // was a write lock acquired between tryOptimisticRead and now?
    // validation failed: fall back to regular read lock
    stamp = sl.readLock();
    try {
        x = point.x;
        y = point.y;
    } finally {
        sl.unlockRead(stamp);
    }
}

// Write:
long stamp = sl.writeLock();
try {
    point.x = newX;
    point.y = newY;
} finally {
    sl.unlockWrite(stamp);
}
```

`StampedLock` achieves maximum read throughput when writes are very rare — reads proceed with zero synchronization overhead in the common case. **However**: `StampedLock` is NOT reentrant (unlike `ReentrantLock`), does not support conditions, and its API is more complex. Use it only when profiling shows `ReadWriteLock` is a bottleneck.

---

## J7.4 — Atomic Variables & CAS

> **Builds on:** [J6.3 — volatile & Java Memory Model](J6_concurrency_fundamentals.md#j63--volatile--java-memory-model)
> **Connects to:** [J7.2 — Concurrent Collections](J7_concurrent_utilities.md#j72--concurrent-collections)

### WHY CAS Instead of Locking?

Locks have costs: context switches, OS involvement (for contended locks escalated to OS mutex), and thread blocking. For simple operations like incrementing a counter, this overhead is disproportionate. Compare-And-Swap (CAS) provides atomicity without locks — it's a single CPU instruction (`CMPXCHG` on x86, `STXR/LDXR` on ARM) that the CPU guarantees is atomic.

CAS semantics: "Set the memory location to `newValue` IF it currently contains `expectedValue`, otherwise do nothing. Return whether the swap succeeded."

```java
// Conceptual CAS (actual implementation is native/intrinsic):
boolean compareAndSet(long expectedValue, long newValue) {
    // ATOMIC (single CPU instruction):
    if (currentValue == expectedValue) {
        currentValue = newValue;
        return true;
    }
    return false;
}
```

### AtomicInteger

The most common atomic class. Uses `volatile int` + CAS under the hood:

```java
AtomicInteger counter = new AtomicInteger(0);

counter.get()                         // read (volatile load)
counter.set(42)                       // write (volatile store)
counter.getAndIncrement()             // i++ equivalent (returns old value)
counter.incrementAndGet()             // ++i equivalent (returns new value)
counter.addAndGet(5)                  // add 5, return new value
counter.compareAndSet(expected, new)  // CAS: returns true if swap succeeded

// Atomic update with a function (Java 8+):
counter.updateAndGet(x -> x * 2);    // atomically doubles the value
counter.accumulateAndGet(5, Integer::sum); // atomically adds 5
```

**Internally, increment looks like this:**

```java
// AtomicInteger.incrementAndGet() implementation:
public final int incrementAndGet() {
    return unsafe.getAndAddInt(this, valueOffset, 1) + 1;
    // getAndAddInt does a CAS loop:
    // do {
    //     v = getIntVolatile(obj, offset);  // read current value
    // } while (!compareAndSwapInt(obj, offset, v, v + 1));  // retry if CAS fails
    // return v;  // old value
}
```

CAS with retry loop: if two threads simultaneously try to increment, one will succeed and one will fail the CAS check (the value changed since it was read). The loser retries — re-reads the new value and tries again. No thread is ever blocked; both make forward progress.

### The ABA Problem

CAS compares values, not history. If a value changes from A → B → A, a CAS that expected A will succeed even though the state has changed:

```
Thread 1: reads value A
Thread 2: changes A → B, then B → A
Thread 1: CAS(expected=A, new=C) — SUCCEEDS! (sees A, doesn't know it changed)
```

In practice, ABA only matters when the "value" is a pointer and the objects at those addresses have different semantic state (e.g., a node that was removed and re-added to a lock-free stack). Solutions:
- `AtomicStampedReference<V>`: pairs a reference with an integer stamp (version counter)
- `AtomicMarkableReference<V>`: pairs a reference with a boolean mark

### AtomicReference and Field Updaters

```java
// AtomicReference: CAS on object references
AtomicReference<String> ref = new AtomicReference<>("initial");
ref.compareAndSet("initial", "updated");   // CAS on reference (pointer)

// AtomicReferenceFieldUpdater: CAS on a volatile field WITHOUT wrapping in AtomicReference
// Avoids object overhead when you have millions of objects each needing atomic updates
class Node {
    volatile Node next;
    static final AtomicReferenceFieldUpdater<Node, Node> nextUpdater =
        AtomicReferenceFieldUpdater.newUpdater(Node.class, Node.class, "next");
}
node.nextUpdater.compareAndSet(node, expectedNext, newNext);
```

`AtomicReferenceFieldUpdater` is used in the internals of `ConcurrentLinkedQueue` and other JDK data structures to avoid the per-object wrapper overhead of `AtomicReference`.

### LongAdder vs AtomicLong (High Contention)

`AtomicLong` with CAS becomes a bottleneck under very high thread contention — many threads retrying the same CAS loop on a single cache line. `LongAdder` (Java 8) solves this with striping:

```
LongAdder internal structure:
  base value (AtomicLong)
  cells[] (an array of Cell, each in its own cache line)

Thread 1 → cells[0]  ─┐
Thread 2 → cells[1]  ─┤
Thread 3 → cells[0]  ─┤
Thread 4 → cells[2]  ─┤── sum() = base + cells[0] + cells[1] + cells[2] + ...
Thread 5 → cells[1]  ─┘
```

Each thread hashes to a cell and does CAS on that cell. Contention is spread across multiple cache lines. Under low contention, threads use the `base` field directly (no cells allocated). `LongAdder.sum()` adds all cells — this is NOT atomic, so it's only accurate at a point when no updates are occurring.

**Rule:** Use `AtomicLong` when you need `get()`, `compareAndSet()`, or exact reads alongside increments. Use `LongAdder` for pure counters where you only need the total at the end (e.g., metrics, statistics).

---

## J7.5 — Synchronizers (CountDownLatch, CyclicBarrier, Semaphore)

> **Builds on:** [J6.1 — Thread Lifecycle](J6_concurrency_fundamentals.md#j61--thread-lifecycle) · [J7.1 — Executor Framework](J7_concurrent_utilities.md#j71--executor-framework--threadpoolexecutor)

### WHY Purpose-Built Synchronizers?

Coordinating threads using raw `wait()/notify()` is brittle. JUC provides three classes that cover the most common coordination patterns, each with a clear semantic contract and safe implementation on top of `AbstractQueuedSynchronizer` (AQS).

### CountDownLatch: Wait for N Events

A `CountDownLatch(N)` starts with count N. Any thread can call `countDown()` to decrement. Any thread calling `await()` blocks until the count reaches zero. The latch **cannot be reset** — it's one-time use.

**Pattern 1: One thread waits for multiple worker threads to finish**

```java
int workerCount = 5;
CountDownLatch latch = new CountDownLatch(workerCount);

for (int i = 0; i < workerCount; i++) {
    executor.submit(() -> {
        try {
            doWork();
        } finally {
            latch.countDown();  // always count down, even on exception
        }
    });
}

latch.await();  // main thread blocks until all 5 workers call countDown()
// All workers have finished — proceed
```

**Pattern 2: Multiple threads wait for a single start signal**

```java
CountDownLatch startSignal = new CountDownLatch(1);
CountDownLatch doneLatch = new CountDownLatch(workerCount);

for (int i = 0; i < workerCount; i++) {
    executor.submit(() -> {
        try {
            startSignal.await();   // all workers wait here
            doWork();
        } finally {
            doneLatch.countDown();
        }
    });
}

// All workers are now waiting at startSignal.await()
initializeResources();           // do setup while workers wait
startSignal.countDown();         // release ALL workers simultaneously
doneLatch.await();               // wait for all to finish
```

This pattern is useful for performance testing — it ensures all threads start simultaneously, measuring true concurrent throughput rather than staggered starts.

**State diagram:**

```
CountDownLatch(3):
  count=3: all await() calls BLOCK
  countDown() → count=2: still blocking
  countDown() → count=1: still blocking
  countDown() → count=0: ALL await() calls UNBLOCK simultaneously

  (count never goes negative; further countDown() calls are no-ops)
```

### CyclicBarrier: All-or-Nothing Rendezvous

A `CyclicBarrier(N)` makes N threads wait until all N have reached the barrier, then releases them all simultaneously. Unlike `CountDownLatch`, it **can be reused** (cyclic) — after all threads are released, the barrier resets.

```java
int threadCount = 4;
CyclicBarrier barrier = new CyclicBarrier(threadCount, () -> {
    // Optional barrier action: runs once in the last thread to arrive
    // before any thread is released
    System.out.println("All threads reached barrier — proceeding to next phase");
});

for (int i = 0; i < threadCount; i++) {
    executor.submit(() -> {
        for (int phase = 0; phase < 3; phase++) {
            doPhaseWork(phase);
            barrier.await();   // wait for ALL threads to finish this phase
            // ALL threads released simultaneously here, start next phase
        }
    });
}
```

```
CyclicBarrier(4) — thread arrival:
  Thread1 arrives → waiting (1/4)
  Thread2 arrives → waiting (2/4)
  Thread3 arrives → waiting (3/4)
  Thread4 arrives → count=4=parties → RELEASE ALL → barrier resets to 0/4
  ← All threads continue →
  Thread1 arrives (phase 2) → waiting (1/4)   ← reuse!
```

**CountDownLatch vs CyclicBarrier:**

| | CountDownLatch | CyclicBarrier |
|---|---|---|
| Who counts down? | ANY thread (not necessarily the waiters) | Only the waiting threads |
| Reusable? | No (one-shot) | Yes (resets after each release) |
| Barrier action? | No | Yes (runs in last arriving thread) |
| `broken` state? | No | Yes — if a thread is interrupted or barrier times out, barrier is broken and all threads throw `BrokenBarrierException` |
| Use case | Wait for events/tasks to complete | Synchronize steps across N peer threads |

### Semaphore: Resource Pool Limiting

A `Semaphore(N)` allows at most N threads to hold a permit simultaneously. `acquire()` blocks until a permit is available; `release()` returns a permit.

```java
// Allow at most 3 concurrent database connections:
Semaphore permits = new Semaphore(3);

// Thread competing for a connection:
permits.acquire();       // blocks if 3 threads already hold permits
try {
    useDatabase();
} finally {
    permits.release();   // always release in finally
}
```

**Key methods:**

```java
semaphore.acquire()            // block until 1 permit available
semaphore.acquire(3)           // block until 3 permits available (drains atomically)
semaphore.tryAcquire()         // return false immediately if no permit
semaphore.tryAcquire(1, TimeUnit.SECONDS)  // try for up to 1 second
semaphore.release()            // return 1 permit
semaphore.release(3)           // return 3 permits
semaphore.availablePermits()   // how many permits currently available
```

`Semaphore(1)` acts like a mutex (exclusive lock) but with one important difference: unlike `synchronized` or `ReentrantLock`, a Semaphore has NO concept of ownership — a different thread can call `release()` than the one that called `acquire()`. This enables producer-consumer signaling patterns impossible with locks.

```java
// Binary semaphore as a signal (not a lock):
Semaphore signal = new Semaphore(0);  // starts at 0 — consumer will block

// Producer:
doWork();
signal.release();   // post signal

// Consumer:
signal.acquire();   // wait for producer's signal
processResult();
```

### Phaser (Java 7): Flexible Multi-Phase Coordination

`Phaser` is a generalization of both `CountDownLatch` and `CyclicBarrier`. Parties can dynamically register/deregister, and the phase number increments automatically after each barrier:

```java
Phaser phaser = new Phaser(3);  // 3 parties initially

// Thread can arrive and wait for others:
phaser.arriveAndAwaitAdvance();   // like CyclicBarrier.await()

// Thread can arrive and deregister:
phaser.arriveAndDeregister();    // counted as arrived, then leaves the phaser

// Thread can wait for a specific phase without being a party:
phaser.awaitAdvance(phaser.getPhase());
```

`Phaser` supports tree structures for very large numbers of parties (reduces contention on the root).

---

## J7.6 — CompletableFuture

> **Builds on:** [J7.1 — Executor Framework](J7_concurrent_utilities.md#j71--executor-framework--threadpoolexecutor)
> **Connects to:** [J6.3 — volatile & Java Memory Model](J6_concurrency_fundamentals.md#j63--volatile--java-memory-model)

### WHY CompletableFuture Over Future?

`Future<T>` from Java 5 has two fundamental problems:
1. `get()` is blocking — there is no way to say "when this is done, do that" without blocking a thread to wait.
2. You cannot chain computations, combine multiple futures, or attach callbacks.

`CompletableFuture<T>` (Java 8) implements both `Future<T>` and `CompletionStage<T>`. It provides a fluent API for building pipelines of asynchronous operations without blocking threads.

### Creating CompletableFutures

```java
// Run asynchronously, return void:
CompletableFuture<Void> f1 = CompletableFuture.runAsync(() -> doWork());

// Run asynchronously, return a value:
CompletableFuture<String> f2 = CompletableFuture.supplyAsync(() -> fetchData());

// With explicit executor (STRONGLY RECOMMENDED — don't use ForkJoinPool.commonPool() for I/O):
CompletableFuture<String> f3 = CompletableFuture.supplyAsync(
    () -> fetchData(),
    myIoExecutor          // use a thread pool sized for I/O blocking
);

// Already-completed future (useful for testing):
CompletableFuture<String> done = CompletableFuture.completedFuture("result");
```

### Transforming Results (thenApply / thenAccept / thenRun)

```java
CompletableFuture<String> raw = CompletableFuture.supplyAsync(() -> "  hello  ");

// thenApply: transform T → U (like Stream.map)
CompletableFuture<String> trimmed = raw.thenApply(String::trim);

// thenAccept: consume T → void (terminal, no result)
trimmed.thenAccept(s -> System.out.println("Result: " + s));

// thenRun: run action → void (doesn't see the value)
trimmed.thenRun(() -> System.out.println("Pipeline complete"));
```

**Async variants** (`thenApplyAsync`, `thenAcceptAsync`, `thenRunAsync`): run the next stage in a different thread (from the executor or `ForkJoinPool.commonPool()`). Without `Async`, the next stage runs in the thread that completed the previous stage (or the calling thread if already done).

```java
CompletableFuture.supplyAsync(() -> fetchFromDatabase(), dbPool)   // DB thread
    .thenApplyAsync(data -> transform(data), cpuPool)              // CPU thread
    .thenAcceptAsync(result -> sendResponse(result), ioPool);      // I/O thread
```

### Chaining Async Operations (thenCompose)

`thenApply` wraps the result in another `CompletableFuture` if the function itself returns one, giving `CompletableFuture<CompletableFuture<T>>`. Use `thenCompose` (like `flatMap`) to flatten:

```java
// WRONG: produces CompletableFuture<CompletableFuture<String>>
CompletableFuture<CompletableFuture<String>> nested =
    CompletableFuture.supplyAsync(() -> "userId")
        .thenApply(id -> fetchUserAsync(id));  // fetchUserAsync returns CompletableFuture<String>

// CORRECT: thenCompose flattens to CompletableFuture<String>
CompletableFuture<String> flat =
    CompletableFuture.supplyAsync(() -> "userId")
        .thenCompose(id -> fetchUserAsync(id));
```

`thenCompose` is to `thenApply` what `flatMap` is to `map` in streams.

### Combining Multiple Futures

```java
CompletableFuture<String> user    = fetchUserAsync(userId);
CompletableFuture<List<Order>> orders = fetchOrdersAsync(userId);

// thenCombine: wait for BOTH, combine results
CompletableFuture<String> report =
    user.thenCombine(orders, (u, o) -> buildReport(u, o));

// allOf: wait for ALL futures (returns CompletableFuture<Void>)
CompletableFuture<Void> all = CompletableFuture.allOf(user, orders);
all.thenRun(() -> System.out.println("Both done"));

// anyOf: complete when ANY one completes (returns CompletableFuture<Object>)
CompletableFuture<Object> first = CompletableFuture.anyOf(mirror1, mirror2, mirror3);
```

To get results from `allOf`:

```java
List<CompletableFuture<String>> futures = List.of(f1, f2, f3);

CompletableFuture<List<String>> allResults = CompletableFuture
    .allOf(futures.toArray(new CompletableFuture[0]))
    .thenApply(v -> futures.stream()
        .map(CompletableFuture::join)   // join() is safe here — all are done
        .collect(Collectors.toList()));
```

### Exception Handling

```java
CompletableFuture<String> cf = CompletableFuture.supplyAsync(() -> {
    if (failureCondition) throw new RuntimeException("fetch failed");
    return "data";
});

// exceptionally: recover from exception (like catch)
CompletableFuture<String> recovered = cf.exceptionally(ex -> {
    log.error("Failed: " + ex.getMessage());
    return "default";  // fallback value
});

// handle: always runs (like finally), sees both result and exception
CompletableFuture<String> handled = cf.handle((result, ex) -> {
    if (ex != null) return "fallback";
    return result.toUpperCase();
});

// whenComplete: side-effect (like finally), does NOT transform the result
cf.whenComplete((result, ex) -> {
    if (ex != null) metrics.recordFailure();
    else metrics.recordSuccess();
});
```

### The Pipeline in Action

```java
CompletableFuture.supplyAsync(() -> httpClient.get("/users/" + id), ioPool)
    .thenApply(response -> parseJson(response))
    .thenCompose(user -> CompletableFuture.supplyAsync(
        () -> dbClient.query("SELECT * FROM orders WHERE user_id=?", user.id), dbPool))
    .thenApply(rows -> buildOrderList(rows))
    .exceptionally(ex -> {
        log.error("Pipeline failed", ex);
        return Collections.emptyList();
    })
    .thenAccept(orders -> sendResponse(orders));
```

This runs the HTTP call on `ioPool`, parses on the thread that completed the HTTP call, runs the DB query on `dbPool`, and sends the response — all without blocking any thread while waiting.

### Interview Trap: ForkJoinPool.commonPool() for I/O

By default, `CompletableFuture.supplyAsync(supplier)` (without an explicit executor) runs on `ForkJoinPool.commonPool()`. This pool is designed for CPU-bound work with a thread count roughly equal to `Runtime.getRuntime().availableProcessors()`. If you use it for I/O-bound tasks (HTTP calls, DB queries), those threads block on I/O, starving the pool for other work — including garbage collection and other JVM internals that use the common pool.

**Always provide an explicit executor** for any I/O-bound operation:

```java
// BAD: uses commonPool, blocks GC and other CPU work if HTTP is slow
CompletableFuture.supplyAsync(() -> httpClient.get(url));

// GOOD: uses a dedicated I/O pool with many threads (I/O is blocking, not CPU-intensive)
ExecutorService ioPool = Executors.newFixedThreadPool(100);
CompletableFuture.supplyAsync(() -> httpClient.get(url), ioPool);
```

---

## Master Summary

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    J7 — java.util.concurrent                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  1. EXECUTOR FRAMEWORK                                                      │
│     ThreadPoolExecutor(core, max, keepAlive, unit, queue, factory, handler) │
│     Dispatch: if < core → new thread; else queue; if queue full → new thread│
│     up to max; if at max → RejectedExecutionHandler.                       │
│     newFixedThreadPool → unbounded LinkedBlockingQueue (never exceeds core) │
│     newCachedThreadPool → SynchronousQueue (can spawn unlimited threads)   │
│     Always shutdown() + awaitTermination() + shutdownNow() on exit.        │
│                                                                             │
│  2. CONCURRENT COLLECTIONS                                                  │
│     ConcurrentHashMap: reads lock-free (volatile); writes lock 1 bucket.   │
│     Use atomic ops: putIfAbsent, compute, merge (NOT containsKey+put).     │
│     CopyOnWriteArrayList: writes copy entire array. Reads lock-free snap.  │
│     Use for read-heavy, write-rare lists (listener lists, configs).        │
│     BlockingQueue.put()/take() block. Use for producer-consumer pipelines. │
│     LinkedBlockingQueue has 2 locks (higher throughput) vs ArrayBlockingQueue│
│                                                                             │
│  3. REENTRANTLOCK & READWRITELOCK                                          │
│     ReentrantLock: tryLock(), lockInterruptibly(), multiple Conditions.    │
│     ALWAYS unlock in finally. Fair mode prevents starvation (costs throughput)│
│     Condition.await/signal replaces wait/notify with named wait-sets.      │
│     ReadWriteLock: concurrent reads OR exclusive write (never both).       │
│     StampedLock: optimistic read (no lock) + validate stamp — fastest but  │
│     not reentrant, no conditions.                                          │
│                                                                             │
│  4. ATOMIC VARIABLES & CAS                                                  │
│     AtomicInteger: get, set, getAndIncrement, compareAndSet — lock-free.   │
│     CAS loop: read → compute → CAS → retry if CAS fails (no blocking).    │
│     ABA problem: value A→B→A fools CAS. Fix: AtomicStampedReference.      │
│     LongAdder: striped across cells → less contention than AtomicLong.    │
│     Use AtomicLong when you need compareAndSet. LongAdder for counters.   │
│                                                                             │
│  5. SYNCHRONIZERS                                                           │
│     CountDownLatch(N): await() blocks until countDown() called N times.    │
│     One-shot (no reset). Use: wait for workers to finish / start signal.   │
│     CyclicBarrier(N): await() until all N threads arrive → release all.    │
│     Reusable. Use: phase-synchronized worker threads. Has barrier action.  │
│     Semaphore(N): at most N concurrent permits. acquire()/release().       │
│     Not ownership-based — different thread can release. Use: rate limiting.│
│                                                                             │
│  6. COMPLETABLEFUTURE                                                       │
│     supplyAsync(supplier, executor) → async pipeline without blocking.     │
│     thenApply: transform (T→U). thenCompose: flatMap (T→CF<U>).          │
│     thenCombine: merge two CFs. allOf: wait for all. anyOf: first wins.   │
│     exceptionally: recover. handle: always (result + ex). whenComplete: side│
│     TRAP: no-executor variant uses ForkJoinPool.commonPool → deadlocks on  │
│     I/O. Always provide explicit executor for blocking operations.         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

*← [Phase J6 — Concurrency Fundamentals](J6_concurrency_fundamentals.md) | [Phase J8 — Garbage Collection & JVM Tuning →](J8_gc_and_jvm_tuning.md)*
