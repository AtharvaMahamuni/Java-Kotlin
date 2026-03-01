# Phase 11: Flow

## Navigation
[← Master Index](master_chains.md)

## Questions in This File
- [Q11.1 — Cold vs Hot Streams](#q111--cold-vs-hot-streams)
- [Q11.2 — Flow Operators](#q112--flow-operators)
- [Q11.3 — `StateFlow` vs `SharedFlow`](#q113--stateflow-vs-sharedflow)
- [Q11.4 — Flow Collection and Lifecycle](#q114--flow-collection-and-lifecycle)
- [Q11.5 — Channels: Hot Streams with Backpressure](#q115--channels-hot-streams-with-backpressure)

---

## Q11.1 — Cold vs Hot Streams

> **Builds on:** [Q7.2 — Sequences](07_collections_and_sequences.md#q72--sequences-vs-eager-collections)
> **Connects to:** [Q11.2 — Flow Operators](11_flow.md#q112--flow-operators) · [Q11.3 — StateFlow vs SharedFlow](11_flow.md#q113--stateflow-vs-sharedflow) · [Q11.4 — Flow Collection](11_flow.md#q114--flow-collection-and-lifecycle)
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

> **Builds on:** [Q11.1 — Cold Flows](11_flow.md#q111--cold-vs-hot-streams) · [Q4.2 — inline operators](04_functions_lambdas_inlining.md#q42--inline-noinline-crossinline)
> **Connects to:** [Q11.3 — StateFlow vs SharedFlow](11_flow.md#q113--stateflow-vs-sharedflow) · [Q7.2 — Sequences (similar lazy pipeline)](07_collections_and_sequences.md#q72--sequences-vs-eager-collections)

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

> **Builds on:** [Q11.1 — Hot vs Cold](11_flow.md#q111--cold-vs-hot-streams) · [Q9.2 — CoroutineContext (scope for stateIn)](09_coroutines_execution_mechanics.md#q92--coroutine-context-and-dispatchers)
> **Connects to:** [Q13.4 — LiveData vs StateFlow](13_android_architecture.md#q134--livedata-vs-stateflow-vs-sharedflow) · [Q11.4 — Collection lifecycle](11_flow.md#q114--flow-collection-and-lifecycle)
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

> **Builds on:** [Q11.3 — StateFlow/SharedFlow](11_flow.md#q113--stateflow-vs-sharedflow) · [Q10.4 — Lifecycle Scopes](10_structured_concurrency.md#q104--lifecycle-scopes-and-process-death)
> **Connects to:** [Q13.3 — ViewModel and StateFlow](13_android_architecture.md#q133--viewmodel-internals) · [Q10.3 — CancellationException](10_structured_concurrency.md#q103--exception-handling-rules)
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

## Q11.5 — Channels: Hot Streams with Backpressure

> **Builds on:** [Q11.1 — Cold vs Hot Streams](11_flow.md#q111--cold-vs-hot-streams) · [Q11.3 — StateFlow vs SharedFlow](11_flow.md#q113--stateflow-vs-sharedflow) · [Q9.3 — launch vs async](09_coroutines_execution_mechanics.md#q93--launch-vs-async)
> **Connects to:** [Q10.6 — Mutex](10_structured_concurrency.md#q106--mutex-and-synchronization-primitives) · [Q10.5 — select Expression](10_structured_concurrency.md#q105--select-expression)
> **Reference:** [Kotlin Docs — Channels](https://kotlinlang.org/docs/channels.html)

### First Principles: The Problem Channels Solve

Both `StateFlow` and `SharedFlow` are built on top of **Channels**. But Channels are more primitive and serve a different purpose: they are a **communication pipe** between coroutines. Where Flow is about transforming a stream of values, Channel is about one coroutine **sending** values and another **receiving** them — like a queue between coroutines.

```
Flow:                          Channel:
  Producer creates              Producer sends    Consumer receives
  values on demand     vs.      values when       values when
  (cold — no sender)            ready (hot)       ready (hot)

  No backpressure needed        Backpressure: if buffer full,
  (consumer pulls)              send suspends (producer waits)
```

---

### What Is a Channel?

A `Channel` is a **coroutine-safe queue** with a suspension protocol:
- **Sender** calls `send(value)` — suspends if the channel buffer is full
- **Receiver** calls `receive()` — suspends if the channel is empty
- Neither ever blocks a thread — they suspend their coroutine while waiting

```kotlin
val channel = Channel<Int>()

// Producer coroutine: sends values
launch {
    for (i in 1..5) {
        channel.send(i)   // suspends if channel buffer full
        println("Sent $i")
    }
    channel.close()       // IMPORTANT: signal no more values coming
}

// Consumer coroutine: receives values
launch {
    for (value in channel) {  // receives until channel is closed
        println("Received $value")
    }
}
```

Output (order may interleave depending on dispatcher):
```
Sent 1
Received 1
Sent 2
Received 2
...
Received 5
```

---

### Channel Types: The Buffer Strategy

The buffer strategy determines what happens when the producer is faster than the consumer:

```kotlin
// 1. Rendezvous (buffer = 0, the default):
val rendezvous = Channel<Int>()
// send() suspends IMMEDIATELY until a receiver is ready
// Most strict: sender and receiver must rendezvous at the same time
// Use when: you want tight coupling (sender should wait for receiver to be ready)

// 2. Buffered:
val buffered = Channel<Int>(capacity = 64)
// send() suspends only when buffer is full (64 items)
// Consumer can lag up to 64 items behind producer before producer blocks
// Use when: producer and consumer run at different speeds

// 3. Conflated:
val conflated = Channel<Int>(Channel.CONFLATED)
// send() never suspends — but only the LATEST value is kept
// Each new send overwrites the previous unread value
// Same behavior as SharedFlow(replay=0, extraBufferCapacity=1, DROP_OLDEST)
// Use when: only the latest state matters (UI updates, sensor readings)

// 4. Unlimited:
val unlimited = Channel<Int>(Channel.UNLIMITED)
// send() never suspends — buffer grows as needed (unbounded!)
// DANGER: memory leak if consumer can't keep up
// Use when: you are certain production is finite and consumer will catch up
```

```
Buffer behavior visualization (buffer size = 2):

Producer sends: 1, 2, 3, 4, 5 (fast)
Consumer reads: one every second (slow)

Time 0: producer sends 1 → buffer [1]
Time 1: producer sends 2 → buffer [1, 2]
Time 2: producer sends 3 → BUFFER FULL → producer SUSPENDS
         consumer reads 1 → buffer [2]
         producer resumes → sends 3 → buffer [2, 3]
...
```

---

### Channel vs Flow — When to Use Which

This is the key architectural question:

| Aspect | `Flow` | `Channel` |
|--------|--------|-----------|
| Temperature | Cold (starts on each collect) | Hot (exists independently) |
| Multiple collectors | Each gets own independent stream | All collectors share ONE stream |
| Backpressure | Built-in (consumer pulls) | Configurable buffer + suspend |
| Cancellation | Cancel collector → stops flow | Must close channel explicitly |
| One-shot events | `SharedFlow(replay=0)` for events | Rendezvous Channel |
| Communication between coroutines | Awkward (needs SharedFlow) | Natural (`send`/`receive`) |
| Operators (`map`, `filter`) | Rich operator set | Limited (use `consumeAsFlow()`) |

**Use Flow when:**
- Transforming a data stream (database query, API results)
- Multiple collectors need independent executions
- You have rich operators to apply

**Use Channel when:**
- Two coroutines need to communicate (producer/consumer pipeline)
- Work items must be processed exactly once (not replayed to each collector)
- You need a bounded work queue with backpressure

---

### `produce` Builder — Channel as a Coroutine

The `produce` coroutine builder creates a channel with a built-in producer coroutine. The channel closes automatically when the producer coroutine finishes:

```kotlin
fun CoroutineScope.generateNumbers(): ReceiveChannel<Int> = produce {
    for (i in 1..10) {
        send(i)         // sends to the channel
        delay(100)      // producer can do async work between sends
    }
    // channel auto-closes when the produce block ends
}

// Usage:
val numbers = generateNumbers()
for (n in numbers) {
    println(n)  // receives 1..10 with 100ms intervals
}
```

This is the idiomatic way to create a channel-based producer.

---

### Critical: Channels Must Be Closed

Unlike Flow (which ends naturally), a Channel stays open forever unless explicitly closed. Forgetting to close causes the receiver to suspend indefinitely:

```kotlin
val channel = Channel<String>()

launch { channel.send("hello") }

launch {
    for (msg in channel) {  // iterates until channel is CLOSED
        println(msg)
    }
    // if channel never closed: this coroutine suspends here forever!
    println("Done")  // never reached if channel not closed
}

// FIX: always close the channel:
// channel.close()  // signals no more values → for loop terminates
```

**The `produce` builder closes automatically** — it's the preferred approach precisely because it eliminates this footgun.

---

### `select` With Channels: First-Come, First-Served

Channels integrate directly with the `select` expression (see [Q10.5](10_structured_concurrency.md#q105--select-expression)) to wait on multiple channels simultaneously:

```kotlin
val updates = Channel<String>()
val alerts  = Channel<String>()

// Process whichever channel has data first:
select<Unit> {
    updates.onReceive { msg ->
        println("Update: $msg")
    }
    alerts.onReceive { msg ->
        println("ALERT: $msg")
    }
}
```

This is a powerful pattern for coroutines that must respond to multiple event sources.

---

### Channel vs SharedFlow for Events

A common Android pattern is routing UI events (button clicks, navigation) through a channel or SharedFlow. Channel is actually better for this specific case:

```kotlin
// Using Channel for one-shot events (preferred):
class MyViewModel : ViewModel() {
    private val _events = Channel<UiEvent>(Channel.BUFFERED)
    val events: Flow<UiEvent> = _events.receiveAsFlow()

    fun onButtonClick() {
        viewModelScope.launch {
            _events.send(UiEvent.NavigateToDetail)
        }
    }
}

// Why Channel over SharedFlow for events:
// - Each event processed exactly ONCE (Channel guarantees delivery to one receiver)
// - SharedFlow might deliver to multiple collectors or miss if no collector active
// - Channel buffers if collector is momentarily inactive (Activity recreating)
```

> **Key Takeaway:** Channels are the low-level primitive beneath Flow, SharedFlow, and StateFlow. They're a coroutine-safe queue: `send()` suspends if buffer full, `receive()` suspends if empty — but never blocks a thread. Use Flow for data streams with operators; use Channel for coroutine-to-coroutine communication where each item must be processed exactly once. Always close channels (or use `produce` which auto-closes).

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
