# Phase 0: JVM Mental Model

> **The JVM has exactly two worlds: primitives and Objects. Every Kotlin feature you'll study — nullable types, generics, lateinit, inline — exists because of the tension between these two worlds.** Understanding this tension is understanding the JVM.

## Navigation
[← Master Index](master_chains.md)

## Questions in This File
- [Q0.1 — Primitives vs References: The Two Worlds](#q01--primitives-vs-references-the-two-worlds)
- [Q0.2 — JVM Type Mapping: When Does Kotlin Box?](#q02--jvm-type-mapping-when-does-kotlin-box)
- [Q0.3 — Class Loading and `init {}` in `object`](#q03--class-loading-and-init--in-object)
- [Q0.4 — The JVM Call Stack](#q04--the-jvm-call-stack)
- [Q0.5 — Code Execution Pipeline: .kt to Running Code](#q05--code-execution-pipeline-kt-to-running-code)

---

## Q0.1 — Primitives vs References: The Two Worlds

> **This section answers ONE question: What are the two kinds of types the JVM has, and why do they exist?**
>
> **Connects to:** [Q1.1 (val stores primitives)](01_type_system_foundations.md#q11--val-vs-const-val) · [Q5.1 (lateinit can't use null sentinel with primitives)](05_properties_and_delegation.md#q51--lateinit-internals) · [Q3.3 (reified erases to Object)](03_generics_and_variance.md#q33--reified-type-parameters)

### The Concrete Picture

```
val x: Int = 42

  STACK
  +--------+
  | x = 42 |   <-- value IS here
  +--------+

val y: String = "hi"

  STACK              HEAP
  +----------+       +----------------+
  | y = 0x7f |------>| header | "hi"  |
  +----------+       +----------------+
    (pointer)           (object)
```

`x` IS the number 42. No pointer, no wrapper.
`y` is an ADDRESS pointing to a String on the heap.

That's the entire distinction.
Everything else follows from this.

### Why Two Kinds? — The 1990s Trade-off

The JVM designers faced two competing needs:

1. **Performance** — math on numbers must be fast. You can't afford pointer indirection on every `i + 1` in a loop.
2. **Containers** — you need `List`, `Map`, and other collections that can store any type. This requires a common parent type (`Object`) that everything descends from. Primitives don't descend from `Object`, so they can't participate without being wrapped.

These are fundamentally incompatible. A raw `42` on the stack has no object header, no type pointer, no identity — it can't participate in the `Object` system. But wrapping every number in an object would make arithmetic 5-10× slower.

**The solution: two type systems side by side.**

| | Primitive | Reference |
|---|---|---|
| **Where** | On stack directly | Pointer on stack → object on heap |
| **Identity?** | No | Yes — two `String("hi")` can be different objects |
| **Header?** | No — just raw bits | Yes — 12-16 bytes metadata |
| **Can be null?** | **No** | Yes — null = pointer to nothing |
| **Default** | Zero (`0`, `false`) | `null` |
| **Size** | 1-8 bytes | 4-8 byte pointer + 16+ byte object |

### The 8 Primitives

```
Integers:  byte  short  int  long
           8b    16b    32b  64b

Decimals:  float   double
           32b     64b

Other:     boolean  char
           1b       16b (Unicode)
```

That's it. 8 types. Everything else — every class, interface, array of objects, `String` — is a reference type descending from `Object`.

### Why Primitives Can't Be Null

This unlocks [lateinit](05_properties_and_delegation.md#q51--lateinit-internals), so get it deep.

Try a thought experiment. You have an `int` field — 4 bytes, 32 bits. You want to reserve one special bit pattern to mean "this has no value" (null). Which pattern do you sacrifice?

`00000000 00000000 00000000 00000000`?
That's `0`. Zero is a valid number. You need it.

`11111111 11111111 11111111 11111111`?
That's `-1`. Also a valid number.

Pick any pattern — it's already taken by a real integer. All 2³² bit patterns are spoken for. There is literally no room to say "not a value yet."

Now look at a reference field. It holds a memory address — a pointer to an object on the heap. But not every address is a valid object location. The JVM reserves address `0x0` to mean "points to nothing." That's `null`. It works because no real object ever lives at address zero.

```
int field (4 bytes):
  [0000...00101010]  = 42
  [0000...00000000]  = 0  (a real number, NOT null)
  All 2^32 patterns = valid numbers.
  Zero spare.

reference field (4-8 bytes):
  [0000...00000000]  = null (address zero)
  [0111...00001000]  = pointer to object
  Address zero is reserved. One spare value exists.
```

**Primitives can't be null because there's no bit pattern left to mean "empty."** References can be null because they have a spare address.

Now you see why `lateinit var count: Int` is impossible — `lateinit` uses `null` internally to mean "not yet assigned." But an `int` can't hold null. There's no way to tell "set to 0" apart from "never set at all." See [Q5.1](05_properties_and_delegation.md#q51--lateinit-internals).

### Stack vs Heap

```
JVM MEMORY
==========

HEAP (shared by all threads)
  - All objects live here
  - Managed by GC
  - Survives beyond the method

STACK (one per thread, private)
  |                        |
  | Frame: doWork()        |  <-- current
  |   int count = 5        |  primitive here
  |   User u = 0x7f --------->  [User on heap]
  |________________________|
  |                        |
  | Frame: main()          |  <-- caller
  |________________________|
```

**The rule:**
- Local primitives → stack (dies when method returns)
- Objects → heap (GC manages lifetime)
- Local references → stack (pointing into heap)
- Instance fields → inside object on heap

### Garbage Collection — What Happens to Dead Objects

Stack cleanup is automatic — when a method returns, its frame is popped and everything in it is gone. No cost.

Heap cleanup is the GC's job. And understanding *when* it runs explains why boxing (Q0.2) actually hurts performance.

**The heap is split into generations:**

```
HEAP
  Young Gen (small, collected often)
    Eden:      new objects land here
    Survivor:  survived 1+ collections

  Old Gen (large, collected rarely)
    Objects that survived many cycles
```

**What triggers a collection:**

| Trigger | What happens |
|---|---|
| Eden is full | **Minor GC** — Young Gen only. Fast (ms). Most objects already dead. |
| Old Gen is full | **Major GC** — scan everything. Slow (10-100ms). Causes jank. |
| `System.gc()` | *Suggests* GC. JVM can ignore it. Never rely on this. |

**Why "most objects already dead"?**

Most objects are short-lived — a temporary `String` from concatenation, a lambda's `Function0` wrapper, a boxed `Integer` from a loop. They're created, used once, and abandoned. By the time Eden fills up, 90%+ of its objects are already unreachable. Minor GC sweeps them cheaply.

The problem is **volume**. One dead `Integer` is free. A million per second means the GC runs constantly, pausing your app each time:

```
// ~0 garbage, GC barely notices:
var sum = 0
for (i in intArray) { sum += i }

// 1M dead Integer objects per loop:
var sum = 0
for (i in listOfInts) { sum += i }
//         ^^^^^^^^^^
//  List<Integer> -- each unbox leaves
//  a dead wrapper for GC to clean up
```

On Android, each GC pause eats into your 16ms frame budget. Enough pauses = dropped frames = visible jank. This is the real cost of boxing — not the 16 extra bytes per object, but the GC pressure from millions of short-lived wrappers.

### Memory Trick

```
PRIMITIVE = cash in your hand
REFERENCE = receipt for a locker

Null  = "receipt, but locker is empty"
Can't have "null" cash. Cash just IS.

STACK = automatic cleanup (frame popped)
HEAP  = GC cleanup (costs time)
More boxing = more dead wrappers = more GC = jank
```

### Self-Test (Cover Everything Above)

1. Draw the stack/heap for `val x: Int = 42` vs `val y: String = "hi"`
2. Why can `String` be null but `int` can't? (bit patterns, not language rules)
3. How many bytes: `Integer` object vs raw `int`?
4. Instance field `var count: Int` inside a class — stack or heap?
5. A loop creates 1M boxed Integers. Where do they land on the heap, and why does that cause jank?

---

## Q0.2 — JVM Type Mapping: When Does Kotlin Box?

> **This section answers ONE question: Given a Kotlin type, how does the compiler decide whether to use a primitive or boxed Object?**
>
> **Connects to:** [Q5.1 (why lateinit forbids Int)](05_properties_and_delegation.md#q51--lateinit-internals) · [Q3.1 (erasure works on Object)](03_generics_and_variance.md#q31--type-erasure) · [Q7.1 (IntArray vs Array)](07_collections_and_sequences.md#q71--kotlins-collection-hierarchy)

### The Concrete Picture

Three variables. Three JVM representations:

```kotlin
val a: Int  = 5  // JVM: int      (4 bytes, stack)
val b: Int? = 5  // JVM: Integer  (object, heap, ~20 bytes)
val c: Any  = 5  // JVM: Integer  (must be Object)
```

Same `5`. Three different costs.
The compiler decides with two rules.

### The Two Rules (This Is All You Need)

**Rule 1: Nullable → Boxed.**
`Int?` must hold `null`. Primitives can't be null (Q0.1). So it boxes.

```kotlin
val x: Int  = 42  // → int x = 42;
val y: Int? = 42  // → Integer y = Integer.valueOf(42);
```

**Rule 2: Generic position → Boxed.**
JVM generics only work with `Object` (type erasure — [Q3.1](03_generics_and_variance.md#q31--type-erasure)). Primitives aren't Objects.

```kotlin
val list: List<Int> = listOf(1, 2, 3)
// JVM: List<Integer>
// There is no List<int>. Impossible.
```

**Decision flow:**

```
Is it nullable (Int?) ?
  YES --> Boxed (Integer)
  NO  --> Is it in a generic position?
            YES --> Boxed (Integer)
            NO  --> Primitive (int)
```

### The Complete Mapping Table

| Kotlin | JVM | Boxed? | Why |
|---|---|---|---|
| `Int` | `int` | No | Non-nullable, not generic |
| `Int?` | `Integer` | Yes | Rule 1 |
| `Long` | `long` | No | |
| `Long?` | `Long` | Yes | Rule 1 |
| `Boolean` | `boolean` | No | |
| `Boolean?` | `Boolean` | Yes | Rule 1 |
| `String` | `String` | N/A | Already reference |
| `List<Int>` | `List<Integer>` | Yes | Rule 2 |
| `Any` | `Object` | — | Top type |

### `Any` and `Nothing` — Top and Bottom

Every type in Kotlin sits in a hierarchy. `Any` is at the top — the parent of every non-nullable type. Every class implicitly extends it. It's Kotlin's equivalent of Java's `Object`.

```kotlin
val x: Any = "hello"  // String IS-A Any  ✓
val y: Any = 42        // Int IS-A Any     ✓
val z: Any = User()    // User IS-A Any    ✓
```

This is why `val c: Any = 5` forces boxing — the JVM slot is `Object`, and a raw `int` can't be an `Object`.

At the bottom sits `Nothing` — a subtype of *every* type. No value can ever be `Nothing`. It represents "this never produces a value" (functions that always throw, infinite loops).

```
    Any        (top -- parent of all)
   / | \
String Int  User ...
   \ | /
  Nothing      (bottom -- child of all)
```

`Nothing` is useful because code that never returns can fit anywhere the type system expects a value:

```kotlin
val x: String = throw Exception()
// throw returns Nothing
// Nothing IS-A String  ✓
// So this type-checks

sealed class Result<out T> {
    data class Success<T>(val data: T) : Result<T>()
    data class Error(val e: Throwable) : Result<Nothing>()
    //  Result<Nothing> IS-A Result<T> for any T
    //  because Nothing is bottom type + out variance
}
```

You'll see `Nothing` show up in sealed class patterns throughout [Q2.3](02_classes_and_objects.md#q23--sealed-classes-and-interfaces) and [Q1.3](01_type_system_foundations.md#q13--nothing-unit-and-the-type-hierarchy).

### Boxing Has a Cost

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

In a tight loop, this matters:

```kotlin
// SLOW: List<Integer>, 1M heap objects
for (item in listOf(1, 2, ..., 1_000_000)) {
    sum += item  // unbox each time
}

// FAST: int[], no boxing
for (item in intArrayOf(1, 2, ..., 1_000_000)) {
    sum += item  // direct memory read
}
```

### `IntArray` vs `Array<Int>`

| | `IntArray` | `Array<Int>` |
|---|---|---|
| JVM type | `int[]` | `Integer[]` |
| Storage | Raw primitives | Boxed objects |
| 1M ints | ~4 MB | ~20 MB (5×) |
| Iteration | 1 instruction | load + unbox |
| Use when | Performance | Need nulls |

```kotlin
// ✅ Numeric work
val scores = IntArray(100)

// ❌ Unless you need nullability
val scores = Array<Int>(100) { 0 }  // 5× memory
```

### The Integer Cache Trap

Java caches `Integer` for -128 to 127. Inside: same object. Outside: new object every time.

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

### Connecting to What Comes Next

| Feature | Why Boxing Matters |
|---|---|
| `lateinit var count: Int` | Impossible — null sentinel, int can't be null → [Q5.1](05_properties_and_delegation.md#q51--lateinit-internals) |
| `List<Int>` boxed | Generics erase to Object → [Q3.1](03_generics_and_variance.md#q31--type-erasure) |
| `reified` inline | Defeats erasure at call site → [Q3.3](03_generics_and_variance.md#q33--reified-type-parameters) |
| `inline fun` + lambda | Eliminates Function object → [Q4.2](04_functions_lambdas_inlining.md#q42-inline-noinline-crossinline) |

### Memory Trick

```
WHEN DOES KOTLIN BOX?
  Nullable?  --> Boxed
  Generic?   --> Boxed
  Otherwise  --> Primitive

ARRAY SHORTCUT:
  IntArray   = int[]     = fast
  Array<Int> = Integer[] = 5x memory
```

### Self-Test (Cover Everything Above)

1. What JVM type for `val x: Int = 5`? For `val y: Int? = 5`? Why different?
2. Why does `List<Int>` store boxed Integers?
3. Memory: `IntArray(1_000_000)` vs `Array<Int>(1_000_000)`?
4. Why `127 as Int? === 127 as Int?` → true but `128` → false?
5. Iterating 10M numbers in a game loop — which type?
6. Why does `val x: Any = 5` force boxing? What does `Any` map to on the JVM?

---

## Q0.3 — Class Loading and `init {}` in `object`

> **Connects to:** [Q2.4 (object singleton thread safety)](02_classes_and_objects.md#q24--the-object-keyword) · [Q2.5.4 (companion object init time)](02_5_initialization_mechanics.md#q254--companion-object-and-object-initialization)

### The Concrete Picture

```kotlin
object DatabaseConfig {
    val URL = "jdbc:sqlite:app.db"
    init { println("DatabaseConfig initialized!") }
}

// Somewhere in your app:
val url  = DatabaseConfig.URL  // first access
val url2 = DatabaseConfig.URL  // second access
```

What happens inside the JVM for each access:

```
FIRST ACCESS:  val url = DatabaseConfig.URL
  |
  v
  Is DatabaseConfig loaded? NO
  |
  v
  Load .class --> Verify --> Init
  |                          |
  |               run init {} block
  |               print "DatabaseConfig initialized!"
  v
  Return URL value


SECOND ACCESS:  val url2 = DatabaseConfig.URL
  |
  v
  Is DatabaseConfig loaded? YES
  |
  v
  Return URL immediately (no init, no print)
```

First access pays the cost.
Every access after is instant.
Initialization happens **exactly once, thread-safely**.

### The Three-Phase Pipeline

```
1. LOAD
   ClassLoader reads .class bytes
          |
          v
2. LINK
   a. Verify  (bytecode safety)
   b. Prepare (allocate static fields, zero them)
   c. Resolve (link symbolic references)
          |
          v
3. INITIALIZE
   Run <clinit> (class initializer)
   Kotlin's init {} inside object compiles to here
   Field assignments execute here
```

Phase 3 is where everything interesting happens.

**Kotlin `init {}` vs JVM `<clinit>`:** Kotlin has no `static {}` keyword. You write `init {}` inside an `object` or `companion object`. The compiler places this code inside the JVM's `<clinit>` (class initializer) method. Same mechanism, different syntax. When this document says `<clinit>`, it means "where your `init {}` code ends up in bytecode."

### What Triggers Initialization

This is what interviewers probe:
"Does accessing X trigger class initialization?"

| Access | Triggers Init? | Why |
|---|---|---|
| `new MyClass()` | **Yes** | Instance creation |
| `MyClass.method()` | **Yes** | Static method |
| `MyClass.someVal` | **Yes** | Static field read |
| `MyClass.CONST_VAL` | **No** | Inlined at compile time |
| `MyClass::class` | **No** | Metadata only |
| `Subclass.parentField` | Parent: **Yes** | Parent before child |

```kotlin
object Config {
    const val TAG = "MyApp"        // inlined
    val VERSION = computeVersion() // runtime

    init { println("Config initialized!") }
}

// Does NOT print "Config initialized!":
Log.d(Config.TAG, "hello")
// TAG replaced with "MyApp" at compile time
// Config class never touched

// DOES print "Config initialized!":
Log.d(Config.VERSION, "hello")
// VERSION requires field read --> triggers init
```

### The Thread Safety Guarantee

The JVM spec (§5.5) guarantees:

1. Only **one thread** executes `<clinit>`
2. Other threads **block** until it completes
3. `<clinit>` never runs again

**Free synchronization.** No `synchronized`, no `volatile`, no double-checked locking.

This is why Kotlin `object` = thread-safe singleton:

```kotlin
object SessionManager {
    val resource = ExpensiveResource()
}
```

```java
// Decompiled:
public final class SessionManager {
    public static final SessionManager INSTANCE;

    static {
        // JVM guarantees: once, thread-safe
        INSTANCE = new SessionManager();
    }

    private SessionManager() {}
}
```

JVM class loading IS the singleton pattern.

### Memory Trick

```
TRIGGERS INIT?
  new / method / field read --> YES
  const val / ::class       --> NO

THREAD SAFETY:
  <clinit> = once, one thread, others block
  Kotlin object = free thread-safe singleton
```

### Self-Test (Cover Everything Above)

1. `object Config { const val TAG = "app"; val URL = "..." }` — does `Config.TAG` trigger init? Does `Config.URL`?
2. Why is `object` thread-safe without synchronization?
3. Three phases of class loading — which phase runs `init {}`?
4. Two threads hit `Config.URL` first time simultaneously — what happens?

---

## Q0.4 — The JVM Call Stack

> **Connects to:** [Q1.1 (val getter overhead)](01_type_system_foundations.md#q11--val-vs-const-val) · [Q4.2 (inline eliminates method call)](04_functions_lambdas_inlining.md#q42-inline-noinline-crossinline)

### The Concrete Picture

Every method call pushes a frame.
Every return pops it off.

```
main() calls loadData()
  calls processUser()


AT DEEPEST POINT:

  | processUser() |  <-- top
  |________________|
  | loadData()     |
  |________________|
  | main()         |
  |________________|


AFTER processUser() RETURNS:

  | loadData()     |  <-- top
  |________________|
  | main()         |
  |________________|

  processUser()'s frame is gone.
  All its local variables destroyed.
```

### What's Inside a Stack Frame

Each frame contains:
- **Local variable table** — params + locals
- **Operand stack** — temporary scratch space for math. The JVM has no registers — it pushes values here, operates on them, pops the result. Like a calculator that works one step at a time.
- **Return address** — where to continue after return

### Why Method Calls Cost More Than Field Reads

**Field read — 1 instruction:**

```
GETFIELD MyClass.value : int
  (read from known memory offset)
```

**Getter call — 4 steps:**

```
INVOKEVIRTUAL MyClass.getValue()
  1. Look up method in vtable
  2. Push new stack frame
  3. GETFIELD MyClass.value
  4. Pop frame, return value
```

For `final` classes, JIT inlines this away.
For `open` classes, the vtable lookup stays.

### Virtual Dispatch vs Direct Call

| Type | Instruction | When | Overhead |
|---|---|---|---|
| Virtual | `INVOKEVIRTUAL` | `open` methods | vtable lookup |
| Interface | `INVOKEINTERFACE` | Interface calls | **slowest** |
| Direct | `INVOKESPECIAL` | `private`, `super` | none |
| Static | `INVOKESTATIC` | Top-level, extensions | none |

**Speed ranking:**

```
FASTEST                        SLOWEST
static/special > virtual > interface
  (direct)       (vtable)   (itable)
```

### Why `final` by Default Is a Performance Feature

`final` class → JIT knows no subclass overrides → **devirtualize** (replace vtable lookup with direct jump):

```kotlin
// final (Kotlin default) → JIT inlines entirely
class Calculator {
    fun add(a: Int, b: Int) = a + b
}

// open → vtable lookup stays
open class OpenCalc {
    open fun add(a: Int, b: Int) = a + b
}
```

### Why This Matters on Android

A lambda `{ doStuff() }` passed to a
non-inline function:

```
() -> Unit
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

This is why `let`, `apply`, `also`, `map`, `filter` are ALL `inline`. See [Q4.2](04_functions_lambdas_inlining.md#q42-inline-noinline-crossinline).

### Memory Trick

```
CALL COST:
  field read  = 1 instruction
  method call = vtable + frame + field + frame

DISPATCH:
  final  --> devirtualize --> fast
  open   --> vtable stays --> slower
  inline --> no call at all --> fastest
```

### Self-Test (Cover Everything Above)

1. What's inside a stack frame? (3 things)
2. Why is `GETFIELD` faster than a getter call?
3. Lambda passed to non-inline function — what bytecode instruction? Why slowest?
4. Why does `final` by default help JIT?

---

## Q0.5 — Code Execution Pipeline: .kt to Running Code

> **Connects to:** [Q3.1 (Type Erasure)](03_generics_and_variance.md#q31--type-erasure) · [Q4.2 (inline)](04_functions_lambdas_inlining.md#q42-inline-noinline-crossinline) · [Q16.4 (Zygote and App Startup)](16_android_system_internals.md#q164--zygote-and-app-startup)

### The 30-Second Answer (Memorize This)

```
.kt --> kotlinc --> .class --> d8 --> .dex --> ART

Desktop: interpret first, JIT hot code
Android: AOT at install, profile-guided later
```

That's the interview answer.
Everything below is the deep version.

### The Pieces: JDK, JRE, JVM, JIT

Before the pipeline — what are all these acronyms? They nest inside each other:

```
JDK (Java Development Kit)
|
|  YOUR development tools:
|    kotlinc, javac, d8, debugger, profiler
|
|  JRE (Java Runtime Environment)
|  |
|  |  Class libraries:
|  |    java.lang, java.util, java.io, etc.
|  |
|  |  JVM (Java Virtual Machine)
|  |  |
|  |  |  ClassLoader
|  |  |    loads .class files
|  |  |
|  |  |  Interpreter
|  |  |    executes bytecode (slow, correct)
|  |  |
|  |  |  JIT Compiler (Just-In-Time)
|  |  |    compiles hot bytecode --> native
|  |  |    (C1 = quick, C2 = aggressive)
|  |  |
|  |  |  Memory Manager
|  |  |    heap, stack, garbage collector
```

**How each piece maps to the pipeline:**

| Piece | What it does | When |
|---|---|---|
| **JDK** | Contains `kotlinc` and `d8` that compile your code | Build time (your machine) |
| **JRE** | Provides standard libraries your code calls (`List`, `String`, etc.) | Runtime |
| **JVM** | Loads bytecode, manages memory, runs your program | Runtime |
| **JIT** | Inside the JVM — compiles hot methods to native machine code | Runtime (after enough calls) |

**The key insight:** You only need the JDK to *build*. Users only need the JRE to *run*. The JIT lives inside the JVM and works silently — you never call it directly.

**On Android**, this picture changes: there is no JRE or JVM. Android replaces both with **ART** (Android Runtime), which does its own class loading, memory management, and AOT/JIT compilation. But the JDK tools (`kotlinc`, `d8`) are still what build your code.

```
Desktop:  JDK (build) --> JRE + JVM + JIT (run)
Android:  JDK (build) --> ART replaces everything (run)
```

### The Full Pipeline

```
STAGE 1: COMPILE TIME (your machine)
==========================================
.kt source
  |  kotlinc
  v
Parse       (text --> AST tree)
  |
Type check  (infer types, null safety)
  |
Desugar     (Kotlin features --> JVM equivalents)
  |
Emit        (.class files with bytecode)


STAGE 2: BYTECODE
==========================================
.class files = stack-based instructions
  ICONST_2, ICONST_3, IMUL
  = push 2, push 3, multiply = 6
  ~200 opcodes total

Desktop: JVM loads .class directly
Android: d8 converts .class --> .dex


STAGE 3: RUNTIME
==========================================
Desktop JVM (HotSpot):
  Interpret first (slow, correct)
  --> JIT compiles hot methods
  --> Native speed

Android ART:
  AOT at install time (pre-compiled)
  --> Profile-guided recompilation
  --> Hot paths native on next launch
```

### What kotlinc Desugars

The compiler rewrites Kotlin features into JVM equivalents:

| Kotlin | Desugars To |
|---|---|
| `data class` | `equals` + `hashCode` + `copy` + `componentN` |
| `suspend fun` | State machine + `Continuation` — [Q9.1](09_coroutines_execution_mechanics.md#q91--what-suspend-actually-does) |
| `inline fun { }` | Body pasted at call site — [Q4.2](04_functions_lambdas_inlining.md#q42-inline-noinline-crossinline) |
| `a + b` (operator) | `a.plus(b)` method call |
| `for (i in 1..10)` | `while` loop with counter |
| `{ x -> x + 1 }` | Anonymous `Function1` class |

**After desugaring, there's no "Kotlin" left.** The `.class` file is pure JVM bytecode.

### JIT: Why Hot Code Gets Fast

```
CALL COUNT       MODE          SPEED
--------------------------------------------
1 - 100          Interpreted   Slow
100 - 10,000     C1 compiled   Moderate
10,000+          C2 compiled   Full native
```

**Optimizations that matter for interviews:**

1. **Method inlining** — hot methods pasted at call site. Kotlin `inline` does this at compile time for lambdas.

2. **Devirtualization** — JIT profiles types at call sites. If always `Dog`, replaces vtable lookup with direct call.

3. **Escape analysis** — object never leaves method? Allocate on stack, skip GC.

### Desktop JVM vs Android ART

| | Desktop (HotSpot) | Android (ART) |
|---|---|---|
| When | Runtime (JIT) | Install (AOT) + runtime |
| Cold start | Slow | Fast |
| Peak speed | Very high | High |
| Warm-up? | Yes (10-30s) | Minimal |

**Android interview connection:** Baseline Profiles give ART a list of hot methods to AOT-compile at install time. Google Maps, Meta, Zomato report ~30% startup improvement. See [Q17.3](17_performance_and_memory.md#q173--the-16ms-budget).

### Memory Trick

```
NESTING:
  JDK > JRE > JVM > JIT
  Build    Runtime
  Android: ART replaces JRE + JVM + JIT

TWO COMPILERS:
  kotlinc = your machine, produces bytecode
  JIT/ART = user's device, produces native code

DESUGARING = "no Kotlin at runtime"
  suspend --> state machine
  inline  --> pasted body
  data    --> equals + hashCode + copy
  lambda  --> Function object (unless inline)

ANDROID vs DESKTOP:
  Desktop: start slow, get fast
  Android: start fast, get faster
```

### Self-Test (Cover Everything Above)

1. What's the nesting: JDK contains what? JRE contains what? Where does JIT live?
2. 4 things kotlinc does during compilation?
3. After compilation — any "Kotlin" left in .class?
4. Desktop JVM vs Android ART — key difference?
5. Why do Baseline Profiles improve startup?
6. Method called 50,000 times — what tier? What optimizations?

---

## Master Summary: Phase 0

> Everything in this guide traces back to one tension: **primitives live as raw values, Objects live on the heap behind pointers.** Kotlin's features exist to bridge, optimize, or work around this split.

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

### Final Self-Test: All of Phase 0

One question per section. No scrolling up.
If you can answer all five, Phase 0 is solid.

1. **(Q0.1)** Why can't `int` be null? Explain using bit patterns, not language rules.
2. **(Q0.2)** What two conditions force Kotlin to box a primitive? What's the memory cost of `Array<Int>` vs `IntArray` for 1M elements?
3. **(Q0.3)** `object Config { const val TAG = "x"; val URL = "y" }` — which access triggers `init {}` and which doesn't? Why?
4. **(Q0.4)** A lambda passed to a non-inline function — what dispatch instruction runs it? Why is `inline` faster?
5. **(Q0.5)** What does kotlinc produce? What does the JIT do with it? How does Android ART differ from Desktop JVM?

---

*Next: [Phase 1 — Type System Foundations →](01_type_system_foundations.md)*
