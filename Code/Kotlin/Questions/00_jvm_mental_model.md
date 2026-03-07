# Phase 0 — JVM Mental Model

> The JVM has exactly two worlds: **primitives** and **Objects**. Every Kotlin feature — nullable types, generics, lateinit, inline — exists because of the tension between these two worlds.

## Navigation

[→ Phase 1 — Type System Foundations](01_type_system_foundations.md)

## Questions in This File

- [Q0.1 — Primitives vs References: The Two Worlds](#q01--primitives-vs-references-the-two-worlds)
- [Q0.2 — JVM Type Mapping: When Does Kotlin Box?](#q02--jvm-type-mapping-when-does-kotlin-box)
- [Q0.3 — Class Loading and `init {}` in `object`](#q03--class-loading-and-init--in-object)
- [Q0.4 — The JVM Call Stack](#q04--the-jvm-call-stack)
- [Q0.5 — Code Execution Pipeline: .kt to Running Code](#q05--code-execution-pipeline-kt-to-running-code)

---

# Q0.1 — Primitives vs References: The Two Worlds

> **Connects to:** [Q1.1 (val stores primitives)](01_type_system_foundations.md#q11--val-vs-const-val) · [Q5.1 (lateinit can't use null sentinel with primitives)](05_properties_and_delegation.md#q51--lateinit-internals) · [Q3.3 (reified erases to Object)](03_generics_and_variance.md#q33--reified-type-parameters)

---

## The Core Distinction

```
val x: Int = 42

  STACK
  +--------+
  | x = 42 |   ← value IS here
  +--------+

val y: String = "hi"

  STACK              HEAP
  +----------+       +----------------+
  | y = 0x7f |-----> | header | "hi"  |
  +----------+       +----------------+
    (pointer)           (object)
```

`x` IS the number 42. No pointer. No wrapper.
`y` is an address pointing to a String on the heap.

That's the entire distinction. Everything else follows.

---

## Why Two Kinds?

The JVM designers faced two incompatible needs:

**Performance** — `i + 1` in a loop can't afford pointer indirection on every step.

**Containers** — `List`, `Map` need a common parent type (`Object`) to store anything. Primitives don't descend from `Object`.

A raw `42` on the stack has no object header, no type pointer, no identity — it can't participate in the `Object` system. But wrapping every number costs 5–10× slowdown.

**Solution: two type systems side by side.**

| | Primitive | Reference |
|---|---|---|
| Where | On stack directly | Pointer on stack → object on heap |
| Identity? | No | Yes |
| Header? | No — raw bits | Yes — 12–16 bytes |
| Can be null? | **No** | Yes |
| Default | Zero (`0`, `false`) | `null` |
| Size | 1–8 bytes | 4–8 byte pointer + 16+ byte object |

---

## The 8 Primitives

```
Integers:  byte  short  int   long
           8b    16b    32b   64b

Decimals:  float   double
           32b     64b

Other:     boolean  char
           1b       16b (Unicode)
```

Everything else descends from `Object`.

---

## Why Primitives Can't Be Null

An `int` field is 4 bytes, 32 bits. To support null, you'd need to reserve one bit pattern to mean "no value." But:

```
int field (4 bytes):
  [0000...00000000]  = 0  ← valid integer, NOT null
  [0000...00101010]  = 42 ← valid integer
  All 2^32 patterns = valid numbers. Zero spare.

reference field (4–8 bytes):
  [0000...00000000]  = null ← address zero, reserved
  [0111...00001000]  = pointer to object
  Address zero is reserved. One spare value exists.
```

**Primitives can't be null: no bit pattern left to mean "empty."**
References can be null: address `0x0` is reserved and never holds a real object.

This directly explains `lateinit var count: Int` being illegal — [Q5.1](05_properties_and_delegation.md#q51--lateinit-internals).

---

## Stack vs Heap

```
JVM MEMORY

HEAP (shared, GC-managed)
  All objects live here.
  Survives beyond the method call.

STACK (one per thread, private)
  | Frame: doWork()         |  ← current
  |   int count = 5         |  primitive here
  |   User u = 0x7f ---------> [User object on heap]
  |__________________________|
  | Frame: main()           |  ← caller
  |__________________________|
```

**The rule:**
- Local primitives → stack (gone when method returns)
- Objects → heap (GC manages lifetime)
- Local references → stack (pointers into heap)
- Instance fields → inside the object on heap

---

## Garbage Collection

Stack cleanup is free — method returns, frame is popped.

Heap cleanup is the GC's job.

```
HEAP (generational)

  Young Gen (small, collected often)
    Eden:     new objects land here
    Survivor: survived 1+ collections

  Old Gen (large, collected rarely)
    Objects that survived many cycles
```

| Trigger | What happens |
|---|---|
| Eden full | **Minor GC** — Young Gen only. Fast (ms). Most objects already dead. |
| Old Gen full | **Major GC** — scan everything. Slow (10–100ms). Causes jank. |

Most objects are short-lived (temporary Strings, lambda wrappers, boxed Integers). By the time Eden fills, 90%+ are already unreachable.

The problem is **volume**:

```kotlin
// ~0 garbage:
var sum = 0
for (i in intArray) { sum += i }

// 1M dead Integer objects:
var sum = 0
for (i in listOfInts) { sum += i }
//         ^^^^^^^^^^ List<Integer> — each unbox leaves a dead wrapper
```

On Android, each GC pause eats into your 16ms frame budget. This is the real cost of boxing — not memory, but GC pressure from millions of short-lived wrappers.

---

## Memory Trick

```
PRIMITIVE = cash in hand    (value IS the variable)
REFERENCE = receipt for locker (pointer to object)

null = "receipt, but locker is empty"
Can't have null cash. Cash just IS.

STACK = auto cleanup (frame popped on return)
HEAP  = GC cleanup   (costs time = jank)
More boxing → more dead wrappers → more GC → dropped frames
```

---

## Self-Test

1. Draw stack/heap for `val x: Int = 42` vs `val y: String = "hi"`.
2. Why can `String` be null but `int` can't? (bit patterns, not language rules)
3. How many bytes: `Integer` object vs raw `int`?
4. Instance field `var count: Int` inside a class — stack or heap?
5. A loop creates 1M boxed Integers. Where do they land, and why does that cause jank?

---

# Q0.2 — JVM Type Mapping: When Does Kotlin Box?

> **Connects to:** [Q5.1 (lateinit forbids Int)](05_properties_and_delegation.md#q51--lateinit-internals) · [Q3.1 (erasure works on Object)](03_generics_and_variance.md#q31--type-erasure) · [Q7.1 (IntArray vs Array)](07_collections_and_sequences.md#q71--kotlins-collection-hierarchy)

---

## The Concrete Picture

```kotlin
val a: Int  = 5  // JVM: int      (4 bytes, stack)
val b: Int? = 5  // JVM: Integer  (object, heap, ~20 bytes)
val c: Any  = 5  // JVM: Integer  (must be Object)
```

Same `5`. Three different costs. The compiler decides with two rules.

---

## The Two Rules

**Rule 1: Nullable → Boxed.**

`Int?` must hold `null`. Primitives can't (Q0.1). So it boxes.

```kotlin
val x: Int  = 42  // → int x = 42;
val y: Int? = 42  // → Integer y = Integer.valueOf(42);
```

**Rule 2: Generic position → Boxed.**

JVM generics work only with `Object` (type erasure — [Q3.1](03_generics_and_variance.md#q31--type-erasure)). Primitives aren't Objects.

```kotlin
val list: List<Int> = listOf(1, 2, 3)
// JVM: List<Integer>
// There is no List<int>. Impossible.
```

**Decision flow:**

```
Is it nullable (Int?)?
  YES → Boxed (Integer)
  NO  → Is it in a generic position?
          YES → Boxed (Integer)
          NO  → Primitive (int)
```

---

## Complete Mapping Table

| Kotlin | JVM | Boxed? | Why |
|---|---|---|---|
| `Int` | `int` | No | Non-nullable, not generic |
| `Int?` | `Integer` | Yes | Rule 1 |
| `Long` | `long` | No | |
| `Long?` | `Long` | Yes | Rule 1 |
| `Boolean` | `boolean` | No | |
| `Boolean?` | `Boolean` | Yes | Rule 1 |
| `String` | `String` | N/A | Already a reference |
| `List<Int>` | `List<Integer>` | Yes | Rule 2 |
| `Any` | `Object` | — | Top type |

---

## `Any` and `Nothing` — Top and Bottom

Every Kotlin type sits in a hierarchy. `Any` is at the top — parent of every non-nullable type. It's Kotlin's `Object`.

```
    Any        (top — parent of all)
   / | \
String Int  User ...
   \ | /
  Nothing      (bottom — child of all)
```

```kotlin
val x: Any = "hello"  // String IS-A Any  ✓
val y: Any = 42        // Int IS-A Any     ✓ (forces boxing)
val z: Any = User()    // User IS-A Any    ✓
```

This is why `val c: Any = 5` forces boxing — the JVM slot is `Object`, and a raw `int` can't be an `Object`.

At the bottom sits `Nothing` — a subtype of *every* type. No value can ever be `Nothing`. It represents "this computation never produces a value."

```kotlin
val x: String = throw Exception()
// throw returns Nothing
// Nothing IS-A String  ✓ — type-checks

sealed class Result<out T> {
    data class Success<T>(val data: T) : Result<T>()
    data class Error(val e: Throwable) : Result<Nothing>()
    // Result<Nothing> IS-A Result<T> for any T
    // because Nothing is the bottom type + out variance
}
```

`Nothing` will appear in depth at [Q1.3](01_type_system_foundations.md#q13--type-hierarchy-any-nothing-unit). The Q0.2 connection is: `Any` = `Object` = forces boxing whenever a primitive must fill an `Any`-typed slot.

---

## Boxing Cost

```
Primitive int:
  4 bytes on stack. Done.

Boxed Integer:
  4 bytes  pointer (stack)
  12 bytes object header (heap)
  4 bytes  int value (heap)
  ─────────
  20 bytes total + GC overhead
```

---

## `IntArray` vs `Array<Int>`

| | `IntArray` | `Array<Int>` |
|---|---|---|
| JVM type | `int[]` | `Integer[]` |
| 1M elements | ~4 MB | ~20 MB (5×) |
| Iteration | 1 instruction | load + unbox |
| Use when | Numeric work | Need nulls |

```kotlin
val scores = IntArray(100)        // ✅ fast
val scores = Array<Int>(100) { 0 } // ❌ 5× memory unless you need nulls
```

---

## The Integer Cache Trap

Java caches `Integer` for –128 to 127. Inside range: same object. Outside: new object every time.

```kotlin
val a: Int? = 127
val b: Int? = 127
a === b    // true (same cached object)

val c: Int? = 128
val d: Int? = 128
c === d    // false (different objects!)
c == d     // true  (structural equality)
```

Interview trap: "Why does `===` differ for small vs large nullable Ints?"

---

## Connections Forward

| Feature | Why Boxing Matters |
|---|---|
| `lateinit var count: Int` | Impossible — null sentinel, `int` can't be null → [Q5.1](05_properties_and_delegation.md#q51--lateinit-internals) |
| `List<Int>` | Generics erase to `Object` → [Q3.1](03_generics_and_variance.md#q31--type-erasure) |
| `reified` inline | Defeats erasure at call site → [Q3.3](03_generics_and_variance.md#q33--reified-type-parameters) |
| `inline fun` + lambda | Eliminates `Function` object → [Q4.2](04_functions_lambdas_inlining.md#q42-inline-noinline-crossinline) |

---

## Memory Trick

```
WHEN DOES KOTLIN BOX?
  Nullable? → Boxed
  Generic?  → Boxed
  Otherwise → Primitive

ARRAY SHORTCUT:
  IntArray   = int[]     = fast
  Array<Int> = Integer[] = 5× memory
```

---

## Self-Test

1. What JVM type for `val x: Int = 5`? For `val y: Int? = 5`? Why different?
2. Why does `List<Int>` store boxed Integers?
3. Memory: `IntArray(1_000_000)` vs `Array<Int>(1_000_000)`?
4. Why does `127 as Int? === 127 as Int?` return true, but `128` returns false?
5. Iterating 10M numbers in a game loop — which type and why?
6. Why does `val x: Any = 5` force boxing? What does `Any` map to on the JVM?

---

# Q0.3 — Class Loading and `init {}` in `object`

> **Connects to:** [Q2.4 (object singleton thread safety)](02_classes_and_objects.md#q24--the-object-keyword) · [Q1.1 (const val doesn't trigger loading)](01_type_system_foundations.md#q11--val-vs-const-val)

---

## The Concrete Picture

```kotlin
object DatabaseConfig {
    val URL = "jdbc:sqlite:app.db"
    init { println("DatabaseConfig initialized!") }
}
```

```
FIRST ACCESS: DatabaseConfig.URL
  Is it loaded? NO
  → Load .class → Verify → Init
  → run init {} → print message
  → return URL

SECOND ACCESS: DatabaseConfig.URL
  Is it loaded? YES
  → return URL immediately (no init, no print)
```

First access pays. Every subsequent access is instant.
`init {}` runs **exactly once, thread-safely**.

---

## The Three-Phase Loading Pipeline

```
1. LOAD
   ClassLoader reads .class bytes

2. LINK
   a. Verify  (bytecode safety check)
   b. Prepare (allocate static fields, zero them)
   c. Resolve (link symbolic references)

3. INITIALIZE
   Run <clinit> (class initializer)
   ← Kotlin's init {} ends up here
   ← Field assignments execute here
```

`init {}` inside `object` or `companion object` compiles to `<clinit>`. Same mechanism, Kotlin syntax.

---

## What Triggers Initialization

| Access | Triggers Init? | Why |
|---|---|---|
| `new MyClass()` | **Yes** | Instance creation |
| `MyClass.method()` | **Yes** | Static method call |
| `MyClass.someVal` | **Yes** | Static field read |
| `MyClass.CONST_VAL` | **No** | Inlined at compile time |
| `MyClass::class` | **No** | Metadata only |

```kotlin
object Config {
    const val TAG = "MyApp"        // inlined
    val VERSION = computeVersion() // runtime field

    init { println("Config initialized!") }
}

Log.d(Config.TAG, "hello")     // ❌ does NOT print — TAG is "MyApp" in bytecode
Log.d(Config.VERSION, "hello") // ✅ DOES print — field read triggers init
```

---

## The Thread Safety Guarantee

JVM spec (§5.5) guarantees:
1. Only **one thread** executes `<clinit>`
2. Other threads **block** until it completes
3. `<clinit>` never runs again

Free synchronization. No `synchronized`, no `volatile`, no double-checked locking.

```java
// What Kotlin object compiles to:
public final class SessionManager {
    public static final SessionManager INSTANCE;

    static {
        INSTANCE = new SessionManager(); // once, thread-safe
    }

    private SessionManager() {}
}
```

**JVM class loading IS the singleton pattern.**

---

## Memory Trick

```
TRIGGERS INIT?
  new / method / field read → YES
  const val / ::class        → NO

THREAD SAFETY:
  <clinit> = once, one thread, others block
  Kotlin object = free thread-safe singleton
```

---

## Self-Test

1. `object Config { const val TAG = "app"; val URL = "..." }` — does `Config.TAG` trigger init? Does `Config.URL`?
2. Why is `object` thread-safe without any synchronization keywords?
3. Which phase of the 3-phase pipeline runs `init {}`?
4. Two threads hit `Config.URL` simultaneously for the first time — what happens?

---

# Q0.4 — The JVM Call Stack

> **Connects to:** [Q1.1 (val getter overhead)](01_type_system_foundations.md#q11--val-vs-const-val) · [Q4.2 (inline eliminates method call)](04_functions_lambdas_inlining.md#q42-inline-noinline-crossinline)

---

## The Concrete Picture

Every method call pushes a frame. Every return pops it.

```
main() → loadData() → processUser()

AT DEEPEST POINT:

  | processUser() |  ← top
  |_______________|
  | loadData()    |
  |_______________|
  | main()        |
  |_______________|

AFTER processUser() RETURNS:

  | loadData()    |  ← top (processUser's locals are gone)
  |_______________|
  | main()        |
  |_______________|
```

---

## What's Inside a Frame

- **Local variable table** — parameters + local variables
- **Operand stack** — scratch space for math (the JVM has no registers; push values, operate, pop result)
- **Return address** — where to continue after return

---

## Why Method Calls Cost More Than Field Reads

**Field read — 1 instruction:**

```
GETFIELD MyClass.value : int
```

**Getter call — 4 steps:**

```
INVOKEVIRTUAL MyClass.getValue()
  1. Look up method in vtable
  2. Push new stack frame
  3. GETFIELD MyClass.value
  4. Pop frame, return value
```

For `final` classes, JIT inlines this away. For `open` classes, the vtable lookup stays.

---

## Virtual Dispatch vs Direct Call

| Type | Instruction | When | Overhead |
|---|---|---|---|
| Virtual | `INVOKEVIRTUAL` | `open` methods | vtable lookup |
| Interface | `INVOKEINTERFACE` | Interface calls | **slowest** |
| Direct | `INVOKESPECIAL` | `private`, `super` | none |
| Static | `INVOKESTATIC` | Top-level, extensions | none |

```
FASTEST                        SLOWEST
static/special > virtual > interface
  (direct)       (vtable)   (itable)
```

---

## Why `final` by Default Is a Performance Feature

`final` class → JIT knows no subclass overrides → replaces vtable lookup with a direct jump (devirtualization).

```kotlin
class Calculator {          // final by default → JIT inlines entirely
    fun add(a: Int, b: Int) = a + b
}

open class OpenCalc {       // open → vtable lookup stays
    open fun add(a: Int, b: Int) = a + b
}
```

---

## Lambdas and Inline

Lambda passed to a non-inline function:

```
{ doStuff() }
  = Function0 interface
  = INVOKEINTERFACE  (slowest dispatch)
  + heap allocation  (Function0 object)
```

With `inline fun`:

```
inline fun measure(block: () -> Unit)
  = body pasted at call site
  = no Function0 object
  = no interface dispatch
  = no stack frame
  = ZERO overhead
```

This is why `let`, `apply`, `also`, `map`, `filter` are all `inline`. See [Q4.2](04_functions_lambdas_inlining.md#q42-inline-noinline-crossinline).

---

## Memory Trick

```
CALL COST:
  field read  = 1 instruction
  method call = vtable + frame + field + return

DISPATCH SPEED:
  final  → devirtualize → fast
  open   → vtable stays → slower
  inline → no call at all → fastest
```

---

## Self-Test

1. What 3 things are inside a stack frame?
2. Why is `GETFIELD` faster than a getter call?
3. Lambda passed to a non-inline function — what bytecode instruction runs it? Why is it the slowest?
4. Why does `final` by default help JIT performance?

---

# Q0.5 — Code Execution Pipeline: .kt to Running Code

> **Connects to:** [Q3.1 (type erasure)](03_generics_and_variance.md#q31--type-erasure) · [Q4.2 (inline)](04_functions_lambdas_inlining.md#q42-inline-noinline-crossinline) · [Q16.4 (Zygote and App Startup)](16_android_system_internals.md#q164--zygote-and-app-startup)

---

## The 30-Second Answer

```
.kt → kotlinc → .class → d8 → .dex → ART

Desktop: interpret first, JIT hot code
Android: AOT at install, profile-guided later
```

---

## JDK, JRE, JVM, JIT — The Nesting

```
JDK (Java Development Kit)
│  kotlinc, javac, d8, debugger, profiler
│
└─ JRE (Java Runtime Environment)
   │  java.lang, java.util, java.io, ...
   │
   └─ JVM (Java Virtual Machine)
      │  ClassLoader    ← loads .class files
      │  Interpreter    ← executes bytecode (slow, correct)
      │  JIT Compiler   ← compiles hot bytecode → native
      │  Memory Manager ← heap, stack, GC
```

| Piece | What it does | When |
|---|---|---|
| JDK | Contains `kotlinc`, `d8` | Build time |
| JRE | Standard libraries (`List`, `String`, etc.) | Runtime |
| JVM | Loads bytecode, manages memory | Runtime |
| JIT | Compiles hot methods to native inside the JVM | Runtime |

**On Android**, ART replaces JRE + JVM + JIT entirely.

```
Desktop:  JDK (build) → JRE + JVM + JIT (run)
Android:  JDK (build) → ART replaces everything (run)
```

---

## The Full Pipeline

```
STAGE 1: COMPILE TIME (your machine)

.kt source
  ↓ kotlinc
Parse      (text → AST)
  ↓
Type check (infer types, null safety)
  ↓
Desugar    (Kotlin features → JVM equivalents)
  ↓
Emit       (.class files with bytecode)


STAGE 2: BYTECODE

.class = stack-based instructions
  ICONST_2, ICONST_3, IMUL
  = push 2, push 3, multiply → 6
  ~200 opcodes total

Desktop: JVM loads .class directly
Android: d8 converts .class → .dex


STAGE 3: RUNTIME

Desktop JVM (HotSpot):
  Interpret first → JIT compiles hot methods → native speed

Android ART:
  AOT at install (pre-compiled) → profile-guided recompilation
  → hot paths are native on next launch
```

---

## What kotlinc Desugars

| Kotlin | Desugars To |
|---|---|
| `data class` | `equals` + `hashCode` + `copy` + `componentN` |
| `suspend fun` | State machine + `Continuation` — [Q9.1](09_coroutines_execution_mechanics.md#q91--what-suspend-actually-does) |
| `inline fun { }` | Body pasted at call site — [Q4.2](04_functions_lambdas_inlining.md#q42-inline-noinline-crossinline) |
| `a + b` (operator) | `a.plus(b)` |
| `for (i in 1..10)` | `while` loop with counter |
| `{ x -> x + 1 }` | Anonymous `Function1` class |

**After desugaring, there's no "Kotlin" left.** The `.class` file is pure JVM bytecode.

---

## JIT Tiers: Why Hot Code Gets Fast

```
CALL COUNT       MODE          SPEED
1 – 100          Interpreted   Slow
100 – 10,000     C1 compiled   Moderate
10,000+          C2 compiled   Full native
```

**Key optimizations:**

**Method inlining** — hot methods pasted at call site. Kotlin `inline` does this at compile time for lambdas.

**Devirtualization** — JIT profiles types at call sites. If always `Dog`, replaces vtable lookup with direct call.

**Escape analysis** — object never leaves method? Allocate on stack, skip GC entirely.

---

## Desktop JVM vs Android ART

| | Desktop (HotSpot) | Android (ART) |
|---|---|---|
| When | Runtime (JIT) | Install (AOT) + runtime |
| Cold start | Slow | Fast |
| Peak speed | Very high | High |
| Warm-up? | Yes (10–30s) | Minimal |

Baseline Profiles give ART a list of hot methods to AOT-compile at install time. Google Maps, Meta, Zomato report ~30% startup improvement. See [Q17.3](17_performance_and_memory.md#q173--the-16ms-budget).

---

## Memory Trick

```
NESTING:
  JDK > JRE > JVM > JIT
  Build    Runtime
  Android: ART replaces JRE + JVM + JIT

TWO COMPILERS:
  kotlinc  = your machine → bytecode
  JIT/ART  = user's device → native code

DESUGARING = "no Kotlin at runtime"
  suspend → state machine
  inline  → pasted body
  data    → equals + hashCode + copy
  lambda  → Function object (unless inline)

ANDROID vs DESKTOP:
  Desktop → start slow, get fast
  Android → start fast, get faster
```

---

## Self-Test

1. What's the nesting: JDK contains what? JRE contains what? Where does JIT live?
2. What 4 things does `kotlinc` do during compilation?
3. After compilation — is there any "Kotlin" left in the `.class` file?
4. Desktop JVM vs Android ART — key difference in when compilation happens?
5. Why do Baseline Profiles improve startup?
6. Method called 50,000 times — what tier? What optimizations apply?

---

# Master Summary: Phase 0

> Everything traces back to one tension: **primitives live as raw values, Objects live on the heap behind pointers.** Kotlin's features exist to bridge, optimize, or work around this split.

**1. TWO WORLDS** (Q0.1)
Primitives = value IS the variable. References = pointer to heap object.
Primitives can't be null (no spare bit pattern). This is why `lateinit` can't work with `Int`.
→ Foundation for [Phase 5: Properties and Delegation](05_properties_and_delegation.md)

**2. BOXING** (Q0.2)
Nullable or generic position → boxed Object. Otherwise → primitive.
`IntArray` = `int[]` (fast). `Array<Int>` = `Integer[]` (5× memory).
GC pressure from boxing = dropped frames on Android.
→ Foundation for [Phase 3: Generics and Variance](03_generics_and_variance.md)

**3. CLASS LOADING** (Q0.3)
`init {}` in `object` compiles to `<clinit>`. Runs once, thread-safely.
`const val` is inlined — does NOT trigger loading.
JVM class loading IS the singleton pattern.
→ Foundation for [Phase 2: Classes and Objects](02_classes_and_objects.md)

**4. CALL COST** (Q0.4)
field read (1 instruction) < virtual call (vtable) < interface call (slowest).
`final` → JIT devirtualizes. `inline` → no call at all.
Every non-inline lambda = `Function` object + `INVOKEINTERFACE`.
→ Foundation for [Phase 4: Functions, Lambdas, Inlining](04_functions_lambdas_inlining.md)

**5. PIPELINE** (Q0.5)
JDK (build) → JRE + JVM + JIT (run). Android: ART replaces all three.
kotlinc desugars everything — no Kotlin left at runtime.
Cold code = interpreted. Hot code = C2 native. Baseline Profiles = skip warmup.
→ Foundation for [Phase 16: Android System Internals](16_android_system_internals.md)

---

## Final Self-Test: All of Phase 0

1. **(Q0.1)** Why can't `int` be null? Explain using bit patterns, not language rules.
2. **(Q0.2)** What two conditions force Kotlin to box a primitive? Memory cost of `Array<Int>` vs `IntArray` for 1M elements?
3. **(Q0.3)** `object Config { const val TAG = "x"; val URL = "y" }` — which access triggers `init {}` and which doesn't? Why?
4. **(Q0.4)** A lambda passed to a non-inline function — what dispatch instruction runs it? Why is `inline` faster?
5. **(Q0.5)** What does `kotlinc` produce? What does the JIT do with it? How does Android ART differ from Desktop JVM?

---

*Next: [Phase 1 — Type System Foundations →](01_type_system_foundations.md)*