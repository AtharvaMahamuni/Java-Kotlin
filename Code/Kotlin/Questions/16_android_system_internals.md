# Phase 16: Android System Internals

## Navigation
[← Master Index](master_chains.md)

## Questions in This File
- [Q16.1 — Activity and Fragment Lifecycle](#q161--activity-and-fragment-lifecycle)
- [Q16.2 — Background Work Evolution](#q162--background-work-evolution)
- [Q16.3 — Binder IPC](#q163--binder-ipc)
- [Q16.4 — Zygote and App Startup](#q164--zygote-and-app-startup)
- [Q16.5 — Handler, Looper, and MessageQueue](#q165--handler-looper-and-messagequeue)

---

## Q16.1 — Activity and Fragment Lifecycle

> **Builds on:** [Q13.3 — ViewModel survives rotation](13_android_architecture.md#q133--viewmodel-internals)
> **Connects to:** [Q16.2 — Background Work](16_android_system_internals.md#q162--background-work-evolution) · [Q17.1 — Memory Leaks](17_performance_and_memory.md#q171--memory-leaks--top-5-causes) · [Q10.4 — lifecycleScope](10_structured_concurrency.md#q104--lifecycle-scopes-and-process-death)
> **Reference:** [Android Docs — Activity lifecycle](https://developer.android.com/guide/components/activities/activity-lifecycle)

### The Concrete Picture

Starting state: Activity is fully running (onResume returned), user rotates device.

```
BEFORE rotation:
  Activity A (portrait)  ←  currently displayed, onResume returned

ROTATION sequence (Android P+):
  Activity A:  onPause()
               onSaveInstanceState(bundle)  ──► bundle stored by AMS via Binder
               onStop()
               onDestroy()                  ──► A is garbage-collected

  Activity A2: onCreate(savedInstanceState) ◄── same bundle restored from AMS
               onStart()
               onResume()                   ──► user sees landscape Activity

KEY DISTINCTION — process death vs rotation:
  Rotation:      onDestroy IS called, bundle IS passed to next onCreate
  Process death: onDestroy NOT called, OS kills process with no warning
```

The bundle travels through Binder IPC (subject to 1MB limit). ViewModel survives rotation because it is stored in ViewModelStore, not in the bundle.

### Exact Callback Order During Rotation

```
User rotates device:

Old Activity:
  onPause()
  onStop()
  onSaveInstanceState(bundle)  ← Called BEFORE onStop in Android P+!
  onDestroy()

New Activity (recreated):
  onCreate(savedInstanceState)  ← same bundle from onSaveInstanceState
  onStart()
  onResume()
```

**Android P (API 28) change:** Before Android P, `onSaveInstanceState` was called BEFORE `onStop` but AFTER `onPause`. From Android P+, it's guaranteed to be called BEFORE `onStop` (but can be before or after `onPause`). This gives more time to save state.

### When Is `onDestroy` NOT Called?

The OS does NOT call `onDestroy` when it kills the app process for memory. Process death is immediate — no callbacks.

```
Memory pressure scenario:
App in background → OS needs memory → kills process (no warning, no onDestroy!)
User returns to app → system restores Activity state from saved instance state
(if available) → Activity appears to resume normally
```

This is why critical state must be saved in `onSaveInstanceState`, not `onDestroy`. You may never reach `onDestroy`.

### Two Fragment Lifecycles — The ViewBinding Memory Leak

A Fragment has TWO lifecycles:
1. **Fragment lifecycle** (`onAttach` → `onDetach`): the Fragment object's lifetime
2. **View lifecycle** (`onCreateView` → `onDestroyView`): the Fragment's view's lifetime

The view is destroyed in `onDestroyView` but the Fragment object CONTINUES to exist (it may be added to the back stack). This creates a memory leak with ViewBinding:

```kotlin
// WRONG — binding held beyond view lifetime:
class MyFragment : Fragment() {
    private var binding: MyFragmentBinding? = null  // nullable

    override fun onCreateView(...): View {
        binding = MyFragmentBinding.inflate(inflater, container, false)
        return binding!!.root
    }

    override fun onDestroyView() {
        super.onDestroyView()
        // binding = null  ← MISSING! Without this, binding holds old views!
    }
}

// CORRECT — clear binding in onDestroyView:
override fun onDestroyView() {
    super.onDestroyView()
    binding = null  // ← releases the view reference!
}
```

**Why:** When the Fragment goes to the back stack, its view is destroyed (`onDestroyView`). If `binding` still holds a reference to the old views, those views can't be garbage collected — memory leak.

**Better pattern using Kotlin property delegation:**
```kotlin
class MyFragment : Fragment() {
    private val binding by viewBinding(MyFragmentBinding::bind)
    // viewBinding delegate handles null/clear automatically
}
```

### `repeatOnLifecycle(STARTED)` at the Lifecycle Level

When a Fragment is on the back stack:
- `onStop()` is called (fragment stopped)
- `repeatOnLifecycle(STARTED)` CANCELS the collecting block
- Memory and CPU freed during backstacking

When user presses back to the Fragment:
- `onStart()` is called
- `repeatOnLifecycle(STARTED)` RESTARTS the collecting block
- UI gets fresh data

### Memory Trick

```
ROTATION:  OLD activity → onPause → onSaveInstanceState → onStop → onDestroy
           NEW activity → onCreate(bundle) → onStart → onResume

DEATH:     process killed → NO callbacks → bundle restored from Binder store
           ViewModel GONE (heap gone), SavedStateHandle survives (Binder store)

FRAGMENT TWO LIFECYCLES:
  Fragment object:  onAttach ──────────────────────────── onDetach
  Fragment view:             onCreateView ── onDestroyView
                             (clear binding = null here!)

Android P+ guarantee: onSaveInstanceState BEFORE onStop (not before onPause)
```

---

## Q16.2 — Background Work Evolution

> **Builds on:** [Q16.1 — Activity Lifecycle](16_android_system_internals.md#q161--activity-and-fragment-lifecycle) · [Q10.4 — Lifecycle Scopes](10_structured_concurrency.md#q104--lifecycle-scopes-and-process-death)
> **Connects to:** [Q14.2 — WorkManager](14_jetpack_components.md#q142--workmanager)

### The Concrete Picture

Starting state: You have a long-running upload task that must survive the user pressing Home.

```
WRONG mental model:
  Service created ──► runs on background thread automatically

CORRECT picture:
  Service.onStartCommand() ──► MAIN THREAD
                                │
                                ├── network call here ──► NetworkOnMainThreadException
                                └── heavy loop here   ──► ANR after 5s

CORRECT approach:
  Service.onStartCommand() ──► MAIN THREAD
                                │
                                └── CoroutineScope(Dispatchers.IO).launch { ... }
                                         │
                                         └──► background thread (safe)

Android 8+ additional constraint:
  App in background ──► startService() ──► IllegalStateException (BLOCKED)
  Fix: startForegroundService() + call startForeground() within 5s ──► shows notification
```

The word "background" in "background Service" = running while Activity not visible, NOT a background thread.

### Does a `Service` Run on a Background Thread?

**NO.** A Service runs on the **main thread** by default. This is one of the most common wrong answers in Android interviews.

```kotlin
class MyService : Service() {
    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        // THIS IS ON THE MAIN THREAD!
        // Doing network call here → NetworkOnMainThreadException
        // Doing heavy computation → ANR (Application Not Responding)

        // Must create a thread or use coroutines yourself:
        CoroutineScope(Dispatchers.IO).launch {
            doBackgroundWork()
        }
        return START_STICKY
    }
}
```

The word "background" in "background Service" refers to running when the Activity is not visible — NOT running on a background thread.

### Android 8 (Oreo) Background Execution Limits

Before Android 8: Services could run indefinitely in the background.

After Android 8:
- Apps in the background cannot start services (`IllegalStateException: Not allowed to start service Intent`)
- Background services can be killed within ~1 minute
- Exception: Foreground services (have a persistent notification) can run longer

```kotlin
// Starting a service from background (pre-Oreo):
startService(intent)  // OK on API < 26

// Starting a service (API 26+):
if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
    startForegroundService(intent)  // Must call startForeground() within 5 seconds!
} else {
    startService(intent)
}
```

### Android 14 Foreground Service Changes

Android 14 added **foreground service types** — you must declare what kind of work the foreground service is doing:

```xml
<!-- AndroidManifest.xml -->
<service
    android:name=".UploadService"
    android:foregroundServiceType="dataSync" />
<!-- Types: camera, connectedDevice, dataSync, location, mediaPlayback,
            mediaProjection, microphone, phoneCall, remoteMessaging,
            shortService, specialUse, systemExempted -->
```

```kotlin
// Android 14+ — must specify type when calling startForeground:
startForeground(
    NOTIFICATION_ID,
    notification,
    ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC  // must match manifest!
)
// If type doesn't match manifest → MissingForegroundServiceTypeException!
```

### Background Work Evolution Chain

```
AsyncTask (deprecated):
- Ran on a thread pool for background + post back to main thread
- Problems: leaked Activity context, sequential execution by default,
  killed with process, no built-in error handling
- Deprecated in API 30

IntentService (deprecated):
- Background thread handling Intents via a work queue
- Auto-stopped when work was done
- Problems: Oreo background restrictions killed it, single thread, no coroutines
- Deprecated in API 30

WorkManager (current):
- Persists to Room DB → survives process death, reboot
- Respects Doze mode (defers, doesn't cancel)
- Thread-pool based with coroutines support
- Constraint-aware (network, charging, etc.)
```

### Memory Trick

```
SERVICE = runs on MAIN thread (background = invisible, not background thread)

EVOLUTION chain (all deprecated → WorkManager):
  AsyncTask (API 30-)  →  leaked Activity, sequential pool
  IntentService (API 30-)  →  killed by Oreo limits, single thread
  WorkManager (current)  →  Room-persisted, Doze-aware, coroutines, constraints

OREO RULE: background app + startService() = IllegalStateException
FIX: startForegroundService() → must call startForeground() within 5s

ANDROID 14: foregroundServiceType in manifest MUST match startForeground() type
```

---

## Q16.3 — Binder IPC

> **Builds on:** [Q16.4 — Zygote and App Startup](16_android_system_internals.md#q164--zygote-and-app-startup)
> **Connects to:** [Q13.3 — SavedStateHandle uses Binder](13_android_architecture.md#q133--viewmodel-internals) · [Q16.5 — Handler/Looper](16_android_system_internals.md#q165--handler-looper-and-messagequeue)
> **Reference:** [Android Docs — Bound services overview](https://developer.android.com/guide/components/bound-services)

### The Concrete Picture

Starting state: Your Activity calls `getSystemService(ACTIVITY_SERVICE)`. This crosses a process boundary.

```
Your app process (PID 12345)          system_server process (PID 600)
  ┌──────────────────────────┐          ┌─────────────────────────────┐
  │  ActivityManager.getXxx()│          │  ActivityManagerService     │
  │  (Java wrapper — proxy)  │          │  (real implementation)      │
  │          │               │          │          ▲                  │
  │          ▼               │          │          │                  │
  │  BinderProxy             │          │  Binder Stub (onTransact)   │
  └──────────┬───────────────┘          └──────────┬──────────────────┘
             │                                      │
             └──────────────► /dev/binder ──────────┘
                              (kernel driver)
                              ONE copy via mmap

Traditional IPC: Process A → kernel buffer → kernel buffer → Process B  (2 copies)
Binder IPC:      Process A ──────────────────────────────────► Process B  (1 copy via mmap)

1MB LIMIT: all concurrent Binder transactions for a process share ~1MB buffer
  Small primitives (IDs, ints) → safe
  Large lists, Bitmaps        → TransactionTooLargeException
```

### What Is Binder IPC?

**IPC = Inter-Process Communication.** Android apps run in separate processes. When you call `getSystemService()`, access the `ActivityManager`, or use AIDL — you're communicating across process boundaries.

**Binder** is Android's IPC mechanism. Unlike traditional Unix IPC (pipes, shared memory) which copies data twice (sender → kernel → receiver), Binder copies data **only once** (via memory mapping):

```
Traditional IPC:
Process A → [copy to kernel buffer] → [copy from kernel buffer] → Process B
2 copies!

Binder IPC:
Process A → [mmap: single copy to shared memory region] → Process B
1 copy!
```

### The Binder Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                  Android Binder Architecture                     │
│                                                                  │
│  Client Process                    Server Process               │
│  ┌──────────────────┐              ┌──────────────────────────┐  │
│  │  Your Code       │              │  System Service           │  │
│  │  calls method    │              │  (ActivityManagerService, │  │
│  │        │         │              │   WindowManagerService)   │  │
│  │        ▼         │              │         ▲                 │  │
│  │  BinderProxy     │              │    Binder (Stub)          │  │
│  │  (Proxy object)  │              │    handles calls          │  │
│  └────────┬─────────┘              └──────────┬────────────────┘  │
│           │                                    │                  │
│           │       Kernel (Binder Driver)        │                  │
│           └──────────────┐  ┌──────────────────┘                  │
│                          ▼  ▼                                     │
│              /dev/binder (kernel driver)                          │
│              Manages transactions, one copy of data               │
└──────────────────────────────────────────────────────────────────┘
```

### The 1MB Transaction Size Limit

Binder uses a **1MB transaction buffer per process** (actually ~1MB shared across all concurrent Binder transactions). Exceeding it throws:

```
android.os.TransactionTooLargeException: data parcel size N bytes
```

This affects:
- `onSaveInstanceState` (Binder IPC to persist Bundle)
- [`SavedStateHandle`](13_android_architecture.md#q133--viewmodel-internals)
- Intents with large extras
- AIDL method calls with large arguments

**Practical limits:**
```kotlin
// Safe: small primitives, IDs
savedState["userId"] = "user_123"           // ~10 bytes ✓
savedState["selectedTab"] = 2               // 4 bytes ✓

// Dangerous: large objects
savedState["userList"] = listOf<User>(...)  // 500+ objects → CRASH!
savedState["bitmap"] = bitmap               // bytes → DEFINITELY CRASH!

// Fix: store in Room/DataStore, save only the identifier
savedState["selectedUserId"] = "user_123"   // fetch from DB on restore
```

### Memory Trick

```
BINDER = Android's IPC highway
  Traditional IPC: 2 copies (process → kernel → process)
  Binder:          1 copy (mmap shared region)

1MB LIMIT — what fits:
  SAFE:   primitives, IDs, small strings ("userId", tab index)
  DANGER: List<User> > ~500 items, any Bitmap, serialized objects > 1MB

REMEMBER: every getSystemService() call crosses Binder
          onSaveInstanceState bundle crosses Binder (subject to same 1MB!)
          SavedStateHandle also crosses Binder — same limit applies

Error: TransactionTooLargeException: data parcel size N bytes
Fix:   store large data in Room/DataStore, save only the key
```

---

## Q16.4 — Zygote and App Startup

> **Builds on:** [Q0.3 — Class Loading](00_jvm_mental_model.md#q03--class-loading-and-the-static--block)
> **Connects to:** [Q16.3 — Binder IPC](16_android_system_internals.md#q163--binder-ipc) · [Q17.3 — The 16ms Budget](17_performance_and_memory.md#q173--the-16ms-budget)

### The Concrete Picture

Starting state: Device is running, your app is NOT launched. User taps the launcher icon.

```
Launcher (process A)                   system_server                  Your app (new process)
      │                                      │                               │
      ├──► Intent via Binder IPC ──────────► │                               │
      │                               ActivityManagerService                 │
      │                                      │                               │
      │                               checks: process alive?                 │
      │                               NO ──► asks Zygote to fork ──────────► │
      │                                                                 Zygote.fork()
      │                                                                 (copy-on-write)
      │                                                                 new PID assigned
      │                                                                       │
      │                                                                 ActivityThread.main()
      │                                                                       │
      │                                                                 Looper.prepareMainLooper()
      │                                                                       │
      │                                                                 Application.onCreate()
      │                                                                       │
      │                                                                 Activity.onCreate()
      │                                                                       │
      │                                                                 first frame drawn
      │                                                                       │
      └──────────────────────────────────────────────────────────────── user sees app

Zygote pre-loads: java.lang.*, android.*, ART runtime, common resources
Fork result: child shares Zygote pages via CoW → no redundant class loading
```

### The Path from App Icon Tap to First Activity Frame

```
1. User taps app icon in Launcher
        │
        ▼
2. Launcher sends an Intent to ActivityManagerService (via Binder IPC)
        │
        ▼
3. ActivityManagerService checks if app process exists
   └── If YES → sends intent to existing process
   └── If NO → requests Zygote to fork a new process
        │
        ▼
4. Zygote.fork() — creates a new process as a copy of Zygote
   (copy-on-write — fast because most class data shared via mmap)
        │
        ▼
5. New process runs ActivityThread.main()
        │
        ▼
6. Looper.prepareMainLooper() — creates main thread event loop
        │
        ▼
7. Application.onCreate() called
        │
        ▼
8. Activity.onCreate() called
        │
        ▼
9. First frame drawn → user sees the app
```

### What Is Zygote Forking?

**Zygote** is a special process that Android starts at boot time. It pre-loads:
- Common Java/Android classes (String, View, Activity, etc.)
- Runtime libraries (art, bionic libc, etc.)
- Resources (common drawables, styles)

When your app starts, the OS **forks** Zygote — creates a copy of it. Since fork uses **copy-on-write** (CoW), the child process shares Zygote's memory pages until it needs to modify them. This means:
- No need to re-load all those pre-loaded classes
- App startup is fast — it "inherits" all the common classes

```
Zygote process (always running):
  Pre-loaded: java.lang.*, android.*, common classes
              art runtime, bionic
  Memory: ~50MB shared between ALL app processes

Fork:
  New process gets a copy (CoW) of all Zygote's pages
  Actual copy happens only when the page is written
  App-specific code loaded on top
```

### `ActivityThread.main()` — Before `Application.onCreate()`

`ActivityThread.main()` is the entry point of your app's main thread (invoked by the OS after forking):

```java
// Simplified Android source:
public static void main(String[] args) {
    // 1. Set up uncaught exception handler
    // 2. Prepare main thread looper:
    Looper.prepareMainLooper();

    // 3. Create the ActivityThread and attach it to AMS:
    ActivityThread thread = new ActivityThread();
    thread.attach(false, startSeq);

    // 4. Start the main message loop (infinite loop!):
    Looper.loop();  // never returns until the process dies!
}
```

`Application.onCreate()` is dispatched as a **message** to the main looper — it happens inside `Looper.loop()`, not before it.

### `Looper.prepareMainLooper()` — The Infinite Loop

The Android main thread's core is an **infinite message loop**:

```kotlin
// Conceptual equivalent:
fun loop() {
    while (true) {
        val message = messageQueue.next()  // blocks until a message arrives
        message.target.dispatchMessage(message)  // process it
    }
}
```

Every UI update, every Activity lifecycle callback, every touch event — they are all **messages** posted to this queue and processed by this loop. The loop itself never returns until the process dies.

An **ANR** (Application Not Responding) occurs when a message in this queue takes too long to process:
- Input event not handled in 5 seconds
- Broadcast receiver not completing in 10 seconds

### Memory Trick

```
STARTUP ORDER (memorize the 9-step chain):
  tap icon → Launcher Binder → AMS checks process → Zygote.fork()
  → ActivityThread.main() → Looper.prepareMainLooper()
  → Application.onCreate() → Activity.onCreate() → first frame

ZYGOTE = template process (always running at boot)
  Pre-loaded: ~50MB of shared classes (CoW = not copied until written)
  fork() is fast because child starts with Zygote's pages already mapped

Application.onCreate() runs INSIDE Looper.loop() (as a message)
  → heavy work in Application.onCreate() delays EVERY future message
  → keep it minimal (lazy-init SDKs, avoid synchronous I/O)
```

---

## Q16.5 — Handler, Looper, and MessageQueue

> **Builds on:** [Q16.4 — Zygote (main thread setup)](16_android_system_internals.md#q164--zygote-and-app-startup) · [Q9.2 — Dispatchers.Main uses Looper](09_coroutines_execution_mechanics.md#q92--coroutine-context-and-dispatchers)
> **Connects to:** [Q9.2 — Dispatchers.Main.immediate](09_coroutines_execution_mechanics.md#q92--coroutine-context-and-dispatchers)
> **Reference:** [Android Docs — Processes and threads overview](https://developer.android.com/guide/components/processes-and-threads)

### The Concrete Picture

Starting state: Your app is running. Multiple things post to the UI: touch events, animations, your own `postDelayed`.

```
THREAD (one):
  main thread ──────────────────────────────────────────────────────────────►
                          │ (runs Looper.loop() — infinite)
                          │
LOOPER (one per thread):  │
  Looper.loop()  picks one message at a time from queue ──► dispatches to Handler

MESSAGEQUEUE (one per Looper):
  ┌──────────────────────────────────────────────────────┐
  │ msg1 (touch event, t=0ms) │ msg2 (draw, t=16ms) │ ..│
  └──────────────────────────────────────────────────────┘
        ▲                ▲               ▲
  Handler (touch)  Handler (Choreographer)  Handler (your postDelayed)

PROBLEM: one slow message blocks everything else
  database.query() on main thread → query takes 6s
  → touch events piling up in queue unprocessed → ANR after 5s
```

### The Relationship: Thread → Looper → MessageQueue → Handlers

```
One Thread → One Looper → One MessageQueue → Many Handlers

Main Thread:
┌─────────────────────────────────────────────────────┐
│  Thread: main                                       │
│  └── Looper: main looper                           │
│       └── MessageQueue: shared queue               │
│            ├── Handler 1 (View touch events)        │
│            ├── Handler 2 (Activity callbacks)       │
│            └── Handler 3 (your postDelayed)         │
└─────────────────────────────────────────────────────┘
All 3 handlers post to the SAME queue,
processed by the SAME looper on the SAME thread.
```

A `Handler` is just a "ticket booth" — it lets you post messages TO a specific Looper's queue. The messages are processed by the thread that runs that Looper.

### What Is an ANR?

**ANR = Application Not Responding.** Android displays the "App isn't responding" dialog when:

1. **Input dispatch timeout:** An input event (touch, key) isn't handled within **5 seconds**
2. **Broadcast receiver timeout:** A broadcast receiver doesn't finish its `onReceive()` within **10 seconds** (for most broadcasts)
3. **Service timeout:** A Service doesn't respond to `onCreate()` or `onStartCommand()` within **20 seconds**

**What causes ANR:** Long-running work on the main thread — database queries, network calls, long computations, heavy object creation.

```kotlin
// CAUSES ANR:
override fun onCreate(savedInstanceState: Bundle?) {
    super.onCreate(savedInstanceState)
    val data = database.query("SELECT * FROM users")  // blocks main thread!
    // If this takes > 5 seconds → ANR!
}

// FIX: move to background thread:
override fun onCreate(savedInstanceState: Bundle?) {
    super.onCreate(savedInstanceState)
    lifecycleScope.launch {
        val data = withContext(Dispatchers.IO) {
            database.query("SELECT * FROM users")  // background thread
        }
        updateUI(data)  // back on main thread
    }
}
```

### Handler Without `Looper.prepare()` on a Background Thread

```kotlin
Thread {
    val handler = Handler()  // CRASH: Can't create handler inside thread that has not called Looper.prepare()
}.start()

// Fix: call Looper.prepare() first:
Thread {
    Looper.prepare()       // creates a Looper (and MessageQueue) for this thread
    val handler = Handler()  // now works — uses the Looper just created
    Looper.loop()            // start processing messages on this thread
}.start()
```

The main thread has Looper pre-prepared by `ActivityThread.main()`. Background threads don't — you must do it manually if you want a Handler on a background thread.

### `Handler.postDelayed()` vs `delay()` on `Dispatchers.Main`

```kotlin
// Handler-based delay (older approach):
handler.postDelayed({
    updateUI()
}, 1000)  // posts a message with 1s delay to MessageQueue

// Coroutine delay (modern approach):
lifecycleScope.launch {
    delay(1000)   // suspends the coroutine for 1s
    updateUI()
}
```

**Under the hood, `delay()` on [`Dispatchers.Main`](09_coroutines_execution_mechanics.md#q92--coroutine-context-and-dispatchers) uses `Handler.postDelayed()`!** The `Dispatchers.Main` implementation (via `HandlerContext`) schedules coroutine resumptions by posting delayed messages to the main Looper's MessageQueue.

Both are equivalent in behavior. Coroutines just make it cleaner and composable with other suspend functions.

### Memory Trick

```
THREAD:LOOPER:QUEUE:HANDLER = 1:1:1:many
  One thread has exactly one Looper (created by Looper.prepare())
  One Looper has exactly one MessageQueue
  Many Handlers can all post to the same queue

ANR TIMEOUTS (memorize the 3):
  Input dispatch: 5 seconds
  BroadcastReceiver.onReceive(): 10 seconds
  Service.onCreate/onStartCommand(): 20 seconds

Background thread + Handler:
  Thread { Handler() }  ──► CRASH (no Looper)
  Thread { Looper.prepare(); Handler(); Looper.loop() }  ──► works

delay() on Dispatchers.Main == Handler.postDelayed() under the hood
```

---

## Master Summary: Android System Internals in 5 Points

```
┌──────────────────────────────────────────────────────────────────────┐
│  1. Service runs on the MAIN THREAD — not a background thread.      │
│     You must create threads/coroutines yourself inside a Service.   │
│                                                                       │
│  2. onDestroy is NOT called on process death. Save critical state   │
│     in onSaveInstanceState. Binder limit: ~1MB for Bundle data.     │
│                                                                       │
│  3. Zygote forks give fast startup via copy-on-write. Pre-loaded    │
│     classes are shared across all app processes.                    │
│                                                                       │
│  4. The Android main thread is an infinite message loop.             │
│     ANR = message takes > 5s (input) or > 10s (broadcast).         │
│                                                                       │
│  5. delay() on Dispatchers.Main uses Handler.postDelayed() under    │
│     the hood. Fragment has TWO lifecycles — clear ViewBinding in    │
│     onDestroyView to prevent view leaks.                            │
└──────────────────────────────────────────────────────────────────────┘
```

---

*← [Phase 15 — Networking](15_networking.md) | [Phase 17 — Performance & Memory →](17_performance_and_memory.md)*
