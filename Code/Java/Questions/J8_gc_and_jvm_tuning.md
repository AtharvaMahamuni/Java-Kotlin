# Phase J8 — Garbage Collection & JVM Tuning

Garbage collection is the most-asked JVM internals topic in senior Java interviews. "Explain G1GC", "how do you tune GC pause times", "what caused this OOM" — these appear in virtually every systems-focused Java interview. GC is also the reason Java's promise of memory safety holds: you never free memory manually, yet the JVM reclaims it correctly. This phase closes the loop that began in J0: you now understand the heap, the object header, and JVM internals well enough to reason about why the garbage collector is designed the way it is, which algorithm to choose, and how to diagnose production failures.

---

## J8.1 — Generational GC & Heap Anatomy

> **Builds on:** [J0.1 — Primitives vs References](J0_jvm_mental_model.md#j01--primitives-vs-references-in-java)
> **Connects to:** [J8.2 — GC Algorithms](J8_gc_and_jvm_tuning.md#j82--gc-algorithms-from-serial-to-zgc)

### WHY This Matters

Before you can tune GC, you need to know what the JVM is managing. The generational hypothesis — the empirical observation that most objects die young — is the foundation of nearly every mainstream GC algorithm. Violating this hypothesis (keeping many long-lived objects in your application) is the root cause of most GC performance problems.

### The Weak Generational Hypothesis

The JVM's allocation model is based on a key empirical observation about Java programs:

```
Object Lifetime Distribution in Typical Java Programs:
                        ▲
                        │
              ██████    │
              ██████    │
              ██████    │
              ██████    │    ██
              ██████    │    ██          ██
─────────────────────────────────────────────►
              young     │    middle     old
              (bytes)        aged       (tenured)

~80-95% of objects die before their first GC.
Very few objects survive long enough to be "old".
```

This is the **weak generational hypothesis**: most objects are short-lived. The insight has a key implication — you can collect the young generation frequently and cheaply (most of it is garbage by the time you collect it), and collect the old generation rarely (it changes slowly). This is dramatically more efficient than tracing the entire heap every time.

### Heap Layout: Young Gen → Old Gen → Metaspace

The classic heap layout (Serial, Parallel, G1GC all start here conceptually):

```
JVM Heap (example: -Xmx4g)
┌──────────────────────────────────────────────────────────────┐
│                      Young Generation (~1/3 of heap)         │
│  ┌─────────────────┐  ┌──────────────┐  ┌──────────────┐   │
│  │  Eden Space     │  │ Survivor 0   │  │ Survivor 1   │   │
│  │  (new objects   │  │ (S0 / from)  │  │ (S1 / to)    │   │
│  │   land here)    │  │              │  │              │   │
│  └─────────────────┘  └──────────────┘  └──────────────┘   │
│          ~80% of young gen              ~10%       ~10%      │
├──────────────────────────────────────────────────────────────┤
│                      Old Generation (~2/3 of heap)            │
│              (long-lived objects promoted here)               │
│                                                              │
└──────────────────────────────────────────────────────────────┘

Outside heap (not controlled by -Xmx):
┌─────────────────────────────────────────────────────────────┐
│  Metaspace (Java 8+, replaces PermGen)                      │
│  Class metadata, method bytecode, static fields             │
│  Bounded by: -XX:MaxMetaspaceSize (default: unlimited)      │
└─────────────────────────────────────────────────────────────┘
```

### GC Roots: Where Tracing Begins

The GC cannot simply scan all objects — it must start from a known live set called **GC roots**: objects that are definitionally alive. Everything reachable from a GC root is kept; everything else is garbage.

GC roots include:
- **Stack frames**: every local variable and method parameter in every active stack frame on every thread
- **Static fields**: fields of classes currently loaded in the JVM
- **JNI references**: objects held by native code via JNI (Java Native Interface)
- **Thread objects**: the `Thread` objects of all living threads
- **Class loaders**: the class loader objects themselves (keeping loaded classes alive)
- **JVM internal references**: interned strings, exception objects cached by the JVM, etc.

```
GC Root Tracing (mark phase):

  Stack Frame     Static Fields    JNI
  ┌───────┐       ┌──────────┐    ┌─────┐
  │ ref A │       │ ref B    │    │ ref │
  └───┬───┘       └────┬─────┘    └──┬──┘
      │                │             │
      ▼                ▼             ▼
   Object A         Object B      Object C
      │                │
      ▼                ▼
   Object D         Object E ──► Object F
      │
      ▼
   Object G         Object H ← NO root → GARBAGE

All reachable objects (A, B, C, D, E, F, G) are MARKED as live.
Unreachable objects (H) are GARBAGE — eligible for collection.
```

### Mark → Sweep → Compact: The Three Phases

Every GC algorithm is a variation of three fundamental phases:

**Phase 1: Mark** — start from GC roots, trace all reachable objects, mark them as live. Uses a work list (gray set) and processes objects until all reachable objects are marked.

**Phase 2: Sweep** — scan the heap, reclaim memory of all unmarked objects. Free list or bump-pointer reset, depending on algorithm.

**Phase 3: Compact (optional)** — move surviving objects to pack them into contiguous memory. Eliminates fragmentation. Requires updating all references to moved objects (expensive).

```
Heap before GC:
[ Live │ Garbage │ Live │ Live │ Garbage │ Garbage │ Live ]

After Mark + Sweep (no compact — fragmented):
[ Live │  FREE   │ Live │ Live │  FREE   │  FREE   │ Live ]
  ^holes remain — new allocations must fit into gaps

After Mark + Sweep + Compact (no fragmentation):
[ Live │ Live │ Live │ Live │         FREE                ]
  ^all live objects packed at one end — new allocs are fast (bump pointer)
```

Compaction makes future allocations cheap (just advance a pointer) but the compaction pass itself is expensive — every live object must be moved and every reference to it updated. This pause is where G1GC and ZGC focus their engineering efforts.

### Minor GC, Major GC, Full GC

These terms are frequently confused:

| Term | What It Means |
|------|--------------|
| **Minor GC** | Collects the Young Generation only. Usually fast (milliseconds). Objects that survive are promoted to Old Gen or kept in survivor space. |
| **Major GC** | Collects the Old Generation. Slower — old gen is larger. Often triggered when old gen fills up. |
| **Full GC** | Collects the entire heap (Young + Old + Metaspace). Stop-the-world. Triggered by explicit `System.gc()`, `OutOfMemoryError` attempts, or when other GCs cannot free enough memory. |

> **Interview trap:** "Major GC" and "Full GC" are often used interchangeably but they are not the same. A major GC may collect just the old gen; a full GC collects everything. G1GC's mixed collections are also sometimes called "major" but are not full GCs.

### Object Promotion: Survivor Spaces and Tenuring

When a Minor GC fires, Eden is collected. Surviving objects are copied to the active Survivor space (S0 or S1):

```
Minor GC process:

1. Eden fills up → Minor GC triggered
2. GC traces from roots into Eden + active Survivor space
3. Live objects in Eden → copied to empty Survivor space (S1 if S0 was active)
4. Live objects in S0 (previously surviving) → their age counter incremented
5. Objects whose age >= tenuring threshold → promoted to Old Gen
6. Eden + old Survivor space (S0) → entirely cleared

Age counter (stored in object's mark word, 4 bits):
  age 0: survived 0 GCs (new in Eden)
  age 1: survived 1 Minor GC
  ...
  age N: promoted to Old Gen (default N = 15, set by -XX:MaxTenuringThreshold)
```

**Spatial diagram of a Minor GC cycle:**

```
BEFORE Minor GC (Eden full):
┌──────────────────────────────────────┬──────────────┬──────────────┬───────────────────┐
│             Eden                     │  Survivor S0 │  Survivor S1 │    Old Gen        │
│  [A,age0][B,age0][C,age0][D,age0]   │  [E,age2]    │   (empty)    │  [F][G][H]        │
│  [E,age0] ... (full — GC triggered) │  [I,age4]    │              │                   │
└──────────────────────────────────────┴──────────────┴──────────────┴───────────────────┘
  A,B,C,D,E = live objects   X = garbage (unreachable)   S0 = "from" space (active)

DURING Minor GC:
  GC traces GC roots → marks A, C, E (in Eden) as live; B, D are garbage
  GC traces S0 → marks E (in S0) as live; increments ages

        A(age0)──────────────────────────────────────────────► S1 (age becomes 1)
        C(age0)──────────────────────────────────────────────► S1 (age becomes 1)
        E(age0)──────────────────────────────────────────────► S1 (age becomes 1)
        E(age2) in S0──────────────────────────────────────► S1 (age becomes 3)
        I(age4) in S0  (age 4 >= threshold? if threshold=4)──► Old Gen (PROMOTED)

AFTER Minor GC:
┌──────────────────────────────────────┬──────────────┬──────────────┬───────────────────┐
│             Eden                     │  Survivor S0 │  Survivor S1 │    Old Gen        │
│   (completely empty — zero frag.)    │  (cleared)   │  [A,age1]    │  [F][G][H][I]     │
│                                      │              │  [C,age1]    │       ▲ promoted  │
│                                      │              │  [E,age1]    │                   │
│                                      │              │  [E,age3]    │                   │
└──────────────────────────────────────┴──────────────┴──────────────┴───────────────────┘
  Next cycle: S1 becomes the "from" space; S0 becomes the empty "to" space
```

Key: Eden + S0 are ENTIRELY freed — no fragmentation. The "to" space (S1) now becomes the active Survivor space for the next cycle. The roles of S0 and S1 flip every Minor GC.

This copy-based collection means Eden and the "from" Survivor space are completely freed with zero fragmentation — the cost is proportional to the number of *live* objects (not garbage), which is small in the young generation.

---

## J8.2 — GC Algorithms: From Serial to ZGC

> **Builds on:** [J8.1 — Generational GC & Heap Anatomy](J8_gc_and_jvm_tuning.md#j81--generational-gc--heap-anatomy)
> **Connects to:** [J8.3 — JVM Flags & GC Tuning](J8_gc_and_jvm_tuning.md#j83--jvm-flags--gc-tuning)

### WHY Multiple GC Algorithms Exist

No single GC algorithm is optimal for all workloads. The key tensions are:

- **Throughput vs latency**: minimising total CPU time spent in GC (throughput) conflicts with minimising individual pause lengths (latency)
- **Stop-the-world vs concurrent**: stopping all application threads during GC guarantees consistency but causes pauses; concurrent GC does work while the application runs but adds complexity and overhead
- **Compaction vs fragmentation**: compaction eliminates fragmentation but requires moving objects and updating references (a pause); not compacting leaves holes but avoids the cost

### Serial GC (`-XX:+UseSerialGC`)

Single-threaded, stop-the-world GC. The oldest and simplest algorithm.

```
Application threads: ██████████░░░░░░░░░░░░░████████████
GC thread:           (idle)    ██████████████(idle)

Pause: entire GC pause, single thread, all application work stops
```

Use case: single-core VMs, client applications, embedded systems, very small heaps (<100MB). Not appropriate for server workloads.

### Parallel GC (`-XX:+UseParallelGC`) — Default Before Java 9

Multi-threaded stop-the-world GC. Both the minor GC and major GC use multiple GC threads in parallel, reducing pause time compared to Serial GC. All application threads still stop.

```
Application threads: ██████████░░░░░░░░█████████████
GC threads (×N):     (idle)    ████████(idle)
                               ████████
                               ████████

Pause: shorter than Serial (N threads), but still stop-the-world
```

**When to use:** batch processing, analytics workloads where throughput matters and individual pause times are acceptable. Not appropriate for latency-sensitive services.

Key flag: `-XX:ParallelGCThreads=N` (defaults to number of CPU cores for heaps up to 8GB).

### G1GC (`-XX:+UseG1GC`) — Default Since Java 9

G1GC (Garbage-First) fundamentally restructures how the heap is divided:

**Region-based heap:** Instead of fixed young/old areas, G1GC divides the heap into approximately 2048 equal-sized **regions** (each 1–32 MB, power of 2). Each region is independently labeled Eden, Survivor, Old, or Humongous at any given time.

```
G1GC Heap (example: 32 regions shown, actual ~2048):

┌──┬──┬──┬──┬──┬──┬──┬──┐
│E │E │E │S │O │O │E │H │   E = Eden
├──┼──┼──┼──┼──┼──┼──┼──┤   S = Survivor
│O │O │. │E │E │H │O │O │   O = Old
├──┼──┼──┼──┼──┼──┼──┼──┤   H = Humongous
│E │O │O │. │O │E │E │O │   . = Free
├──┼──┼──┼──┼──┼──┼──┼──┤
│O │. │E │O │O │. │S │O │   Regions are flexible — a region's
└──┴──┴──┴──┴──┴──┴──┴──┘   role can change between GC cycles
```

**How G1GC collects:**

1. **Concurrent marking:** while the application runs, G1GC traces the heap and builds a picture of which regions have the most garbage (highest "garbage ratio")
2. **Young GC (minor):** stop-the-world, evacuates all Eden and Survivor regions; live objects copied to new Survivor or Old regions
3. **Mixed GC:** after a concurrent marking cycle, G1 also evacuates the Old regions with the highest garbage ratio alongside the Young GC — this is the "Garbage First" name: it prioritises the regions with the most garbage
4. **Full GC (fallback):** if G1 cannot keep up with allocation rate, falls back to a single-threaded (Java 8) or multi-threaded (Java 10+) full GC — this is the pause you want to avoid

**Humongous objects:** objects larger than half a region are classified as Humongous and allocated in contiguous regions. They are allocated directly in the Old gen and can cause fragmentation. Excessive humongous allocations are a common G1GC performance issue.

**Pause targets:** G1GC allows you to set a soft pause target: `-XX:MaxGCPauseMillis=200` (default 200ms). G1 dynamically adjusts region selection to try to stay within this budget. It is a *goal*, not a hard guarantee.

```
G1GC Collection Cycle:

      Concurrent         Young GC      Remark &      Mixed GC
      Mark Start         (STW)         Cleanup        (STW)
          │                │           (concurrent)     │
 ─────────▼────────────────▼───────────────────────────▼────────►
 App:  ████████████████░░░█████████████████████████░░░█████████
 GC:               ████████          ███████████        ████████
                   (concurrent                          (mixed:
                   marking)                             young+old)
```

### ZGC (`-XX:+UseZGC`) — Production Since Java 15

ZGC is designed for one goal: sub-millisecond GC pauses regardless of heap size. It has been tested on heaps up to 16 TB.

**Core technique:** ZGC performs marking, relocation, and remapping **concurrently** while the application runs. It uses **load barriers** — small code snippets inserted by the JIT at every heap reference load — to maintain consistency while objects are being moved.

```
ZGC Timeline:

 App:  ██████████████████████████████████████████████
 GC:   ███████████████████████████████████████████████
       (concurrent mark + relocate + remap — all concurrent)

 Pause:  │< 1ms │      │< 1ms │      │< 1ms │
         ^STW    ^STW   ^STW
         (roots) (remap (roots)
                 check)

ZGC STW pauses: only for root scanning — typically < 1ms
```

**Load barriers:** every time the application loads a reference from the heap, the JIT-inserted barrier checks a "colored pointer" (metadata embedded in the pointer bits) to see if the object has been relocated. If so, it transparently updates the reference. This is the key mechanism that allows ZGC to move objects without stopping the application.

**When to use ZGC:** latency-critical services where individual GC pauses > 1ms are unacceptable; very large heaps (>8 GB) where G1GC's predictable-pause guarantees become harder to meet; services with strict SLAs.

**Trade-off:** ZGC uses more CPU (the concurrent work and load barriers have overhead) and slightly more memory (colored pointers, mapping tables). It optimises for latency, not peak throughput.

### GC Algorithm Comparison

| Algorithm | Pause Type | Pause Length | Throughput | Best Use Case | Default Version |
|-----------|------------|--------------|------------|----------------|-----------------|
| Serial GC | Stop-the-world | High (single thread) | Low | Single-core, tiny heaps | Never default |
| Parallel GC | Stop-the-world | Medium (multi-thread) | Highest | Batch, analytics | Java 8 default |
| G1GC | Mostly STW (concurrent marking) | Predictable (configurable) | Good | General server apps | Java 9+ default |
| ZGC | Mostly concurrent | Sub-millisecond | Good (slightly lower) | Latency-critical, huge heaps | Java 15+ (production) |
| Shenandoah | Mostly concurrent | Sub-millisecond | Similar to ZGC | Same as ZGC (Red Hat JDK) | Not in Oracle JDK |

---

## J8.3 — JVM Flags & GC Tuning

> **Builds on:** [J8.2 — GC Algorithms](J8_gc_and_jvm_tuning.md#j82--gc-algorithms-from-serial-to-zgc)
> **Connects to:** [J8.4 — Memory Leaks, Heap Dumps & Profiling](J8_gc_and_jvm_tuning.md#j84--memory-leaks-heap-dumps--profiling)

### WHY Flags Matter

The JVM ships with defaults optimised for "typical" workloads. Your workload may differ: small heap, huge heap, I/O-bound, CPU-bound, latency-critical, throughput-critical. Flags let you express your workload's needs to the JVM. Knowing which flags to reach for — and which to leave alone — is a key senior engineering skill.

### Memory Sizing Flags

```
Flag                        Meaning
────────────────────────────────────────────────────────────────────
-Xms<size>                  Initial heap size (e.g. -Xms512m, -Xms4g)
                            JVM allocates this on startup.
                            Set equal to -Xmx to avoid heap resizing
                            pauses and GC overhead at startup.

-Xmx<size>                  Maximum heap size (e.g. -Xmx8g)
                            Total young + old generation.
                            Never set above ~75% of available RAM —
                            leave room for OS, Metaspace, threads.

-Xmn<size>                  Young generation size (e.g. -Xmn2g)
                            Only for Parallel/Serial GC. Not used by G1GC
                            (G1 manages region allocation dynamically).
                            Larger young gen → less frequent minor GCs
                            but longer minor GC pauses.

-XX:MaxMetaspaceSize=<size> Cap on Metaspace (e.g. -XX:MaxMetaspaceSize=256m)
                            Without this cap, Metaspace grows unbounded
                            on the native heap — a memory leak in apps
                            that load many classes dynamically.

-XX:MetaspaceSize=<size>    Initial Metaspace size before first GC of
                            Metaspace is triggered (not a reservation).
```

**Sizing heuristic:** start with `-Xms = -Xmx` (avoids heap resize pauses). Set `-Xmx` to 70–75% of available RAM. Monitor GC logs to see if Old Gen is consistently >80% full after GC (indicates heap is too small) or consistently <30% full (indicates heap could be reduced to reduce GC time).

### GC Selection Flags

```java
// G1GC (recommended default for Java 9+, especially heap > 2GB)
-XX:+UseG1GC

// ZGC (Java 15+, sub-millisecond latency target)
-XX:+UseZGC

// Shenandoah (sub-millisecond, Red Hat / Eclipse Temurin builds)
-XX:+UseShenandoahGC

// Parallel GC (max throughput, accepts longer pauses, batch workloads)
-XX:+UseParallelGC

// Serial GC (single-core, tiny heaps, microcontainers)
-XX:+UseSerialGC
```

### G1GC Key Tuning Flags

```
Flag                              Default   Meaning
──────────────────────────────────────────────────────────────────────
-XX:MaxGCPauseMillis=200          200       Soft pause target in ms.
                                            G1 tries to keep STW pauses
                                            below this. Lower = more CPU
                                            overhead to maintain goal.

-XX:G1HeapRegionSize=<n>m         auto      Region size (1–32 MB, power 2).
                                            Auto-computed from heap size.
                                            Larger regions = fewer Humongous
                                            allocations. Override only if
                                            you have many large objects.

-XX:G1NewSizePercent=5            5         Minimum young gen size as % of heap.
-XX:G1MaxNewSizePercent=60        60        Maximum young gen size as % of heap.

-XX:InitiatingHeapOccupancyPercent=45  45   Old gen occupancy % at which
(IHOP)                                      G1 starts concurrent marking.
                                            Lower = more frequent marking,
                                            less Full GC risk.
                                            Higher = fewer marking cycles,
                                            more Full GC risk.

-XX:G1MixedGCCountTarget=8        8         Target number of mixed GC cycles
                                            per marking cycle. More = slower
                                            old-gen cleanup but shorter pauses.

-XX:ConcGCThreads=N               auto      Threads for concurrent G1 work.
                                            Increase for large heaps on many
                                            CPU systems.
```

**G1GC tuning priority:**
1. First: set `-XX:MaxGCPauseMillis` to your target
2. If Full GCs occur: lower `InitiatingHeapOccupancyPercent` or increase heap
3. If Humongous allocation warnings: increase `G1HeapRegionSize`
4. If concurrent marking can't keep up: increase `ConcGCThreads`

### GC Logging (Essential for Diagnosis)

```bash
# Java 9+ unified logging (use this)
-Xlog:gc*:file=gc.log:time,uptime,level,tags

# Java 8 (legacy)
-XX:+PrintGCDetails
-XX:+PrintGCDateStamps
-Xloggc:/var/log/myapp/gc.log
```

The unified logging format (`-Xlog`) produces structured output parseable by tools like GCViewer and GCEasy:

```
[2024-01-15T10:23:45.123+0000][1.234s][info][gc] GC(42) Pause Young (Normal) (G1 Evacuation Pause) 256M->128M(4096M) 12.345ms
[2024-01-15T10:23:46.456+0000][2.567s][info][gc] GC(43) Pause Young (Concurrent Start) (G1 Humongous Allocation) 512M->256M(4096M) 18.901ms
```

### Diagnostic Flags

```bash
# Dump heap to file on OOM (ALWAYS enable in production)
-XX:+HeapDumpOnOutOfMemoryError
-XX:HeapDumpPath=/var/log/myapp/heapdump.hprof

# Print GC cause and details (Java 9+)
-Xlog:gc+cause=debug

# JVM ergonomics — show what the JVM chose for heap size, GC, etc.
-XX:+PrintFlagsFinal | grep -E "HeapSize|GC|Pause"
```

### Tuning Decision Tree

```
What is your primary concern?

├── THROUGHPUT (batch, analytics, MapReduce)
│   └── Use Parallel GC (-XX:+UseParallelGC)
│       Tune -XX:ParallelGCThreads, -Xmx
│
├── LATENCY (APIs, trading, game servers)
│   ├── Pauses < ~10ms acceptable → G1GC (default)
│   │   Tune -XX:MaxGCPauseMillis
│   └── Pauses MUST be < 1ms → ZGC or Shenandoah
│       Ensure heap >> live data set
│
└── MEMORY (containers, microservices, tiny VMs)
    └── Use Serial GC or G1GC with small -Xmx
        Consider -XX:+UseContainerSupport (Java 8u191+, Java 10+)
        for correct container memory limit detection
```

---

## J8.4 — Memory Leaks, Heap Dumps & Profiling

> **Builds on:** [J8.3 — JVM Flags & GC Tuning](J8_gc_and_jvm_tuning.md#j83--jvm-flags--gc-tuning)

### WHY This Matters

In theory, garbage collection eliminates memory leaks. In practice, Java programs leak memory all the time — not because memory is not freed, but because the GC cannot collect objects that are still reachable. A "memory leak" in Java is an **unintentional retention**: a root (or chain from a root) keeps objects alive longer than intended.

### Generating a Heap Dump

A heap dump is a snapshot of all live objects on the heap at a moment in time. It is the primary tool for diagnosing OOM errors and high memory usage.

```bash
# Method 1: jmap (from any running JVM, requires pid)
jmap -dump:live,format=b,file=heap.hprof <pid>
# Note: `live` triggers a Full GC first to get only reachable objects

# Method 2: jcmd (preferred — same JVM tools, better maintained)
jcmd <pid> GC.heap_dump /var/log/myapp/heap.hprof

# Method 3: Automatic on OOM (always enable in production!)
-XX:+HeapDumpOnOutOfMemoryError
-XX:HeapDumpPath=/var/log/myapp/
# JVM writes the dump automatically at the moment of OOM, then continues
# (or terminates if unhandled — check your JVM exit on OOM setting)

# Method 4: Via VisualVM, JMC (Java Mission Control), or your APM tool
```

### Reading Heap Dumps: Eclipse Memory Analyzer (MAT)

MAT is the standard tool for heap dump analysis. Key concepts:

```
Shallow Heap:   Memory consumed by the object itself (fields only).
                An ArrayList's shallow heap = ~40 bytes (header + fields).

Retained Heap:  Memory that would be freed if this object were GC'd.
                Includes the object AND everything exclusively reachable
                through it.
                An ArrayList with 1M entries: shallow ~40 bytes,
                retained could be hundreds of MB.

Dominator Tree: A tree where each node dominates the set of objects
                exclusively reachable through it. The top of the
                dominator tree shows you what is "holding" the most
                memory.
```

**MAT workflow for OOM analysis:**
1. Open `.hprof` file in MAT
2. Click "Leak Suspects Report" — automated heuristic analysis
3. Open Dominator Tree — look for unexpected large retained heaps
4. Follow the reference chain to find the GC root holding everything alive

### Common Memory Leak Patterns

**Pattern 1: Static Collections**

```java
// LEAK: static list grows forever, never cleared
public class EventBus {
    private static final List<Event> ALL_EVENTS = new ArrayList<>();

    public static void publish(Event event) {
        ALL_EVENTS.add(event);   // never removed — held by static field (GC root)
        // ... dispatch to listeners
    }
}
// Fix: use a WeakReference list, or clear after dispatch,
// or don't store events statically
```

**Pattern 2: Listeners Not Unregistered**

```java
// LEAK: component registers listener but never unregisters
class MyComponent {
    void init(EventSource source) {
        source.addListener(this::onEvent);   // MyComponent is now held by source
        // When MyComponent is "done", source still holds a reference to it
        // MyComponent cannot be GC'd until source is GC'd
    }
    // Fix: store the reference and call source.removeListener() in destroy/close
}
```

**Pattern 3: ThreadLocal Not Removed**

```java
// LEAK in thread pool: ThreadLocal not cleaned up
ThreadLocal<HeavyObject> context = new ThreadLocal<>();

// In a servlet handler (runs on pooled thread):
context.set(new HeavyObject());
try {
    // ... handle request
} finally {
    context.remove();   // REQUIRED — without this, the ThreadLocal entry
                        // stays associated with the pooled thread forever.
                        // Pooled threads never die → entry never freed.
}
```

**Pattern 4: Inner Class Holding Outer Reference**

```java
// LEAK: anonymous Runnable captures enclosing Activity/Fragment
class MyActivity {
    void startLongTask() {
        new Thread(() -> {
            // This lambda captures `this` (MyActivity)
            longRunningOperation();
            updateUi();   // references MyActivity
        }).start();
        // If the user navigates away, MyActivity should be GC'd,
        // but the thread holds a reference → leak until thread finishes
    }
    // Fix: use WeakReference<MyActivity> or cancel the thread on destroy
}
```

### GC Log Analysis: Understanding Key Messages

```
"Allocation Failure"
    → Eden space exhausted; Minor GC triggered.
    → Normal unless extremely frequent (allocation rate too high).

"Humongous Allocation" (G1GC)
    → Object > 50% of region size allocated directly in Old Gen.
    → Symptom: frequent Concurrent Start GCs, rising Old Gen occupancy.
    → Fix: increase -XX:G1HeapRegionSize, or reduce object size.

"to-space exhausted" (G1GC)
    → Survivor / Old Gen regions insufficient to hold evacuated objects.
    → Triggers Full GC fallback.
    → Symptom: very long pause immediately after.
    → Fix: increase heap, lower InitiatingHeapOccupancyPercent, or reduce
       allocation rate.

"Promotion Failure" (Parallel/Serial GC)
    → No room in Old Gen for objects being promoted from Young Gen.
    → Triggers Full GC.
    → Fix: increase -Xmx, increase -Xmn, or reduce long-lived object count.

"Metadata GC Threshold" (Metaspace)
    → Metaspace is growing and triggering Full GC.
    → Common in apps that load many classes dynamically (e.g., Spring, Hibernate).
    → Fix: set -XX:MaxMetaspaceSize, investigate class loader leaks.
```

### JVM Diagnostic Tools Reference

| Tool | Purpose | Key Commands |
|------|---------|--------------|
| `jstat` | GC statistics from running JVM | `jstat -gc <pid> 1000` (poll every 1s) |
| `jstack` | Thread dump — all thread states and stack traces | `jstack <pid>` |
| `jmap` | Heap dump, class histogram | `jmap -histo <pid>` (live class sizes) |
| `jcmd` | Multi-purpose — preferred modern tool | `jcmd <pid> help` |
| `jinfo` | JVM flags and system properties | `jinfo <pid>` |
| `VisualVM` | GUI: heap, threads, profiler, heap dump | Free, bundled with JDK ≤8 |
| **JFR** | Java Flight Recorder: low-overhead event recording | `jcmd <pid> JFR.start duration=60s filename=recording.jfr` |

**JFR (Java Flight Recorder)** is the recommended production-safe profiler. It records JVM events (GC pauses, lock contention, method profiling, I/O) with typically <2% overhead. Combined with **JMC (Java Mission Control)** for analysis, it is the most powerful tool for diagnosing JVM performance issues in production.

```bash
# Enable JFR for 60 seconds and save recording
jcmd <pid> JFR.start name=profile duration=60s filename=/tmp/recording.jfr

# Or enable at JVM startup with continuous recording
-XX:StartFlightRecording=filename=recording.jfr,maxsize=100m,maxage=1h
```

---

## Master Summary: GC & JVM Tuning

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  PHASE J8 — GC & JVM TUNING MASTER SUMMARY                                   │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  1. GENERATIONAL GC (J8.1)                                                   │
│     Weak generational hypothesis: most objects die young (~80-95%).          │
│     Heap: Eden → Survivor S0/S1 (young) → Old Gen. Plus Metaspace (off-heap).│
│     GC roots: stack frames, static fields, JNI refs, threads.                │
│     Minor GC: Young gen only (fast). Full GC: entire heap (slow, avoid).    │
│     Objects promoted when age counter >= MaxTenuringThreshold (default 15). │
│                                                                              │
│  2. GC ALGORITHMS (J8.2)                                                     │
│     Serial: single-thread STW. Simple. For tiny heaps/single-core only.     │
│     Parallel: multi-thread STW. Max throughput. Batch jobs. Java 8 default. │
│     G1GC: region-based (~2048 regions). Concurrent marking + mixed GC.      │
│       Set pause target with MaxGCPauseMillis. Java 9+ default. General use. │
│     ZGC: concurrent mark+relocate+remap. Sub-ms pauses. 16TB tested.        │
│       Uses load barriers (colored pointers). Java 15+ production ready.     │
│                                                                              │
│  3. JVM FLAGS (J8.3)                                                         │
│     -Xms = -Xmx: avoid heap resize pauses. Never exceed 75% of RAM.         │
│     -XX:MaxMetaspaceSize: cap Metaspace or it grows unbounded (OOM risk).   │
│     -XX:MaxGCPauseMillis: G1GC soft pause target (default 200ms).           │
│     -XX:InitiatingHeapOccupancyPercent: lower → earlier marking → fewer FGC.│
│     -XX:+HeapDumpOnOutOfMemoryError: ALWAYS enable in production.           │
│     GC logging: -Xlog:gc*:file=gc.log:time,uptime,level,tags               │
│                                                                              │
│  4. LEAKS & PROFILING (J8.4)                                                 │
│     Java leaks = unintentional retention (object still reachable, not used).│
│     Common patterns: static collections, unremoved listeners, ThreadLocal   │
│       not cleaned up, inner classes capturing outer context.                 │
│     Heap dump: jmap/jcmd → analyze with MAT (dominator tree, retained heap).│
│     GC log keywords: Allocation Failure, Humongous, to-space exhausted.     │
│     JFR (Java Flight Recorder): <2% overhead, best production profiler.     │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

*← [Phase J7 — java.util.concurrent](J7_concurrent_utilities.md) | [Phase J9 — Modern Java →](J9_modern_java.md)*
