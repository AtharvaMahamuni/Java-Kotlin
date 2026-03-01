# Phase 17: Performance and Memory

## Navigation
[← Master Index](master_chains.md)

## Questions in This File
- [Q17.1 — Memory Leaks — Top 5 Causes](#q171--memory-leaks--top-5-causes)
- [Q17.2 — RecyclerView Internals](#q172--recyclerview-internals)
- [Q17.3 — The 16ms Budget](#q173--the-16ms-budget)
- [Q17.4 — Testing](#q174--testing)

---

## Q17.1 — Memory Leaks — Top 5 Causes

> **Builds on:** [Q0.1 — Heap allocation and GC](00_jvm_mental_model.md#q01--primitives-vs-references) · [Q2.4 — Anonymous objects and inner classes](02_classes_and_objects.md#q24--the-object-keyword)
> **Connects to:** [Q17.2 — RecyclerView](17_performance_and_memory.md#q172--recyclerview-internals) · [Q16.1 — Activity lifecycle](16_android_system_internals.md#q161--activity-and-fragment-lifecycle)
> **Reference:** [Android Docs — Inspect your app's memory usage](https://developer.android.com/studio/profile/memory-profiler)

### First Principles: What Is a Memory Leak?

A memory leak occurs when an object that should be garbage collected is still **reachable** from a GC root (live reference). The GC cannot free it, so memory usage grows over time.

GC roots in Android: threads, static fields, JNI references, and `Application.onCreate()` objects.

**The leak chain:** A long-lived object holds a reference to a short-lived object that should have been freed.

---

### Leak 1: Activity Context in Singleton

```kotlin
// WRONG — singleton holds Activity context:
object NetworkManager {
    lateinit var context: Context  // LEAKED!

    fun init(context: Context) {
        this.context = context  // storing Activity → Activity can never be GC'd!
    }
}

// NetworkManager lives forever (singleton)
// Activity (short-lived) referenced by singleton → never GC'd!
// Result: Every Activity instance leaks — memory grows with each rotation!

// FIX: use Application context:
object NetworkManager {
    lateinit var context: Context  // Application context is safe

    fun init(context: Context) {
        this.context = context.applicationContext  // lives as long as the app!
    }
}
```

**Why `applicationContext` fixes it:** `Application` is a singleton itself — its lifetime IS the app lifetime. Holding it in another singleton creates no extra retention.

---

### Leak 2: Non-Static Inner Class Holding Outer Reference

```kotlin
class MyActivity : Activity() {
    // Inner class (non-static) implicitly holds reference to outer MyActivity:
    inner class MyHandler : Handler(Looper.getMainLooper()) {
        override fun handleMessage(msg: Message) {
            // Can access MyActivity's members because it holds a reference!
        }
    }

    val handler = MyHandler()  // handler is posted with 10-second delay

    override fun onDestroy() {
        super.onDestroy()
        // handler.removeCallbacksAndMessages(null)  ← NOT called!
    }
}

// User rotates device → Activity destroyed
// Handler still in MessageQueue (10-second delay not expired)
// Handler holds MyActivity reference → MyActivity not GC'd → LEAK!
```

Non-static inner classes and anonymous objects (see [Q2.4 — The object keyword](02_classes_and_objects.md#q24--the-object-keyword)) hold an implicit reference to their outer class.

**Fix:**
```kotlin
// Option 1: Static inner class (no implicit outer reference):
class MyActivity : Activity() {
    private class StaticHandler(activity: WeakReference<MyActivity>) :
        Handler(Looper.getMainLooper()) {
        override fun handleMessage(msg: Message) {
            activity.get()?.handleIt()  // null if Activity destroyed
        }
    }

    // Option 2: Remove callbacks in onDestroy:
    override fun onDestroy() {
        super.onDestroy()
        handler.removeCallbacksAndMessages(null)  // removes pending messages
    }
}
```

---

### Leak 3: Handler with `postDelayed` Leak

Same as Leak 2 but worth emphasizing: `handler.postDelayed(runnable, delay)` keeps `runnable` in the MessageQueue until it fires. If the `runnable` captures the Activity (via anonymous class / lambda), the Activity leaks for the duration of the delay.

```kotlin
// WRONG:
class SplashActivity : Activity() {
    override fun onCreate(...) {
        Handler(Looper.getMainLooper()).postDelayed({
            startActivity(Intent(this, MainActivity::class.java))  // captures `this`!
        }, 2000)
    }
    // If user presses back: Activity should die, but lambda holds `this` for 2 seconds
}

// FIX: store the Runnable and cancel in onDestroy:
class SplashActivity : Activity() {
    private val navigateRunnable = Runnable {
        startActivity(Intent(this, MainActivity::class.java))
    }
    private val handler = Handler(Looper.getMainLooper())

    override fun onCreate(...) {
        handler.postDelayed(navigateRunnable, 2000)
    }

    override fun onDestroy() {
        super.onDestroy()
        handler.removeCallbacks(navigateRunnable)  // cancel if Activity is destroyed
    }
}
```

---

### Leak 4: `GlobalScope` Coroutine

```kotlin
class MyActivity : Activity() {
    override fun onCreate(...) {
        GlobalScope.launch {  // WRONG! GlobalScope lives as long as the process!
            val result = api.fetchData()
            withContext(Dispatchers.Main) {
                updateUI(result)  // captures `this` (MyActivity) here!
            }
        }
    }
    // Activity is destroyed → but coroutine in GlobalScope continues running!
    // Holds reference to MyActivity (via `this` in the lambda) → LEAK!
}

// FIX: use lifecycle-bound scope:
class MyActivity : Activity() {
    override fun onCreate(...) {
        lifecycleScope.launch {  // cancelled when Activity is destroyed!
            val result = api.fetchData()
            updateUI(result)
        }
    }
}
```

**`GlobalScope` leak chain:** `GlobalScope.Job` → coroutine → lambda → `this` (Activity). GlobalScope's Job is never cancelled → Activity never freed ([Q10.3 — Exception handling rules](10_structured_concurrency.md#q103--exception-handling-rules)).

---

### Leak 5: Unregistered Listener

Three common examples:

```kotlin
// 1. BroadcastReceiver:
class MyActivity : Activity() {
    private val receiver = MyBroadcastReceiver()

    override fun onResume() {
        registerReceiver(receiver, IntentFilter("MY_ACTION"))  // register
    }

    override fun onPause() {
        unregisterReceiver(receiver)  // MUST unregister! Or memory leaks.
    }
}

// 2. SensorManager:
class SensorActivity : Activity() {
    private val sensorManager by lazy { getSystemService(SENSOR_SERVICE) as SensorManager }
    private val sensorListener = object : SensorEventListener { ... }

    override fun onResume() { sensorManager.registerListener(sensorListener, ...) }
    override fun onPause() { sensorManager.unregisterListener(sensorListener) }
}

// 3. EventBus / custom listener:
class MyFragment : Fragment() {
    override fun onStart() { EventBus.getDefault().register(this) }
    override fun onStop() { EventBus.getDefault().unregister(this) }
}
```

---

## Q17.2 — RecyclerView Internals

> **Builds on:** [Q17.1 — Memory Leaks](17_performance_and_memory.md#q171--memory-leaks--top-5-causes) · [Q16.1 — Fragment Lifecycle](16_android_system_internals.md#q161--activity-and-fragment-lifecycle)
> **Connects to:** [Q17.3 — The 16ms Budget](17_performance_and_memory.md#q173--the-16ms-budget)
> **Reference:** [Android Docs — RecyclerView](https://developer.android.com/develop/ui/views/layout/recyclerview)

### The 4-Level Cache

RecyclerView has a sophisticated recycling system to avoid inflating views unnecessarily:

```
Level 1 — SCRAP CACHE (fastest):
  Views that are still "attached" but about to be recycled (during layout pass)
  Retrieved by exact position — no rebind needed!

Level 2 — CACHE (fast):
  Recently scrolled-off views (default: holds 2)
  Retrieved by position — no rebind needed!
  (The view still has valid data for its position)

Level 3 — VIEW CACHE EXTENSION (custom):
  User-defined cache layer (rarely used, very specialized)

Level 4 — RECYCLED VIEW POOL (slow):
  Views by view type — need rebind (onBindViewHolder called)
  Default capacity: 5 per view type
  Shared across multiple RecyclerViews with setRecycledViewPool()
```

```
Scroll down → item goes off screen:
1. Try Scrap → not available (new layout)
2. Try Cache → holds last 2 items → retrieved without rebind!
3. Try ViewCacheExtension → custom logic
4. Try RecycledViewPool → get a ViewHolder, call onBindViewHolder, rebind

onCreateViewHolder called only when: pool is empty AND no recycled views available
```

### `setHasFixedSize(true)` — What It Skips

```kotlin
recyclerView.setHasFixedSize(true)
```

This tells RecyclerView: "The adapter changes don't affect my size. Skip re-measuring me on every change."

Without `setHasFixedSize(true)`: Every `notifyDataSetChanged()` triggers a full `requestLayout()` → RecyclerView re-measures itself → potentially re-measures the parent → expensive!

With `setHasFixedSize(true)`: Only re-layouts RecyclerView's children. Skips the parent chain re-measurement.

**Use when:** RecyclerView's size doesn't depend on adapter content (fixed height/width, `match_parent`, etc.).

### `notifyDataSetChanged()` vs `submitList()` with `DiffUtil`

```kotlin
// BAD — notifyDataSetChanged():
adapter.notifyDataSetChanged()
// Effect: EVERY visible item is recycled and rebound
// Animation: none (no add/remove/move animations)
// Performance: O(N) rebinds even if 1 item changed
// Problem: RecyclerView can't animate changes — jarring UX

// GOOD — DiffUtil + submitList (with ListAdapter):
class UserAdapter : ListAdapter<User, UserViewHolder>(
    object : DiffUtil.ItemCallback<User>() {
        override fun areItemsTheSame(old: User, new: User) = old.id == new.id
        override fun areContentsTheSame(old: User, new: User) = old == new
    }
) { ... }

adapter.submitList(newList)
// DiffUtil runs on background thread, finds minimum changes,
// then RecyclerView animates only the changed items!
```

### Myers' Diff Algorithm

DiffUtil uses Myers' diff algorithm to find the minimum set of edits (insertions, deletions) to transform the old list to the new list.

- Time complexity: `O((N + D²)` where `N` = list size, `D` = edit distance
- Practical limit: ~1,000 items efficiently. For larger lists, consider chunking.

```kotlin
// For lists > 1000 items, DiffUtil can be slow even on background thread:
// Consider: paged loading, sorting changes, or limiting batch sizes
```

### RecyclerView Inside NestedScrollView — Anti-Pattern

```xml
<!-- ANTI-PATTERN: RecyclerView inside NestedScrollView -->
<NestedScrollView>
    <LinearLayout>
        <TextView android:text="Header" />
        <RecyclerView
            android:layout_height="wrap_content" /> <!-- PROBLEM! -->
    </LinearLayout>
</NestedScrollView>
```

**What happens:** `wrap_content` height causes RecyclerView to measure ALL items at once — it cannot recycle! Every item is inflated and measured, regardless of whether it's visible. For 1,000 items, all 1,000 views are in memory simultaneously.

**Fix options:**
1. **Use `ConcatAdapter`** — combine header adapter + content adapter, keep RecyclerView as the root with `match_parent`
2. **Use `addItemDecoration`** — add header-like decorations to RecyclerView itself
3. **Set a fixed height** on RecyclerView (not `wrap_content`) — recycling works
4. **Use Compose** with `LazyColumn` — handles this natively

---

## Q17.3 — The 16ms Budget

> **Builds on:** [Q17.2 — RecyclerView](17_performance_and_memory.md#q172--recyclerview-internals) · [Q16.5 — Handler/Looper (main thread)](16_android_system_internals.md#q165--handler-looper-and-messagequeue)
> **Connects to:** [Q17.4 — Testing](17_performance_and_memory.md#q174--testing)
> **Reference:** [Android Docs — Slow rendering](https://developer.android.com/topic/performance/vitals/render)

### First Principles: Why 16ms?

Displays typically refresh at 60 frames per second (60 FPS). Time per frame = 1000ms / 60 = **16.67ms**. If any frame takes longer than 16ms to produce, the display misses that frame and shows the previous one — a dropped frame, visible as "jank" (stuttering animation).

High refresh rate displays (90Hz, 120Hz) reduce this budget to 11ms or 8ms.

### Three Phases of Rendering

```
Every frame: Measure → Layout → Draw

1. MEASURE: How big should each view be?
   ViewGroup.measure() → recursive, can be expensive for complex hierarchies

2. LAYOUT: Where should each view be positioned?
   ViewGroup.layout() → sets final positions and sizes

3. DRAW: Paint each view onto a Canvas.
   View.onDraw() → most expensive if creating objects, complex paths

Each phase is triggered when:
  - Measure/Layout: view requests layout (invalidate + requestLayout)
  - Draw: view requests redraw (invalidate only)

requestLayout() triggers all 3. invalidate() triggers only Draw.
```

**Optimization:** Only call `invalidate()` (not `requestLayout()`) when only appearance changes, not size/position. `setHasFixedSize(true)` on RecyclerView avoids unnecessary `requestLayout()` up the tree.

### Never Create Objects in `onDraw`

```kotlin
// WRONG — creates Paint object on every frame:
class TemperatureView(context: Context) : View(context) {
    override fun onDraw(canvas: Canvas) {
        val paint = Paint()  // ALLOCATED ON EVERY DRAW CALL!
        paint.color = Color.RED
        paint.textSize = 48f
        canvas.drawText("23°C", 0f, 100f, paint)
    }
}

// CORRECT — create once in init:
class TemperatureView(context: Context) : View(context) {
    private val paint = Paint().apply {  // created ONCE
        color = Color.RED
        textSize = 48f
    }

    override fun onDraw(canvas: Canvas) {
        canvas.drawText("23°C", 0f, 100f, paint)  // no allocation!
    }
}
```

**Why:** `onDraw` is called at 60 FPS = 60 times per second. Creating a `Paint` object 60 times/second generates significant GC pressure. GC pauses can cause dropped frames.

Same rule applies to: `Path`, `RectF`, `Rect`, `Matrix`, `Bitmap`, any `new` in `onDraw`.

### Baseline Profiles

A Baseline Profile is a set of **AOT (Ahead-Of-Time) compilation rules** that tell ART which code paths to compile at install time, rather than JIT-compiled at runtime.

Without Baseline Profiles, ART uses JIT compilation — hot code paths are compiled progressively as the app runs. The first several seconds of app use may be slower as JIT hasn't compiled the hot paths yet.

With Baseline Profiles:
1. You run the app through key user journeys and record which methods are executed
2. This creates a `baseline.prof` file included in your APK
3. At install time, the Play Store / ART pre-compiles those methods
4. **Cold start** and **first-scroll** performance improves dramatically

**Reported improvements:** Major apps (Tinder, Reddit, etc.) report **~30% cold start improvement** and **~15-20% frame time improvement** for first scrolls.

```kotlin
// Generate a Baseline Profile with Macrobenchmark:
@ExperimentalBaselineProfilesApi
class BaselineProfileGenerator {
    @get:Rule
    val rule = BaselineProfileRule()

    @Test
    fun generate() = rule.collectBaselineProfile(
        packageName = "com.example.myapp"
    ) {
        startActivityAndWait()
        device.findObject(By.text("Feed")).click()
        device.waitForIdle()
        // Record: scrolling through feed
        repeat(3) { device.swipe(540, 1500, 540, 500, 100) }
    }
}
```

---

## Q17.4 — Testing

> **Builds on:** [Q9.2 — Dispatchers (TestDispatcher)](09_coroutines_execution_mechanics.md#q92--coroutine-context-and-dispatchers) · [Q10.3 — Exception handling in tests](10_structured_concurrency.md#q103--exception-handling-rules)
> **Connects to:** [Q13.1 — MVVM testability](13_android_architecture.md#q131--mvvm-and-unidirectional-data-flow)
> **Reference:** [Kotlin Coroutines Testing Docs](https://kotlinlang.org/docs/coroutines-test.html)

### `runTest` vs `runBlockingTest`

**`runBlockingTest`** was the old API (deprecated in kotlinx.coroutines 1.6).
**`runTest`** is the current API.

```kotlin
// OLD (deprecated):
@Test
fun testOld() = runBlockingTest {
    // Automatically advances time
}

// NEW:
@Test
fun testNew() = runTest {
    // runTest by default uses StandardTestDispatcher
    // Time is controlled, virtual clock
    delay(5000)  // doesn't actually wait 5 seconds — advances virtual clock!
}
```

Key feature: `runTest` uses a **virtual clock**. `delay(5000)` doesn't pause the test for 5 real seconds — it advances virtual time instantly.

### `StandardTestDispatcher` vs `UnconfinedTestDispatcher`

[**`StandardTestDispatcher`**](09_coroutines_execution_mechanics.md#q92--coroutine-context-and-dispatchers) (default in `runTest`):
- Coroutines do NOT run until you explicitly advance time or call `runCurrent()`
- Gives you full control: test assertions can happen "between" coroutine steps

```kotlin
@Test
fun testStandard() = runTest {
    // StandardTestDispatcher — coroutines queued but NOT running

    val job = launch { delay(1000); emit("result") }
    // job is queued but hasn't run yet!

    advanceTimeBy(1001)  // advance clock past the delay
    // Now the coroutine runs!

    assertEquals("result", lastEmitted)
}
```

**`UnconfinedTestDispatcher`:**
- Coroutines run eagerly — they execute as far as possible before returning control
- Easier for simple tests, but less control

```kotlin
@Test
fun testUnconfined() = runTest(UnconfinedTestDispatcher()) {
    val result = mutableListOf<Int>()

    launch {
        emit(1)
        delay(100)
        emit(2)
    }
    // With UnconfinedTestDispatcher: 1 is emitted immediately
    // Test can check result without needing to advance time for the first emission

    assertEquals(listOf(1), result)
}
```

### Turbine — Flow Testing

[Turbine](https://github.com/cashapp/turbine) is a testing library for Kotlin Flows:

```kotlin
@Test
fun testFlow() = runTest {
    val flow = flowOf(1, 2, 3)

    flow.test {
        assertEquals(1, awaitItem())  // wait for next emission, assert value
        assertEquals(2, awaitItem())
        assertEquals(3, awaitItem())
        awaitComplete()               // assert the flow completes
    }
}

// Testing StateFlow:
@Test
fun testStateFlow() = runTest {
    val viewModel = MyViewModel()

    viewModel.uiState.test {
        assertEquals(UiState.Loading, awaitItem())  // initial state

        viewModel.loadData()
        assertEquals(UiState.Content(testData), awaitItem())  // after load
    }
}
```

### Test Double Hierarchy

| Type | Description | When to Use |
|------|-------------|-------------|
| **Stub** | Returns hardcoded values | When you need deterministic responses, don't care about call verification |
| **Mock** | Records calls, verifiable | When you need to verify interactions (was method called with correct args?) |
| **Fake** | Working implementation (simplified) | When you need realistic behavior (fake DB, fake network) |
| **Spy** | Wraps real object, records calls | When you need real behavior + call verification |

**Prefer Fakes for Repositories:**

```kotlin
// Fake repository — actually stores data in memory, real behavior:
class FakeUserRepository : UserRepository {
    private val users = mutableMapOf<String, User>()

    override suspend fun getUser(id: String): User =
        users[id] ?: throw NotFoundException("User $id not found")

    override suspend fun saveUser(user: User) {
        users[user.id] = user
    }

    // Test helper:
    fun addUser(user: User) { users[user.id] = user }
}

// Test:
@Test
fun `loading user shows content state`() = runTest {
    val fakeRepo = FakeUserRepository()
    fakeRepo.addUser(User("1", "Alice"))
    val viewModel = UserViewModel(fakeRepo)

    viewModel.loadUser("1")

    assertEquals(UiState.Content(User("1", "Alice")), viewModel.uiState.value)
}
```

### Why `adb shell am kill` Simulates Process Death Better Than Home Button

Home button: process stays alive, Activity goes to stopped state.

```bash
# Simulates actual process death (OS kills the process):
adb shell am kill com.example.myapp
# Process is killed as if Android killed it for memory pressure
# SavedStateHandle data will be restored on next launch
# ViewModel is NOT restored (was in memory — gone!)
```

This is the only way to test:
- `SavedStateHandle` restoration
- Room state persistence
- "Process death and restore" user scenario

---

## Master Summary: Performance and Memory in 5 Points

```
┌───────────────────────────────────────────────────────────────────────┐
│  1. Memory leaks: Activity context in singletons, non-static inner   │
│     classes, postDelayed Runnables, GlobalScope coroutines,          │
│     unregistered listeners. Fix: applicationContext, removeCallbacks,│
│     lifecycleScope, unregister in onStop/onDestroy.                 │
│                                                                        │
│  2. RecyclerView 4-level cache: Scrap (no rebind) → Cache (no rebind)│
│     → ViewCacheExtension → RecycledViewPool (rebind required).       │
│     Never put RecyclerView with wrap_content in NestedScrollView.   │
│                                                                        │
│  3. 16ms budget: requestLayout triggers all 3 phases; invalidate     │
│     only triggers Draw. NEVER create objects (Paint, Path) in       │
│     onDraw — pre-allocate in init.                                   │
│                                                                        │
│  4. Baseline Profiles: AOT compile hot paths at install time.        │
│     ~30% cold start improvement. Generated via Macrobenchmark.      │
│                                                                        │
│  5. StandardTestDispatcher: manual time control. UnconfinedTestDispatcher:
│     eager execution. Use Turbine for Flow assertions (awaitItem,    │
│     awaitComplete). Prefer Fake over Mock for repositories.          │
└───────────────────────────────────────────────────────────────────────┘
```

---

*← [Phase 16 — Android System Internals](16_android_system_internals.md) | [Master Chains →](master_chains.md)*
