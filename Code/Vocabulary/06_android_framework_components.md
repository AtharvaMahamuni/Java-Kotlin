# Section 6 — Android Framework & Components (Q92–Q132)

---

## Android Architecture (Q92–Q95)

### Q92. What is the Android framework?
**Definition:** The set of APIs and system services that Android apps are built on — Activity, Fragment, Context, Services, etc.
**Core Idea:** The framework manages the app lifecycle, provides UI components, and mediates hardware access.
**How it Works:** Your app code calls into framework APIs (`startActivity`, `getSystemService`). The framework communicates with system services via Binder IPC.
**Example:** Calling `getSystemService(LOCATION_SERVICE)` returns a proxy to the LocationManagerService running in `system_server`.
**Interview Insight:** The Android framework is a layer between your code and the OS. You never own the main thread's Looper — the framework does.

---

### Q93. What are the main Android application components?
**Definition:** The four building blocks of an Android app: Activity, Service, BroadcastReceiver, ContentProvider.
**Core Idea:** Each has its own lifecycle, declared in the manifest. The system can instantiate them independently.

| Component | Purpose |
|---|---|
| Activity | UI screen |
| Service | Background work |
| BroadcastReceiver | System/app-wide events |
| ContentProvider | Shared data between apps |

**Interview Insight:** These are the entry points the system uses to activate your app. Even if the user hasn't launched your app, a BroadcastReceiver can wake it up.

---

### Q94. What is AndroidManifest.xml?
**Definition:** The XML configuration file declaring everything the app needs: components, permissions, features, minimum SDK.
**Core Idea:** The system reads the manifest to know what your app is and what it needs. Components not in the manifest are invisible to the system.
**How it Works:** Declares `<activity>`, `<service>`, `<receiver>`, `<provider>`, `<uses-permission>`, `<uses-feature>`.
**Example:** `<activity android:name=".MainActivity">` — registers MainActivity with the system.
**Interview Insight:** Missing a component from the manifest = "ActivityNotFoundException" at runtime. Permissions not declared = `SecurityException`. The manifest is read by PackageManager at install time.

---

### Q95. What is the Application class?
**Definition:** The base class for the global application state. Instantiated before any Activity/Service.
**Core Idea:** One instance per app process. Used for global initialization (DI setup, analytics, crash reporting).
**How it Works:** Extend `Application`, declare in manifest: `android:name=".MyApp"`. `onCreate()` runs when the process starts.
**Example:** Initializing Hilt (`@HiltAndroidApp`), Timber, Firebase — all done in `Application.onCreate()`.
**Interview Insight:** Don't store UI state or Activity references in Application — it lives longer than any Activity. It's killed with the process, NOT when the user "closes" the app.

---

## Activities (Q96–Q100)

### Q96. What is an Activity?
**Definition:** A single screen with a user interface. The fundamental unit of Android UI.
**Core Idea:** Each screen = one Activity (traditionally). Manages its own lifecycle and back stack position.
**How it Works:** Extends `AppCompatActivity`. System creates, starts, resumes, pauses, stops, destroys it based on user navigation and system memory.
**Example:** `MainActivity`, `SettingsActivity`, `LoginActivity` — each is a separate Activity.
**Interview Insight:** In modern Android (single-activity architecture), one Activity hosts multiple Fragments. But the Activity lifecycle knowledge is still essential.

---

### Q97. What is the Activity lifecycle?
**Definition:** The sequence of states an Activity passes through from creation to destruction.
**Core Idea:** The system controls the lifecycle; you respond to callbacks.

```
onCreate → onStart → onResume → [RUNNING]
                               ↓
                            onPause → onStop → onDestroy
```

| Callback | When called |
|---|---|
| `onCreate` | First creation; setup UI, ViewModel |
| `onStart` | Becoming visible |
| `onResume` | Foreground, user interacting |
| `onPause` | Losing foreground (another activity on top) |
| `onStop` | No longer visible |
| `onDestroy` | Being destroyed (back press or system) |

**Interview Insight:** `onPause` must be fast — the next Activity won't `onResume` until yours finishes `onPause`. Save state in `onSaveInstanceState`, not `onPause`/`onStop`.

---

### Q98. What happens during a configuration change?
**Definition:** A change in device configuration (rotation, locale, dark mode) causes the Activity to be destroyed and recreated.
**Core Idea:** The system saves and restores UI state via `onSaveInstanceState`/`onRestoreInstanceState`. ViewModel survives this.
**How it Works:** `onPause → onStop → onDestroy → onCreate → onStart → onResume`. ViewModel's `onCleared()` is NOT called during rotation.
**Example:** User rotates phone → Activity destroyed → recreated → ViewModel still has the data → no re-fetch needed.
**Interview Insight:** Bundle (from `onSaveInstanceState`) survives rotation but is limited in size. ViewModel survives rotation and holds large data. ViewModel + SavedStateHandle handles both cases.

---

### Q99. What is the Activity back stack?
**Definition:** A stack of Activities managed by the system. The top of the stack is the foreground Activity; back press pops it.
**Core Idea:** LIFO structure. `startActivity()` pushes. Back press / `finish()` pops.
**How it Works:** Each task has its own back stack. Multiple tasks can exist (app switcher shows tasks).
**Example:** Home → App A (MainActivity) → Settings → DetailActivity. Back stack: [Main, Settings, Detail]. Press back twice → Settings → Main.
**Interview Insight:** Tasks and back stacks are why launch modes exist. `singleTask` prevents duplicate Activity instances. `FLAG_ACTIVITY_CLEAR_TOP` clears above a target Activity.

---

### Q100. What are launch modes?
**Definition:** Attributes on an Activity that control how it is instantiated and placed in the back stack.
**Core Idea:** Controls whether a new instance is created or an existing one is reused.

| Mode | Behavior |
|---|---|
| `standard` | New instance every time (default) |
| `singleTop` | Reuses top if already there; calls `onNewIntent()` |
| `singleTask` | Single instance per task; clears above it |
| `singleInstance` | Single instance, own task, no other Activities allowed |

**Interview Insight:** `singleTop` is used for notification-tapped Activities (don't want duplicate). `singleTask` is used for the main launcher Activity. In modern Jetpack Navigation, you rarely need launch modes explicitly.

---

## Fragments (Q101–Q104)

### Q101. What is a Fragment?
**Definition:** A reusable, modular portion of UI that lives within an Activity. Has its own lifecycle.
**Core Idea:** Fragments enable flexible UI — one Activity can show different Fragments based on screen size or navigation.
**How it Works:** Managed by `FragmentManager`. Fragments are added to a container view in the Activity's layout.
**Example:** A tablet shows a list Fragment and detail Fragment side-by-side. A phone shows them sequentially in the same Activity.
**Interview Insight:** Fragments have TWO lifecycles: the Fragment lifecycle and the View lifecycle (`viewLifecycleOwner`). Always use `viewLifecycleOwner` for LiveData observation to avoid observing after the view is destroyed.

---

### Q102. What is the Fragment lifecycle?
**Definition:** The sequence of callbacks a Fragment goes through from attachment to detachment.

```
onAttach → onCreate → onCreateView → onViewCreated
         → onStart → onResume → [ACTIVE]
         → onPause → onStop → onDestroyView
         → onDestroy → onDetach
```

**Key difference from Activity:** `onDestroyView` is called when the view is removed but the Fragment instance may survive (in the back stack).
**Interview Insight:** Use `onViewCreated` for view setup (not `onCreateView`). Observe LiveData with `viewLifecycleOwner` to avoid leaks when view is destroyed but Fragment isn't.

---

### Q103. What is FragmentManager?
**Definition:** The class responsible for managing Fragment transactions — adding, removing, replacing, and finding Fragments.
**Core Idea:** Handles the Fragment back stack and transactions atomically.
**How it Works:** `supportFragmentManager.beginTransaction().replace(R.id.container, fragment).commit()`
**Example:** `supportFragmentManager.findFragmentById(R.id.container)` — find an existing Fragment.
**Interview Insight:** `commit()` is asynchronous (queued on main thread). `commitNow()` is synchronous. Using `commit()` after `onSaveInstanceState` throws `IllegalStateException` — use `commitAllowingStateLoss()` only as a last resort.

---

### Q104. Difference between `add()` and `replace()`?
**Definition:** `add()` adds a new Fragment on top (previous Fragment stays in layout). `replace()` removes the current Fragment and adds the new one.

| | `add()` | `replace()` |
|---|---|---|
| Previous Fragment | Stays in layout (views kept) | Removed from layout |
| Back stack | Both can be added | Both can be added |
| Memory | Higher (two Fragment views) | Lower |
| Use case | Overlay (dialogs, panels) | Full screen swap |

**Interview Insight:** `add()` keeps the previous Fragment's view alive — it can receive touch events (use `addToBackStack`). `replace()` destroys the previous view but the Fragment instance survives if added to back stack.

---

## Intents and Communication (Q105–Q108)

### Q105. What is an Intent?
**Definition:** A messaging object used to request an action from another Android component (Activity, Service, BroadcastReceiver).
**Core Idea:** Intents decouple components. You describe WHAT you want, not WHO should do it.
**How it Works:** `startActivity(intent)`, `startService(intent)`, `sendBroadcast(intent)` all use Intents.
**Example:** `Intent(this, DetailActivity::class.java)` — explicit. `Intent(Intent.ACTION_VIEW, uri)` — implicit.
**Interview Insight:** Intents pass data via `putExtra()`. Large data should NOT go in Intents — use a database or content provider. Intent has a 1MB IPC limit (Binder buffer).

---

### Q106. Difference between explicit and implicit intents?
**Definition:** Explicit = you specify the exact component class. Implicit = you describe the action, the system finds the component.

| | Explicit | Implicit |
|---|---|---|
| Target | Specified (`DetailActivity::class`) | Not specified |
| Use for | Within your app | Sharing, opening URLs, camera |
| Resolved by | Direct | PackageManager (intent filters) |

**Example:** Explicit: `Intent(this, SettingsActivity::class.java)`. Implicit: `Intent(Intent.ACTION_SEND).apply { type = "text/plain"; putExtra(Intent.EXTRA_TEXT, "Hello") }`.
**Interview Insight:** From Android 12+, implicit broadcast receivers must be declared in manifest. For security, use explicit intents within your app.

---

### Q107. What is an Intent filter?
**Definition:** Declared in the manifest, an Intent filter says "this component can handle Intents with THIS action/category/data."
**Core Idea:** How implicit intents are resolved — the system matches the intent to all registered filters.
**How it Works:** `<intent-filter><action android:name="android.intent.action.VIEW"/></intent-filter>` — this Activity can handle VIEW actions.
**Example:** `<action android:name="android.intent.action.MAIN"/>` + `<category android:name="android.intent.category.LAUNCHER"/>` = the app's entry point Activity.
**Interview Insight:** If no component matches an implicit Intent, `ActivityNotFoundException` is thrown. Always check `resolveActivity()` before calling `startActivity()` with an implicit intent.

---

### Q108. What are Intent extras?
**Definition:** Key-value pairs attached to an Intent to pass data between components.
**Core Idea:** Small data (IDs, strings, primitives) travels with the Intent. Parcelables for objects.
**How it Works:** `intent.putExtra("USER_ID", userId)`. Retrieved with `intent.getStringExtra("USER_ID")`.
**Example:** `intent.putExtra("user", user)` where `User` implements `Parcelable`.
**Interview Insight:** Intent extras go through Binder IPC (max ~1MB). For large data, pass an ID and load from DB on the other side. Never pass Bitmaps via Intent extras.

---

## Bundle (Q109–Q111)

### Q109. What is a Bundle?
**Definition:** A key-value data container used for passing data between Android components and saving instance state.
**Core Idea:** A map of String keys to supported types: primitives, strings, Parcelables, Serializables.
**How it Works:** `Bundle` is `Parcelable` — it can be serialized for IPC and for saving state.
**Example:** `bundle.putString("name", "Alice"); val name = bundle.getString("name")`
**Interview Insight:** Bundle uses `Parcel` under the hood — it's efficient for IPC. But it has size limits (~1MB for IPC). Large data should go in ViewModel or database.

---

### Q110. How is Bundle used to pass data?
**Definition:** As Fragment arguments (`fragment.arguments = bundle`) and to save/restore instance state (`onSaveInstanceState`).
**How it Works:**
- Fragment args: `MyFragment().apply { arguments = bundleOf("id" to userId) }`
- State save: `override fun onSaveInstanceState(outState: Bundle) { outState.putString("key", value) }`
- Restore: in `onCreate(savedInstanceState: Bundle?)`
**Example:** Navigation component passes data via Safe Args (type-safe Bundle wrapper).
**Interview Insight:** Fragment arguments survive configuration changes and process death. ViewModel survives rotation but NOT process death — use `SavedStateHandle` + Bundle for that.

---

### Q111. What are the limitations of Bundle?
**Definition:** Size (~1MB limit), type restrictions (only primitives/Parcelable/Serializable), no complex objects.
**Core Idea:** Bundle is a serialization mechanism — not every object can be put in it. Large data causes `TransactionTooLargeException`.
**How it Works:** Everything in a Bundle goes through Binder IPC. Binder's transaction buffer is ~1MB per process.
**Example:** Trying to put a large Bitmap in a Bundle → `TransactionTooLargeException`.
**Interview Insight:** The fix: save the data in a local database or in-memory cache, pass only the ID in the Bundle/Intent.

---

## Services (Q112–Q115)

### Q112. What is a Service?
**Definition:** An app component for running long-running background operations without a UI.
**Core Idea:** Runs in the main thread by default (NOT a background thread). Use a separate thread or coroutines for actual work.
**How it Works:** Extend `Service`. Declared in manifest. Started with `startService()` or `bindService()`.
**Example:** Downloading a file, playing music, syncing data — all long-running background tasks.
**Interview Insight:** Service runs on the main thread — doing blocking work in `onStartCommand` causes ANR. Always spawn a thread/coroutine inside the Service.

---

### Q113. What is a started service?
**Definition:** A Service started with `startService()`. Runs until it stops itself (`stopSelf()`) or someone calls `stopService()`.
**Core Idea:** Fire-and-forget. The component that started it doesn't get results back.
**How it Works:** `onStartCommand()` is called. Returns `START_STICKY` (restart on kill) or `START_NOT_STICKY`.
**Example:** `startService(Intent(this, DownloadService::class.java))` — starts downloading; Activity moves away; download continues.
**Interview Insight:** Modern replacement: `WorkManager` for deferrable background work, or `CoroutineWorker`. Direct use of `startService` is less common in new code.

---

### Q114. What is a bound service?
**Definition:** A Service that allows other components to bind to it and communicate via an interface (IBinder).
**Core Idea:** Client-server relationship. The service lives as long as a component is bound to it.
**How it Works:** Clients call `bindService()`. Service returns an `IBinder` in `onBind()`. Clients call methods on the binder.
**Example:** A music player Service that exposes `play()`, `pause()`, `getPosition()` to a bound Activity.
**Interview Insight:** Bound service is destroyed when all clients unbind (unless also started). Useful for local communication; for cross-process, use AIDL.

---

### Q115. What is a foreground service?
**Definition:** A Service that shows a persistent notification, indicating ongoing work the user is aware of. Not killed by the system under memory pressure.
**Core Idea:** Required for operations that must continue while the app is in the background AND the user is aware of it.
**How it Works:** Call `startForeground(notificationId, notification)` in `onStartCommand()` within 5 seconds.
**Example:** Music player, navigation (GPS), fitness tracker, file download progress.
**Interview Insight:** Android 9+ requires `FOREGROUND_SERVICE` permission. Android 12+ requires foreground service types. Background services are heavily restricted on modern Android — foreground service or WorkManager are the alternatives.

---

## Broadcast Receivers (Q116–Q118)

### Q116. What is a BroadcastReceiver?
**Definition:** A component that listens for system-wide or app-level broadcast messages (Intents).
**Core Idea:** Event-driven activation. The system or another app sends a broadcast; your receiver handles it.
**How it Works:** Extend `BroadcastReceiver`, implement `onReceive()`. Register in manifest or programmatically.
**Example:** Listen for `BOOT_COMPLETED` to start a service on boot; listen for `CONNECTIVITY_CHANGE` for network status.
**Interview Insight:** `onReceive()` runs on the main thread and must complete in 10 seconds or it gets ANR'd. For long work, use `goAsync()` or start a Service/WorkManager.

---

### Q117. What is a system broadcast?
**Definition:** An Intent broadcast sent by the Android system to notify apps of system events.
**Core Idea:** Device-wide events — boot completed, battery low, network changes, airplane mode, etc.
**How it Works:** Declared in manifest (`BOOT_COMPLETED`) or registered dynamically. Since Android 8.0, most implicit broadcasts can't be received by manifest-declared receivers.
**Example:** `Intent.ACTION_BATTERY_LOW`, `ConnectivityManager.CONNECTIVITY_ACTION`.
**Interview Insight:** Android 8.0 (Oreo) restricted background implicit broadcasts to save battery. Most are now dynamic-only or require `JobScheduler`/WorkManager.

---

### Q118. What is an ordered broadcast?
**Definition:** A broadcast delivered to receivers one at a time, in priority order. Each receiver can modify, abort, or pass along the broadcast.
**Core Idea:** Unlike normal broadcasts (delivered simultaneously), ordered broadcasts form a processing chain.
**How it Works:** `sendOrderedBroadcast()`. Higher priority receivers run first. Any receiver can abort with `abortBroadcast()`.
**Example:** SMS apps use ordered broadcasts — the highest-priority receiver can intercept and abort the default SMS notification.
**Interview Insight:** Normal broadcasts are more efficient (parallel). Ordered broadcasts guarantee sequential processing but are slower. Rarely needed in modern Android development.

---

## Content Providers (Q119–Q121)

### Q119. What is a ContentProvider?
**Definition:** A component that manages structured access to a shared data set. Enables sharing data between apps.
**Core Idea:** Provides a standard interface for CRUD operations on shared data, accessible via a URI.
**How it Works:** Extend `ContentProvider`, implement `query/insert/update/delete/getType`. Accessed via `ContentResolver`.
**Example:** Contacts, MediaStore (photos/videos), Calendar — all exposed as ContentProviders.
**Interview Insight:** ContentProvider is also used internally (Jetpack libraries use them for initialization — see `AppInitializer`). You rarely write one, but you use `ContentResolver` to query MediaStore.

---

### Q120. What is a content URI?
**Definition:** A URI that identifies content managed by a ContentProvider: `content://authority/path/id`.
**Core Idea:** Like a URL for data. The authority identifies the provider; the path/id identifies the data.
**How it Works:** `content://com.example.provider/users/42` — provider is `com.example.provider`, querying user with id 42.
**Example:** `MediaStore.Images.Media.EXTERNAL_CONTENT_URI` = `content://media/external/images/media`.
**Interview Insight:** Content URIs abstract the storage location. You use `ContentResolver.query(uri, ...)` without knowing if data is in SQLite, files, or memory.

---

### Q121. What are the CRUD operations in ContentProvider?
**Definition:** `query()`, `insert()`, `update()`, `delete()` — the four standard data operations on a ContentProvider.

| Method | SQL Equivalent | Returns |
|---|---|---|
| `query()` | SELECT | `Cursor` |
| `insert()` | INSERT | `Uri` of new row |
| `update()` | UPDATE | Rows affected (`Int`) |
| `delete()` | DELETE | Rows deleted (`Int`) |

**Example:** `contentResolver.query(uri, projection, selection, selectionArgs, sortOrder)` — returns a Cursor.
**Interview Insight:** Always close Cursors! Use `cursor.use { }` in Kotlin to auto-close. Cursors are expensive resources — don't keep them open longer than needed.

---

## Background Processing (Q122–Q125)

### Q122. What is WorkManager?
**Definition:** Jetpack library for deferrable, guaranteed background work that must run even if the app exits or the device restarts.
**Core Idea:** The modern solution for background tasks with constraints (network, charging, etc.).
**How it Works:** Define a `Worker`/`CoroutineWorker`, enqueue with constraints via `WorkManager.enqueue()`. Internally uses `JobScheduler` (API 23+) or `AlarmManager`.
**Example:** Uploading logs, syncing data, processing images — tasks that must eventually complete.
**Interview Insight:** Use WorkManager for guaranteed execution. For immediate background work (while app is visible), use coroutines. For precise timing, use `AlarmManager`.

---

### Q123. What is JobScheduler?
**Definition:** Android system API for scheduling background jobs with constraints (network, charging, idle) since API 21.
**Core Idea:** The system runs your job when conditions are met, batching jobs to save battery.
**How it Works:** Create a `JobInfo` with constraints, schedule via `JobScheduler.schedule()`. System calls `JobService.onStartJob()`.
**Example:** Sync data only when on WiFi and charging — declare as constraints in `JobInfo`.
**Interview Insight:** WorkManager wraps `JobScheduler` (and `AlarmManager` for older APIs). Prefer WorkManager — it handles API level differences and is restartable.

---

### Q124. What is a Handler?
**Definition:** Allows sending and processing `Message`s and `Runnable`s associated with a thread's `Looper`/`MessageQueue`.
**Core Idea:** The mechanism for posting work to run on a specific thread, most commonly the main thread.
**How it Works:** `Handler(Looper.getMainLooper()).post { updateUI() }` — posts a runnable to the main thread queue.
**Example:** From a background thread: `mainHandler.post { textView.text = result }` — safe UI update.
**Interview Insight:** In modern code, use coroutines (`withContext(Dispatchers.Main)`) instead of Handler. Handler is the underlying mechanism — understanding it explains how Looper/MessageQueue works.

---

### Q125. What is a Looper?
**Definition:** A class that runs a message loop for a thread. Continuously processes messages from the thread's `MessageQueue`.
**Core Idea:** The main thread has a `Looper` — that's what keeps the app running and responsive to UI events.
**How it Works:** `Looper.loop()` runs indefinitely, dequeuing messages and dispatching them to Handlers. The main thread's Looper is started by the framework.
**Example:** `Looper.getMainLooper()` — gets the main thread's Looper to post UI work.
**Interview Insight:** Every ANR is caused by blocking the main thread's Looper. The Looper can't process the next message (user touch, frame render) because your code is blocking. The Choreographer also uses the Looper to schedule frame renders.

---

## Data Passing (Q126–Q128)

### Q126. What is Parcelable?
**Definition:** An Android-specific interface for serializing objects to pass between components (Intent, Bundle, IPC).
**Core Idea:** Faster than Java `Serializable` because it avoids reflection. You write/read each field explicitly.
**How it Works:** Implement `Parcelable`, override `writeToParcel()` and `CREATOR`. Use `@Parcelize` in Kotlin for auto-generation.
**Example:** `@Parcelize data class User(val id: Int, val name: String) : Parcelable` — one annotation handles everything.
**Interview Insight:** Parcelable is ~10x faster than Serializable on Android because it uses a typed binary format (Parcel) not reflection. Always use Parcelable for Android-specific data passing.

---

### Q127. What is Serializable? (Android context)
**Definition:** Java's `Serializable` interface — objects can be passed via Intent/Bundle but with reflection-based serialization.
**Core Idea:** Easy to implement (just `implements Serializable`) but slower than Parcelable due to reflection and temp object creation.
**How it Works:** JVM reflects on all fields, creates temp objects during serialization/deserialization → GC pressure.
**Example:** `class User(val name: String) : Serializable` — works but not recommended for Android.
**Interview Insight:** Use `Parcelable` (or `@Parcelize`) on Android. The only time `Serializable` is acceptable is for cross-platform data (sharing with backend), not for inter-component communication.

---

### Q128. What is AIDL?
**Definition:** Android Interface Definition Language — a language for defining cross-process method interfaces (IPC).
**Core Idea:** Allows calling methods in another process as if they were local methods, via Binder under the hood.
**How it Works:** Define `.aidl` file → Android generates Java stub + proxy. Client calls proxy; Binder marshals args across process boundary to the stub.
**Example:** System APIs (LocationManager, WindowManager) use AIDL internally. Apps use AIDL for bound services that span processes.
**Interview Insight:** You rarely write AIDL directly — use Messenger or Binder directly for simple cases, or use alternatives (Broadcast, ContentProvider). AIDL is for complex cross-process method calls.

---

## System Behavior (Q129–Q132)

### Q129. What is ANR?
**Definition:** Application Not Responding — the system displays this dialog when the main thread is blocked for too long.
**Core Idea:** The UI thread can't process input events or draw frames because it's blocked by your code.
**How it Works:** Activity: 5 seconds without input response. BroadcastReceiver: 10 seconds. Service: 20 seconds. System shows ANR dialog.
**Example:** `Thread.sleep(10000)` on the main thread → ANR.
**Interview Insight:** Fix: move all I/O, computation, and database operations to background threads (coroutines, RxJava). Use `StrictMode` in debug builds to detect accidental disk/network I/O on main thread.

---

### Q130. What is the main/UI thread?
**Definition:** The single thread that handles all UI rendering, user input events, and Activity/Fragment lifecycle callbacks.
**Core Idea:** ALL view manipulation must happen here. It's driven by a Looper/MessageQueue.
**How it Works:** The framework starts the Looper on process start. Choreographer uses it to schedule 60fps frames. All lifecycle callbacks arrive via this Looper.
**Example:** `textView.text = "Hello"` — must be called from the main thread.
**Interview Insight:** The main thread is NOT just for UI — all lifecycle callbacks (onCreate, onResume, etc.) run here too. Any blocking call here (even a fast one in a loop) can cause dropped frames or ANR.

---

### Q131. What is process death?
**Definition:** When Android kills your app's process to free memory for the foreground app.
**Core Idea:** Your app can be killed without warning while in the background. No lifecycle callbacks fire for process death.
**How it Works:** The system uses Low Memory Killer (LMK) to kill background processes. When the user returns, Android recreates the Activity with `savedInstanceState`.
**Example:** User opens Maps → your app (in background) is killed → user switches back → your app restarts.
**Interview Insight:** ViewModel does NOT survive process death. Only `savedInstanceState` (Bundle) and persistent storage (DB, SharedPreferences) survive. Use `SavedStateHandle` in ViewModel for process-death-safe state.

---

### Q132. What is Low Memory Killer?
**Definition:** A kernel-level daemon that kills processes based on priority when the system is low on memory.
**Core Idea:** Android ranks processes by importance (foreground > visible > service > cached). LMK kills lowest-priority first.
**How it Works:** Process importance levels:
1. Foreground (active Activity)
2. Visible (partially visible Activity)
3. Service
4. Cached (backgrounded apps)

LMK kills cached processes first, then services if still low.
**Interview Insight:** You can't prevent LMK from killing your app. Design for it: save state persistently, use `SavedStateHandle`, don't assume your background process survives. This is why `onSaveInstanceState` exists.

---

← [05 Kotlin Collections](05_kotlin_collections_coroutines.md) | [07 Android Build System →](07_android_build_system.md)
