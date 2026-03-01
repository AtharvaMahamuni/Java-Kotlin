# Phase 10: Structured Concurrency

## Navigation
| Phase | File |
|-------|------|
| 00 | JVM Mental Model |
| 01 | Type System Foundations |
| 02 | Classes and Objects |
| 02.5 | Initialization and Construction Mechanics |
| 03 | Generics and Variance |
| 04 | Functions, Lambdas, and Inlining |
| 05 | Properties and Delegation |
| 06 | Extension Functions |
| 07 | Collections and Sequences |
| 08 | Other Kotlin Features |
| 09 | [Coroutines — Execution Mechanics](./09_coroutines_execution_mechanics.md) |
| **10** | **Structured Concurrency (THIS FILE)** |
| 11 | Flow |
| 12 | Reference Operators and Reflection |
| 13 | Android Architecture |
| 14 | Jetpack Components |
| 15 | Networking |
| 16 | Android System Internals |
| 17 | Performance and Memory |
| master | Master Follow-Up Chains |

**Cross-references in this file:**
- Builds on: Q9.1 (CPS / state machine), Q9.3 (launch vs async), Q4.3 (CancellationException re-throw)
- Leads to: Q11 (Flow collection and lifecycle), Q13 (MVVM and ViewModel), Q17.1 (GlobalScope memory leak)

---

## 10.1 The Job Hierarchy

### The Tree Structure of Coroutine Jobs

Every coroutine has a `Job` object. When a coroutine is launched inside a scope, it becomes a **child** of the scope's Job. This forms a tree:

```
CoroutineScope.coroutineContext[Job]  ← root Job (e.g., SupervisorJob in viewModelScope)
         │
         ├── Job (child coroutine: launch { })
         │       │
         │       ├── Job (grandchild: launch { } inside the child)
         │       │
         │       └── Job (grandchild: async { } inside the child)
         │
         └── Job (child coroutine: async { })
                 │
                 └── Job (grandchild: launch { } inside async)
```

Each `Job` holds references to its parent and its children. The runtime traverses this tree during cancellation and exception propagation.

---

### The Three Invariants of Structured Concurrency

These are the three guarantees that make structured concurrency work:

**Invariant 1: A parent waits for all its children to complete.**

A parent `Job` does not transition to `Completed` state until every single child `Job` has completed (either successfully, with cancellation, or with failure that was handled). You never "lose" a coroutine — it is always tracked by its parent.

```kotlin
coroutineScope {
    launch { delay(1000); println("child 1") }
    launch { delay(2000); println("child 2") }
    // coroutineScope does NOT return until both launches are done
}
println("Both children finished") // printed after t=2000ms
```

**Invariant 2: Cancelling a parent cancels all its children.**

Cancellation flows **downward** through the tree. When you cancel a parent Job, every descendant is cancelled.

```kotlin
val scope = CoroutineScope(SupervisorJob())
val parent = scope.launch {
    val child1 = launch { delay(Long.MAX_VALUE); println("child1") }
    val child2 = launch { delay(Long.MAX_VALUE); println("child2") }
}
parent.cancel()
// child1 and child2 are both cancelled — "child1" and "child2" never print
```

**Invariant 3: An unhandled exception in a child cancels the parent (and by extension, all siblings).**

Exceptions flow **upward** through the tree. When a child fails with a non-`CancellationException`, it cancels its parent, which cancels all other children.

```kotlin
coroutineScope {
    launch { throw RuntimeException("I failed") } // ← upward propagation
    launch { delay(Long.MAX_VALUE) }              // ← cancelled as sibling
}
// coroutineScope itself throws RuntimeException
```

The exception direction:
```
Downward (cancellation):
  Parent cancelled ──► children cancelled ──► grandchildren cancelled

Upward (exceptions):
  Grandchild fails ──► parent cancelled ──► sibling grandchildren cancelled
                   └──► grandparent cancelled ──► ...
```

---

### `childCancelled(cause: Throwable): Boolean` — The Core Mechanism

`childCancelled` is an internal method in `JobSupport` (the base implementation of `Job`) that is called when a child coroutine fails. It is the single decision point for whether exception propagation continues upward.

**Return value semantics:**

```
childCancelled() returns true:
    "I handled this failure myself — do NOT propagate it further up to MY parent."
    The failure stops here. My parent is unaffected.

childCancelled() returns false:
    "I did NOT handle this failure — propagate it up to my parent."
    The failure continues upward. My parent will receive it.
```

**`CoroutineScope` (regular scope / `coroutineScope { }`):**

```kotlin
// JobImpl / ScopeCoroutine: returns false → propagate upward
override fun childCancelled(cause: Throwable): Boolean {
    if (cause is CancellationException) return true // cancel silently
    return false // non-cancellation exception: propagate up
}
```

Regular scopes propagate non-`CancellationException` failures upward. This is why `coroutineScope { }` throws when a child fails.

**`SupervisorJob` / `supervisorScope { }`:**

```kotlin
// SupervisorCoroutine: returns true → absorb, don't propagate
override fun childCancelled(cause: Throwable): Boolean {
    return false // ALSO returns false? Wait—read carefully below
}
```

Actually, the key distinction is in how `SupervisorJob` overrides the propagation of exceptions. In the source code of `SupervisorJob`:

```kotlin
// SupervisorJob overrides childCancelled to NOT cancel itself
// when a child fails. The child's failure is isolated.
private class SupervisorJobImpl(parent: Job?) : JobImpl(parent) {
    override fun childCancelled(cause: Throwable): Boolean = false
    // Returns false = "I don't handle it either"
    // BUT SupervisorJob also does NOT cancel siblings or itself
    // The child job is simply removed from the tree without propagating.
}
```

The real mechanism: `SupervisorJob.childCancelled` returns `false` in a way that means "let the child fail independently." Because the supervisor does not call `cancel()` on itself in response to child failure, siblings are unaffected.

The practical summary (interview-level):

```
Regular Job / coroutineScope:
    child fails ──► childCancelled(cause) called on parent
                ──► parent cancels itself
                ──► parent cancels all other children (siblings)
                ──► parent's parent receives failure

SupervisorJob / supervisorScope:
    child fails ──► childCancelled(cause) called on parent
                ──► parent does NOT cancel itself
                ──► siblings continue running
                ──► parent's parent does NOT receive failure
```

---

### CancellationException vs Non-Cancellation Exceptions

`CancellationException` is special in the coroutine framework:

```kotlin
sealed class JobCancellationException : CancellationException()
```

When a child is cancelled (normal lifecycle event), it throws `CancellationException`. This is treated as a normal part of the structured concurrency lifecycle — it does NOT count as a failure. The parent ignores it (does not fail because a child was cancelled).

```
Child throws CancellationException:
    ──► parent.childCancelled(CancellationException)
    ──► parent treats this as: "child ended normally (was cancelled)"
    ──► no upward propagation of failure
    ──► other siblings unaffected

Child throws RuntimeException (or any non-CancellationException):
    ──► parent.childCancelled(RuntimeException)
    ──► parent treats this as: "child FAILED unexpectedly"
    ──► (with regular Job) parent cancels itself and siblings
    ──► failure propagates upward
```

---

### Key Takeaways — 10.1

| Concept | Fact |
|---------|------|
| Job tree | Every coroutine's Job is a child of its scope's Job |
| Invariant 1 | Parent waits for all children |
| Invariant 2 | Cancelling parent cancels all children (downward) |
| Invariant 3 | Child exception cancels parent and siblings (upward, unless SupervisorJob) |
| `childCancelled` | True = absorb (SupervisorJob); False = propagate (regular Job) |
| `CancellationException` | Normal lifecycle event, never propagates as failure |

---

## 10.2 `coroutineScope` vs `supervisorScope`

### The One Source-Code-Level Difference

`coroutineScope { }` creates a `ScopeCoroutine`. `supervisorScope { }` creates a `SupervisorCoroutine`.

The **one** difference between them:

```kotlin
// ScopeCoroutine (regular coroutineScope):
internal open class ScopeCoroutine<in T>(
    context: CoroutineContext,
    uCont: Continuation<T>
) : AbstractCoroutine<T>(context, true, true), CoroutineScope {
    override val isScopedCoroutine: Boolean get() = true
    // Uses the DEFAULT childCancelled from JobSupport:
    // child failure → cancels this scope → propagates up
}

// SupervisorCoroutine (supervisorScope):
private class SupervisorCoroutine<in T>(
    context: CoroutineContext,
    uCont: Continuation<T>
) : ScopeCoroutine<T>(context, uCont) {
    // THE ONE DIFFERENCE:
    override fun childCancelled(cause: Throwable): Boolean = false
    // Child failure does NOT cancel this scope
    // Other children continue running
}
```

That single override of `childCancelled` is what separates the two. Everything else — how they wait for children, how they propagate their own cancellation downward, how they handle their own exceptions — is identical.

---

### When Does `supervisorScope` Itself Throw?

`supervisorScope` isolates **child** failures, but it still throws in two cases:

**Case 1: The scope's own body (not a child) throws.**

```kotlin
supervisorScope {
    launch { throw RuntimeException("child — isolated") } // does NOT affect scope
    throw RuntimeException("scope body failed") // DOES throw from supervisorScope
}
// supervisorScope throws RuntimeException from scope body
```

**Case 2: ALL children fail (and the scope has no more work to do).**

Actually this is a nuance: if all children fail, `supervisorScope` still completes normally after waiting for them. The children's exceptions are NOT rethrown by `supervisorScope` itself — they go to the individual `await()` calls or to the uncaught exception handler.

The clearest rule:
```
supervisorScope throws when:
    - The scope's own suspending code (not a child coroutine) throws an exception
    - The scope is cancelled from outside

supervisorScope does NOT throw when:
    - A child coroutine fails
    - Multiple child coroutines all fail
    (children fail silently unless you await() their Deferred)
```

```kotlin
// Example: supervisorScope does NOT throw despite child failing
val result = supervisorScope {
    val a = async { throw RuntimeException("a failed") }
    val b = async { "b succeeded" }
    // a failed, but supervisorScope itself doesn't throw
    // b runs to completion
    try {
        a.await() // THIS throws RuntimeException
    } catch (e: RuntimeException) {
        "caught a's failure"
    } + b.await() // b succeeded
}
// result = "caught a's failureb succeeded"
// supervisorScope completes normally
```

---

### When to Use `coroutineScope` vs `supervisorScope`

**Use `coroutineScope` when: all parts must succeed for the operation to succeed.**

This is "parallel decomposition" — you are decomposing one task into subtasks that all need to complete successfully:

```kotlin
// Downloading and parsing a file: both must succeed
suspend fun downloadAndParse(url: String): ParsedData = coroutineScope {
    val bytes = async { downloadFile(url) }   // must succeed
    val config = async { loadConfig() }       // must succeed

    // If either fails, coroutineScope cancels both and throws
    parseData(bytes.await(), config.await())
}
```

If either `downloadFile` or `loadConfig` fails, the entire operation fails immediately — there is no partial result. This is the correct behavior for this use case.

**Use `supervisorScope` when: operations are independent and one failure should not kill the others.**

```kotlin
// Loading multiple independent feed items: one failure shouldn't kill others
suspend fun loadFeedItems(): List<FeedItem> = supervisorScope {
    val newsItems = async { fetchNews() }
    val weatherItem = async { fetchWeather() }
    val adsItems = async { fetchAds() }

    // Even if fetchAds() fails, news and weather still load
    buildList {
        try { addAll(newsItems.await()) } catch (e: Exception) { /* skip */ }
        try { add(weatherItem.await()) }  catch (e: Exception) { /* skip */ }
        try { addAll(adsItems.await()) }  catch (e: Exception) { /* skip */ }
    }
}
```

---

### Why `viewModelScope` and `lifecycleScope` Use `SupervisorJob`

Both Android scopes use `SupervisorJob` at their root. The reason:

A `ViewModel` typically launches multiple independent coroutines — fetching user data, loading recommendations, refreshing ads, tracking analytics events. These are independent operations.

If one fails (say, the ads request gets a 404), you do NOT want it to cancel all other coroutines in the ViewModel. The user profile should still load. The recommendations should still appear.

```kotlin
// viewModelScope is approximately:
val viewModelScope = CoroutineScope(
    SupervisorJob() +       ← children are independent
    Dispatchers.Main.immediate  ← UI updates run inline on Main
)

// lifecycleScope is approximately:
val lifecycleScope = CoroutineScope(
    SupervisorJob() +       ← same reason
    Dispatchers.Main.immediate
)
```

With `SupervisorJob`:
```
viewModelScope.launch { fetchUserProfile() }  ─┐
viewModelScope.launch { loadRecommendations() } ├─ all independent
viewModelScope.launch { fetchAds() }           ─┘

fetchAds() fails ──► ONLY fetchAds() coroutine is cancelled
                 ──► fetchUserProfile() and loadRecommendations() continue
```

Without `SupervisorJob` (hypothetical):
```
viewModelScope (with regular Job).launch { fetchUserProfile() }  ─┐
viewModelScope.launch { loadRecommendations() }                    ├─ all linked
viewModelScope.launch { fetchAds() }                              ─┘

fetchAds() fails ──► viewModelScope cancels itself
                 ──► fetchUserProfile() cancelled!
                 ──► loadRecommendations() cancelled!
                 ──► ViewModel is broken until recreated
```

The `SupervisorJob` root is what makes Android scopes resilient.

---

### Key Takeaways — 10.2

| Concept | Fact |
|---------|------|
| The one difference | `SupervisorCoroutine` overrides `childCancelled()` to return `false` |
| `supervisorScope` throws | Only when scope body fails or scope is externally cancelled |
| `coroutineScope` use case | All-or-nothing parallel decomposition |
| `supervisorScope` use case | Independent operations, partial success acceptable |
| `viewModelScope` SupervisorJob | One failing coroutine doesn't kill all others in the ViewModel |

---

## 10.3 Exception Handling Rules

### Why `CoroutineExceptionHandler` Only Works on Root Coroutines with `launch`

`CoroutineExceptionHandler` (CEH) is a last-resort handler that catches exceptions that have fully propagated up through the coroutine hierarchy and have nowhere left to go. It only fires on **root coroutines** — coroutines that have no parent to propagate to.

```kotlin
val handler = CoroutineExceptionHandler { coroutineContext, throwable ->
    println("Caught by handler: $throwable")
}

// WORKS: root coroutine (no parent scope)
GlobalScope.launch(handler) {
    throw RuntimeException("root failure")
}
// Prints: "Caught by handler: RuntimeException: root failure"

// WORKS: root-level scope with handler
val scope = CoroutineScope(handler + SupervisorJob())
scope.launch {
    throw RuntimeException("root failure in scope")
}

// DOES NOT WORK: nested coroutine
scope.launch {
    launch(handler) { // handler here is IGNORED for nested coroutines
        throw RuntimeException("nested failure")
    }
}
// The handler on the nested launch is IGNORED
// Exception propagates to parent, then to scope's handler (if any)
```

**Why?** Because nested coroutines propagate their exceptions to their parent via `childCancelled`. The parent handles it (either by cancelling and propagating further, or isolating if SupervisorJob). The `CoroutineExceptionHandler` is only consulted at the end of the propagation chain — when there is no parent to receive it.

The decision tree for exception handling:

```
Child coroutine throws non-CancellationException
    │
    ▼
Is there a parent? ──YES──► propagate to parent via childCancelled()
    │ NO                         │
    │                            ▼
    │                    Does parent have SupervisorJob?
    │                        │ YES                │ NO
    │                        ▼                    ▼
    │                  Isolate failure       Parent cancels,
    │                  (child fails,         propagates up
    │                  parent continues)
    ▼
Is there a CoroutineExceptionHandler?
    │ YES                │ NO
    ▼                    ▼
Handler fires       Thread.uncaughtExceptionHandler
                    (crash in Android)
```

---

### Why `async` Encapsulates Exceptions in `Deferred` — And Propagation Without `await()`

`async` stores the exception in the `Deferred` so it can be retrieved via `await()`. But this does NOT prevent the exception from propagating to the parent coroutine immediately.

```kotlin
// Demonstration of BOTH behaviors:
coroutineScope {
    val deferred = async {
        throw RuntimeException("async failure")
    }

    // At this point, even without calling await(),
    // the coroutineScope is already being cancelled
    // because the child (async) failed and propagated upward.

    delay(100) // This delay may throw CancellationException
               // because the scope is already cancelling

    val result = deferred.await() // Also throws RuntimeException
}
// coroutineScope throws RuntimeException
```

The `Deferred` stores the exception so that even if you `await()` after the scope has handled the failure, you get the original exception back rather than a generic cancellation.

```kotlin
// With supervisorScope: exception is truly contained until await()
supervisorScope {
    val deferred = async {
        throw RuntimeException("contained failure")
    }

    delay(100) // Runs fine — supervisorScope not cancelled by child failure

    try {
        deferred.await() // Only HERE does the exception surface
    } catch (e: RuntimeException) {
        println("Caught at await: $e") // Caught here
    }
}
// supervisorScope completes normally
```

---

### `CancellationException` — Why It Must ALWAYS Be Re-Thrown

`CancellationException` is the mechanism by which the coroutine runtime signals cancellation to running coroutines. It is thrown by suspension points (like `delay`, `yield`, `await`) when the coroutine has been cancelled.

**If you catch `CancellationException` and do not re-throw it, the coroutine thinks the cancellation was handled and continues running.**

```kotlin
// WRONG: swallowing CancellationException
launch {
    try {
        delay(Long.MAX_VALUE) // throws CancellationException when cancelled
    } catch (e: Exception) { // catches CancellationException!
        println("Caught exception, continuing...")
        // coroutine continues running despite being cancelled!
        // This is a coroutine leak
    }
}
```

```kotlin
// CORRECT: re-throw CancellationException
launch {
    try {
        delay(Long.MAX_VALUE)
    } catch (e: CancellationException) {
        // Optional: do cleanup
        cleanup()
        throw e // MUST re-throw
    } catch (e: Exception) {
        // Handle other exceptions
        handleError(e)
    }
}
```

```kotlin
// CORRECT: use catch for specific types, let CE propagate
launch {
    try {
        riskyOperation()
    } catch (e: IOException) {
        // handle IO error
    }
    // CancellationException is NOT IOException — it propagates naturally
}
```

```kotlin
// CORRECT: if you must catch Exception broadly, re-throw CE
suspend fun retryWithBackoff(action: suspend () -> Unit) {
    repeat(3) {
        try {
            action()
            return
        } catch (e: CancellationException) {
            throw e // MUST re-throw — do not retry cancellation
        } catch (e: Exception) {
            delay(1000L * it)
        }
    }
}
```

`CancellationException` is defined as:

```kotlin
public actual open class CancellationException
    actual constructor(message: String?) : IllegalStateException(message)
```

It extends `IllegalStateException` which extends `RuntimeException` which extends `Exception`. This means a broad `catch (e: Exception)` WILL catch it. Always check for `CancellationException` explicitly.

> **Concurrency Trap:** In the context of `runCatching { }` — the Kotlin standard library function — the returned `Result.Failure` may contain a `CancellationException`. If you then call `result.getOrElse { defaultValue }` without re-throwing the CE, you have swallowed the cancellation signal. Use `result.getOrThrow()` or check `result.exceptionOrNull() is CancellationException` and rethrow.

---

### Tight CPU Loop and Cooperative Cancellation

Coroutines use **cooperative cancellation** — a coroutine only becomes aware of its cancellation at suspension points. If a coroutine runs a tight CPU loop without any `suspend` calls, it will never see the cancellation and will run forever (or until the thread is forcibly terminated).

```kotlin
// PROBLEM: tight loop never cancels
val job = launch(Dispatchers.Default) {
    var count = 0
    while (true) { // no suspension point!
        count++    // CPU-intensive work, never yields
    }
}
job.cancel() // cancel() is called, but the loop keeps running!
// The coroutine is "stuck" — it cannot observe cancellation
```

**Fix 1: Check `isActive` in the loop condition**

```kotlin
val job = launch(Dispatchers.Default) {
    var count = 0
    while (isActive) { // cooperative cancellation check
        count++
        doWork()
    }
    // Loop exits when the coroutine is cancelled
    // isActive becomes false when cancel() is called
}
job.cancel() // Loop will exit on the next iteration
```

**Fix 2: Call `yield()` periodically to create a suspension point**

```kotlin
val job = launch(Dispatchers.Default) {
    var count = 0
    while (true) {
        count++
        doWork()
        yield() // suspension point: throws CancellationException if cancelled
    }
}
job.cancel() // yield() will throw CancellationException on next call
```

**Fix 3: Use `ensureActive()` for explicit cancellation checks**

```kotlin
val job = launch(Dispatchers.Default) {
    var count = 0
    while (true) {
        ensureActive() // throws CancellationException if cancelled
        count++
        doWork()
    }
}
job.cancel() // ensureActive() will throw on next call
```

The difference between `yield()` and `ensureActive()`:
- `yield()` is a `suspend` function that also allows other coroutines to run (it gives up the current thread slot). It is a full suspension point.
- `ensureActive()` throws `CancellationException` if cancelled but does NOT suspend — it is not a full suspension point. Use it when you do not want to yield the thread, just check for cancellation.

```
isActive        → Boolean property; read it, do NOT throw automatically
yield()         → suspend: yield thread + check cancellation
ensureActive()  → NOT suspend: just check cancellation and throw if cancelled
```

---

### Why `try-catch` INSIDE a `launch` Works but AROUND Does Not

Inside a `launch`, the `try-catch` is on the **same call stack as the exception**. The coroutine body runs synchronously within the coroutine's own call stack context. Exceptions thrown inside the block propagate normally through that call stack.

```kotlin
launch {
    try {
        // "throw" here is on THIS coroutine's call stack
        throw RuntimeException("exception in body")
    } catch (e: RuntimeException) {
        // This catch is ALSO on this coroutine's call stack
        // Caught correctly
        println("Caught inside launch: $e")
    }
}
```

Outside a `launch`, the `try-catch` is on the **caller's call stack** — the thread that called `launch`. `launch` returns a `Job` immediately (it is not `suspend`). The exception from the coroutine body surfaces on the coroutine's own call stack, which is completely separate.

```kotlin
try {
    launch {
        // This runs LATER, on the coroutine's own call stack
        throw RuntimeException("exception in body")
    }
    // launch() itself does not throw — it returns a Job immediately
} catch (e: RuntimeException) {
    // Never fires — the exception from inside is not on this call stack
}
```

The call stack diagram:

```
Thread A (caller):
  ──► main()
  ──► someFunction()
  ──► try { launch { ... } } catch (e) { }
           │
           └─── launch() returns Job ← NO EXCEPTION HERE
  ──► catch block: never reached

Thread B (coroutine dispatcher thread):  [later]
  ──► coroutine execution
  ──► body of the lambda
  ──► throw RuntimeException ← exception is HERE
  ──► coroutine framework catches it
  ──► propagates via childCancelled(), CoroutineExceptionHandler, etc.
```

---

### Key Takeaways — 10.3

| Concept | Fact |
|---------|------|
| `CoroutineExceptionHandler` scope | Root coroutines only; nested coroutines propagate to parent |
| `async` exception | Stored in `Deferred` AND propagated to parent immediately |
| `CancellationException` | Must ALWAYS be re-thrown; catching broadly swallows it |
| Tight CPU loops | Cooperative cancellation — must call `yield()`, `ensureActive()`, or check `isActive` |
| `try-catch` inside launch | Works — same call stack as exception |
| `try-catch` around launch | Does NOT work — different call stacks |

---

## 10.4 Lifecycle Scopes and Process Death

### What `viewModelScope` Uses Internally

`viewModelScope` is defined in `androidx.lifecycle:lifecycle-viewmodel-ktx`. Its internal construction is approximately:

```kotlin
// In ViewModel.kt (lifecycle-viewmodel-ktx):
val ViewModel.viewModelScope: CoroutineScope
    get() {
        val scope: CoroutineScope? = this.getTag(JOB_KEY)
        if (scope != null) {
            return scope
        }
        return setTagIfAbsent(
            JOB_KEY,
            CloseableCoroutineScope(
                SupervisorJob() + Dispatchers.Main.immediate
            )
        )
    }
```

The two choices and why:

**`SupervisorJob()`:** Children of `viewModelScope` are independent. A failing network call does not cancel the entire ViewModel's work. See 10.2 for full rationale.

**`Dispatchers.Main.immediate`:** ViewModel coroutines are typically launched to update UI state (`_uiState.value = ...`). Using `Main.immediate` means that when the coroutine is launched from the main thread (which ViewModel code usually is), the first block runs synchronously without posting to the Handler queue. This reduces latency for UI updates.

The `CloseableCoroutineScope` is a `CoroutineScope` that implements `Closeable`, allowing the `ViewModel` infrastructure to call `close()` (which cancels the scope) when `onCleared()` is called.

```kotlin
// When ViewModel.onCleared() is called by the framework:
override fun onCleared() {
    super.onCleared()
    // closeables includes viewModelScope's CloseableCoroutineScope
    closeables.forEach { it.close() } // ← cancels SupervisorJob
}
// All coroutines in viewModelScope are cancelled
```

### Does ViewModel Survive Process Death?

**Configuration change (rotation): YES, ViewModel survives.**

**Process death: NO, ViewModel does NOT survive.**

The exact mechanism:

**Rotation survival:**
1. `Activity` is being destroyed due to configuration change.
2. `ActivityThread` calls `Activity.onRetainNonConfigurationInstance()`.
3. `ViewModelStore` (which holds all ViewModels) is stored in `NonConfigurationInstances`.
4. `NonConfigurationInstances` is kept in memory by the framework (not serialized).
5. The new `Activity` instance retrieves the same `ViewModelStore` via `ComponentActivity.getLastNonConfigurationInstance()`.
6. ViewModels are the same objects — they were never destroyed.

**Process death:**
1. The OS kills the app process entirely.
2. All in-memory state is gone: `NonConfigurationInstances`, `ViewModelStore`, and all ViewModels.
3. When the app relaunches, a new process starts, a new `Activity` is created, a new `ViewModelStore` is created, and new ViewModel instances are created.
4. ViewModels are new objects — any state from before is gone.

```
Rotation:
  Activity destroyed ──► ViewModelStore retained in memory ──► Activity recreated
                                     │                              │
                                     └─── same ViewModel ──────────┘

Process death:
  Process killed ──► EVERYTHING in memory is gone
  App relaunches ──► new Activity ──► new ViewModelStore ──► new ViewModel
                                                                  │
                                                              SavedStateHandle
                                                              (restored from Bundle)
```

The exact boundary: **ViewModel survives as long as the process is alive and the Activity is on the back stack, up to but not including process death.**

---

### `lifecycleScope.launch { }` vs `repeatOnLifecycle(STARTED) { }`

These two patterns look similar but have a critical behavioral difference:

**`lifecycleScope.launch { collect { } }` — THE WRONG PATTERN for UI work:**

```kotlin
// PROBLEMATIC: continues in background when app goes to background
lifecycleScope.launch {
    viewModel.uiState.collect { state ->
        updateUI(state) // called even when Activity is in background!
    }
}
```

The `lifecycleScope` is cancelled when the `Activity`/`Fragment` is destroyed. But when the app goes to background (Activity paused/stopped), the coroutine **keeps running**. The `collect` block keeps receiving emissions and calling `updateUI()`. This is wasteful — the UI is not visible and the update is pointless — and in the worst case, accessing Views that are in a bad state.

**`repeatOnLifecycle(STARTED) { collect { } }` — THE CORRECT PATTERN:**

```kotlin
// CORRECT: automatically pauses when stopped, resumes when started
lifecycleScope.launch {
    repeatOnLifecycle(Lifecycle.State.STARTED) {
        viewModel.uiState.collect { state ->
            updateUI(state) // ONLY called when Activity is STARTED
        }
    }
}
```

`repeatOnLifecycle` is a lifecycle-aware suspending function that:
1. **When the lifecycle reaches `STARTED`:** Launches the block as a new coroutine.
2. **When the lifecycle drops below `STARTED` (goes to `STOPPED`):** Cancels that coroutine.
3. **When the lifecycle reaches `STARTED` again:** Launches the block as a new coroutine (restarted from scratch).

```
Lifecycle state:    CREATED ──► STARTED ──► RESUMED ──► PAUSED ──► STOPPED ──► STARTED ──► ...
                                   │                               │              │
repeatOnLifecycle(STARTED):  block starts                    block cancelled  block restarts
collect:                     collecting                       not collecting   collecting again
```

The lifecycle boundary for `STARTED`:
- Activity `onStart()` → `STARTED` → block starts
- Activity `onStop()` → below `STARTED` → block cancelled
- Activity `onStart()` again → `STARTED` → block restarts

For Fragments, using `viewLifecycleOwner.repeatOnLifecycle` is important (not `this.repeatOnLifecycle`), because the Fragment's own lifecycle may differ from the View's lifecycle.

---

### What Is `SavedStateHandle` — How It Survives Process Death

`SavedStateHandle` is a key-value store that is backed by the Android `Bundle` mechanism (`onSaveInstanceState`). It bridges the gap between process-death-safe state and ViewModel-level access.

**The survival chain:**

```
SavedStateHandle (ViewModel level)
         │
         │ delegates to
         ▼
SavedStateRegistry (Activity/Fragment level)
         │
         │ called during
         ▼
Activity.onSaveInstanceState(Bundle)
         │
         │ serialized into
         ▼
Bundle (key-value, Parcelable/Serializable values only)
         │
         │ stored in
         ▼
Activity's state bundle (managed by Android framework)
         │
         │ survives
         ▼
Process death (as long as activity is on back stack)
         │
         │ restored during
         ▼
Activity.onCreate(savedInstanceState: Bundle?)
         │
         │ fed into
         ▼
SavedStateRegistry → SavedStateHandle → ViewModel
```

Key constraints of `SavedStateHandle`:
1. Values must be Parcelable, Serializable, or primitive types (same as Bundle).
2. There is a size limit (~1 MB for the entire Bundle transaction through Binder IPC).
3. Not appropriate for large data (images, big lists) — use Room or DataStore for that.

```kotlin
class MyViewModel(
    private val savedStateHandle: SavedStateHandle
) : ViewModel() {

    // Survives process death:
    var searchQuery: String
        get() = savedStateHandle["query"] ?: ""
        set(value) { savedStateHandle["query"] = value }

    // StateFlow backed by SavedStateHandle:
    val queryFlow: StateFlow<String> = savedStateHandle.getStateFlow("query", "")
}
```

```kotlin
// With Hilt — SavedStateHandle is automatically injected:
@HiltViewModel
class SearchViewModel @Inject constructor(
    private val repository: SearchRepository,
    private val savedStateHandle: SavedStateHandle
) : ViewModel() {
    // savedStateHandle is automatically populated with the saved state
}
```

---

### Key Takeaways — 10.4

| Concept | Fact |
|---------|------|
| `viewModelScope` internals | `SupervisorJob() + Dispatchers.Main.immediate` |
| ViewModel + rotation | Survives (NonConfigurationInstances, in-memory) |
| ViewModel + process death | Does NOT survive (entire process killed) |
| `lifecycleScope.launch { collect }` | Keeps running in background — wasteful and potentially wrong |
| `repeatOnLifecycle(STARTED)` | Cancels block when STOPPED, restarts when STARTED — correct pattern |
| `SavedStateHandle` | Backed by Bundle via onSaveInstanceState — survives process death |

---

## 10.5 `select` Expression

### What `select { }` Does — Racing Multiple Async Operations

`select` is a coroutine primitive that waits for the **first** of multiple suspending operations to become available, then executes the winner's block. It is the coroutine equivalent of `select(2)` in Unix or `CompletableFuture.anyOf()` in Java.

The `select` block contains **clauses**, each specifying a suspending operation and a handler block for when that operation wins.

```kotlin
import kotlinx.coroutines.selects.select

// Race between cache and network:
val result = select<String> {
    async { fetchFromCache() }.onAwait { cachedValue ->
        "from cache: $cachedValue"
    }
    async { fetchFromNetwork() }.onAwait { networkValue ->
        "from network: $networkValue"
    }
}
// result is the return value of whichever completes first
```

Common clauses in `select`:

| Clause | Source | Fires when |
|--------|--------|------------|
| `deferred.onAwait { }` | `Deferred<T>` | The deferred completes |
| `channel.onReceive { }` | `ReceiveChannel<T>` | An element is available |
| `channel.onSend(value) { }` | `SendChannel<T>` | The channel accepts a send |
| `onTimeout(millis) { }` | Timer | The timeout elapses |

```kotlin
// Select with timeout:
val result = select<String> {
    async { slowOperation() }.onAwait { it }
    onTimeout(5000L) { "timeout — using default" }
}

// Select on channels:
val result = select<Int> {
    channel1.onReceive { it * 2 }
    channel2.onReceive { it * 3 }
}
```

---

### "Biased Toward the First Clause" — What It Means

If two or more clauses are **simultaneously ready** when `select` evaluates, it does NOT pick randomly. It always picks the **first clause in declaration order** that is ready.

```kotlin
val result = select<String> {
    // If BOTH deferred1 and deferred2 complete at the same time:
    deferred1.onAwait { "first clause wins" }  // ← always wins ties
    deferred2.onAwait { "second clause wins" } // ← only if first not ready
}
```

This bias is a deterministic, documented behavior. It exists to avoid the complexity of truly random selection and to make reasoning about concurrent code more predictable.

Practical implication:

```kotlin
// If you want fair racing (no bias), shuffle your clauses or use a different mechanism.
// For cache-then-network patterns, bias toward cache (put it first):
val result = select<Data> {
    cacheDeferred.onAwait { it }   // ← preferred if both ready simultaneously
    networkDeferred.onAwait { it } // ← fallback
}
```

---

### Why `select` Does NOT Auto-Cancel the Losing Coroutine

When `select` picks a winner, the losing coroutines (the `async` blocks for the losing clauses) are **still running**. `select` does not cancel them. You must cancel them manually.

```kotlin
// WRONG: the losing async keeps running, wasting resources
val result = select<String> {
    async { fetchFromCache() }.onAwait { it }
    async { fetchFromNetwork() }.onAwait { it }
}
// After select: one of these async blocks is still running!
```

```kotlin
// CORRECT: cancel the losers manually
coroutineScope {
    val cacheDeferred = async { fetchFromCache() }
    val networkDeferred = async { fetchFromNetwork() }

    val result = select<String> {
        cacheDeferred.onAwait { value ->
            networkDeferred.cancel() // cancel the loser
            value
        }
        networkDeferred.onAwait { value ->
            cacheDeferred.cancel() // cancel the loser
            value
        }
    }
    result
}
```

Or more cleanly, using a helper pattern:

```kotlin
suspend fun <T> selectFirst(
    vararg producers: Deferred<T>
): T = select {
    producers.forEach { deferred ->
        deferred.onAwait { result ->
            // cancel all other deferreds
            producers.forEach { other ->
                if (other !== deferred) other.cancel()
            }
            result
        }
    }
}
```

**Why doesn't `select` auto-cancel losers?**
Because `select` does not own the coroutines — the coroutines were launched in an outer scope. The loser coroutines may have side effects you want to preserve, or you may want to collect their results later. Cancellation is a policy decision that belongs to the caller, not to `select`.

---

### Comparison to `CompletableFuture.anyOf()`

| Feature | `CompletableFuture.anyOf()` | `select { }` |
|---------|----------------------------|--------------|
| Cancels losers? | No | No |
| Random winner on tie? | Not guaranteed | No — biased to first clause |
| Multiple clause types? | No — only CompletableFuture | Yes — Deferred, Channel, timeout |
| Coroutine-friendly? | No — blocking | Yes — suspending |
| Lambda in winner | Not directly | Yes — handler block |
| Type-safe result | No (returns `Object`) | Yes — generic `select<T>` |

```java
// Java equivalent (approximate):
CompletableFuture<Object> result = CompletableFuture.anyOf(
    fetchFromCache(),
    fetchFromNetwork()
);
// Both futures still run after anyOf() completes
// Result is Object (not type-safe)
// No cancellation of losers
```

```kotlin
// Kotlin select — type-safe, coroutine-native:
val result: String = select<String> {
    cacheDeferred.onAwait { it }
    networkDeferred.onAwait { it }
}
// Both coroutines still run after select completes
// Result is String (type-safe)
// Must cancel losers manually
```

---

### Full `select` Example: Cache-with-Network Fallback

A common pattern is to return the cached result if it is available within a timeout, otherwise wait for the network:

```kotlin
suspend fun getDataWithCacheFallback(): Data = coroutineScope {
    val cacheDeferred = async { localCache.get() }
    val networkDeferred = async { api.fetchData() }

    val result = select<Data?> {
        cacheDeferred.onAwait { cachedData ->
            if (cachedData != null) {
                networkDeferred.cancel() // cache hit — cancel network
                cachedData
            } else {
                null // cache miss — let network clause win
            }
        }
        networkDeferred.onAwait { networkData ->
            cacheDeferred.cancel() // network won — cancel cache (may already be done)
            localCache.put(networkData) // update cache
            networkData
        }
        onTimeout(3000L) {
            // neither cache nor network ready in 3s
            networkDeferred.cancel()
            cacheDeferred.cancel()
            null
        }
    }

    result ?: throw TimeoutException("No data within timeout")
}
```

---

### Key Takeaways — 10.5

| Concept | Fact |
|---------|------|
| `select { }` | Races multiple suspending operations, runs handler of first winner |
| Clause types | `onAwait`, `onReceive`, `onSend`, `onTimeout` |
| Bias | First clause in declaration order wins ties |
| Loser cancellation | NOT automatic — caller must cancel losing coroutines |
| vs `anyOf()` | `select` is type-safe, suspending, multi-clause-type, coroutine-native |

---

## Master Follow-Up Chains — Phase 10

**Chain F (Coroutine Cancellation) — Phase 10 segment:**

```
CancellationException must be re-thrown ← Q4.3
  └─► catch(Exception) swallows it → coroutine leaks
       └─► viewModelScope auto-cancels on onCleared()
            └─► SupervisorJob: one child failure doesn't cancel scope
                 └─► repeatOnLifecycle: correct lifecycle-aware collection
```

**Chain H (Structured Concurrency) — Full chain:**

```
GlobalScope leaks (no parent) → Q17.1
  └─► viewModelScope uses SupervisorJob → Q10.2
       └─► childCancelled() returns false → sibling isolation
            └─► CoroutineExceptionHandler root only → Q10.3
                 └─► async exception at await() (+ immediate propagation)
                      └─► supervisorScope isolates child failures
```

**Chain E (ViewModel to Process Death) — Phase 10 segment:**

```
ViewModel survives rotation (NonConfigurationInstances)
  └─► ViewModel does NOT survive process death
       └─► SavedStateHandle hooks onSaveInstanceState
            └─► Bundle 1MB limit (Binder IPC) → Q16.3
                 └─► Room/DataStore for large state → Q14.1
```

---

## Cross-References

- Q9.1: CPS / state machine — what a `Job` fundamentally is (a reference to a coroutine's state machine)
- Q9.3: `launch` vs `async` — how `Deferred<T>` extends `Job`, exception propagation
- Q11.4: Flow collection and lifecycle — `repeatOnLifecycle` in depth, `collectAsStateWithLifecycle`
- Q13.3: ViewModel internals — `ViewModelStore`, `NonConfigurationInstances`, process death
- Q13.4: LiveData vs StateFlow — when to use each, duplicate filtering bug
- Q17.1: Memory leaks — `GlobalScope` coroutine leak, why `lifecycleScope` is the fix
- Q17.4: Testing — `runTest`, `StandardTestDispatcher`, `UnconfinedTestDispatcher`, Turbine for Flow

---

*Previous: [09_coroutines_execution_mechanics.md](./09_coroutines_execution_mechanics.md)*
*Next: Phase 11 — Flow (cold vs hot, operators, StateFlow vs SharedFlow, lifecycle collection)*
