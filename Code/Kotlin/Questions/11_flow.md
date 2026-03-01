# Phase 11: Flow

## Navigation
| Phase | File |
|-------|------|
| 10 — Structured Concurrency | [10_structured_concurrency.md](10_structured_concurrency.md) |
| **11 — Flow** | ← You are here |
| 12 — Reference Operators & Reflection | [12_reference_operators_and_reflection.md](12_reference_operators_and_reflection.md) |
| 13 — Android Architecture | [13_android_architecture.md](13_android_architecture.md) |

---

## Q11.1 — Cold vs Hot Streams

> **Builds on:** [Q7.2 — Sequences](07_collections_and_sequences.md#q72--sequences-vs-eager-collections)
> **Reference:** [Kotlin Docs — Flows](https://kotlinlang.org/docs/flow.html)

### First Principles: The Problem Flow Solves

`Sequence` is lazy and synchronous — it blocks the calling thread while producing elements. You can't use `delay()` or any suspend function inside a `Sequence` block.

`Flow` is the **async, coroutine-aware counterpart** to `Sequence`. It can suspend at any point, emit from background threads, and participate in coroutine cancellation.

```kotlin
// Sequence — synchronous, can't suspend:
val seq = sequence {
    yield(1)
    Thread.sleep(100)  // blocks the thread — works but ugly
    yield(2)
    // delay(100)  // ERROR: can't call suspend in sequence builder!
}

// Flow — asynchronous, suspend-aware:
val flow = flow {
    emit(1)
    delay(100)  // suspend! thread is freed during this delay
    emit(2)
}
```

### What Makes `Flow` Cold

A **cold flow** is a flow where the producer code runs ONLY when a collector subscribes, and runs ONCE PER COLLECTOR. Each new collector gets its own independent execution.

```kotlin
val coldFlow = flow {
    println("Flow started")
    emit(1)
    emit(2)
    emit(3)
}

// Nothing happens yet — no collector
coldFlow.collect { println(it) }   // collector 1: "Flow started", 1, 2, 3
coldFlow.collect { println(it) }   // collector 2: "Flow started" AGAIN, 1, 2, 3
// Two collectors → flow body ran TWICE, independently
```

```
Cold Flow:
Producer code → runs fresh for each collector

Collector A ──► [producer: emit 1, 2, 3] ──► receives 1, 2, 3
Collector B ──► [producer: emit 1, 2, 3] ──► receives 1, 2, 3
                (NEW execution each time)
```

### What Makes `StateFlow` and `SharedFlow` Hot

**Hot flows** have a producer that runs independently of collectors. They are "always on." Collectors tap into an existing stream of values rather than starting a new one.

```kotlin
val hotFlow = MutableStateFlow(0)  // already "running" — holds state

// Producer runs independently:
launch {
    hotFlow.value = 1
    delay(100)
    hotFlow.value = 2
}

// Collector 1: subscribes and immediately gets current value (0), then updates
hotFlow.collect { println(it) }  // 0, 1, 2

// Collector 2: subscribes later, gets CURRENT value (2) — missed 0 and 1!
hotFlow.collect { println(it) }  // 2 (only current state, no history)
```

```
Hot Flow (StateFlow):
Producer ──► [state: 0] ──► [state: 1] ──► [state: 2] ──► ...

Collector A (subscribed from start): 0, 1, 2
Collector B (subscribed late):             2  ← only gets current value
```

### The "Source of Truth" Model

`StateFlow` and `SharedFlow` enable the **single source of truth** pattern:

```kotlin
class UserViewModel : ViewModel() {
    private val _uiState = MutableStateFlow<UiState>(UiState.Loading)
    val uiState: StateFlow<UiState> = _uiState  // read-only for outside

    // Multiple UI collectors all see the SAME state
    fun loadUser() {
        viewModelScope.launch {
            _uiState.value = UiState.Loading
            val user = userRepository.getUser()
            _uiState.value = UiState.Content(user)
        }
    }
}
```

### `Sequence` vs `Flow` — Final Comparison

| Aspect | `Sequence` | `Flow` |
|--------|-----------|--------|
| Thread | Caller's thread (blocking) | Any dispatcher (non-blocking) |
| Can `delay()` | No | Yes |
| Cancellation-aware | No | Yes |
| Cold | Yes | Yes (cold by default) |
| Backpressure | No (synchronous = natural backpressure) | Yes (via `buffer`, `conflate`, etc.) |

### What Is Backpressure?

Backpressure is the problem where a producer emits faster than a consumer can process:

```kotlin
flow {
    repeat(1000) {
        emit(it)      // emits 1000 items very fast
    }
}.collect { item ->
    delay(100)        // consumer is slow — takes 100ms per item
}
// Without backpressure control: the producer waits for consumer by default
// This means emit() suspends until collect{} completes each item
```

Flow handles backpressure via:

```kotlin
// buffer: producer can emit ahead; consumer processes at its pace
flow { ... }.buffer(10).collect { ... }

// conflate: drop old values; consumer only gets latest
flow { ... }.conflate().collect { ... }

// collectLatest: cancel previous processing when new value arrives
flow { ... }.collectLatest { item ->
    delay(100)     // if new item arrives before delay finishes, this is cancelled!
    process(item)
}
```

---

## Q11.2 — Flow Operators

### `map` vs `flatMapLatest`

**`map`** transforms each value: one input → one output. Never cancels ongoing work.

```kotlin
userIdFlow.map { id -> fetchUser(id) }
// For each id: fetch user, emit user. Processes each in order.
```

**`flatMapLatest`** transforms each value into a new flow, **cancelling the previous inner flow when a new value arrives**:

```kotlin
searchQueryFlow.flatMapLatest { query ->
    flow {
        delay(300)  // debounce inside
        emit(searchApi.search(query))
    }
}
// If user types fast: "a", "ap", "app", "appl", "apple"
// Only the last query ("apple") completes — others are cancelled!
```

```
flatMapLatest timeline:
query: "a" ──────────────────────────────────────────── (cancelled when "ap" arrives)
query:     "ap" ─────────────────────────────────────── (cancelled when "app" arrives)
query:          "app" ─────────────────────────────── ... (cancelled)
query:               "apple" ──────────────────────────►  [search result emitted]
```

### Debounce Search Pattern

```kotlin
// The complete search pattern:
searchEditText.textChanges()  // emits on every keystroke
    .debounce(300)            // wait for 300ms of silence
    .filter { it.length >= 2 } // ignore short queries
    .distinctUntilChanged()   // ignore same value repeated
    .flatMapLatest { query ->
        searchRepository.search(query)
            .catch { emit(emptyList()) }  // handle errors gracefully
    }
    .collect { results ->
        updateUI(results)
    }
```

**Why `flatMapLatest` is essential:** Without it, slow network requests from early keystrokes could arrive AFTER faster results from later keystrokes, causing stale data to overwrite fresh data.

### `conflate` vs `buffer(capacity = 1)` vs `buffer(UNLIMITED)`

| Operator | Behavior | When to Use |
|----------|----------|-------------|
| `conflate()` | Producer runs freely; collector only gets LATEST value (all intermediate values dropped) | UI state: only latest matters (e.g., sensor readings) |
| `buffer(capacity = 1)` | Keeps 1 buffered value; suspends producer when buffer full | Slow consumer, but don't want to miss values in sequence |
| `buffer(UNLIMITED)` | Never suspends producer; all values buffered in memory | Producer must never block; memory trade-off |

```kotlin
// conflate example:
flow {
    repeat(100) { i ->
        emit(i)
        delay(10)
    }
}.conflate().collect { value ->
    delay(100)  // slow consumer
    println(value)  // only sees: 0, ~10, ~20, ... (skips most intermediate values)
}

// buffer example:
flow {
    repeat(5) { i ->
        emit(i)
        println("emitted $i")
    }
}.buffer(2).collect { value ->
    delay(100)
    println("collected $value")
}
// Producer emits ahead, filling buffer. Consumer processes at its pace.
```

### `distinctUntilChanged`

Emits only when the value has CHANGED from the previous emission:

```kotlin
flow { emit(1); emit(1); emit(2); emit(2); emit(3) }
    .distinctUntilChanged()
    .collect { println(it) }
// Prints: 1, 2, 3  (duplicates filtered)
```

Uses `equals()` for comparison by default:
```kotlin
flow { emit(User("Alice")); emit(User("Alice")); emit(User("Bob")) }
    .distinctUntilChanged()
// User("Alice") emitted once, User("Bob") emitted once (equals() based)
```

Custom comparison:
```kotlin
.distinctUntilChangedBy { it.id }  // only filter if id is same
```

### `zip` vs `combine`

**`zip`:** Pairs elements one-to-one. Emits only when BOTH flows have produced a new value. If one flow is slower, the faster one waits.

```kotlin
flowOf(1, 2, 3)
    .zip(flowOf("a", "b", "c")) { num, letter ->
        "$num$letter"
    }
    .collect { println(it) }
// 1a, 2b, 3c
// Each pair emitted only when both flows have contributed a new value
```

**`combine`:** Emits whenever EITHER flow produces a new value, using the latest value from both:

```kotlin
val temperature = MutableStateFlow(20)
val humidity = MutableStateFlow(50)

combine(temperature, humidity) { temp, hum ->
    "Temp: ${temp}°C, Humidity: ${hum}%"
}.collect { println(it) }

// Whenever either changes:
temperature.value = 25  // emits: "Temp: 25°C, Humidity: 50%"
humidity.value = 60     // emits: "Temp: 25°C, Humidity: 60%"
temperature.value = 22  // emits: "Temp: 22°C, Humidity: 60%"
```

```
zip:                         combine:
flow1: ──1──2──3──           flow1: ──1──────2──────3──
flow2: ────a──b──c──         flow2: ────a──────b──────
output: ─────1a─2b─3c──      output: ─────(1,a)─(2,a)─(2,b)─(3,b)─...
(waits for BOTH)             (fires when EITHER changes)
```

---

## Q11.3 — `StateFlow` vs `SharedFlow`

> **Reference:** [Kotlin Docs — StateFlow and SharedFlow](https://kotlinlang.org/docs/flow.html#stateflow-and-sharedflow)

### Why `StateFlow` Skips Duplicate Consecutive Emissions

`StateFlow` uses `equals()` to compare the new value with the current value. If they're equal, the new value is NOT emitted:

```kotlin
val state = MutableStateFlow("hello")
state.collect { println(it) }

state.value = "hello"  // SAME value → NOT emitted (duplicate filtered!)
state.value = "world"  // different → emitted
state.value = "hello"  // different from "world" → emitted
// Output: hello, world, hello (not: hello, hello, world, hello)
```

**When is this a bug?**
```kotlin
// Navigation event as StateFlow:
val navigateTo = MutableStateFlow<String?>(null)
navigateTo.value = "DetailScreen"  // → navigates!
// User navigates back, state = null
navigateTo.value = "DetailScreen"  // DUPLICATE → NOT emitted! Bug: no navigation!
```

This is why StateFlow is WRONG for one-shot events like navigation. The duplicate filter means the second navigation command is silently dropped.

### One-Shot Navigation Events: `SharedFlow`

```kotlin
// WRONG: StateFlow for navigation (duplicates filtered)
val navigateTo = MutableStateFlow<String?>(null)

// CORRECT: SharedFlow with replay=0 (no caching, no filtering)
private val _navigationEvents = MutableSharedFlow<String>(
    replay = 0,              // don't replay to new subscribers
    extraBufferCapacity = 1, // buffer 1 event in case no subscriber yet
    onBufferOverflow = BufferOverflow.DROP_OLDEST
)
val navigationEvents = _navigationEvents.asSharedFlow()

// Emit from ViewModel:
viewModelScope.launch {
    _navigationEvents.emit("DetailScreen")
}
```

### `StateFlow` vs `SharedFlow` — Configuration

```kotlin
// StateFlow:
// - Always has an initial value
// - replay = 1 (always caches the current value)
// - Filters duplicates with equals()
// - Good for: UI state, current value observation
MutableStateFlow<T>(initialValue)

// SharedFlow:
// - No initial value
// - Configurable replay, buffer, overflow
// - No duplicate filtering
// - Good for: events, one-shot actions, streams without state
MutableSharedFlow<T>(
    replay = 0,              // how many values new subscribers get immediately
    extraBufferCapacity = 0, // additional buffer beyond replay
    onBufferOverflow = BufferOverflow.SUSPEND  // what to do when buffer full
)
```

### Why `StateFlow` Is Wrong for Navigation After Rotation

When the screen rotates:
1. Activity is destroyed, re-created
2. New `Activity` subscribes to `StateFlow`
3. `StateFlow` has `replay = 1` — it immediately emits the last value to new subscriber
4. If last value was "DetailScreen", the app navigates AGAIN on rotation!

```
StateFlow replay on rotation:
ViewModel (survives rotation)
  navigateTo = StateFlow("DetailScreen")  ← still holds this value!

Old Activity → destroyed
New Activity → subscribes → immediately receives "DetailScreen" → NAVIGATES AGAIN!
```

**Fix:** Use `SharedFlow(replay = 0)` + set to `null` or use `Channel`. Either way: don't use `StateFlow` for events.

### `stateIn` vs `shareIn` on a Cold Flow

```kotlin
// Cold flow (fetches from DB/network on each collection):
val userFlow: Flow<User> = flow { emit(repository.getUser()) }

// stateIn: converts cold flow → StateFlow (with initial value)
val userState: StateFlow<User?> = userFlow.stateIn(
    scope = viewModelScope,
    started = SharingStarted.WhileSubscribed(5000),  // keep alive 5s after last subscriber
    initialValue = null
)

// shareIn: converts cold flow → SharedFlow
val userShared: SharedFlow<User> = userFlow.shareIn(
    scope = viewModelScope,
    started = SharingStarted.WhileSubscribed(5000),
    replay = 1
)
```

`SharingStarted.WhileSubscribed(5000)` means: start upstream collection when first subscriber arrives, stop 5 seconds after the last subscriber leaves. The 5-second grace period handles configuration changes.

---

## Q11.4 — Flow Collection and Lifecycle

> **Reference:** [Android Docs — Collect flows from Android UIs](https://developer.android.com/kotlin/flow/stateflow-and-sharedflow)

### The Lifecycle Bug with `lifecycleScope.launch { flow.collect {} }`

```kotlin
// BUGGY: continues collecting in background!
class MyFragment : Fragment() {
    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        lifecycleScope.launch {
            viewModel.uiState.collect { state ->
                updateUI(state)  // updates UI even when app is in background!
            }
        }
    }
}
```

**The bug:** `lifecycleScope` is tied to the Fragment's lifecycle — destroyed when Fragment is destroyed. But when the app goes to BACKGROUND (Fragment is stopped, not destroyed), collection CONTINUES. You're consuming resources and potentially updating a non-visible UI.

### What `repeatOnLifecycle(STARTED)` Adds

```kotlin
// CORRECT: collection suspends when lifecycle drops below STARTED
class MyFragment : Fragment() {
    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        viewLifecycleOwner.lifecycleScope.launch {
            viewLifecycleOwner.repeatOnLifecycle(Lifecycle.State.STARTED) {
                viewModel.uiState.collect { state ->
                    updateUI(state)
                }
            }
        }
    }
}
```

`repeatOnLifecycle(STARTED)`:
- **Starts** collecting when lifecycle enters STARTED state (onStart)
- **Cancels** the collection block when lifecycle drops below STARTED (onStop)
- **Restarts** the collection block when lifecycle re-enters STARTED

```
App lifecycle:     onCreate──onStart──onResume──onPause──onStop──onStart──onResume...
                                  │                         │         │
collection:                    STARTS                    CANCELS   RESTARTS
```

### What `collectAsStateWithLifecycle` Does (Compose)

```kotlin
@Composable
fun MyScreen(viewModel: MyViewModel) {
    // Lifecycle-aware collection for Compose:
    val uiState by viewModel.uiState.collectAsStateWithLifecycle()
    // Stops collecting when screen goes to background (lifecycle < STARTED)
    // Equivalent to repeatOnLifecycle(STARTED) but for Compose
}

// vs the INCORRECT:
val uiState by viewModel.uiState.collectAsState()
// collectAsState ignores lifecycle — always collects, even in background!
```

### What Happens to Buffered Emissions When Collector Is Cancelled

When a Flow collector is cancelled:
- **Cold flow:** The flow producer is also cancelled (they share the same coroutine)
- **Hot flow (SharedFlow/StateFlow):** The producer continues; the cancelled collector simply stops receiving
- **Buffered emissions that haven't been processed yet:** Lost for that collector

For hot flows with `buffer()`:
```kotlin
sharedFlow.buffer(10).collect { value ->
    // If this collector is cancelled while buffer has values,
    // those buffered values are lost for this collector
    // but they may still be in the SharedFlow's own buffer for other collectors
}
```

---

## Master Summary: Flow in 5 Points

```
┌───────────────────────────────────────────────────────────────────────┐
│  1. Cold flows: producer runs fresh per collector. Each subscribe    │
│     creates an independent execution.                                │
│     Hot flows (StateFlow/SharedFlow): always running; collectors tap│
│     into an ongoing stream.                                          │
│                                                                       │
│  2. flatMapLatest cancels the inner flow when a new value arrives.   │
│     Essential for search: only the latest query proceeds.            │
│                                                                       │
│  3. StateFlow filters consecutive duplicate values (equals()).        │
│     This makes it WRONG for navigation events (may drop them).       │
│     Use SharedFlow(replay=0) for one-shot events.                    │
│                                                                       │
│  4. lifecycleScope.launch { flow.collect{} } collects even in bg.   │
│     Use repeatOnLifecycle(STARTED) to stop in background.           │
│     In Compose: use collectAsStateWithLifecycle, not collectAsState. │
│                                                                       │
│  5. zip: pairs one-to-one, waits for both. combine: fires when      │
│     EITHER flow emits, using latest from both.                      │
└───────────────────────────────────────────────────────────────────────┘
```

---

*← [Phase 10 — Structured Concurrency](10_structured_concurrency.md) | [Phase 12 — Reflection & References →](12_reference_operators_and_reflection.md)*
