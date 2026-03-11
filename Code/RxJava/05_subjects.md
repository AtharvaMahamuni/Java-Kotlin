# Phase 05 — Subjects: Imperative Meets Reactive

A Subject is the bridge between imperative code and reactive streams. It is
simultaneously an Observable (you can subscribe to it) and an Observer (you
can push items into it manually). This makes Subjects powerful — and dangerous.
They are the "escape hatch" when you have data arriving from non-reactive
sources (lifecycle events, callback-based SDKs, UI events without RxBinding).
The danger: they are hot, stateful, and have no backpressure. Misuse causes
missed emissions, memory leaks, and subtle timing bugs.

---

## RX.05.1 — What Is a Subject?

> **Builds on:** [02_observable_types.md] · [01_observer_pattern.md]
> **Connects to:** [06_error_handling.md] · [08_disposables_lifecycle.md]

### Memory Trick
Subject = Observable + Observer. Push items in with onNext();
subscribers receive them downstream. It's a hot multicasting bus.

### The Dual Interface

```kotlin
// Subject IS-A Observable: you subscribe to it
// Subject IS-A Observer: you push items into it

val subject = PublishSubject.create<String>()

// As Observable: subscribe to receive items
subject.subscribe { item -> println("Got: $item") }

// As Observer: push items in imperatively
subject.onNext("hello")   // subscriber sees "hello"
subject.onNext("world")   // subscriber sees "world"
subject.onComplete()      // stream terminates
```

### The Hot Nature of Subjects

```
subject.onNext("A")   // emitted BEFORE any subscriber — LOST

val sub1 = subject.subscribe { println("Sub1: $it") }

subject.onNext("B")   // sub1 sees "B"

val sub2 = subject.subscribe { println("Sub2: $it") }

subject.onNext("C")   // BOTH sub1 and sub2 see "C"
subject.onNext("D")   // BOTH see "D"

sub1.dispose()

subject.onNext("E")   // ONLY sub2 sees "E"
```

---

## RX.05.2 — The Four Subject Types

> **Connects to:** [10_decision_maps.md] · [09_android_patterns.md]

### Comparison Table

| Subject           | What late subscribers see          | Completes when     | Use case                    |
|-------------------|------------------------------------|--------------------|-----------------------------|
| `PublishSubject`  | Only items emitted AFTER subscribe | `onComplete()` called | Event bus, one-shot events  |
| `BehaviorSubject` | Last item + all subsequent         | `onComplete()` called | Current state, ViewModel state |
| `ReplaySubject`   | ALL past items + all subsequent    | `onComplete()` called | History replay, event log   |
| `AsyncSubject`    | Only the LAST item, on complete    | `onComplete()` called | Single result that isn't ready yet |

### Memory Diagrams Per Type

**PublishSubject** — join the live broadcast

```
Emissions: ──A──B────C────D──────►

Sub1 (joined at start):
  ──A──B────C────D──────►  (sees all)

Sub2 (joined after B):
  ─────────C────D──────►   (missed A and B)
```

**BehaviorSubject** — get current state immediately

```
Emissions: ──A──B────C────D──────►
                     ↑
             Sub2 subscribes here

Sub2 receives:   C──D──────►
                 ↑ gets last value (C) immediately on subscribe
```

```kotlin
// BehaviorSubject for ViewModel state — the right choice
val uiState = BehaviorSubject.createDefault<UiState>(UiState.Idle)

// When Activity rotates and re-subscribes, it immediately gets
// the current state (Loading, Success, Error, etc.)
uiState.onNext(UiState.Loading)
// ...later...
uiState.onNext(UiState.Success(data))
```

**ReplaySubject** — full history available

```kotlin
// Replays ALL past emissions to each new subscriber
val replay = ReplaySubject.create<String>()
replay.onNext("event1")
replay.onNext("event2")

// Late subscriber gets EVERYTHING
replay.subscribe { println(it) }
// Output: event1, event2
```

```kotlin
// ReplaySubject with buffer limit:
val limited = ReplaySubject.createWithSize<Int>(3)
// Only replays the last 3 items
```

**AsyncSubject** — only the last value, on completion

```kotlin
val async = AsyncSubject.create<Int>()
async.subscribe { println("Got: $it") }

async.onNext(1)   // nothing emitted yet
async.onNext(2)   // nothing emitted yet
async.onNext(3)   // nothing emitted yet
async.onComplete()  // NOW emits: only 3 (the last value)
// Output: Got: 3
```

---

## RX.05.3 — When to Use Subject vs Observable.create()

> **Connects to:** [02_observable_types.md]

### Prefer Observable.create() When:

```kotlin
// You're wrapping a callback API
// Observable.create is cleaner — the callback IS the emission logic
fun fromLocationCallback(): Observable<Location> =
    Observable.create { emitter ->
        val listener = LocationListener { location ->
            if (!emitter.isDisposed) emitter.onNext(location)
        }
        locationManager.requestUpdates(listener)
        emitter.setCancellable {
            locationManager.removeUpdates(listener)
        }
    }
```

### Use Subject When:

```kotlin
// You need to push items from MULTIPLE places
// Or when you're bridging lifecycle events into reactive code

class EventBus {
    private val bus = PublishSubject.create<AppEvent>().toSerialized()
    //                                                 ^ thread-safe wrapper

    fun post(event: AppEvent) = bus.onNext(event)
    fun observe(): Observable<AppEvent> = bus.hide()
    //                                        ^ hides Subject as Observable
    //                                          prevents callers from casting back
}
```

### Subject Thread Safety

```kotlin
// IMPORTANT: Subjects are NOT thread-safe by default
// If multiple threads call onNext(), use .toSerialized()
val subject = PublishSubject.create<Int>().toSerialized()
// Now it's safe to call subject.onNext() from multiple threads
```

---

## RX.05.4 — Interview Traps

### Trap 1: PublishSubject Misses Values Before Subscribe

```kotlin
// WRONG: using PublishSubject for "current state" in ViewModel
class ViewModel {
    val events = PublishSubject.create<Event>()

    fun loadData() {
        // This fires before Activity subscribes!
        events.onNext(Event.Loading)
        // ...async work...
        events.onNext(Event.Success(data))
    }
}

// Activity subscribes in onResume — AFTER events.onNext(Loading)
// It NEVER sees the Loading event! UI shows nothing.

// CORRECT: BehaviorSubject or StateFlow
class ViewModel {
    val state = BehaviorSubject.createDefault<UiState>(UiState.Idle)
    // Late subscriber gets current state immediately
}
```

### Trap 2: ReplaySubject Memory Leak

```kotlin
// WRONG: Unbounded ReplaySubject in a long-lived component
class Analytics {
    // DANGER: stores ALL events in memory forever
    val events = ReplaySubject.create<AnalyticsEvent>()
}

// CORRECT: Limit buffer size or time window
val events = ReplaySubject.createWithSize<AnalyticsEvent>(100)
val events = ReplaySubject.createWithTime<AnalyticsEvent>(
    5, TimeUnit.MINUTES, Schedulers.computation()
)
```

### Trap 3: Exposing Subject Directly

```kotlin
// WRONG: callers can push items into your Subject
class ViewModel {
    val state = PublishSubject.create<UiState>()  // public!
}

// Anyone can call: viewModel.state.onNext(UiState.Broken)
// This breaks encapsulation — only ViewModel should control state

// CORRECT: hide the Subject behind Observable
class ViewModel {
    private val _state = PublishSubject.create<UiState>()
    val state: Observable<UiState> = _state.hide()
    //                                      ^ callers can only subscribe,
    //                                        not push
}
```

### Trap 4: Subject as Shared Bus = No Backpressure

```kotlin
// Subjects are hot Observables — no backpressure
// If you push 10,000 items/second into a PublishSubject
// and the subscriber processes 100 items/second,
// items are DROPPED (PublishSubject) or memory explodes (ReplaySubject)

// For high-throughput scenarios, use Flowable + BackpressureStrategy
// instead of a Subject
```

---

## Self-Test — RX.05

1. A ViewModel starts loading data, calls `subject.onNext(Loading)`,
   then the Activity subscribes. With `PublishSubject`, what does
   the Activity see? With `BehaviorSubject`? Explain the mechanism.

2. `AsyncSubject` only emits the last value on completion. Name a real
   use case where this behavior is exactly what you want.

3. Why should you call `.hide()` on a Subject before exposing it?
   What could go wrong if a caller receives the raw Subject?

4. Your EventBus Subject receives items from both the main thread and
   a background thread simultaneously. What contract does the Observer
   pattern require about concurrent `onNext` calls? How do you fix it?

5. `ReplaySubject` without size limits can cause OOM. `BehaviorSubject`
   only keeps the last value. Design a scenario where you need exactly
   the last 5 values (e.g., an undo history). Which Subject do you use?

---

← [04_schedulers.md](04_schedulers.md) | [06_error_handling.md →](06_error_handling.md)
