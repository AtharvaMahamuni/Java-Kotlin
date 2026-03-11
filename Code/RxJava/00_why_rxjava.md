# Phase 00 — Why RxJava? The Problem It Solves

Before studying any RxJava API, you need to feel the pain it solves. Android
development is fundamentally asynchronous: network calls, DB queries, user
events, location updates — none of these arrive synchronously. The naive
solution is callbacks. The problem is that callbacks compose catastrophically.
RxJava replaces "callback pyramids you nest" with "data streams you transform."
Once that mental shift lands, every operator, every scheduler, every Subject
makes intuitive sense.

---

## RX.00.1 — The Callback Problem

> **Connects to:** [01_observer_pattern.md] · [04_schedulers.md]

### Memory Trick
Callbacks nest → errors escape → threads tangle → cancellation is impossible.
RxJava makes data a stream: transform it, don't nest it.

### WHY This Matters

Every Android dev has written nested callbacks. They look fine for one level.
At three levels, error handling is broken, thread identity is unclear,
and cancelling mid-chain requires custom boolean flags scattered across closures.

### The Callback Hell Diagram

```
fetchUser(userId) { user ->            // Level 1
    if (user == null) {
        handleError("no user")         // error 1: lost
        return
    }
    fetchPosts(user.id) { posts ->     // Level 2
        if (posts == null) {
            handleError("no posts")    // error 2: different handler
            return
        }
        fetchComments(posts[0].id) { comments ->  // Level 3
            if (comments == null) {
                handleError("no comments") // error 3: yet another
                return
            }
            // Finally do the work —
            // but on WHICH thread?
            updateUI(user, posts, comments)
        }
    }
}
```

**What breaks at each level:**

| Problem         | Callback Reality                          |
|-----------------|------------------------------------------|
| Error propagation | Each callback has its own null check; errors don't bubble |
| Thread switching | You must manually post to Main; easy to forget |
| Cancellation    | No standard cancel(); need boolean flags |
| Composition     | Combining two async results requires nesting or a counter |
| Testing         | Can't unit-test without running real async ops |

### What the Reactive Version Looks Like

```kotlin
fetchUser(userId)               // returns Single<User>
    .flatMap { user ->
        fetchPosts(user.id)     // returns Single<List<Post>>
            .map { posts -> Pair(user, posts) }
    }
    .flatMap { (user, posts) ->
        fetchComments(posts[0].id)  // Single<List<Comment>>
            .map { comments -> Triple(user, posts, comments) }
    }
    .subscribeOn(Schedulers.io())
    .observeOn(AndroidSchedulers.mainThread())
    .subscribe(
        { (user, posts, comments) -> updateUI(user, posts, comments) },
        { error -> handleError(error) }  // ONE place for ALL errors
    )
```

**All three problems solved in one chain:**
- Errors: one `onError` handler catches any failure in the chain
- Threading: declared once with `subscribeOn`/`observeOn`
- Cancellation: `dispose()` cancels the entire chain

---

## RX.00.2 — What "Reactive" Means

> **Connects to:** [02_observable_types.md] · [03_operators.md]

### Memory Trick
Data flows downstream through operators like water through pipes.
You describe the transformation; RxJava handles the plumbing.

### The Core Mental Model

```
Source ──[op1]──[op2]──[op3]──► Subscriber
  │                                  │
  │   data flows downstream ──►      │
  │                                  │
  └── errors flow downstream ──► onError()
```

Instead of "I call a function and wait for a callback," think:
"I declare a pipeline. When data appears at the top, it flows through
all operators and arrives transformed at the bottom."

### The Three Reactive Promises

1. **Data as a stream** — any async source (network, DB, sensor, user input)
   becomes an Observable that emits items over time
2. **Operators as transformations** — `map`, `filter`, `flatMap` transform
   the stream without blocking; you compose them like Unix pipes
3. **Unified error model** — errors are just another signal flowing downstream;
   you handle them once at the subscriber

### Marble Diagram: The Concept

```
Time axis: ─────────────────────────────►

Observable:  ──a──b──c──d──|──►
              items      complete

After map(toUppercase):
             ──A──B──C──D──|──►

After filter(isVowel):
             ──A────────────|──►
```

`a`, `b`, `c`, `d` = items emitted
`|` = onComplete signal
`X` = onError signal (stream terminates)

---

## RX.00.3 — RxJava vs Coroutines/Flow: When Each Wins

> **Connects to:** [09_android_patterns.md] · [10_decision_maps.md]

### Memory Trick
Coroutines = sequential async code that LOOKS synchronous.
RxJava = event stream pipelines with rich operator library.

### Comparison Table

| Dimension            | RxJava 2/3                         | Kotlin Coroutines + Flow         |
|----------------------|------------------------------------|----------------------------------|
| **Mental model**     | Push-based stream pipeline         | Suspend/resume sequential code   |
| **Error handling**   | onError signal in stream           | try/catch, structured concurrency|
| **Backpressure**     | Flowable has built-in strategies   | Flow is cold + suspending = natural |
| **Operator library** | 200+ operators, very mature        | Growing; some gaps vs RxJava     |
| **Thread switching** | subscribeOn/observeOn explicit     | withContext { } or flowOn { }    |
| **Android Lifecycle**| RxLifecycle / manual dispose       | viewModelScope, repeatOnLifecycle|
| **Cancellation**     | dispose() / CompositeDisposable    | Structured cancellation automatic|
| **Learning curve**   | Steep (cold/hot, backpressure)     | Gentler if you know coroutines   |
| **Retrofit/Room**    | First-class support (RxJava adapters)| Now preferred (suspend funs)   |
| **Legacy codebases** | Ubiquitous pre-2020 Android        | New code default post-2020       |

### When RxJava Still Wins

- **Existing codebase:** migrating a 200k-line RxJava app isn't free
- **Complex operator chains:** `combineLatest` + `throttleFirst` + `switchMap`
  is one line; equivalent in Flow requires more code
- **Cross-platform teams:** RxJava works on Java backends too
- **Multi-source combining:** `zip`, `combineLatest` are battle-tested

### When Coroutines/Flow Wins

- **New Android project:** Google's recommendation post-2020
- **Simpler mental model:** suspend functions look like regular code
- **Lifecycle integration:** `repeatOnLifecycle`, `viewModelScope` are seamless
- **Retrofit:** suspend functions are the default now
- **Structured concurrency:** automatic cancellation propagation

### The Honest Answer

For a new Android project in 2024+: **start with Coroutines/Flow.**
For an existing RxJava codebase or where you need RxJava's operator richness:
**RxJava is still excellent.** The concepts (streams, operators, schedulers) are
transferable — learn RxJava deeply and Flow becomes obvious.

---

## Self-Test — RX.00

1. In the nested-callback example, if `fetchPosts` throws an exception inside
   its callback, what happens to the UI? Why can't you easily fix this without
   restructuring the code?

2. A colleague says "RxJava and callbacks do the same thing, just different
   syntax." What is the fundamental model difference that makes them NOT the
   same?

3. You have a search bar. As the user types, you want to: debounce 300ms,
   cancel the previous network call if a new character arrives, retry on error.
   Sketch the callback version vs the RxJava version. Which aspects does RxJava
   handle for free?

4. `subscribeOn` and `observeOn` both affect threading. Before reading the
   schedulers file, predict: which one controls where the source runs, and
   which controls where your observer's code runs? Why would they be separate?

5. A teammate says "just use Coroutines, RxJava is dead." What would you tell
   them about the tradeoffs, and what question would you ask before deciding?

---

← [Index](00_index.md) | [01_observer_pattern.md →](01_observer_pattern.md)
