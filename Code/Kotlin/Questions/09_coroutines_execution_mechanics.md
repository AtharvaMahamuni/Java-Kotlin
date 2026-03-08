# Phase 9: Coroutines — Execution Mechanics

## Navigation
[← Phase 8 — Other Kotlin Features](08_other_kotlin_features.md) | [→ Phase 10 — Structured Concurrency](10_structured_concurrency.md)

## Questions in This File
- [Q9.1 — What `suspend` Actually Does](#q91--what-suspend-actually-does)
- [Q9.2 — Coroutine Context and Dispatchers](#q92--coroutine-context-and-dispatchers)
- [Q9.3 — `launch` vs `async`](#q93--launch-vs-async)
- [Q9.4 — Coroutine Start Modes](#q94--coroutine-start-modes)

---

## Q9.1 — What `suspend` Actually Does

> **Builds on:** [Q0.1 — Stack vs Heap](phase0_jvm_mental_model_v3.md#q01--primitives-vs-references) · [Q0.4 — JVM Call Stack](phase0_jvm_mental_model_v3.md#q04--the-jvm-call-stack)
> **Connects to:** [Q9.2 — Dispatchers](#q92--coroutine-context-and-dispatchers) · [Q10.1 — Job Hierarchy](10_structured_concurrency.md#q101--the-job-hierarchy) · [Q10.3 — Exception Handling](10_structured_concurrency.md#q103--exception-handling-rules)

---

### The Concrete Picture

You write two lines. The compiler writes a state machine:

```kotlin
suspend fun loadData(): String {
    val user = fetchUser()      // suspension point 1
    val data = fetchData(user)  // suspension point 2
    return data
}
```

What the JVM actually executes:

```
First call: label=0 → calls fetchUser → returns COROUTINE_SUSPENDED
  Thread is freed. Other coroutines run.

fetchUser completes → resumes loadData at label=1
  label=1 → calls fetchData → returns COROUTINE_SUSPENDED
  Thread freed again.

fetchData completes → resumes loadData at label=2
  label=2 → calls completion.resume(data)
  Caller receives the result.
```

The state machine remembers WHERE to resume (`label`) and the local variable values (fields on a heap object).

---

### CPS Transformation — Two Things the Compiler Adds

Every `suspend` function undergoes **Continuation Passing Style (CPS)** transformation. The compiler adds:

1. **A `Continuation<T>` parameter** appended to the function signature
2. **A state machine** using a `label` field to remember which suspension point to resume at

```kotlin
// What you write:
suspend fun loadData(): String

// What the compiler generates at the JVM level:
fun loadData(continuation: Continuation<String>): Any
//                         ^^^^^^^^^^^^^^^^^^^^         ^
//                         extra parameter              return type: Any
//                         the "callback"               (String OR COROUTINE_SUSPENDED)
```

**Why `Any` return type?**
The function can return in two ways:
- Immediately with a `String` value (fast path — no actual suspension needed)
- The `COROUTINE_SUSPENDED` sentinel object (signals "I suspended, I'll call you back")

These are different types at the Kotlin level. Only `Any` covers both. At the call site, the caller checks: did I get back `COROUTINE_SUSPENDED`? If yes, wait for the callback. If no, use the returned value directly.

---

### Bytecode Reality — What the JVM Sees

The CPS transformation is visible at the bytecode level. The `Continuation<T>` parameter becomes a real JVM parameter, and `COROUTINE_SUSPENDED` is a concrete singleton object from the coroutines runtime.

**Decompiled Java equivalent of `suspend fun loadData(): String`:**

```java
// Before transformation (your Kotlin):
// suspend fun loadData(): String

// After CPS transformation (JVM bytecode, viewed as decompiled Java):
@Nullable
public static final Object loadData(@NotNull Continuation<? super String> $completion) {
    // The state machine object — cast-or-create pattern
    LoadDataContinuation $continuation;
    if ($completion instanceof LoadDataContinuation &&
        ((LoadDataContinuation)$completion).label < 0) {
        $continuation = (LoadDataContinuation) $completion;
        $continuation.label -= Integer.MIN_VALUE;  // un-mark
    } else {
        $continuation = new LoadDataContinuation($completion);  // first call
    }

    Object $result = $continuation.result;
    Object var3 = IntrinsicsKt.getCOROUTINE_SUSPENDED();  // the sentinel

    switch ($continuation.label) {
        case 0: {
            ResultKt.throwOnFailure($result);
            $continuation.label = 1;
            Object r = fetchUser($continuation);        // pass sm as callback
            if (r == var3) return var3;                 // suspended → return sentinel
            $continuation.user = (User) r;
            // fall through — fast path
        }
        case 1: {
            ResultKt.throwOnFailure($result);
            $continuation.user = (User) $result;
            $continuation.label = 2;
            Object r = fetchData($continuation.user, $continuation);
            if (r == var3) return var3;
            $continuation.data = (String) r;
        }
        case 2: {
            ResultKt.throwOnFailure($result);
            $continuation.data = (String) $result;
        }
    }
    return $continuation.data;
}

// The generated state machine class:
static final class LoadDataContinuation extends ContinuationImpl {
    int label;           // resume point index
    Object result;       // result of the last resumed call
    User user;           // local var promoted to field (lives across suspension)
    String data;         // local var promoted to field

    LoadDataContinuation(Continuation<? super String> completion) {
        super(completion);
    }

    @Override
    public final Object invokeSuspend(@NotNull Object result) {
        this.result = result;
        this.label |= Integer.MIN_VALUE;  // mark as resuming
        return loadData(this);            // re-enter the state machine
    }
}
```

**Key bytecode observations:**
- `COROUTINE_SUSPENDED` = `IntrinsicsKt.getCOROUTINE_SUSPENDED()` — a real singleton object on the heap
- `invokeSuspend` is the re-entry point called by the scheduler when async work completes
- `label |= Integer.MIN_VALUE` is the trick to distinguish a first call from a resume: the `instanceof` check at the top looks for this marking
- The `switch` statement is the state machine — each `case` is a resume point

---

### State Machine Deep Dive — `label` Field

The `label` field is an `Int` on the `Continuation` object. It is the **resume point index** — which `switch` case to jump to when the function is resumed.

**State transition diagram:**

```
Entry ──► label=0
            │  calls fetchUser(sm)
            │
            ▼
     ┌── == COROUTINE_SUSPENDED? ──┐
     │ YES                          │ NO (fast path — already cached)
     ▼                              ▼
 Thread yields                 sm.user = result → fall through to label=1
 [async work runs on other thread]
 fetchUser calls sm.invokeSuspend(result)
            │
            ▼
     label=1 ◄── resume here
            │  calls fetchData(sm.user, sm)
            │
            ▼
     ┌── == COROUTINE_SUSPENDED? ──┐
     │ YES                          │ NO
     ▼                              ▼
 Thread yields                 sm.data = result → fall through
 fetchData calls sm.invokeSuspend(result)
            │
            ▼
     label=2 ◄── resume here
            │  return sm.data  →  completion.resume(data) called by caller
            ▼
           DONE
```

**Key invariant:** `label` is set BEFORE the suspend call. This guarantees that if the function is immediately resumed (before it even returns `COROUTINE_SUSPENDED` — the fast path), it resumes at the correct label.

---

### One State Machine Per Call Site, Reused Across Resumes

A question interviewers love to follow up with: *"Does every suspend call create a new state machine object, or is it reused?"*

**One object per coroutine invocation, reused across all resumes:**

```
First call to loadData(completion):
  → `completion instanceof LoadDataContinuation?` → NO
  → creates new LoadDataContinuation object on heap
  → returns COROUTINE_SUSPENDED (object stays alive via reference in scheduler)

fetchUser completes → calls sm.invokeSuspend(result)
  → `completion instanceof LoadDataContinuation?` → YES (it's the SAME object)
  → reuses existing object, label=1 now
  → no new allocation

fetchData completes → calls sm.invokeSuspend(result)
  → SAME object again, label=2
  → returns result → object becomes eligible for GC
```

**Why this matters:** Each coroutine invocation allocates exactly ONE `ContinuationImpl` object. All resumes reuse it. The cost is one heap allocation per suspend function call, not one per suspension point. This is far cheaper than creating a new thread (which costs ~1MB of stack space).

---

### Where Local Variables Live — Stack vs Heap

In a normal JVM method, local variables live in the **stack frame** — they disappear when the method returns.

A `suspend` function must "pause" and "resume" — potentially on a different thread. If locals were on the stack, they'd be gone when the thread moved on. The compiler solves this by **promoting only the locals that live across a suspension point to fields on the `Continuation` object** (heap-allocated):

```
Normal function (stack frame — ephemeral, gone on return):
  [ user: User  ] ← local variable slot 1
  [ data: String] ← local variable slot 2

Suspend function (LoadDataContinuation on heap — lives until coroutine completes):
  [ label: Int  ] ← resume point index
  [ user: User  ] ← PROMOTED: survives suspension at label=1 until label=2
  [ data: String] ← PROMOTED: survives suspension at label=2 until return
  [ completion  ] ← the caller's continuation to notify
  [ result      ] ← last resumed value, checked via throwOnFailure
```

Variables NOT live across a suspension point stay on the stack (no promotion). The compiler performs liveness analysis to minimize heap allocations.

---

### `COROUTINE_SUSPENDED` — The Callback Model

`COROUTINE_SUSPENDED` is a singleton (`IntrinsicsKt.getCOROUTINE_SUSPENDED()`). When a `suspend` function suspends, it:
1. Registers its `Continuation` (the state machine) as a callback with the async operation
2. Returns `COROUTINE_SUSPENDED` to signal "don't wait for me — I'll call back via `invokeSuspend`"

The thread is immediately freed. Other coroutines run on it. When async work completes, it calls `continuation.resumeWith(result)` → `invokeSuspend` is called → the state machine re-enters at the correct label.

This is exactly the Callback pattern — the compiler writes the callbacks for you.

```
suspend fun → returns COROUTINE_SUSPENDED
    │
    ▼
Thread freed → dispatcher runs other coroutines on this thread
    │
    ▼
async work completes → continuation.resumeWith(result)
    │                  → calls continuation.invokeSuspend(result)
    ▼
state machine re-enters at correct label on dispatcher thread
```

---

### `delay()` vs `Thread.sleep()` — Why They Behave Differently

**`Thread.sleep(1000)` — blocks the OS thread:**

```kotlin
// WRONG: blocks the thread for 1 second
suspend fun bad(): String {
    Thread.sleep(1000)  // OS call: parks this thread for 1000ms
    return fetchData()  // no other coroutines ran during sleep
}
```

`Thread.sleep` makes an OS syscall. The OS parks the thread in a wait queue. The thread cannot run anything else. One blocked thread = one wasted OS resource (typically ~1MB stack).

**`delay(1000)` — suspends the coroutine, not the thread:**

```kotlin
// CORRECT: frees the thread for 1 second
suspend fun good(): String {
    delay(1000)    // returns COROUTINE_SUSPENDED + registers timed callback
    return fetchData()
}
```

`delay` is a `suspend` function. Internally it calls `suspendCancellableCoroutine` which returns `COROUTINE_SUSPENDED` immediately and registers a callback via `scheduleResumeAfterDelay`. On Android this is `Handler.postDelayed`. After 1000ms, the scheduler calls `continuation.resume(Unit)` → the coroutine resumes.

```
Thread.sleep(1000) on Dispatchers.Main:
  Main thread → BLOCKED for 1 second → UI can't process events → ANR risk

delay(1000) on Dispatchers.Main:
  Main thread → coroutine suspended → thread free → processes other UI events
  → after 1000ms → coroutine resumes → continues normally
```

---

### How Exceptions Propagate Through Suspensions

`try-catch` works correctly across suspension points because of `ResultKt.throwOnFailure`:

```kotlin
suspend fun loadData(): String {
    return try {
        val user = fetchUser()   // if fetchUser fails...
        fetchData(user)
    } catch (e: IOException) {
        "fallback"
    }
}
```

When `fetchUser()` fails, it calls `sm.resumeWith(Result.failure(IOException(...)))`. The state machine re-enters at `label=1`, and the first line executed is:

```java
// Decompiled — first thing in every case block:
ResultKt.throwOnFailure($result);
// If $result = Result.failure(e) → throws e at this exact position
// The throw is INSIDE the try block → caught by catch(IOException)
```

`throwOnFailure` re-throws the exception at the position in the state machine corresponding to the original suspension point. This preserves try-catch semantics exactly as if the code ran synchronously — the throw appears to come from the `fetchUser()` call site, inside the `try` block.

---

### Why `suspend` Says Nothing About Which Thread

`suspend` is purely a compile-time annotation about calling convention. It means:
- This function can suspend execution
- It participates in CPS transformation
- It carries an implicit `Continuation<T>` parameter

It says **nothing** about threads. Thread assignment is determined entirely by the **Dispatcher** in the coroutine context:

```kotlin
withContext(Dispatchers.Main) { val user = fetchUser() }   // Main thread
withContext(Dispatchers.IO)   { val user = fetchUser() }   // IO thread pool
// Same fetchUser, same bytecode, different thread — only the Dispatcher changed
```

```
suspend keyword → "this function can pause" (compile-time annotation)
Dispatcher      → "on which thread it runs"  (runtime context value)
These are orthogonal. suspend ≠ "runs on background thread".
```

---

### Memory Trick

```
SUSPEND = compiler transforms function body into STATE MACHINE (one object per invocation, reused).
  label (Int field) = resume point index → which switch-case to jump to
  Local vars ACROSS suspension point → promoted to FIELDS on Continuation (heap)
  Vars NOT crossing suspension point → stay on stack (compiler liveness analysis)

CPS adds:
  1. Continuation<T> param at end of JVM signature
  2. Return type → Any (value OR IntrinsicsKt.getCOROUTINE_SUSPENDED() sentinel)
  3. State machine: switch(label) + invokeSuspend() re-entry

ONE OBJECT PER INVOCATION. Not one per suspension point. Reused on every resume.

COROUTINE_SUSPENDED = "call invokeSuspend when done, don't wait"
  Thread freed immediately. invokeSuspend called on completion.

delay() vs Thread.sleep():
  sleep → OS syscall: parks the OS thread. Thread does NOTHING for N ms.
  delay → suspendCancellableCoroutine + scheduleResumeAfterDelay callback.
          Thread freed. Resumes via Handler.postDelayed (Android).
  sleep on Main → thread blocked → UI frozen → ANR. delay → fine.

SUSPEND ≠ THREAD: suspend = can pause (compile-time). Dispatcher = thread (runtime).
```

### Key Takeaways — Q9.1

| Concept | Fact |
|---|---|
| CPS transformation | Adds `Continuation<T>` param + switch-based state machine |
| Return type change | `String` → `Any` (covers value AND `COROUTINE_SUSPENDED` sentinel) |
| `COROUTINE_SUSPENDED` | `IntrinsicsKt.getCOROUTINE_SUSPENDED()` singleton — frees thread |
| State machine allocation | ONE object per call, reused on every resume via `invokeSuspend` |
| Local variables | Across suspension point → heap fields; otherwise stack |
| `delay()` vs `Thread.sleep()` | `delay` suspends coroutine (thread freed); `sleep` blocks OS thread |
| `suspend` and threads | Orthogonal — thread determined by `Dispatcher` only |

### Self-Test

1. What two things does the compiler add to every `suspend` function?
2. Why does `suspend fun foo(): String` become `fun foo(continuation: Continuation<String>): Any` at the JVM level? Why `Any`?
3. *"Does creating a suspend function call allocate an object on each suspension point, or once per invocation?"* — What is the answer, and why?
4. Where are local variables stored in a suspend function? What determines whether a variable is promoted to the heap?
5. What is `COROUTINE_SUSPENDED` at the JVM level? What does returning it signal?
6. `Thread.sleep(1000)` vs `delay(1000)` inside a coroutine on `Dispatchers.Main` — what is the mechanical difference?
7. Does `suspend` say anything about which thread the function runs on? Prove it.

---

## Q9.2 — Coroutine Context and Dispatchers

> **Builds on:** [Q9.1 — CPS and suspend](#q91--what-suspend-actually-does)
> **Connects to:** [Q9.4 — Start Modes](#q94--coroutine-start-modes) · [Q10.4 — viewModelScope](10_structured_concurrency.md#q104--lifecycle-scopes-and-process-death) · [Q10.6 — Mutex](10_structured_concurrency.md#q106--mutex-and-synchronization-primitives)

---

### `CoroutineContext` — A Typed Map

`CoroutineContext` is an **immutable, typed map** from keys to elements. Each element has a companion `Key`. Only one element per key can exist.

```
CoroutineContext (typed map):
  Job.Key              → Job      (lifecycle: active/cancelling/cancelled/completed)
  ContinuationInterceptor.Key → Dispatcher  (thread scheduling — Dispatcher IS a ContinuationInterceptor)
  CoroutineName.Key    → CoroutineName("MyCoroutine")   (optional, debugging)
  ExceptionHandler.Key → CoroutineExceptionHandler       (optional, last-resort handler)
```

**Why is `Dispatcher` a `ContinuationInterceptor`?**
After each suspension, `invokeSuspend` must be called on the right thread. The `Dispatcher` intercepts the resumption and routes it to the correct thread: `interceptContinuation(continuation)` wraps the raw continuation in a `DispatchedContinuation` that posts to the right thread before calling `invokeSuspend`.

**The `+` operator — right-biased merge:**

```kotlin
val ctx = Dispatchers.IO + CoroutineName("Fetcher") + Dispatchers.Main
// Dispatcher slot = Main (Main replaced IO — right side wins same-key conflict)
// Name slot = "Fetcher"
```

`+` is not set union. It is a `put` operation: for each element in the right operand, it replaces any existing element with the same key in the left operand.

```kotlin
// Practical consequence — right side always wins on conflict:
val a = Dispatchers.IO + CoroutineExceptionHandler { _, _ -> }
val b = Dispatchers.Default

val merged = a + b
// merged has: Dispatchers.Default (replaced IO), CoroutineExceptionHandler (kept)
```

**Decompiled Java — what `+` compiles to:**

```java
// ctx1 + ctx2 compiles to:
CoroutineContext merged = ctx1.plus(ctx2);
// which calls ctx2.fold(ctx1, (acc, element) -> acc.minusKey(element.getKey()).plus(element))
// = for each element in ctx2: remove same key from acc, then add element
```

---

### `Dispatchers.Default` vs `Dispatchers.IO` — Why They Share a Pool

**The mechanism — `CoroutineScheduler`:**

Both `Dispatchers.Default` and `Dispatchers.IO` are backed by the same `CoroutineScheduler` instance — a work-stealing thread pool. This is deliberate: JVM thread creation is expensive (~1MB stack allocation, OS-level context switching). Sharing the pool means switching from Default to IO may not allocate a new thread at all.

```
CoroutineScheduler (shared pool):
  Worker-1  Worker-2  Worker-3  ...  Worker-64

  Dispatchers.Default: CORE_POOL_SIZE = max(2, CPU cores)
    Tasks marked as NON_BLOCKING — workers prefer these
    When 8 Default tasks run on 8-core machine: all workers busy → no benefit adding more

  Dispatchers.IO:     MAX_POOL_SIZE  = max(64, systemProperty)
    Tasks marked as BLOCKING — workers can create additional threads if all busy
    Rationale: IO tasks mostly WAIT (network, disk) — more threads = more parallelism
```

```
Default → IO context switch:
  SAME CoroutineScheduler → may use the same physical worker thread
  Only the task label changes (NON_BLOCKING → BLOCKING)
  No OS thread switch needed if a worker is available

Main → IO context switch:
  Completely different thread — Main is a single Looper thread, not from the pool
  ALWAYS changes physical thread
```

**`withContext` switching cost:**

```kotlin
// Cheapest switch (no OS thread change possible):
withContext(Dispatchers.IO) { ... }      // from Default: same pool, possibly same thread
withContext(Dispatchers.Default) { ... } // from IO: same pool, possibly same thread

// Always expensive (crosses pool boundary):
withContext(Dispatchers.Main) { ... }    // from any background: Handler.post() required
```

---

### `Dispatchers.Main` vs `Dispatchers.Main.immediate`

`Dispatchers.Main` always posts work to the main thread's `Handler` queue — even if you are already on the main thread. This introduces a queue round-trip (enqueue → process → execute).

`Dispatchers.Main.immediate` checks: am I already on the main thread? If YES → run synchronously inline, no queue. If NO → post to `Handler`.

```kotlin
// Already on Main thread:
withContext(Dispatchers.Main) {
    updateUI()  // posted to Handler queue → waits for queue turn (latency added)
}

withContext(Dispatchers.Main.immediate) {
    updateUI()  // if already on Main: runs RIGHT NOW inline — zero queue overhead
}
```

**Why `viewModelScope` uses `Main.immediate`:**

ViewModel state updates typically happen from already-on-Main code (e.g., user interaction callback). With `Main`, each state update incurs a `Handler.post()` round-trip. With `Main.immediate`, if the update triggers from Main, it runs inline — the `StateFlow` value is updated synchronously, the collector receives it in the same frame.

---

### ## Trap: `Dispatchers.IO` Does NOT Mean "New Thread Per Coroutine"

```kotlin
// WRONG mental model:
repeat(100) {
    launch(Dispatchers.IO) { doWork() }
}
// WRONG assumption: "100 different IO threads created"

// REALITY:
// max 64 threads in IO pool (default)
// → at most 64 run simultaneously
// → remaining 36 queue behind those 64
// → physical threads: ≤ 64, likely far fewer
```

`Dispatchers.IO` limits to 64 concurrent threads, not unlimited threads. This prevents thread exhaustion but can still be too many for limited resources (e.g., database connections). Use `limitedParallelism` to constrain further.

---

### `limitedParallelism(N)` — Restricting IO Concurrency

```kotlin
// Wrong: 64 coroutines may all hit the database simultaneously
withContext(Dispatchers.IO) { readDatabase() }

// Correct: at most 4 database coroutines at once
val dbDispatcher = Dispatchers.IO.limitedParallelism(4)
withContext(dbDispatcher) { readDatabase() }
```

`limitedParallelism(N)` creates a **view** of the dispatcher — it does not create a new thread pool. The physical threads still come from the shared IO pool. It enforces that at most `N` coroutines are executing concurrently through this view; extras queue.

```
Dispatchers.IO (max 64)
  ├── dbDispatcher = limitedParallelism(4)   → at most 4 DB calls at once
  └── cacheDispatcher = limitedParallelism(2) → at most 2 cache ops at once
  (threads still from same shared pool — no duplication)
```

`limitedParallelism(1)` = serial execution through this view. Different from `newSingleThreadContext`: `limitedParallelism(1)` reuses pool threads (different thread each time, but never concurrent); `newSingleThreadContext` creates a dedicated OS thread (use sparingly, always `close()` it).

| | Thread origin | Concurrent tasks | Thread identity |
|---|---|---|---|
| `Dispatchers.IO` | Shared pool | 64 | Any worker |
| `.limitedParallelism(4)` | Same shared pool | 4 | Any worker (different each time) |
| `.limitedParallelism(1)` | Same shared pool | 1 (serial) | Any worker (different each time) |
| `newSingleThreadContext` | Dedicated OS thread | 1 (serial) | Always same thread |

---

### Memory Trick

```
CoroutineContext = TYPED MAP. Key per element type. + = right-biased put.
  Dispatcher IS a ContinuationInterceptor — wraps each resumption to route to correct thread.

DEFAULT + IO = same CoroutineScheduler pool:
  Default: max = CPU cores, NON_BLOCKING tasks.
  IO: max = 64, BLOCKING tasks — can expand pool for waiting threads.
  Default→IO: same pool, may not change physical thread.
  Main→IO: ALWAYS changes thread (Main is its own Looper, not in pool).

Main vs Main.immediate:
  Main         = always posts to Handler (latency even when already on Main)
  Main.immediate = inline if already on Main (viewModelScope uses this for zero-latency)

limitedParallelism(N): view of dispatcher, NOT new pool. Max N concurrent.
  limitedParallelism(1) = serial queue (thread may differ each time, unlike newSingleThreadContext)
```

### Key Takeaways — Q9.2

| Concept | Fact |
|---|---|
| `CoroutineContext` | Typed map; `+` is right-biased merge (`put`) per key |
| `Dispatcher` is | A `ContinuationInterceptor` — routes resumptions to correct thread |
| `Default` + `IO` | Same `CoroutineScheduler` pool; Default = CPU cores, IO = 64 |
| `Default` → `IO` switch | May not change physical thread (same pool) |
| `Main.immediate` | Inline if on Main already; `viewModelScope` uses this |
| `limitedParallelism(N)` | View of dispatcher; max N concurrent; same underlying threads |
| `limitedParallelism(1)` vs `newSingleThreadContext` | Former: serial, any pool thread; latter: dedicated OS thread |

### Self-Test

1. `CoroutineContext` — what kind of data structure is it? If you `+` two contexts each containing a `Dispatcher`, what is the result?
2. `Dispatchers.Default` and `Dispatchers.IO` — do they share threads? What would you observe if you switched between them rapidly?
3. Why is `Dispatcher` implemented as a `ContinuationInterceptor`? What does it intercept?
4. Why does `viewModelScope` use `Dispatchers.Main.immediate` instead of `Dispatchers.Main`? What is the concrete difference?
5. `Dispatchers.IO.limitedParallelism(1)` vs `newSingleThreadContext("DB")` — when would you choose each?

---

## Q9.3 — `launch` vs `async`

> **Builds on:** [Q9.1 — suspend mechanics](#q91--what-suspend-actually-does) · [Q9.2 — context](#q92--coroutine-context-and-dispatchers)
> **Connects to:** [Q10.1 — Job Hierarchy](10_structured_concurrency.md#q101--the-job-hierarchy) · [Q10.2 — coroutineScope vs supervisorScope](10_structured_concurrency.md#q102--coroutinescope-vs-supervisorscope) · [Q10.3 — Exception handling](10_structured_concurrency.md#q103--exception-handling-rules)

---

### The Core Difference

```
launch { } → returns Job          (fire and forget — no result, cannot get value back)
async  { } → returns Deferred<T>  (call await() to suspend until result is ready)

Deferred<T> extends Job → has cancel(), join(), isActive PLUS:
  .await()          → suspend until complete, return value (re-throws on failure)
  .getCompleted()   → returns value immediately — throws IllegalStateException if not done
  .getCompletionExceptionOrNull() → returns exception if failed, null otherwise
```

---

### ## Trap: `async` Does NOT Contain Exceptions Until `await()`

The most common misconception about `async`. Exception propagation depends on the **scope**, not on whether `await()` has been called.

```kotlin
// WRONG mental model: "async isolates the exception until await()"
coroutineScope {
    val deferred = async {
        throw RuntimeException("failure")  // ← propagates to coroutineScope IMMEDIATELY
    }
    delay(100)         // coroutineScope is ALREADY cancelling at this point
    deferred.await()   // throws — but scope may already be dead
}
// coroutineScope itself throws RuntimeException
```

**Why:** The `async` block's `Job` is a child of the `coroutineScope`'s `Job`. When the child fails with a non-`CancellationException`, it calls `parent.childCancelled(cause)` → `coroutineScope` returns `false` (not handled) → parent cancels itself → cancels all siblings → propagates up.

**Only `supervisorScope` truly contains until `await()`:**

```kotlin
supervisorScope {
    val deferred = async { throw RuntimeException("isolated") }
    delay(100)         // supervisorScope NOT cancelled — SupervisorJob absorbed it
    try {
        deferred.await()   // throws HERE and ONLY here
    } catch (e: RuntimeException) {
        println("caught: ${e.message}")  // "caught: isolated"
    }
}
// supervisorScope returns normally
```

```
Scope type → where does async exception propagate?
  coroutineScope  → immediately to parent (scope cancels, siblings cancelled)
  supervisorScope → contained, only re-thrown at await()
```

---

### ## Trap: `try-catch` Around `launch` Never Works

`launch` schedules the coroutine and returns a `Job` **immediately** — before the body executes. The `try-catch` wraps the scheduling call, not the coroutine body.

```kotlin
// WRONG: try-catch is on the wrong call stack
try {
    launch {
        throw RuntimeException("inside coroutine")  // runs LATER, different call stack
    }
    // launch() returns Job here — no exception thrown at this point
} catch (e: RuntimeException) {
    // NEVER fires
}
```

**Why it fails:** The exception does not travel via JVM exception propagation. It travels through `continuation.resumeWith(Result.failure(e))` → `childCancelled(e)` on parent → the coroutine hierarchy. These are different call stacks.

**What works:**

```kotlin
// Option 1: try-catch INSIDE the launch (same call stack as the throw)
launch {
    try { riskyOp() } catch (e: IOException) { handle(e) }
}

// Option 2: CoroutineExceptionHandler (root coroutines only — see Q10.3)
val handler = CoroutineExceptionHandler { _, e -> log(e) }
scope.launch(handler) { throw RuntimeException("root") }

// Option 3: async + await + try-catch
val result = runCatching { async { riskyOp() }.await() }
// Note: check for CancellationException — see Q10.3
```

---

### ## Trap: `awaitAll()` vs Sequential `await()` — Leaked Coroutine

**Sequential `await()` — the common leak:**

```kotlin
val a = async { compute1() }  // starts immediately
val b = async { compute2() }  // starts immediately

// TRAP: sequential await
val result = a.await() + b.await()
// If a fails → a.await() throws → b.await() is NEVER called
// b keeps running, result is never used, b is an orphaned coroutine
// (It will eventually complete, but its result goes unobserved — resource waste)
```

**`awaitAll()` — the correct parallel pattern:**

```kotlin
val a = async { compute1() }
val b = async { compute2() }

val (r1, r2) = awaitAll(a, b)
// Awaits BOTH — if either fails, awaitAll cancels ALL provided Deferreds immediately
// No orphaned coroutines, no resource waste
```

`awaitAll` propagates the first exception AND cancels all other provided deferreds. Sequential `await()` only throws on the first failure it hits — subsequent deferreds run unobserved.

```kotlin
// Idiomatic parallel decomposition:
coroutineScope {
    val (user, config, ads) = awaitAll(
        async { fetchUser() },
        async { fetchConfig() },
        async { fetchAds() }
    )
    // If any fail: scope cancels all, coroutineScope throws
    // If all succeed: results available as destructured list in declaration order
}
```

---

### ## Trap: Lazy `async` Sequential Execution

`async(start = CoroutineStart.LAZY)` does NOT start until `await()` or `start()` is called.

```kotlin
// WRONG: appears parallel but is actually sequential
val a = async(start = LAZY) { compute1() }  // not started
val b = async(start = LAZY) { compute2() }  // not started

a.await()  // starts a, suspends until done (3s)
b.await()  // THEN starts b, suspends until done (3s)
// Total: 6 seconds — sequential!

// CORRECT: explicitly start both before awaiting
a.start(); b.start()  // both start simultaneously now
awaitAll(a, b)         // total: max(3s, 3s) = 3s — parallel!
```

---

### Memory Trick

```
launch = Job (fire and forget). async = Deferred<T> (await() for result).
Deferred extends Job → has all Job ops plus await().

ASYNC EXCEPTION SCOPE RULES:
  coroutineScope  → async failure propagates to parent IMMEDIATELY (not at await())
  supervisorScope → truly contained, only at await()
  Common mistake: "async always holds until await" → WRONG for coroutineScope

TRY-CATCH AROUND launch = NEVER WORKS.
  launch() returns Job immediately.
  Exception travels via childCancelled chain, NOT JVM exception propagation.
  Fix: try-catch INSIDE launch, or CoroutineExceptionHandler (root only).

awaitAll(a, b) vs a.await() + b.await():
  Sequential: first failure → throws → second never awaited → ORPHANED coroutine
  awaitAll:   first failure → cancels ALL → no orphans
  ALWAYS use awaitAll for parallel operations with multiple Deferreds.

LAZY ASYNC:
  async(LAZY) starts ONLY on await() or start().
  Calling await() directly = sequential (start a, wait, then start b, wait).
  Fix: a.start(); b.start() BEFORE any await().
```

### Key Takeaways — Q9.3

| Concept | Fact |
|---|---|
| `async` in `coroutineScope` | Exception propagates to parent IMMEDIATELY — not only at `await()` |
| `async` in `supervisorScope` | Exception truly contained until `await()` |
| `try-catch` around `launch` | Never works — exception on a different call stack |
| `awaitAll(a, b)` | Cancels all on first failure — no orphaned coroutines |
| Sequential `await()` | First failure → second never awaited → orphaned coroutine |
| `async(LAZY)` trap | Sequential unless `.start()` called on all before any `.await()` |

### Self-Test

1. `async { throw Exception() }` in a `coroutineScope` — when does the scope cancel? Why does the scope type matter?
2. Why does `try-catch { launch { } }` never catch the exception? What mechanism carries the exception instead?
3. `a.await() + b.await()` vs `awaitAll(a, b)` — what exactly happens when `a` fails in each case?
4. Write the idiomatic parallel pattern for fetching user, config, and ads simultaneously using `awaitAll`, handling any failure as a total failure.
5. `async(start = LAZY)` — when does it actually start? Show the wrong (sequential) code and the fix that makes it parallel.

---

## Q9.4 — Coroutine Start Modes

> **Builds on:** [Q9.3 — launch vs async](#q93--launch-vs-async) · [Q9.2 — Dispatchers](#q92--coroutine-context-and-dispatchers)
> **Connects to:** [Q10.3 — CancellationException](10_structured_concurrency.md#q103--exception-handling-rules) · [Q11.4 — Flow collection and lifecycle](11_flow.md#q114--flow-collection-and-lifecycle)

---

### The Four Modes — One Sentence Each

```
DEFAULT:       Scheduled immediately on dispatcher. Cancellable before it starts running.
LAZY:          Nothing happens until start() or await() is called.
ATOMIC:        Scheduled immediately. CANNOT be cancelled before first suspension point.
UNDISPATCHED:  Runs synchronously on the CURRENT thread until the first suspension point.
               After first suspension: resumes on the coroutine's dispatcher thread.
```

---

### `DEFAULT` — Standard Scheduling

```kotlin
val job = launch(start = CoroutineStart.DEFAULT) {
    println("Running")
}
job.cancel()  // if called fast enough, "Running" never prints
// Cancel window: from launch() returning to the coroutine body actually executing
// In practice: microseconds on a real device — but real and observable in tests
```

Internally, `DEFAULT` calls `dispatcher.dispatch(context, block)` which enqueues the block on the dispatcher's work queue. Between enqueue and dequeue, the coroutine can be cancelled.

---

### `LAZY` — On-Demand

```kotlin
val job = launch(start = CoroutineStart.LAZY) {
    println("Only runs when started")
}
// Nothing queued yet — state = New

job.start()    // transitions to Active → enqueued on dispatcher
// or:
job.join()     // start() + suspend until completion
```

`LAZY` creates the coroutine in the `New` state. No work is enqueued until `start()`, `join()`, or `await()` transitions it to `Active`.

Beware the sequential trap with `async(LAZY)` — see Q9.3.

---

### `ATOMIC` — Guaranteed-to-Start

```kotlin
// PROBLEM this solves: cancel() called immediately after launch() in DEFAULT mode
launch(start = CoroutineStart.DEFAULT) {
    acquireResource()  // might NEVER run if cancelled before it starts
    delay(100)
    releaseResource()  // if acquireResource ran, this MUST run → resource leak risk
}

// FIX with ATOMIC:
launch(start = CoroutineStart.ATOMIC) {
    acquireResource()  // GUARANTEED to run — no cancel window
    delay(100)         // ← first suspension point → normal cancellation applies from here
    releaseResource()  // may or may not run depending on cancellation
}
job.cancel()
// acquireResource() WILL execute even if cancel() was called first
```

`ATOMIC` bypasses the cancellation check that `DEFAULT` performs before entering the coroutine body. The coroutine runs at least until its first suspension point, at which point normal cooperative cancellation resumes.

---

### `UNDISPATCHED` — Synchronous Until First Suspension

```kotlin
// Dispatcher = IO, but calling thread = Main
launch(Dispatchers.IO, start = CoroutineStart.UNDISPATCHED) {
    println(Thread.currentThread().name)  // "main" ← no dispatch, runs here NOW

    delay(100)   // ← FIRST SUSPENSION POINT: returns COROUTINE_SUSPENDED

    println(Thread.currentThread().name)  // "DefaultDispatcher-worker-N" ← IO thread
}
// The line AFTER launch() executes AFTER delay() is reached (not after the whole coroutine)
```

**Why this is useful — the SharedFlow registration race:**

```kotlin
val sharedFlow = MutableSharedFlow<Int>()

// WRONG — DEFAULT mode: race condition
launch { sharedFlow.collect { println(it) } }
// ↑ scheduled, NOT yet running — collector not registered yet
sharedFlow.emit(1)   // emitted BEFORE collector registered → MISSED

// CORRECT — UNDISPATCHED: no race
launch(start = UNDISPATCHED) {
    sharedFlow.collect { println(it) }
    // ↑ collect() is a suspend call = first suspension point
    // UNDISPATCHED runs synchronously until here → collector IS registered
}
sharedFlow.emit(1)   // collector already registered → received ✓
```

`UNDISPATCHED` ensures the coroutine reaches its first suspension (the `collect` call, which registers the subscription) before the calling code continues — eliminating the registration race.

**Important:** `UNDISPATCHED` does NOT mean "entire coroutine on current thread." Only BEFORE the first suspension. After first suspension → the coroutine's configured `Dispatcher` takes over.

---

### Start Mode Comparison

```
Time ──────────────────────────────────────────────────────────────►

DEFAULT:
  launch() ──► [enqueued] ──────────────────► [body executes on dispatcher thread]
               └─ cancel window ─┘
               (can cancel here before body starts)

LAZY:
  launch() ──► [New state, nothing enqueued] ─────────────────────────────────────
                                              start()/await() ──► [enqueued] ──► [runs]

ATOMIC:
  launch() ──► [enqueued] ──► [body runs: NO cancel possible] ──► [1st suspend] ──► ...
                               ◄──── guaranteed execution ────►     (normal cancel from here)

UNDISPATCHED:
  launch() ──► [runs NOW on calling thread, synchronously] ──► [1st suspend] ──► [dispatcher]
               ◄──── no dispatch, inline ────────────────►      ◄──── async ────────────────►
```

---

### Memory Trick

```
DEFAULT:       Normal. Enqueued immediately. Cancel window before body starts.
LAZY:          New state. Nothing until start()/await(). Beware sequential trap.
ATOMIC:        Guaranteed to reach first suspension. No cancel window at entry.
               Use for: must-run init code before first suspension.
UNDISPATCHED:  Inline on current thread to first suspension. Dispatcher takes over after.
               Use for: must register (subscribe/collect) BEFORE producer emits.

UNDISPATCHED ≠ "whole coroutine on current thread." ONLY to first suspension.
```

### Key Takeaways — Q9.4

| Mode | Execution begins | Cancellable before first suspension? | First thread |
|---|---|---|---|
| `DEFAULT` | Enqueued on dispatcher immediately | Yes (cancel window exists) | Dispatcher's |
| `LAZY` | Only on `start()`/`await()` | Yes | Dispatcher's |
| `ATOMIC` | Enqueued immediately | **No** (guaranteed to first suspension) | Dispatcher's |
| `UNDISPATCHED` | Synchronously inline right now | **No** | **Current calling thread** |

### Self-Test

1. What is the "cancel window" in `DEFAULT` mode? Why does it exist?
2. When would you use `ATOMIC`? Give a concrete example where `DEFAULT` would cause a resource leak that `ATOMIC` prevents.
3. `UNDISPATCHED` — what thread does the code run on before the first suspension? After the first suspension? Where does "after" come from?
4. Show the SharedFlow registration race condition. Explain exactly why `UNDISPATCHED` eliminates it.
5. An interviewer asks: "If `UNDISPATCHED` runs on the current thread, is it the same as calling the suspend function directly?" — What is the answer?

---

## Master Follow-Up Chain — Phase 9

```
Chain F (Suspend Mechanics → Thread Model):
  suspend = CPS transformation (Continuation<T> param + switch state machine)
    └─► ONE ContinuationImpl object per invocation, reused on every resume
         └─► COROUTINE_SUSPENDED = IntrinsicsKt.getCOROUTINE_SUSPENDED() singleton → thread freed
              └─► delay() = suspendCancellableCoroutine + scheduleResumeAfterDelay (NOT Thread.sleep)
                   └─► Dispatcher = ContinuationInterceptor (routes invokeSuspend to correct thread)
                        └─► CancellationException must be re-thrown → Q10.3
                             └─► viewModelScope auto-cancels on onCleared() → Q10.4

Chain H (Structured Concurrency):
  launch returns Job immediately → try-catch around launch: NEVER works (wrong call stack)
    └─► async returns Deferred<T>
         └─► async exception in coroutineScope → propagates IMMEDIATELY (not at await())
              └─► async exception in supervisorScope → contained until await()
                   └─► awaitAll vs sequential await → orphaned coroutine risk
                        └─► CoroutineExceptionHandler root only → Q10.3
```

---

*← [Phase 8 — Other Kotlin Features](08_other_kotlin_features.md) | [Phase 10 — Structured Concurrency →](10_structured_concurrency.md)*