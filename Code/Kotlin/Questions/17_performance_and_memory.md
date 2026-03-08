# Phase 17 — Performance and Memory

> Performance problems in Android have a common root: the main thread doing too much. Memory leaks have a common root: a long-lived object holding a reference to a short-lived one. Understanding both from first principles — GC roots, reachability, the 16ms render budget — is what separates candidates who can spot the bug from those who need a profiler to find it.

## Navigation

[← Phase 16 — Android System Internals](16_android_system_internals.md) | [→ Phase 18 — Testing](18_testing.md)

## Questions in This File

- [Q17.1 — Memory Leaks — Top 5 Causes](#q171--memory-leaks--top-5-causes)
- [Q17.2 — RecyclerView Internals](#q172--recyclerview-internals)
- [Q17.3 — The 16ms Budget](#q173--the-16ms-budget)

---

# Q17.1 — Memory Leaks — Top 5 Causes

> **Builds on:** [Q0.1 (heap allocation and GC)](phase0_jvm_mental_model_v3.md#q01--primitives-vs-references) · [Q2.4 (anonymous objects and inner classes)](02_classes_and_objects.md#q24--the-object-keyword)
> **Connects to:** [Q16.1 (Activity lifecycle)](16_android_system_internals.md#q161--activity-and-fragment-lifecycle)

---

## The Core Rule

```
Memory leak = long-lived holds ref
  to short-lived → GC can't collect

LIFETIME (longest → shortest):
┌─────────────────────────────┐
│          Process            │
│   ┌─────────────────┐      │
│   │   Application   │      │
│   │  ┌───────────┐  │      │
│   │  │ Activity  │  │      │
│   │  │ ┌───────┐ │  │      │
│   │  │ │ View  │ │  │      │
│   │  │ └───────┘ │  │      │
│   │  └───────────┘  │      │
│   └─────────────────┘      │
└─────────────────────────────┘
Outer holds inner ref → LEAK!
```

---

## Leak 1 — Singleton Holding Activity Context

```kotlin
// WRONG — singleton (process lifetime) holds Activity (shorter lifetime):
object NetworkManager {
    var context: Context? = null
    fun init(ctx: Context) { context = ctx }  // ctx is an Activity!
}
// Activity destroyed on rotation → still referenced by NetworkManager → never GC'd

// CORRECT — use Application context (same lifetime as the singleton):
object NetworkManager {
    lateinit var context: Context
    fun init(ctx: Context) { context = ctx.applicationContext }  // safe
}
```

**Why `applicationContext` is safe:** The `Application` object is itself a singleton — holding it in another singleton creates no additional retention.

---

## Leak 2 — Non-Static Inner Class Holding Outer Reference

```kotlin
// WRONG — inner class holds implicit reference to MyActivity:
class MyActivity : Activity() {
    inner class MyHandler : Handler(Looper.getMainLooper()) {
        override fun handleMessage(msg: Message) {
            // accesses MyActivity's members via implicit outer reference
        }
    }

    val handler = MyHandler()

    override fun onCreate(...) {
        handler.postDelayed({ }, 10_000)  // message lives in queue for 10s
    }
    // User rotates → Activity destroyed → handler still in MessageQueue
    // handler holds MyActivity → MyActivity not GC'd → LEAK for 10s
}

// CORRECT — option 1: remove callbacks in onDestroy:
override fun onDestroy() {
    super.onDestroy()
    handler.removeCallbacksAndMessages(null)
}

// CORRECT — option 2: static class + WeakReference:
private class StaticHandler(activity: WeakReference<MyActivity>) :
    Handler(Looper.getMainLooper()) {
    override fun handleMessage(msg: Message) {
        activity.get()?.handleIt()   // null if Activity was destroyed
    }
}
```

Non-static inner classes and anonymous objects (see [Q2.4](02_classes_and_objects.md#q24--the-object-keyword)) hold an implicit `this$0` reference to the outer class. The Kotlin `inner` keyword generates this reference.

---

## Leak 3 — `postDelayed` Capturing Activity

Same root cause as Leak 2 — a lambda captures `this` and lives in the MessageQueue.

```kotlin
// WRONG — lambda captures `this` (Activity) for 2 seconds:
class SplashActivity : Activity() {
    override fun onCreate(...) {
        Handler(Looper.getMainLooper()).postDelayed({
            startActivity(Intent(this, MainActivity::class.java))
        }, 2000)
    }
    // User presses Back → Activity should die
    // Lambda holds `this` → Activity lives for 2s → LEAK
}

// CORRECT — cancel the runnable if Activity is destroyed:
class SplashActivity : Activity() {
    private val handler = Handler(Looper.getMainLooper())
    private val navigate = Runnable {
        startActivity(Intent(this, MainActivity::class.java))
    }

    override fun onCreate(...) { handler.postDelayed(navigate, 2000) }
    override fun onDestroy() {
        super.onDestroy()
        handler.removeCallbacks(navigate)  // cancel before Activity is GC'd
    }
}
```

---

## Leak 4 — `GlobalScope` Coroutine

```kotlin
// WRONG — GlobalScope lives as long as the process:
class MyActivity : Activity() {
    override fun onCreate(...) {
        GlobalScope.launch {
            val result = api.fetchData()
            withContext(Dispatchers.Main) {
                updateUI(result)  // captures `this` (Activity) here!
            }
        }
    }
}
// Activity destroyed → coroutine keeps running in GlobalScope
// Coroutine holds Activity reference via lambda capture → LEAK

// CORRECT — lifecycle-bound scope:
class MyActivity : Activity() {
    override fun onCreate(...) {
        lifecycleScope.launch {   // cancelled when Activity is destroyed
            val result = api.fetchData()
            updateUI(result)
        }
    }
}
```

**Leak chain:** `GlobalScope.Job` (never cancelled) → coroutine → lambda → `this` (Activity). Since `GlobalScope.Job` is never cancelled, the chain is never broken.

---

## Leak 5 — Unregistered Listener

```kotlin
// BroadcastReceiver — must pair register/unregister:
class MyActivity : Activity() {
    private val receiver = MyReceiver()

    override fun onResume() {
        super.onResume()
        registerReceiver(receiver, IntentFilter("MY_ACTION"))
    }
    override fun onPause() {
        super.onPause()
        unregisterReceiver(receiver)  // MUST match the register call
    }
}

// SensorManager — same pattern:
override fun onResume() { sensorManager.registerListener(listener, sensor, RATE) }
override fun onPause() { sensorManager.unregisterListener(listener) }

// EventBus:
override fun onStart() { EventBus.getDefault().register(this) }
override fun onStop() { EventBus.getDefault().unregister(this) }
```

The system/bus holds a reference to the listener. If you never unregister, the system holds the Activity forever.

---

## ## Traps

**Trap — `WeakReference` not checked before use:**

```kotlin
// WRONG:
activity.get().doSomething()   // NPE if Activity was collected

// CORRECT:
activity.get()?.doSomething()  // safe-call, no-op if collected
```

**Trap — Forgetting that ViewBinding in Fragment leaks (Leak 2 variant):**

Fragment's `binding` field holds a view reference. The Fragment object survives back-stack navigation but the view is destroyed in `onDestroyView`. See [Q16.1](16_android_system_internals.md#q161--activity-and-fragment-lifecycle).

---

## Memory Trick

```
5 LEAKS — mnemonic "SHDGU":
  S — Singleton with Activity context     fix: applicationContext
  H — Handler inner class (non-static)   fix: static + WeakReference or removeCallbacks
  D — Delayed Runnable captures `this`   fix: removeCallbacks in onDestroy
  G — GlobalScope coroutine captures this fix: lifecycleScope
  U — Unregistered listener              fix: unregister in matching lifecycle method

RULE: Lifetime of HOLDER must not outlive lifetime of HELD.
  Process > Application > Activity > Fragment > View
  If holder is higher → leak risk.

LeakCanary: install in debug builds only. It detects these automatically.
```

---

## Self-Test

1. What is the definition of a memory leak in terms of GC reachability?
2. Why does a non-static inner class in Java/Kotlin hold a reference to its outer class? What bytecode field is generated?
3. You call `GlobalScope.launch { updateUI() }` in an Activity. Trace the complete leak chain.
4. `registerReceiver()` in `onResume()` — where must the matching `unregisterReceiver()` call go? Why not `onDestroy()`?
5. Why is `context.applicationContext` safe to hold in a singleton?

---

# Q17.2 — RecyclerView Internals

> **Builds on:** [Q17.1 (Memory leaks)](17_performance_and_memory.md#q171--memory-leaks--top-5-causes) · [Q16.1 (Fragment lifecycle)](16_android_system_internals.md#q161--activity-and-fragment-lifecycle)
> **Connects to:** [Q17.3 (16ms budget)](17_performance_and_memory.md#q173--the-16ms-budget)

---

## The Core Rule

```
RecyclerView has a 4-level cache.
Only levels 1 and 2 (Scrap and Cache) avoid onBindViewHolder.
Level 4 (RecycledViewPool) requires a rebind.
Level 5 (miss) calls onCreateViewHolder — inflate XML.

wrap_content inside NestedScrollView defeats recycling entirely.
```

---

## The 4-Level Cache

```
Scroll down: item goes off screen.
RecyclerView tries each level:

Level 1 — Scrap cache:
  Views still "attached" during an ongoing layout pass.
  Retrieved by exact position. NO rebind.
  (Used internally during layout, rarely relevant to your code)

Level 2 — Cache (default: 2 items):
  Recently scrolled-off views, cached by position.
  Retrieved by position. NO rebind (view data still valid for that position).
  User scrolls back → item is back instantly from cache.

Level 3 — ViewCacheExtension:
  Custom cache layer. Rarely used. You implement the lookup logic.

Level 4 — RecycledViewPool (default: 5 per view type):
  Views by view type, not by position.
  Retrieved, then MUST call onBindViewHolder (data is stale).
  Shared across multiple RecyclerViews with setRecycledViewPool().

Level 5 — Miss:
  Pool empty. Calls onCreateViewHolder → inflate XML → expensive.
```

```
RECYCLERVIEW CACHE (fast → slow):
┌─────────────────────────────┐
│ L1: Scrap   → 0 rebind ✓  │
│ L2: Cache   → 0 rebind ✓  │
│ L3: Custom ext. (rare)     │
│ L4: Pool    → rebind! ⚠   │
│ L5: MISS    → inflate 🐢  │
└─────────────────────────────┘
Only L1+L2 skip onBindViewHolder
```

---

## `setHasFixedSize(true)` — What It Skips

```kotlin
recyclerView.setHasFixedSize(true)
```

Without: Every `notifyDataSetChanged()` → `requestLayout()` → RecyclerView re-measures → re-measures parent → expensive chain up the view tree.

With: Only relays children. Skips `requestLayout()` to parent. RecyclerView's own size is declared stable.

**Use when:** RecyclerView height/width doesn't change when adapter content changes (e.g., `match_parent`, fixed `dp`).

---

## `notifyDataSetChanged()` vs `DiffUtil`

```kotlin
// WRONG — blunt hammer:
adapter.notifyDataSetChanged()
// All visible items recycled and rebound. No animation. O(N) rebinds.

// CORRECT — surgical diff:
class UserAdapter : ListAdapter<User, UserViewHolder>(
    object : DiffUtil.ItemCallback<User>() {
        override fun areItemsTheSame(old: User, new: User) = old.id == new.id
        // identity check — is this the same logical item?

        override fun areContentsTheSame(old: User, new: User) = old == new
        // equality check — did the data change?
    }
)

adapter.submitList(newList)
// DiffUtil runs Myers' diff on a background thread.
// RecyclerView animates only the changed items.
// Unchanged items: no rebind.
```

**Myers' diff complexity:** `O(N + D²)` where `N` = list size, `D` = edit distance. Practical limit: ~1,000 items. Beyond that, consider pre-computing diffs or paging.

---

## `wrap_content` in `NestedScrollView` — The Anti-Pattern

```xml
<!-- WRONG: -->
<NestedScrollView>
    <LinearLayout>
        <TextView ... />
        <RecyclerView
            android:layout_height="wrap_content" />  ← kills recycling
    </LinearLayout>
</NestedScrollView>
```

**What happens:** `wrap_content` forces RecyclerView to measure all items at once to determine its own height. All N items are inflated and kept in memory simultaneously. Recycling is disabled — the pool is never used.

**Fix options:**

```
Option 1: ConcatAdapter
  Combine header adapter + items adapter. Keep RecyclerView as the root with match_parent.

Option 2: Fixed height
  android:layout_height="400dp"  — recycling works but height is fixed.

Option 3: Compose LazyColumn
  Handles this natively — only visible items are composed.
```

---

## ## Traps

**Trap — `setHasFixedSize(true)` when size CAN change:**

```kotlin
// WRONG — RecyclerView grows as items are added:
recyclerView.layoutParams.height = WRAP_CONTENT
recyclerView.setHasFixedSize(true)
// RecyclerView won't re-measure on notifyItemInserted → wrong size shown
```

**Trap — `notifyDataSetChanged()` in animations:**

```kotlin
// WRONG — no animation, all items flash:
fun onUserUpdated(newList: List<User>) {
    items = newList
    adapter.notifyDataSetChanged()
}

// CORRECT — smooth animation:
fun onUserUpdated(newList: List<User>) {
    adapter.submitList(newList)  // DiffUtil handles animation
}
```

**Trap — `areContentsTheSame` returning false for equal objects:**

```kotlin
// WRONG — data class with a mutable list field breaks equality:
data class User(val id: String, val tags: MutableList<String>)
// MutableList equality depends on content, but if mutated in place,
// the same list reference shows equal even when content changed.
// Fix: use immutable List<String>
```

---

## Memory Trick

```
4-LEVEL CACHE (fastest → slowest):
  1. Scrap     → still attached, exact position → NO rebind
  2. Cache     → recently scrolled off (2) → NO rebind
  3. Extension → custom (rare)
  4. Pool      → by view type (5 per type) → MUST rebind
  5. Miss      → onCreateViewHolder → inflate → expensive

Only 1 and 2 skip onBindViewHolder.

setHasFixedSize(true): skip requestLayout() to parent → only when size doesn't change.

DiffUtil vs notifyDataSetChanged:
  notifyDataSetChanged → O(N) rebinds, no animation.
  submitList (ListAdapter) → Myers' diff on BG thread, animate only changes.
  DiffUtil limit: ~1,000 items.

NEVER: RecyclerView wrap_content inside NestedScrollView
  = all N items inflated simultaneously = recycling disabled = OOM risk for large lists.
```

---

## Self-Test

1. Name the 4 cache levels in RecyclerView. Which ones avoid `onBindViewHolder`? Which requires it?
2. What does `setHasFixedSize(true)` skip? When is it wrong to use it?
3. You change one item in a list of 500 and call `notifyDataSetChanged()`. How many `onBindViewHolder` calls happen? What about `submitList()`?
4. Why does `wrap_content` on a RecyclerView inside a `NestedScrollView` disable recycling?
5. What is Myers' diff algorithm? What is its practical size limit for smooth performance?

---

# Q17.3 — The 16ms Budget

> **Builds on:** [Q17.2 (RecyclerView)](17_performance_and_memory.md#q172--recyclerview-internals) · [Q16.5 (main thread message loop)](16_android_system_internals.md#q165--handler-looper-and-messagequeue)
> **Connects to:** [Q17.1 (allocation → GC pressure)](17_performance_and_memory.md#q171--memory-leaks--top-5-causes)

---

## The Core Rule

```
60 FPS = 16.67ms per frame. 90Hz = 11ms. 120Hz = 8ms.
Miss the budget → dropped frame → visible jank.

Three phases per frame: Measure → Layout → Draw.
requestLayout() triggers all 3. invalidate() triggers only Draw.
NEVER allocate objects inside onDraw() — runs 60 times/second.
```

---

## Three Phases of Rendering

```
16ms FRAME BUDGET (60 FPS):
┌──────────┬────────┬────────┐
│ MEASURE  │ LAYOUT │  DRAW  │
│ how big? │ where? │ paint  │
└──────────┴────────┴────────┘
requestLayout() → all 3 phases
invalidate()    → Draw only ✓

Triggered by:
  size/pos changes → requestLayout
  color/text       → invalidate

onDraw() runs 60×/sec:
  ✗ new Paint() inside → GC → jank
  ✓ val paint in init  → zero alloc
```

**Optimization rule:** Call `invalidate()` when only appearance changes (color, text content). Call `requestLayout()` only when size or position changes.

---

## Never Allocate in `onDraw()`

```kotlin
// WRONG — creates Paint on every frame (60 times/second):
class TemperatureView(context: Context) : View(context) {
    override fun onDraw(canvas: Canvas) {
        val paint = Paint()    // 60 allocations/second → GC pressure → dropped frames
        paint.color = Color.RED
        paint.textSize = 48f
        canvas.drawText("23°C", 0f, 100f, paint)
    }
}

// CORRECT — allocate once in init:
class TemperatureView(context: Context) : View(context) {
    private val paint = Paint().apply {   // created ONCE
        color = Color.RED
        textSize = 48f
    }

    override fun onDraw(canvas: Canvas) {
        canvas.drawText("23°C", 0f, 100f, paint)  // zero allocation per frame
    }
}
```

**Objects to pre-allocate:** `Paint`, `Path`, `RectF`, `Rect`, `Matrix`, any `Bitmap` used for drawing.

---

## `requestLayout()` vs `invalidate()` — Cost Comparison

```
requestLayout():
  View → parent.requestLayout() → parent.parent.requestLayout() → ... → root
  Full Measure + Layout + Draw chain.
  Slow for deep hierarchies. Avoid in animations.

invalidate():
  View → mark as dirty → next Vsync: only Draw phase runs.
  No re-measurement. No re-layout. Fast.

Animation rule: use invalidate() in onDraw(), not requestLayout().
```

---

## Baseline Profiles — AOT for Hot Paths

Without a Baseline Profile, ART uses JIT compilation. The first several seconds of app use are slower as JIT hasn't compiled the hot paths.

With a Baseline Profile:
1. Record critical user journeys (app startup, first scroll) using `Macrobenchmark`
2. Generate `baseline.prof` — a list of methods to pre-compile
3. Include in the APK → Play Store pre-compiles at install time
4. Cold start and first-scroll are faster

```kotlin
// Macrobenchmark to generate the profile:
@ExperimentalBaselineProfilesApi
class BaselineProfileGenerator {
    @get:Rule val rule = BaselineProfileRule()

    @Test
    fun generate() = rule.collectBaselineProfile("com.example.myapp") {
        startActivityAndWait()
        device.findObject(By.text("Feed")).click()
        repeat(3) { device.swipe(540, 1500, 540, 500, 100) }
    }
}
```

**Reported improvement:** ~30% cold start, ~15-20% first-scroll frame time. Major apps (Tinder, Reddit) have published these numbers.

---

## ## Traps

**Trap — `postInvalidate()` vs `invalidate()`:**

```kotlin
// From a background thread:
invalidate()         // crashes — not on main thread!
postInvalidate()     // safe — posts invalidate() as a message to main thread Looper
```

**Trap — `clipRect` forgetting to restore canvas state:**

```kotlin
// WRONG — clipRect state leaks to next onDraw:
override fun onDraw(canvas: Canvas) {
    canvas.clipRect(...)
    drawSomething(canvas)
    // forgot to restore
}

// CORRECT:
override fun onDraw(canvas: Canvas) {
    val save = canvas.save()
    canvas.clipRect(...)
    drawSomething(canvas)
    canvas.restoreToCount(save)   // restore clip state
}
```

**Trap — `setWillNotDraw(false)` missing on custom ViewGroups:**

By default, `ViewGroup.setWillNotDraw(true)`. If you override `onDraw()` in a ViewGroup, Android may skip your `onDraw()` unless you call `setWillNotDraw(false)` in `init`.

---

## Memory Trick

```
16ms = 1000ms / 60 FPS. (90Hz → 11ms. 120Hz → 8ms.)

THREE PHASES: Measure → Layout → Draw.
  requestLayout() = all 3.  invalidate() = Draw only.
  Rule: invalidate() for appearance. requestLayout() for size/position.

ONDRAW RULE: NEVER allocate. NEVER.
  BAD:  val paint = Paint()  inside onDraw = 60/s = GC = dropped frames
  GOOD: val paint = Paint()  in init block, reused forever

Pre-allocate: Paint, Path, RectF, Rect, Matrix, Bitmap.

BASELINE PROFILES:
  JIT = compile at runtime (slow first use).
  AOT via Baseline Profile = compile at install time (~30% faster cold start).
  Tool: Macrobenchmark + BaselineProfileRule → baseline.prof → include in APK.
```

---

## Self-Test

1. Why is the render budget 16ms? What happens if a frame takes 20ms?
2. What is the difference between `requestLayout()` and `invalidate()`? When should you use each?
3. Why is allocating a `Paint` inside `onDraw()` a problem? What is the correct pattern?
4. What is a Baseline Profile? What problem does it solve and how is it generated?
5. You update an animated progress bar's progress value. Should you call `requestLayout()` or `invalidate()`? Why?

---

## Phase 17 — Summary

```
┌──────────────────────────────────────────────────────────────────────┐
│  1. 5 leaks (SHDGU): Singleton context, Handler inner class,        │
│     postDelayed capture, GlobalScope, Unregistered listener.        │
│     Rule: holder lifetime must not outlive held object lifetime.    │
│                                                                      │
│  2. RecyclerView 4-level cache: Scrap → Cache → Extension → Pool.  │
│     Only Scrap and Cache skip onBindViewHolder.                     │
│     wrap_content in NestedScrollView disables recycling.            │
│     DiffUtil (submitList) > notifyDataSetChanged for UX + perf.    │
│                                                                      │
│  3. 16ms budget: Measure → Layout → Draw.                          │
│     requestLayout = all 3. invalidate = Draw only.                 │
│     NEVER allocate in onDraw (Paint, Path, RectF, etc.).           │
│     Baseline Profiles: AOT compile hot paths → ~30% faster start.  │
└──────────────────────────────────────────────────────────────────────┘
```

---

*← [Phase 16 — Android System Internals](16_android_system_internals.md) | [Phase 18 — Testing →](18_testing.md)*