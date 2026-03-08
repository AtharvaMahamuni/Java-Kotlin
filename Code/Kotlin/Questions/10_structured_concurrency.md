# Phase 10: Structured Concurrency

## Navigation
[← Phase 9 — Coroutines: Execution Mechanics](09_coroutines_execution_mechanics.md) | [→ Phase 11 — Flow](11_flow.md)

## Questions in This File
- [Q10.1 — The Job Hierarchy](#q101--the-job-hierarchy)
- [Q10.2 — `coroutineScope` vs `supervisorScope`](#q102--coroutinescope-vs-supervisorscope)
- [Q10.3 — Exception Handling Rules](#q103--exception-handling-rules)
- [Q10.4 — Lifecycle Scopes and Process Death](#q104--lifecycle-scopes-and-process-death)
- [Q10.5 — `select` Expression](#q105--select-expression)
- [Q10.6 — Mutex and Synchronization Primitives](#q106--mutex-and-synchronization-primitives)

---

## Q10.1 — The Job Hierarchy

> **Builds on:** [Q9.3 — launch vs async](09_coroutines_execution_mechanics.md#q93--launch-vs-async) · [Q9.2 — CoroutineContext](09_coroutines_execution_mechanics.md#q92--coroutine-context-and-dispatchers)
> **Connects to:** [Q10.2 — coroutineScope](#q102--coroutinescope-vs-supervisorscope) · [Q10.3 — Exception propagation](#q103--exception-handling-rules)

---

### The Concrete Picture

Every `launch` and `async` creates a child `Job` linked into a tree:

```
viewModelScope (SupervisorJob)
  ├── Job A  ← launch { fetchProfile() }
  ├── Job B  ← launch { fetchAds() }     ← throws RuntimeException
  └── Job C  ← launch { fetchWeather() }
```

Two directions of propagation:

```
CANCELLATION flows DOWN:
  viewModelScope cancelled → A, B, C all cancelled via cancel() chain

EXCEPTIONS flow UP (regular Job):
  Job B throws RuntimeException
    → childCancelled(RuntimeException) on parent → returns false (not handled)
    → parent cancels itself → cancels A and C (siblings!)
    → propagates up to viewModelScope

EXCEPTIONS absorbed by SupervisorJob:
  Job B throws RuntimeException
    → childCancelled(RuntimeException) on SupervisorJob → returns true (absorbed)
    → A continues, C continues, viewModelScope unaffected
```

---

### The Three Invariants of Structured Concurrency

**Invariant 1: A parent waits for all its children.**

A parent `Job` does not transition to `Completed` until every child `Job` completes (success, cancellation, or handled failure). This is enforced by reference counting in `JobSupport` — no coroutine is ever "lost."

```kotlin
coroutineScope {
    launch { delay(1000); println("child 1") }
    launch { delay(2000); println("child 2") }
}
println("Both finished")  // printed at t=2000ms — scope waited for both children
```

**Invariant 2: Cancelling a parent cancels all its children.**

Cancellation flows downward through the entire subtree by calling `cancel()` on each child recursively.

```kotlin
val parent = scope.launch {
    val c1 = launch { delay(Long.MAX_VALUE) }
    val c2 = launch { delay(Long.MAX_VALUE) }
}
parent.cancel()  // c1 and c2 both receive CancellationException — they stop
```

**Invariant 3: An unhandled child exception cancels the parent (and all siblings).**

With a regular `Job`, exceptions flow upward. A failing child cancels its parent, which cancels all siblings.

```kotlin
coroutineScope {
    launch { throw RuntimeException("I failed") }  // propagates up via childCancelled
    launch { delay(Long.MAX_VALUE) }               // cancelled as collateral sibling
}
// coroutineScope throws RuntimeException
```

---

### ## Trap: `GlobalScope` Breaks All Three Invariants

`GlobalScope` is a scope whose `Job` has no parent. Any coroutine launched in it is outside the structured concurrency hierarchy:

```kotlin
// WRONG: GlobalScope escapes the hierarchy
class MyViewModel : ViewModel() {
    fun loadData() {
        GlobalScope.launch {    // NOT a child of viewModelScope
            fetchData()         // runs even after ViewModel is destroyed
        }                       // → memory leak, potential crash
    }
}

// CORRECT: viewModelScope
class MyViewModel : ViewModel() {
    fun loadData() {
        viewModelScope.launch {   // child of viewModelScope's SupervisorJob
            fetchData()           // auto-cancelled on onCleared()
        }
    }
}
```

**What `GlobalScope.launch` breaks:**

```
Invariant 1: parent does NOT wait → coroutine outlives its logical owner
Invariant 2: parent cancelled → GlobalScope children NOT cancelled → leak
Invariant 3: exceptions propagate to GlobalScope → no parent → crash or swallowed
```

Never use `GlobalScope` in production Android code. Use `viewModelScope`, `lifecycleScope`, or a custom scope with a known lifecycle.

---

### `childCancelled(cause)` — The Core Decision Point

`childCancelled` is called on a parent `Job` when one of its children fails. The return value determines propagation:

```
childCancelled returns true:
  "I handled this — do NOT propagate further up."
  Parent absorbs the failure. Its own parent and siblings are unaffected.

childCancelled returns false:
  "I did not handle this — propagate up."
  Parent cancels itself and notifies its own parent.
```

**Regular `Job` / `coroutineScope` (class `ScopeCoroutine`):**

```kotlin
// Source-level behaviour of ScopeCoroutine.childCancelled:
// CancellationException → returns true  (normal lifecycle end, not a failure)
// Any other exception   → returns false (failure, propagate up)
```

**`SupervisorJob` / `supervisorScope` (class `SupervisorCoroutine`):**

```kotlin
// THE ONE OVERRIDE that makes supervisor scopes work:
override fun childCancelled(cause: Throwable): Boolean = false
// Wait — returns false for ALL exceptions?
// Yes — but "false" from a SupervisorJob means: "I'm not cancelling myself,
// and I'm marking this child as failed in isolation."
// The difference: regular Job also cancels itself when it returns false.
// SupervisorJob's childCancelled is effectively "absorb but don't self-cancel."
```

More precisely: `SupervisorJob.childCancelled` returns `false` to say "I won't self-cancel due to this child," and the coroutines framework respects this by not cancelling the supervisor or its other children.

Interview-level summary:
```
Regular Job:     child fails → parent cancels itself → siblings cancelled → propagates up.
SupervisorJob:   child fails → absorbed → siblings continue → parent unaffected.
```

---

### `CancellationException` Is NOT a Failure

`CancellationException` is a normal lifecycle signal — "this coroutine was cancelled." The framework treats it as an expected outcome, not an error:

```
Child throws CancellationException:
  parent.childCancelled(CancellationException) → returns true (handled normally)
  Parent does NOT cancel itself
  Siblings unaffected

Child throws RuntimeException:
  parent.childCancelled(RuntimeException) → returns false (with regular Job)
  → parent cancels → siblings cancelled → propagates
```

This distinction is why `CancellationException` must always be re-thrown if caught — see Q10.3.

---

### Memory Trick

```
CANCELLATION = DOWN the tree.   Cancel parent → all children cancelled.
EXCEPTIONS   = UP the tree.     Child fails → parent fails → siblings cancelled.
SupervisorJob = FIREWALL.        child fails → absorbed → siblings continue.

3 INVARIANTS:
  1. Parent WAITS for ALL children (no coroutine ever lost — JobSupport ref count)
  2. Cancel parent → CANCEL all children (downward, recursive)
  3. Child non-CE exception → cancels parent + siblings (upward) — unless SupervisorJob

GlobalScope = NO PARENT → breaks all 3 invariants → ALWAYS a leak risk.
  viewModelScope / lifecycleScope = always use these in Android.

CancellationException = normal lifecycle event. NOT a failure.
  parent.childCancelled(CE) → returns true → siblings unaffected.
  parent.childCancelled(RuntimeException) → returns false → siblings cancelled.
```

### Key Takeaways — Q10.1

| Concept | Fact |
|---|---|
| Invariant 1 | Parent waits for all children before completing |
| Invariant 2 | Cancelling parent cancels all children |
| Invariant 3 | Child exception cancels parent + siblings (regular Job) |
| `GlobalScope` | No parent — breaks all 3 invariants — leak risk |
| `childCancelled` returns `true` | Exception absorbed, no upward propagation |
| `childCancelled` returns `false` | Exception propagates, parent cancels itself |
| `CancellationException` | Normal lifecycle signal, not a failure |

### Self-Test

1. Draw the Job tree for `viewModelScope` launching 3 sibling coroutines. Label which Job is the root.
2. One of 3 sibling coroutines throws `RuntimeException` with a regular `coroutineScope`. What happens to the other two? Trace the `childCancelled` call chain.
3. Same scenario with `supervisorScope`. What happens and why — what does `childCancelled` return?
4. What are the three invariants of structured concurrency? Which one does `GlobalScope` break?
5. *"A child throws `CancellationException` — does the parent cancel its other children?"* Why not?

---

## Q10.2 — `coroutineScope` vs `supervisorScope`

> **Builds on:** [Q10.1 — Job Hierarchy](#q101--the-job-hierarchy)
> **Connects to:** [Q10.3 — Exception Handling](#q103--exception-handling-rules) · [Q9.3 — async exception propagation](09_coroutines_execution_mechanics.md#q93--launch-vs-async)

---

### The Concrete Picture

```kotlin
// coroutineScope — ALL OR NOTHING:
coroutineScope {
    val a = async { downloadFile() }    // ok
    val b = async { loadConfig() }      // throws IOException!
    // b throws → b.childCancelled on coroutineScope returns false
    //           → coroutineScope cancels itself → cancels a → scope throws IOException
    a.await() + b.await()
}
// → IOException propagates to caller

// supervisorScope — EACH STANDS ALONE:
supervisorScope {
    val news    = async { fetchNews() }     // ok
    val weather = async { fetchWeather() }  // throws!
    val ads     = async { fetchAds() }      // ok
    // weather throws → SupervisorCoroutine.childCancelled returns false
    //                → weather job failed in isolation
    //                → news and ads continue normally
    buildList {
        try { addAll(news.await()) }    catch (e: Exception) { /* skip */ }
        try { add(weather.await()) }    catch (e: Exception) { /* skip */ }
        try { addAll(ads.await()) }     catch (e: Exception) { /* skip */ }
    }
}
```

**The single source-code difference:**

```kotlin
// ScopeCoroutine (coroutineScope) — uses base JobSupport.childCancelled:
//   CancellationException → true (absorbed)
//   Any other exception   → false (propagate → self-cancel)

// SupervisorCoroutine (supervisorScope) — one override:
private class SupervisorCoroutine<in T>(
    context: CoroutineContext,
    uCont: Continuation<T>
) : ScopeCoroutine<T>(context, uCont) {
    override fun childCancelled(cause: Throwable): Boolean = false
    // ← THIS IS THE ENTIRE DIFFERENCE — one boolean override
}
```

That single `override fun childCancelled` is the complete implementation difference. Everything else — waiting for children, cancellation propagating downward, exception re-throwing — is identical.

---

### When Does `supervisorScope` Itself Throw?

`supervisorScope` isolates **child** failures. It still throws in exactly two cases:

```kotlin
// Case 1: the SCOPE BODY itself throws (not a launched child coroutine):
supervisorScope {
    launch { throw RuntimeException("child — isolated, scope unaffected") }
    throw RuntimeException("scope body — DOES throw from supervisorScope")
    //   ↑ this is not a child failure, this is the scope coroutine itself failing
}
// → throws RuntimeException("scope body")

// Case 2: externally cancelled (parent scope cancelled):
val outer = CoroutineScope(Job())
outer.launch {
    supervisorScope {
        launch { delay(Long.MAX_VALUE) }
    }
}
outer.cancel()  // supervisorScope IS cancelled — downward cancellation still applies

// Does NOT throw when children fail:
supervisorScope {
    val a = async { throw RuntimeException("child failure") }
    val b = async { "b succeeded" }
    try { a.await() } catch (e: Exception) { println("caught: ${e.message}") }
    println(b.await())  // prints "b succeeded"
}
// → supervisorScope returns normally — no exception propagated from scope itself
```

```
supervisorScope throws: scope body fails | externally cancelled
supervisorScope does NOT throw: children fail (isolated)
```

---

### When to Use Which — Decision Table

| Situation | Scope | Reason |
|---|---|---|
| All sub-tasks must succeed for result | `coroutineScope` | Fail fast — no partial results |
| Sub-tasks are independent, partial success OK | `supervisorScope` | Isolate individual failures |
| Parallel data fetch where any missing piece = abort | `coroutineScope` | e.g., download + decrypt + save |
| Feed with news + weather + ads | `supervisorScope` | Weather failing ≠ news unavailable |
| ViewModel root scope | `SupervisorJob` | One failing coroutine ≠ broken ViewModel |

```kotlin
// coroutineScope — all-or-nothing:
suspend fun fetchAndParse(url: String): ParsedData = coroutineScope {
    val bytes  = async { downloadFile(url) }   // both must succeed
    val config = async { loadConfig() }
    parse(bytes.await(), config.await())
    // if either fails: both cancelled, coroutineScope throws
}

// supervisorScope — independent:
suspend fun loadFeedItems(): FeedData = supervisorScope {
    val news    = async { fetchNews() }
    val weather = async { fetchWeather() }
    val ads     = async { fetchAds() }
    FeedData(
        news    = runCatching { news.await() }.getOrNull(),
        weather = runCatching { weather.await() }.getOrNull(),
        ads     = runCatching { ads.await() }.getOrNull()
    )
    // any combination of success/failure acceptable
}
```

---

### Memory Trick

```
coroutineScope  = ALL OR NOTHING.
  Child fails → everything fails. Fail fast. Use when all parts must succeed.

supervisorScope = EACH STANDS ALONE.
  Child fails → that child fails alone. Use for independent parallel operations.

THE ONE DIFFERENCE:
  SupervisorCoroutine overrides childCancelled() to return false for ALL exceptions.
  ScopeCoroutine uses base: non-CE → false + self-cancels.

supervisorScope STILL throws when: scope BODY fails (not a child).
viewModelScope = SupervisorJob at root → one failing coroutine ≠ broken ViewModel.

async in coroutineScope → exception propagates IMMEDIATELY (not at await()). See Q9.3.
async in supervisorScope → exception truly contained until await().
```

### Self-Test

1. What is the single source-code difference between `coroutineScope` and `supervisorScope`? Show the actual method signature.
2. Three `async` blocks in `supervisorScope` — second one fails. What happens to first and third? Trace `childCancelled`.
3. `supervisorScope { throw RuntimeException() }` — does the scope throw? What about `supervisorScope { launch { throw RuntimeException() } }`?
4. You're loading a social feed with news, ads, and trending. Which scope? Justify.
5. *"Does `async { throw e }` in a `supervisorScope` only throw at `await()`?"* — Yes. Why does scope type change this behaviour?

---

## Q10.3 — Exception Handling Rules

> **Builds on:** [Q10.1 — Job Hierarchy](#q101--the-job-hierarchy) · [Q10.2 — supervisorScope](#q102--coroutinescope-vs-supervisorscope)
> **Connects to:** [Q4.3 — CancellationException in lambdas](04_functions_lambdas_inlining.md#q43--higher-order-functions-with-suspend) · [Q9.3 — try-catch around launch](09_coroutines_execution_mechanics.md#q93--launch-vs-async)

---

### Rule 1: `try-catch` Around `launch` Never Works (see Q9.3)

`launch` returns a `Job` immediately. The coroutine body runs later, on a different call stack. The exception travels via `childCancelled`, not JVM exception propagation.

```kotlin
// WRONG:
try {
    launch { throw RuntimeException("inside") }
} catch (e: RuntimeException) { /* NEVER fires */ }

// CORRECT options:
launch { try { riskyOp() } catch (e: IOException) { handle(e) } }  // inside
val handler = CoroutineExceptionHandler { _, e -> log(e) }
scope.launch(handler) { throw RuntimeException("root") }           // CEH (root only)
```

---

### Rule 2: `CoroutineExceptionHandler` — Root Coroutines Only

CEH is the last-resort handler for exceptions that have **fully propagated** through the hierarchy with no parent remaining to receive them.

```kotlin
val handler = CoroutineExceptionHandler { _, e -> log(e) }

// WORKS: root coroutine
scope.launch(handler) { throw RuntimeException("root") }
// Exception propagates, reaches root, no parent → CEH fires

// DOES NOT WORK: nested coroutine — handler is completely ignored
scope.launch {
    launch(handler) {         // handler on nested launch = IGNORED
        throw RuntimeException("nested")
        // propagates to parent scope.launch's Job, then up
        // CEH on nested launch never consulted
    }
}
```

**Why nested CEH is ignored:** The exception travels up via `childCancelled`. CEH is only consulted after the exception reaches the root coroutine with no parent — an intermediate handler in the hierarchy is never invoked. The `CoroutineExceptionHandler` is part of the context, but `childCancelled` does not check it — the framework only checks CEH at the final root level.

Decision tree for exception routing:

```
Child coroutine throws non-CancellationException
  │
  ▼
parent.childCancelled(exception)
  ├── SupervisorJob? → true → child fails alone, CEH NOT consulted
  └── Regular Job?  → false → parent cancels itself
                               │
                               ▼
                          parent's parent.childCancelled(exception)
                               │
                               ▼
                          ... propagates up the tree ...
                               │
                               ▼
                          Reaches root (no parent)?
                            ├── has CEH in context? → YES → CEH fires
                            └── no CEH             → Thread.uncaughtExceptionHandler
                                                     (crash on Android)
```

---

### Rule 3: `CancellationException` MUST Always Be Re-Thrown

`CancellationException` extends `IllegalStateException` which extends `Exception`. A `catch (e: Exception)` **will catch it**. If you swallow it, the coroutine ignores the cancellation signal and **keeps running** — a coroutine leak.

**Bytecode reality:** When `job.cancel()` is called, it sets the Job's state to `Cancelling` and throws `CancellationException` at the next suspension point via `resumeWithException`. This exception travels through the normal Kotlin `try-catch` mechanism on the coroutine's call stack. If a `catch (e: Exception)` eats it, the coroutine never observes that it was cancelled.

```kotlin
// WRONG — swallows CancellationException: coroutine becomes unkillable
launch {
    try {
        delay(Long.MAX_VALUE)  // CancellationException thrown here on cancel()
    } catch (e: Exception) {   // catches CancellationException!
        println("Caught, continuing...")
        // coroutine body continues despite job being cancelled → LEAK
    }
}
job.cancel()  // cancel flag set, but coroutine just keeps running
```

```kotlin
// CORRECT — re-throw CE explicitly:
launch {
    try {
        riskyOperation()
    } catch (e: CancellationException) {
        cleanup()
        throw e   // MUST re-throw — this is the cancellation signal
    } catch (e: IOException) {
        handleError(e)
    }
}

// CORRECT — catch only specific non-CE types (CE propagates naturally):
launch {
    try {
        riskyOperation()
    } catch (e: IOException) {
        // CancellationException is NOT IOException → propagates naturally → correct
    }
}
```

---

### ## Trap: `runCatching` Swallows `CancellationException`

`runCatching` internally calls `try { ... } catch (e: Throwable) { Result.failure(e) }`. It catches `CancellationException` and wraps it in `Result.failure` — the cancellation signal is silently swallowed.

```kotlin
// WRONG: runCatching swallows CE
suspend fun doWork(): Result<String> {
    return runCatching { fetchData() }
    // If fetchData() was cancelled → Result.failure(CancellationException)
    // CE is now wrapped in a Result — not re-thrown → coroutine keeps running
}
```

```kotlin
// CORRECT — check and re-throw CE after runCatching:
suspend fun doWork(): Result<String> {
    return runCatching { fetchData() }.also { result ->
        result.exceptionOrNull()?.let { e ->
            if (e is CancellationException) throw e  // re-throw CE
        }
    }
}

// CORRECT — retry logic with explicit CE re-throw:
suspend fun retryWithBackoff(action: suspend () -> Unit) {
    repeat(3) { attempt ->
        try {
            action()
            return
        } catch (e: CancellationException) {
            throw e              // NEVER retry a cancellation — re-throw immediately
        } catch (e: Exception) {
            delay(1000L * attempt)
        }
    }
}
```

---

### Rule 4: Tight CPU Loop — Cooperative Cancellation

Coroutines use **cooperative** cancellation. A tight loop with no suspension points will never observe the cancellation flag:

```kotlin
// WRONG: never cancels
launch(Dispatchers.Default) {
    var count = 0
    while (true) { count++ }  // no suspend call → CancellationException never thrown
}
job.cancel()  // sets cancel flag on the Job, but the loop never checks it
// This coroutine runs FOREVER — a true coroutine leak
```

**Three fixes — different trade-offs:**

```kotlin
// Fix 1: isActive — check flag, branch, no throw, no yield
while (isActive) { count++ }
// Use when: tight loop where you control the exit logic manually

// Fix 2: yield() — suspend + yield thread to scheduler + check cancellation
while (true) { count++; yield() }
// Use when: also want to give other coroutines a turn on the dispatcher

// Fix 3: ensureActive() — check flag + throw CE immediately if cancelled, no yield
while (true) { ensureActive(); count++ }
// Use when: want explicit throw at cancellation point, no yield
```

| Method | Suspends? | Yields thread? | On cancelled: | Use when |
|---|---|---|---|---|
| `isActive` | No | No | Returns `false`, you branch | Control loop condition manually |
| `yield()` | Yes | Yes | Throws `CancellationException` | Also give other coroutines CPU time |
| `ensureActive()` | No | No | Throws `CancellationException` | Just check + throw, no yield |

---

### Memory Trick

```
CEH = LAST RESORT, root coroutines ONLY.
  Nested launch(handler) { } → handler IGNORED. Exception propagates to parent.
  CEH checked ONLY after exception bubbles to root with no parent.

CancellationException:
  extends IllegalStateException → extends Exception
  catch(Exception) CATCHES IT → coroutine becomes unkillable → LEAK
  ALWAYS: catch(CE) { cleanup(); throw e }
  OR: catch only specific types (IOException) → CE propagates naturally

runCatching:
  internally: catch(Throwable) → wraps ALL exceptions including CE.
  Fix: result.exceptionOrNull()?.let { if (it is CE) throw it }
  NEVER retry CE — always re-throw immediately.

try-catch INSIDE launch  → works (same call stack as the throw)
try-catch AROUND launch  → NEVER works (different call stacks — exception via childCancelled)

TIGHT CPU LOOP needs cooperative cancellation:
  isActive       → Boolean check, no suspend, manual exit
  yield()        → suspend + yield thread + throw CE if cancelled
  ensureActive() → throw CE if cancelled, no suspend, no yield
```

### Key Takeaways — Q10.3

| Concept | Fact |
|---|---|
| `CoroutineExceptionHandler` | Root coroutines only; nested: ignored, exception propagates to parent |
| `CancellationException` | Must ALWAYS be re-thrown; `catch(Exception)` swallows it |
| `runCatching` trap | Wraps CE in `Result.failure` — check `exceptionOrNull` and re-throw |
| Tight CPU loop | Cooperative: must call `yield()`, `ensureActive()`, or check `isActive` |
| `try-catch` inside launch | Works — same call stack |
| `try-catch` around launch | Never works — exception travels via `childCancelled`, not JVM throw |

### Self-Test

1. Why doesn't `CoroutineExceptionHandler` fire for a nested `launch`? Trace the exception routing.
2. `catch (e: Exception)` catches `CancellationException`. Show the failing code and both correct patterns.
3. Why does `runCatching` need special treatment for `CancellationException`? What does it do internally?
4. Three ways to make a tight CPU loop respect cancellation — what are the concrete differences between `isActive`, `yield()`, and `ensureActive()`?
5. *"Can I use `CoroutineExceptionHandler` to recover from exceptions?"* — What is the answer? (Hint: what does "last resort" mean?)

---

## Q10.4 — Lifecycle Scopes and Process Death

> **Builds on:** [Q10.1 — Job Hierarchy](#q101--the-job-hierarchy) · [Q9.2 — Dispatchers](09_coroutines_execution_mechanics.md#q92--coroutine-context-and-dispatchers)
> **Connects to:** [Q11.4 — Flow collection with lifecycle](11_flow.md#q114--flow-collection-and-lifecycle)

---

### `viewModelScope` Internals

```kotlin
// viewModelScope is created approximately as:
val viewModelScope = CloseableCoroutineScope(
    SupervisorJob() + Dispatchers.Main.immediate
)
// cancelled in ViewModel.clear() → calls viewModelScope.close() → cancels SupervisorJob
```

**`SupervisorJob()`:** Children are independent. A failing network call doesn't cancel all other ViewModel work. This is the correct default — ViewModels typically launch logically unrelated coroutines.

**`Dispatchers.Main.immediate`:** ViewModel coroutines often update `StateFlow` or `LiveData` from Main. `Main.immediate` skips the `Handler.post()` round-trip if already on Main — the update happens synchronously inline, not queued. Avoids the one-frame-later UI update latency.

**Cancellation mechanism:** `ViewModel.onCleared()` calls `clear()` → `closeables.forEach { it.close() }` → `viewModelScope` is in `closeables` → `cancel()` called on `SupervisorJob` → all child coroutines receive `CancellationException`.

---

### Rotation vs Process Death

```
ROTATION (configuration change):
  Activity destroyed
  → ActivityThread retains NonConfigurationInstances (in-memory object)
  → NonConfigurationInstances holds ViewModelStore
  → ViewModelStore holds all ViewModel objects
  → new Activity instance created → same ViewModelStore attached
  → same ViewModel objects, onCleared() NOT called
  → viewModelScope NOT cancelled → coroutines KEEP RUNNING

PROCESS DEATH (OS kills app due to memory pressure or system restart):
  Entire Linux process killed (SIGKILL)
  → ALL memory gone — heap, stack, everything
  → App relaunched → new process → new Application → new Activity
  → new ViewModelStore → new ViewModel instances
  → viewModelScope starts fresh — no surviving coroutines
  → SavedStateHandle is the ONLY bridge to pre-death UI state
```

**The exact survival boundary:**

```
ViewModel survives: rotation, go home + come back (app in back stack, process alive)
ViewModel dies:     process death, finish(), navigating back (activity removed from back stack)
```

---

### ## Trap: `lifecycleScope.launch { collect }` — Always Running

```kotlin
// WRONG — collection never stops in background:
lifecycleScope.launch {
    viewModel.uiState.collect { state ->
        updateUI(state)   // called even when Activity is STOPPED (not visible)
    }
}
// lifecycleScope is only cancelled on DESTROY — not on STOP
// While app is in background (STOPPED): collect still runs, updateUI called
// → Wasted CPU/battery, potential stale state, possible view crash
```

```kotlin
// CORRECT — collection pauses on STOP, restarts on START:
lifecycleScope.launch {
    repeatOnLifecycle(Lifecycle.State.STARTED) {
        viewModel.uiState.collect { state ->
            updateUI(state)   // ONLY called when Activity is at least STARTED (visible)
        }
    }
}
```

**How `repeatOnLifecycle(STARTED)` works mechanically:**

```
Lifecycle: CREATED ──► STARTED ──► RESUMED ──► PAUSED ──► STOPPED ──► STARTED ──► ...
                           │                               │              │
repeatOnLifecycle(STARTED): launches inner coroutine    cancels inner   launches new
                            (collect begins)            (collect stops)  inner coroutine
```

Each time the lifecycle reaches `STARTED`, a new coroutine is launched with the provided block. Each time it drops below `STARTED`, that coroutine is cancelled. The outer coroutine (the `repeatOnLifecycle` call itself) lives as long as the `lifecycleScope` (until `DESTROY`).

---

### ## Trap: Fragment `this.lifecycleScope` vs `viewLifecycleOwner.lifecycleScope`

A Fragment has **two distinct lifecycles**. This is the source of the most common Fragment crash pattern.

**Fragment lifecycle:** from `onAttach()` to `onDetach()`. The Fragment object exists.
**Fragment view lifecycle:** from `onCreateView()` to `onDestroyView()`. The Fragment's views exist.

When a Fragment is on the **back stack** (navigated away from):
- Fragment lifecycle: **ALIVE** (Fragment object retained in back stack)
- Fragment view lifecycle: **DESTROYED** (views cleaned up to save memory)

```kotlin
// WRONG — uses Fragment's OWN lifecycle:
override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
    lifecycleScope.launch {   // ← Fragment.lifecycleScope = Fragment's lifecycle
        repeatOnLifecycle(Lifecycle.State.STARTED) {
            // This can execute when Fragment is on the back stack:
            // Fragment lifecycle is STARTED, but views are DESTROYED
            binding.textView.text = "update"  // → NullPointerException or view reference leak
        }
    }
}

// CORRECT — uses the VIEW lifecycle:
override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
    viewLifecycleOwner.lifecycleScope.launch {    // ← VIEW lifecycle
        viewLifecycleOwner.repeatOnLifecycle(Lifecycle.State.STARTED) {
            viewModel.uiState.collect { state ->
                binding.textView.text = state.text  // safe — views exist here
            }
        }
    }
}
// viewLifecycleOwner.lifecycle is DESTROYED on onDestroyView()
// → inner coroutine cancelled → binding never touched after views destroyed
```

```
Fragment back stack scenario:
  Navigate to FragB from FragA
  → FragA.onDestroyView() called → binding = null
  → FragA.viewLifecycleOwner.lifecycle → DESTROYED → coroutine cancelled ✓
  → FragA.lifecycle → still STARTED (fragment alive in back stack)

  Using Fragment.lifecycleScope → coroutine still running → binding.textView = NullPointerException
  Using viewLifecycleOwner.lifecycleScope → coroutine cancelled on onDestroyView → safe
```

`viewLifecycleOwner` is only valid between `onCreateView()` and `onDestroyView()`. Never access it in `onCreate()` or `onAttach()` — it is `null` before `onCreateView()`.

---

### `SavedStateHandle` — Surviving Process Death

```kotlin
@HiltViewModel
class SearchViewModel @Inject constructor(
    private val savedStateHandle: SavedStateHandle
) : ViewModel() {
    // Read/write like a typed map:
    var query: String
        get() = savedStateHandle["query"] ?: ""
        set(value) { savedStateHandle["query"] = value }

    // Or observe as StateFlow:
    val queryFlow: StateFlow<String> = savedStateHandle.getStateFlow("query", "")
}
```

**Survival chain — how values cross process death:**

```
ViewModel writes SavedStateHandle["query"] = "kotlin"
  │
  ▼ SavedStateHandle is backed by a Bundle via SavedStateRegistry
  │
  ▼ Activity.onSaveInstanceState(Bundle outState) called by OS before kill
  │   → SavedStateRegistry serialises all registered handles into outState Bundle
  │
  ▼ OS kills process (SIGKILL)
  │
  ▼ User returns — OS relaunches process with saved Bundle
  │
  ▼ Activity.onCreate(savedInstanceState: Bundle?)
  │   → SavedStateRegistry restores from Bundle
  │   → SavedStateHandle populated with ["query" = "kotlin"]
  │
  ▼ New ViewModel created → SavedStateHandle injected with restored data
  │
  ▼ queryFlow emits "kotlin" → UI restored
```

**Constraints — what you can and cannot store:**

```kotlin
// CAN store (Parcelable/Serializable or primitive types):
savedStateHandle["query"]  = "kotlin"           // String — fine
savedStateHandle["page"]   = 3                  // Int — fine
savedStateHandle["filter"] = FilterState(...)   // custom @Parcelize class — fine

// CANNOT store:
savedStateHandle["bitmap"]  = largeBitmap        // Bitmap — too large, Binder limit crash
savedStateHandle["list"]    = listOf(10_000_items) // too large — ~1MB Binder limit
savedStateHandle["stream"]  = inputStream        // not Parcelable — won't compile/crash
```

Size constraint: ~1MB Binder transaction limit for the entire `Bundle`. Exceeding it causes `TransactionTooLargeException` on restore. For large state, use `Room` or `DataStore`.

---

### Memory Trick

```
viewModelScope = SupervisorJob() + Dispatchers.Main.immediate
  SupervisorJob  → independent coroutines (one fails ≠ all cancelled)
  Main.immediate → inline on Main (no Handler queue round-trip if already on Main)
  Cancelled via ViewModel.clear() → onCleared()

ROTATION → NonConfigurationInstances (in-memory object bridge)
           ViewModel NOT destroyed → viewModelScope NOT cancelled → coroutines continue

PROCESS DEATH → entire Linux process SIGKILL → all memory gone
           ViewModel dies → SavedStateHandle ONLY bridge
           SavedStateHandle → Bundle → onSaveInstanceState → ActivityManager stores it
           Constraints: Parcelable/primitive only, ~1MB limit

lifecycleScope.launch { collect } = always running even in background. WRONG.
repeatOnLifecycle(STARTED) { collect } = pauses on STOP, restarts on START. CORRECT.

FRAGMENT TWO LIFECYCLES:
  Fragment lifecycle:      onAttach → onDetach (object exists)
  Fragment VIEW lifecycle: onCreateView → onDestroyView (views exist)
  Back stack: Fragment alive, views DESTROYED.
  ALWAYS use viewLifecycleOwner.lifecycleScope for any view-touching coroutine.
  Fragment.lifecycleScope in onViewCreated → crash when navigating back.
```

### Key Takeaways — Q10.4

| Concept | Fact |
|---|---|
| `viewModelScope` | `SupervisorJob() + Dispatchers.Main.immediate`; cancelled on `onCleared()` |
| Rotation | ViewModel survives via in-memory `NonConfigurationInstances` |
| Process death | ViewModel dies (entire process killed); `SavedStateHandle` is the bridge |
| `repeatOnLifecycle(STARTED)` | Cancels block on STOP, restarts on START — pauses in background |
| Fragment `viewLifecycleOwner` | VIEW lifecycle: `onCreateView` to `onDestroyView` (NOT Fragment lifecycle) |
| `SavedStateHandle` | Bundle-backed, survives process death, Parcelable/primitive only, ~1MB limit |

### Self-Test

1. `viewModelScope` — what Job type and Dispatcher? Why those specific choices?
2. ViewModel survives rotation. Does it survive process death? Explain the mechanism for each case.
3. What is the bug in `lifecycleScope.launch { flow.collect { } }`? What is the correct pattern?
4. A Fragment is on the back stack. Which lifecycle is alive — Fragment lifecycle or view lifecycle? Which one is destroyed?
5. Why must you use `viewLifecycleOwner.lifecycleScope` instead of `lifecycleScope` in `onViewCreated`? Show the crash scenario.
6. `SavedStateHandle` — what types can it store? What is the size constraint and what exception do you get on violation?

---

## Q10.5 — `select` Expression

> **Builds on:** [Q10.1 — Job Hierarchy](#q101--the-job-hierarchy) · [Q9.3 — Deferred](09_coroutines_execution_mechanics.md#q93--launch-vs-async)
> **Connects to:** [Q11.2 — Flow operators](11_flow.md#q112--flow-operators)

---

### What `select` Does

`select` waits for the **first** of multiple suspending operations to become available, then executes its handler block:

```kotlin
val result = select<String> {
    async { fetchFromCache() }.onAwait  { "cache: $it" }
    async { fetchFromNetwork() }.onAwait { "network: $it" }
}
// result = handler block of whichever Deferred completed first
// BOTH async blocks are still running after select picks a winner!
// You must cancel the loser yourself — select does NOT do it for you.
```

**Common clauses:**

| Clause | Fires when |
|---|---|
| `deferred.onAwait { }` | Deferred completes (success or failure) |
| `channel.onReceive { }` | Element available in channel |
| `channel.onSend(v) { }` | Channel accepts a send |
| `onTimeout(ms) { }` | Timeout elapses first |

---

### Bias Toward First Clause

If multiple clauses are simultaneously ready, `select` picks the **first one declared** — deterministically, not randomly. This is because `select` scans clauses in declaration order when registering, and if any is immediately available, that one wins.

```kotlin
select<String> {
    deferredA.onAwait { "A wins" }   // ← always wins if both ready simultaneously
    deferredB.onAwait { "B wins" }
}
// Put the preferred source first: cache before network, primary before fallback
```

---

### ## Trap: Losers Are NOT Auto-Cancelled — Resource Leak

```kotlin
// WRONG — the losing async continues running, result goes unobserved:
val result = select<String> {
    async { fetchFromCache() }.onAwait  { it }
    async { fetchFromNetwork() }.onAwait { it }
}
// Cache wins → network async still running, result never used → resource waste / leak
```

```kotlin
// CORRECT — cancel losers explicitly inside the handler:
coroutineScope {
    val cacheD   = async { fetchFromCache() }
    val networkD = async { fetchFromNetwork() }

    val result = select<String> {
        cacheD.onAwait { value ->
            networkD.cancel()   // cache won → cancel network
            value
        }
        networkD.onAwait { value ->
            cacheD.cancel()     // network won → cancel cache
            value
        }
    }
    // both Deferreds are now either completed or cancelled — no leaks
}
```

---

### Memory Trick

```
select = FIRST READY clause wins → executes its handler block.
Bias: multiple simultaneously ready → FIRST declared clause wins (scan order, deterministic).
Losers NOT cancelled automatically → cancel in the handler to prevent leaks.

Clauses: onAwait (Deferred), onReceive / onSend (Channel), onTimeout.

vs withTimeoutOrNull:
  withTimeoutOrNull(ms) { ... }  = single operation with timeout.
  select { op.onAwait { }; onTimeout(ms) { null } } = same but composable with other clauses.
```

---

## Q10.6 — Mutex and Synchronization Primitives

> **Builds on:** [Q9.2 — Dispatchers](09_coroutines_execution_mechanics.md#q92--coroutine-context-and-dispatchers) · [Q9.1 — suspend mechanics](09_coroutines_execution_mechanics.md#q91--what-suspend-actually-does)
> **Connects to:** [Q15.2 — Token Refresh Pattern](15_networking.md#q152--token-refresh-pattern)

---

### The Problem — Race Conditions in Coroutines

```kotlin
// WRONG: counter++ is NOT atomic — it is three bytecode instructions
var counter = 0
repeat(1000) { launch { counter++ } }
// counter++ compiles to:
//   ILOAD counter    ← read current value (e.g., 42)
//   ICONST_1
//   IADD             ← add 1 in register (= 43)
//   ISTORE counter   ← write back (= 43)
// Two coroutines both read 42, both write 43 → one increment lost
// Final counter: unpredictable, always < 1000
```

---

### `@Volatile` — JVM `ACC_VOLATILE` Flag

**What it guarantees:** Every write to the field is immediately flushed to main memory. Every read fetches from main memory. No CPU cache inconsistency — all threads see the most recent write.

**What it does NOT guarantee:** Atomicity of compound operations (read-modify-write).

**Bytecode:** `@Volatile` maps to the JVM `ACC_VOLATILE` access flag on the field descriptor:

```java
// Decompiled Java equivalent of @Volatile var running: Boolean = true
@Volatile
private volatile boolean running = true;  // JVM: field descriptor has ACC_VOLATILE flag
```

The JVM spec guarantees that reads/writes to `volatile` fields have happens-before ordering — but only for individual reads and writes, not for compound operations.

```kotlin
@Volatile var running = true       // ✓ Every thread sees the latest value immediately
@Volatile var counter = 0
counter++                          // ✗ Still a race: read (volatile), add, write (volatile)
                                   //   Two threads can both read 42, both write 43
```

Use `@Volatile` only for simple flag variables where you **never** do read-modify-write operations.

---

### `AtomicInteger` — CAS-Backed Single-Variable Atomicity

```kotlin
val counter = AtomicInteger(0)
counter.incrementAndGet()   // atomic: hardware CAS (compare-and-swap) instruction
```

**How CAS works at the CPU level:**

```
CPU instruction: CMPXCHG (x86) / LDXR+STXR (ARM)
  1. Read current value (e.g., 42)
  2. Compute new value (43)
  3. Atomically: IF memory still == 42, THEN write 43 (returns success)
                 IF memory != 42 (another thread changed it), retry loop
  Result: exactly one increment per call, no lost updates
```

**CAS only covers a single memory location.** Two `AtomicInteger`s together are NOT atomic:

```kotlin
val a = AtomicInteger(0)
val b = AtomicInteger(0)

// Each individual op is atomic, but together they are NOT:
a.incrementAndGet()   // atomic: a becomes 1
                      // ← another thread can observe a=1, b=0 here
b.decrementAndGet()   // atomic: b becomes -1

// Invariant "a + b == 0" can be violated between the two atomic ops
```

---

### `Mutex` — Coroutine-Native Mutual Exclusion

`Mutex` allows only one coroutine at a time in the critical section. Unlike `synchronized`, waiting coroutines **suspend** (thread freed) instead of blocking (thread parked by OS):

```kotlin
val mutex = Mutex()
var counter = 0

repeat(1000) {
    launch {
        mutex.withLock {
            counter++   // only ONE coroutine executes this at a time — safe
        }
    }
}
```

**Why `suspend` vs block matters:**

```
synchronized { counter++ }   → JVM monitor: WAITING thread is BLOCKED
                               OS parks the thread — it sits idle, consuming a thread slot
                               On a 4-thread pool: 4 waiting coroutines = pool exhausted

mutex.withLock { counter++ } → coroutine SUSPENDED: thread returned to dispatcher
                               same 4-thread pool can service hundreds of waiting coroutines
                               waiting coroutine consumes a Continuation object, not a thread
```

**`withLock` uses `try/finally` — bytecode guarantee:**

```java
// Decompiled Java equivalent of mutex.withLock { body() }:
mutex.lock();           // or: lockSuspend() — suspending version
try {
    body();
} finally {
    mutex.unlock();     // ALWAYS called — even if body() throws, even if cancelled
}
```

This is why you **always** use `withLock` — the `finally` block guarantees the lock is released even on exception or cancellation. Manual `lock()`/`unlock()` loses this guarantee:

```kotlin
// WRONG — exception between lock and unlock → mutex held forever → DEADLOCK:
mutex.lock()
riskyOperation()  // throws IOException
mutex.unlock()    // NEVER reached → mutex is permanently locked → all waiters stuck forever

// CORRECT — withLock wraps in try/finally → always released:
mutex.withLock { riskyOperation() }  // unlock in finally → always happens
```

---

### Deadlock Prevention

Deadlock: coroutine A holds lock 1, tries to acquire lock 2; coroutine B holds lock 2, tries to acquire lock 1 → both suspended forever, waiting for each other.

```kotlin
// DEADLOCK-PRONE — inconsistent acquisition order:
launch { mutexA.withLock { mutexB.withLock { doWork() } } }  // A then B
launch { mutexB.withLock { mutexA.withLock { doWork() } } }  // B then A
// First launch holds A, waits for B.
// Second launch holds B, waits for A.
// Both suspended forever — deadlock.

// SAFE — consistent acquisition order:
launch { mutexA.withLock { mutexB.withLock { doWork() } } }  // A then B
launch { mutexA.withLock { mutexB.withLock { doWork() } } }  // A then B — same order
// First launch holds A, gets B, does work, releases.
// Second launch waits for A (not B), then proceeds — no circular wait.
```

**Prevention rule:** Always acquire multiple locks in the same fixed global order. A canonical ordering (e.g., by object identity: `System.identityHashCode`) ensures no circular dependency.

---

### `Semaphore` — Limiting Concurrent Access to N

`Mutex` = `Semaphore(1)`. `Semaphore(N)` allows N coroutines concurrently:

```kotlin
val semaphore = Semaphore(3)  // at most 3 coroutines in critical section at once

suspend fun fetchWithLimit(url: String): String {
    return semaphore.withPermit {
        networkClient.get(url)  // at most 3 simultaneous network requests
    }
}
// 4th caller → suspends (thread freed) until one of the 3 finishes and releases permit
```

Use `Semaphore` for: rate limiting API calls, limiting DB connections, throttling heavy background work, implementing connection pools.

---

### Summary Table

| Tool | JVM/bytecode mechanism | Guarantees | When to Use |
|---|---|---|---|
| `@Volatile` | `ACC_VOLATILE` field flag | Visibility (no CPU cache) | Simple flag, never read-modify-write |
| `AtomicInteger` | CAS (CMPXCHG/LDXR+STXR) | Atomic single-variable ops | Counter, single int/long |
| `Mutex.withLock` | Coroutine suspension queue | Mutual exclusion, any block | Multiple vars, compound ops |
| `synchronized` | JVM monitor (MONITORENTER) | Mutual exclusion, blocks thread | Non-coroutine code only |
| `Semaphore(N)` | N-permit suspension queue | At most N concurrent | Rate limiting, connection pools |

---

### Memory Trick

```
@Volatile → ACC_VOLATILE JVM field flag → CPU cache flush on write/read.
  Guarantees: visibility only. flag = true seen by ALL threads immediately.
  Does NOT guarantee: atomicity. flag++ is still 3 bytecode ops → race.

AtomicInteger → CAS (compare-and-swap) CPU instruction. Single memory location.
  incrementAndGet() = one atomic hardware op → no lost updates.
  Two AtomicIntegers together = NOT atomic (gap between the two CAS ops).

Mutex.withLock → coroutine SUSPENDS while waiting (thread freed, not wasted).
  withLock = try { lock } finally { unlock } → ALWAYS released even on exception/cancel.
  NEVER manual lock()/unlock() → exception between them = permanent deadlock.

Deadlock: A holds 1, waits 2; B holds 2, waits 1 → circular wait → suspended forever.
  Prevention: always acquire locks in SAME fixed global order.

Semaphore(N) = Mutex but N concurrent. Semaphore(1) == Mutex.
  Use for: rate limiting, connection pools, throttling.
```

### Self-Test

1. `@Volatile` — what JVM bytecode flag does it compile to? What does it guarantee? What does it NOT guarantee? Show a race that `@Volatile` does NOT fix.
2. Why is `AtomicInteger.incrementAndGet()` not enough when you have two related atomic variables?
3. `Mutex` vs `synchronized` — what is the fundamental difference in how a waiting coroutine behaves?
4. Why must you always use `withLock` instead of manual `lock()`/`unlock()`? Show the deadlock scenario.
5. How do you prevent deadlock when you need to acquire two mutexes? State the prevention rule.
6. You need to limit concurrent API calls to 5 at a time. What primitive do you use?

---

## Master Follow-Up Chains — Phase 10

```
Chain F (Cancellation → Lifecycle):
  CancellationException must be re-thrown ← catch(Exception) swallows it
    └─► runCatching wraps CE → re-check exceptionOrNull or it leaks
         └─► tight CPU loop: cooperative cancellation via isActive/yield/ensureActive
              └─► viewModelScope SupervisorJob: one child failure ≠ scope cancelled
                   └─► viewModelScope cancelled on onCleared() → all children cancelled (Invariant 2)
                        └─► repeatOnLifecycle: correct lifecycle-aware collection
                             └─► viewLifecycleOwner for Fragments (two separate lifecycles)

Chain H (Structured Concurrency):
  GlobalScope = no parent → breaks all 3 invariants → ALWAYS a leak risk
    └─► viewModelScope SupervisorJob: children independent
         └─► childCancelled returns false → sibling isolation
              └─► CEH: root only, nested ignored, last resort after full hierarchy traversal
                   └─► async exception in coroutineScope → IMMEDIATELY (not at await())
                        └─► async exception in supervisorScope → contained until await()
                             └─► awaitAll vs sequential await → orphaned coroutine risk

Chain E (ViewModel → Process Death):
  ViewModel survives rotation (NonConfigurationInstances — in-memory object bridge)
    └─► ViewModel does NOT survive process death (SIGKILL — all memory gone)
         └─► SavedStateHandle → Bundle → onSaveInstanceState → ActivityManager
              └─► Bundle ~1MB Binder limit → TransactionTooLargeException if exceeded
                   └─► Room/DataStore for large persistent state
```

---

*← [Phase 9 — Coroutines: Execution Mechanics](09_coroutines_execution_mechanics.md) | [Phase 11 — Flow →](11_flow.md)*