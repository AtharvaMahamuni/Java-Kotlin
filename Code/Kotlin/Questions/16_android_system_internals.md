# Phase 16 — Android System Internals

> The Android main thread is a queue processor running an infinite loop. Every lifecycle callback, every touch event, every `postDelayed` — they are all messages in that queue. Understanding this one fact explains ANRs, Binder limits, Handler deadlocks, and Zygote's role in startup speed.

## Navigation

[← Phase 15 — Networking](15_networking.md) | [→ Phase 17 — Performance and Memory](17_performance_and_memory.md)

## Questions in This File

- [Q16.1 — Activity and Fragment Lifecycle](#q161--activity-and-fragment-lifecycle)
- [Q16.2 — Background Work Evolution](#q162--background-work-evolution)
- [Q16.3 — Binder IPC](#q163--binder-ipc)
- [Q16.4 — Zygote and App Startup](#q164--zygote-and-app-startup)
- [Q16.5 — Handler, Looper, and MessageQueue](#q165--handler-looper-and-messagequeue)

---

# Q16.1 — Activity and Fragment Lifecycle

> **Builds on:** [Q13.3 (ViewModel survives rotation)](13_android_architecture.md#q133--viewmodel-internals)
> **Connects to:** [Q17.1 (Memory leaks)](17_performance_and_memory.md#q171--memory-leaks--top-5-causes) · [Q10.4 (lifecycleScope)](10_structured_concurrency.md#q104--lifecycle-scopes-and-process-death)

---

## The Core Rule

```
Rotation:      onDestroy IS called. Bundle IS passed to new Activity via Binder.
Process death: onDestroy NOT called. OS kills process immediately. No callbacks.

Fragment has TWO lifecycles:
  Fragment object lifetime: onAttach → onDetach
  Fragment VIEW lifetime:   onCreateView → onDestroyView
  ViewBinding must be cleared in onDestroyView or it leaks.
```

---

## Rotation — Exact Callback Order

```
User rotates device:

Old Activity:
  onPause()
  onSaveInstanceState(bundle)  ← Android P+: guaranteed BEFORE onStop
  onStop()
  onDestroy()

New Activity (recreated):
  onCreate(savedInstanceState)  ← same bundle restored
  onStart()
  onResume()
```

**Android P (API 28) change:** Before API 28, `onSaveInstanceState` could be called after `onStop`. From API 28, it's guaranteed before `onStop`. This gives a more predictable window to save state.

The bundle travels via **Binder IPC** to the system server and back. It is subject to the **~1MB Binder transaction limit**.

---

## Process Death — No Callbacks

```
Memory pressure:
  App in background → OS kills the process (no warning, no onDestroy!)
  User returns → system restores Activity from saved instance state (if available)
  ViewModel is GONE (heap is gone). SavedStateHandle survives (Binder store).

Why this matters for onDestroy():
  "Save critical state in onSaveInstanceState, not onDestroy.
   You may never reach onDestroy."
```

---

## ViewModel vs Bundle — What Survives What

```
Event                 ViewModel   Bundle (SavedStateHandle)   Room/DataStore
Rotation              ✓ YES       ✓ YES                       ✓ YES
Process death         ✗ NO        ✓ YES (Binder store)        ✓ YES
Force quit            ✗ NO        ✗ NO                        ✓ YES
```

---

## Fragment's Two Lifecycles — The ViewBinding Leak

A Fragment object survives back-stack navigation (pushed to the back stack). Its VIEW is destroyed (`onDestroyView`) and recreated on return. If `binding` holds the old view, the view can't be GC'd.

```kotlin
// WRONG — binding outlives the view:
class MyFragment : Fragment() {
    private var binding: MyFragmentBinding? = null

    override fun onCreateView(inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?): View {
        binding = MyFragmentBinding.inflate(inflater, container, false)
        return binding!!.root
    }

    // Missing: onDestroyView never clears binding
    // Fragment goes to back stack → view destroyed → binding still holds view reference → LEAK
}

// CORRECT — clear in onDestroyView:
override fun onDestroyView() {
    super.onDestroyView()
    binding = null   // release the view reference
}
```

```
Fragment object:  onAttach ──────────────────────────────── onDetach
Fragment view:             onCreateView ─── onDestroyView
                                              ↑ clear binding HERE
```

---

## `repeatOnLifecycle(STARTED)` and the Back Stack

```kotlin
// In Fragment.onViewCreated:
viewLifecycleOwner.lifecycleScope.launch {
    viewLifecycleOwner.repeatOnLifecycle(Lifecycle.State.STARTED) {
        viewModel.state.collect { render(it) }
    }
}
```

Fragment goes to back stack → `onStop()` → `STARTED` threshold not met → inner block **cancelled** → collection stops, CPU freed.
User presses back → `onStart()` → `STARTED` threshold met → inner block **relaunched** → fresh data collected.

---

## ## Traps

**Trap — `onDestroy` as save point:**

```kotlin
// WRONG — may never be called on process death:
override fun onDestroy() {
    super.onDestroy()
    prefs.save(currentState)  // won't run if OS kills the process
}

// CORRECT:
override fun onSaveInstanceState(outState: Bundle) {
    super.onSaveInstanceState(outState)
    outState.putString("key", currentValue)  // always called before process kill
}
```

**Trap — Fragment.viewLifecycleOwner vs Fragment:**

```kotlin
// WRONG — uses Fragment lifecycle (survives view destruction):
lifecycleScope.launch { viewModel.state.collect { binding!!.text = it } }
// Fragment on back stack → view destroyed → binding!! throws NullPointerException

// CORRECT — use viewLifecycleOwner:
viewLifecycleOwner.lifecycleScope.launch { ... }
```

---

## Memory Trick

```
ROTATION callback order:
  Old: onPause → onSaveInstanceState → onStop → onDestroy
  New: onCreate(bundle) → onStart → onResume

DEATH: no callbacks. Bundle survives (Binder). ViewModel doesn't (RAM).

FRAGMENT: two lifecycles.
  View lifecycle ends at onDestroyView → clear binding here.
  Use viewLifecycleOwner for coroutines, not lifecycleOwner.

Android P+: onSaveInstanceState guaranteed BEFORE onStop.
```

---

## Self-Test

1. What is the exact callback order when a user rotates the device? What is different from process death?
2. A Fragment is pushed to the back stack. What happens to its View? What happens to the Fragment object?
3. Why is `onDestroy` a bad place to save critical state?
4. You hold a `binding` reference in a Fragment without clearing it in `onDestroyView`. Trace the memory leak.
5. What is the difference between `lifecycleScope` and `viewLifecycleOwner.lifecycleScope` in a Fragment?

---

# Q16.2 — Background Work Evolution

> **Builds on:** [Q16.1 (Activity lifecycle)](16_android_system_internals.md#q161--activity-and-fragment-lifecycle)
> **Connects to:** [Q14.2 (WorkManager)](14_jetpack_components.md#q142--workmanager)

---

## The Core Rule

```
A Service runs on the MAIN THREAD. Not a background thread.
"Background" in "background Service" = running while Activity is not visible.
It says nothing about which thread the Service code runs on.
```

---

## Service Runs on the Main Thread

```kotlin
class MyService : Service() {
    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        // THIS IS THE MAIN THREAD
        val data = database.query(...)  // NetworkOnMainThreadException or ANR!

        // Must dispatch work yourself:
        CoroutineScope(Dispatchers.IO).launch {
            val data = database.query(...)  // background thread
        }
        return START_STICKY
    }
}
```

---

## Android 8 (Oreo) Background Execution Limits

**Before API 26:** Services could run indefinitely in the background.

**API 26+:** Background services are killed within ~60 seconds of the app going to background.

```kotlin
// WRONG — crashes on API 26+ when app is in background:
startService(intent)  // IllegalStateException: Not allowed to start service

// CORRECT — use foreground service:
if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
    startForegroundService(intent)  // must call startForeground() within 5 seconds!
} else {
    startService(intent)
}
```

Foreground services show a persistent notification and can run longer.

---

## Android 14 — Foreground Service Types

Android 14 added mandatory foreground service type declarations:

```xml
<!-- AndroidManifest.xml -->
<service
    android:name=".UploadService"
    android:foregroundServiceType="dataSync" />
```

```kotlin
// Must match the manifest type:
startForeground(
    NOTIFICATION_ID,
    notification,
    ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC  // mismatched type → exception
)
```

Valid types: `camera`, `connectedDevice`, `dataSync`, `location`, `mediaPlayback`, `mediaProjection`, `microphone`, `phoneCall`, `shortService`, `specialUse`.

---

## Background Work Evolution

```
AsyncTask (deprecated API 30):
  + ran heavy work on thread pool, posted result to main thread
  − leaked Activity context via inner class
  − sequential execution by default (one task at a time)
  − no retry, no persistence, killed with process

IntentService (deprecated API 30):
  + dedicated background thread + work queue + auto-stopped on empty queue
  − killed by Oreo background limits
  − single-threaded, no coroutine support

WorkManager (current):
  + persisted to Room DB → survives process death and reboot
  + respects Doze mode (defers, doesn't cancel)
  + constraint-aware (network, charging, storage)
  + coroutine support via CoroutineWorker
```

---

## ## Traps

**Trap — "Service runs in the background" meaning a background thread:**

This is the #1 Android misconception. Service = component that runs without UI. Thread = execution context. A Service's `onStartCommand()` is called on the main thread by the Android framework.

**Trap — `startService()` from background on API 26+:**

```kotlin
// WRONG — app in background → IllegalStateException:
startService(Intent(this, UploadService::class.java))

// CORRECT:
ContextCompat.startForegroundService(this, Intent(this, UploadService::class.java))
```

---

## Memory Trick

```
SERVICE ≠ background thread. Service = no Activity, but still on main thread.
  onStartCommand() → main thread → must dispatch to IO yourself.

OREO RULE: background app + startService() = IllegalStateException.
  Fix: startForegroundService() + startForeground() within 5s.

ANDROID 14: foregroundServiceType in manifest AND in startForeground() must match.

EVOLUTION (all deprecated → WorkManager):
  AsyncTask → leaked context, sequential pool
  IntentService → killed by Oreo limits, single thread
  WorkManager → Room-persisted, Doze-aware, coroutines, constraints
```

---

## Self-Test

1. Which thread does `Service.onStartCommand()` run on?
2. A Service starts a network call in `onStartCommand()`. What exception is thrown on a non-rooted device?
3. What happens when you call `startService()` from a background app on Android 8+?
4. What must you call within 5 seconds of `startForegroundService()`? What happens if you don't?
5. Name two reasons `AsyncTask` was deprecated.

---

# Q16.3 — Binder IPC

> **Builds on:** [Q16.4 (Zygote — process model)](16_android_system_internals.md#q164--zygote-and-app-startup)
> **Connects to:** [Q13.3 (SavedStateHandle uses Binder)](13_android_architecture.md#q133--viewmodel-internals)

---

## The Core Rule

```
Binder = Android's IPC mechanism. One memory copy (via mmap), not two.
~1MB transaction buffer per process, shared across ALL concurrent Binder calls.
Exceed it → TransactionTooLargeException.
```

---

## Traditional IPC vs Binder

```
Traditional IPC (pipes, sockets):
  Process A → [copy to kernel buffer] → [copy from kernel buffer] → Process B
  2 copies. Two context switches.

Binder IPC:
  Process A → [single copy via mmap shared region] → Process B
  1 copy. One context switch.
```

Binder achieves one-copy by memory-mapping a region shared between the sender, the kernel driver (`/dev/binder`), and the receiver.

---

## The Architecture

```
Your app process (PID 12345)               system_server (PID 600)
  ┌────────────────────────────┐             ┌───────────────────────────┐
  │  getSystemService(ACTIVITY)│             │  ActivityManagerService   │
  │  → ActivityManager (proxy) │             │  (real implementation)    │
  │          │                 │             │          ▲                │
  │          ▼                 │             │          │                │
  │  BinderProxy               │             │  Binder Stub (onTransact) │
  └──────────┬─────────────────┘             └──────────┬────────────────┘
             │                                           │
             └──────────────► /dev/binder ───────────────┘
                              (kernel driver, 1 copy via mmap)
```

Every `getSystemService()` call crosses this boundary. So does `onSaveInstanceState`, `SavedStateHandle`, and any Intent with large extras.

---

## The ~1MB Transaction Limit

```
android.os.TransactionTooLargeException: data parcel size N bytes
```

The ~1MB buffer is shared across ALL concurrent Binder transactions in your process. Even a single 500KB Bundle can fail if other calls are active simultaneously.

```kotlin
// SAFE — small primitives:
savedState["userId"] = "user_123"           // ~10 bytes ✓
intent.putExtra("tab", 2)                   // 4 bytes ✓

// DANGEROUS — large objects:
savedState["users"] = listOf<User>(...)     // 500+ objects → CRASH
intent.putExtra("bitmap", bitmap)           // bitmap bytes → CRASH

// FIX — store in Room, save only the key:
savedState["selectedUserId"] = "user_123"
// On restore: read selectedUserId → fetch User from Room
```

---

## ## Traps

**Trap — Assuming `onSaveInstanceState` can hold large data:**

```kotlin
// WRONG — may crash with TransactionTooLargeException:
override fun onSaveInstanceState(outState: Bundle) {
    outState.putSerializable("data", largeList)  // large Serializable → crash
}

// CORRECT — save identifier only:
override fun onSaveInstanceState(outState: Bundle) {
    outState.putString("selectedId", selectedUser.id)  // tiny
}
```

**Trap — Forgetting that getSystemService() is a Binder call:**

Calling `getSystemService()` very frequently in a tight loop can add up. Cache the result in a field.

---

## Memory Trick

```
Binder = 1-copy IPC via mmap. Traditional IPC = 2 copies.
~1MB limit = shared across ALL concurrent Binder transactions in the process.

Everything that crosses process boundaries uses Binder:
  getSystemService() → Binder to system_server
  onSaveInstanceState Bundle → Binder to system_server
  SavedStateHandle → same Bundle, same limit
  Intents with large extras → same limit

SAFE in Bundle: String, Int, Boolean, small Parcelable.
UNSAFE: List<User> > ~500 items, any Bitmap.
Error: TransactionTooLargeException.
Fix: save key → fetch from Room on restore.
```

---

## Self-Test

1. How many memory copies does a Binder transaction require? How does it achieve this?
2. What is the approximate transaction size limit? Is it per-call or shared?
3. You put a `List<User>` of 10,000 items into a `Bundle` in `onSaveInstanceState`. What happens?
4. Name three things in Android that use Binder IPC internally.
5. What is `TransactionTooLargeException` and how do you fix it?

---

# Q16.4 — Zygote and App Startup

> **Builds on:** [Q0.3 (class loading)](phase0_jvm_mental_model_v3.md#q03--class-loading-and-the-static--block)
> **Connects to:** [Q16.3 (Binder IPC)](16_android_system_internals.md#q163--binder-ipc) · [Q16.5 (Handler/Looper)](16_android_system_internals.md#q165--handler-looper-and-messagequeue)

---

## The Core Rule

```
Zygote = template process, always running since boot.
  Pre-loads: java.lang.*, android.*, ART runtime, common resources.

App launch = fork() Zygote (copy-on-write).
  Child inherits all pre-loaded classes without re-loading them.
  App-specific code loaded on top.
  Fast startup because most memory is already mapped.
```

---

## The 9-Step Startup Chain

```
User tap
  │ Binder IPC
  ▼
AMS: process alive?
  │ NO
  ▼
Zygote.fork() [Copy-on-Write]
  │ inherit ~50MB pre-loaded
  ▼
ActivityThread.main()
  │
  ▼
Looper.prepareMainLooper()
  │ message dispatched
  ▼
Application.onCreate()
  │
  ▼
Activity.onCreate()
  │
  ▼
First frame drawn ✓
```

---

## Zygote Fork — Why It's Fast

```
Zygote process (always running):
  Pre-loaded: java.lang.*, android.*, ART ~50MB of shared classes

fork() result:
  Child process starts with ALL of Zygote's pages already mapped (CoW)
  Pages are shared, not copied — actual copy only when the page is WRITTEN
  App-specific classes loaded on top (much smaller than Zygote's pre-loaded set)

Without Zygote:
  Every app start → load ART → load java.lang.* → load android.* → seconds
With Zygote:
  Every app start → fork (milliseconds) → load your classes (fast)
```

**Copy-on-Write (CoW):** The child process initially shares all of Zygote's memory pages. A physical copy is made only when either process writes to a page. Read-only pages (class bytecode) are never copied.

---

## `ActivityThread.main()` — Before `Application.onCreate()`

```java
// Simplified Android source (ActivityThread.java):
public static void main(String[] args) {
    Looper.prepareMainLooper();       // 1. create main thread Looper

    ActivityThread thread = new ActivityThread();
    thread.attach(false, startSeq);   // 2. connect to AMS via Binder

    Looper.loop();                    // 3. infinite message loop — never returns
}
```

`Application.onCreate()` is **not** called directly from `main()`. It's dispatched as a **message** to the main Looper by `thread.attach()`. It runs inside `Looper.loop()`.

**Implication:** Heavy work in `Application.onCreate()` delays every future message in the queue. Keep it minimal — lazy-initialize SDKs, never do synchronous I/O here.

---

## ## Traps

**Trap — Slow `Application.onCreate()` delays everything:**

```kotlin
// WRONG — synchronous SDK init in Application.onCreate():
class MyApp : Application() {
    override fun onCreate() {
        super.onCreate()
        analyticsSDK.initSync()    // blocks for 300ms
        crashReporter.initSync()   // blocks for 200ms
        // Every message (including the Activity) is delayed 500ms
    }
}

// CORRECT — lazy init or async:
class MyApp : Application() {
    override fun onCreate() {
        super.onCreate()
        CoroutineScope(Dispatchers.IO).launch {
            analyticsSDK.init()   // non-blocking
        }
    }
}
```

**Trap — Assuming your code runs before `Looper.loop()`:**

`Application.onCreate()` runs inside `Looper.loop()` as a message. Code that expects to run before the Looper starts (e.g., replacing the UncaughtExceptionHandler) should be done before `Looper.loop()` — but that's inside `ActivityThread.main()` which you don't control. The earliest entry point you own is `Application.onCreate()`.

---

## Memory Trick

```
STARTUP CHAIN (9 steps):
  tap → Launcher Binder → AMS checks → Zygote.fork()
  → ActivityThread.main() → Looper.prepareMainLooper()
  → Application.onCreate() → Activity.onCreate() → first frame

ZYGOTE = template, pre-loaded ~50MB of shared classes.
  fork() = CoW (shared until written). Re-loading = never needed.
  Zygote must not be "used" by developers — it's an OS process.

Application.onCreate() runs INSIDE Looper.loop() as a message.
  Heavy work here = delays EVERY future message (Activity, touch events).
  Rule: lazy-init SDKs, no synchronous I/O in Application.onCreate().
```

---

## Self-Test

1. What is Zygote and why does it make app startup fast?
2. What is copy-on-write? When does an actual memory copy happen after a fork?
3. What runs before `Application.onCreate()`? What is `ActivityThread.main()` responsible for?
4. You add a 500ms synchronous SDK init to `Application.onCreate()`. What is the effect on the first Activity launch?
5. Trace the complete path from "user taps app icon" to "first frame is drawn" in 9 steps.

---

# Q16.5 — Handler, Looper, and MessageQueue

> **Builds on:** [Q16.4 (Looper setup in ActivityThread)](16_android_system_internals.md#q164--zygote-and-app-startup) · [Q9.2 (Dispatchers.Main uses Looper)](09_coroutines_execution_mechanics.md#q92--coroutine-context-and-dispatchers)
> **Connects to:** [Q17.3 (16ms budget — message processing time)](17_performance_and_memory.md#q173--the-16ms-budget)

---

## The Core Rule

```
Thread : Looper : MessageQueue : Handler = 1 : 1 : 1 : many
One thread has at most one Looper.
One Looper has one MessageQueue.
Many Handlers can all post to the same MessageQueue.
Looper.loop() processes one message at a time from the queue.
```

```
Thread-A
  └─ Looper (1)
       └─ MessageQueue (1)
            ├─ msg ← Handler-1.post()
            ├─ msg ← Handler-2.post()
            └─ msg ← Handler-3.post()

Many Handlers → 1 queue → 1 thread
```

---

## The Main Thread's Infinite Loop

```
Main thread:
  ActivityThread.main()
       │
       ├── Looper.prepareMainLooper()    ← creates Looper + MessageQueue for this thread
       │
       └── Looper.loop()                 ← infinite loop, never returns
               │
               while (true) {
                 Message msg = queue.next()        // blocks until message arrives
                 msg.target.dispatchMessage(msg)   // Handler processes it
               }

Every callback is a message:
  Activity.onCreate()     → posted as message by AMS
  touch event             → posted as message by InputEventReceiver
  handler.post { }        → posted as message by you
  Choreographer VSYNC     → posted as message by display system
```

---

## ANR — When a Message Takes Too Long

```
ANR TIMEOUTS
┌────────────────────────────┐
│ Input dispatch:    5 sec   │
│ BroadcastReceiver: 10 sec  │
│ Service onCreate:  20 sec  │
└────────────────────────────┘
All = main thread blocked too long
```

**What causes ANR:** Long work on the main thread blocking `Looper.loop()` from processing the next message.

```kotlin
// CAUSES ANR:
override fun onCreate(savedInstanceState: Bundle?) {
    super.onCreate(savedInstanceState)
    val data = database.query("SELECT * FROM users")  // blocks for 6s → ANR!
}

// FIX:
override fun onCreate(savedInstanceState: Bundle?) {
    super.onCreate(savedInstanceState)
    lifecycleScope.launch {
        val data = withContext(Dispatchers.IO) { database.query("SELECT * FROM users") }
        updateUI(data)
    }
}
```

---

## Handler on a Background Thread

The main thread's Looper is set up by `ActivityThread.main()`. Background threads have no Looper by default.

```kotlin
// WRONG — no Looper on background thread:
Thread {
    val handler = Handler()  // RuntimeException: Can't create handler inside thread that has not called Looper.prepare()
}.start()

// CORRECT — call Looper.prepare() first:
Thread {
    Looper.prepare()              // create Looper + MessageQueue for THIS thread
    val handler = Handler(Looper.myLooper()!!)
    Looper.loop()                 // start processing messages
}.start()
```

---

## `delay()` on `Dispatchers.Main` — What Actually Happens

```kotlin
lifecycleScope.launch {
    delay(1000)      // doesn't spin-wait — suspends the coroutine
    updateUI()
}
```

Under the hood, `Dispatchers.Main` is implemented via `HandlerContext`:

```
delay(1000)
     │
     ▼
Coroutines runtime calls Handler.postDelayed(resumeRunnable, 1000)
     │
     ▼
MessageQueue stores resumeRunnable with timestamp + 1000ms
     │
     ▼
After 1000ms: Looper picks it up → dispatches → coroutine resumed on main thread
```

`delay()` on `Dispatchers.Main` **is** `Handler.postDelayed()`. Same mechanism, cleaner API.

---

## ## Traps

**Trap — `synchronized` on the main thread can cause ANR:**

```kotlin
// WRONG — if another thread holds the lock for > 5s, main thread is blocked → ANR:
synchronized(lock) {
    expensiveOperation()  // main thread waits here
}

// CORRECT — do expensive work on a background dispatcher:
lifecycleScope.launch(Dispatchers.IO) {
    val result = expensiveOperation()
    withContext(Dispatchers.Main) { updateUI(result) }
}
```

**Trap — `Handler(Looper.getMainLooper())` vs `Handler()`:**

```kotlin
// WRONG — Handler() with no args uses the current thread's Looper:
// If called from a background thread with no Looper → crash.

// CORRECT — explicitly specify the main Looper:
val handler = Handler(Looper.getMainLooper())
// Now safe to call from any thread — always posts to the main thread queue.
```

---

## Memory Trick

```
RELATIONSHIPS:
  Thread : Looper : MessageQueue : Handler = 1 : 1 : 1 : many
  Many Handlers → same queue → same Looper → same thread

ANR TIMEOUTS:
  Input dispatch:       5 seconds
  BroadcastReceiver:   10 seconds
  Service onCreate:    20 seconds

Background thread + Handler:
  Thread { Handler() }  → CRASH (no Looper)
  Thread { Looper.prepare(); Handler(); Looper.loop() }  → works

delay() on Dispatchers.Main == Handler.postDelayed() under the hood.
Dispatchers.Main is implemented via HandlerContext wrapping the main Looper.
```

---

## Self-Test

1. What is the relationship between a Thread, a Looper, a MessageQueue, and a Handler? What is the multiplicity of each?
2. You call `Handler()` (no-arg constructor) from a background thread. What happens and why?
3. What are the three ANR timeout values? What causes each?
4. Trace what happens when `delay(1000)` is called on `Dispatchers.Main` down to the `Handler` level.
5. How is a touch event delivered to an Activity? What is the mechanism between the hardware event and `onTouchEvent()`?

---

## Phase 16 — Summary

```
┌──────────────────────────────────────────────────────────────────────┐
│  1. Rotation: onPause → onSaveInstanceState → onStop → onDestroy    │
│     → new onCreate(bundle). Process death: NO callbacks.            │
│     Fragment: two lifecycles. Clear ViewBinding in onDestroyView.  │
│                                                                      │
│  2. Service runs on the MAIN THREAD. Must dispatch to IO yourself.  │
│     API 26+: background services killed in ~60s. Use foreground     │
│     service + startForeground() within 5s.                          │
│                                                                      │
│  3. Binder = 1-copy IPC via mmap. ~1MB limit shared across all     │
│     concurrent calls. Exceeding it → TransactionTooLargeException.  │
│     onSaveInstanceState Bundle crosses Binder — same limit applies. │
│                                                                      │
│  4. Zygote = pre-loaded template process. fork() = CoW = fast.     │
│     Application.onCreate() runs inside Looper.loop() as a message. │
│     Heavy work there delays every lifecycle callback.               │
│                                                                      │
│  5. Main thread = Looper.loop() (infinite). ANR = message > 5s.   │
│     delay() on Dispatchers.Main = Handler.postDelayed() underneath.│
│     Background thread needs Looper.prepare() before a Handler.     │
└──────────────────────────────────────────────────────────────────────┘
```

---

*← [Phase 15 — Networking](15_networking.md) | [Phase 17 — Performance and Memory →](17_performance_and_memory.md)*