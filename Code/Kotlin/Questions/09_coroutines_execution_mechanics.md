# Phase 9: Coroutines — Execution Mechanics

## Navigation
[← Master Index](master_chains.md)

## Questions in This File
- [Q9.1 — What `suspend` Actually Does](#q91--what-suspend-actually-does)
- [Q9.2 — Coroutine Context and Dispatchers](#q92--coroutine-context-and-dispatchers)
- [Q9.3 — `launch` vs `async`](#q93--launch-vs-async)
- [Q9.4 — Coroutine Start Modes](#q94--coroutine-start-modes)

---

## Q9.1 — What `suspend` Actually Does

> **Builds on:** [Q0.1 — Stack vs Heap (locals become heap fields)](00_jvm_mental_model.md#q01--primitives-vs-references) · [Q0.4 — JVM Call Stack](00_jvm_mental_model.md#q04--the-jvm-call-stack)
> **Connects to:** [Q9.2 — Dispatchers](09_coroutines_execution_mechanics.md#q92--coroutine-context-and-dispatchers) · [Q10.1 — Job Hierarchy](10_structured_concurrency.md#q101--the-job-hierarchy) · [Q4.3 — suspend lambdas](04_functions_lambdas_inlining.md#q43--higher-order-functions-with-suspend)

### The Concrete Picture

You write two lines. The compiler writes a state machine with callbacks:

```kotlin
suspend fun loadData(): String {
    val user = fetchUser()     // line 1: may pause here
    val data = fetchData(user) // line 2: may pause here
    return data
}
```

What the JVM actually runs:
```
First call: label=0 → calls fetchUser → if suspended, returns COROUTINE_SUSPENDED
  Thread is freed. Other work can run.

fetchUser completes → resumes loadData at label=1
  label=1 → calls fetchData → if suspended, returns COROUTINE_SUSPENDED
  Thread freed again.

fetchData completes → resumes loadData at label=2
  label=2 → calls completion.resume(data)
  Caller gets the result.
```

The state machine remembers WHERE to resume (label) and WHAT the local variables were (fields on the Continuation heap object).

### The Core Question: What Is Continuation Passing Style (CPS)?

Continuation Passing Style is a transformation where instead of returning a value directly, a function receives an extra parameter — a **callback** — that it will call with the result when it is done. The "continuation" is "what to do next."

The Kotlin compiler applies CPS transformation to every `suspend` function automatically. You write natural-looking code; the compiler rewrites it. The two things the compiler adds to every `suspend` function are:

1. **A `Continuation<T>` parameter** appended to the function signature
2. **A state machine** that wraps the function body, using a `label` field to remember where execution left off

This is why `suspend fun foo(): String` becomes, at the JVM level, `fun foo(continuation: Continuation<String>): Any`. The return type changes to `Any` because the function may either return a value immediately (`String`) or return the sentinel `COROUTINE_SUSPENDED` to signal that it is not done yet.

---

### State Machine Deep Dive: The `label` Field

The `label` field is an `Int` stored inside the `Continuation` object. It is the **resume point index** — it tells the state machine which `when` branch to jump to when the function is resumed after a suspension.

Every `suspend` call site inside your function becomes a new label value.

#### Original Code

```kotlin
suspend fun loadData(): String {
    val user = fetchUser()     // suspension point 1
    val data = fetchData(user) // suspension point 2
    return data
}
```

#### What the Compiler Generates (Simplified Decompilation)

```kotlin
// The state machine class the compiler creates:
class LoadDataStateMachine(
    val completion: Continuation<String>
) : ContinuationImpl(completion) {

    // Resume point tracker
    var label: Int = 0

    // Local variables that must survive across suspension points
    // are promoted from the stack to fields on this heap object
    var user: User? = null
    var data: String? = null

    // Called by the coroutine runtime when this coroutine is resumed
    override fun invokeSuspend(result: Result<Any?>): Any? {
        return loadData(this)
    }
}

// The transformed function:
fun loadData(continuation: Continuation<String>): Any {
    // Cast or create the state machine
    val sm = continuation as? LoadDataStateMachine
        ?: LoadDataStateMachine(continuation)

    when (sm.label) {
        0 -> {
            // Check for failures from previous resume
            ResultKt.throwOnFailure(sm.result)
            // Advance the label BEFORE suspending,
            // so the next resume lands in label 1
            sm.label = 1
            val result = fetchUser(sm) // pass sm as the continuation
            if (result == COROUTINE_SUSPENDED) {
                return COROUTINE_SUSPENDED // yield control
            }
            sm.user = result as User
            // fall through to label 1 if not suspended
        }
        1 -> {
            ResultKt.throwOnFailure(sm.result)
            sm.user = sm.result as User
            sm.label = 2
            val result = fetchData(sm.user!!, sm)
            if (result == COROUTINE_SUSPENDED) {
                return COROUTINE_SUSPENDED
            }
            sm.data = result as String
            // fall through to label 2
        }
        2 -> {
            ResultKt.throwOnFailure(sm.result)
            sm.data = sm.result as String
        }
        else -> throw IllegalStateException("unexpected label: ${sm.label}")
    }

    // Resume the caller with the final result
    sm.completion.resume(sm.data!!)
    return sm.data!! // (or Unit, depending on context)
}
```

#### State Transition Diagram

```
                  ┌─────────────────────────────────────────────┐
                  │         loadData() State Machine             │
                  └─────────────────────────────────────────────┘

  Entry ──────► label = 0
                    │
                    │  calls fetchUser(sm)
                    │
                    ▼
             fetchUser returns
          ┌── COROUTINE_SUSPENDED? ──┐
          │ YES                      │ NO (fast path, no actual suspend)
          │                          │
          ▼                          ▼
    Thread yields             sm.user = result
    (returns to               fall through to label 1
     coroutine runtime)
          │
          │ ... time passes ...
          │ fetchUser completes, calls sm.resumeWith(result)
          │
          ▼
  label = 1 ◄──── resume here
      │
      │  calls fetchData(sm.user, sm)
      │
      ▼
   fetchData returns
 ┌── COROUTINE_SUSPENDED? ──┐
 │ YES                      │ NO
 │                          │
 ▼                          ▼
Thread yields           sm.data = result
                        fall through to label 2
      │
      │ ... time passes ...
      │ fetchData completes, calls sm.resumeWith(result)
      │
      ▼
label = 2 ◄──── resume here
      │
      │  sm.completion.resume(sm.data)
      │  ──► the caller's continuation is resumed with the String
      │
      ▼
     DONE
```

The key insight: **the label is set BEFORE the suspension call**, so that if the coroutine is resumed, it resumes at the correct label, not at label 0 again.

---

### Where Are Local Variables Stored Across Suspension Points?

**They are stored on the HEAP, not the stack.**

This is one of the most important mechanical facts about coroutines.

In a normal JVM method, local variables live in the stack frame. When the method returns, the stack frame is popped and those variables are gone. But a `suspend` function must be able to "pause" and "resume" — potentially on a completely different thread — without losing its local variable values.

The solution: the compiler promotes any local variable that is live across a suspension point into a **field on the `Continuation` object** (the state machine). Since the `Continuation` is a regular heap-allocated object, it lives as long as there is a reference to it.

```
Before CPS transformation:
  Stack frame (ephemeral):
    [ label: int ]
    [ user: User ]
    [ data: String ]

After CPS transformation:
  Heap (LoadDataStateMachine object):
    [ label: int ]   ← resume point tracker
    [ user: User ]   ← local var promoted to field
    [ data: String ] ← local var promoted to field
    [ completion: Continuation<String> ] ← the caller to notify
```

**Consequence:** Every suspension point creates potential heap allocation overhead. Variables that are NOT live across a suspension point may remain on the stack and not be promoted.

---

### What Is `COROUTINE_SUSPENDED` — The Callback Model

`COROUTINE_SUSPENDED` is a singleton sentinel object defined in the Kotlin coroutines runtime:

```kotlin
// From kotlinx.coroutines internals:
internal val COROUTINE_SUSPENDED: Any = CoroutineSuspendedMarker
```

When a `suspend` function wants to pause and wait for something asynchronous, it:
1. Registers a callback (passes the `Continuation` to some async operation)
2. Returns `COROUTINE_SUSPENDED` to its caller

This is pure callback-based programming under the hood. The difference is that the compiler writes the callbacks for you.

The flow:

```
Your suspend fun ──► calls inner suspend fun ──► inner returns COROUTINE_SUSPENDED
         │                                                      │
         │ also returns COROUTINE_SUSPENDED                     │
         ▼                                                      │
  coroutine runtime                                            │
  (dispatcher / event loop)                                    │
         │                                                      │
         │ ◄── async work completes ──────────────────────────┘
         │     calls continuation.resumeWith(result)
         │
         ▼
  state machine re-entered at correct label
```

The `COROUTINE_SUSPENDED` return value is the signal: "do not call me again directly — I will call you back via the `Continuation`." This is exactly the Callback pattern, just automated by the compiler.

> **Concurrency Trap:** If you inspect the return value of a `suspend` function and it is `COROUTINE_SUSPENDED`, do NOT resume the continuation yourself — the async operation that owns it will do so. Resuming it twice causes undefined behavior (usually a crash with "already resumed").

---

### How Exceptions Propagate Through Suspensions

This is the mechanism behind the fact that `try/catch` works across suspension points — which seems magical until you see how it works.

**The happy path** shown above has `fetchUser()` calling `sm.resumeWith(Result.success(user))`. The failure path is symmetric: `sm.resumeWith(Result.failure(exception))`.

Here is what happens when an async operation fails:

```
1. fetchUser() call fails internally (e.g., IOException from network)

2. Inside fetchUser's state machine:
   sm.completion.resumeWith(Result.failure(IOException("timeout")))
      │
      └─► This sets the CALLER's sm.result = Result.failure(IOException)
          then calls sm.invokeSuspend(sm.result)

3. The caller (loadData) re-enters at label = 1:
   1 -> {
       ResultKt.throwOnFailure(sm.result)   // ← sm.result is Failure here
       // throwOnFailure inspects the Result:
       //   if Success → does nothing
       //   if Failure → throws the wrapped exception
       //               → throws IOException here, in the caller's try/catch scope
   }
```

The critical insight: **`ResultKt.throwOnFailure(sm.result)` is the re-throw point.** Every label in the state machine starts with this call. When a suspended function fails, it resumes the caller with a `Result.failure(...)` — the caller's state machine re-enters at the correct label, and `throwOnFailure` immediately re-throws the exception as if it had been thrown at the original `fetchUser()` call site.

This is why `try/catch` works across suspension points:

```kotlin
suspend fun loadData(): String {
    return try {
        val user = fetchUser()   // suspends here — if fetchUser fails,
                                 // the exception is re-thrown HERE after resume
        val data = fetchData(user)
        data
    } catch (e: IOException) {
        "fallback"               // catches exceptions thrown at either suspension point
    }
}
```

The compiler wraps the entire `try` block's span in the state machine, and any `Result.failure(...)` that arrives during that span is thrown — and therefore caught — by your `catch`.

> **Interview Q:** "Can you catch exceptions from suspended functions with a normal try/catch?"
> Yes. The CPS transformation preserves try/catch semantics by re-throwing failures at the original call site inside the state machine. This is one of coroutines' key advantages over callbacks, where exception handling requires per-callback error handling.

---

### Why Does `suspend` Say NOTHING About Which Thread a Function Runs On?

`suspend` is purely a **compile-time annotation** about the function's calling convention. It means:
- This function may suspend execution
- It participates in the CPS transformation
- It can only be called from other `suspend` functions or coroutine builders

It says absolutely **nothing** about threading. The thread on which a `suspend` function runs is determined entirely by the [**Dispatcher**](09_coroutines_execution_mechanics.md#q92--coroutine-context-and-dispatchers) in the coroutine's context.

```kotlin
// This runs on the Main thread:
withContext(Dispatchers.Main) {
    val user = fetchUser() // fetchUser runs on Main thread!
}

// This runs on an IO thread:
withContext(Dispatchers.IO) {
    val user = fetchUser() // fetchUser runs on IO thread!
}

// This runs on whatever thread called the coroutine:
suspend fun fetchUser(): User { ... }
// fetchUser itself has zero thread preference
```

Think of `suspend` as marking a function as "I can be paused." It is the Dispatcher's job to decide which thread to schedule execution on.

```
suspend keyword ──► only controls: can this function pause?
Dispatcher ──────► controls: on which thread does it run?
```

These are orthogonal concerns. A `suspend` function on `Dispatchers.Main` runs on the main thread. The same `suspend` function under `Dispatchers.IO` runs on an IO thread. The function's code is identical; only the context changes.

---

### Memory Trick

```
SUSPEND = compiler transforms function into a STATE MACHINE.
  Each suspension point → a label in a when() block.
  label = "which line to resume at."

LOCAL VARIABLES across suspension points:
  Normal function: locals on stack (gone when method returns)
  Suspend function: locals promoted to FIELDS on Continuation object (heap)
  → They survive because the Continuation is a heap object that outlives the call.

COROUTINE_SUSPENDED = "I'll call you back. Don't call me."
  The function returns this sentinel to free the thread.
  The thread does other work.
  When async work completes: continuation.resumeWith(result) is called.
  → State machine re-enters at the correct label.

SUSPEND ≠ THREAD:
  suspend = "this can pause" (compile-time concept)
  Thread  = "this runs here" (runtime concept, determined by Dispatcher)
  Same suspend function can run on Main, IO, or Default — depends on context.
```

### Key Takeaways — 9.1

| Concept | Fact |
|---------|------|
| CPS transformation | Compiler adds `Continuation<T>` param + state machine |
| `label` field | Int that tracks which suspension point to resume at |
| Local variables | Promoted from stack to fields on the `Continuation` (heap) |
| `COROUTINE_SUSPENDED` | Sentinel that means "I'll call you back, don't block" |
| `suspend` and threads | Completely unrelated — thread is determined by Dispatcher |

---

## Q9.2 — Coroutine Context and Dispatchers

> **Builds on:** [Q9.1 — CPS and suspend](09_coroutines_execution_mechanics.md#q91--what-suspend-actually-does)
> **Connects to:** [Q10.4 — Lifecycle Scopes](10_structured_concurrency.md#q104--lifecycle-scopes-and-process-death) · [Q13.3 — viewModelScope](13_android_architecture.md#q133--viewmodel-internals)

### The Concrete Picture

CoroutineContext = a typed map. Think of it as a bag with slots:

```
CoroutineContext bag:
  [Job slot]         → Job (tracks lifecycle: active/cancelled/done)
  [Dispatcher slot]  → Dispatchers.Main / IO / Default
  [Name slot]        → CoroutineName("MyCoroutine")  (optional)
  [Handler slot]     → CoroutineExceptionHandler      (optional)

Only ONE element per slot. Right side wins when merging:
  Dispatchers.IO + CoroutineName("X") + Dispatchers.Main
  → Dispatcher slot = Main  (Main replaced IO)
  → Name slot = "X"
```

Dispatchers.Default vs IO — they share ONE thread pool:
```
Same physical threads in the pool!
  Default → max = CPU cores (e.g., 8 on 8-core machine)
  IO      → max = 64 (expands for blocking work)

Same pool means: switching Default→IO may not change the actual thread.
Switching Main→IO ALWAYS changes the thread (Main is its own thread).
```

### What Is a `CoroutineContext`?

`CoroutineContext` is a **typed, immutable map** from keys to elements. Each element in the context has a companion `Key` object, and only one element per key can exist in a context.

The elements that typically live in a `CoroutineContext`:

```
CoroutineContext (typed map)
┌──────────────────────────────────────────────────────────┐
│  Key                    │  Element                       │
│─────────────────────────│───────────────────────────────│
│  Job.Key                │  Job (the coroutine's lifecycle)│
│  ContinuationInterceptor│  Dispatcher (thread scheduling) │
│  CoroutineName.Key      │  CoroutineName("MyCoroutine")  │
│  CoroutineExceptionHandler.Key │ ExceptionHandler        │
└──────────────────────────────────────────────────────────┘
```

The `CoroutineContext` interface:

```kotlin
interface CoroutineContext {
    operator fun <E : Element> get(key: Key<E>): E?
    fun <R> fold(initial: R, operation: (R, Element) -> R): R
    operator fun plus(context: CoroutineContext): CoroutineContext
    fun minusKey(key: Key<*>): CoroutineContext
}
```

### The `+` Operator: Combining Contexts

The `+` operator on two `CoroutineContext` objects **merges them, with the right-hand side winning on key conflicts** (see [Q10.1 — Job Hierarchy](10_structured_concurrency.md#q101--the-job-hierarchy) for the Job tree structure).

```kotlin
val context1 = Dispatchers.IO + CoroutineName("Fetcher")
val context2 = Dispatchers.Main + CoroutineName("UI-Fetcher")

val merged = context1 + context2
// merged contains:
//   Dispatcher = Dispatchers.Main   (right side wins, replaces IO)
//   CoroutineName = "UI-Fetcher"    (right side wins)
```

This is not set union — it is a **right-biased merge**. You can think of it as: each `Element` carries its own `Key`, and `plus` is a `put` operation that overwrites the existing value for that key.

```kotlin
// The actual implementation in CoroutineContext.kt (simplified):
operator fun plus(context: CoroutineContext): CoroutineContext {
    // fold over the right context, accumulating into left
    // for each element in right: if same key exists in left, replace it
    return if (context === EmptyCoroutineContext) this
    else context.fold(this) { acc, element ->
        val removed = acc.minusKey(element.key)
        if (removed === EmptyCoroutineContext) element
        else CombinedContext(removed, element)
    }
}
```

### `Dispatchers.Default` vs `Dispatchers.IO` — Same Pool or Different?

**They share the SAME underlying thread pool**, but with different concurrency limits.

```
JVM Thread Pool (kotlinx.coroutines shared pool)
┌──────────────────────────────────────────────────────┐
│  Thread-1  Thread-2  Thread-3  Thread-4  ...         │
│                                                      │
│  ┌────────────────────┐  ┌─────────────────────────┐│
│  │  Dispatchers.Default│  │   Dispatchers.IO        ││
│  │  Limit: CPU cores   │  │   Limit: 64 threads     ││
│  │  (e.g., 8 on 8-core)│  │   (system property      ││
│  │                     │  │    configurable)         ││
│  └────────────────────┘  └─────────────────────────┘│
│                                                      │
│  Same threads, different scheduling policies         │
└──────────────────────────────────────────────────────┘
```

- `Dispatchers.Default`: backed by a pool limited to `max(2, Runtime.getRuntime().availableProcessors())` threads. Designed for CPU-intensive work where you don't want more threads than cores.
- `Dispatchers.IO`: uses the SAME thread pool, but can **expand** it up to 64 threads (or `kotlinx.coroutines.io.parallelism` system property) to handle blocking I/O where threads spend most of their time waiting.

This is why switching from `Dispatchers.Default` to `Dispatchers.IO` does NOT always cause a thread switch — if there are idle threads in the pool, the same physical thread may be reused.

```kotlin
// Both dispatchers pull from the same pool:
withContext(Dispatchers.IO) {
    // may run on Thread-3
    withContext(Dispatchers.Default) {
        // may STILL run on Thread-3 (same pool, thread not necessarily switched)
    }
}
```

### `Dispatchers.Main` vs `Dispatchers.Main.immediate`

`Dispatchers.Main` on Android posts work to the main thread's `Handler` (message queue). Even if you are already on the main thread, it will **post** the block to the queue, introducing a small delay and a queue-round-trip.

`Dispatchers.Main.immediate` is smarter: if you are **already on the main thread**, it executes the block **inline, synchronously**, without posting to the Handler queue. Only if you are on a background thread does it post to the main thread queue.

```kotlin
// On Main thread:
withContext(Dispatchers.Main) {
    // Posts to Handler queue, even though we're already on Main.
    // Must wait for other pending messages in the queue.
    updateUI()
}

withContext(Dispatchers.Main.immediate) {
    // If already on Main thread: executes RIGHT NOW, no queue round-trip
    // If on background thread: posts to Handler queue (same as Main)
    updateUI()
}
```

**Why does this matter?** `viewModelScope` uses `Dispatchers.Main.immediate` (via `SupervisorJob() + Dispatchers.Main.immediate`) precisely so that ViewModel-launched coroutines that start on the main thread do not unnecessarily delay their first resumption.

### When Does `withContext(Dispatchers.IO)` Cause a Thread Switch?

`withContext` checks whether the current dispatcher and the target dispatcher are the same. If they are, no thread switch occurs.

The exact logic:
1. If the current coroutine is already dispatched on `Dispatchers.IO`, `withContext(Dispatchers.IO)` may reuse the current thread (no thread switch).
2. If switching from `Dispatchers.Default` to `Dispatchers.IO`, since they share a pool, the "switch" may or may not involve an actual thread change — the dispatcher logic schedules the continuation on an IO-qualified thread, which could be the same physical thread.
3. A switch from `Dispatchers.Main` to `Dispatchers.IO` always involves a thread switch (Main thread cannot be an IO thread).

```kotlin
// Case 1: No switch (already on IO)
withContext(Dispatchers.IO) {
    withContext(Dispatchers.IO) {
        // Likely same thread — dispatcher sees no change
    }
}

// Case 2: Possible switch (Default → IO, same pool)
withContext(Dispatchers.Default) {
    withContext(Dispatchers.IO) {
        // Scheduler picks an IO-eligible thread, may or may not be same
    }
}

// Case 3: Always switches (Main → IO)
// (on Main thread)
withContext(Dispatchers.IO) {
    // Always jumps to a background thread
}
```

### `limitedParallelism(N)` — Restricting Concurrency on IO

`Dispatchers.IO.limitedParallelism(N)` creates a **view** of the IO dispatcher that limits how many coroutines from that view can run concurrently to `N`.

```kotlin
// Default IO dispatcher: up to 64 threads can run simultaneously
val dbDispatcher = Dispatchers.IO.limitedParallelism(4)
// Only 4 coroutines dispatched to dbDispatcher can run at once
// Others wait in a queue

// Usage:
withContext(dbDispatcher) {
    // At most 4 of these run concurrently across all callers using dbDispatcher
    readDatabase()
}
```

The key differences from the raw `Dispatchers.IO`:

| Aspect | `Dispatchers.IO` | `Dispatchers.IO.limitedParallelism(N)` |
|--------|------------------|----------------------------------------|
| Max concurrent tasks | 64 (default) | N (your choice) |
| Thread pool used | Shared IO pool | Same shared IO pool |
| Queue behavior | All 64 slots compete | Only N slots active, rest queue |
| Use case | General IO | Critical resource (DB connections, file handles) |

This is useful when you have a resource that supports limited simultaneous access (e.g., a SQLite database, a fixed-size connection pool, or a file that should be written by at most N writers).

> **Concurrency Trap:** `limitedParallelism(N)` limits concurrency, not thread count. The threads used still come from the shared pool. If you call `limitedParallelism(1)`, you get serial execution through that view, but the thread may be different each time.

---

### Memory Trick

```
CoroutineContext = TYPED MAP. Key per element. + merges, right side wins.

FOUR DISPATCHER RULES:
  Dispatchers.Main     → UI thread (Android handler queue)
  Dispatchers.Default  → CPU work (max = core count)
  Dispatchers.IO       → blocking I/O (max = 64, same pool as Default)
  Dispatchers.Unconfined → runs wherever, rarely used

Main vs Main.immediate:
  Main          → always posts to Handler queue (even if already on Main)
  Main.immediate → executes inline if already on Main (no queue round-trip)
  viewModelScope uses Main.immediate for faster startup.

limitedParallelism(N) → limits concurrent coroutines, NOT thread count.
  .limitedParallelism(1) → serial execution through that view.
  Threads still come from the shared IO pool.
```

### Key Takeaways — 9.2

| Concept | Fact |
|---------|------|
| `CoroutineContext` | Typed map of Key → Element; `+` is right-biased merge |
| `Dispatchers.Default` | Same pool as IO, limited to CPU core count |
| `Dispatchers.IO` | Same pool as Default, expands up to 64 threads |
| `Main.immediate` | If already on Main: runs inline; otherwise posts to Handler |
| `withContext` thread switch | Not guaranteed if same pool — depends on scheduler |
| `limitedParallelism(N)` | Creates a view limiting concurrent access to N; same underlying pool |

---

## Q9.3 — `launch` vs `async`

> **Builds on:** [Q9.1 — suspend mechanics](09_coroutines_execution_mechanics.md#q91--what-suspend-actually-does) · [Q9.2 — CoroutineContext](09_coroutines_execution_mechanics.md#q92--coroutine-context-and-dispatchers)
> **Connects to:** [Q10.2 — coroutineScope vs supervisorScope](10_structured_concurrency.md#q102--coroutinescope-vs-supervisorscope) · [Q10.3 — Exception handling](10_structured_concurrency.md#q103--exception-handling-rules)

### The Concrete Picture

launch vs async — two outcomes, one key difference:

```
launch {  } → returns Job  (fire and forget, no result)
async  {  } → returns Deferred<T>  (result holder, call await() to get it)

Deferred<T> extends Job. So it also has cancel(), join(), isActive.
```

Common misconception about async exception timing:
```
async exception propagation:

coroutineScope {
    val d = async { throw Exception("fail") }
    // RIGHT NOW: exception propagates up to coroutineScope
    // coroutineScope starts cancelling
    delay(100)   // may never reach here
    d.await()    // also throws here (but scope may already be dead)
}

NOT "contained until await()". That's the supervisorScope version.
```

try-catch around `launch` — why it doesn't work:
```
try {
    launch { throw Exception() }  // schedules, returns immediately
} catch (e: Exception) {
    // NEVER fires — the exception is on a DIFFERENT call stack
    // (inside the coroutine, not this code)
}
```

### Type Hierarchy: `Job` vs `Deferred<T>`

`launch` returns a `Job`. `async` returns a `Deferred<T>`. `Deferred<T>` extends `Job`:

```kotlin
interface Deferred<out T> : Job {
    suspend fun await(): T
    fun getCompleted(): T             // throws if not yet complete
    fun getCompletionExceptionOrNull(): Throwable?
}
```

```
Job (interface)
├── cancel(): Boolean
├── join(): Unit (suspend)
├── isActive: Boolean
├── isCompleted: Boolean
├── isCancelled: Boolean
│
└── Deferred<T> (interface, extends Job)
    ├── await(): T   (suspend — waits for result)
    ├── getCompleted(): T
    └── getCompletionExceptionOrNull(): Throwable?
```

`launch` is fire-and-forget: the result (if any) is discarded; you only get lifecycle control via `Job`.

`async` is eager computation: it starts immediately (by default) and holds a result or exception that you retrieve via `await()`.

```kotlin
// launch: no result, fire and forget
val job: Job = launch {
    performTask()
}
job.join() // wait for completion, no result

// async: returns a result via Deferred
val deferred: Deferred<String> = async {
    computeResult()
}
val result: String = deferred.await() // suspend until result ready
```

### Does `async` Propagate Exceptions to the Parent Immediately?

**Yes, immediately when the coroutine fails — not only at `.await()`.** This is a common interview misconception.

The exact behavior:
1. The `async` block throws an exception.
2. The exception is **stored in the `Deferred`** (to be re-thrown at `await()`).
3. The exception is **also propagated to the parent coroutine immediately** through the structured concurrency mechanism.
4. When you call `await()`, the stored exception is re-thrown.

```kotlin
coroutineScope {
    val deferred = async {
        throw RuntimeException("failure")
        // This exception propagates to the parent coroutineScope NOW
        // (not waiting for await())
    }

    delay(100) // The coroutineScope may already be failing here

    val result = deferred.await() // Also throws RuntimeException here
}
```

> **Concurrency Trap:** Many developers believe that `async` "contains" exceptions until `await()`. This is WRONG. The `async` coroutine is still a child of its scope, and its failures propagate upward immediately via structured concurrency. The exception is BOTH stored in `Deferred` AND propagated. Only if you use `supervisorScope` or `SupervisorJob` does the exception get isolated.

The only case where `async` appears to "contain" the exception is when you use it inside a `supervisorScope`, which prevents upward propagation. Then only `await()` throws.

```kotlin
// With supervisorScope: exception contained until await()
supervisorScope {
    val deferred = async {
        throw RuntimeException("isolated failure")
    }
    // supervisorScope does NOT cancel here
    try {
        deferred.await() // throws here
    } catch (e: RuntimeException) {
        // handle it
    }
}

// With coroutineScope: exception propagates immediately
coroutineScope {
    val deferred = async {
        throw RuntimeException("propagates NOW")
    }
    // coroutineScope is already cancelling at this point
    deferred.await() // throws, but scope may already be dead
}
```

### Why Does `try-catch` Around `launch { }` NOT Catch the Exception?

`launch` schedules the coroutine and returns a `Job` **immediately** — before the coroutine body even starts executing. The `try-catch` wraps the launch scheduling call, not the execution of the lambda body.

```kotlin
try {
    launch {
        throw RuntimeException("exception inside coroutine")
        // This runs LATER, on a different coroutine's call stack
    }
    // launch returns immediately here — no exception thrown
} catch (e: RuntimeException) {
    // This catch NEVER fires
    // The exception from inside launch goes to the CoroutineExceptionHandler
    // or crashes the app, depending on scope
}
```

The coroutine body executes asynchronously. It has its own call stack, which is completely separate from the stack that contains the `try-catch`. Exceptions from inside `launch` travel through the **coroutine hierarchy** (via `childCancelled`) — see [Job hierarchy](10_structured_concurrency.md#q101--the-job-hierarchy) — not through the JVM call stack.

**What DOES work:**

```kotlin
// Option 1: try-catch INSIDE the launch
launch {
    try {
        riskyOperation()
    } catch (e: RuntimeException) {
        // This catches it correctly
    }
}

// Option 2: CoroutineExceptionHandler (for root coroutines)
val handler = CoroutineExceptionHandler { _, exception ->
    println("Caught: $exception")
}
GlobalScope.launch(handler) {
    throw RuntimeException("caught by handler")
}

// Option 3: Use async + await
val result = runCatching {
    async {
        riskyOperation()
    }.await()
}
```

### The Lazy `async` Sequential Trap

`async(start = CoroutineStart.LAZY)` does NOT start the coroutine until `await()` (or `start()`) is called. This means if you call `await()` on each deferred sequentially, you get sequential execution, not parallel.

```kotlin
// WRONG: Sequential execution, NOT parallel!
val a = async(start = CoroutineStart.LAZY) { compute1() } // not started yet
val b = async(start = CoroutineStart.LAZY) { compute2() } // not started yet

val result = a.await() + b.await()
// Timeline:
// t=0: a.await() → compute1() STARTS now
// t=3: compute1() finishes, a.await() returns
// t=3: b.await() → compute2() STARTS now (b was waiting for a to finish!)
// t=6: compute2() finishes
// Total time: 6 seconds (sequential)
```

```kotlin
// CORRECT: Parallel execution
val a = async { compute1() } // starts immediately
val b = async { compute2() } // starts immediately

val result = a.await() + b.await()
// Timeline:
// t=0: compute1() and compute2() both running simultaneously
// t=3: both finish
// t=3: result computed
// Total time: 3 seconds (parallel)
```

If you DO want lazy async for parallelism, you must manually start both before awaiting:

```kotlin
// CORRECT with LAZY: start both before awaiting
val a = async(start = CoroutineStart.LAZY) { compute1() }
val b = async(start = CoroutineStart.LAZY) { compute2() }

a.start() // start a
b.start() // start b, now both are running

val result = a.await() + b.await() // now truly parallel
```

> **Concurrency Trap:** `async(start = LAZY)` is not automatically parallel. You must call `.start()` on all of them before awaiting, or simply omit `LAZY` for eager parallel execution.

---

### Memory Trick

```
launch = fire and forget (Job, no result)
async  = get a result later (Deferred<T>, await() to retrieve)

ASYNC EXCEPTION = propagates to parent IMMEDIATELY.
  NOT "contained until await()". That's only in supervisorScope.
  In coroutineScope: async failure cancels the whole scope NOW.

TRY-CATCH AROUND LAUNCH = DOESN'T WORK.
  launch returns immediately. Exception is on a different call stack.
  Fix: put try-catch INSIDE the launch block.
  Or use CoroutineExceptionHandler for root coroutines.

LAZY ASYNC TRAP:
  async(LAZY) { }  → NOT started until await() or start()
  a.await() + b.await()  ← sequential if a and b are both LAZY
  Fix: call a.start(); b.start() BEFORE any await().
```

### Key Takeaways — 9.3

| Concept | Fact |
|---------|------|
| `Deferred<T>` | Extends `Job`; adds `await()` for retrieving result |
| `async` exception propagation | Propagates to parent IMMEDIATELY (not only at `await()`) |
| `try-catch` around `launch` | Does NOT work — exception is on a different call stack |
| Lazy `async` trap | `async(start = LAZY)` is sequential unless you call `.start()` on all before any `.await()` |

---

## Q9.4 — Coroutine Start Modes

> **Builds on:** [Q9.3 — launch vs async](09_coroutines_execution_mechanics.md#q93--launch-vs-async) · [Q9.2 — Dispatchers](09_coroutines_execution_mechanics.md#q92--coroutine-context-and-dispatchers)
> **Connects to:** [Q11.4 — Flow collection and lifecycle](11_flow.md#q114--flow-collection-and-lifecycle)

### The Concrete Picture

Four modes, one question each:

```
DEFAULT:       scheduled immediately. Cancel window before it starts running.
               "Normal. Schedule now, run when dispatcher picks it up."

LAZY:          nothing happens until you call start() or await().
               "I'll tell you when to start."

ATOMIC:        scheduled immediately. Cannot cancel before first suspension.
               "Guaranteed to run at least to the first suspend point."
               Use when: must acquire a resource before any cancellation.

UNDISPATCHED:  runs RIGHT NOW on the CURRENT thread until first suspension.
               Then switches to the dispatcher's thread after that.
               "Start immediately here, then hand off after first pause."
               Use when: must register listener BEFORE producer emits.
```

### The Four Start Modes

`CoroutineStart` is an enum with four values: `DEFAULT`, `LAZY`, `ATOMIC`, and `UNDISPATCHED`.

#### Comparison Table

| Start Mode | When Execution Begins | Cancellable Before First Suspension? | Thread of First Execution |
|------------|----------------------|--------------------------------------|--------------------------|
| `DEFAULT` | Immediately scheduled | YES — can be cancelled before first line | Dispatcher's thread |
| `LAZY` | Only when `start()` or `await()` called | YES — same as DEFAULT | Dispatcher's thread |
| `ATOMIC` | Immediately scheduled | NO — cannot be cancelled until first suspension | Dispatcher's thread |
| `UNDISPATCHED` | Immediately, on current thread | NO — same guarantee as ATOMIC for first block | Current thread (caller's thread) |

#### `DEFAULT` — Standard Scheduling

```kotlin
val job = launch(start = CoroutineStart.DEFAULT) {
    // scheduled immediately
    // but can be cancelled before it actually starts running
    println("Running")
}
job.cancel() // If called fast enough, "Running" never prints
```

`DEFAULT` schedules the coroutine on the dispatcher immediately. Because scheduling is asynchronous, there is a window between `launch` returning and the coroutine body starting. In that window, the coroutine can be cancelled.

#### `LAZY` — On-Demand Execution

```kotlin
val job = launch(start = CoroutineStart.LAZY) {
    println("This only runs when you call start() or join()")
}
// Nothing happens yet

job.start() // Now it runs
// or: job.join() also starts + waits
```

Useful for building coroutines that are conditionally started, or for `async(start = LAZY)` when you want explicit control over when computation begins (though beware the sequential trap above).

#### `ATOMIC` — Guaranteed-to-Start

```kotlin
val job = launch(start = CoroutineStart.ATOMIC) {
    // This block will ALWAYS start, even if the job is cancelled
    // before the dispatcher runs it.
    acquireResource()  // guaranteed to run
    // ...
    delay(100)         // THIS is the first suspension point
    // From this point on, normal cancellation applies
    releaseResource()
}
job.cancel()
// Even with cancel() called immediately, acquireResource() WILL run
// The coroutine cannot be cancelled until the first suspension (delay)
```

`ATOMIC` guarantees that the coroutine body executes **at least up to the first suspension point**, regardless of cancellation. After the first suspension, cancellation works normally.

**When to use `ATOMIC`:** When you need to ensure initialization code runs before any cancellation can occur — for example, registering a resource before any suspension that might never return.

#### `UNDISPATCHED` — Runs Now, On This Thread

```kotlin
// Suppose we're on the Main thread

launch(start = CoroutineStart.UNDISPATCHED) {
    // First block: runs SYNCHRONOUSLY on the CURRENT thread (Main thread)
    // even if the dispatcher is Dispatchers.IO
    println("I'm on: ${Thread.currentThread().name}") // Main thread

    delay(100) // <<< FIRST SUSPENSION POINT

    // After first suspension: resumes on the Dispatcher's thread (IO thread)
    println("I'm on: ${Thread.currentThread().name}") // IO thread
}
// Execution reaches here AFTER the delay is encountered (not after the whole launch)
```

`UNDISPATCHED` runs the coroutine **synchronously on the calling thread** until the first suspension point. After that, normal dispatch rules apply.

**Key distinction:**
- **Before first suspension:** Current thread, synchronously, no dispatch overhead
- **After first suspension:** Determined by the coroutine's dispatcher

**Why is `UNDISPATCHED` useful for guaranteed initialization before an emitter fires?**

Consider a [`SharedFlow`](11_flow.md#q113--stateflow-vs-sharedflow) or `Channel` where you want to collect from it before the producer starts emitting. With `DEFAULT`, there is a scheduling gap:

```kotlin
// Problem with DEFAULT:
val sharedFlow = MutableSharedFlow<Int>()

launch { sharedFlow.collect { println(it) } } // scheduled, may not start yet!
sharedFlow.emit(1)  // emitted BEFORE the collector is even registered!

// Solution with UNDISPATCHED:
launch(start = CoroutineStart.UNDISPATCHED) {
    sharedFlow.collect { println(it) } // runs NOW, on current thread, registers immediately
}
sharedFlow.emit(1) // guaranteed: collector is already registered
```

The `UNDISPATCHED` start ensures that the coroutine reaches its first suspension point (the `collect` call, which suspends waiting for emissions) before the calling code continues. This eliminates the race condition between registration and emission.

> **Concurrency Trap:** `UNDISPATCHED` does NOT mean the entire coroutine runs on the current thread. Only the segment before the first `suspend` call does. If you have important work after the first suspension, it runs on the dispatcher's thread, not the current one.

---

### ASCII Diagram: Start Mode Timelines

```
Time ──────────────────────────────────────────────────────────►

DEFAULT:
  launch() ──► [scheduled] ─── [dispatcher picks up] ──► [runs]
                   ▲ cancel window ▲

LAZY:
  launch() ──► [not scheduled] ──────────────────────────────────
                                 start() ──► [scheduled] ──► [runs]

ATOMIC:
  launch() ──► [scheduled] ──► [runs: CANNOT cancel until here]──►[first suspend]──►...
                                ◄───── guaranteed execution ──────►

UNDISPATCHED:
  launch() ──► [runs NOW on current thread] ──► [first suspend]──►[dispatcher thread]
               ◄── synchronous ──────────────►  ◄── async ──────►
```

---

### Key Takeaways — 9.4

| Start Mode | Key Property | Typical Use Case |
|------------|-------------|------------------|
| `DEFAULT` | Immediate schedule, cancellable before start | Normal coroutines |
| `LAZY` | Only starts when explicitly triggered | Conditional computation, explicit control |
| `ATOMIC` | Cancellation impossible before first suspension | Must-run initialization code |
| `UNDISPATCHED` | Synchronous on current thread until first suspension | Register listener before producer fires |

---

## Master Follow-Up Chain — Phase 9

**Chain F (Coroutine Cancellation) — Phase 9 segment:**

```
suspend = state machine, not thread
  └─► label field = resume point index
       └─► locals stored in Continuation object (heap, not stack)
            └─► COROUTINE_SUSPENDED = callback sentinel
                 └─► Dispatcher = which thread, separate from suspend
                      └─► CancellationException must be re-thrown
                           └─► Q10: structured cancellation propagation
```

**Chain H (Structured Concurrency) — Phase 9 segment:**

```
launch returns Job immediately
  └─► try-catch around launch won't work
       └─► async returns Deferred<T>
            └─► async exception propagates NOW, not just at await()
                 └─► supervisorScope isolates it → Q10.2
                      └─► CoroutineExceptionHandler → Q10.3
```

---

## Cross-References

- [Q4.3](04_functions_lambdas_inlining.md#q43--higher-order-functions-with-suspend): suspend lambdas — how they differ from regular lambdas (`CPS` + extra `Continuation` param)
- [Q10.1](10_structured_concurrency.md#q101--the-job-hierarchy): Job hierarchy — how the Job/parent-child tree connects to coroutine scopes
- [Q10.3](10_structured_concurrency.md#q103--exception-handling-rules): Exception handling rules — why `CoroutineExceptionHandler` root-only, `CancellationException` rules
- [Q11.1](11_flow.md#q111--cold-vs-hot-streams): Flow — how `Flow` uses `suspend` and the CPS model for reactive streams
- [Q17.4](17_performance_and_memory.md#q174--testing): Testing — `StandardTestDispatcher`, `UnconfinedTestDispatcher`, `runTest`
- [J6.3 — wait/notify](../../Java/Questions/J6_concurrency_fundamentals.md): The JVM primitive that coroutines abstract over — `suspend` replaces `wait()`, Dispatcher replaces thread pool management
- [J9.3 — Virtual Threads](../../Java/Questions/J9_modern_java.md): Java's answer to the same I/O-blocking problem coroutines solve — understand the contrast before interviews

---

*← [Phase 8 — Other Kotlin Features](08_other_kotlin_features.md) | [Phase 10 — Structured Concurrency →](10_structured_concurrency.md)*
