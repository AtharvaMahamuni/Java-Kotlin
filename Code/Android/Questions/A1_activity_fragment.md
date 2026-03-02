# Phase A1 — Activity & Fragment

Activity and Fragment are the foundational UI building blocks of Android. They are also the source of the most bugs, crashes, and memory leaks in Android development. The reason is deceptively simple: Android owns your Activity. You do not control when it is created, paused, stopped, destroyed, or recreated. You only receive callbacks. Every Android developer who does not deeply understand the lifecycle eventually writes code that crashes on rotation, leaks memory after navigation, or loses user data on process death. This phase gives you the mental model to reason about every state transition precisely.

---

## A1.1 — Activity Lifecycle

> **Builds on:** [A0.2 — Zygote & App Startup](A0_android_platform.md#a02--zygote--app-startup) · [A0.4 — Binder IPC](A0_android_platform.md#a04--binder-ipc)
> **Connects to:** [A1.2 — Configuration Changes](A1_activity_fragment.md#a12--configuration-changes) · [A1.3 — Fragment Lifecycle](A1_activity_fragment.md#a13--fragment-lifecycle)

### The Concrete Picture

Starting point: a running app. User presses the Home button, then returns to the app.

```
[User presses Home]
  Activity (currently in onResume — RUNNING)
      │
      ▼  onPause()      ← stop camera, release audio focus
      ▼  onStop()       ← persist data to DB, unregister receivers
      │
      │  [OS may kill process here — no callbacks!]
      │
[User taps icon again]
      │
      ├── if process alive ──► onRestart() ──► onStart() ──► onResume()
      │
      └── if process killed ──► cold start
              onCreate(savedBundle?)  ← bundle contains saved UI state
              onStart() ──► onResume()

[User presses Back]
  onPause() ──► onStop() ──► onDestroy()
  isFinishing = true  ← permanent destruction

[Screen rotates]
  onPause() ──► onSaveInstanceState(bundle) ──► onStop() ──► onDestroy()
  onCreate(bundle) ──► onStart() ──► onResume()
  isFinishing = false  ← temporary, ViewModel survives
```

### WHY The Lifecycle Exists

On a mobile device, the operating system needs to reclaim resources from apps that the user isn't actively looking at. Unlike a desktop OS where your app runs continuously in its own window with guaranteed RAM, Android's design principle is that the OS can kill any background app at any time to free memory for the foreground app. The Activity lifecycle is the mechanism by which Android tells your code what state your UI is in so you can respond appropriately — save state, release resources, stop animations.

The lifecycle is a contract between your app and the operating system. Android guarantees it will call these methods in a defined order. Your code must respond correctly to each.

### The 7 Callbacks: Precise Semantics

```
Activity created
      │
      ▼
 onCreate()      ← Called once per Activity instance. Inflate layout, init ViewModel,
      │            restore saved instance state. View hierarchy is not yet visible.
      │
      ▼
 onStart()       ← Activity is now visible to user but NOT interactive.
      │            Register broadcast receivers for UI-affecting events.
      │            onStop() is the paired callback.
      │
      ▼
 onResume()      ← Activity is now in FOREGROUND and INTERACTIVE.
      │            Start animations, camera preview, sensors.
      │            onPause() is the paired callback.
      │            Activity is now RUNNING.
      │
      │        ◄── User can interact here ──►
      │
      ▼
 onPause()       ← Activity is PARTIALLY obscured (dialog, multi-window, another app).
      │            Stop animations, release camera, pause video.
      │            MUST be fast — next Activity cannot resume until THIS returns.
      │            Do NOT do disk/network I/O here (too slow, blocks transition).
      │
      ▼
 onStop()        ← Activity is NO LONGER VISIBLE.
      │            Persist data, unregister broadcast receivers.
      │            Activity object is NOT yet destroyed (still in memory).
      │            Can be called directly from onStart() if Activity was briefly started.
      │
      ▼
 onDestroy()     ← Activity is about to be destroyed. Two causes:
      │            (a) finish() was called / user pressed Back → PERMANENT destroy
      │            (b) Configuration change (rotation) → TEMPORARY destroy + recreate
      │            Use isFinishing() to distinguish.
      │            Release ALL remaining resources. After this, the instance is gone.
      │
      ▼
 (Activity instance garbage collected)
```

**The return path (coming back to foreground):**

```
App was in background (onStop was called):
     ▼
 onRestart()     ← Called only when Activity returns from stopped state (NOT from paused).
     ▼            Use to refresh data that may have changed while stopped.
 onStart()
     ▼
 onResume()
```

### The Visibility Model: 3 Nested Scopes

The seven callbacks define three nested scopes with clear semantics:

```
┌──────────────────────────────────────────────────────────────────┐
│  ENTIRE LIFETIME: onCreate() ─────────────────────── onDestroy() │
│                                                                   │
│  ┌────────────────────────────────────────────────────────────┐   │
│  │  VISIBLE LIFETIME: onStart() ──────────────── onStop()     │   │
│  │                                                            │   │
│  │  ┌──────────────────────────────────────────────────────┐ │   │
│  │  │  FOREGROUND LIFETIME: onResume() ──── onPause()      │ │   │
│  │  │                                                      │ │   │
│  │  │   ← User can SEE and INTERACT with Activity here →  │ │   │
│  │  └──────────────────────────────────────────────────────┘ │   │
│  │                                                            │   │
│  │  Activity is VISIBLE but not interactive (onPause→onStop) │   │
│  └────────────────────────────────────────────────────────────┘   │
│                                                                   │
│  Activity exists in memory but is NOT visible (onStop→onDestroy) │
└──────────────────────────────────────────────────────────────────┘
```

### What To Do In Each Callback

| Callback | DO | DO NOT |
|----------|-----|--------|
| `onCreate` | Inflate layout, init ViewModel, set click listeners, restore savedInstanceState | Start animations, camera, location |
| `onStart` | Register receivers for UI events | Heavy initialization |
| `onResume` | Start camera/sensors/animations, acquire audio focus | Anything slow (it's on the main thread immediately) |
| `onPause` | Stop animations, release camera, release audio focus | Disk/network I/O (too slow — blocks next Activity from appearing) |
| `onStop` | Persist data to DB/prefs, unregister receivers, cancel network requests | Release ViewModel data (ViewModel survives config changes) |
| `onDestroy` | Release ALL resources, close threads | Anything you should have done in onStop |

### When the OS Can Kill Your Process

**The OS will NEVER kill a process in the foreground (onResume state).** It kills processes in order from least important to most important:

```
Kill priority (highest to lowest):
  1. Empty processes — no active components           ← killed first
  2. Background processes — Activity in stopped state ← killed frequently
  3. Service processes — running a Service            ← killed under pressure
  4. Visible processes — Activity partially visible (onPause) ← rarely killed
  5. Foreground processes — Activity in onResume      ← never killed
```

This is why `onStop()` is the right place to save persistent data — your process can be killed AFTER `onStop()` but the OS will never kill you during or before `onStop()` unless you're a low-priority process.

**Critical: the OS does NOT call `onDestroy()` when killing your process.** Process death is immediate — the kernel sends SIGKILL. There is no opportunity for cleanup. This is why you should never rely on `onDestroy()` for critical resource release.

### The `isFinishing()` Flag

In `onDestroy()`, you often need to know whether the Activity is being destroyed permanently (user pressed Back) or temporarily (rotation):

```kotlin
override fun onDestroy() {
    super.onDestroy()
    if (isFinishing) {
        // User is leaving — permanent destroy
        // Release resources that the ViewModel doesn't need
        analytics.trackExit()
    } else {
        // Configuration change — Activity will be recreated immediately
        // ViewModel WILL survive, so don't release ViewModel-owned resources
    }
}
```

### Complete State Transition Diagram

```
                    [Activity does NOT exist]
                             │
                             │ startActivity() called
                             ▼
                         onCreate()
                             │
                             ▼
                          onStart()
                             │
                             ▼
                          onResume()
                             │
               ┌─────────── RUNNING ─────────────┐
               │      (foreground, interactive)    │
               │                                   │
               │ another app / dialog appears      │ user presses Back
               ▼                                   ▼
           onPause()                          onPause()
               │                                   │
               │ that app goes away                │
               │ (Activity visible again)          ▼
               │                             onStop()
               ▼                                   │
           onResume()                              │
                                                   ▼
                                             onDestroy()
                                                   │
                                    ┌──────────────┴──────────────┐
                                    │                             │
                             isFinishing=true              isFinishing=false
                                    │                             │
                          [Activity gone forever]       [Recreated for config change]
                                                               │
                                                          onCreate(savedState)
                                                               │
                                                            onStart()
                                                               │
                                                            onResume()
```

### Memory Trick

```
7 CALLBACKS: Create Start Resume [RUNNING] Pause Stop Destroy
  "Can Steve Run? Perhaps Sadly Died."

3 SCOPES (nested):
  Entire:     onCreate ────────────────────── onDestroy
  Visible:      onStart ──────────── onStop
  Foreground:     onResume ── onPause

KILL ORDER (highest kill priority to lowest):
  Empty > Background > Service > Visible > Foreground (NEVER killed)

TRAP: onDestroy() NOT called on process kill (SIGKILL is instant).
  Save critical data in onStop(). isFinishing() = true means Back was pressed.
```

---

## A1.2 — Configuration Changes

> **Builds on:** [A1.1 — Activity Lifecycle](A1_activity_fragment.md#a11--activity-lifecycle)
> **Connects to:** [A4 — ViewModel & State Management](A4_viewmodel_state.md)

### The Concrete Picture

Starting point: user is on your app with a loaded list of 100 items, then rotates the phone.

```
Portrait Activity (instance A, PID 12345)
  users: [100 User objects in memory]
  searchQuery: "alice"
      │
      ▼  onPause()
      ▼  onSaveInstanceState(bundle)  ← bundle.putString("query", "alice")
      ▼  onStop()
      ▼  onDestroy()  ← instance A is GC'd
         (but ViewModelStore is RETAINED by ActivityThread.NonConfigurationInstance)

Landscape Activity (instance B, same PID 12345)
      ▼  onCreate(bundle)   ← bundle.getString("query") → "alice"   (small UI state back)
      ▼  viewModels<MyViewModel>()  ──► returns SAME ViewModel from retained store
         users: still the 100 User objects  ← no re-fetch needed!
      ▼  onStart() ──► onResume()

Result:
  searchQuery restored from bundle  (survived process death too)
  users list restored from ViewModel (survived rotation, NOT process death)
```

### WHY Configuration Changes Destroy Activities

Android's design decision to destroy and recreate an Activity on configuration changes is controversial but principled. The reason: many app resources are configuration-dependent. When you rotate from portrait to landscape, the correct layout file changes (`res/layout/` vs `res/layout-land/`), the correct strings change (locale change), the correct colors change (night mode change). The cleanest way to pick up these new resources is to recreate the Activity from scratch — the system can then re-inflate the layout, re-read strings and drawables, and start with a fresh configuration-aware resource set.

**Triggers for configuration change (Activity is destroyed and recreated):**
- Screen rotation (portrait ↔ landscape)
- Multi-window resize
- Locale change (language switch)
- Night mode toggle (dark/light mode)
- Font size change (accessibility)
- Keyboard availability change
- Screen density change (foldable unfolding to a larger display)

### The Four Mechanisms for Surviving Configuration Changes

#### Mechanism 1: `onSaveInstanceState` / `onRestoreInstanceState`

The system calls `onSaveInstanceState(Bundle)` before destroying the Activity. You populate the Bundle with primitive state. On recreation, `onCreate(savedInstanceState)` receives it back.

```kotlin
override fun onSaveInstanceState(outState: Bundle) {
    super.onSaveInstanceState(outState)
    outState.putString("search_query", searchQuery)
    outState.putInt("scroll_position", recyclerView.computeVerticalScrollOffset())
    // Parcelable objects (not bitmaps! — too large):
    outState.putParcelable("selected_item", selectedItem)
}

override fun onCreate(savedInstanceState: Bundle?) {
    super.onCreate(savedInstanceState)
    setContentView(R.layout.activity_main)
    if (savedInstanceState != null) {
        searchQuery = savedInstanceState.getString("search_query")
        // scroll position restore after layout is done:
        binding.recyclerView.post {
            binding.recyclerView.scrollBy(0, savedInstanceState.getInt("scroll_position"))
        }
    }
}
```

**What the Bundle survives:**
- Configuration changes: YES
- Process death (OS kills background app): YES (the system serializes the Bundle to disk)
- User pressing Back: NO (activity is finishing, not being saved)

**Size limit:** The Bundle is serialized and passed through the Binder IPC. Binder has a 1MB transaction limit across ALL active Binder calls for a process. Do NOT put large objects (bitmaps, large lists) in a Bundle — you risk `TransactionTooLargeException`.

**What to save:** Small, primitive UI state — selected tab index, scroll position, search query text, checked state of checkboxes. NOT your data (network responses, database results) — that belongs in ViewModel.

#### Mechanism 2: ViewModel (The Right Approach)

`ViewModel` is the modern solution. It survives configuration changes because it is stored in a `ViewModelStore` that is retained across the destroy-recreate cycle. See A4 for full details.

```
Configuration change:

  Activity instance A  ─── onSaveInstanceState() ──►  Bundle (persisted)
  Activity instance A  ─── onDestroy() ──────────────► [destroyed]

  ViewModelStore ────────────────────────────────────► [RETAINED, not destroyed]
       │ contains ViewModel instance
       ▼
  Activity instance B  ─── onCreate(bundle) ────────── [recreated]
  Activity instance B  ─── viewModels<MyViewModel>() → SAME ViewModel instance
```

#### Mechanism 3: `android:configChanges` (Intercept Specific Changes)

You can declare in the manifest that your Activity will handle specific configuration changes itself, preventing the system from recreating it:

```xml
<activity
    android:name=".VideoPlayerActivity"
    android:configChanges="orientation|screenSize|keyboardHidden" />
```

When these changes occur, the system calls `onConfigurationChanged(newConfig)` instead of destroying the Activity. You manually update UI for the new configuration.

**Use sparingly.** This is appropriate for Activities that handle their own resource loading (e.g., a full-screen video player using custom SurfaceView that doesn't need to re-inflate any layouts). Misusing it prevents proper resource re-selection — your app will use the wrong drawable/string on configuration change.

#### Mechanism 4: Retained Fragments (deprecated pattern)

Before ViewModel, `setRetainInstance(true)` on a Fragment retained the Fragment object across configuration changes. This is now deprecated — use ViewModel instead.

### The Exact Callback Order During Rotation (Android P+)

```
User rotates device — this is the EXACT callback sequence:

Old Activity:
  1. onPause()
  2. onSaveInstanceState(bundle)    ← Android P+: guaranteed before onStop
  3. onStop()
  4. onDestroy()

New Activity (created immediately):
  5. onCreate(bundle)              ← receives the same bundle
  6. onStart()
  7. onResume()
```

The key detail from Android P (API 28): `onSaveInstanceState` is guaranteed to be called BEFORE `onStop`. Before API 28, it was called between `onPause` and `onStop`. This means on modern Android you can safely rely on `onSaveInstanceState` being called even when `onStop` is followed by process death.

### Process Death vs Configuration Change

These are fundamentally different events:

```
Configuration Change:                    Process Death:
─────────────────────                    ─────────────────
Old Activity destroyed:                  Process killed by OS (SIGKILL):
  onPause → onStop →                      NO CALLBACKS AT ALL
  onSaveInstanceState → onDestroy

ViewModel: SURVIVES                      ViewModel: DESTROYED (in-memory only)
Bundle: PASSED directly                  Bundle: PERSISTED to disk by system
        to new Activity                         (at the time of onSaveInstanceState)
Non-serializable data: KEPT (ViewModel)  Non-serializable data: LOST

User perception: seamless               User perception: app "restarts" but
                (same process)          UI state is restored from bundle
```

This is why you need BOTH ViewModel AND `onSaveInstanceState`:
- ViewModel holds the large data (network results, lists) — survives rotation efficiently
- Bundle holds the minimal UI state — survives process death

**Three destruction paths — what survives each:**

```
                   Config Change          Process Death          user.finish()
                   (rotation, locale)     (OS kills process)     (back/explicit)
                   ─────────────────      ──────────────────     ───────────────
Callbacks:         onPause                NO CALLBACKS            onPause
                   onSaveInstState        (SIGKILL is instant)    onStop
                   onStop                                         onDestroy
                   onDestroy
                   onCreate(bundle)
                   onStart / onResume

ViewModel:         ✅ SURVIVES            ❌ DESTROYED            ❌ DESTROYED
                   (ViewModelStore        (in-memory object       (cleared with
                    retained via           is gone)                the Activity)
                    NonConfigInstance)

savedInstanceState ✅ SURVIVES            ✅ SURVIVES             ❌ GONE
Bundle:            (passed directly       (serialized to disk     (never saved if
                    to new onCreate)       by system before        user presses back
                                          kill; restored on       without rotation)
                                          next launch)

In-memory state:   ✅ SURVIVES            ❌ LOST                 ❌ LOST
(non-ViewModel)    (same process)

Persistent store:  ✅ SURVIVES            ✅ SURVIVES             ✅ SURVIVES
(Room, prefs)      (never affected)       (disk is intact)        (disk is intact)

─────────────────────────────────────────────────────────────────────────────────
Rule of thumb:
  • Large in-flight data (loaded list, user session)  →  ViewModel
  • Small UI state (search query, scroll position)   →  savedInstanceState
  • Critical persistent data (drafts, edits)         →  Room / DataStore
    (before onStop — the only guarantee across all three paths)
```

---

## A1.3 — Fragment Lifecycle

> **Builds on:** [A1.1 — Activity Lifecycle](A1_activity_fragment.md#a11--activity-lifecycle)
> **Connects to:** [A1.4 — Tasks & Back Stack](A1_activity_fragment.md#a14--tasks-back-stack--launch-modes)

### WHY Fragments Are Complex

A Fragment's lifecycle is more complex than an Activity's because a Fragment has TWO separate lifetimes running in parallel:
1. The **Fragment object lifetime** — when the Fragment instance is created and destroyed
2. The **Fragment view lifetime** — when the Fragment's inflated view hierarchy exists

These two lifetimes are DIFFERENT. A Fragment can exist without a view — specifically, when a Fragment is on the back stack. The Fragment manager retains the Fragment object but destroys its view to save memory. When the user presses Back, the Fragment's view is re-created without re-creating the Fragment object.

Failing to understand this duality is the root cause of the most common Fragment memory leak.

### The Complete Fragment Lifecycle

```
Activity starts, Fragment added:
    ┌──────────────────────────────────────────┐
    │  FRAGMENT OBJECT LIFETIME                │
    │                                          │
    │  onAttach(context)  ← Fragment attached  │
    │       │               to Activity        │
    │       ▼                                  │
    │  onCreate()         ← Fragment created   │
    │       │               (NOT view yet)     │
    │       │                                  │
    │       │  ┌─────────────────────────────┐ │
    │       │  │  VIEW LIFETIME              │ │
    │       │  │                             │ │
    │       ▼  ▼                             │ │
    │  onCreateView()     ← inflate the view │ │
    │       │                                │ │
    │       ▼                                │ │
    │  onViewCreated()    ← view is ready    │ │
    │       │               set up observers │ │
    │       │               click listeners  │ │
    │       ▼                                │ │
    │  onStart()                             │ │
    │       ▼                                │ │
    │  onResume()         ← INTERACTIVE      │ │
    │       │                                │ │
    │       │  ◄── user interacts ──►        │ │
    │       │                                │ │
    │       ▼                                │ │
    │  onPause()                             │ │
    │       ▼                                │ │
    │  onStop()                              │ │
    │       ▼                                │ │
    │  onDestroyView()   ← VIEW DESTROYED   │ │
    │       │  (Fragment may still exist     │ │
    │       │   on back stack!)              │ │
    │       │  └─────────────────────────────┘ │
    │       │                                  │
    │       ▼                                  │
    │  onDestroy()        ← Fragment destroyed │
    │       ▼                                  │
    │  onDetach()         ← detached from      │
    │                       Activity           │
    └──────────────────────────────────────────┘
```

### The Back Stack Scenario: Why Two Lifecycles Matter

```
Initial state:  Activity with FragmentA displayed
  FragmentA: onAttach → onCreate → onCreateView → onViewCreated → onStart → onResume

User navigates to FragmentB (FragmentA added to back stack):
  FragmentA: onPause → onStop → onDestroyView    ← VIEW DESTROYED
             (Fragment A OBJECT still exists! It's on the back stack)
  FragmentB: onAttach → onCreate → onCreateView → ... → onResume

User presses Back (return to FragmentA):
  FragmentB: onPause → onStop → onDestroyView → onDestroy → onDetach
  FragmentA: onCreateView → onViewCreated → onStart → onResume
             (Fragment A OBJECT was retained — no onCreate again!)
             (View is RE-CREATED from scratch)
```

**The critical insight:** Between `onDestroyView` and `onCreateView` (when on the back stack), the Fragment object exists but its view does not. Any reference your Fragment holds to its views (via ViewBinding, `findViewById`, etc.) points to a destroyed view tree that will never be drawn again. This is the memory leak.

### The ViewBinding Memory Leak (and the Fix)

This is one of the most famous Fragment bugs:

```kotlin
// WRONG — MEMORY LEAK:
class MyFragment : Fragment(R.layout.fragment_my) {
    private lateinit var binding: FragmentMyBinding

    override fun onCreateView(inflater: LayoutInflater, container: ViewGroup?, saved: Bundle?): View {
        binding = FragmentMyBinding.inflate(inflater, container, false)
        return binding.root
    }

    // NO nulling of binding in onDestroyView!
    // The Fragment object (on back stack) holds a reference to binding,
    // which holds references to all the Views in the layout,
    // which hold references to Context, Drawables, etc.
    // None of this can be GC'd while the Fragment is on the back stack.
}

// CORRECT — null the binding in onDestroyView:
class MyFragment : Fragment(R.layout.fragment_my) {
    private var _binding: FragmentMyBinding? = null
    private val binding get() = _binding!!   // non-null accessor (safe in onViewCreated..onDestroyView)

    override fun onCreateView(inflater: LayoutInflater, container: ViewGroup?, saved: Bundle?): View {
        _binding = FragmentMyBinding.inflate(inflater, container, false)
        return _binding!!.root
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)
        // Use binding here safely
        binding.button.setOnClickListener { ... }
    }

    override fun onDestroyView() {
        super.onDestroyView()
        _binding = null    // ← CRITICAL: break the reference to the view hierarchy
    }
}
```

### `viewLifecycleOwner` vs `viewModelOwner`: The Observer Trap

Coroutine flows and LiveData must be collected/observed with the **view's** lifecycle owner, not the fragment's lifecycle owner:

```kotlin
override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
    // WRONG: uses Fragment's lifecycle
    // On back navigation, Fragment exists but its view is gone.
    // When the user returns, a NEW observer is added to the same LiveData.
    // Now you have TWO active observers — data delivered twice!
    viewModel.data.observe(this) { updateUI(it) }

    // CORRECT: uses the view's lifecycle (tied to view creation/destruction)
    // Observer is removed in onDestroyView, so no duplicate observers.
    viewModel.data.observe(viewLifecycleOwner) { updateUI(it) }

    // For StateFlow/SharedFlow, ALWAYS use viewLifecycleOwner:
    viewLifecycleOwner.lifecycleScope.launch {
        viewLifecycleOwner.repeatOnLifecycle(Lifecycle.State.STARTED) {
            viewModel.uiState.collect { render(it) }
        }
    }
}
```

The `viewLifecycleOwner` starts at `onViewCreated` and ends at `onDestroyView`. The `this` (Fragment) lifecycle starts at `onCreate` and ends at `onDestroy`. Using `this` for a view observer means the observer lives longer than the view.

### Fragment Communication: The Right Patterns

**Pattern 1: Shared ViewModel (same Activity scope — recommended)**
```kotlin
// Both fragments share the SAME ViewModel instance (scoped to the Activity):
class FragmentA : Fragment() {
    private val sharedVm: SharedViewModel by activityViewModels()
    // publish event:
    fun onButtonClick() { sharedVm.selectedItem.value = item }
}

class FragmentB : Fragment() {
    private val sharedVm: SharedViewModel by activityViewModels()
    override fun onViewCreated(...) {
        sharedVm.selectedItem.observe(viewLifecycleOwner) { display(it) }
    }
}
```

**Pattern 2: Fragment Result API (one-shot results — e.g., dialog results)**
```kotlin
// Sender fragment (child/dialog):
setFragmentResult("requestKey", bundleOf("result" to selectedValue))

// Receiver fragment:
setFragmentResultListener("requestKey") { _, bundle ->
    val result = bundle.getString("result")
    handleResult(result)
}
```

**Anti-pattern: Direct fragment references**
```kotlin
// NEVER do this — fragments should not hold references to each other:
val otherFragment = parentFragmentManager.findFragmentById(R.id.other) as OtherFragment
otherFragment.updateData(data)  // tight coupling, lifecycle issues
```

---

## A1.4 — Tasks, Back Stack & Launch Modes

> **Builds on:** [A0.4 — Binder IPC](A0_android_platform.md#a04--binder-ipc) · [A1.1 — Activity Lifecycle](A1_activity_fragment.md#a11--activity-lifecycle)
> **Connects to:** [A5 — Navigation Component](A5_navigation.md)

### WHY Tasks Exist

Android supports multiple apps running simultaneously. A user might be reading an email, tap a link, have Chrome open, then press Back to return to the email. The system needs to track which Activity belongs to which navigation session. **Tasks** are Android's mechanism for this: a stack of Activities that represents a discrete user journey.

### What Is a Task?

A Task is a stack of Activity records that the system maintains. Each time you call `startActivity()`, the new Activity is pushed onto the current task's stack. When the user presses Back, the top Activity is popped and destroyed, revealing the one below.

```
Task (back stack) — user opens Email → taps link → Chrome opens URL:

     ┌──────────────────────┐  ← TOP (current screen = ChomeTabActivity)
     │  ChromeTabActivity   │
     ├──────────────────────┤
     │  EmailDetailActivity │
     ├──────────────────────┤
     │  EmailListActivity   │
     └──────────────────────┘  ← BOTTOM (root)

Back pressed:
  ChromeTabActivity popped → EmailDetailActivity is shown
Back pressed again:
  EmailDetailActivity popped → EmailListActivity is shown
Back pressed again:
  EmailListActivity popped → Task is empty → app goes to background (or home)
```

### The Four Launch Modes

Launch modes control how the Activity Manager creates or reuses Activity instances when `startActivity()` is called.

#### `standard` (default)
A new instance is ALWAYS created, regardless of whether an instance of this Activity already exists in the task.

```
Stack before: [A] [B] [C]
startActivity(C):
Stack after:  [A] [B] [C] [C]   ← two instances of C!
```
Use when: most Activities. Each `startActivity()` call represents a distinct piece of navigation.

#### `singleTop`
If an instance of this Activity is already at the TOP of the current task, no new instance is created. Instead, `onNewIntent(intent)` is called on the existing instance.

```
Stack before: [A] [B] [C]       ← C is at top
startActivity(C):
  C is at top → call onNewIntent(intent) on existing C
Stack after:  [A] [B] [C]       ← no new instance
```

```
Stack before: [A] [C] [B]       ← B is at top, not C
startActivity(C):
Stack after:  [A] [C] [B] [C]  ← C created (B was on top, not C)
```

Use when: notification-launched Activities (multiple notifications might launch the same Activity; you want to reuse the top one rather than stacking duplicates), search Activities.

#### `singleTask`
The Activity can only have ONE instance across ALL tasks. If an instance exists in ANY task, that task is brought to the foreground and `onNewIntent` is called. All Activities ABOVE it in its task are destroyed (popped off).

```
Task 1: [A] [B] [C]            Task 2: [X] [Y (singleTask)]
startActivity(Y) from C:
  Y exists in Task 2 → bring Task 2 to foreground → onNewIntent(Y)
  All activities above Y (none here) are destroyed
Result: Task 2: [X] [Y] in foreground
```

```
Task 1: [A] [B] [C]            Task 2: [X] [Y (singleTask)] [Z]
startActivity(Y) from C:
  Y exists in Task 2 → bring Task 2 → Z is DESTROYED (popped) → onNewIntent(Y)
Result: Task 2: [X] [Y] in foreground (Z is gone!)
```

Use when: The app's "home" screen or main entry point (launcher Activity). Deep-linked root screens.

#### `singleInstance`
Like `singleTask` but even more extreme: the Activity gets its OWN private task that no other Activity can be added to. Starting any other Activity from a `singleInstance` Activity opens that Activity in a DIFFERENT task.

```
singleInstance Activity I in its own Task:
  Task SI: [I]       (nothing else can join this task)

I calls startActivity(B):
  B cannot join Task SI → B goes to the previous task or a new task
```

Use when: System-level overlay Activities (the incoming call screen, alarm screen). Rarely needed in normal app development.

### Intent Flags: The Imperative Version of Launch Modes

Instead of declaring launch mode in the manifest, you can specify behavior per Intent:

```kotlin
// FLAG_ACTIVITY_SINGLE_TOP: same as singleTop launch mode for this intent
intent.addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP)

// FLAG_ACTIVITY_CLEAR_TOP: if the target Activity is in the current task,
// all activities ABOVE it are destroyed and onNewIntent is called
// (similar to singleTask but for the current task only)
intent.addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP)
// Without SINGLE_TOP: the target Activity is DESTROYED and RECREATED
// With SINGLE_TOP: onNewIntent is called on the existing instance (usually what you want)

// FLAG_ACTIVITY_NEW_TASK: start Activity in a new task (required when starting
// from non-Activity context: Service, Application)
intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)

// FLAG_ACTIVITY_CLEAR_TASK + FLAG_ACTIVITY_NEW_TASK: clears the entire task,
// then starts the Activity at the bottom of a fresh task.
// Used for "logout and go to login screen" flows.
intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK)
```

### The "Logout → Login" Pattern

A common requirement: user logs out, go to LoginActivity, make it impossible to press Back to return to the authenticated screens:

```kotlin
fun logout() {
    clearAuthData()
    val intent = Intent(this, LoginActivity::class.java).apply {
        addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK)
        // This creates a new task and clears ALL existing tasks,
        // placing LoginActivity as the only activity.
        // Back press from Login exits the app.
    }
    startActivity(intent)
}
```

---

## Master Summary

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    A1 — Activity & Fragment                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  1. ACTIVITY LIFECYCLE (7 callbacks)                                        │
│     onCreate → onStart → onResume → [RUNNING] → onPause → onStop →         │
│     onDestroy (or BACK to onRestart → onStart → onResume)                  │
│                                                                             │
│     3 scopes: entire(onCreate→onDestroy), visible(onStart→onStop),         │
│     foreground(onResume→onPause).                                           │
│                                                                             │
│     OS kills: background (onStop'd) > services > visible (onPause'd) >     │
│     foreground (onResume'd, NEVER killed). Process death = no callbacks.   │
│                                                                             │
│     onSaveInstanceState: save primitive UI state. Survives config change    │
│     AND process death. Max ~50KB (Binder 1MB limit). NO bitmaps.          │
│                                                                             │
│  2. CONFIGURATION CHANGES                                                   │
│     Default: destroy + recreate Activity. Resources re-selected correctly. │
│     ViewModel: SURVIVES config change (ViewModelStore retained). Lost on   │
│     process death. Save non-serializable, expensive-to-recreate data here. │
│     Bundle: survives BOTH config change AND process death. Persisted to    │
│     disk. Use for minimal UI state only.                                   │
│     Rotation callback order: onPause → onSaveInstanceState → onStop →     │
│     onDestroy → onCreate(bundle) → onStart → onResume                     │
│                                                                             │
│  3. FRAGMENT LIFECYCLE (TWO lifetimes!)                                     │
│     Fragment object: onCreate → ... → onDestroy                            │
│     Fragment view: onCreateView → onViewCreated → ... → onDestroyView      │
│     Back stack: Fragment object SURVIVES (retained), view DESTROYED.       │
│     ViewBinding LEAK: binding = null in onDestroyView to break reference.  │
│     Observer leak: use viewLifecycleOwner (not `this`) for observers.      │
│     Duplicate observers: using `this` = observer lives past onDestroyView  │
│     → on re-attach, second observer added → events delivered TWICE.        │
│                                                                             │
│  4. TASKS & LAUNCH MODES                                                    │
│     Task = back stack of Activities for one user journey.                  │
│     standard: always new instance. singleTop: reuse if at top (onNewIntent)│
│     singleTask: one instance per system, clears above it in task.          │
│     singleInstance: own private task (no other activities join).           │
│     Flags: CLEAR_TOP+SINGLE_TOP = reuse existing. NEW_TASK+CLEAR_TASK =   │
│     fresh start (use for logout flows).                                    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

*← [Phase A0 — Android Platform](A0_android_platform.md) | [Phase A2 — Main Thread & View System →](A2_main_thread_and_views.md)*
