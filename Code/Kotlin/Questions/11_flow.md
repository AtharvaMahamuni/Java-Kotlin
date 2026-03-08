# Phase 11: Flow

## Navigation
[← Phase 10 — Structured Concurrency](10_structured_concurrency.md) | [→ Phase 12 — Reflection & References](12_reference_operators_and_reflection.md)

## Questions in This File
- [Q11.1 — Cold vs Hot Streams](#q111--cold-vs-hot-streams)
- [Q11.2 — Flow Operators](#q112--flow-operators)
- [Q11.3 — `StateFlow` vs `SharedFlow`](#q113--stateflow-vs-sharedflow)
- [Q11.4 — Flow Collection and Lifecycle](#q114--flow-collection-and-lifecycle)
- [Q11.5 — Channels: Hot Streams with Backpressure](#q115--channels-hot-streams-with-backpressure)

---

## Q11.1 — Cold vs Hot Streams

> **Builds on:** [Q7.2 — Sequences](07_collections_and_sequences.md#q72--sequences-vs-eager-collections) · [Q9.1 — suspend mechanics](09_coroutines_execution_mechanics.md#q91--what-suspend-actually-does) · [Q9.4 — UNDISPATCHED start mode](09_coroutines_execution_mechanics.md#q94--coroutine-start-modes)
> **Connects to:** [Q11.2 — Flow Operators](#q112--flow-operators) · [Q11.3 — StateFlow vs SharedFlow](#q113--stateflow-vs-sharedflow) · [Q11.4 — Flow Collection](#q114--flow-collection-and-lifecycle)

---

### The Concrete Picture — Instant Orientation

```
COLD: each collector gets a fresh, independent producer execution
  val f = flow { emit(1); emit(2) }
  f.collect { }   // producer runs: 1, 2
  f.collect { }   // producer runs AGAIN: 1, 2  ← new execution, no shared state

HOT: producer runs independently; collectors tap into an ongoing stream
  val s = MutableStateFlow(0)       // producer "already running" — holds 0
  s.value = 1                       // updates regardless of collectors
  Collector A (from start): 0, 1
  Collector B (joins late):     1   ← only current state, missed 0
```

---

### Why Flow Exists — Derived From Sequence's Limitation

`Sequence` is lazy and synchronous. The `SequenceScope` receiver does not inherit `CoroutineScope`, so suspension functions cannot be called inside it:

```kotlin
// Sequence — synchronous, cannot suspend:
val seq = sequence {
    yield(1)
    Thread.sleep(100)   // blocks the OS thread — other coroutines starve
    yield(2)
    // delay(100)       // COMPILE ERROR: RestrictsSuspension annotation on SequenceScope
}

// Flow — asynchronous, suspension-aware:
val flow = flow {
    emit(1)
    delay(100)          // suspends coroutine, OS thread freed for other work
    emit(2)
}
```

`Flow` is the **async, coroutine-aware counterpart** to `Sequence`. It can suspend at any point, emit from background threads, and participates fully in structured cancellation.

---

### What `flow { }` Compiles To — Why Cold Flows Are Cold

Every `flow { }` block compiles to a `SafeFlow` object that stores the lambda as a field. No producer code runs at construction time — the object is just a recipe:

```kotlin
val coldFlow: Flow<Int> = flow {
    emit(1)
    emit(2)
}
// Nothing runs. coldFlow is a SafeFlow object holding a lambda reference.
```

**Decompiled Java (simplified):**
```java
// flow { emit(1); emit(2) } creates:
Flow<Integer> coldFlow = new SafeFlow(
    new Function2<FlowCollector<Integer>, Continuation<?>, Object>() {
        @Override
        public Object invoke(FlowCollector<Integer> collector, Continuation<?> cont) {
            // emit(1) is a suspend call — passes Continuation downstream:
            Object r1 = collector.emit(1, cont);
            if (r1 == COROUTINE_SUSPENDED) return COROUTINE_SUSPENDED;
            return collector.emit(2, cont);
        }
    }
);

// coldFlow.collect { println(it) } calls:
// SafeFlow.collect(collector) → invokes the stored lambda with a new FlowCollector
// → emit(1) suspends producer until downstream prints 1 → RESUME → emit(2) → done
```

**Why this makes `Flow` cold:** `SafeFlow` is a passive object. No coroutine is spawned at construction. Each call to `.collect()` creates a *new* `FlowCollector` and invokes the lambda freshly — independent of any previous or concurrent collection.

**Why `emit()` suspends:** `emit()` is a `suspend fun`. After calling `emit(value)`, the producer coroutine suspends until the downstream `collect { }` block finishes processing that value. This is **natural backpressure** — the producer cannot outrun the consumer without explicit buffering.

```
Producer:   emit(1) ──SUSPEND──────────────────RESUME──► emit(2) ──SUSPEND──...
                     │                          ▲
Downstream:          ▼                          │
                 receives 1 → processes → signals done
```

---

### Hot Flow — Producer Runs Independently of Collectors

A hot flow has a producer that runs regardless of collectors. `MutableStateFlow` is always "on" — it holds state from construction:

```kotlin
val hotFlow = MutableStateFlow(0)   // already holds state — no collect() needed

viewModelScope.launch {
    hotFlow.value = 1; delay(100)
    hotFlow.value = 2
}

// Collector A (from the start): 0, 1, 2
// Collector B (joins after value=2): 2 only — missed history
```

```
Hot Flow (StateFlow):
Producer ──► [state:0] ──► [state:1] ──► [state:2] ──► ...  (runs independently)

Collector A:  0   →   1   →   2
Collector B:                  2   ← only current value
```

**The single source of truth model:** One `MutableStateFlow` in the ViewModel; multiple UI collectors all see the same state:

```kotlin
class UserViewModel : ViewModel() {
    private val _uiState = MutableStateFlow<UiState>(UiState.Loading)
    val uiState: StateFlow<UiState> = _uiState  // read-only public surface

    fun loadUser() {
        viewModelScope.launch {
            _uiState.value = UiState.Loading
            _uiState.value = UiState.Content(userRepository.getUser())
        }
    }
}
```

---

### ## Trap: SharedFlow Registration Race with DEFAULT Start Mode

When collecting a `SharedFlow` with `CoroutineStart.DEFAULT`, the collector coroutine is *scheduled* but not yet *registered* when the next line executes:

```kotlin
val sharedFlow = MutableSharedFlow<Int>(replay = 0)

// WRONG — race: collector scheduled but not yet registered
launch { sharedFlow.collect { println(it) } }
sharedFlow.emit(1)   // emitted before collector's coroutine starts → MISSED

// CORRECT — UNDISPATCHED: runs synchronously to first suspension point (collect())
launch(start = CoroutineStart.UNDISPATCHED) {
    sharedFlow.collect { println(it) }
    // collect() IS the first suspension point → runs here before launch returns
    // collector is registered before the next line executes
}
sharedFlow.emit(1)   // collector already registered → received ✓
```

`CoroutineStart.UNDISPATCHED` runs the coroutine body synchronously on the current thread until the first real suspension point. Since `collect()` immediately suspends (it waits for emissions), the collector is registered before `launch {}` returns. See [Q9.4](09_coroutines_execution_mechanics.md#q94--coroutine-start-modes).

---

### Backpressure — When Producer Is Faster Than Consumer

Default behaviour: `emit()` suspends until downstream finishes — natural lockstep. Explicit backpressure operators relax this:

```kotlin
// Default: lockstep — emit waits per item
flow { repeat(1000) { emit(it) } }.collect { delay(100) }

// buffer(n): producer runs n items ahead, then suspends
flow { repeat(1000) { emit(it) } }.buffer(10).collect { delay(100) }

// conflate(): producer never blocks; collector sees LATEST only
flow { repeat(1000) { emit(it) } }.conflate().collect { delay(100); println(it) }
// prints: 0, ~10, ~20 ... — most values skipped

// collectLatest: new item cancels previous processing
flow { repeat(1000) { emit(it); delay(10) } }.collectLatest { item ->
    delay(100)        // if new item arrives in 10ms: THIS IS CANCELLED
    println(item)     // only items that survive 100ms without interruption print
}
```

| Strategy | Producer blocked? | Consumer sees | Use when |
|---|---|---|---|
| Default | Yes — per item | Every item | Must process all |
| `buffer(n)` | After n items ahead | Every item | Bursty producer, steady consumer |
| `conflate()` | Never | Latest only | Only latest matters (sensor/UI state) |
| `collectLatest` | Never | Latest that completed | Cancel stale work on new item |

**`conflate()` vs `buffer(Channel.CONFLATED)` — same thing:** `conflate()` is syntactic sugar for `.buffer(Channel.CONFLATED)`. Both use `Channel(CONFLATED)` internally — a capacity-1 buffer that overwrites on overflow.

---

### `Sequence` vs `Flow` — Final Comparison

| Aspect | `Sequence<T>` | `Flow<T>` |
|---|---|---|
| Execution thread | Caller's thread (blocking) | Any dispatcher (non-blocking) |
| Can call `delay()` | ❌ compile error (`RestrictsSuspension`) | ✅ suspends coroutine |
| Cancellation-aware | ❌ | ✅ `CancellationException` propagates |
| Temperature | Cold | Cold by default; Hot via StateFlow/SharedFlow |
| Backpressure | Natural (pull model, synchronous) | Configurable: buffer, conflate, collectLatest |
| When to use | CPU-only lazy transforms, no I/O | Any async data stream |

---

### Memory Trick

```
COLD = SafeFlow object stores lambda. No coroutine until collect() invokes it.
  Each collect() = fresh lambda invocation = independent execution.
  emit() is suspend → producer waits per item → natural backpressure.

HOT = producer runs independently. Collectors tap into existing stream.
  StateFlow: AtomicRef holds current value. replay=1. equals() duplicate filter.
  SharedFlow: no duplicate filter. configurable replay/buffer.

## Trap: SharedFlow + DEFAULT start → collector scheduled, not yet registered → missed events.
  Fix: CoroutineStart.UNDISPATCHED → runs synchronously to collect() = first suspend point.

BACKPRESSURE:
  Default:       lockstep (emit suspends per item)
  buffer(n):     n items ahead, then suspends
  conflate():    only latest — sugar for buffer(CONFLATED)
  collectLatest: cancels previous processing when new item arrives

Sequence: blocks thread, no delay(), no cancellation, CPU-only.
Flow:     suspends, delay() works, CancellationException propagates, any dispatcher.
```

### Self-Test

1. Why can't you call `delay()` inside a `Sequence` block but you can in `flow { }`? What annotation is responsible?
2. `flow { emit(1) }` — write the decompiled Java. What is `SafeFlow`? Why is the flow cold by this implementation?
3. Why does `emit()` suspend? What is the consequence for a slow consumer with no buffering?
4. `MutableSharedFlow(replay=0)` — a value is emitted before any collector subscribes. What happens?
5. Show the SharedFlow registration race and the `UNDISPATCHED` fix. Trace the execution order.
6. `conflate()` vs `collectLatest` — both handle a slow consumer. What is the mechanical difference?

---

## Q11.2 — Flow Operators

> **Builds on:** [Q11.1 — Cold vs Hot Streams](#q111--cold-vs-hot-streams) · [Q4.2 — inline operators](04_functions_lambdas_inlining.md#q42--inline-noinline-crossinline)
> **Connects to:** [Q11.3 — StateFlow vs SharedFlow](#q113--stateflow-vs-sharedflow) · [Q10.3 — CancellationException in operators](10_structured_concurrency.md#q103--exception-handling-rules) · [Q7.2 — Sequences lazy pipeline](07_collections_and_sequences.md#q72--sequences-vs-eager-collections)

---

### The Concrete Picture — Instant Orientation

```
flatMapLatest — only latest search survives:
  keystrokes: "a" → "ap" → "app" → "apple"
  inner flows: [cancel] → [cancel] → [cancel] → [runs → result]
  Only "apple" search completes. Earlier searches cancelled mid-flight.

zip vs combine:
  zip:     flow1:──1────2────3──    combine:  flow1:──1─────────2──────3──
           flow2:────a────b────c──            flow2:────a──────────b────────
           out:──(1,a)─(2,b)─(3,c)           out:──(1,a)─(2,a)─(2,b)─(3,b)─
           Waits for BOTH                    Fires when EITHER changes
```

---

### Intermediate vs Terminal Operators — Bytecode Reality

Flow operators split into two kinds — exactly like `Sequence`:

**Intermediate operators** return a new `Flow` object immediately. They add a transformation to the pipeline but start nothing. They are NOT `suspend`.

**Terminal operators** are `suspend fun`s that call `.collect()` internally and drive actual execution.

```kotlin
flowOf(1, 2, 3, 4, 5)           // source — nothing runs
    .filter { it % 2 == 0 }     // intermediate — returns new Flow object, nothing runs
    .map { it * it }             // intermediate — wraps previous Flow, nothing runs
    .toList()                    // TERMINAL suspend fun → triggers collection → [4, 16]
```

**What an intermediate operator compiles to:**

```java
// .filter { it % 2 == 0 } generates (simplified):
new AbstractFlow<Integer>() {
    @Override
    public suspend void collect(FlowCollector<Integer> collector) {
        // delegate to upstream, only forward if predicate passes:
        upstream.collect(new FlowCollector<Integer>() {
            @Override
            public suspend Object emit(Integer value, Continuation cont) {
                if (value % 2 == 0) {
                    return collector.emit(value, cont); // forward
                }
                return Unit.INSTANCE; // skip
            }
        });
    }
}
```

Each intermediate operator is a lightweight `AbstractFlow` subclass that wraps the upstream `Flow` and overrides `collect()`. The whole chain is a nested wrapper — nothing executes until the terminal operator calls `.collect()` on the outermost wrapper.

```
Intermediate: filter, map, flatMapLatest, zip, combine, debounce,
              distinctUntilChanged, buffer, conflate, onEach, catch, take, drop
Terminal:     collect, toList, toSet, first, single, last, count, sum, fold, reduce
```

**Why intermediate operators are not `suspend`:** They return a `Flow` object immediately — no coroutine starts, no data flows. Only the terminal operator launches collection.

---

### `map` vs `flatMapLatest` — Mechanism Deep Dive

**`map`:** 1-to-1 synchronous transform. Processes each value in order, never cancels:

```kotlin
userIdFlow.map { id -> fetchUser(id) }
// fetchUser is called for EVERY emission, in order, sequentially
// Even if a new id arrives: current fetchUser completes first, THEN next id processed
```

**`flatMapLatest`:** each upstream value launches a **new inner `Flow`** as a child coroutine. When a NEW upstream value arrives, the current inner coroutine is cancelled via `CancellationException` before the new one starts:

```kotlin
searchQueryFlow.flatMapLatest { query ->
    flow {
        delay(300)                         // waits 300ms in inner coroutine
        emit(searchApi.search(query))      // only reaches here if not cancelled
    }
}
```

**Why cancellation prevents stale results:**

```
flatMapLatest timeline:
query "a"    ──► [child coroutine A: delay(300)...]
query "ap"       ──CANCEL A──► [child coroutine B: delay(300)...]
query "app"                    ──CANCEL B──► [child coroutine C: delay(300)...]
query "apple"                               ──CANCEL C──► [child coroutine D: delay(300)...search()...emit(result)]
                                                           ↑ only D completes — only one result emitted
```

Child coroutine A, B, C are cancelled via `CancellationException` at the next suspension point (`delay`). The cancelled coroutines never reach `emit()`. Only the inner flow for the last query emits a result.

---

### ## Trap: `map` Instead of `flatMapLatest` for Async Search

```kotlin
// WRONG: map calls the suspend function for EVERY keystroke — no cancellation
searchQueryFlow.map { query -> searchApi.search(query) }
// Interleaving scenario:
//   query "a"     → search starts, takes 500ms
//   query "apple" → search starts, takes 100ms
//   "apple" result arrives FIRST → displayed ✓
//   "a" result arrives 400ms later → OVERWRITES "apple" with STALE data ✗

// CORRECT: flatMapLatest — "a" search cancelled when "apple" arrives
searchQueryFlow.flatMapLatest { query ->
    flow { emit(searchApi.search(query)) }
}
// "a" search cancelled → stale result never emitted
```

---

### Complete Search Pattern — Each Operator Justified

```kotlin
searchEditText.textChanges()         // emits on every keystroke
    .debounce(300)                   // suppress emissions until 300ms of silence
    .filter { it.length >= 2 }       // ignore trivially short queries
    .distinctUntilChanged()          // skip if user typed same query again
    .flatMapLatest { query ->        // cancel previous search on new query
        searchRepository.search(query)
            .catch { emit(emptyList()) }  // per-search error recovery
    }
    .collect { results -> updateUI(results) }
```

**Why each operator is necessary:**
- `debounce(300)` — prevents one network call per keystroke; waits for a pause
- `filter { length >= 2 }` — single-char searches are too broad; skips before debounce
- `distinctUntilChanged()` — user types "ab", deletes "b", types "b" again: debounce lets it through, but query is identical. Prevents duplicate request for same string
- `flatMapLatest` — if two queries slip through debounce, only the latest matters
- `.catch { emit(emptyList()) }` — **placed inside `flatMapLatest`**: recovers per-search without killing the whole pipeline. If placed outside, one network error terminates all future searches permanently

---

### `catch` — Error Handling Without Terminating the Pipeline

```kotlin
// WRONG: uncaught exception terminates the flow — no more results ever
flow { emit(networkApi.fetch()) }
    .collect { updateUI(it) }    // one exception → flow dead

// CORRECT: catch recovers per-emission
flow { emit(networkApi.fetch()) }
    .catch { e ->
        emit(defaultValue)       // substitute safe default — flow continues
        // or: log and rethrow to propagate
    }
    .collect { updateUI(it) }

// CRITICAL: catch only catches UPSTREAM errors
flow { emit(1) }
    .catch { e -> println("caught: $e") }   // would catch errors from emit()
    .collect { value ->
        throw RuntimeException("downstream") // NOT caught by .catch — propagates to scope
    }
```

`catch` intercepts `Throwable` from upstream operators and the flow builder itself. Exceptions thrown inside `collect { }` bypass `catch` entirely — they propagate directly to the coroutine scope.

**`catch` + rethrow for logging:**
```kotlin
.catch { e ->
    Timber.e(e, "Search failed")
    throw e   // rethrow after logging — terminates flow but caller knows why
}
```

---

### `distinctUntilChanged` — Mechanism and Data Class Trap

Emits only when the value differs from the previous emission using `equals()`:

```kotlin
flow { emit(1); emit(1); emit(2); emit(2); emit(3) }
    .distinctUntilChanged()
    .collect { println(it) }   // prints: 1, 2, 3
```

**Why `equals()` matters for custom classes:**

```kotlin
// data class: equals() compares by value → works correctly
data class User(val id: Int, val name: String)
flow { emit(User(1, "Alice")); emit(User(1, "Alice")) }
    .distinctUntilChanged()
    .collect { println(it) }
// prints: User(1, "Alice") once ← second filtered, same content ✓

// regular class: equals() = reference equality → every emission distinct
class User(val id: Int, val name: String)  // no data class
flow { emit(User(1, "Alice")); emit(User(1, "Alice")) }
    .distinctUntilChanged()
    .collect { println(it) }
// prints BOTH ← different objects despite same fields — reference comparison ✗
```

Custom key extraction: `.distinctUntilChangedBy { it.id }` — only filter if id is same (name change still emits).

---

### `zip` vs `combine` — When Each Fires

**`zip`:** pairs elements one-to-one. Waits for BOTH flows to produce a new value before emitting:

```kotlin
flowOf(1, 2, 3)
    .zip(flowOf("a", "b", "c")) { num, letter -> "$num$letter" }
    .collect { println(it) }   // 1a, 2b, 3c
// If one flow is faster, it WAITS. Emission only when BOTH have new values.
```

**`combine`:** emits whenever EITHER flow produces a value, using the **latest** from both:

```kotlin
val temperature = MutableStateFlow(20)
val humidity    = MutableStateFlow(50)

combine(temperature, humidity) { temp, hum -> "T:$temp H:$hum" }
    .collect { println(it) }

temperature.value = 25   // → "T:25 H:50"   humidity unchanged — uses latest
humidity.value    = 60   // → "T:25 H:60"   temperature unchanged — uses latest
```

```
zip     = LOCKSTEP. Waits for BOTH. Output count = min(flow1 count, flow2 count).
combine = REACTIVE. Fires on EITHER. Uses LATEST from each. Output = every change.
```

**When to use which:**
- `zip`: pairing corresponding items — request/response pairs, parallel results to merge
- `combine`: any reactive dashboard — temperature + humidity, user + settings, price + quantity

---

### Memory Trick

```
INTERMEDIATE operators = AbstractFlow subclass wrapping upstream. Nothing runs.
TERMINAL operators (collect, toList, first) = suspend funs that drive collection.

map          → 1-to-1 transform, sequential, no cancellation.
flatMapLatest → each value: cancel previous inner coroutine, launch new one.
               CancellationException at suspension point (delay/network) stops stale work.

## Trap: map { suspend fun } for search → stale overwrites fresh.
   Fix: flatMapLatest → cancel previous before starting new.

catch { }  → catches UPSTREAM errors only. Collect-side errors bypass it.
             Inside flatMapLatest: per-search recovery. Outside: one error = pipeline dead.

distinctUntilChanged → equals(). data class: value equality ✓. Regular class: reference ✗.

zip     = LOCKSTEP. Waits for BOTH new values. Corresponding pairs.
combine = REACTIVE. Fires on EITHER. Latest from each. Dashboard/reactive state.

FULL SEARCH PIPELINE:
  textChanges → debounce(300) → filter(len≥2) → distinctUntilChanged
    → flatMapLatest { search().catch { emptyList() } } → collect
```

### Self-Test

1. What is the difference between intermediate and terminal operators? Write the decompiled Java for `.filter { }`. Why is `filter` not `suspend`?
2. `map { searchApi.search(query) }` vs `flatMapLatest { flow { emit(searchApi.search(query)) } }` — what happens when a new query arrives while the previous is in flight? Trace each.
3. Why does `flatMapLatest` prevent stale results? Name the coroutine mechanism and the specific exception used.
4. In the search pipeline, why is `.catch { emit(emptyList()) }` placed *inside* `flatMapLatest`, not outside? What breaks if it's outside?
5. `data class User` vs `class User` in `distinctUntilChanged()` — why different behaviour? Trace to `equals()`.
6. Prices flow + quantities flow: you want a running total updating on any change. `zip` or `combine`? Why?

---

## Q11.3 — `StateFlow` vs `SharedFlow`

> **Builds on:** [Q11.1 — Hot vs Cold](#q111--cold-vs-hot-streams) · [Q9.2 — CoroutineContext](09_coroutines_execution_mechanics.md#q92--coroutine-context-and-dispatchers) · [Q10.4 — viewModelScope](10_structured_concurrency.md#q104--lifecycle-scopes-and-process-death)
> **Connects to:** [Q11.4 — Collection lifecycle](#q114--flow-collection-and-lifecycle) · [Q13.4 — LiveData vs StateFlow](13_android_architecture.md#q134--livedata-vs-stateflow-vs-sharedflow)

---

### The Concrete Picture — Instant Orientation

```
StateFlow navigation bug #1 — duplicate filter:
  nav.value = "Detail"   → navigates ✓
  nav.value = "Detail"   → SAME VALUE → equals() → NOT emitted → silently dropped ✗

StateFlow navigation bug #2 — rotation replay:
  ViewModel survives rotation. nav still holds "Detail".
  New Activity subscribes → replay=1 → immediately receives "Detail" → navigates AGAIN ✗

SharedFlow fix:
  MutableSharedFlow(replay=0)   → no cached events → no rotation replay
                                → no duplicate filter → every emit delivers
```

---

### `StateFlow` — Internals Derived From Implementation

`MutableStateFlow` is backed by an atomic state reference and a list of suspended collectors. Setting `.value` performs a CAS loop and notifies collectors only if the value changed:

```java
// MutableStateFlow internals (simplified decompiled Java):
public final Object setValue(Object newValue) {
    // CAS loop: atomically swap state
    State oldState = (State) this.state.getAndSet(new State(newValue));

    // equals() check — if same: early return, NO collector notification
    if (Objects.equals(newValue, oldState.value)) return Unit.INSTANCE;

    // Different value: wake all suspended collectors
    notifyCollectors();   // resumes each suspended collect { } coroutine
    return Unit.INSTANCE;
}
```

**Four properties that fall out of this implementation:**

1. **Always has a current value** — `AtomicReference` initialised in constructor; `.value` never null unless `T` is nullable
2. **replay = 1** — new collectors synchronously receive current `.value` on subscription
3. **Duplicate filtering** — the `equals()` check in `setValue` means identical consecutive values silently dropped
4. **Thread-safe reads** — `state.get().value` is a single atomic load; no external lock needed

---

### ## Trap 1: `StateFlow` Drops Duplicate Events

```kotlin
// WRONG: StateFlow for navigation
class MyViewModel : ViewModel() {
    val navigateTo = MutableStateFlow<String?>(null)

    fun onDetailClick() {
        navigateTo.value = "DetailScreen"   // first click → emitted ✓ → navigates
        // user navigates back, ViewModel alive, navigateTo still = "DetailScreen"
        navigateTo.value = "DetailScreen"   // same value → equals() → NOT emitted → dropped ✗
    }
}
```

**Root cause:** `setValue` calls `Objects.equals(newValue, oldState.value)`. `"DetailScreen".equals("DetailScreen")` = `true` → early return → no collector notification → navigation never fires.

---

### ## Trap 2: `StateFlow` Replay Causes Double Navigation on Rotation

```kotlin
// Rotation sequence with StateFlow:
// 1. navigateTo.value = "DetailScreen"  → navigates ✓
// 2. User rotates phone
// 3. Old Activity destroyed → old collector cancelled
// 4. New Activity created → subscribes to navigateTo
// 5. StateFlow replay=1 → immediately emits "DetailScreen" to new subscriber
// 6. New Activity navigates to "DetailScreen" AGAIN → double navigation ✗
```

Both bugs stem from the same design: `StateFlow` is designed for *state* (current value always valid, always emit to new subscriber). Using it for *events* (fire-once, no replay) is the wrong abstraction.

---

### `SharedFlow` — Correct for One-Shot Events

```kotlin
// CORRECT: SharedFlow for navigation events
class MyViewModel : ViewModel() {
    private val _nav = MutableSharedFlow<String>(
        replay = 0,                                   // no cached events for new subscribers
        extraBufferCapacity = 1,                      // buffer 1 if no subscriber momentarily
        onBufferOverflow = BufferOverflow.DROP_OLDEST // never suspend ViewModel on emit
    )
    val nav = _nav.asSharedFlow()

    fun onDetailClick() {
        viewModelScope.launch { _nav.emit("DetailScreen") }
        // every click emits — no equals() filter
        // after rotation: new subscriber gets NO replay → no double navigation ✓
    }
}
```

**Why each parameter:**
- `replay = 0` — new subscribers (new Activity after rotation) receive nothing cached → no double navigation
- `extraBufferCapacity = 1` — if collector is momentarily absent (Activity mid-recreation), event buffers for 1 slot instead of suspending the ViewModel
- `DROP_OLDEST` on overflow — if buffer full (multiple fast clicks + no collector), oldest pending event dropped; ViewModel never suspends

---

### ## Trap 3: Forcing Re-emission of the Same `StateFlow` Value

Sometimes you genuinely need to re-trigger state that hasn't changed — e.g., re-show a validation error after an external change:

```kotlin
// WRONG: StateFlow ignores same value
_uiState.value = UiState.Error("validation failed")
_uiState.value = UiState.Error("validation failed")   // silently ignored ✗

// Option A: sentinel round-trip
_uiState.value = UiState.Idle                          // different → emitted
_uiState.value = UiState.Error("validation failed")    // different from Idle → emitted ✓

// Option B: SharedFlow trigger → StateFlow state
private val _revalidate = MutableSharedFlow<Unit>(extraBufferCapacity = 1)
// ViewModel collects _revalidate → recomputes → pushes to _uiState

// Option C: Versioned<T> wrapper — version always differs
data class Versioned<T>(val value: T, val version: Int)
_uiState.value = Versioned(UiState.Error("validation failed"), version++)
// version++ → equals() always false → always emitted ✓
```

---

### `StateFlow` vs `SharedFlow` — Configuration Comparison

| Property | `StateFlow` | `SharedFlow` |
|---|---|---|
| Initial value | Required | None |
| `replay` | Fixed = 1 | Configurable: 0, 1, N |
| Duplicate filtering | Yes — `equals()` in `setValue` | No |
| Thread-safe `.value` read | Yes — single atomic load | N/A — use `replayCache` |
| Good for | UI state (Loading/Content/Error) | Events, one-shot actions |
| Bad for | Navigation, snackbars, dialogs | Sharing current state to new subscribers |

---

### `stateIn` and `shareIn` — Cold Flow to Hot

Cold flows (Room queries, API calls) re-execute per collector. `stateIn`/`shareIn` converts them to hot so multiple collectors share one upstream subscription:

```kotlin
// Without stateIn: each collector triggers a new DB query
val userFlow: Flow<User> = userDao.getUser()   // cold — new query per collect()

// With stateIn: ONE upstream query, multiple downstream collectors share it
val user: StateFlow<User?> = userFlow.stateIn(
    scope = viewModelScope,
    started = SharingStarted.WhileSubscribed(5000),
    initialValue = null
)
```

**`SharingStarted` — derived from each policy's cost:**

| Policy | Starts when | Stops when | Cost / risk |
|---|---|---|---|
| `Eagerly` | `stateIn` called | Never | Upstream runs even with 0 subscribers |
| `Lazily` | First subscriber | Never | Keeps upstream alive even after all leave |
| `WhileSubscribed(N)` | First subscriber | N ms after last subscriber | Restarts upstream after long absence |

**Why 5000ms is the standard for `WhileSubscribed`:** A configuration change (rotation) destroys the Activity (last subscriber leaves) then recreates it (new subscriber arrives). This round-trip takes 200–500ms. `5000ms` comfortably survives multiple fast rotations while still shutting down the upstream if the user genuinely navigates away for >5 seconds.

```kotlin
// Full pattern: combine multiple cold flows into one shared StateFlow
val uiState: StateFlow<UiState> = combine(userFlow, settingsFlow) { user, settings ->
    UiState(user = user, theme = settings.theme)
}.stateIn(
    scope = viewModelScope,
    started = SharingStarted.WhileSubscribed(5000),
    initialValue = UiState.Loading
)
```

---

### Memory Trick

```
StateFlow  = CURRENT STATE. AtomicReference + CAS. equals() in setValue.
  replay=1 (new subscriber gets current value immediately).
  Duplicate filter: equals() true → early return → no notification → event DROPPED.
  Good: UI state. Bad: events.

SharedFlow = EVENT STREAM. No duplicate filter. Configurable replay/buffer.
  replay=0 + extraBufferCapacity=1 + DROP_OLDEST = correct navigation event pattern.

## TRAP 1: StateFlow drops duplicate events (equals() in setValue).
## TRAP 2: StateFlow replays on rotation (replay=1 → new Activity gets last event).
## TRAP 3: Can't force-emit same StateFlow value.
  Options: sentinel round-trip / SharedFlow trigger / Versioned<T>.

stateIn SharingStarted:
  Eagerly          = starts now (pre-warm). Runs even with 0 subscribers.
  Lazily           = starts on first sub, never stops. Leaks if expensive.
  WhileSubscribed(5000) = stops 5s after last sub. 5000 > config-change time (~500ms).
```

### Self-Test

1. What backing data structure does `MutableStateFlow` use? Write the decompiled Java for `setValue` and identify the line that causes duplicate filtering.
2. Two `StateFlow` bugs for navigation — name both, trace each to the implementation.
3. `MutableSharedFlow(replay=0, extraBufferCapacity=1, DROP_OLDEST)` — explain what each parameter prevents in a navigation event use case.
4. `SharingStarted.WhileSubscribed(5000)` — why 5000ms? What would happen with 0ms?
5. *"I need to re-show the same validation error. `StateFlow` ignores my second emit."* — What are the three workarounds?
6. `stateIn` vs `shareIn` — when would you choose `shareIn` over `stateIn`?

---

## Q11.4 — Flow Collection and Lifecycle

> **Builds on:** [Q11.3 — StateFlow/SharedFlow](#q113--stateflow-vs-sharedflow) · [Q10.4 — Lifecycle Scopes](10_structured_concurrency.md#q104--lifecycle-scopes-and-process-death) · [Q10.3 — CancellationException](10_structured_concurrency.md#q103--exception-handling-rules)
> **Connects to:** [Q11.3 — StateFlow collection](#q113--stateflow-vs-sharedflow)

---

### The Concrete Picture — Instant Orientation

```
lifecycleScope.launch { flow.collect { updateUI() } }
  → onStop() (app goes to background) → collect KEEPS RUNNING → updateUI() on hidden views

viewLifecycleOwner.lifecycleScope.launch {
    viewLifecycleOwner.repeatOnLifecycle(STARTED) {
        flow.collect { updateUI() }
    }
}
  → onStart()  → collect STARTS
  → onStop()   → collect CANCELLED
  → onStart()  → collect RESTARTS
  → Only updates visible UI ✓
```

---

### ## Trap 1: `lifecycleScope.launch { collect }` — Always-Running Bug

```kotlin
// WRONG: collection continues even when app is in background
class MyFragment : Fragment() {
    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        lifecycleScope.launch {                          // Fragment's lifecycleScope
            viewModel.uiState.collect { state ->
                updateUI(state)   // called even when STOPPED (user pressed Home)
            }
        }
    }
}
// lifecycleScope is cancelled on DESTROY — not on STOP.
// When user presses Home: Fragment → STOPPED. lifecycleScope: still alive.
// collect: still running. updateUI(): wasted CPU, battery, potential stale state.

// CORRECT: collection pauses with lifecycle
class MyFragment : Fragment() {
    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        viewLifecycleOwner.lifecycleScope.launch {
            viewLifecycleOwner.repeatOnLifecycle(Lifecycle.State.STARTED) {
                viewModel.uiState.collect { state ->
                    updateUI(state)   // ONLY called when lifecycle ≥ STARTED
                }
            }
        }
    }
}
```

---

### `repeatOnLifecycle(STARTED)` — Mechanism

`repeatOnLifecycle` installs a `LifecycleEventObserver`. On `ON_START`, it launches the inner block as a **child coroutine**. On `ON_STOP`, it cancels that child coroutine via `CancellationException`:

```
Lifecycle:  onCreate  onStart      onStop    onStart      onDestroy
                       ↓            ↓          ↓            ↓
Inner block:           LAUNCH──────►CANCEL     LAUNCH──────►CANCEL
                       [collect                [collect
                        running]                running]
Outer coroutine:       ─────────────────────────────────────►CANCEL
```

Each `ON_START` event creates a **new** collect coroutine — the Flow pipeline is re-subscribed from scratch. For cold flows, this re-executes the producer. For `StateFlow`, the new collector immediately receives the current value.

---

### ## Trap 2: Fragment `lifecycleScope` vs `viewLifecycleOwner.lifecycleScope`

A Fragment has two distinct lifecycles:
- **Fragment lifecycle** (`this.lifecycleScope`): from `onAttach()` to `onDetach()`. Survives back-stack placement.
- **View lifecycle** (`viewLifecycleOwner.lifecycleScope`): from `onCreateView()` to `onDestroyView()`. Cancelled when views are destroyed.

```kotlin
// WRONG: using Fragment's own lifecycle in onViewCreated
override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
    lifecycleScope.launch {                           // Fragment lifecycle
        repeatOnLifecycle(Lifecycle.State.STARTED) {
            viewModel.state.collect { state ->
                binding.textView.text = state.text    // binding reference!
            }
        }
    }
}
// When Fragment goes to back stack:
//   onDestroyView() → binding = null, views destroyed
//   Fragment lifecycle: STILL STARTED (Fragment object alive in back stack)
//   repeatOnLifecycle(STARTED): inner coroutine NOT cancelled (lifecycle is STARTED)
//   collect still running → binding.textView.text → NullPointerException ✗

// CORRECT: viewLifecycleOwner — tied to VIEW lifecycle
override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
    viewLifecycleOwner.lifecycleScope.launch {        // view lifecycle
        viewLifecycleOwner.repeatOnLifecycle(Lifecycle.State.STARTED) {
            viewModel.state.collect { state ->
                binding.textView.text = state.text
            }
        }
    }
}
// onDestroyView() → viewLifecycleOwner lifecycle → DESTROYED
//   → outer lifecycleScope coroutine cancelled → collect stops → binding safe ✓
```

---

### ## Trap 3: `flow { }` Is NOT Concurrent-Safe — `emit()` From a Child Coroutine

Inside `flow { }`, `emit()` can only be called from the same coroutine that entered the builder. Launching a child coroutine and calling `emit()` from it throws:

```kotlin
// WRONG: emit from a child coroutine
val flow = flow<Int> {
    launch {           // new coroutine — different coroutine context
        emit(1)        // THROWS: IllegalStateException (Flow invariant violation)
    }
}
// Why: FlowCollector.emit is not thread-safe. SafeFlow installs a
// ContextPreservingCollector that checks the calling context on each emit().
// Calling from a different coroutine = different context = exception.

// CORRECT: channelFlow for concurrent emission
val flow = channelFlow<Int> {
    launch { send(1) }   // Channel.send is concurrent-safe
    launch { send(2) }   // two producers, one channel — fine
}
// channelFlow wraps a Channel internally; send() uses Channel's lock-free queue.
// Results arrive in completion order (whichever launch finishes first).
```

**When you need `channelFlow`:**
- Emitting from multiple parallel coroutines (fan-out + collect)
- Wrapping callback-based APIs where the callback fires on a different thread
- Parallel network calls emitting as they complete

```kotlin
// channelFlow vs flow + flatMapMerge:
// flatMapMerge: each upstream value launches concurrent inner flows, results merged
// channelFlow:  manual control — you decide which coroutines to launch and when to send
// Use flatMapMerge when: uniform concurrency over a stream of inputs
// Use channelFlow when: heterogeneous concurrent producers or callback wrapping
val parallel = channelFlow {
    listOf("url1", "url2", "url3").forEach { url ->
        launch { send(api.fetch(url)) }   // all three in parallel
    }
}
```

---

### Compose: `collectAsState` vs `collectAsStateWithLifecycle`

```kotlin
@Composable
fun MyScreen(viewModel: MyViewModel) {
    // WRONG: always collecting, even when Composable is invisible
    val state by viewModel.uiState.collectAsState()
    // collectAsState uses rememberCoroutineScope — no lifecycle awareness

    // CORRECT: stops collecting when LifecycleOwner drops below STARTED
    val state by viewModel.uiState.collectAsStateWithLifecycle()
    // equivalent to repeatOnLifecycle(STARTED) for Compose
    // from: androidx.lifecycle:lifecycle-runtime-compose
}
```

---

### What Happens to In-Flight Emissions on Cancel

When `repeatOnLifecycle` cancels the inner collect coroutine on `onStop()`:

```
Cold flow (Room query wrapped in flow { }):
  CancellationException propagates upstream → producer coroutine cancelled → query stops.
  On next onStart(): NEW collect coroutine → flow re-subscribed → fresh producer execution.

Hot flow (StateFlow):
  Producer continues running — it's independent of any collector.
  Cancelled collector is removed from subscriber list.
  New emissions NOT delivered to cancelled collector.
  On next onStart(): new collect coroutine → re-subscribes → immediately gets current value (replay=1).

SharedFlow(replay=0):
  Events emitted while collector is inactive (between onStop and onStart): LOST.
  Use replay=1 or Channel if events must survive collector absence.
```

---

### Memory Trick

```
lifecycleScope.launch { collect }      → DESTROY-only cancel. WRONG: runs in background.
repeatOnLifecycle(STARTED) { collect } → STOP/START aware. CORRECT.

Mechanism: LifecycleEventObserver.
  ON_START → launch inner coroutine (collect begins).
  ON_STOP  → cancel inner coroutine via CancellationException (collect stops cleanly).
  ON_START → launch fresh coroutine again (cold: re-executes; hot: gets current value).

## Trap 1: lifecycleScope vs viewLifecycleOwner.lifecycleScope in Fragment.
  Back stack: Fragment STARTED, views DESTROYED, binding = null.
  Fragment lifecycle → collect runs → NPE.
  viewLifecycleOwner → cancelled on onDestroyView → safe.

## Trap 2: flow { launch { emit() } } → IllegalStateException.
  flow { } is NOT concurrent-safe. emit() must be in same coroutine.
  Fix: channelFlow { send() } — Channel.send is concurrent-safe.
  channelFlow vs flatMapMerge: channel = manual control, flatMapMerge = uniform concurrency.

Compose:
  collectAsState()              → no lifecycle awareness. Runs in background. WRONG.
  collectAsStateWithLifecycle() → repeatOnLifecycle(STARTED) equivalent. CORRECT.
```

### Self-Test

1. `lifecycleScope.launch { flow.collect { updateUI() } }` — what exactly is the bug? When is `lifecycleScope` cancelled vs when is it not?
2. How does `repeatOnLifecycle(STARTED)` work mechanically? What does it install and what does it launch/cancel?
3. Fragment `lifecycleScope` vs `viewLifecycleOwner.lifecycleScope` — show the crash scenario on back-stack navigation step by step.
4. Why does `flow { launch { emit(1) } }` throw? What class checks the calling context? What is the fix?
5. When `repeatOnLifecycle` cancels a `StateFlow` collect on `onStop()` — what happens to the `StateFlow`'s producer? What does the new collector receive on `onStart()`?
6. `collectAsState()` vs `collectAsStateWithLifecycle()` — mechanical difference in Compose.

---

## Q11.5 — Channels: Hot Streams with Backpressure

> **Builds on:** [Q11.1 — Cold vs Hot Streams](#q111--cold-vs-hot-streams) · [Q11.3 — StateFlow vs SharedFlow](#q113--stateflow-vs-sharedflow) · [Q9.3 — launch vs async](09_coroutines_execution_mechanics.md#q93--launch-vs-async)
> **Connects to:** [Q10.6 — Mutex](10_structured_concurrency.md#q106--mutex-and-synchronization-primitives) · [Q10.5 — select Expression](10_structured_concurrency.md#q105--select-expression)

---

### The Concrete Picture — Instant Orientation

```
Channel = coroutine-safe queue with suspension protocol

Producer:  send(1)─► send(2)─► send(3)─► [buffer full → SUSPEND]
Channel:   [1][2]    [1][2]    [2][3]↑                  [3]
Consumer:             receive→1          receive→2  ──► producer resumes

SharedFlow: one producer → ALL collectors get each item (broadcast)
Channel:    one producer → ONE receiver per item (queue — item consumed once)
```

---

### What Channels Are — Derived From the Problem

`StateFlow` and `SharedFlow` broadcast to all subscribers. But what if each work item must be processed by **exactly one** consumer — like a job queue? That is what `Channel` solves.

```
SharedFlow = broadcast bus.    emit(x) → every subscriber gets x simultaneously.
Channel    = work queue.       send(x) → exactly one receiver gets x. Item gone after consume.
```

A `Channel` is a coroutine-safe queue with a suspension protocol:
- `send(value)` — suspends the **producer** coroutine if the buffer is full (no thread blocked)
- `receive()` — suspends the **consumer** coroutine if the buffer is empty (no thread blocked)

---

### Channel Internals — Lock-Free Queue

`Channel` is backed by a **lock-free linked list** (`AbstractChannel` in kotlinx.coroutines). When `send()` is called:

1. **Receiver already waiting:** atomically pair via CAS, resume the receiver's `Continuation`, return immediately
2. **Buffer has space:** enqueue the value, return immediately
3. **Buffer full:** enqueue a `SendElement` (wrapper around the sender's `Continuation`), suspend the sender

```java
// Conceptual decompiled send():
public Object send(Object value, Continuation cont) {
    // Try to hand off directly to a waiting receiver:
    if (casOfferToReceiver(value)) return Unit.INSTANCE;   // immediate: CAS succeeded

    // Try to buffer:
    if (offer(value)) return Unit.INSTANCE;                // buffered: no suspension

    // Buffer full: enqueue sender's continuation, suspend:
    enqueueSender(new SendElement(value, cont));
    return COROUTINE_SUSPENDED;                            // caller suspends
}
```

Cost of suspension/resumption: one CAS + `resumeWith()` call — no OS lock, no thread context switch.

---

### Buffer Strategies — Derived From Suspension Model

Each strategy determines when `send()` suspends:

```kotlin
// Rendezvous (buffer = 0, the default):
Channel<Int>()
// send() suspends IMMEDIATELY until a receiver calls receive().
// Sender and receiver must meet at the same point in time.
// Use: tight coupling — producer should pace itself to consumer speed.

// Buffered:
Channel<Int>(capacity = 64)
// send() suspends only when 64 items are queued and unread.
// Producer can run 64 items ahead before being throttled.
// Use: bursty producer, steady consumer — smooth timing differences.

// Conflated:
Channel<Int>(Channel.CONFLATED)
// send() NEVER suspends. Only the LATEST value is kept.
// New send() atomically overwrites the previous unread value.
// Use: only latest matters (sensor readings, UI state updates).

// Unlimited:
Channel<Int>(Channel.UNLIMITED)
// send() NEVER suspends. Buffer grows without bound.
// DANGER: if consumer can't keep up → unbounded heap growth → OOM.
// Use: only when production is provably finite and consumer will catch up.
```

```
Buffer size = 2, producer faster than consumer:

Producer: send(1)  send(2)  send(3) ←SUSPEND    send(4)
                                      ↑resumes when consumer reads
Channel:  [1]      [1,2]    [1,2]    [2,3]       [3,4]
Consumer:                    recv→1              recv→2
```

---

### `produce` Builder — Preferred Pattern

`produce` creates a `ReceiveChannel` with a built-in producer coroutine that auto-closes the channel when the block ends or throws:

```kotlin
fun CoroutineScope.numbers(): ReceiveChannel<Int> = produce {
    for (i in 1..10) {
        send(i)
        delay(100)
    }
    // Block ends → channel automatically closed → consumer for-loop terminates
}

val nums = numbers()
for (n in nums) { println(n) }   // prints 1..10 then exits cleanly
```

**If the producer throws:** the channel is closed with the exception. The consumer's `for (n in channel)` rethrows it at the receive site. Structured concurrency: if the consumer's scope is cancelled, the producer coroutine is cancelled too.

---

### ## Trap: Forgetting to Close a Channel — Coroutine Leak

An unclosed channel causes the consumer coroutine to suspend forever:

```kotlin
// WRONG: channel never closed → consumer stuck indefinitely
val channel = Channel<String>()
launch { channel.send("hello") }
launch {
    for (msg in channel) {    // iterates until channel CLOSED
        println(msg)          // prints "hello"
    }
    println("Done")           // NEVER REACHED — suspended waiting for more items
}
// channel.close() never called → consumer coroutine leaks forever

// CORRECT: explicit close
launch {
    channel.send("hello")
    channel.close()           // signals: no more items → for-loop terminates
}

// BEST: produce {} — auto-closes, no footgun
val ch = produce { send("hello") }
for (msg in ch) { println(msg) }
println("Done")   // reached ✓
```

---

### Channel for One-Shot UI Events — Why Channel Over `SharedFlow`

```kotlin
// Channel for events — robust delivery:
class MyViewModel : ViewModel() {
    private val _events = Channel<UiEvent>(Channel.BUFFERED)  // capacity = 64
    val events: Flow<UiEvent> = _events.receiveAsFlow()       // expose as Flow

    fun onNavigateClick() {
        viewModelScope.launch {
            _events.send(UiEvent.NavigateToDetail)
            // Event buffered if collector momentarily absent (Activity recreating)
            // Each event delivered to exactly ONE collector — not broadcast
        }
    }
}

// Activity collects with repeatOnLifecycle:
viewLifecycleOwner.lifecycleScope.launch {
    viewLifecycleOwner.repeatOnLifecycle(STARTED) {
        viewModel.events.collect { event -> handleEvent(event) }
    }
}
// If Activity recreates: new collector resumes, buffered events delivered in order
```

**Why Channel beats `SharedFlow(replay=0)` for events:** Each `send()` puts an item in the queue. The item waits there until exactly one `receive()` consumes it. Even if the collector is briefly absent (Activity recreating), the event stays in the buffer — guaranteed delivery. `SharedFlow(replay=0)` with no `extraBufferCapacity` drops events if no collector is active when `emit()` is called.

---

### `select` With Channels

Channels integrate with `select` to race multiple queues — process whichever has data first:

```kotlin
val updates = Channel<String>()
val alerts  = Channel<String>()

repeat(10) {
    select<Unit> {
        updates.onReceive { msg -> handleUpdate(msg) }
        alerts.onReceive  { msg -> handleAlert(msg) }
    }
}
```

When both channels have data simultaneously, `select` picks the first clause by default (bias). See [Q10.5](10_structured_concurrency.md#q105--select-expression) for bias and loser-cancellation rules.

---

### Flow vs SharedFlow vs Channel — Decision Table

| | `Flow` | `SharedFlow` | `Channel` |
|---|---|---|---|
| Temperature | Cold | Hot | Hot |
| Multiple collectors | Each gets own stream | ALL get every emission | ONE receiver per item |
| Delivery guarantee | Per-collector independent | Broadcast to all active | Queue — survives absent collector |
| Backpressure | Natural (`emit` suspends) | Configurable buffer | Configurable buffer |
| Operators (`map`, `filter`) | Rich set | Via `.asFlow()` | Via `.consumeAsFlow()` |
| Must close? | No | No | YES — or consumer leaks |
| Use for | Data streams, transforms | State broadcast, events | Work queues, one-item-once |

---

### Memory Trick

```
Channel = COROUTINE-SAFE QUEUE. Lock-free linked list.
  send()    → suspends if buffer full (CAS → enqueue Continuation).
  receive() → suspends if buffer empty (CAS → enqueue Continuation).
  Neither blocks an OS thread. One CAS + resumeWith = full cost.

BUFFER STRATEGIES (when does send() suspend?):
  Rendezvous(0) → immediately (sender waits for receiver rendezvous)
  Buffered(64)  → when 64 items in queue
  Conflated     → never (only latest kept — CAS overwrites previous)
  Unlimited     → never (OOM risk — use only for finite, bounded production)

## TRAP: Forgetting close() → consumer for-loop suspends forever = coroutine leak.
  BEST: produce { } — auto-closes on block end or exception.

Channel vs SharedFlow:
  SharedFlow = broadcast (all active subscribers get each item)
  Channel    = queue (exactly one receiver per item, buffers during absence)

For one-shot UI events:
  SharedFlow(replay=0, extraBufferCapacity=1): fine, but can drop if buffer fills
  Channel(BUFFERED).receiveAsFlow(): robust — 64-item buffer, guaranteed one-consumer delivery
```

### Self-Test

1. What is the internal data structure backing `Channel`? Write the conceptual decompiled Java for `send()`. How does it avoid blocking an OS thread?
2. When does `send()` suspend for each of the four buffer strategies? Derive from the suspension model.
3. Why must channels be closed? Show the coroutine leak scenario. What does `produce` guarantee?
4. `Channel(BUFFERED).receiveAsFlow()` vs `MutableSharedFlow(replay=0, extraBufferCapacity=1)` for one-shot events — what does Channel guarantee that SharedFlow cannot?
5. If a `produce { }` block throws an exception, what happens to the consumer's `for (n in channel)` loop?
6. `select` with two channels — both have data simultaneously. Which is processed? What happens to the other?

---

## Master Summary: Flow in 5 Points

```
1. COLD vs HOT
   Cold (flow { }): SafeFlow stores lambda. Nothing runs until collect().
     Each collect() = fresh producer execution. emit() is suspend = natural backpressure.
   Hot (StateFlow/SharedFlow): always running. Collectors tap into ongoing stream.
   SharedFlow + DEFAULT start → registration race → use UNDISPATCHED.

2. OPERATORS
   Intermediate = AbstractFlow subclass wrapping upstream. Not suspend. Lazy.
   Terminal = suspend fun (collect, toList, first) — drives execution.
   flatMapLatest: each value launches inner Flow as child coroutine.
     New value → CancellationException → inner cancelled → stale result never emits.
   catch { }: upstream errors only. Collect-side errors bypass it.
   zip = lockstep pairs. combine = fire on either, use latest from each.

3. StateFlow vs SharedFlow
   StateFlow: AtomicRef + equals() in setValue → duplicate filter → replay=1.
     Wrong for events: drops duplicates + replays on rotation.
   SharedFlow: no filter, configurable replay/buffer.
     (replay=0, extraBufferCapacity=1, DROP_OLDEST) = correct event pattern.
   stateIn(WhileSubscribed(5000)): one upstream subscription, survives rotation.

4. LIFECYCLE COLLECTION
   lifecycleScope.launch { collect }: cancelled on DESTROY only. Runs in background. WRONG.
   repeatOnLifecycle(STARTED): LifecycleEventObserver → launch on START, cancel on STOP.
   Fragment: viewLifecycleOwner (VIEW lifecycle) not this (FRAGMENT lifecycle).
   flow { emit from child coroutine } → IllegalStateException. Fix: channelFlow { send }.
   Compose: collectAsStateWithLifecycle ✓, collectAsState ✗.

5. CHANNELS
   Lock-free queue. send() suspends if full, receive() suspends if empty. No thread blocking.
   Strategies: Rendezvous (0) / Buffered (64) / Conflated (latest) / Unlimited (OOM risk).
   ALWAYS close, or consumer leaks. produce { } auto-closes.
   Channel vs SharedFlow: queue (one receiver, survives absence) vs broadcast (all active subs).
```

---

## Master Follow-Up Chains — Phase 11

```
Chain I — Cold → Hot → Lifecycle:
  flow { } = SafeFlow(lambda) → nothing runs until collect()
    └─► emit() is suspend → natural backpressure
         └─► buffer/conflate/collectLatest = relax backpressure
              └─► StateFlow = AtomicRef + equals() → duplicate filter
                   └─► wrong for events → SharedFlow(replay=0)
                        └─► repeatOnLifecycle(STARTED) = LifecycleEventObserver pattern
                             └─► viewLifecycleOwner (Fragment) = VIEW lifecycle, not Fragment
                                  └─► collectAsStateWithLifecycle (Compose) = same model

Chain J — Concurrency:
  flow { } = NOT concurrent-safe (emit from same coroutine only)
    └─► channelFlow { send() } = Channel.send under the hood — concurrent-safe
         └─► Channel = lock-free queue, one item one consumer
              └─► produce { } = Channel + auto-close = preferred builder
                   └─► select { ch.onReceive } = race multiple channels → Q10.5
                        └─► flatMapLatest inner cancel = CancellationException → Q10.3
```

---

*← [Phase 10 — Structured Concurrency](10_structured_concurrency.md) | [Phase 12 — Reflection & References →](12_reference_operators_and_reflection.md)*