# Phase A5 — Jetpack Compose

Jetpack Compose is Android's modern declarative UI toolkit. It replaced the imperative View system as Google's recommended approach for new UI development. If you're interviewing for any Android role post-2022, Compose questions are guaranteed. The core challenge is that Compose rewires your mental model: instead of mutating Views, you describe what the UI *should look like* given the current state, and Compose figures out what changed and re-renders accordingly. Every performance problem and every confusing bug in Compose comes from misunderstanding this model.

> **Connects to:** [A3 — Architecture Patterns](A3_architecture_patterns.md) · [Kotlin 09 — Coroutines](../../Kotlin/Questions/09_coroutines_execution_mechanics.md) · [Kotlin 11 — Flow](../../Kotlin/Questions/11_flow.md)

---

## A5.1 — The Recomposition Model

> **Connects to:** [A5.2 — State in Compose](A5_jetpack_compose.md#a52--state-in-compose)

### WHY: The Fundamental Mental Model Shift

In the View system, you write imperative code:
```kotlin
// View system: you mutate the view directly
textView.text = "Hello $name"
button.isEnabled = isLoggedIn
progressBar.visibility = if (isLoading) View.VISIBLE else View.GONE
```

In Compose, you describe the UI as a function of state:
```kotlin
// Compose: you describe what it should look like
@Composable
fun UserScreen(name: String, isLoggedIn: Boolean, isLoading: Boolean) {
    if (isLoading) {
        CircularProgressIndicator()
    } else {
        Text("Hello $name")
        Button(enabled = isLoggedIn) { /* click */ }
    }
}
```

When state changes, Compose calls your `@Composable` functions again — this is **recomposition**. Compose is smart enough to skip functions whose inputs haven't changed.

---

### What Triggers Recomposition

Recomposition is triggered when a **State object** that was READ during a composition changes.

```kotlin
var count by remember { mutableStateOf(0) }

// This composable reads `count`. When count changes → recomposition.
Text("Count: $count")
Button(onClick = { count++ }) { Text("Increment") }
```

**Compose tracks reads at the granularity of individual composable function calls.** Only composables that READ a changed State value are recomposed — not the whole screen.

```
State changes
      │
      ▼
Compose identifies which composables READ this state
      │
      ▼
Only those composables are recomposed (skipped if inputs unchanged)
      │
      ▼
Compose diffs the composition tree — only changed nodes go to the layout/draw phase
```

---

### Composable Function Properties — Stability

Compose can skip recomposing a function if all its inputs are **equal to the previous inputs**. But "equal" is not always straightforward:

| Type | Skippable? | Why |
|------|-----------|-----|
| Primitive (Int, Boolean, String) | ✅ Yes | Stable, compared by value |
| data class with only stable fields | ✅ Yes | Stable, compared with equals() |
| List, Map, Set (Kotlin standard) | ❌ No | Mutable — Compose treats as unstable |
| Immutable collections (kotlinx.collections) | ✅ Yes | Explicitly immutable |
| Class not annotated with @Stable | ❌ No | Compose assumes mutable |
| Lambda (without capture changes) | ✅ Yes | Same instance via remember |

```kotlin
// BAD: List is unstable — UserList always recomposes even if content is the same
@Composable
fun UserList(users: List<User>) { /* ... */ }

// GOOD: wrap in an immutable holder or use @Immutable
@Immutable
data class UserListState(val users: List<User>)

@Composable
fun UserList(state: UserListState) { /* ... */ }
```

**`@Stable`** and **`@Immutable`** are contracts you promise to the compiler: "I guarantee this type's fields won't change in a way that requires recomposition." Breaking this contract causes silent missed recompositions.

---

### Interview Trap: Recomposition Is NOT Free

```kotlin
// BAD: creates a new lambda on every recomposition → always treated as changed
@Composable
fun Parent() {
    val count by remember { mutableStateOf(0) }
    // This lambda is recreated every time Parent recomposes
    Child(onClick = { doSomething(count) })
}

// GOOD: use rememberUpdatedState + lambda reference
@Composable
fun Parent() {
    val count by remember { mutableStateOf(0) }
    val currentCount by rememberUpdatedState(count)
    val onClick = remember { { doSomething(currentCount) } }
    Child(onClick = onClick)
}
```

---

## A5.2 — State in Compose

> **Builds on:** [A5.1 — Recomposition Model](A5_jetpack_compose.md#a51--the-recomposition-model)

### `remember` — Survives Recomposition, Not Navigation

```kotlin
@Composable
fun Counter() {
    var count by remember { mutableStateOf(0) }
    //   ↑ survives recomposition but LOST on:
    //     - navigation away and back
    //     - configuration change (rotation)
    //     - process death
    Button(onClick = { count++ }) { Text("$count") }
}
```

`remember` stores its value in the composition tree node for this composable. As long as the composable stays in the composition (not navigated away from), the value persists across recompositions.

**It does NOT survive:**
- Navigating away and back (the composable leaves the composition tree)
- Configuration changes (by default — the composition is rebuilt)
- Process death

---

### `rememberSaveable` — Survives Configuration Change + Process Death

```kotlin
@Composable
fun Counter() {
    var count by rememberSaveable { mutableStateOf(0) }
    //   ↑ survives rotation AND process death
    //     stored in savedInstanceState Bundle
}
```

`rememberSaveable` hooks into `onSaveInstanceState`. The value is serialized to a Bundle on configuration change or before process death. On recreation, it restores the value.

**Constraints:**
- Value must be Bundle-compatible (primitive, Parcelable, Serializable)
- For complex types: provide a `Saver`

```kotlin
// Custom Saver for a data class
val userSaver = Saver<User, Bundle>(
    save = { user -> Bundle().apply { putString("id", user.id) } },
    restore = { bundle -> User(id = bundle.getString("id")!!) }
)
var user by rememberSaveable(stateSaver = userSaver) { mutableStateOf(User("1")) }
```

---

### State Hoisting — Moving State Up

**State hoisting** = moving state out of a composable to make it stateless and reusable.

```
Stateful (tightly coupled, hard to test):

  @Composable
  fun SearchBar() {
      var text by remember { mutableStateOf("") }
      TextField(value = text, onValueChange = { text = it })
  }

Stateless (hoisted — accepts state and events as parameters):

  @Composable
  fun SearchBar(
      text: String,                    // STATE flows DOWN
      onTextChange: (String) -> Unit   // EVENTS flow UP
  ) {
      TextField(value = text, onValueChange = onTextChange)
  }

  // Caller controls the state:
  var searchText by remember { mutableStateOf("") }
  SearchBar(text = searchText, onTextChange = { searchText = it })
```

**Rule: state belongs at the LOWEST common ancestor of all composables that need it.**

Benefits of hoisting:
- Composable is reusable in different contexts (screen, dialog, bottom sheet)
- Composable is testable without Android dependencies (pass values directly)
- Parent controls state → single source of truth

---

## A5.3 — Side Effects in Compose

> **Builds on:** [A5.2 — State](A5_jetpack_compose.md#a52--state-in-compose)

### WHY Side Effects Need Special Handling

Composable functions can recompose many times. Code inside a composable body runs on every recomposition. If you start a coroutine, register a listener, or log analytics inside the composable body directly, you do it on EVERY recompose — which could be many times per second.

Compose provides **effect handlers** that tie side effects to the composable's lifecycle.

---

### `LaunchedEffect` — Coroutine Tied to Composition Lifetime

```kotlin
@Composable
fun UserScreen(userId: String) {
    val viewModel: UserViewModel = hiltViewModel()

    // Starts a coroutine when this composable enters composition.
    // Cancels the coroutine when it leaves composition.
    // Re-launches when `userId` changes (key parameter).
    LaunchedEffect(userId) {
        viewModel.loadUser(userId)
    }
}
```

**Key parameter rule:** LaunchedEffect re-launches whenever any key changes.
- `LaunchedEffect(Unit)`: runs ONCE when composable enters composition.
- `LaunchedEffect(userId)`: re-runs whenever userId changes.
- `LaunchedEffect(key1, key2)`: re-runs when either key changes.

**WHY not just launch a coroutine in the body?**
```kotlin
// BAD: launches a new coroutine on EVERY recomposition
@Composable
fun UserScreen(userId: String) {
    val scope = rememberCoroutineScope()
    scope.launch { viewModel.loadUser(userId) }  // ← fires on every recompose!
}
```

---

### `DisposableEffect` — Non-Coroutine Cleanup

For side effects that have a lifecycle: register → cleanup (listeners, analytics, sensors).

```kotlin
@Composable
fun LifecycleObserver(lifecycle: Lifecycle, onStop: () -> Unit) {
    DisposableEffect(lifecycle) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_STOP) onStop()
        }
        lifecycle.addObserver(observer)

        // onDispose: called when composable leaves composition OR key changes
        onDispose {
            lifecycle.removeObserver(observer)
        }
    }
}
```

**Must always include `onDispose { }`.** The block runs when:
- The composable leaves the composition (navigation away)
- The key parameter changes (cleanup old, setup new)

---

### `rememberCoroutineScope` — User-Triggered Coroutines

For coroutines triggered by user actions (button clicks, not lifecycle events):

```kotlin
@Composable
fun SubmitButton(onSubmit: suspend () -> Unit) {
    val scope = rememberCoroutineScope()

    Button(onClick = {
        // scope is tied to this composable's lifetime
        // automatically cancelled when composable leaves composition
        scope.launch { onSubmit() }
    }) {
        Text("Submit")
    }
}
```

**Comparison:**

| | `LaunchedEffect` | `DisposableEffect` | `rememberCoroutineScope` |
|--|--|----|--|
| Triggered by | Composition / key change | Composition / key change | User action (onClick etc.) |
| For coroutines | ✅ | ❌ | ✅ |
| For cleanup | ❌ | ✅ (onDispose) | ❌ |
| Cancels on leave | ✅ automatic | ✅ onDispose | ✅ automatic |

---

## A5.4 — Performance: `derivedStateOf` and Keys

### `derivedStateOf` — Avoid Redundant Recomposition

Use when a computed value depends on state but changes less frequently than the input state.

```kotlin
// BAD: every scroll position change recomposes the FAB
@Composable
fun Screen() {
    val listState = rememberLazyListState()
    // firstVisibleItemIndex changes on EVERY scroll pixel
    val showFab = listState.firstVisibleItemIndex > 0

    FloatingActionButton(
        onClick = { /* scroll to top */ },
        visible = showFab  // recomposes on every scroll event
    )
}

// GOOD: derivedStateOf memoizes — FAB only recomposes when showFab flips
@Composable
fun Screen() {
    val listState = rememberLazyListState()
    val showFab by remember {
        derivedStateOf { listState.firstVisibleItemIndex > 0 }
    }
    // showFab is true/false — only changes when crossing the threshold
    // FAB recomposes only when showFab changes (true→false or false→true)
    FloatingActionButton(onClick = { /* scroll to top */ }, visible = showFab)
}
```

**Rule:** Use `derivedStateOf` when your composable reads a State value but only cares about a boolean threshold or aggregated result, not the raw value.

---

### `key()` — Preserve Identity in Lists

In a `LazyColumn`, Compose identifies each item by its **position** by default. When you insert an item at the top, Compose thinks every item changed position → recomposes all items.

```kotlin
// BAD: position-based identity — insert at top → recompose everything
LazyColumn {
    items(users) { user ->
        UserRow(user)
    }
}

// GOOD: key-based identity — Compose knows which item is which
LazyColumn {
    items(users, key = { user -> user.id }) { user ->
        UserRow(user)
    }
}
```

With `key`, inserting an item at the top means only the new item is composed. All existing items keep their identity and are not recomposed.

**Also use `key()` in `Column`/`Row` when items can reorder:**
```kotlin
Column {
    for (item in items) {
        key(item.id) {
            ItemRow(item)
        }
    }
}
```

---

## A5.5 — ViewModel Integration and State Collection

### Collecting StateFlow in Compose

```kotlin
@Composable
fun UserScreen(viewModel: UserViewModel = hiltViewModel()) {

    // collectAsStateWithLifecycle: pauses collection when lifecycle < STARTED
    // prevents wasted work when screen is in background
    val uiState by viewModel.uiState.collectAsStateWithLifecycle()

    when (uiState) {
        is UserUiState.Loading -> CircularProgressIndicator()
        is UserUiState.Success -> UserContent(uiState.user)
        is UserUiState.Error -> ErrorView(uiState.message)
    }
}
```

**`collectAsStateWithLifecycle` vs `collectAsState`:**

```
collectAsState:
  Always collecting, even in background.
  Background network events trigger recomposition even when screen invisible.
  Wastes battery, CPU, and potentially does unnecessary work.

collectAsStateWithLifecycle (correct):
  Stops collecting when lifecycle drops below Lifecycle.State.STARTED.
  Automatically resumes when app returns to foreground.
  No wasted recompositions while screen is invisible.
```

---

### One-Time Events (Navigation, Toasts)

```kotlin
class UserViewModel : ViewModel() {
    // SharedFlow(replay=0) for events: no duplicate filter, no replay
    private val _events = MutableSharedFlow<UserEvent>()
    val events: SharedFlow<UserEvent> = _events
}

sealed class UserEvent {
    data class NavigateToDetail(val userId: String) : UserEvent()
    data class ShowError(val message: String) : UserEvent()
}

@Composable
fun UserScreen(navController: NavController, viewModel: UserViewModel = hiltViewModel()) {
    // LaunchedEffect with Unit: collect events for composable's lifetime
    LaunchedEffect(Unit) {
        viewModel.events.collect { event ->
            when (event) {
                is UserEvent.NavigateToDetail -> navController.navigate("detail/${event.userId}")
                is UserEvent.ShowError -> { /* show snackbar */ }
            }
        }
    }
}
```

---

## A5.6 — AndroidView Interop

For situations where you need a legacy View inside Compose (maps, camera, web view):

```kotlin
@Composable
fun MapView(location: LatLng) {
    AndroidView(
        factory = { context ->
            // Called ONCE to create the View
            MapView(context).apply {
                onCreate(Bundle())
                onResume()
            }
        },
        update = { mapView ->
            // Called on recomposition when parameters change
            mapView.getMapAsync { map ->
                map.moveCamera(CameraUpdateFactory.newLatLng(location))
            }
        }
    )
}
```

**`factory`:** called once when the composable enters composition. Creates the View.
**`update`:** called on every recomposition. Update the View to reflect new parameters.
**Cleanup:** use `DisposableEffect` alongside `AndroidView` to call View lifecycle methods (onPause, onDestroy).

---

## Master Summary: Jetpack Compose

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  PHASE A5 — JETPACK COMPOSE MASTER SUMMARY                                  │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  1. RECOMPOSITION MODEL                                                      │
│     Composables are functions that run on every state change.               │
│     Compose tracks which State objects each composable READS.               │
│     Only composables that read changed state are recomposed (not all).      │
│     Unstable inputs (List, non-@Stable classes) prevent skipping.          │
│                                                                              │
│  2. STATE HIERARCHY                                                          │
│     remember: survives recomposition only.                                  │
│     rememberSaveable: survives rotation + process death (Bundle-backed).   │
│     ViewModel StateFlow: survives rotation, not process death.              │
│     Room/DataStore: survives everything (disk-backed).                      │
│     State hoisting: move state UP to lowest common ancestor.               │
│                                                                              │
│  3. SIDE EFFECTS — which to use                                              │
│     LaunchedEffect(key): coroutine, tied to composition, re-runs on key.  │
│     DisposableEffect(key): register+cleanup pairs (listeners, sensors).    │
│     rememberCoroutineScope: coroutines launched by user actions.           │
│                                                                              │
│  4. PERFORMANCE                                                              │
│     derivedStateOf: memoize a computed boolean/value from state.           │
│     key() in LazyColumn: identity-based (not position-based) diffing.     │
│     @Stable/@Immutable: mark types to enable composable skipping.         │
│     Avoid lambdas that capture mutable state without remember.             │
│                                                                              │
│  5. VIEWMODEL INTEGRATION                                                    │
│     collectAsStateWithLifecycle: stops collection in background.           │
│     SharedFlow(replay=0): one-time events (navigation, toasts).           │
│     StateFlow: persistent UI state, replays current value on subscribe.   │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

**Interview Traps:**

> **"What's the difference between `remember` and `rememberSaveable`?"**
> `remember` survives recomposition only — lost on rotation or navigation. `rememberSaveable` is backed by `savedInstanceState` Bundle, surviving rotation and process death. Use `rememberSaveable` for any UI state the user would notice losing (text field input, scroll position, selected tab).

> **"Why does my LazyColumn recompose everything when I insert one item?"**
> Default identity is position-based. Insert at index 0 → every item's position changes → all recompose. Fix: `items(list, key = { it.id })` for stable identity-based tracking.

> **"Can you call a suspend function directly inside a composable?"**
> No. Composables are not coroutines — they run synchronously on the UI thread. To call a suspend function, use `LaunchedEffect` (for lifecycle-tied work) or `rememberCoroutineScope().launch` (for event-triggered work).

> **"What causes excessive recomposition?"**
> 1. Unstable types passed as parameters (List, non-@Stable classes). 2. Lambdas created inline that capture changing state. 3. Reading high-frequency State directly (use `derivedStateOf` to threshold it). 4. Missing `key` in `LazyColumn` causing position-based recomposition.

---

*← [Phase A4 — Offline & Data Layer](A4_offline_and_data.md)*

**Cross-references:**
- Kotlin coroutines (LaunchedEffect, coroutineScope): [Kotlin 09 — Coroutines](../../Kotlin/Questions/09_coroutines_execution_mechanics.md)
- StateFlow / SharedFlow (collecting in Compose): [Kotlin 11 — Flow](../../Kotlin/Questions/11_flow.md)
- ViewModel integration: [Kotlin 13 — Android Architecture](../../Kotlin/Questions/13_android_architecture.md)
- Android architecture patterns (MVVM/MVI with Compose): [A3 — Architecture Patterns](A3_architecture_patterns.md)
