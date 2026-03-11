# Section 8 — Android Architecture & System Internals (Q167–Q185)

---

## Architecture Components (Q167–Q172)

### Q167. What is MVVM architecture?
**Definition:** Model-View-ViewModel — an architecture pattern separating UI (View) from business logic (ViewModel) from data (Model).
**Core Idea:** View observes ViewModel state. ViewModel exposes state, handles logic. Model = repositories + data sources.

```
View (Activity/Fragment)
  ↕ observes state
ViewModel (state + logic)
  ↕ requests data
Model (Repository → DB, Network)
```

**How it Works:** ViewModel exposes `LiveData`/`StateFlow`. View observes and renders. User actions call ViewModel methods.
**Example:** `LoginViewModel` has `uiState: StateFlow<LoginUiState>`. `LoginFragment` collects the flow and renders.
**Interview Insight:** MVVM is the Google-recommended pattern for Android. ViewModel survives rotation; separating it from Activity prevents logic in lifecycle callbacks.

---

### Q168. What is ViewModel?
**Definition:** A Jetpack class that holds UI-related data and survives configuration changes (like rotation).
**Core Idea:** Survives rotation. Dies when Activity is permanently finished. Scoped to `ViewModelStore`.
**How it Works:** `ViewModelProvider` returns the same instance on configuration change. `onCleared()` called when permanently destroyed.
**Example:** `val vm: UserViewModel by viewModels()` — same instance survives rotation.
**Interview Insight:** ViewModel must NOT hold references to Context, Activity, or Views — these are configuration-sensitive and will be recreated. ViewModel outlives them, causing leaks.

---

### Q169. What problem does ViewModel solve?
**Definition:** Survives configuration changes (rotation, locale change) without re-fetching data.
**Core Idea:** Before ViewModel: rotation = Activity destroyed = network call lost = UI flashes. ViewModel holds the data across rotation.
**How it Works:** The OS recreates the Activity but reuses the ViewModel from the `ViewModelStore` attached to the Activity. Data is still there.
**Example:** User is on a list screen, rotates phone. Without ViewModel: list re-fetches. With ViewModel: list is still in memory.
**Interview Insight:** ViewModel doesn't survive process death — only configuration changes. For process death, use `SavedStateHandle` + persistent storage (Room/DataStore).

---

### Q170. What is LiveData?
**Definition:** An observable data holder from Jetpack that is lifecycle-aware — only delivers updates to active (started/resumed) observers.
**Core Idea:** Automatically stops delivering updates to stopped/destroyed observers. No memory leaks from dead observers.
**How it Works:** Observers register with a `LifecycleOwner`. If the owner is stopped/destroyed, LiveData stops delivering. Active again → latest value delivered.
**Example:** `viewModel.users.observe(viewLifecycleOwner) { users -> adapter.submitList(users) }`
**Interview Insight:** LiveData's lifecycle awareness prevents crashes from updating destroyed views. Disadvantage: main-thread only, limited operators. Modern alternative: `StateFlow` + `repeatOnLifecycle`.

---

### Q171. What is Flow?
**Definition:** A Kotlin coroutine-based asynchronous data stream that emits multiple values sequentially.
**Core Idea:** Coroutines' answer to RxJava Observable / LiveData. Cold by default. Rich operators.
**How it Works:** A `Flow` is a suspending lambda that emits values. Collected in a coroutine. `StateFlow` = hot, always has a value (LiveData equivalent).
**Example:** `val usersFlow: Flow<List<User>> = dao.getUsers()` → collected with `lifecycleScope.launch { flow.collect { } }`.
**Interview Insight:** `StateFlow` replaces `LiveData` in modern Android. Use `repeatOnLifecycle(STARTED)` to collect safely — stops collecting when UI is in background, preventing wasted work.

---

### Q172. What is LifecycleOwner?
**Definition:** An interface implemented by Activity and Fragment that exposes a `Lifecycle` object, allowing observers to react to lifecycle state changes.
**Core Idea:** Lifecycle-aware components (LiveData, Coroutines, CameraX) use LifecycleOwner to auto-start/stop based on lifecycle.
**How it Works:** `LifecycleOwner.lifecycle` returns a `Lifecycle` object. Observers can register via `lifecycle.addObserver(...)`.
**Example:** `viewLifecycleOwner` in Fragment = the Fragment's VIEW lifecycle (preferred over `this` for LiveData observation).
**Interview Insight:** Always use `viewLifecycleOwner` (not `this`) in Fragments for LiveData observation. The Fragment instance can outlive its view — using `this` causes a second observer after recreation.

---

## System Internals (Q173–Q177)

### Q173. What is Binder?
**Definition:** Android's inter-process communication (IPC) mechanism — a kernel-level driver enabling efficient cross-process method calls.
**Core Idea:** All Android IPC goes through Binder. Calling `getSystemService()` crosses a process boundary via Binder.
**How it Works:** Client calls Proxy → Binder kernel driver marshals data → routes to Stub in server process → method executes → result returns the same way.
**Example:** Your app calls `locationManager.getLastKnownLocation()` → Binder IPC → runs in `system_server` → returns location.
**Interview Insight:** Binder transactions have a ~1MB buffer limit. Large data (Bitmap, large lists) should NOT go via Binder — use shared memory (`ashmem`). ANR in a service = Binder thread pool is full.

---

### Q174. What is Android IPC?
**Definition:** Inter-Process Communication — mechanisms for processes to communicate in Android (Binder, Intent, ContentProvider, AIDL, Messenger).
**Core Idea:** Android apps are isolated processes. IPC is required for any cross-app or app-to-system communication.
**How it Works:** All IPC ultimately uses Binder driver. Higher-level abstractions: Intents, ContentProviders, AIDL, Messenger.

| Mechanism | Use case |
|---|---|
| Intent | Start components, broadcast events |
| Binder | Direct method calls (system APIs) |
| ContentProvider | Shared data access |
| AIDL | Complex cross-process interfaces |

**Interview Insight:** IPC has cost — crossing process boundaries involves context switches and data marshaling. Avoid high-frequency IPC calls. Batch requests where possible.

---

### Q175. What is Zygote?
**Definition:** The Android process from which all app processes are forked. Pre-loads the Android runtime and framework classes.
**Core Idea:** Fork-on-demand model — instead of cold-starting every app, Zygote has the JVM and framework already warm.
**How it Works:** Zygote starts at boot, loads the entire Android framework into memory, then listens for fork requests. When you launch an app, Zygote forks itself — the new process inherits the pre-loaded state.
**Example:** App launch is fast because the fork inherits pre-loaded classes (Activity, Fragment, View hierarchy).
**Interview Insight:** This is why Android app launches are relatively fast — no JVM cold start. The first app launch after boot is slower (Zygote needs to pre-load). Cold start = first ever launch or after force-stop.

---

### Q176. What is ActivityManager?
**Definition:** The system service managing the lifecycle of Activities, Tasks, and the back stack. Also manages process priority.
**Core Idea:** ActivityManager is the "traffic controller" for all Activity navigation and process management.
**How it Works:** Your calls to `startActivity()` go to `ActivityManagerService` in `system_server` via Binder. AMS validates intent, manages back stack, decides whether to create a new process.
**Example:** `startActivity(intent)` → Binder IPC → ActivityManagerService → finds/creates target process → tells Zygote to fork if needed → starts Activity.
**Interview Insight:** ActivityManager decides process priority and kills low-priority processes (via LMK). When debugging "why was my Service killed" — it's ActivityManager enforcing memory policies.

---

### Q177. What is PackageManager?
**Definition:** The system service that manages installed apps — knows what components exist, what permissions they have, and resolves implicit intents.
**Core Idea:** The app registry. Reads every app's `AndroidManifest.xml` at install time and stores the information.
**How it Works:** When you call `startActivity(implicitIntent)`, PackageManager queries all registered intent filters to find who can handle it.
**Example:** `packageManager.resolveActivity(intent, 0)` — check if anyone can handle the intent before calling `startActivity`. Prevents `ActivityNotFoundException`.
**Interview Insight:** PackageManager is why changes to `AndroidManifest.xml` require reinstalling the app — the manifest must be re-parsed by PackageManager.

---

## Rendering System (Q178–Q181)

### Q178. What is the Android UI thread?
**Definition:** The single thread responsible for ALL UI rendering, input event processing, and lifecycle callbacks.
**Core Idea:** Serial. Never block it. Has a Looper running the message queue.
**How it Works:** Framework posts messages (draw calls, touch events, lifecycle callbacks) to the main thread's message queue. Choreographer coordinates frame rendering.
**Example:** `RecyclerView.onDraw()`, `onClick()`, `onResume()` — all run on the UI thread.
**Interview Insight:** The UI thread runs at ~60fps (16ms per frame). ANY operation taking >16ms causes a dropped frame (jank). >5 seconds of blocking = ANR. Profile with Systrace/Perfetto.

---

### Q179. What is Choreographer?
**Definition:** Android's class that coordinates frame rendering with the display's vsync signal.
**Core Idea:** "Draw when the screen is ready." Choreographer receives vsync signals from the display hardware (~60Hz) and triggers the draw traversal.
**How it Works:** Vsync arrives → Choreographer fires → View hierarchy traversal (measure → layout → draw) → GPU composition → frame displayed.
**Example:** When you call `View.invalidate()`, the view doesn't redraw immediately — it posts a callback to the Choreographer, which renders it on the next vsync.
**Interview Insight:** `Choreographer.FrameCallback` is used by performance tools to measure frame timing. If your `doFrame()` callback takes >16ms, you dropped a frame.

---

### Q180. What is a frame in Android rendering?
**Definition:** A single rendered image displayed on screen. At 60fps, each frame must be produced in ≤16ms.
**Core Idea:** Measure → Layout → Draw → GPU composite = one frame. If any step exceeds the vsync window, the frame is dropped (jank).
**How it Works:** Choreographer receives vsync → triggers `performTraversals()` → `measure()` → `layout()` → `draw()` → uploaded to GPU → displayed on screen.
**Example:** At 60fps: 1000ms / 60 frames = 16.6ms per frame. At 120fps: 8.3ms per frame.
**Interview Insight:** `invalidate()` = redraw needed (draw phase only). `requestLayout()` = measure + layout + draw. `requestLayout()` is more expensive — only call when size/position changes.

---

### Q181. What causes UI jank?
**Definition:** Jank = dropped frames, causing choppy/stuttering animation. Caused by operations exceeding 16ms on the UI thread.
**Core Idea:** The UI thread is blocked > 16ms → Choreographer misses the vsync → frame dropped → visible stutter.

**Common causes:**

| Cause | Fix |
|---|---|
| Heavy `onDraw()` / creating objects in draw | Move to `onSizeChanged`, use `drawBitmap` |
| Deep view hierarchy | Flatten with ConstraintLayout |
| RecyclerView `onBindViewHolder` doing I/O | Move to ViewModel |
| Synchronous DB/network on main thread | Use Coroutines/RxJava |
| Too many `requestLayout()` | Minimize layout invalidations |

**Interview Insight:** Use Android Studio's GPU Rendering Profiler or Systrace to identify jank. `RecyclerView.RecycledViewPool` and `DiffUtil` are key tools for smooth lists.

---

## Performance (Q182–Q185)

### Q182. What is a memory leak in Android?
**Definition:** An object that the app no longer needs but can't be garbage collected because something is still holding a reference to it.
**Core Idea:** Long-lived object holds reference to short-lived object (Activity, Fragment, View) → GC can't collect → memory grows → OOM crash.
**How it Works:** The GC traces reachability from GC roots. If a static field holds an Activity → Activity is reachable → never collected.

**Common Android memory leaks:**

| Leak | Cause | Fix |
|---|---|---|
| Activity leak | Static reference, inner class | WeakReference, don't use static |
| View leak | View captured in coroutine/lambda | Clear view binding in `onDestroyView` |
| Observer leak | Not removing LiveData observer | Use lifecycle-aware observe |
| Cursor leak | Not closing Cursor | Use `cursor.use { }` |

**Interview Insight:** Use LeakCanary in debug builds — it automatically detects and reports leaks. Profile with Android Studio Memory Profiler to find retained objects.

---

### Q183. What causes ANR?
**Definition:** Application Not Responding — the system shows an ANR dialog when the main thread is blocked.
**Core Idea:** The main thread's Looper can't process the next message because it's stuck executing your code.

**ANR triggers:**

| Scenario | Timeout |
|---|---|
| Activity input (touch, key) | 5 seconds |
| Broadcast receiver `onReceive` | 10 seconds |
| Service `onStartCommand` / `onBind` | 20 seconds |
| Content provider query | 10 seconds |

**Common causes:** Synchronous network/DB on main thread, deadlocks, long-running loops, excessive `SharedPreferences.commit()`.
**Interview Insight:** Fix: move EVERYTHING non-UI off the main thread. Use `StrictMode` in debug to detect disk/network on main thread. Check ANR traces in `/data/anr/traces.txt`.

---

### Q184. What is StrictMode?
**Definition:** A developer tool that detects potentially harmful operations (disk/network I/O on main thread) and alerts you (log, crash, or dialog).
**Core Idea:** Catches bad practices at development time so they don't ship to users.
**How it Works:** Set in `Application.onCreate()`. Has `ThreadPolicy` (main thread violations) and `VmPolicy` (memory leaks, untagged sockets).
**Example:**
```kotlin
StrictMode.setThreadPolicy(
    StrictMode.ThreadPolicy.Builder()
        .detectDiskReads()
        .detectNetwork()
        .penaltyLog()  // or .penaltyDeath() in debug
        .build()
)
```
**Interview Insight:** Enable StrictMode in debug builds only. `penaltyDeath()` crashes on violation — very useful to catch issues early. Never enable in release builds.

---

### Q185. What is the Android profiler?
**Definition:** Android Studio's built-in suite of profilers for analyzing CPU, memory, network, and energy usage of a running app.
**Core Idea:** Visual performance debugging tool. Identify bottlenecks, leaks, and heavy operations.
**How it Works:** Attach to a running process in Android Studio. Real-time graphs. Can record CPU traces (Method tracing, Sampled), take heap snapshots.

| Profiler | What it shows |
|---|---|
| CPU | Method traces, thread activity, jank frames |
| Memory | Heap allocations, GC events, leaked objects |
| Network | Request/response timing, payload sizes |
| Energy | Battery drain by component |

**Interview Insight:** For memory leaks: take heap snapshot → filter by Activity/Fragment → if instances > 1 when only 1 should exist = leak. For ANR: CPU profiler shows the main thread stuck on a blocking call.

---

```
╔══════════════════════════════════════════════════╗
║        Android Vocabulary — Master Summary       ║
╠══════════════════════════════════════════════════╣
║ Java    : OOP basics, JVM, GC, Generics          ║
║ Kotlin  : Null safety, Data/Sealed, Coroutines   ║
║ Android : 4 components, Lifecycle, ViewModel     ║
║ Build   : Gradle → DEX → APK/AAB, R8/ProGuard    ║
║ System  : Binder IPC, Zygote, LMK                ║
║ Perf    : ANR (5s), Frame (16ms), LeakCanary     ║
╚══════════════════════════════════════════════════╝
```

---

← [07 Android Build System](07_android_build_system.md) | [Index →](00_index.md)
