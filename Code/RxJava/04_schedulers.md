# Phase 04 — Schedulers: Which Thread

RxJava operators are thread-agnostic by default: they run on whatever thread
called `subscribe()`. This is a deliberate design choice — the operator chain
is a pure data pipeline, and you declare threading separately. Schedulers are
how you declare threading. The most important rule: `subscribeOn` controls
where the SOURCE runs; `observeOn` controls where DOWNSTREAM runs. If you
understand this asymmetry, threading bugs become obvious rather than mystical.

---

## RX.04.1 — Scheduler Types

> **Builds on:** [01_observer_pattern.md] · [03_operators.md]
> **Connects to:** [08_disposables_lifecycle.md] · [09_android_patterns.md]

### Memory Trick
IO = blocking work. Computation = CPU work. Main = UI updates.
subscribeOn = source thread. observeOn = observer thread.

### Scheduler Reference Table

| Scheduler                         | Thread pool            | Use for                                      |
|-----------------------------------|------------------------|----------------------------------------------|
| `Schedulers.io()`                 | Unbounded, cached      | Network, DB, file I/O — blocks are OK        |
| `Schedulers.computation()`        | Fixed = CPU cores      | CPU-bound: parsing, encryption, sorting      |
| `Schedulers.newThread()`          | One new thread per use | Rare — prefer io() which reuses threads      |
| `Schedulers.single()`             | Single background thread| Ordered background work                     |
| `Schedulers.trampoline()`         | Current thread (queued)| Testing; serializes on calling thread        |
| `AndroidSchedulers.mainThread()`  | Android Main Looper    | UI updates, LiveData/View manipulation       |

### When to Use Each

```
What kind of work?
├── Blocking I/O (network, DB, files) → Schedulers.io()
├── CPU-bound (computation, parsing) → Schedulers.computation()
├── UI / View updates                → AndroidSchedulers.mainThread()
├── Sequential background work       → Schedulers.single()
└── Tests (synchronous)              → Schedulers.trampoline()
```

**Why NOT `computation()` for I/O:**
`computation()` has a fixed pool = number of CPU cores (e.g., 8 threads).
If you use it for blocking I/O, you fill all 8 threads with waiting operations,
starving actual CPU-bound work. `io()` is unbounded — it expands as needed.

**Why NOT `newThread()` in production:**
Creating a new thread per subscription is expensive. `io()` reuses cached
threads from a pool. Use `newThread()` only when you explicitly need thread
isolation and can manage the cost.

---

## RX.04.2 — subscribeOn vs observeOn

> **Connects to:** [09_android_patterns.md] · [10_decision_maps.md]

### Memory Trick
subscribeOn = "start the source here." observeOn = "deliver results here."
subscribeOn affects everything ABOVE it; observeOn affects everything BELOW.

### subscribeOn — Controls Source Thread

```kotlin
Observable.create<User> { emitter ->
    // THIS block runs on IO thread
    val user = database.fetchUser()  // blocking call OK on IO
    emitter.onNext(user)
    emitter.onComplete()
}
.subscribeOn(Schedulers.io())   // source runs on IO
.subscribe { user -> println(user) }
// println runs on IO thread too (no observeOn yet)
```

**Rules:**
1. Only the FIRST `subscribeOn` in a chain takes effect
2. It affects the source and everything upstream of it
3. Calling `subscribeOn` twice: only the first one wins

### observeOn — Controls Downstream Thread

```kotlin
Observable.create<User> { emitter ->
    // Runs on IO (from subscribeOn)
    emitter.onNext(database.fetchUser())
}
.subscribeOn(Schedulers.io())        // source on IO
.map { user -> user.name.uppercase() }   // runs on IO
.observeOn(AndroidSchedulers.mainThread())  // SWITCH to Main
.map { name -> "Hello, $name" }      // runs on Main thread now
.subscribe { greeting ->
    textView.text = greeting         // runs on Main — safe!
}
```

**Rules:**
1. `observeOn` applies to all operators BELOW it in the chain
2. You can call `observeOn` multiple times to switch threads
3. Each `observeOn` inserts a queue (buffer) between threads

### Thread-Switching Diagram

```
source.subscribeOn(IO)
  │
  │ subscribe() call travels UP the chain
  ▼
Source code executes on: [IO thread]
  │
  │ onNext emission flows DOWN
  ▼
.map { }          [IO thread]   ← before observeOn
  │
  ▼
.observeOn(Main)  ← THREAD SWITCH HERE (queues items)
  │
  ▼
.map { }          [Main thread] ← after observeOn
  │
  ▼
.subscribe { }    [Main thread]
```

### Full Android Pattern

```kotlin
// The canonical Android pattern:
apiService.getUsers()              // Single<List<User>>
    .toObservable()
    .subscribeOn(Schedulers.io())  // network call on IO
    .observeOn(AndroidSchedulers.mainThread())  // result on Main
    .subscribe(
        { users -> recyclerAdapter.submitList(users) },  // Main
        { error -> showError(error) }                    // Main
    )
```

---

## RX.04.3 — Multiple subscribeOn / observeOn Calls

> **Connects to:** [10_decision_maps.md]

### Multiple subscribeOn: Only First Wins

```kotlin
Observable.create<Int> { emitter ->
    println("Source: ${Thread.currentThread().name}")
    emitter.onNext(1)
}
.subscribeOn(Schedulers.io())           // WINS — only this takes effect
.subscribeOn(Schedulers.computation())  // IGNORED
.subscribe { println("Got: $it on ${Thread.currentThread().name}") }

// Output:
// Source: RxCachedThreadScheduler-1   (IO thread — first subscribeOn wins)
// Got: 1 on RxCachedThreadScheduler-1
```

**Why:** When `subscribe()` is called, the subscription travels UP the
operator chain. Each `subscribeOn` encountered would wrap the upstream.
The OUTERMOST (first called) wrapping wins because it's the last applied
during the subscription propagation.

### Multiple observeOn: Each Takes Effect

```kotlin
Observable.just(1, 2, 3)
    .subscribeOn(Schedulers.io())
    .map { it * 2 }                      // IO thread
    .observeOn(Schedulers.computation()) // SWITCH to Computation
    .map { it + 1 }                      // Computation thread
    .observeOn(AndroidSchedulers.mainThread())  // SWITCH to Main
    .subscribe { println(it) }           // Main thread
```

```
Thread timeline:
[IO]:          ──source──map(x2)──────────────────────────────────►
[Computation]: ──────────────────map(+1)──────────────────────────►
[Main]:        ──────────────────────────────subscribe { }────────►
```

**Why multiple observeOn works:** Each `observeOn` inserts a queue between
the upstream (running on one thread) and downstream (running on another).
This is useful when you need to do heavy CPU work after fetching data, then
switch to Main for UI.

---

## RX.04.4 — Threading Reality: What Actually Happens

### The Queue Between Threads

When `observeOn(Main)` is used, RxJava doesn't magically teleport items.
It posts each `onNext` call as a `Runnable` to the Main Looper queue.

```
IO thread emits ──► [Main Looper Queue] ──► Main thread processes
                          │
               items buffer here while Main is busy
```

**Implication:** If Main thread is busy (heavy UI work), items queue up.
This is why `observeOn` can introduce backpressure-like behavior
(use `Flowable` with a proper strategy if you need to handle this).

### Trampoline Scheduler for Tests

```kotlin
// Tests: subscribeOn/observeOn would make tests async and fragile
// Trampoline queues work on the CALLING thread, executes synchronously

val testScheduler = Schedulers.trampoline()

observable
    .subscribeOn(testScheduler)   // runs synchronously on test thread
    .observeOn(testScheduler)
    .test()                        // TestObserver for assertions
    .assertValues(1, 2, 3)
    .assertComplete()
```

---

## RX.04.5 — Interview Traps

### Trap 1: Second subscribeOn Is Silently Ignored

```kotlin
// WRONG: expecting the second subscribeOn to override the first
observable
    .subscribeOn(Schedulers.computation())
    .map { heavyTransform(it) }
    .subscribeOn(Schedulers.io())  // IGNORED — first one wins
    .subscribe { /* runs on computation, not io */ }
```

### Trap 2: Forgetting observeOn Before UI Update

```kotlin
// WRONG: touching View on background thread = crash
apiService.getData()
    .subscribeOn(Schedulers.io())
    // MISSING: .observeOn(AndroidSchedulers.mainThread())
    .subscribe { data ->
        textView.text = data  // CalledFromWrongThreadException!
    }

// CORRECT:
apiService.getData()
    .subscribeOn(Schedulers.io())
    .observeOn(AndroidSchedulers.mainThread())
    .subscribe { data ->
        textView.text = data  // Safe — Main thread
    }
```

### Trap 3: Using computation() for I/O

```kotlin
// WRONG: blocks computation thread pool with I/O wait
Observable.create<Bitmap> { emitter ->
    val bitmap = BitmapFactory.decodeFile(path)  // blocking I/O!
    emitter.onNext(bitmap)
}
.subscribeOn(Schedulers.computation())  // WRONG — blocks CPU threads

// CORRECT:
.subscribeOn(Schedulers.io())  // I/O threads handle blocking
```

### Trap 4: Where Does flatMap's Inner Observable Run?

```kotlin
// subscribeOn inside flatMap controls the INNER Observable's thread
// The OUTER subscribeOn controls the source

observable
    .subscribeOn(Schedulers.io())      // source on IO
    .flatMap { item ->
        Observable.fromCallable { processItem(item) }
            .subscribeOn(Schedulers.computation())  // inner on Computation
    }
    .observeOn(AndroidSchedulers.mainThread())
    .subscribe { updateUI(it) }
// Source: IO, inner transforms: Computation, UI: Main
```

---

## Self-Test — RX.04

1. You call `subscribeOn(IO)` twice in a chain. Trace the subscription
   propagation from `subscribe()` upward through the operators. At which point
   does the thread actually switch? Why does only the first `subscribeOn` win?

2. You have a chain: `source → map → observeOn(Computation) → map →
   observeOn(Main) → subscribe`. Trace each operator: which thread does it
   run on?

3. You're writing a test for a class that uses `subscribeOn(IO).observeOn(Main)`.
   Without using real threads, how do you make the test synchronous and
   deterministic? What scheduler do you use and why?

4. `observeOn` inserts a queue between threads. What happens to that queue
   if the downstream (Main thread) is busy processing a long layout pass?
   How could this cause a memory problem?

5. A network call on `io()` emits a large list. You then `flatMap` each
   item to another network call. Without thinking about backpressure yet,
   what threading configuration allows maximum parallelism? What's the risk?

---

← [03_operators.md](03_operators.md) | [05_subjects.md →](05_subjects.md)
