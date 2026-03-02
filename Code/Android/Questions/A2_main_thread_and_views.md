# Phase A2 — Main Thread, Looper & View System

If Phase A0 is the foundation of the Android OS and Phase A1 is the lifecycle contract, Phase A2 is the engine that makes your UI run. Every touch event, every animation frame, every layout pass, every text measurement — everything that affects what the user sees — flows through a single thread: the main thread. Understanding this thread's architecture (Looper, MessageQueue, Handler) explains why "don't do I/O on the main thread" is not just advice but a mechanistic necessity. Understanding how the View system measures, positions, and draws itself explains every layout performance problem you will ever encounter.

---

## A2.1 — Looper, MessageQueue & Handler

> **Builds on:** [A0.2 — Zygote & App Startup](A0_android_platform.md#a02--zygote--app-startup) · [A0.4 — Binder IPC](A0_android_platform.md#a04--binder-ipc)
> **Connects to:** [A2.2 — ANR](A2_main_thread_and_views.md#a22--anr-application-not-responding)

### WHY This Architecture Exists

The main thread needs to handle events from many sources simultaneously:
- Touch input from the input driver (via InputManagerService → Binder → InputChannel)
- Lifecycle callbacks from ActivityManagerService (via Binder → ApplicationThread)
- Timer-based events (animations, postDelayed callbacks)
- Results from background threads (post computation result to UI)
- Vsync signals from Choreographer (for frame rendering)

A naive approach would be to use multiple threads for these — but then all of them would need synchronization to safely modify the View hierarchy. Android's solution is simpler: serialize ALL of these events through a single queue on a single thread. There are no race conditions on the View hierarchy because only one thread ever touches it.

This is the **event loop** pattern — identical in concept to JavaScript's event loop, Node.js, and GUI frameworks everywhere.

### The Three Components

```
┌────────────────────────────────────────────────────────────────────────┐
│  MAIN THREAD                                                           │
│                                                                        │
│  MessageQueue                           Looper                         │
│  ┌──────────────────────────────┐      ┌──────────────────────────┐   │
│  │ Message(target=H, what=DRAW) │      │ loop() {                 │   │
│  │ Message(target=H, what=TOUCH)│  ◄── │   msg = queue.next()    │   │
│  │ Message(target=H, what=PAUSE)│      │   msg.target.dispatchMsg│   │
│  │ ...                          │      │   // repeat forever      │   │
│  └──────────────────────────────┘      │ }                        │   │
│                                        └──────────────────────────┘   │
│                                                                        │
│  Handler(H)                                                            │
│  ┌──────────────────────────────────────────────────────────────┐     │
│  │ dispatchMessage(msg) → handleMessage(msg) [switch msg.what]  │     │
│  └──────────────────────────────────────────────────────────────┘     │
└────────────────────────────────────────────────────────────────────────┘
```

**MessageQueue:** A priority queue (sorted by time) of `Message` objects. Each `Message` has:
- `target`: the `Handler` that should receive it
- `what`: an integer code the Handler uses to identify the message type
- `obj` / `arg1` / `arg2`: optional payload
- `when`: the scheduled delivery time (milliseconds from `SystemClock.uptimeMillis()`)

**Looper:** Owns the `MessageQueue`. `Looper.loop()` is an infinite loop that:
1. Calls `queue.next()` — blocks if the queue is empty or if the next message's `when` is in the future
2. When a message is ready, delivers it: `msg.target.dispatchMessage(msg)`
3. Repeat forever

**Handler:** Sends messages to a queue and receives them. A `Handler` is permanently associated with one `Looper` (and thus one thread). You can create a `Handler` anywhere but it will always deliver to the thread that owns the `Looper` it was constructed with.

### How a Touch Event Reaches Your View

Follow a finger tap from hardware to `View.onClick()`:

```
1. User taps screen
     ↓
2. Touchscreen driver generates interrupt → kernel input event
     ↓
3. InputManagerService (in system_server) reads the event
     ↓ (via InputChannel — a socket pair between system_server and your app)
4. NativeInputEventReceiver in your app's process wakes up
     ↓
5. Event is dispatched to ViewRootImpl on the main thread
   (via Handler message: MSG_DISPATCH_INPUT_EVENT)
     ↓
6. Looper picks up the message → Handler dispatches
     ↓
7. ViewRootImpl.processInputEvent()
     ↓
8. DecorView.dispatchTouchEvent()
     ↓ (down the View hierarchy)
9. Your Button.dispatchTouchEvent() → performClick() → onClick()
```

Every step after step 4 happens on the main thread, sequentially. If your `onClick()` takes 100ms, the next touch event is stuck behind it in the queue.

### Handler: Posting to the Main Thread

The most common use of `Handler` is posting from a background thread to the main thread:

```kotlin
// Kotlin idiomatic approach (uses Handler internally):
view.post { /* runs on main thread */ }

// Direct Handler approach:
val mainHandler = Handler(Looper.getMainLooper())

// Post a Runnable (wraps it in a Message):
mainHandler.post {
    textView.text = "Updated from background thread"
}

// Post with delay:
mainHandler.postDelayed({
    showTimeoutMessage()
}, 5000)  // executes 5 seconds from now (not a separate thread — scheduled message)

// Post at a specific time:
mainHandler.postAtTime({ doWork() }, SystemClock.uptimeMillis() + 1000)

// Remove pending callbacks (CRITICAL to avoid memory leaks):
mainHandler.removeCallbacks(myRunnable)
mainHandler.removeCallbacksAndMessages(null)  // remove ALL pending messages
```

### HandlerThread: Looper on a Background Thread

Sometimes you need a persistent background thread with its own event loop (not a one-off executor task). `HandlerThread` creates a thread that runs a `Looper`:

```kotlin
val handlerThread = HandlerThread("DatabaseThread")
handlerThread.start()  // starts the thread and prepares its Looper

val bgHandler = Handler(handlerThread.looper)

// Post work to the background thread:
bgHandler.post {
    // runs on DatabaseThread, NOT main thread
    database.insert(entity)
    // post result back to main thread:
    mainHandler.post { updateUI(result) }
}

// Cleanup:
handlerThread.quitSafely()  // finish pending messages then stop
```

`HandlerThread` is used internally by `WorkManager`, `SurfaceView`'s render thread, `Glide`'s disk cache thread, and many other Android framework components.

### The `postDelayed` Mental Model

`postDelayed(runnable, 5000)` does NOT start a new thread. It schedules a Message in the MessageQueue with `when = SystemClock.uptimeMillis() + 5000`. `Looper.loop()` calls `queue.next()`, which blocks until `when` is reached, then delivers the message. The runnable executes on the SAME thread as the Looper — the main thread. This is why:

```kotlin
mainHandler.postDelayed({
    heavyWork()  // THIS BLOCKS THE MAIN THREAD 5 seconds after it was posted
}, 5000)
```

The 5-second delay only delays when the Runnable is placed into the dispatch queue. The Runnable itself still blocks the main thread when it runs.

---

## A2.2 — ANR: Application Not Responding

> **Builds on:** [A2.1 — Looper, MessageQueue & Handler](A2_main_thread_and_views.md#a21--looper-messagequeue--handler)
> **Connects to:** [A2.3 — View Measure/Layout/Draw](A2_main_thread_and_views.md#a23--view-measurelayoutdraw-pipeline)

### WHY ANRs Happen

An ANR (Application Not Responding) dialog appears when the Android OS detects that the main thread has been unresponsive for too long. The system monitors the main thread by sending "ping" messages through the event loop and checking if they're processed within the timeout. If the main thread is blocked (doing I/O, holding a lock, computing heavily), these pings never get processed → ANR.

### ANR Thresholds

```
Input dispatch timeout:   5 seconds  ← most common
  The main thread did not process an input event (touch, key) within 5s.
  This is what the user sees as the "spinning wheel" before the dialog appears.

Broadcast receiver:       10 seconds (foreground), 60 seconds (background)
  BroadcastReceiver.onReceive() runs on the main thread.
  If it doesn't return within the timeout → ANR.

Service:                  20 seconds (foreground), 200 seconds (background)
  Service.onCreate() / onStartCommand() / onBind() run on main thread.
  Must complete within timeout.

ContentProvider:          10 seconds
  ContentProvider calls on the main thread must complete within timeout.
```

### Common ANR Causes

**1. Synchronous network/disk I/O on the main thread:**
```kotlin
// WRONG — blocks main thread waiting for network:
val result = URL("https://api.example.com/data").readText()  // could take seconds!
textView.text = result

// WRONG — blocks main thread waiting for disk:
val prefs = File("/data/data/.../prefs.xml").readText()  // could take hundreds of ms

// CORRECT — use coroutines with Dispatchers.IO:
viewLifecycleOwner.lifecycleScope.launch {
    val result = withContext(Dispatchers.IO) {
        URL("https://api.example.com/data").readText()
    }
    textView.text = result   // back on Main dispatcher
}
```

**2. Synchronous Binder calls that block waiting on a slow system service:**
```kotlin
// WRONG — PackageManager.getInstalledPackages() is a Binder call that can
// take hundreds of ms if the package manager is busy:
val packages = packageManager.getInstalledPackages(PackageManager.GET_META_DATA)
```

**3. Lock contention — main thread waiting for a background thread's lock:**
```kotlin
// WRONG — if backgroundThread holds synchronizedLock for 10 seconds:
@GuardedBy("synchronizedLock")
fun mainThreadWork() {  // called from main thread
    synchronized(synchronizedLock) {
        // if background thread holds this lock → ANR
    }
}
```

**4. Heavy computation on the main thread:**
```kotlin
// WRONG — sorting a 100,000-item list on the main thread:
val sorted = items.sortedBy { it.name }  // could take >16ms → visible jank, >5s → ANR
```

### Diagnosing ANRs: The ANR Trace File

When an ANR occurs, Android writes a trace file to `/data/anr/traces.txt` (or `/data/anr/anr_*.txt` on newer versions). This file contains a stack dump of all threads at the moment of the ANR:

```
"main" prio=5 tid=1 Blocked
  | group="main" sCount=1 flags=1 obj=0x... self=0x...
  | sysTid=1234 nice=-10 cgrp=default handle=0x...
  | state=S schedstat=( 0 0 0 ) utm=0 stm=0 core=2 HZ=100
  | stack=0x... stackSize=8192KB
  | held mutexes=
  at com.example.MyClass.processData(MyClass.kt:87)
  - waiting to lock <0x0b9c4567> (a java.lang.Object)  ← BLOCKED HERE
  - held by thread 23

"background-thread" prio=5 tid=23 TimedWaiting
  at java.lang.Object.wait(Object.java:-2)
  - waiting on <0x0c1d2345> (a java.lang.Object)
  at com.example.DbHelper.fetchData(DbHelper.kt:123)  ← HOLDING THE LOCK, WAITING FOR DB
  - locked <0x0b9c4567> (a java.lang.Object)
```

This tells you: the main thread (`tid=1`) is `Blocked` waiting on the lock `0x0b9c4567`, which is held by `tid=23`. `tid=23` is `TimedWaiting` on a DB call. Solution: don't acquire this lock on the main thread.

**StrictMode for detecting ANR-prone patterns during development:**

```kotlin
// In Application.onCreate() during DEBUG builds only:
if (BuildConfig.DEBUG) {
    StrictMode.setThreadPolicy(
        StrictMode.ThreadPolicy.Builder()
            .detectAll()              // detect disk read, disk write, network on main thread
            .penaltyLog()             // log violations to logcat
            .penaltyDeath()           // crash on violation (ensures you notice)
            .build()
    )
    StrictMode.setVmPolicy(
        StrictMode.VmPolicy.Builder()
            .detectLeakedSqlLiteObjects()
            .detectLeakedClosableObjects()
            .detectActivityLeaks()
            .penaltyLog()
            .build()
    )
}
```

---

## A2.3 — View Measure/Layout/Draw Pipeline

> **Builds on:** [A2.1 — Looper & Handler](A2_main_thread_and_views.md#a21--looper-messagequeue--handler)
> **Connects to:** [A2.4 — Choreographer & 16ms Budget](A2_main_thread_and_views.md#a24--choreographer--the-16ms-frame-budget)

### WHY Understanding This Pipeline Matters

Every time your UI updates — a button state changes, a list scrolls, an animation advances — the View system needs to figure out: what size should each View be? where should it be positioned? what should it look like? These three questions are answered by three passes: **Measure**, **Layout**, and **Draw**. Getting any of these wrong — doing heavy work in `onDraw()`, triggering unnecessary layout passes, creating deeply nested hierarchies — is what causes dropped frames, jank, and poor performance. The entire discipline of "optimizing Android UI" is really optimizing these three passes.

### The Pipeline: Three Passes Top-Down

```
          View Hierarchy
                │
    ┌───────────▼───────────┐
    │       DecorView        │    ← root of every Activity's view tree
    │   (FrameLayout)        │
    └───────────┬───────────┘
                │
     ┌──────────▼──────────┐
     │    ContentView       │    ← your setContentView() layout
     │  (LinearLayout, etc.)│
     └──────────┬──────────┘
          ┌─────┴──────┐
          ▼            ▼
     (children)    (children)  ← each child recursively
```

**Pass 1: Measure** — "How big should each View be?"
**Pass 2: Layout** — "Where should each View be placed?"
**Pass 3: Draw** — "What does each View look like?"

Each pass traverses the tree top-down (parent to children). The parent calls each child's measure/layout/draw method, and children recursively call their children's methods.

### Pass 1: Measure

**`ViewGroup.measureChild(child, widthMeasureSpec, heightMeasureSpec)`** is called by each parent for each child. The parent passes **MeasureSpec** constraints.

**MeasureSpec:** A packed 32-bit integer encoding two things:
- **Mode** (2 bits): how the child should interpret the size
- **Size** (30 bits): the available size

```
MeasureSpec modes:
  EXACTLY:      "You must be exactly this size"
                Produced by: match_parent, or specific dp value (e.g., 100dp)
  AT_MOST:      "You can be at most this size"
                Produced by: wrap_content in a parent with a known size
  UNSPECIFIED:  "Be whatever size you want"
                Produced by: ScrollView (lets children be as tall as needed)
```

The child receives the MeasureSpec, measures itself (calls `onMeasure()`), and must call `setMeasuredDimension(width, height)` to declare its measured size.

```kotlin
// Custom View onMeasure:
override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
    val widthMode = MeasureSpec.getMode(widthMeasureSpec)
    val widthSize = MeasureSpec.getSize(widthMeasureSpec)

    val desiredWidth = 200  // what I "want" to be

    val width = when (widthMode) {
        MeasureSpec.EXACTLY -> widthSize           // parent says: be this wide
        MeasureSpec.AT_MOST -> minOf(desiredWidth, widthSize) // wrap to desired but cap at available
        else -> desiredWidth                       // UNSPECIFIED: be as wide as desired
    }

    setMeasuredDimension(width, resolveHeight(heightMeasureSpec))
}
```

### Pass 2: Layout

After measuring, the parent knows each child's desired size. Now it positions them.

**`ViewGroup.onLayout(changed, left, top, right, bottom)`** is called with the parent's final bounds. The parent then calls `child.layout(left, top, right, bottom)` for each child, providing absolute coordinates relative to the parent.

```kotlin
// Simplified LinearLayout vertical onLayout:
override fun onLayout(changed: Boolean, l: Int, t: Int, r: Int, b: Int) {
    var top = paddingTop
    for (child in children) {
        if (child.visibility == GONE) continue
        val childWidth = child.measuredWidth
        val childHeight = child.measuredHeight
        child.layout(
            paddingLeft,
            top,
            paddingLeft + childWidth,
            top + childHeight
        )
        top += childHeight + child.marginBottom
    }
}
```

### Pass 3: Draw

After layout, each View knows its exact bounds. Now it paints itself.

**`View.draw(canvas)`** calls:
1. `drawBackground(canvas)` — draws the background drawable
2. `onDraw(canvas)` — YOUR drawing code; paint the View's content
3. `dispatchDraw(canvas)` — draws children (for ViewGroups)
4. `drawForeground(canvas)` — draws foreground/scrollbars

```kotlin
override fun onDraw(canvas: Canvas) {
    // Draw a circle:
    canvas.drawCircle(width / 2f, height / 2f, radius, paint)
    // Draw text:
    canvas.drawText("Hello", x, y, textPaint)
}
```

**What NOT to do in `onDraw()`:**
```kotlin
// WRONG — object allocation in onDraw() causes GC on every frame:
override fun onDraw(canvas: Canvas) {
    val paint = Paint()  // allocates a new object EVERY FRAME (60 times/second!)
    canvas.drawCircle(cx, cy, r, paint)
}

// CORRECT — allocate once:
private val paint = Paint().apply { color = Color.RED }  // allocated once

override fun onDraw(canvas: Canvas) {
    canvas.drawCircle(cx, cy, r, paint)  // no allocation
}
```

### `invalidate()` vs `requestLayout()`: Two Different Triggers

These two methods trigger different passes:

**`invalidate()`** — "My appearance has changed, redraw me."
- Triggers only the **Draw** pass for this View (and its region on the screen)
- Does NOT trigger Measure or Layout
- Use when: color changed, text changed, animation frame, any visual-only update
- Cost: relatively cheap — only the Draw pass

**`requestLayout()`** — "My size might have changed, re-measure and re-layout the hierarchy."
- Triggers **Measure + Layout + Draw** for this View and potentially its entire parent chain
- Use when: the View's desired size has changed (adding items to a ViewGroup, changing text that changes the size)
- Cost: expensive — may propagate all the way to the root and back

```kotlin
// Just color change — invalidate() only:
fun setHighlighted(highlighted: Boolean) {
    paint.color = if (highlighted) Color.RED else Color.GRAY
    invalidate()        // just redraw, no size change
}

// Text change that might change the View's size — requestLayout():
fun setText(text: String) {
    this.text = text
    requestLayout()     // measured width might change
    invalidate()        // also need to redraw
}
```

### The Overdraw Problem

**Overdraw** occurs when a pixel on screen is drawn multiple times in a single frame. The GPU draws from back to front (painter's algorithm):

```
Background drawable (whole screen)  ← pixel drawn once
  └─ Activity background             ← pixel drawn twice (overdraw!)
       └─ CardView background         ← pixel drawn three times!
            └─ TextView text content   ← pixel drawn four times!
```

Each overdraw wastes GPU time. The GPU doesn't know that lower layers will be covered — it draws all of them. Tools to detect overdraw:
- Developer Options → "Debug GPU overdraw" — overlays colors: blue (1x), green (2x), pink (3x), red (4x+)
- `canvas.clipRect()` in custom Views to explicitly tell the GPU which region actually needs drawing

**Solutions:**
- Remove unnecessary backgrounds (especially from the Window or top-level layouts)
- `ViewGroup.setWillNotDraw(true)` if a ViewGroup doesn't draw anything itself
- Use `canvas.clipRect()` to skip drawing in obscured regions

### Layout Hierarchy Depth and Double Taxation

**Double taxation** occurs when a View is measured TWICE during a single layout pass. This happens with `RelativeLayout` and some uses of `LinearLayout` with `layout_weight`:

```
RelativeLayout measures children TWICE:
  Pass 1: measure children horizontally
  Pass 2: measure children vertically (after resolving relative constraints)
  → O(2n) for n children in the simplest case

ConstraintLayout solves this:
  Uses a constraint solver (Cassowary algorithm)
  Flat hierarchy + single-pass measure for most layouts
  → O(n) for n children
```

Deep hierarchy multiplication: if each level doubles the measure calls, a 10-level `RelativeLayout` nesting could result in 2^10 = 1024 measure calls. This is why the dogma "flatten your hierarchy" exists — but ConstraintLayout makes it achievable without sacrificing expressiveness.

---

## A2.4 — Choreographer & The 16ms Frame Budget

> **Builds on:** [A2.3 — View Measure/Layout/Draw](A2_main_thread_and_views.md#a23--view-measurelayoutdraw-pipeline)
> **Connects to:** [A3 — Jetpack Compose](A3_jetpack_compose.md)

### WHY 16ms? The Physics of Display

A display at 60Hz refreshes its screen exactly 60 times per second — once every 16.67ms. At 90Hz (many modern phones), once every 11.1ms. At 120Hz, once every 8.3ms.

The display hardware reads the GPU's frame buffer at each refresh interval (Vsync signal) and shows whatever is there. If your app hasn't produced a new frame by the time the display reads the buffer, the display shows the SAME frame it showed last time — a **dropped frame**. The user perceives this as stuttering or "jank."

**The 16ms budget:** For 60Hz, your app has exactly 16ms to:
1. Process any pending input events
2. Run any animation callbacks
3. Execute the Measure + Layout + Draw passes
4. Upload the frame to the GPU (RenderThread)

Miss any of these → drop a frame.

### Vsync and Choreographer

**Vsync** (Vertical Sync) is a hardware signal the display sends once per refresh cycle. Android uses Vsync to synchronize all drawing to the display refresh rate, eliminating tearing (where you see part of an old frame and part of a new frame at the same time).

**Choreographer** is the Android class that:
1. Receives Vsync signals from the hardware (via `DisplayEventReceiver`)
2. Batches all pending drawing work and schedules it to run at the START of each Vsync interval
3. Calls registered callbacks in a fixed order: input → animation → traversal (measure/layout/draw)

```
Vsync signal:
─────────────────────────────────────────────────────────────────────►
    │                │                │                │
    ▼ frame 1        ▼ frame 2        ▼ frame 3        ▼ frame 4
 t=0ms            t=16ms           t=32ms           t=48ms

  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
  │ input events │ │ input events │ │ input events │
  │ animations   │ │ animations   │ │ animations   │
  │ measure      │ │ measure      │ │ measure      │
  │ layout       │ │ layout       │ │ layout       │
  │ draw         │ │ draw         │ │ draw         │
  └──────────────┘ └──────────────┘ └──────────────┘
   ≤16ms each        ≤16ms each        ≤16ms each     ← SMOOTH 60fps

If ANY of these exceeds 16ms:
  t=0ms:  frame 1 starts
          │ (takes 25ms — missed Vsync!)
  t=16ms: ▲ Vsync fires — but frame 1 isn't done!
  t=25ms: frame 1 finishes → uploaded to GPU
  t=32ms: ▲ Vsync fires — shows frame 1 again (display has nothing newer)
             ← DROPPED FRAME at t=32ms
```

### The RenderThread (Android 5.0+)

Since Android 5.0, Android has a dedicated `RenderThread` for GPU operations. The flow is:

```
Main Thread (per frame, 16ms budget):
  1. Choreographer callbacks (input, animations)
  2. Measure + Layout
  3. Record drawing commands into a DisplayList (NOT actual GPU calls)
  ─────────────────────────────────── hand off DisplayList ───────────────►

RenderThread (parallel to main thread):
  4. Take the DisplayList
  5. Translate to GPU commands (OpenGL ES / Vulkan calls)
  6. Upload to GPU → frame is in the buffer → display reads it at next Vsync
```

The key insight: **the main thread only records drawing commands** (into a `DisplayList`), it does not execute GPU calls. GPU execution is off-loaded to `RenderThread`. This means:
- Main thread is free to start processing the next frame's input while GPU renders this frame
- GPU uploads can run in parallel with main thread work
- Even if the main thread is temporarily busy, the `RenderThread` can still render a simple animation (like a property animator on a `View` with `hardware acceleration`)

### `View.animate()` vs ObjectAnimator vs ValueAnimator

All animation APIs in Android ultimately register callbacks with Choreographer:

```kotlin
// All of these run their update callbacks on Choreographer's animation phase:
view.animate()
    .translationX(100f)
    .duration = 300

ObjectAnimator.ofFloat(view, "alpha", 0f, 1f).start()

val animator = ValueAnimator.ofFloat(0f, 1f).apply {
    duration = 300
    addUpdateListener { anim ->
        // Called once per frame (every ~16ms)
        val value = anim.animatedValue as Float
        view.alpha = value
    }
    start()
}
```

`view.alpha = value` calls `invalidate()` → schedules a Draw pass for the next Vsync.

**Hardware-accelerated properties (GPU-only, no Measure/Layout pass):**
Animating these properties is handled entirely by `RenderThread` without any main thread work:
- `translationX`, `translationY`, `translationZ`
- `scaleX`, `scaleY`
- `rotation`, `rotationX`, `rotationY`
- `alpha`

These are cheap. Animating `width`, `height`, `text`, or anything that changes layout → triggers Measure + Layout on EVERY frame → expensive.

### Systrace and Perfetto: Measuring Frame Times

To verify your frames fit within budget, use:

```bash
# Capture a Perfetto trace:
adb shell perfetto -c /dev/stdin --txt -o /data/misc/perfetto-traces/trace.pb << EOF
buffers: { size_kb: 65536 }
data_sources: { config { name: "linux.ftrace" ftrace_config { ftrace_events: "sched/sched_switch" ftrace_events: "power/suspend_resume" ftrace_events: "sched/sched_wakeup" } } }
duration_ms: 5000
EOF
adb pull /data/misc/perfetto-traces/trace.pb
```

In Perfetto UI: look for "Choreographer#doFrame" slices on the main thread. Each slice should be <16ms. Long slices = dropped frame. Drill into the slice to see which phase (measure, layout, draw, input) consumed the time.

### The Jank Sources: Quick Reference

```
Source                              What triggers it                Fix
──────────────────────────────────  ──────────────────────────────  ────────────────────────
Heavy onDraw()                      Object allocation, complex ops  Pre-allocate, simplify
requestLayout() during animation    Text change, add/remove View    Cache sizes, avoid layout
                                    that causes parent re-measure   in animation frames
Overdraw                            Stacked opaque backgrounds      Remove backgrounds
Deep hierarchy                      RelativeLayout nesting          ConstraintLayout
Main thread I/O                     Disk read, network in click     Dispatchers.IO coroutine
Slow Adapter.getView/onBind         Heavy inflation, synchronous    ViewHolder, async loading
                                    image decode
GC pressure                         Allocations in draw/scroll      Pool objects, avoid allocs
Large bitmaps                       Decode full-size into memory    BitmapFactory.Options.inSampleSize
Blocking main thread lock           synchronized on heavy data      Coroutines, ConcurrentHashMap
```

---

## Master Summary

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                A2 — Main Thread, Looper & View System                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  1. LOOPER / MESSAGEQUEUE / HANDLER                                         │
│     Main thread = single event loop. Looper.loop() reads Messages from     │
│     MessageQueue and dispatches them to Handlers. NEVER returns.            │
│     Handler posts Messages to a queue. A Handler always delivers to the     │
│     thread that owns its Looper.                                            │
│     view.post {} → schedules Runnable as Message on main Looper.           │
│     postDelayed(r, ms) → schedules r at uptime + ms. NOT a new thread.     │
│     Touch → InputChannel → ViewRootImpl Handler → dispatchTouchEvent()     │
│     Lifecycle callback: AMS → Binder → ApplicationThread → H.post() →     │
│     Activity.onResume() (always on main thread via Handler dispatch)        │
│                                                                             │
│  2. ANR (Application Not Responding)                                        │
│     Input: >5s. Broadcast: >10s. Service: >20s.                            │
│     Causes: network/disk on main thread, blocked lock, heavy compute.      │
│     Diagnose: /data/anr/traces.txt — stack dump of all threads at ANR.    │
│     Fix: move I/O to Dispatchers.IO. Use coroutines. Never block main.    │
│     Detect early: StrictMode.ThreadPolicy in DEBUG builds.                 │
│                                                                             │
│  3. VIEW MEASURE / LAYOUT / DRAW                                            │
│     Three passes, top-down. All on main thread.                            │
│     Measure: parent passes MeasureSpec to child. Child calls               │
│     setMeasuredDimension(). Modes: EXACTLY, AT_MOST, UNSPECIFIED.         │
│     Layout: parent calls child.layout(l,t,r,b) to position each child.    │
│     Draw: drawBackground → onDraw (YOUR code) → dispatchDraw (children).  │
│     invalidate() = redraw only (no measure/layout). Cheap.                │
│     requestLayout() = full measure+layout+draw chain. Expensive.          │
│     onDraw(): NEVER allocate. Pre-create Paint, Path, etc.                │
│     ConstraintLayout: flat + single-pass. RelativeLayout: 2-pass (costly) │
│                                                                             │
│  4. CHOREOGRAPHER & 16ms BUDGET                                             │
│     Display at 60Hz refreshes every 16.67ms (90Hz=11.1ms, 120Hz=8.3ms).  │
│     Missed deadline = dropped frame = jank.                                │
│     Choreographer batches Vsync callbacks: input → animation → traversal  │
│     RenderThread (Android 5+): main thread RECORDS display list;           │
│     RenderThread executes GPU commands in parallel.                        │
│     Hardware-accelerated props (alpha, translation, scale, rotation):      │
│     RenderThread only — no main thread Measure/Layout → always smooth.    │
│     Animating width/height/text → Measure+Layout every frame → expensive. │
│     Profile: Perfetto / Systrace. Find frames > 16ms on main thread.      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

*← [Phase A1 — Activity & Fragment](A1_activity_fragment.md) | [Phase A3 — Architecture Patterns →](A3_architecture_patterns.md)*
