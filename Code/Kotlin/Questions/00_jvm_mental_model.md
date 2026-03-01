# Phase 0: JVM Mental Model

> **Must be understood first — every phase builds on this.**

## Navigation
[← Master Index](master_chains.md)

## Questions in This File
- [Q0.1 — Primitives vs References](#q01--primitives-vs-references)
- [Q0.2 — JVM Type Mapping](#q02--jvm-type-mapping)
- [Q0.3 — Class Loading and the `static {}` Block](#q03--class-loading-and-the-static--block)
- [Q0.4 — The JVM Call Stack](#q04--the-jvm-call-stack)
- [Q0.5 — Code Execution Pipeline: .kt to Running Code](#q05--code-execution-pipeline-kt-to-running-code)

---

## Q0.1 — Primitives vs References

> **Connects to:** [Q1.1 (val stores primitives)](01_type_system_foundations.md#q11--val-vs-const-val) · [Q5.1 (lateinit can't use null with primitives)](05_properties_and_delegation.md#q51--lateinit-internals) · [Q3.3 (reified erases to Object)](03_generics_and_variance.md#q33--reified-type-parameters)

### First Principles: Why Two Kinds of Types?

The JVM was designed in the mid-1990s to run on machines with limited memory. Two competing needs:
1. **Performance** — numeric data must be fast (no pointer indirection)
2. **Polymorphism** — everything must fit into a common `Object` container

The solution: **two type systems** living side by side.

---

### What is a JVM Primitive?

A **primitive** is a value that lives **directly** in memory — no pointer, no header, no identity.

| Primitive | Size | Default | JVM mnemonic |
|-----------|------|---------|--------------|
| `byte` | 8 bits | `0` | `B` |
| `short` | 16 bits | `0` | `S` |
| `int` | 32 bits | `0` | `I` |
| `long` | 64 bits | `0L` | `J` |
| `float` | 32 bits | `0.0f` | `F` |
| `double` | 64 bits | `0.0` | `D` |
| `boolean` | 1 bit (JVM uses int) | `false` | `Z` |
| `char` | 16 bits (Unicode) | `'\u0000'` | `C` |

A **reference type** is a pointer (4 or 8 bytes) to an object on the heap. The object itself has:
- **Object header** (8–16 bytes): class pointer + mark word (GC/lock info)
- **Fields**: actual data

```
PRIMITIVE (int x = 42):            REFERENCE (Integer x = 42):

Stack Frame                         Stack Frame        Heap
┌──────────────┐                   ┌──────────────┐   ┌──────────────────┐
│  x = 42      │ ← value is HERE   │  x = 0x7f3a  │──▶│ Object header    │
└──────────────┘                   └──────────────┘   │ (16 bytes)       │
                                                       │ value = 42       │
                                                       └──────────────────┘
```

### Why Do Primitives Have Default Values But References Default to `null`?

**Primitives default to zero** because the JVM guarantees that class fields are zero-initialized before the `<init>` method runs. This maps naturally: `0` for numbers, `false` for boolean, `'\u0000'` for char.

**Reference types default to `null`** because `null` is the "no object pointed to" sentinel — a zero/empty pointer (typically the literal address `0x0` or a reserved null-pointer region).

```kotlin
class Example {
    var count: Int = 0          // JVM guarantee: zero-initialized → 0
    var name: String? = null    // JVM guarantee: zero-initialized → null pointer
    var flag: Boolean = false   // zero-initialized → false
}
```

> **Interview Answer:** Primitives are value types stored directly; the JVM zeroes all memory before initialization, so their zero-value IS the default. References are pointers; a pointer-to-nothing is `null` (address zero). This isn't a language choice — it's the JVM memory model.

---

### Stack vs Heap

```
                    JVM Memory Layout
┌─────────────────────────────────────────────────────┐
│  METHOD AREA (Metaspace)                            │
│  Class definitions, static fields, bytecode        │
├─────────────────────────────────────────────────────┤
│  HEAP                                               │
│  ┌─────────────────────────────────────────────┐   │
│  │  Young Gen    │  Old Gen   │  (String pool)  │   │
│  │  new objects  │  survived  │                 │   │
│  └─────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────┤
│  STACK (one per thread)                             │
│  ┌────────────────────┐                             │
│  │  Frame: main()     │ ← current method            │
│  │   int x = 5        │   primitive stored HERE     │
│  │   String* s = ───────────────────────────────▶  │
│  ├────────────────────┤                             │
│  │  Frame: foo()      │ ← calling method            │
│  └────────────────────┘                             │
└─────────────────────────────────────────────────────┘
```

- **Local primitive variables** (`int`, `boolean`, `long`) live on the **stack** inside their method's frame.
- **Objects** always live on the **heap**.
- **Local reference variables** are on the **stack** — but they *point into* the heap.
- **Instance/static fields** live in the object on the heap (or Metaspace for `static`).

```kotlin
fun compute() {
    val x = 42          // int on stack — no heap allocation
    val s = "hello"     // reference on stack → String object on heap
    val n = Integer(42) // reference on stack → Integer object on heap
}
```

---

### Boxing and Unboxing

**Boxing** = wrapping a primitive in a reference type object.
**Unboxing** = extracting the primitive from the wrapper object.

```java
// Java — explicit boxing visible
int x = 5;
Integer boxed = Integer.valueOf(x);  // Boxing: allocates heap object
int back = boxed.intValue();          // Unboxing: reads field, discards object
```

```kotlin
// Kotlin — same thing happens invisibly
var x: Int = 5          // → int (primitive)
var y: Int? = x         // → Integer (boxed!) — Int? maps to java.lang.Integer
```

**Bytecode for boxing:**
```bytecode
BIPUSH 5
INVOKESTATIC java/lang/Integer.valueOf (I)Ljava/lang/Integer;  // Boxing
```

**Runtime cost of boxing:**
1. **Heap allocation** — GC must eventually collect the wrapper
2. **Cache miss** — wrapper on heap, value accessed via pointer (indirection)
3. **Integer cache only -128 to 127** — outside this range, every box is a fresh allocation

```kotlin
// TRAP: boxing in a hot loop
fun sumBoxed(list: List<Int>): Int {  // List<Int> = List<Integer> on JVM
    var sum = 0
    for (item in list) {              // unbox Integer → int on every iteration
        sum += item
    }
    return sum
}

// BETTER: use IntArray (primitive array)
fun sumPrimitive(arr: IntArray): Int {
    var sum = 0
    for (item in arr) {   // no boxing — directly reads int
        sum += item
    }
    return sum
}
```

> **Key Takeaway:** Boxing is automatic but not free. Every `Int?`, every [`List<Int>`](00_jvm_mental_model.md#q02--jvm-type-mapping), every generic container that holds an `Int` forces [boxing](00_jvm_mental_model.md#q02--jvm-type-mapping). In tight loops or large datasets, this causes measurable GC pressure.

---

## Q0.2 — JVM Type Mapping

> **Connects to:** [Q5.1 (why lateinit forbids Int)](05_properties_and_delegation.md#q51--lateinit-internals) · [Q3.1 (erasure works on Object)](03_generics_and_variance.md#q31--type-erasure) · [Q7.1 (IntArray vs Array)](07_collections_and_sequences.md#q71--kotlins-collection-hierarchy)

### Kotlin Type → JVM Type Mapping

| Kotlin Type | JVM Type | Boxed? | Notes |
|-------------|----------|--------|-------|
| `Int` | `int` | No | When not nullable or in generics |
| `Int?` | `java.lang.Integer` | Yes | Always boxed |
| `Long` | `long` | No | |
| `Long?` | `java.lang.Long` | Yes | |
| `Boolean` | `boolean` | No | |
| `Boolean?` | `java.lang.Boolean` | Yes | |
| `Double` | `double` | No | |
| `Double?` | `java.lang.Double` | Yes | |
| `String` | `java.lang.String` | N/A | Already a reference type |
| `String?` | `java.lang.String` | N/A | Same type, null allowed |
| `IntArray` | `int[]` | No | Primitive array |
| `Array<Int>` | `Integer[]` | Yes | Object array, always boxed |
| `List<Int>` | `List<Integer>` | Yes | Generics erase to Object |

### The Rule: When Does Kotlin Box?

```
Kotlin boxes Int when:
1. The type is nullable: Int?
2. The type appears in a generic position: List<Int>, Map<String, Int>
3. The receiver of an extension function on a nullable type
4. Any position that requires an Object (e.g., interface Any)
```

```kotlin
// Decompiled view of what the Kotlin compiler does:

val a: Int = 5           // → int a = 5;          (primitive)
val b: Int? = 5          // → Integer b = 5;       (boxed)
val c: Any = 5           // → Object c = Integer.valueOf(5); (boxed — Any = Object)

fun takes(x: Int) {}     // → takes(int x)         (primitive param)
fun takes(x: Int?) {}    // → takes(Integer x)      (boxed param)
```

### Why `List<Int>` Always Boxes

Java's generics use **type erasure** — at runtime, `List<String>`, `List<Int>`, and `List<Animal>` are ALL just `List`. The JVM only knows the *erased* type, which must be an **Object**.

Since `int` (primitive) is not an Object, the JVM cannot store it in `List`. It must box it to `Integer`.

```kotlin
val list = listOf(1, 2, 3)
// At JVM level: List<Integer> containing boxed Integer objects
// NOT: List<int> — that's impossible in Java generics
```

### `IntArray` vs `Array<Int>` Performance

```kotlin
// IntArray = int[] in JVM (primitive array — no boxing)
val primitiveArray = IntArray(1_000_000) { it }

// Array<Int> = Integer[] in JVM (object array — all boxed)
val boxedArray = Array<Int>(1_000_000) { it }
```

**Memory comparison for 1 million integers:**
```
IntArray:   4 bytes × 1,000,000 = ~4 MB (+ small array header)
Array<Int>: 16 bytes × 1,000,000 = ~16 MB (Integer object headers)
            + 4 bytes × 1,000,000 =  ~4 MB (references in array)
            Total: ~20 MB — 5× more memory!
```

**Iteration bytecode:**

```bytecode
// IntArray iteration:
IALOAD   ; load int from primitive array — direct memory read

// Array<Int> iteration:
AALOAD   ; load reference (Integer) from object array
INVOKEVIRTUAL java/lang/Integer.intValue  ; unbox on every access
```

> **Key Takeaway:** For numeric arrays in performance-sensitive code (data processing, image manipulation, game loops), always use `IntArray`, `LongArray`, `FloatArray` — never `Array<Int>`.

---

## Q0.3 — Class Loading and the `static {}` Block

> **Connects to:** [Q2.4 (object singleton thread safety)](02_classes_and_objects.md#q24--the-object-keyword) · [Q2.5.4 (companion object init time)](02_5_initialization_mechanics.md#q254--companion-object-and-object-initialization)

### JVM Class Loading Lifecycle

```
               JVM Class Loading Pipeline
┌──────────────────────────────────────────────────────┐
│                                                      │
│  1. LOAD                                             │
│     ClassLoader reads .class file from disk/jar     │
│     Creates Class object in Metaspace                │
│                    │                                 │
│                    ▼                                 │
│  2. LINK                                             │
│     a. VERIFY   — bytecode safety checks             │
│     b. PREPARE  — allocate static fields, set to 0  │
│     c. RESOLVE  — resolve symbolic references        │
│                    │                                 │
│                    ▼                                 │
│  3. INITIALIZE                                       │
│     Run <clinit> (class initializer / static block) │
│     Assign static field values                       │
│     Run [companion object](02_classes_and_objects.md#q24--the-object-keyword) initializers                │
│                                                      │
└──────────────────────────────────────────────────────┘
```

### When Does `static {}` Run?

The class initializer (`<clinit>`) runs **exactly once**, the first time any of the following occur:
1. An instance of the class is created (`new`)
2. A static method of the class is called
3. A static field of the class is **read or written** (unless it's a `compile-time constant`)

```kotlin
object DatabaseConfig {
    val URL = "jdbc:sqlite:app.db"  // triggers <clinit> on first access
    init {
        println("DatabaseConfig initialized!")
    }
}

// This triggers class loading + initialization:
val url = DatabaseConfig.URL  // prints: "DatabaseConfig initialized!"

// Second access: NO re-initialization (already done)
val url2 = DatabaseConfig.URL  // prints nothing
```

**Exception:** [`const val`](01_type_system_foundations.md#q11--val-vs-const-val) (compile-time constant) is **inlined at the call site** — the class is never loaded!

```kotlin
object Constants {
    const val TAG = "MyApp"   // inlined at call site, never triggers class loading
    val VERSION = "1.0"       // triggers class loading when accessed
}

// This compiles to: Log.d("MyApp", ...) — no class loading!
Log.d(Constants.TAG, "message")
```

### Thread Safety Guarantee

The JVM specification (§5.5) guarantees that class initialization is **thread-safe by design**:
- Only one thread executes `<clinit>`
- Other threads trying to access the class block until initialization completes
- The JVM uses an internal lock per class

This is why Kotlin `object` (singleton) is thread-safe:

```kotlin
object Singleton {
    // Initialized in <clinit> — JVM guarantees single-threaded execution
    val instance = ExpensiveResource()
}
```

```java
// Decompiled — what JVM sees:
public final class Singleton {
    public static final Singleton INSTANCE;

    static {  // <clinit> — JVM guarantees: runs once, thread-safe
        INSTANCE = new Singleton();
    }

    private Singleton() {}
}
```

> **Key Takeaway:** The JVM class initialization lock is what makes Kotlin `object` a free, thread-safe singleton — no `synchronized`, no `volatile`, no double-checked locking needed.

---

## Q0.4 — The JVM Call Stack

> **Connects to:** [Q1.1 (val getter overhead)](01_type_system_foundations.md#q11--val-vs-const-val) · [Q4.2 (inline eliminates method call)](04_functions_lambdas_inlining.md#q42-inline-noinline-crossinline)

### What Is a Stack Frame?

Every method call creates a **stack frame** on the thread's call stack. The frame contains:
- **Local variable table** — parameters and local variables (primitives stored directly, references stored as addresses)
- **Operand stack** — working area for computations (the JVM's "registers")
- **Return address** — where to jump when the method returns
- **Reference to constant pool** — for resolving class/method names

```
           Thread Stack (grows downward)
┌──────────────────────────────────────┐  ← Stack top (current frame)
│  Frame: processUser(user: User)      │
│  ┌─────────────────────────────┐    │
│  │ Local vars: user=0x7f3a     │    │  ← reference to User on heap
│  │             result=0        │    │  ← int stored directly
│  │ Operand stack: [temp vals]  │    │
│  └─────────────────────────────┘    │
├──────────────────────────────────────┤
│  Frame: loadData()                   │
│  ┌─────────────────────────────┐    │
│  │ Local vars: ...             │    │
│  └─────────────────────────────┘    │
├──────────────────────────────────────┤
│  Frame: main()                       │
└──────────────────────────────────────┘  ← Stack bottom
```

**Stack frame allocation cost:** Pushing a frame requires updating the stack pointer and initializing local variable slots. It's fast (nanoseconds), but not zero — calling a method has overhead vs reading a field directly.

### Why Does Calling a Getter Cost More Than Reading a Field?

**Accessing a field directly:**
```bytecode
GETFIELD com/example/MyClass.value : I   ; 1 instruction — read from object offset
```

**Calling a getter:**
```bytecode
ALOAD_0                                 ; push `this` onto operand stack
INVOKEVIRTUAL com/example/MyClass.getValue ()I  ; dispatch + new stack frame
; ... inside getValue():
ALOAD_0                                 ; push `this` again
GETFIELD com/example/MyClass.value : I  ; read field
IRETURN                                 ; return, pop frame
```

The getter requires:
1. Virtual method dispatch (look up vtable)
2. New stack frame pushed
3. Field access inside getter
4. Frame popped on return

For a simple getter on a `final` class, the JIT compiler will [**inline it**](04_functions_lambdas_inlining.md#q42--inline-noinline-crossinline) and eliminate the overhead. But in hot paths with non-final classes, the virtual dispatch overhead is real.

### Virtual Method Dispatch vs Direct Call

```
Virtual Dispatch (open/interface methods):
┌──────────────────────────────────────────────────────┐
│  Object has vtable pointer                           │
│  object.method()                                     │
│     │                                                │
│     ├─ Load vtable address from object header        │
│     ├─ Look up method index in vtable               │
│     └─ Jump to method address                       │
│                                                      │
│  Vtable for Dog (extends Animal):                    │
│  [0] → Object.toString()                            │
│  [1] → Animal.breathe()                             │
│  [2] → Dog.speak()  ← overridden                   │
└──────────────────────────────────────────────────────┘

Direct Call (final/private methods):
┌──────────────────────────────────────────────────────┐
│  INVOKESPECIAL or INVOKESTATIC                       │
│  Compile-time resolved — no vtable lookup            │
│  Jump directly to method address                     │
└──────────────────────────────────────────────────────┘
```

| Call Type | Bytecode Instruction | When Used | Cost |
|-----------|---------------------|-----------|------|
| Virtual dispatch | `INVOKEVIRTUAL` | Open/override methods | vtable lookup |
| Interface dispatch | `INVOKEINTERFACE` | Interface methods | vtable lookup (slower!) |
| Direct call | `INVOKESPECIAL` | Private, constructors, `super` | No lookup |
| Static call | `INVOKESTATIC` | Static methods, extensions | No lookup |

**Why Kotlin's `final` default matters:**
When a class is [`final`](02_classes_and_objects.md#q21--class-modifiers), the JIT compiler knows there's only ONE possible implementation. It can devirtualize the call — replacing the vtable lookup with a direct jump. This is a significant optimization for frequently called methods.

```kotlin
// Kotlin: final by default → INVOKEVIRTUAL but JIT can devirtualize
class Calculator {
    fun add(a: Int, b: Int) = a + b  // JIT can inline this
}

// open: JIT must keep virtual dispatch (unknown subclass might override)
open class OpenCalculator {
    open fun add(a: Int, b: Int) = a + b  // harder for JIT to optimize
}
```

> **Key Takeaway:** Virtual dispatch adds indirection. Kotlin's `final` default isn't just about safety — it's about enabling JIT optimizations. Every `open` method is a potential polymorphism point the JIT must remain pessimistic about.

---

## Q0.5 — Code Execution Pipeline: .kt to Running Code

> **Builds on:** [Q0.3 — Class Loading](00_jvm_mental_model.md#q03--class-loading-and-the-static--block) · [Q0.4 — The JVM Call Stack](00_jvm_mental_model.md#q04--the-jvm-call-stack)
> **Connects to:** [Q3.1 — Type Erasure](03_generics_and_variance.md#q31--type-erasure) · [Q3.3 — Reified](03_generics_and_variance.md#q33--reified-type-parameters) · [Q4.2 — inline](04_functions_lambdas_inlining.md#q42--inline-noinline-crossinline) · [Q16.4 — Zygote and App Startup](16_android_system_internals.md#q164--zygote-and-app-startup)

### The Big Picture: From Source to Electrons

Before any code can run, it must travel through several transformation layers. Each layer speaks a different "language": your source code speaks Kotlin, the JVM speaks bytecode, your CPU speaks machine code. Compilers and runtimes are the translators between each layer.

```
  Your .kt file                              Running on CPU
 (human-readable)                           (machine code)

   .kt source                                  Native
      │                                        Code
      │ kotlinc                                  ▲
      │ (Kotlin compiler)                        │
      ▼                                       JIT/AOT
   .class file         ClassLoader           Compiler
  (JVM bytecode)  ────────────────▶  JVM ─────────────▶  Run
```

---

### Stage 1 — Compilation: kotlinc Turns .kt Into .class

The Kotlin compiler (`kotlinc`) takes your `.kt` source file and produces `.class` files containing **JVM bytecode**.

```
Input:  MyClass.kt  (Kotlin source — human-readable text)
Output: MyClass.class (JVM bytecode — binary, not text)
```

What `kotlinc` does during compilation:

**1. Parsing — Kotlin source → Abstract Syntax Tree (AST)**

The compiler reads your text and builds a tree structure representing the program's meaning:
```
val x = 1 + 2 * 3

AST:
  Assignment
  ├── target: "x"
  └── value: BinaryOp(+)
              ├── 1
              └── BinaryOp(*)
                    ├── 2
                    └── 3
```

**2. Type checking and inference**

The compiler infers and verifies types across the entire program:
```kotlin
val x = 1 + 2      // compiler infers: x: Int
val y: String = x  // COMPILE ERROR caught here — Int ≠ String
```

All null safety checks, smart cast checks, and variance rules are enforced at this stage. If your code compiles, the compiler has mathematically proven these properties hold.

**3. Desugaring — Kotlin features → simpler equivalents**

Many Kotlin features are "syntactic sugar" — the compiler rewrites them into simpler forms before generating bytecode:

```kotlin
// Your Kotlin code:
val doubled = listOf(1, 2, 3).map { it * 2 }

// Desugared to (approximately):
val lambda = object : Function1<Int, Int> {
    override fun invoke(it: Int): Int = it * 2
}
val doubled = listOf(1, 2, 3).map(lambda)
```

Other desugaring examples:
- Data classes → auto-generated `equals()`, `hashCode()`, `copy()`, `componentN()`
- `suspend` functions → state machine classes (see [Q9.1](09_coroutines_execution_mechanics.md#q91--what-suspend-actually-does))
- `inline` lambdas → body pasted at call site (see [Q4.2](04_functions_lambdas_inlining.md#q42--inline-noinline-crossinline))
- Operator overloads → method calls (`a + b` → `a.plus(b)`)
- `for` loops over ranges → while loops with counters

**4. Code generation — AST → JVM bytecode**

The compiler emits `.class` files containing JVM bytecode. These files follow a strict binary format (defined in the JVM specification) and can be read by any JVM.

---

### Stage 2 — What Is Bytecode? A Platform-Neutral Language

**Bytecode** is an intermediate language designed for the JVM — not for your specific CPU (x86, ARM, etc.), but for a virtual "ideal" CPU. This is the "write once, run anywhere" trick: any machine that has a JVM can run the same `.class` file.

The JVM is a **stack-based** virtual machine. Instead of registers (like real CPUs), it uses an **operand stack** for computation:

```kotlin
// Kotlin source:
val result = 1 + 2 * 3
```

```bytecode
; JVM bytecode (human-readable form shown with mnemonics):
ICONST_1      ; push constant 1 onto operand stack     → stack: [1]
ICONST_2      ; push constant 2                        → stack: [1, 2]
ICONST_3      ; push constant 3                        → stack: [1, 2, 3]
IMUL          ; pop 2 and 3, push 2*3=6                → stack: [1, 6]
IADD          ; pop 1 and 6, push 1+6=7                → stack: [7]
ISTORE_1      ; pop 7, store in local variable slot 1  → stack: []
```

Each instruction is a single byte (hence "bytecode") followed by optional arguments. The full instruction set has ~200 opcodes covering arithmetic, comparisons, control flow, method calls, and object creation.

**Key bytecode instructions you'll see in decompiled Kotlin:**

| Instruction | Meaning |
|------------|---------|
| `ICONST_n` | Push integer constant n |
| `ILOAD_n` | Load int from local variable slot n |
| `ISTORE_n` | Store int to local variable slot n |
| `IADD / IMUL` | Integer add / multiply |
| `INVOKEVIRTUAL` | Call instance method (virtual dispatch) |
| `INVOKESTATIC` | Call static method (direct) |
| `INVOKESPECIAL` | Call constructor or private method |
| `GETFIELD / PUTFIELD` | Read/write object fields |
| `NEW` | Allocate new object |
| `CHECKCAST` | Assert type (inserted by erasure) |
| `INSTANCEOF` | Type check |
| `RETURN / IRETURN` | Return void / int from method |

---

### Stage 3 — JVM Startup: ClassLoader Loads Your .class Files

When you launch your app, the JVM starts and the [ClassLoader](00_jvm_mental_model.md#q03--class-loading-and-the-static--block) loads `.class` files into memory as needed:

```
JVM Start
  │
  ├─ Bootstrap ClassLoader loads JDK core classes (java.lang.*, java.util.*)
  ├─ Application ClassLoader loads your app's .class files
  │
  └─ Classes are loaded LAZILY — only when first referenced
      (not all at startup — see Q0.3)
```

After loading, the JVM:
1. **Verifies** bytecode — checks for safety violations (no stack underflow, type mismatches, illegal memory access). This is what lets the JVM guarantee memory safety even for untrusted code.
2. **Prepares** — allocates static fields and sets them to zero/null
3. **Initializes** — runs the `<clinit>` static initializer block

---

### Stage 4 — Interpretation: Running Bytecode the Slow Way

When a method is first called, the JVM **interprets** the bytecode — it reads each instruction and executes it one by one. This is safe, correct, but **slow**: ~10–50× slower than native code.

```
JVM Interpreter:
  read opcode byte
  execute corresponding C++ code
  advance program counter
  repeat
```

The interpreter works correctly for ALL code, but high-performance code needs something faster. That's where JIT comes in.

---

### Stage 5 — JIT Compilation: Turning Hot Code into Native Machine Code

**JIT = Just-In-Time.** The JVM monitors which methods are called frequently ("hot methods") and compiles them to **native machine code** — real CPU instructions for your specific hardware. These run at full hardware speed with no interpretation overhead.

**How the JVM decides what to compile:**

The JVM keeps a **call counter** per method. When a method exceeds the **compilation threshold**, the JIT kicks in:

```
Method called 1,000 times   → Level 1 compilation (quick and dirty)
Method called 5,000 times   → Level 2 compilation (more optimization)
Method called 10,000 times  → Level 4 compilation (maximum optimization)
```

This is called **Tiered Compilation** (introduced in Java 7, the default since Java 8):

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    JVM Tiered Compilation Levels                        │
│                                                                         │
│  Level 0 — Pure Interpretation                                          │
│    • Interpreter executes bytecode directly                             │
│    • Profiling counters start accumulating                              │
│    • Slowest execution speed                                            │
│                                                                         │
│  Level 1 — C1 (Client Compiler) — Simple Profiling                      │
│    • Fast compilation to native code (milliseconds)                     │
│    • Basic optimizations: inlining small methods                        │
│    • Continues profiling (branch frequencies, type profiles)            │
│    • ~3–5× faster than Level 0                                          │
│                                                                         │
│  Level 2 — C1 — Limited Profiling                                        │
│    • C1 compiled with less profiling overhead                           │
│    • Used when C2 compiler queue is full                                │
│                                                                         │
│  Level 3 — C1 — Full Profiling                                           │
│    • Full profiling: captures branch outcomes, receiver types           │
│    • Feeds profile data to C2 for better optimization                   │
│                                                                         │
│  Level 4 — C2 (Server Compiler) — Maximum Optimization                  │
│    • Slow to compile (tens to hundreds of milliseconds)                 │
│    • Uses profiling data for aggressive optimizations                   │
│    • ~10–100× faster than interpreted code                              │
│    • Native code cached until deoptimization needed                     │
└─────────────────────────────────────────────────────────────────────────┘
```

**A method's journey through the levels:**

```
myMethod() first call:
  Level 0 (interpreted) → call counter increments

After ~100 calls:
  Level 1 (C1 quick) → native code, basic profiling continues

After ~2,000 calls:
  Level 3 (C1 full profile) → rich profiling data collected

After ~15,000 calls:
  Level 4 (C2) → uses profile data for maximum optimization
  Compiled native code cached → future calls run at full speed
```

---

### Stage 6 — What JIT Optimizations Actually Do

**1. Method Inlining — Eliminating the Call Overhead**

The JIT's most important optimization. Small, frequently-called methods get copy-pasted at the call site:

```kotlin
// Source:
fun square(x: Int) = x * x

fun compute(n: Int): Int {
    return square(n) + square(n + 1)
}
```

After JIT inlining:
```kotlin
// What the native code effectively does:
fun compute(n: Int): Int {
    return (n * n) + ((n + 1) * (n + 1))  // square() body inlined!
}
```

No stack frame push, no `INVOKEVIRTUAL` — the method call disappears entirely. This is why Kotlin's `inline` modifier does the same at *compile time* for lambdas — the JIT can't always inline them because lambda types are interfaces.

**2. Devirtualization — Knowing the Real Type**

Virtual dispatch (vtable lookup) has overhead. The JIT uses runtime profiling to discover: "in practice, every call to `animal.speak()` uses a `Dog` — never a `Cat`". It then:
- Generates native code that checks if it's a Dog
- If yes, calls `Dog.speak()` directly (no vtable)
- If no (rare case), deoptimizes back to interpreter

```
Profile data says: speak() called on Dog 10,000 times, Cat 0 times.

JIT generates:
  if (animal is Dog) call Dog.speak() directly  // fast path
  else: deoptimize → interpreter                // slow path, never taken
```

This is why Kotlin's `final` by default matters (see [Q0.4](00_jvm_mental_model.md#q04--the-jvm-call-stack)) — for truly final classes, the JIT can skip even the type check.

**3. Escape Analysis — Stack-Allocating Objects**

Normally, all objects live on the heap. But if the JIT can prove an object never "escapes" the method that created it, it can allocate it on the **stack** instead — no heap allocation, no GC pressure:

```kotlin
fun process(x: Int): Int {
    val point = Point(x, x * 2)  // Point only used locally
    return point.x + point.y     // point doesn't escape this function
}
```

JIT with escape analysis:
```
Point object doesn't escape process() → allocate fields on stack
No heap allocation → no GC needed → much faster
```

**4. Loop Unrolling — Fewer Branch Instructions**

```kotlin
for (i in 0 until 4) {
    data[i] = data[i] * 2
}
```

After JIT loop unrolling:
```kotlin
// JIT may generate native code equivalent to:
data[0] = data[0] * 2
data[1] = data[1] * 2
data[2] = data[2] * 2
data[3] = data[3] * 2
// No loop counter, no branch instruction — just 4 multiplications
```

**5. Dead Code Elimination**

```kotlin
val debug = false
if (debug) {
    expensiveLogging()  // JIT sees: debug is always false → removes this block
}
```

---

### Stage 7 — Deoptimization: When JIT's Assumptions Break

The JIT makes **optimistic assumptions** based on profiling. If those assumptions become wrong, it must "undo" the optimization:

```kotlin
// JIT assumed: speak() only ever called on Dog
open class Animal { open fun speak() = "..." }
class Dog : Animal() { override fun speak() = "Woof" }
class Cat : Animal() { override fun speak() = "Meow" }

// After JIT compiled Dog.speak() as a direct call...
val cat = Cat()
cat.speak()  // Cat wasn't in the profile! → DEOPTIMIZATION
```

**Deoptimization steps:**
1. JIT detects the assumption violated (new type `Cat` appeared)
2. Reverts to interpreted mode for that method
3. Eventually, with enough Cat calls, re-compiles with Cat included in the type profile

Deoptimizations are visible in JVM profiling tools (JFR, async-profiler). Frequent deoptimization is a performance problem — it means your profile data is unstable (many different types hitting the same call site).

---

### Android ART vs Desktop JVM

On Android, the runtime is **ART (Android Runtime)** — not the standard HotSpot JVM. ART takes a different approach to compilation:

```
Desktop JVM (HotSpot):              Android ART:
  JIT at runtime                      AOT at install time
  Slow cold start → warms up          Fast cold start (pre-compiled)
  Interprets until hot                Profile-guided recompilation
  Works for any code                  Optimized for Android patterns
```

**ART compilation pipeline:**
```
Install time:
  .apk (containing .dex bytecode)
  → ART compiles to native .oat file (AOT compilation)
  → Pre-compiled native code for common code paths

Runtime (Android 7+ with profile-guided compilation):
  App runs → ART collects JIT profiles
  → "What methods are hot in THIS user's usage pattern?"
  → dexopt (background service) recompiles using those profiles
  → Next launch: hot paths already native-compiled → faster
```

**Key difference from desktop JVM:**
- `.kt` files compile to `.class` (standard JVM bytecode)
- Android's `d8` tool converts `.class` → `.dex` (Dalvik bytecode, more compact for mobile)
- ART executes `.dex` via its own interpreter and JIT/AOT compiler

```
Kotlin compilation:
  .kt → kotlinc → .class → d8 → .dex → ART → runs on Android
  .kt → kotlinc → .class → JVM → runs on desktop/server
```

---

### The Full Pipeline in One Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    FULL CODE EXECUTION PIPELINE                         │
│                                                                         │
│  .kt source                                                             │
│    │                                                                    │
│    │ kotlinc: parse → type check → desugar → codegen                   │
│    ▼                                                                    │
│  .class (JVM bytecode)  ──────────────────────────────► .dex (Android) │
│    │                                                          │         │
│    │ ClassLoader: load → verify → prepare → initialize        │         │
│    ▼                                                          │         │
│  JVM Memory                                                   ▼         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  Level 0: Interpreter (slow, correct, collecting profiles)      │   │
│  │      │ method called ~100× times                               │   │
│  │      ▼                                                          │   │
│  │  Level 1–3: C1 JIT (fast compile, profiling)                   │   │
│  │      │ method called ~15,000× times                            │   │
│  │      ▼                                                          │   │
│  │  Level 4: C2 JIT (slow compile, aggressive optimization)        │   │
│  │      │ Uses profile data: inline, devirtualize,                │   │
│  │      │ escape analysis, loop unroll, dead code eliminate        │   │
│  │      ▼                                                          │   │
│  │  Native machine code (runs at full CPU speed)                   │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

> **Key Takeaway:** Your Kotlin code goes through at least two compilation steps — `kotlinc` to bytecode, then JIT to native code at runtime. The JIT is what makes JVM languages fast: it observes real runtime behavior and compiles only the hot paths, using that profile data for optimizations no static compiler can achieve. The cost: cold startup is slow until the JIT warms up.

---

## Master Summary: JVM Mental Model in 6 Points

```
┌─────────────────────────────────────────────────────────────────┐
│  1. PRIMITIVES live on the stack, hold their value directly.   │
│     REFERENCES live on the stack too, but point to the heap.   │
│                                                                 │
│  2. Kotlin maps Int → int (primitive) unless nullable or in     │
│     a generic position, where it maps to Integer (boxed).      │
│                                                                 │
│  3. Class initialization (<clinit>) runs once, thread-safely,  │
│     on first meaningful access. This is the foundation of      │
│     Kotlin `object` singleton safety.                          │
│                                                                 │
│  4. Method calls cost more than field reads: vtable lookup +   │
│     stack frame push. JIT eliminates this for final classes.   │
│                                                                 │
│  5. Generics are erased at runtime — List<Int> is just List.   │
│     This forces boxing wherever generics and primitives meet.  │
│                                                                 │
│  6. CODE RUNS IN TWO STAGES: kotlinc compiles .kt → bytecode;  │
│     the JVM JIT then compiles hot bytecode → native machine    │
│     code using tiered compilation. Cold code is interpreted;   │
│     hot code reaches C2 (Level 4) with inlining,              │
│     devirtualization, escape analysis. Android's ART uses AOT  │
│     at install time.                                           │
└─────────────────────────────────────────────────────────────────┘
```

---

*Next: [Phase 1 — Type System Foundations →](01_type_system_foundations.md)*
