# Phase A0 — Android Platform Architecture

Before you can understand Activities, ViewModels, Coroutines, or any Android framework API, you need a mental model of the runtime environment your code actually executes in. Android is not just a Java runtime with a UI layer on top — it is a carefully layered operating system built on Linux, with its own virtual machine, its own inter-process communication system, and its own process lifecycle rules. Every mysterious behavior in Android development (why does rotation kill my Activity? why is my service killed? why does a context leak? why is IPC expensive?) has a precise root cause in this platform architecture. This phase builds the foundation that every other phase rests on.

---

## A0.1 — The Android System Stack

> **Connects to:** [A0.2 — Zygote & App Startup](A0_android_platform.md#a02--zygote--app-startup) · [A0.4 — Binder IPC](A0_android_platform.md#a04--binder-ipc)

### The Concrete Picture

Starting point: you call `context.getSystemService(Context.LOCATION_SERVICE)` in your Activity.

```
Your Activity (App process, UID 10023)
    │ getSystemService("location")
    ▼
Java Framework Layer (android.location.LocationManager)
    │ returns a LOCAL PROXY object
    │ proxy.getLastKnownLocation() ──────────────────────────────►
    │                                                           Binder IPC call
    ▼                                                           (crosses process boundary)
system_server (PID ~800, UID 1000)
    │ LocationManagerService.getLastKnownLocation()
    ▼
Native GPS library (JNI call)
    ▼
HAL GPS interface (.so library from chip vendor)
    ▼
GPS hardware chip (Linux kernel driver)
```

Every Android API call traverses these layers bottom-to-top and back.
The sandbox: your app cannot touch GPS hardware directly — it must go through Binder.

### WHY This Matters

When you call `context.getSystemService(Context.LOCATION_SERVICE)`, where does that call actually go? When Android kills your app process under memory pressure, what mechanism decides which process dies first? When your code calls `startActivity(intent)`, how does the system find the right Activity across process boundaries? None of these questions are answerable without understanding how Android is layered.

### The Five Layers

Android's architecture is a stack of five distinct layers, each building on the one below:

```
┌─────────────────────────────────────────────────────────────────────┐
│  Layer 5: Applications                                               │
│  Your app, the Launcher, Settings, Phone, Camera...                 │
│  (APK files, run as separate Linux processes)                        │
├─────────────────────────────────────────────────────────────────────┤
│  Layer 4: Java Framework API                                         │
│  ActivityManager, WindowManager, PackageManager, ContentResolver    │
│  LocationManager, TelephonyManager, NotificationManager...          │
│  (android.app.*, android.content.*, android.view.*, android.os.*…) │
├─────────────────────────────────────────────────────────────────────┤
│  Layer 3: Android Runtime (ART) + Native Libraries                  │
│  ART: runs .dex bytecode, garbage collection, JIT/AOT               │
│  Native: OpenGL ES, Bionic libc, SQLite, WebKit, Media Framework    │
├─────────────────────────────────────────────────────────────────────┤
│  Layer 2: Hardware Abstraction Layer (HAL)                           │
│  Standardized interfaces for camera, bluetooth, audio, GPS, NFC…    │
│  Vendor-provided implementations (.so shared libraries)             │
├─────────────────────────────────────────────────────────────────────┤
│  Layer 1: Linux Kernel                                               │
│  Process scheduling, memory management, file system, device drivers │
│  Power management, network stack, IPC (Binder driver)               │
└─────────────────────────────────────────────────────────────────────┘
```

### Layer 1: Linux Kernel — Why Android Uses Linux

Android chose Linux not because of its desktop heritage but because Linux provides exactly what a mobile OS needs:

1. **Process isolation:** Each Android app runs as a separate Linux process with its own UID (user ID). The kernel enforces that process X cannot read the memory of process Y. This is the app sandbox — your app literally cannot touch another app's data because the kernel prevents it.

2. **Memory management:** Linux's virtual memory system, page tables, and the OOM (Out-Of-Memory) killer are what allow Android to juggle dozens of apps. The OOM killer is what kills background apps under memory pressure — it is a Linux kernel feature, not an Android framework one.

3. **File system:** Android's app data isolation (`/data/data/com.your.package/`) is enforced by Linux file permissions — each app's directory is owned by that app's UID.

4. **Binder driver:** The Binder IPC mechanism lives as a Linux kernel driver (`/dev/binder`). Everything in Android that crosses process boundaries goes through it.

### Layer 2: HAL — Hiding Hardware Differences

The Hardware Abstraction Layer exists because Android runs on phones from hundreds of manufacturers, each with different hardware (Qualcomm vs MediaTek vs Samsung Exynos CPUs, different camera hardware, different radios). Without HAL, every Android release would need different code for every chip variant.

HAL defines a standard C/C++ interface for each hardware capability. The hardware vendor provides the implementation (a `.so` shared library). Android calls the HAL interface; the HAL library talks to the hardware-specific drivers. Your code never sees any of this.

```
Your app calls: locationManager.getLastKnownLocation()
     ↓ (Binder IPC)
LocationManagerService (system process)
     ↓ (JNI)
Native GPS library
     ↓ (HAL interface)
Vendor GPS HAL implementation (.so)
     ↓ (kernel driver)
GPS hardware chip
```

### Layer 3: ART and Native Libraries

**ART (Android Runtime)** is the virtual machine that executes your Kotlin/Java code. It takes `.dex` (Dalvik Executable) bytecode and either interprets it, JIT-compiles it, or runs a pre-compiled `.odex`/`.oat` native image. We cover ART in detail in A0.3.

**Bionic libc:** Android does NOT use glibc (the standard GNU C library used on Linux desktops). It uses Bionic — a custom C library written from scratch for mobile. Bionic is smaller, faster to load, and tuned for constrained memory. When your code calls C standard library functions via JNI or native code, it's calling Bionic.

**SQLite:** The entire SQLite database engine is bundled in Android. Room (Android's ORM) is a compile-time-verified wrapper over this same SQLite.

**OpenGL ES / Vulkan:** The GPU rendering libraries. When Jetpack Compose or the View system draws to the screen, it ultimately calls OpenGL ES or Vulkan to issue GPU commands.

### Layer 4: Java Framework API — The SDK You Write Against

This is the layer you interact with daily. It is implemented as a set of Java/Kotlin classes that run partially in your app process and partially in system_server (Android's core system process). When you call `getSystemService()`, you get a local proxy object that transparently makes Binder IPC calls to the corresponding service running in `system_server`.

Key system services running inside `system_server`:
- `ActivityManagerService` (AMS): manages Activities, processes, tasks, back stack
- `WindowManagerService` (WMS): manages windows, surfaces, input dispatch
- `PackageManagerService` (PMS): manages installed apps, APK parsing, permissions
- `NotificationManagerService`: manages the notification shade
- `AlarmManagerService`: manages scheduled alarms

### The App Sandbox: Every App Is a Linux User

This is the security model in concrete terms:

```
App A (com.bank.app):
  Linux UID: 10023
  Process: /proc/PID_A
  Data dir: /data/data/com.bank.app/ (owned by uid 10023)
  Memory: isolated (separate address space)

App B (com.attacker.app):
  Linux UID: 10087
  Process: /proc/PID_B
  Data dir: /data/data/com.attacker.app/ (owned by uid 10087)
  Memory: isolated (separate address space)

→ App B CANNOT read App A's /data/data directory (kernel file permission denied)
→ App B CANNOT access App A's heap (separate process address spaces)
→ App B CANNOT call App A's methods directly (different process)
```

The only official cross-app communication mechanisms are: Intents (via AMS), Content Providers (via Binder), and AIDL services (via Binder). All of them go through the kernel's Binder driver.

### Memory Trick

```
LAYERS (bottom to top): Linux → HAL → ART+Native → Framework → Apps
"Laughing Hares Always Fight Angrily"

SANDBOX = per-app Linux UID
  App A (UID 10023) CANNOT read App B (UID 10087) — kernel enforces it.
  Cross-app talk: Intents / ContentProvider / AIDL → all via Binder.

SYSTEM_SERVER runs: AMS, WMS, PMS, NotificationManager, AlarmManager
  All system services → started by system_server at boot.
```

---

## A0.2 — Zygote & App Startup

> **Builds on:** [A0.1 — Android System Stack](A0_android_platform.md#a01--the-android-system-stack)
> **Connects to:** [A0.3 — ART](A0_android_platform.md#a03--art--dalvik--dex-compilation) · [A1.1 — Activity Lifecycle](A1_activity_fragment.md#a11--activity-lifecycle)

### The Concrete Picture

Starting point: device just booted. User taps your app icon.

```
Boot complete → Zygote (PID ~500) is already waiting
  Zygote has pre-loaded: android.app.*, android.view.*, java.lang.* (~50MB)

User taps icon
    ──► Launcher.startActivity(intent)
    ──► Binder IPC ──► ActivityManagerService (in system_server)
    ──► AMS: "no process for com.myapp" ──► sends fork request to Zygote

Zygote.fork()                       ← FAST: copy-on-write, no re-loading of framework classes
    │
    ▼
New child process (com.myapp, UID 10023)
    │  Inherits Zygote's pre-loaded classes (shared read-only pages)
    │  Gets its own heap, stack, DEX-loaded app code
    ▼
ActivityThread.main()
    ├── Looper.prepareMainLooper()   ← creates the main event loop
    ├── thread.attach(...)           ← registers this process with AMS via Binder
    └── Looper.loop()               ← blocks forever, dispatching Messages

AMS sends "launch Activity" ──► Binder ──► Binder thread ──► Handler msg ──► Activity.onCreate()
```

Cold start time = fork + Application.onCreate() + Activity.onCreate() + first frame render.

### WHY This Matters

App startup time is one of the most critical performance metrics on Android. A cold start that takes 3 seconds is the difference between a 5-star app and user churn. Understanding how Zygote works tells you exactly which parts of startup are fixed overhead (unavoidable) and which parts are your app's responsibility to optimize. It also explains why the first frame of your Activity appears when it does.

### The Boot Sequence

When an Android device boots, here is what actually happens:

```
1. Bootloader
   ↓
2. Linux Kernel starts, mounts file systems
   ↓
3. init (PID 1) — Android's init process, reads /init.rc
   ↓
4. init forks:
   ├─ Zygote (PID ~500)                ← will be parent of every app process
   ├─ system_server fork from Zygote   ← all Android system services
   ├─ surfaceflinger                   ← manages the display
   ├─ mediaserver                      ← audio/video services
   └─ ... other native daemons
   ↓
5. Zygote starts ART, loads framework classes
   ↓
6. Zygote forks system_server
   ↓
7. system_server starts all Java framework services (AMS, WMS, PMS, ...)
   ↓
8. AMS tells system_server to start the Launcher app
   ↓
9. Home screen is visible → device is "booted"
```

### Zygote: The App Incubator

Zygote (Greek: "joined egg") is the most important process in Android's performance story. Its job is to be the pre-warmed parent of every app process.

**The problem Zygote solves:** Starting a new Java VM from scratch for every app launch would take 1-3 seconds just to initialize ART and load framework classes. That's unacceptable for app launch.

**Zygote's solution:** At boot time, Zygote:
1. Starts ART
2. Loads and initializes ALL Android framework classes into memory (all of `android.app.*`, `android.view.*`, `android.content.*`, `java.lang.*`, etc.)
3. Pre-warms resource caches (drawables, layouts from framework)
4. Then **waits**, listening on a Unix socket for fork requests

When you tap an app icon:

```
User taps app icon
     ↓
Launcher calls startActivity(intent)
     ↓ (Binder IPC)
ActivityManagerService (in system_server)
     ↓ (checks: does a process for this app exist?)
     NO → AMS sends fork request to Zygote over Unix socket
     ↓
Zygote forks itself (fork() system call)
     ↓
New child process (your app's process)
  - Inherits ALL of Zygote's pre-loaded classes and memory pages
  - Gets a new Linux UID (your app's UID)
  - Copy-on-write: shares read-only pages with Zygote until written
     ↓
Child process calls ActivityThread.main()
     ↓
Looper.prepareMainLooper()
Application.onCreate()
Activity.onCreate() → setContentView() → first frame rendered
```

**Why fork() is fast:** The Linux `fork()` system call creates a new process that is an exact copy of the parent, but uses **copy-on-write (COW)** memory pages. The child process doesn't physically copy Zygote's memory — it shares the same physical memory pages until it writes to them. Since all of Zygote's loaded classes are read-only (the child never modifies `android.app.Activity`'s class code), those pages are permanently shared. The child process gets access to ~50MB of pre-loaded framework classes essentially for free.

```
Physical Memory
┌─────────────────────────────────────────────────────────────┐
│ Framework classes (android.*, java.*)                        │
│ [android.app.Activity bytecode, ART metadata, ...]          │
│                                                              │
│ ← These pages are READ-ONLY → shared by ALL app processes   │
└─────────────────────────────────────────────────────────────┘
       ▲                    ▲                    ▲
       │                    │                    │
   Zygote             App A process         App B process
 (parent)              (fork of Zygote)      (fork of Zygote)

Each app process also has its OWN private memory:
  - App's own DEX code
  - App's heap (objects, bitmaps, etc.)
  - App's stack
```

### The Three Types of App Start

```
COLD START (slowest — process does not exist):
  Process creation (fork from Zygote)
  + Application.onCreate()
  + Activity.onCreate() / setContentView()
  + First frame draw
  Total: ~300ms – 3s+ depending on your code

WARM START (medium — process exists, Activity doesn't):
  No process creation (Zygote fork skipped)
  + Activity.onCreate() (Activity was destroyed, e.g., killed under memory pressure)
  Total: ~100ms – 800ms

HOT START (fastest — process + Activity exist):
  No process creation
  No Application.onCreate()
  Activity.onStart() / onResume() only (Activity in back stack, brought to foreground)
  Total: ~50ms – 200ms
```

**The Time-to-First-Frame (TTFF) breakdown for cold start:**

```
0ms          100ms         200ms          300ms+
 │────────────│─────────────│──────────────│───────────►

 [fork+ART init]
              [App.onCreate()]
                            [Activity.onCreate() + layout]
                                           [first draw]

Your code contributes to everything after the fork.
Heavy Application.onCreate() directly delays the first frame.
```

### What ActivityThread.main() Does

`ActivityThread` is the entry point the forked process calls after Zygote fork:

```java
// Simplified ActivityThread.main():
public static void main(String[] args) {
    // 1. Prepare the main Looper (the event loop for the main thread)
    Looper.prepareMainLooper();

    // 2. Create the ActivityThread instance
    ActivityThread thread = new ActivityThread();

    // 3. Attach to the system (introduces this process to ActivityManagerService via Binder)
    thread.attach(false, startSeq);
    // → AMS now knows this app process exists
    // → AMS sends "launch this Activity" message back to this process

    // 4. Start the main event loop — blocks forever
    Looper.loop();
    // This never returns under normal operation.
    // Every UI event, every Activity lifecycle callback, every View drawing
    // is dispatched from this Looper.
}
```

Everything in your app — every touch event, every lifecycle callback, every layout pass — is a `Message` dispatched by this single `Looper.loop()`.

### Memory Trick

```
COLD vs WARM vs HOT START:
  Cold = fork + Application.onCreate + Activity.onCreate   (300ms–3s)
  Warm = no fork, just Activity.onCreate                   (100ms–800ms)
  Hot  = no fork, no onCreate, just onStart+onResume       (50ms–200ms)

ZYGOTE trick: Copy-on-Write means all apps share the same physical
  pages for android.app.* bytecode. You get ~50MB free per app.

ENTRY POINT: ActivityThread.main()
  1. prepareMainLooper  2. attach (registers with AMS)  3. Looper.loop()
```

---

## A0.3 — ART, Dalvik & DEX Compilation

> **Builds on:** [A0.2 — Zygote & App Startup](A0_android_platform.md#a02--zygote--app-startup)
> **Connects to:** [J0.4 — JVM Bytecode](../../Java/Questions/J0_jvm_mental_model.md#j04--java-bytecode-basics)

### The Concrete Picture

Starting point: you run `./gradlew assembleRelease`. Follow the code:

```
YourActivity.kt  (Kotlin source)
    │ kotlinc
    ▼
YourActivity.class  (JVM .class bytecode — stack-based, one file per class)
    │ D8/R8 compiler (part of Android Gradle Plugin)
    ▼
classes.dex  (Dalvik Executable — register-based, ONE shared constant pool)
    │ zipped with resources → APK
    ▼
Install on device (Android 7+):
  Step 1: dex2oat VERIFIES bytecode → writes .vdex (fast)
  Step 2: First few runs → ART INTERPRETS dex, JIT compiles hot methods
  Step 3: JIT records profile → primary.prof saved to disk
  Step 4: Device idle + charging → dex2oat AOT-compiles hot methods → .odex
  Step 5: Next launch → hot path runs as pre-compiled native code (fast)

R8 sits at the D8/R8 step:
  Shrink (remove unused methods) → Optimize (inline) → Obfuscate (rename)
```

This is why a freshly-installed app feels slower than one you use daily —
the profile-guided AOT hasn't run yet.

### WHY This Matters

Your Kotlin code compiles to `.class` files, which are then translated to `.dex` bytecode, which ART either interprets or compiles to native machine code. ART's compilation strategy directly affects app startup speed, runtime performance, storage usage, and install time. ProGuard/R8 optimization, multidex, and startup performance tuning all require understanding what ART actually does with your code.

### From Source to Execution: The Full Pipeline

```
YourCode.kt  (Kotlin source)
     │
     ▼ kotlinc
YourCode.class  (JVM bytecode — .class files)
     │
     ▼ D8 / R8 (Android's dex compiler, part of AGP)
classes.dex  (Dalvik Executable — compact bytecode for Android)
     │
     ▼ packaged into
app-release.apk  (zip file containing classes.dex, resources.arsc, assets, manifest)
     │
     ▼ installed on device
ART compiles / profiles / caches
     │
     ├─► .odex / .oat file  (pre-compiled native code — AOT)
     └─► .vdex file         (verified DEX — skip re-verification at runtime)
     │
     ▼ at runtime
Machine code executes on CPU
```

### DEX Format: Why Not Just Use .class Files?

JVM `.class` files are designed for desktop machines with plentiful RAM and disk space. Each `.class` file is independent, with its own constant pool (string/type tables). A large app has thousands of `.class` files.

DEX (Dalvik Executable) was designed for resource-constrained mobile devices:

- **One constant pool per DEX:** All 10,000 of your classes share a single string table, type table, and method table. This reduces redundancy dramatically.
- **Register-based VM:** Dalvik/ART is register-based (like real CPUs), not stack-based like the JVM. Fewer instructions are needed to perform the same computation (registers eliminate push/pop overhead).
- **Smaller file size:** DEX files are typically 30-50% smaller than the equivalent set of `.class` files.

**The 65,535 method reference limit:**

A DEX file's method table is indexed by a 16-bit unsigned integer, which allows at most 65,535 (2^16 - 1) method references per DEX file. If your app (including all libraries) references more than 65,535 methods, you exceed the single-DEX limit.

**Multidex** splits your app into `classes.dex`, `classes2.dex`, `classes3.dex`, etc. On Android 5.0+ (ART), multiple DEX files are natively supported. On older Dalvik devices, the `multidex` support library manually loads secondary DEX files. R8's shrinking (removing unused code) often eliminates the need for multidex by removing enough library code to fit in one DEX.

### Dalvik vs ART: The Evolution

**Dalvik** (Android 1.0 – 4.3, with ART experimental in 4.4):
- Interpreter + JIT compiler
- JIT: identifies hot methods at runtime, compiles them to native on the fly
- Each app launch: re-JIT everything (hot methods re-profiled each boot)
- Startup: fast (no pre-compilation), runtime: slower (interpreted/JIT code)

**ART** (Android 5.0+ as default):

Android 5.0-6.x — **Pure AOT**:
- At install time: `dex2oat` compiled EVERYTHING to native `.oat` files
- Startup: very fast (native code ready immediately)
- Install: very slow (compiling everything at install: 30-120 seconds for large apps)
- Storage: very large `.oat` files

Android 7.0+ — **Hybrid: JIT + AOT + Profile-Guided Compilation** (the current model):

```
Install time:
  Only VERIFY DEX (check bytecode for correctness) → store .vdex
  No heavy compilation. Install is fast again.
  ↓

First few runs (JIT phase):
  ART interprets DEX bytecode
  JIT compiler watches: which methods are called frequently?
  JIT compiles hot methods to native on the fly (just like Dalvik)
  JIT records profile: which classes/methods are "hot"
  Profile saved to /data/misc/profiles/cur/0/<package>/primary.prof
  ↓

Background compilation (AOT phase — happens when device is idle + charging):
  dex2oat reads profile → compiles ONLY the hot methods/classes to .odex
  Next app startup: hot path is pre-compiled native code → much faster startup
  Cold methods remain interpreted/JIT-compiled on demand
```

```
Performance over time with hybrid compilation:

Launch 1: [slow - mostly interpreted         ]
Launch 2: [medium - JIT warmed               ]
Launch 3: [medium - JIT warmed               ]
...device idles + charges → background AOT compilation...
Launch 5: [fast - hot path pre-compiled      ]
Launch 6: [fast                              ]
```

This is why an app that you use regularly feels faster than one you just installed — the profile-guided AOT compilation has had time to optimize your specific usage pattern.

### R8 and ProGuard: What They Actually Do

**R8** (Google's replacement for ProGuard) is a combined shrinker + optimizer + obfuscator:

1. **Shrinking:** Remove unused classes, methods, and fields (dead code elimination). A typical library adds 10,000+ methods, but you use 500 — R8 removes the other 9,500. This is the primary way to stay under the 65,535 method limit.

2. **Optimization:** Inline short methods, remove null checks that can be proven unnecessary, replace interface calls with direct calls when the receiver type is known.

3. **Obfuscation:** Rename `com.myapp.auth.UserAuthenticationManager` → `a.b.c`. Reduces file size; makes reverse engineering harder.

4. **Repackaging:** Moves all classes to a single package (further reduces method/type table size).

R8 operates on DEX level (not Java bytecode level), which gives it visibility into the entire app including libraries.

### Memory Trick

```
PIPELINE: .kt → .class → .dex → .odex/.oat
  "Kotlin Classes Dare Outperform"

DEX vs CLASS:
  DEX = register-based (like real CPU), 1 shared constant pool, ~50% smaller
  CLASS = stack-based, per-class constant pool (verbose)

65,535 METHOD LIMIT: DEX method table = 16-bit index → max 65535 refs
  Fix: multidex (classes.dex + classes2.dex) OR R8 shrinking

ANDROID 7+ HYBRID MODEL: Install fast → JIT warms up → AOT at idle
  Profile = /data/misc/profiles/cur/0/<pkg>/primary.prof
  App gets faster over time as AOT covers more hot paths
```

---

## A0.4 — Binder IPC

> **Builds on:** [A0.1 — Android System Stack](A0_android_platform.md#a01--the-android-system-stack)
> **Connects to:** [A1.1 — Activity Lifecycle](A1_activity_fragment.md#a11--activity-lifecycle) · [A2.1 — Handler & Looper](A2_main_thread_and_views.md#a21--looper-messagequeue--handler)

### The Concrete Picture

Starting point: your app calls `startActivity(intent)`. Watch what actually happens:

```
Your app process (UID 10023)                system_server (UID 1000)
────────────────────────────                ──────────────────────────────
ActivityManager proxy object
proxy.startActivity(intent)
    │
    │ Parcel.writeToParcel(intent)  ←─── intent must be Parcelable!
    │ ioctl(/dev/binder, BC_TRANSACTION, data=parcel)
    │                               ──────────────────────────────►
    │                               Binder kernel driver copies parcel
    │                               (1 copy: sender addr → receiver addr)
    │                                        ──────────────────────►
    │ [main thread BLOCKS here]            ActivityManagerService.startActivity()
    │                                      checks permissions, resolves Activity
    │                               ◄──────────────────────────────
    │                               BC_REPLY with result
    ▼
[main thread unblocks, receives result]

Now AMS needs to call onResume() on YOUR Activity:
  AMS ──► Binder ──► your app's Binder thread pool
  ──► ApplicationThread.scheduleResumeActivity()  (runs on Binder thread)
  ──► Handler.sendMessage(H.RESUME_ACTIVITY)       (posts to main Looper)
  ──► Activity.onResume()                          (runs on main thread)
```

Every lifecycle callback follows this exact path: AMS → Binder → Binder thread → Handler → main thread.

### WHY This Matters

Every single Android API call that touches system services — `startActivity()`, `getSystemService()`, accessing the camera, sending a broadcast, binding a service — crosses a process boundary. The mechanism is Binder. Without understanding Binder, you cannot reason about:
- Why certain API calls have non-trivial latency even when "synchronous"
- Why you must not call Binder-backed APIs on the main thread when the system is under load
- Why AIDL exists and what it generates
- How Android's permission system is enforced across processes

### The Problem: Cross-Process Calls

In a single process, calling a method is just a function call — push args to stack, jump to address, return. Across processes, there is no shared memory, no shared stack. Process A cannot simply call a function in Process B.

Linux provides several IPC mechanisms: pipes, sockets, shared memory, signals. Android needed something different: a typed, object-oriented RPC (Remote Procedure Call) system that could:
1. Pass complex typed objects (not just raw bytes)
2. Handle thread management automatically on both sides
3. Be as fast as possible (called thousands of times per second in the framework)
4. Work with Android's permission system

The solution: **Binder**.

### How Binder Works

Binder is implemented as a Linux kernel driver (`/dev/binder`). It provides a single system call interface that enables two processes to share data through the kernel — without copying data through userspace buffers. Binder uses a single-copy mechanism: data is copied from the sender's address space directly into the receiver's address space using kernel page mapping tricks (one copy, vs two copies for traditional IPC).

```
Process A (your app)                   Kernel                System_server (AMS)
─────────────────────                  ──────                ─────────────────────
  Binder proxy object                  Binder                  Binder stub object
  (IActivityManager stub)              kernel                  (ActivityManagerService)
                                       driver
  proxy.startActivity(intent)
         │
         │ ioctl(/dev/binder,         ◄───── kernel copies
         │  BC_TRANSACTION,           ─────► parcel data into
         │  data=intent_parcel)              AMS memory space
         │
         │ [thread blocks waiting]          AMS.startActivity(intent)
         │                                  [processes the call]
         │                                  [sends BC_REPLY]
         │
         ▼
   [thread unblocks]
   [receives result]
```

**Parcel:** The data format for Binder transactions. A `Parcel` is a flattened binary representation of data. When you pass an `Intent` across a process boundary, the Intent is `writeToParcel()`-ed into a Parcel, transmitted through Binder, and `readFromParcel()`-ed on the other side. This is why `Intent` extras must be `Parcelable` or `Serializable` — they must survive flattening.

### The Binder Thread Pool

Every process that uses Binder has a thread pool dedicated to handling incoming Binder calls:

```
Your app process:
  Main thread (UI thread)
  Binder thread 1 ← handles incoming Binder calls from system_server
  Binder thread 2 ← handles incoming Binder calls from other processes
  Binder thread 3
  (up to 16 Binder threads by default)
```

When `system_server` needs to tell your app that a lifecycle event has happened (e.g., the screen turned off → call `onPause()`), it makes a Binder call INTO your process. One of your Binder threads receives it, then posts a `Message` to your main `Handler` (Looper), which dispatches `Activity.onPause()` on the main thread.

This is the actual path for every lifecycle callback:

```
System event (screen off)
     ↓ (system_server → Binder → your app's Binder thread)
ApplicationThread.handlePauseActivity()  ← runs on Binder thread
     ↓ (posts Message to main Looper)
ActivityThread: H.PAUSE_ACTIVITY message received by main thread Looper
     ↓
Activity.onPause()  ← runs on main thread
```

`ApplicationThread` is a Binder stub object inside your process that AMS holds a reference to. Every time AMS needs to drive your Activity lifecycle, it calls methods on `ApplicationThread` through Binder.

### AIDL: Defining a Binder Interface

When you define your own cross-process service, AIDL (Android Interface Definition Language) generates the Binder proxy/stub boilerplate:

```java
// IMyService.aidl — you write this
interface IMyService {
    int addNumbers(int a, int b);
    void processData(in ParcelableData data);
}
```

AIDL generates two classes:
- **`IMyService.Stub`** (server side): extends `Binder`, receives transactions, dispatches to your implementation
- **`IMyService.Stub.Proxy`** (client side): holds a `IBinder` reference, marshals args into a Parcel, sends via `transact()`

```java
// Generated (simplified):
public interface IMyService extends android.os.IInterface {

    // Server-side: extend this and implement the methods
    abstract class Stub extends android.os.Binder implements IMyService {
        @Override
        public boolean onTransact(int code, Parcel data, Parcel reply, int flags) {
            switch (code) {
                case TRANSACTION_addNumbers:
                    int a = data.readInt();
                    int b = data.readInt();
                    int result = addNumbers(a, b);      // calls your implementation
                    reply.writeInt(result);
                    return true;
            }
        }
    }

    // Client-side: call methods on this
    class Proxy implements IMyService {
        private IBinder mRemote;
        @Override
        public int addNumbers(int a, int b) {
            Parcel data = Parcel.obtain();
            Parcel reply = Parcel.obtain();
            data.writeInt(a);
            data.writeInt(b);
            mRemote.transact(TRANSACTION_addNumbers, data, reply, 0); // crosses process boundary
            return reply.readInt();
        }
    }
}
```

### ServiceManager: The Binder Registry

How does your app find the system service's Binder object in the first place? Every system service registers itself with `ServiceManager` at startup:

```
Boot time:
  ActivityManagerService.main() → ServiceManager.addService("activity", this)
  WindowManagerService.main()   → ServiceManager.addService("window", this)
  PackageManagerService.main()  → ServiceManager.addService("package", this)
  ...

At runtime (your code):
  ActivityManager am = (ActivityManager) context.getSystemService(Context.ACTIVITY_SERVICE);
  // internally:
  //   IBinder binder = ServiceManager.getService("activity");
  //   return IActivityManager.Stub.asProxy(binder);   ← gives you the Binder proxy
```

`ServiceManager` itself is accessible at a well-known Binder handle (handle 0), so the first lookup is always possible.

### Interview Trap: Binder Overhead and the Main Thread

Binder transactions crossing process boundaries are NOT free. A typical Binder call takes 10-100 microseconds of overhead (kernel entry/exit, data copy, thread wakeup). Calling Binder-backed APIs in a tight loop on the main thread can cause jank.

The most important rule: **never call Binder APIs that could block on the main thread.** The system is especially careful about calls that wait for `system_server` to respond, because `system_server` can be slow under memory pressure. This is why `PackageManager.getInstalledPackages()` (a Binder call) is off-limits on the main thread in strict mode — it can take hundreds of milliseconds.

### Memory Trick

```
BINDER = kernel driver (/dev/binder), SINGLE-COPY data transfer
  Data: serialized into Parcel → kernel copies to receiver → deserialized
  Why Parcelable: Intent/extras must survive this Parcel round-trip

LIFECYCLE PATH (always):
  AMS ──► Binder ──► ApplicationThread (Binder thread) ──► Handler ──► main thread

AIDL generates: Stub (server side) + Stub.Proxy (client side)
THREAD POOL: up to 16 Binder threads per process (incoming calls)
SERVICEMANAGER: Binder registry — like DNS for Binder objects (handle 0)

TRAP: Binder calls = 10–100μs. PackageManager.getInstalledPackages()
  on main thread → hundreds of ms → ANR. StrictMode catches this.
```

---

## Master Summary

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                A0 — Android Platform Architecture                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  1. ANDROID SYSTEM STACK (5 layers)                                         │
│     Linux kernel: process isolation (per-app UID), OOM killer, Binder      │
│     HAL: vendor hardware abstraction (camera, GPS, audio)                  │
│     ART + Native: DEX execution, OpenGL ES, Bionic libc, SQLite            │
│     Java Framework: ActivityManager, WindowManager, PackageManager...       │
│     Apps: separate Linux processes, each isolated by UID                   │
│                                                                             │
│  2. ZYGOTE & APP STARTUP                                                    │
│     Zygote pre-loads ALL framework classes at boot, then waits             │
│     New app = fork() from Zygote → inherits classes via copy-on-write      │
│     fork() is fast; COW means all apps share the same physical pages for   │
│     read-only framework code (~50MB free per process)                      │
│     Cold start: fork + Application.onCreate() + Activity.onCreate()        │
│     Warm: no fork, just Activity. Hot: no fork, no Application.onCreate()  │
│     ActivityThread.main() → Looper.prepareMainLooper() → Looper.loop()    │
│     Every lifecycle callback is a Binder call → Handler message → main    │
│                                                                             │
│  3. ART & DEX                                                               │
│     .kt → .class → .dex (D8/R8) → .odex/.oat (AOT by dex2oat)           │
│     DEX: register-based, single constant pool, ~50% smaller than .class    │
│     65,535 method limit per DEX → multidex for large apps                 │
│     Android 7+: hybrid JIT+AOT. Interpret → JIT profile → background AOT  │
│     Profile-guided: only HOT methods get AOT. Apps get faster over time.  │
│     R8: shrink (remove dead code) + optimize (inline) + obfuscate         │
│                                                                             │
│  4. BINDER IPC                                                              │
│     Kernel driver (/dev/binder). Single-copy data transfer.                │
│     Every system API call (startActivity, getSystemService) = Binder RPC  │
│     Parcel: binary format for cross-process data (why extras are Parcelable│
│     Binder thread pool: each process has up to 16 threads for incoming IPC │
│     AMS → Binder → ApplicationThread → Handler → main thread → lifecycle  │
│     AIDL: generates Stub (server) + Proxy (client) for your own services   │
│     ServiceManager: Binder service registry (like DNS for Binder objects)  │
│     TRAP: Binder calls are 10-100μs. Don't call blocking Binder on main   │
│     thread (getInstalledPackages, large IPC). StrictMode detects this.    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

*[Phase A1 — Activity & Fragment →](A1_activity_fragment.md)*
