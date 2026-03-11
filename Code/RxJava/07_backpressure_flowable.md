# Phase 07 — Backpressure and Flowable: When Producer > Consumer

Backpressure is what happens when a data source produces items faster than
a subscriber can process them. With callbacks, this doesn't exist — there's no
buffer; you just process items as they arrive (blocking the producer).
With reactive streams, the producer and consumer are DECOUPLED — they can run
on different threads. This means the producer can race ahead. Observable ignores
this problem. Flowable solves it with explicit strategies. Choosing wrong means
silent data loss or OOM crashes.

---

## RX.07.1 — The Backpressure Problem

> **Builds on:** [02_observable_types.md] · [04_schedulers.md]
> **Connects to:** [10_decision_maps.md]

### Memory Trick
Producer on IO thread: 1M items/second. Consumer on Main thread: 60 items/second.
Observable drops the overflow. Flowable lets you decide what to do.

### The Problem Visualized

```
Producer (IO thread):
  ──a──b──c──d──e──f──g──h──────────────► very fast

Consumer (Main thread):
  ──a──────────────────b──────────────► very slow

Buffer between them (if any):
  [a][b][c][d][e][f][g][h]...  fills up → OOM or MissingBackpressureException
```

### Observable: No Backpressure

```kotlin
// Observable doesn't handle backpressure
// If your source emits faster than consumption:
Observable.interval(1, TimeUnit.MICROSECONDS)  // emits 1M/sec
    .observeOn(Schedulers.computation())       // consumer is slow
    .subscribe { item ->
        Thread.sleep(10)  // simulating slow processing
    }
// Result: OutOfMemoryError or MissingBackpressureException
// Observable just buffers everything — unbounded
```

### Flowable: Backpressure Aware

```kotlin
// Flowable is Reactive Streams spec compliant
// The subscriber can REQUEST items — it controls the rate
Flowable.interval(1, TimeUnit.MICROSECONDS)
    .onBackpressureDrop()   // explicit strategy: drop excess items
    .observeOn(Schedulers.computation())
    .subscribe { item ->
        Thread.sleep(10)    // still slow, but items are DROPPED gracefully
    }
// No OOM — the strategy handles overflow
```

---

## RX.07.2 — BackpressureStrategy Comparison

> **Connects to:** [09_android_patterns.md]

### The Five Strategies

| Strategy  | Behavior when buffer full           | Use case                              |
|-----------|-------------------------------------|---------------------------------------|
| `BUFFER`  | Unbounded buffer (OOM possible)     | When you CANNOT lose items; bounded by RAM |
| `DROP`    | Silently discard new items          | Latest items have no value if backlog exists |
| `LATEST`  | Keep only most recent; discard old  | Only care about current state (sensor) |
| `ERROR`   | Throw `MissingBackpressureException`| Debug: fail fast when overwhelmed     |
| `MISSING` | No strategy; upstream behavior      | You'll add `onBackpressureXxx` manually|

### ASCII Diagram: DROP vs LATEST vs BUFFER

```
Producer: ─1─2─3─4─5─6─7─8─9─10─►  (fast)
Consumer processes: one every 3 ticks

BUFFER:   ─1─2─3─4─5─6─7─8─9─10─►  all stored → OOM risk
           [1,2,3,4,5,6,7,8,9,10] in memory

DROP:     ─1───────4───────7───────►  keeps first in window, drops rest
           (1 processed, 2,3 dropped; 4 processed, 5,6 dropped)

LATEST:   ─────3───────6───────10──►  keeps last in window
           (1,2 dropped; 3 kept; 4,5 dropped; 6 kept; 7,8,9 dropped; 10 kept)
```

### Code Examples

```kotlin
// BUFFER — don't lose any data (careful with memory)
Flowable.create({ emitter ->
    for (item in hugeList) emitter.onNext(item)
    emitter.onComplete()
}, BackpressureStrategy.BUFFER)

// DROP — sensor data where old readings are irrelevant
Flowable.create({ emitter ->
    locationManager.setListener { loc -> emitter.onNext(loc) }
}, BackpressureStrategy.DROP)

// LATEST — only care about current value (stock ticker, game state)
Flowable.create({ emitter ->
    stockFeed.subscribe { price -> emitter.onNext(price) }
}, BackpressureStrategy.LATEST)

// ERROR — fail fast in debug builds
Flowable.create({ emitter ->
    fastSource.subscribe { item -> emitter.onNext(item) }
}, BackpressureStrategy.ERROR)
```

---

## RX.07.3 — Observable vs Flowable Decision

> **Connects to:** [02_observable_types.md] · [10_decision_maps.md]

### When to Use Flowable

```
Does the source emit faster than the consumer can process?
├── YES (or you're unsure) → Flowable with appropriate strategy
└── NO

OR:
Is the source one of these?
├── Room database live queries → always Flowable
├── File reads (large files)   → Flowable
├── Network streams (SSE, WS)  → Flowable
└── Sensor data (GPS, accel)   → Flowable with DROP or LATEST
```

### When to Use Observable

```
UI events (button clicks, text changes):
→ Observable — humans can't click faster than UI can handle

Single network call result:
→ Single (not even Observable)

In-memory list iteration:
→ Observable — it's synchronous, no actual backpressure possible

Timer/interval with slow tick:
→ Observable (interval at 1s intervals won't overflow)
```

### Room: Always Use Flowable for Live Queries

```kotlin
// Room DAO — use Flowable for live queries
@Dao
interface UserDao {
    // CORRECT: Flowable for live queries (auto-updates on DB change)
    @Query("SELECT * FROM users")
    fun getAllUsers(): Flowable<List<User>>

    // Also fine: Single for one-time reads
    @Query("SELECT * FROM users WHERE id = :id")
    fun getUser(id: String): Single<User>

    // CORRECT: Completable for writes
    @Insert
    fun insertUser(user: User): Completable
}
```

**Why Room uses Flowable:**
Room's live query can emit rapidly when many DB changes happen simultaneously.
Flowable + proper backpressure strategy prevents the observer from being overwhelmed.

---

## RX.07.4 — Flowable Creation Patterns

```kotlin
// From Observable: convert with explicit strategy
val observable = Observable.range(1, 1_000_000)
val flowable = observable.toFlowable(BackpressureStrategy.BUFFER)

// From scratch with create():
val flowable = Flowable.create<Int>({ emitter ->
    for (i in 1..1_000_000) {
        if (emitter.isCancelled) return@create
        emitter.onNext(i)
    }
    emitter.onComplete()
}, BackpressureStrategy.LATEST)

// Applying backpressure operator inline:
Observable.interval(1, TimeUnit.MILLISECONDS)
    .toFlowable(BackpressureStrategy.MISSING)
    .onBackpressureLatest()  // explicit inline strategy
    .observeOn(Schedulers.computation())
    .subscribe { item -> processSlowly(item) }
```

---

## RX.07.5 — Interview Traps

### Trap 1: Using Observable for Room Live Queries

```kotlin
// WRONG: Observable for Room live query
@Query("SELECT * FROM messages")
fun getMessages(): Observable<List<Message>>
// Room can emit many updates rapidly (batch inserts, syncs)
// Observable will buffer them unboundedly → OOM on large tables

// CORRECT:
@Query("SELECT * FROM messages")
fun getMessages(): Flowable<List<Message>>
```

### Trap 2: BUFFER Strategy with Unlimited Source

```kotlin
// WRONG: BUFFER strategy with a source that never slows down
Flowable.create({ emitter ->
    while (true) emitter.onNext(generateItem())  // infinite!
}, BackpressureStrategy.BUFFER)
// The buffer grows without bound → OutOfMemoryError

// CORRECT: Use DROP or LATEST for unbounded sources
Flowable.create({ emitter ->
    while (true) emitter.onNext(generateItem())
}, BackpressureStrategy.LATEST)
// Only the latest item is kept — memory stays constant
```

### Trap 3: MissingBackpressureException in Production

```kotlin
// This happens when you use Observable.toFlowable(MISSING)
// and don't add a backpressure strategy before observeOn

Observable.interval(1, TimeUnit.MICROSECONDS)
    .toFlowable(BackpressureStrategy.MISSING)  // no strategy
    .observeOn(Schedulers.computation())       // queue fills up
    .subscribe { /* slow consumer */ }
// io.reactivex.exceptions.MissingBackpressureException
// Buffer size of 128 exceeded!

// CORRECT: add explicit strategy
Observable.interval(1, TimeUnit.MICROSECONDS)
    .toFlowable(BackpressureStrategy.MISSING)
    .onBackpressureDrop()    // add strategy here
    .observeOn(Schedulers.computation())
    .subscribe { /* slow consumer */ }
```

### Trap 4: Flowable vs Observable for button clicks

```kotlin
// WRONG: Using Flowable for UI events is unnecessary overhead
button.clicks()            // RxBinding returns Observable
    .toFlowable(BackpressureStrategy.BUFFER)  // pointless
    .subscribe { handleClick() }

// CORRECT: Observable is fine for UI events
button.clicks()
    .throttleFirst(1000, TimeUnit.MILLISECONDS)
    .subscribe { handleClick() }
// Humans can't click faster than Observable can handle
```

---

## Self-Test — RX.07

1. Your app receives real-time stock price updates via WebSocket: 500 updates
   per second. Your chart view can redraw at 60fps (60 updates/second).
   Which BackpressureStrategy do you use? Explain why BUFFER would be wrong.

2. Room emits `Flowable<List<User>>`. The DB gets batch-updated with 1000
   users simultaneously, triggering 1000 individual emissions. With BUFFER
   strategy, what happens? With LATEST strategy, what does the subscriber
   actually receive?

3. Explain the Reactive Streams specification's "request N" protocol.
   How does a Flowable subscriber "request" items? How is this different
   from Observable's push model?

4. You have a `Flowable` with `BackpressureStrategy.DROP` and a slow
   `observeOn(Schedulers.io())`. The buffer between IO thread and the
   downstream is 128 items (RxJava default). What happens to items 129
   through 1000?

5. A colleague says "just use Observable everywhere and add `.buffer(100)`
   to batch items if it's too fast." What are two problems with this
   approach vs proper Flowable backpressure?

---

← [06_error_handling.md](06_error_handling.md) | [08_disposables_lifecycle.md →](08_disposables_lifecycle.md)
