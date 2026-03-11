# Phase 10 — Decision Maps: Birds-Eye View

This file is a rapid-reference cheat sheet. When you're in a code review or
interview and need to quickly justify a choice, the decision trees here give
you the reasoning chain in under 30 seconds. Bookmark this file. Everything
here has been explained in depth in earlier files — this is the one-page
summary you return to daily.

---

## RX.10.1 — Which Observable Type?

> **Builds on:** [02_observable_types.md] · [07_backpressure_flowable.md]

```
Does your operation produce items?
│
├── NO (fire-and-forget: write, delete, POST)
│   └── Completable
│
└── YES — how many?
    │
    ├── Exactly 1 or error (never zero)
    │   └── Single<T>     e.g. GET /user/{id}, cache lookup
    │
    ├── 0 or 1 (item may not exist)
    │   └── Maybe<T>      e.g. nullable DB find, cache hit/miss
    │
    └── Many (0 to infinite)
        │
        Can the producer overwhelm the consumer?
        (DB live query, file read, sensor data, WebSocket)
        ├── YES / unsure → Flowable<T>  + BackpressureStrategy
        └── NO (UI events, in-memory, slow ticker)
            └── Observable<T>
```

### Quick Reference

```
Network GET one resource     → Single<T>
Network POST no response     → Completable
Cache lookup (may miss)      → Maybe<T>
UI click stream              → Observable<T>
Room live query              → Flowable<T>
Sensor data                  → Flowable<T> + DROP or LATEST
Multiple results from list   → Observable<T>
```

---

## RX.10.2 — Which Flattening Operator?

> **Builds on:** [03_operators.md]

```
Is the transform synchronous (returns T, not Observable<T>)?
├── YES → map { }
└── NO (returns Observable / Single / Flowable)
    │
    Does ORDER of results matter?
    │
    ├── NO (parallel OK, fastest overall)
    │   └── flatMap { }
    │       e.g. fetch 10 users in parallel
    │
    └── YES (preserve emission order)
        │
        Should NEW item CANCEL the previous in-flight work?
        │
        ├── YES (only latest matters)
        │   └── switchMap { }
        │       e.g. search-as-you-type, navigation
        │
        └── NO (all work must complete, in order)
            └── concatMap { }
                e.g. pagination, ordered writes
```

### One-Line Summary

```
map        → sync 1:1 transform
flatMap    → async parallel, order not guaranteed
concatMap  → async sequential, order preserved
switchMap  → async, cancels previous, only latest
```

---

## RX.10.3 — Which Subject?

> **Builds on:** [05_subjects.md]

```
Do new subscribers need past values?
│
├── NO (only future emissions matter)
│   └── PublishSubject
│       e.g. one-shot events, EventBus
│
└── YES — how many past values?
    │
    ├── Only the LAST value (current state)
    │   └── BehaviorSubject
    │       e.g. ViewModel UiState, form state
    │
    ├── ALL past values (full history)
    │   └── ReplaySubject (add size limit!)
    │       e.g. undo history, event log
    │
    └── Only the LAST value, ONLY AFTER complete
        └── AsyncSubject
            e.g. lazy initialization result
```

### ViewModel State Rule

```
Always use BehaviorSubject (or StateFlow) for ViewModel state.
PublishSubject misses values emitted before Activity subscribes.
```

---

## RX.10.4 — Which Scheduler?

> **Builds on:** [04_schedulers.md]

```
What kind of work?
│
├── Blocking I/O (network, DB, files)
│   └── Schedulers.io()
│
├── CPU-intensive (parsing, sorting, crypto)
│   └── Schedulers.computation()
│
├── UI / View updates
│   └── AndroidSchedulers.mainThread()
│
├── One operation at a time, ordered
│   └── Schedulers.single()
│
└── Unit tests (synchronous)
    └── Schedulers.trampoline()
```

### The Android Pattern

```
.subscribeOn(Schedulers.io())
.observeOn(AndroidSchedulers.mainThread())
```

Always in this order. subscribeOn affects the source.
observeOn switches thread for everything below it.

### Multiple Call Rule

```
subscribeOn:  only FIRST call takes effect (others ignored)
observeOn:    EACH call takes effect (creates thread switch)
```

---

## RX.10.5 — Which Backpressure Strategy?

> **Builds on:** [07_backpressure_flowable.md]

```
Can you afford to LOSE items?
│
├── NO (all items are critical: financial, messages)
│   └── BUFFER  ⚠️ watch memory
│
└── YES — which do you prefer to keep?
    │
    ├── Keep FIRST in window (drop new while busy)
    │   └── DROP
    │       e.g. user actions (button tap = once per window)
    │
    └── Keep LATEST (drop old, always process newest)
        └── LATEST
            e.g. sensor data, stock prices, GPS
```

---

## RX.10.6 — Error Handling Decision

> **Builds on:** [06_error_handling.md]

```
Error occurred. What do you want?
│
├── Return a default value, stream ends normally
│   └── onErrorReturn { defaultValue }
│
├── Switch to a fallback stream (cache, default source)
│   └── onErrorResumeNext { fallbackObservable }
│
├── Retry the operation
│   ├── Immediately → retry(n)
│   └── With delay  → retryWhen { exponentialBackoff }
│
└── Propagate to subscriber's onError { }
    (critical errors: auth, data corruption)
```

---

## RX.10.7 — One-Page Operator Cheat Sheet

### Transform

| Operator      | In 3 words              | Use when                        |
|---------------|-------------------------|---------------------------------|
| `map`         | sync value transform    | Change each item synchronously  |
| `flatMap`     | async merge parallel    | Parallel async, order irrelevant|
| `concatMap`   | async sequential order  | Ordered async, all complete     |
| `switchMap`   | async cancel previous   | Latest wins, cancel old         |
| `scan`        | running accumulation    | Cumulative state (sum, history) |
| `buffer(n)`   | batch into lists        | Process in chunks               |

### Filter

| Operator          | In 3 words             | Use when                        |
|-------------------|------------------------|---------------------------------|
| `filter`          | conditional pass-through| Keep matching items only        |
| `take(n)`         | first N only           | Limit stream length             |
| `skip(n)`         | drop first N           | Ignore initial items            |
| `distinct`        | no duplicates          | Deduplicate stream              |
| `distinctUntilChanged` | no consecutive dups | Only emit if value changed  |
| `debounce(t)`     | wait for silence       | Search input, rapid UI events   |
| `throttleFirst(t)`| first per window       | Button clicks (prevent double)  |
| `sample(t)`       | periodic snapshot      | Periodic metrics                |

### Combine

| Operator        | In 3 words              | Use when                         |
|-----------------|-------------------------|----------------------------------|
| `zip`           | pair by position        | Combine two calls, wait for both |
| `combineLatest` | latest from each        | Form validation, reactive UI     |
| `merge`         | interleave all          | Parallel independent streams     |
| `concat`        | sequential all          | Ordered stream sources           |
| `amb`           | first wins only         | Race multiple sources, use first |

### Error

| Operator               | In 3 words           | Use when                        |
|------------------------|----------------------|---------------------------------|
| `onErrorReturn`        | error → value        | Non-critical, has default       |
| `onErrorResumeNext`    | error → stream       | Has fallback source             |
| `retry(n)`             | retry N times        | Transient network errors        |
| `retryWhen`            | retry with backoff   | Production network retry        |

### Utility

| Operator         | In 3 words           | Use when                         |
|------------------|----------------------|----------------------------------|
| `doOnNext`       | peek, don't touch    | Logging, analytics               |
| `doOnError`      | peek at error        | Error logging                    |
| `doOnComplete`   | peek at complete     | Metrics, cleanup                 |
| `doOnSubscribe`  | peek at subscribe    | Show loading spinner             |
| `doFinally`      | always runs last     | Hide loading spinner             |
| `delay(t)`       | emit after pause     | Debounce outgoing (not incoming) |
| `timeout(t)`     | error if too slow    | Network timeout fallback         |

---

## RX.10.8 — Full Pattern Quick Reference

```
Pattern                     → Key operators
──────────────────────────────────────────────────
Search as you type          → debounce + switchMap
Button click (no double)    → throttleFirst
Parallel API calls          → Single.zip or flatMap
Sequential pagination       → concatMap
Current state in ViewModel  → BehaviorSubject or StateFlow
Auto-updating DB query      → Flowable (Room)
Network call with retry     → retry / retryWhen
Network + cache fallback    → onErrorResumeNext
Loading indicator           → doOnSubscribe + doFinally
Cancel on ViewModel clear   → CompositeDisposable.clear()
```

---

## Self-Test — RX.10

1. A friend asks: "My stream needs to: fetch data from network, retry
   twice on failure, fall back to cache if retries fail, then update UI."
   Without looking up operators, name the exact operators in order.

2. You have three `Single<Price>` calls (stock prices A, B, C). You want:
   - Start all three simultaneously
   - Display EACH price as it arrives (don't wait for all three)
   - Cancel remaining if user navigates away
   Which type, which operators?

3. Design the full operator chain for: user types in search box → wait 300ms
   → minimum 3 characters → no duplicate consecutive queries → search API
   → cancel if new query arrives → show results on main thread.
   Write the chain from memory, then verify against 09_android_patterns.md.

4. A ViewModel has 3 independent data streams: user profile, notifications,
   unread count. You want a single `UiState` that combines all three.
   Which combining operator do you use? Draw the marble diagram.

5. You're in a code review. A PR uses `ReplaySubject.create<Event>()` in a
   singleton EventBus (no size limit). No subscribers are present for 10 minutes
   during which 50,000 events fire. What happens? How do you fix the PR?

---

```
╔══════════════════════════════════════════════════╗
║           RxJava Master Summary                  ║
╠══════════════════════════════════════════════════╣
║ TYPE    : Single/Maybe/Completable/Observable/   ║
║           Flowable → cardinality at type level   ║
║ COLD/HOT: Cold = fresh per sub / Hot = shared    ║
║ FLATTEN : map→sync / flat→parallel /             ║
║           concat→ordered / switch→cancelPrev     ║
║ THREAD  : subscribeOn(source) observeOn(below)   ║
║ SUBJECT : Publish/Behavior/Replay/Async          ║
║ ERROR   : onErrorReturn/Resume/retry/retryWhen   ║
║ BACKPRS : Flowable + BUFFER/DROP/LATEST/ERROR    ║
║ DISPOSE : CompositeDisposable.clear() onCleared  ║
╚══════════════════════════════════════════════════╝
```

---

← [09_android_patterns.md](09_android_patterns.md) | [Index →](00_index.md)
