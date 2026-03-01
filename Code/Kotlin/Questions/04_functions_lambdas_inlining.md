# Phase 4: Functions, Lambdas, and Inlining

## Navigation
[← Master Index](master_chains.md)

## Questions in This File
- [Q4.1 — Lambda Compilation](#q41--lambda-compilation)
- [Q4.2 — `inline`, `noinline`, `crossinline`](#q42--inline-noinline-crossinline)
- [Q4.3 — Higher-Order Functions with `suspend`](#q43--higher-order-functions-with-suspend)
- [Q4.4 — Scope Functions](#q44--scope-functions)
- [Q4.5 — Named and Default Parameters](#q45--named-and-default-parameters)

---

## Q4.1 — Lambda Compilation

> **Builds on:** [Q0.1 — heap allocation](00_jvm_mental_model.md#q01--primitives-vs-references)
> **Reference:** [Kotlin Docs — Lambdas](https://kotlinlang.org/docs/lambdas.html)

### First Principles: What IS a Lambda on the JVM?

The JVM, at its core, does not understand "functions as values." It only understands objects and methods on objects. So when Kotlin (or Java) lets you pass a function as a value, the compiler has to translate that into something the JVM understands: **an anonymous class that implements a functional interface**.

Every lambda in Kotlin implements one of the `FunctionN` interfaces from the Kotlin standard library:

```kotlin
interface Function0<out R> { operator fun invoke(): R }
interface Function1<in P1, out R> { operator fun invoke(p1: P1): R }
interface Function2<in P1, in P2, out R> { operator fun invoke(p1: P1, p2: P2): R }
// ... up to Function22
```

When you write a lambda, the compiler generates an anonymous class that implements the matching `FunctionN` interface.

### What Anonymous Class Does a Lambda Compile To?

```kotlin
fun doSomething(action: () -> Unit) {
    action()
}

// Call site:
doSomething { println("hello") }
```

**Without `inline`** — what the compiler generates:

```java
// Generated anonymous class:
final class Lambda$1 implements Function0<Unit> {
    static final Lambda$1 INSTANCE = new Lambda$1();  // singleton if non-capturing!

    @Override
    public Unit invoke() {
        System.out.println("hello");
        return Unit.INSTANCE;
    }
}

// Call site bytecode equivalent:
doSomething(Lambda$1.INSTANCE);  // passes the singleton object
```

```kotlin
// Higher-order function call becomes:
doSomething(Lambda$1.INSTANCE)
// inside doSomething:
action.invoke()  // virtual method call on the lambda object
```

### Non-Capturing vs Capturing Lambdas

**Non-capturing lambda** — doesn't close over any local variables from the enclosing scope:

```kotlin
val nums = listOf(1, 2, 3, 4, 5)
nums.filter { it > 3 }  // lambda { it > 3 } captures nothing
```

```java
// Compiler generates a SINGLETON:
static final SomeFunction PREDICATE_INSTANCE = new SomeFunction() {
    boolean invoke(int it) { return it > 3; }
};
// Reused for every call — zero allocation
```

**Capturing lambda** — closes over (captures) a local variable:

```kotlin
fun filterAbove(list: List<Int>, threshold: Int): List<Int> {
    return list.filter { it > threshold }  // captures `threshold`!
}
```

```java
// NEW object allocated on every call to filterAbove:
new SomeFunction(threshold) {  // threshold captured as constructor arg
    int threshold;
    SomeFunction(int t) { this.threshold = t; }
    boolean invoke(int it) { return it > this.threshold; }
};
```

```
Non-Capturing Lambda:                   Capturing Lambda:
┌───────────────────────┐               ┌───────────────────────────────┐
│  Lambda object         │               │  Lambda object created per    │
│  (singleton, reused)   │               │  call — holds captured vars   │
│                        │               │                               │
│  Heap: ONE instance    │               │  Heap: NEW instance each time │
│  GC: no pressure       │               │  GC: must collect each one    │
└───────────────────────┘               └───────────────────────────────┘
```

### Why Kotlin Uses Anonymous Classes Instead of `invokedynamic`

Java 8 added `invokedynamic` + `LambdaMetafactory` — a JVM instruction that creates lambda objects efficiently at runtime, deferring the class creation strategy to the JVM itself (which may use method handles, class reuse, etc.).

Kotlin originally chose anonymous classes because:
1. **Pre-Java 8 compatibility** — Kotlin needed to target Android, which ran on older Dalvik/ART VMs
2. **Inline is better** — Kotlin's `inline` functions eliminate lambda objects entirely, which is more efficient than `invokedynamic`
3. **Predictable behavior** — anonymous classes have well-understood semantics

> **Note:** Kotlin does use `invokedynamic` for lambdas when compiling to JVM 8+ with `-jvm-target 1.8` and certain other conditions. But on Android, anonymous classes remain common.

### The Heap Allocation Cost in a Hot Path

```kotlin
// WITHOUT inline — allocates a new lambda object on every call in the loop:
fun <T> myFilter(list: List<T>, predicate: (T) -> Boolean): List<T> {
    return list.filter(predicate)
}

val threshold = 3
repeat(1_000_000) {
    myFilter(listOf(1, 2, 3, 4, 5)) { it > threshold }
    //                              ^^^^^ NEW lambda object allocated 1 million times!
}
```

This creates GC pressure: 1 million `Function1` objects that must be garbage collected.

---

## Q4.2 — `inline`, `noinline`, `crossinline`

> **Builds on:** [Q4.1 (lambda anonymous class)](04_functions_lambdas_inlining.md#q41--lambda-compilation) · [Q0.4 (method call overhead)](00_jvm_mental_model.md#q04--the-jvm-call-stack)
> **Connects to:** [Q3.3 (reified requires inline)](03_generics_and_variance.md#q33--reified-type-parameters)
> **Reference:** [Kotlin Docs — Inline Functions](https://kotlinlang.org/docs/inline-functions.html)

### What Exactly Does `inline` Paste at the Call Site?

`inline` pastes **both** the function body AND the lambda body at the call site. Neither becomes an object on the heap.

```kotlin
inline fun doWork(action: () -> Unit) {
    println("Before")
    action()
    println("After")
}

// Call site:
doWork { println("Working") }
```

**What the compiler generates at the call site:**
```kotlin
// The inline call is replaced with:
println("Before")
println("Working")  // lambda body pasted directly — no object!
println("After")
```

```bytecode
; Before inlining:
INVOKESTATIC doWork (Lkotlin/jvm/functions/Function0;)V

; After inlining (doWork call is gone, body is here):
LDC "Before"
INVOKEVIRTUAL PrintStream.println
LDC "Working"
INVOKEVIRTUAL PrintStream.println
LDC "After"
INVOKEVIRTUAL PrintStream.println
```

No `doWork` method call. No `Function0` object. Everything is flattened.

### Non-Local `return` — The Super Power of Inlined Lambdas

**What "non-local" means:** A return that exits not the lambda, but the outer function that called the inline function.

```kotlin
fun findFirst(list: List<Int>): Int? {
    list.forEach { item ->          // forEach is inline!
        if (item > 5) return item   // ← NON-LOCAL return: returns from findFirst!
    }
    return null
}
```

This works because `forEach`'s lambda is pasted directly into `findFirst`. The `return` statement is inside `findFirst`'s pasted body, so it can exit `findFirst` directly.

```kotlin
// What the compiler actually generates:
fun findFirst(list: List<Int>): Int? {
    for (item in list) {            // forEach inlined as loop
        if (item > 5) return item   // return from findFirst — makes sense now!
    }
    return null
}
```

**Why non-local returns are IMPOSSIBLE without `inline`:**

```kotlin
fun findFirst(list: List<Int>): Int? {
    list.forEach(fun(item) {        // anonymous function, not lambda
        if (item > 5) return item   // LOCAL return — exits the anon function only!
    })
    return null  // always reaches here
}
```

The anonymous function has its own call stack frame. `return` exits that frame — not `findFirst`. Only when the lambda is inlined (pasted into `findFirst`) does non-local return work.

---

### `crossinline` — Preventing Non-Local Returns in Nested Contexts

`crossinline` is needed when an inlined lambda is passed to a context where non-local returns are impossible (e.g., inside a Runnable, another lambda, or a non-inlined function).

**The Problem:**

```kotlin
inline fun startAsync(action: () -> Unit) {
    Thread { action() }.start()  // COMPILE ERROR without crossinline!
    // action() is called from inside Thread's lambda
    // That lambda has its OWN scope — non-local return from action
    // would try to exit startAsync, but startAsync has already returned!
}
```

**The Fix:**

```kotlin
inline fun startAsync(crossinline action: () -> Unit) {
    Thread { action() }.start()  // OK: crossinline forbids non-local return in action
}

// Call site: lambda cannot have non-local return
startAsync {
    println("async work")
    // return  // COMPILE ERROR: crossinline lambda can't have non-local return
}
```

```
NORMAL inline lambda:
┌─────────────────────────────────────────────────────┐
│  inline fun doWork(action: () -> Unit)               │
│       │                                              │
│       ▼ pasted directly into caller                  │
│  Can use non-local return ✓                          │
│  Cannot be stored in a variable ✗                    │
│  Cannot be passed to another function ✗              │
└─────────────────────────────────────────────────────┘

crossinline lambda:
┌─────────────────────────────────────────────────────┐
│  inline fun startAsync(crossinline action: () -> Unit│
│       │                                              │
│       ▼ pasted, but wrapped in a new context         │
│  Can NOT use non-local return ✗                      │
│  Can be called from nested lambda/Runnable ✓         │
└─────────────────────────────────────────────────────┘
```

---

### `noinline` — Keeping a Lambda as an Object

Sometimes you need ONE of the lambdas to remain as a `Function` object — for example, to store it, pass it elsewhere, or use it after the inline function returns.

```kotlin
inline fun buildAndRun(
    noinline setup: () -> Unit,   // NOT inlined — remains a Function0 object
    work: () -> Unit              // inlined normally
) {
    val storedSetup = setup       // OK: setup is a real object, can be stored
    storedSetup()
    work()                        // work is inlined, but setup is a real lambda
}
```

```kotlin
// WITHOUT noinline, this would COMPILE ERROR:
inline fun broken(action: () -> Unit) {
    val stored = action  // ERROR: cannot store inline lambda as variable!
}
```

**When noinline is required:**
- Lambda must be stored in a variable
- Lambda must be passed to a non-inline function
- Lambda must be returned from the inline function

---

### When `inline` Is Harmful

**1. Binary compatibility for library APIs:**
If you publish an `inline` function and a caller compiles against your library, the function body is pasted into the caller's bytecode. If you later change the function body in your library and release a new version, callers that haven't recompiled still have the OLD body pasted in. They must recompile.

**2. Code size explosion:**
If an inline function has a large body and is called in 100 places, the body is duplicated 100 times in the bytecode. This can significantly increase APK size.

```kotlin
// This is fine (small body, called rarely):
inline fun measure(block: () -> Unit): Long {
    val start = System.nanoTime()
    block()
    return System.nanoTime() - start
}

// This is bad (large body, called frequently):
inline fun processComplexData(data: List<Any>, transform: (Any) -> Any): List<Any> {
    // 200 lines of complex logic...
    // Called in 50 places → 50 × 200 = 10,000 lines of duplicated bytecode!
}
```

---

### Why All Standard Library Operators Are `inline`

`map`, `filter`, `let`, `also`, `run`, `apply`, `with` — all are `inline`:

```kotlin
// From stdlib:
public inline fun <T, R> Iterable<T>.map(transform: (T) -> R): List<R> { ... }
public inline fun <T> T.also(block: (T) -> Unit): T { ... }
```

Without `inline`, every call to `.map {}` would allocate a `Function1` object for the lambda. Since these are called everywhere in Android code (often in hot paths), the allocation savings are substantial.

**The "cost" at call sites:** Larger bytecode at each call site where the operator is used. This is accepted as a reasonable trade-off because:
- Standard library functions are small
- The allocation savings outweigh the code size increase

---

## Q4.3 — Higher-Order Functions with `suspend`

> **Builds on:** [Q4.1 — Lambda Compilation](04_functions_lambdas_inlining.md#q41--lambda-compilation) · [Q4.2 — inline](04_functions_lambdas_inlining.md#q42--inline-noinline-crossinline)
> **Connects to:** [Q9.1 — What suspend does](09_coroutines_execution_mechanics.md#q91--what-suspend-actually-does) · [Q10.3 — CancellationException rules](10_structured_concurrency.md#q103--exception-handling-rules)

### How a `suspend` Lambda Differs from a Regular Lambda

A `suspend` lambda has a **`Continuation` parameter** added by the compiler to its `invoke` method, following the same CPS transformation as regular suspend functions.

```kotlin
// Regular lambda type:
val regular: () -> String
// JVM: Function0<String> — invoke(): String

// Suspend lambda type:
val suspended: suspend () -> String
// JVM: SuspendFunction0<String> — invoke(continuation: Continuation<String>): Any
```

The `suspend` modifier on a lambda type means the lambda's `invoke` method participates in the coroutine continuation protocol.

```kotlin
// Regular function taking a suspend lambda:
fun doWork(action: suspend () -> Unit) { ... }

// The action parameter's JVM type is:
// Function1<Continuation<Unit>, Object>
//            ^^^^^^^^^^^^^^^^ extra continuation param
```

### `Thread.sleep` vs `delay` Inside a Suspend Function

```kotlin
suspend fun badDelay() {
    Thread.sleep(1000)  // BLOCKS THE THREAD — not coroutine-aware!
}

suspend fun goodDelay() {
    delay(1000)         // SUSPENDS THE COROUTINE — releases the thread!
}
```

```
Thread.sleep(1000) inside suspend:
┌──────────────────────────────────────────────────┐
│  Thread: [blocked, sleeping, cannot run anything] │
│  Duration: 1 full second                          │
│  Other coroutines on this thread: ALSO BLOCKED!  │
└──────────────────────────────────────────────────┘

delay(1000) inside suspend:
┌──────────────────────────────────────────────────┐
│  Thread: [freed, available for other coroutines]  │
│  Continuation: scheduled to resume in 1 second    │
│  Other coroutines on this thread: CAN RUN!        │
└──────────────────────────────────────────────────┘
```

`Thread.sleep` is a blocking JVM call — it tells the OS to put the thread to sleep. The coroutine runtime doesn't know about it, so it can't use the thread for other work.

[`delay`](09_coroutines_execution_mechanics.md#q91--what-suspend-actually-does) is coroutine-aware — it registers a timer callback and returns `COROUTINE_SUSPENDED`, freeing the thread for other coroutines.

### `retryWithBackoff` — The `CancellationException` Rule

```kotlin
suspend fun <T> retryWithBackoff(
    times: Int,
    initialDelay: Long = 100L,
    maxDelay: Long = 1000L,
    block: suspend () -> T
): T {
    var currentDelay = initialDelay
    repeat(times) { attempt ->
        try {
            return block()
        } catch (e: CancellationException) {
            throw e  // ALWAYS RE-THROW — never swallow!
        } catch (e: Exception) {
            if (attempt == times - 1) throw e  // last attempt: propagate
            println("Attempt $attempt failed: ${e.message}. Retrying in ${currentDelay}ms")
        }
        delay(currentDelay)
        currentDelay = minOf(currentDelay * 2, maxDelay)
    }
    throw IllegalStateException("Should not reach here")
}
```

**Why `CancellationException` must ALWAYS be re-thrown:**

[`CancellationException`](10_structured_concurrency.md#q103--exception-handling-rules) is the coroutine cancellation signal. When a coroutine is cancelled (e.g., `job.cancel()`), the runtime throws `CancellationException` at the next suspension point. If you catch it and don't re-throw, the coroutine doesn't know it's been cancelled — it continues running.

```kotlin
// WRONG — swallowing CancellationException causes coroutine leak:
suspend fun badRetry(block: suspend () -> String): String {
    while (true) {
        try {
            return block()
        } catch (e: Exception) {  // catches CancellationException!
            delay(100)           // this delay also throws CancellationException
                                 // if still running → infinite loop risk!
        }
    }
}

// The coroutine called cancel() but badRetry keeps running forever!
```

```
CancellationException flow:
job.cancel()
    │
    ▼
coroutine runtime sets "cancellation requested"
    │
    ▼
next suspension point (delay, withContext, etc.)
    │
    ▼
throws CancellationException
    │
    ├── if re-thrown → propagates up → coroutine properly cancelled ✓
    └── if swallowed → coroutine continues running! Scope never cleans up ✗
```

---

## Q4.4 — Scope Functions

> **Builds on:** [Q4.2 — inline functions](04_functions_lambdas_inlining.md#q42--inline-noinline-crossinline) · [Q4.1 — lambda compilation](04_functions_lambdas_inlining.md#q41--lambda-compilation)
> **Connects to:** [Q6.2 — Extension Functions as API Design](06_extension_functions.md#q62--extension-functions-as-api-design)
> **Reference:** [Kotlin Docs — Scope Functions](https://kotlinlang.org/docs/scope-functions.html)

### The Five Scope Functions — Bytecode Reality

All five scope functions are **`inline`** — they have zero overhead at runtime. After inlining, they all reduce to:
1. Evaluate the block with the receiver/argument
2. Return the result (either the block's result or the original object)

```kotlin
// All five — the ONLY differences are:
// 1. How the context object is accessed (this vs it)
// 2. What is returned (the block result or the original object)
```

### `this` vs `it` — The Exact Distinction

| Function | Access via | Returns | JVM receiver |
|----------|-----------|---------|--------------|
| `let` | `it` | Lambda result | Parameter (T) |
| `run` | `this` | Lambda result | Receiver (extension) |
| `apply` | `this` | The object itself | Receiver (extension) |
| `also` | `it` | The object itself | Parameter (T) |
| `with` | `this` | Lambda result | NOT extension — arg |

```kotlin
val result = someObject
    .let { it.doSomething() }      // it = someObject; returns doSomething() result
    .run { doAnotherThing() }      // this = someObject; returns doAnotherThing() result
    .apply { configure() }         // this = someObject; returns someObject
    .also { println(it) }          // it = someObject; returns someObject

with(someObject) {
    doStuff()                      // this = someObject; returns doStuff() result
}
```

### When Choosing the Wrong Scope Function Causes a Logic Bug

```kotlin
data class User(var name: String, var email: String)

// BUG: Used `let` instead of `apply` — modifies nothing!
val user = User("Alice", "alice@example.com").let {
    it.name = "Bob"    // modifies the object — this is fine
    "Done"             // but `let` returns THIS string, not the User!
}
// user is now "Done" — not the User object!

// CORRECT: Use `apply` to configure and return the same object
val user2 = User("Alice", "alice@example.com").apply {
    name = "Bob"       // this = User, sets name on it
    email = "bob@example.com"
}
// user2 is the configured User object
```

```kotlin
// BUG: Used `also` instead of `let` — transformation result lost!
val length = "hello".also { it.length }  // also returns "hello", not 5!
// length is "hello" — not 5!

// CORRECT: Use `let` when you want to transform
val length = "hello".let { it.length }  // returns 5
// length is 5
```

### Decision Guide

```
Do you want to...

→ Transform the object → use let { }     (return: block result, access: it)
→ Configure the object → use apply { }   (return: same object, access: this)
→ Compute with a non-null value → use let { }
→ Add side effects, keep chain → use also { }  (return: same object, access: it)
→ Run multiple operations on an object → use run { } or with(obj) { }
→ Call multiple methods (fluent builder) → use apply { }
```

---

## Q4.5 — Named and Default Parameters

> **Builds on:** [Q2.5.2 — Secondary Constructors](02_5_initialization_mechanics.md#q252--primary-vs-secondary-constructors)
> **Connects to:** [Q2.5.6 — @JvmOverloads and Java interop](02_5_initialization_mechanics.md#q256--constructor-visibility-and-factory-patterns)
> **Reference:** [Kotlin Docs — Default arguments](https://kotlinlang.org/docs/functions.html#default-arguments)

### What Bytecode Does a Function With Default Parameters Compile To?

```kotlin
fun connect(host: String, port: Int = 443, ssl: Boolean = true) { ... }
```

The compiler generates:
1. The **full method** with all parameters
2. A **synthetic `$default` method** with a bitmask

```java
// Generated:
public static void connect(String host, int port, boolean ssl) {
    // actual implementation
}

// Synthetic method with bitmask (for default param resolution):
public static void connect$default(String host, int port, boolean ssl,
                                    int mask, Object defaultConstructorMarker) {
    // mask bit 0 set → use default for port (443)
    if ((mask & 1) != 0) port = 443;
    // mask bit 1 set → use default for ssl (true)
    if ((mask & 2) != 0) ssl = true;
    connect(host, port, ssl);
}
```

**Call sites:**
```kotlin
connect("example.com")           // → connect$default("example.com", 0, false, 3, null)
                                  //   mask=3 (binary 11) → use defaults for both
connect("example.com", 8080)     // → connect$default("example.com", 8080, false, 2, null)
                                  //   mask=2 (binary 10) → use default only for ssl
connect("example.com", 8080, false) // → connect("example.com", 8080, false)
                                      //   no defaults → call full method directly
```

### `@JvmOverloads` — Java Interop

From Java, Kotlin's default parameters aren't visible — Java only sees the full method. `@JvmOverloads` generates additional Java-visible overloads:

```kotlin
@JvmOverloads
fun connect(host: String, port: Int = 443, ssl: Boolean = true) { ... }
```

```java
// Generated Java-visible overloads:
void connect(String host)                      // uses port=443, ssl=true
void connect(String host, int port)            // uses ssl=true
void connect(String host, int port, boolean ssl) // no defaults
```

### When Default Parameters Eliminate Secondary Constructors

```kotlin
// Old Java pattern with secondary constructors:
class Button {
    constructor(text: String) : this(text, Color.BLACK, 14)
    constructor(text: String, color: Color) : this(text, color, 14)
    constructor(text: String, color: Color, size: Int) {
        // actual init
    }
}

// Kotlin: one primary constructor does it all
class Button(
    val text: String,
    val color: Color = Color.BLACK,
    val size: Int = 14
)
```

---

## Master Summary: Functions and Lambdas in 5 Points

```
┌───────────────────────────────────────────────────────────────────────┐
│  1. LAMBDA = anonymous class implementing FunctionN.                  │
│     Non-capturing → singleton (zero allocation).                      │
│     Capturing → new object per call (GC pressure).                    │
│                                                                        │
│  2. INLINE pastes function body + lambda body at call site.           │
│     Eliminates the anonymous class entirely — no heap allocation.     │
│                                                                        │
│  3. NON-LOCAL RETURN only works with inlined lambdas.                 │
│     crossinline forbids non-local return in nested contexts.          │
│     noinline keeps a lambda as an object for storage/passing.         │
│                                                                        │
│  4. CancellationException must ALWAYS be re-thrown in catch blocks.   │
│     Swallowing it causes coroutine leaks.                             │
│                                                                        │
│  5. All 5 scope functions are inline → zero overhead.                 │
│     The only difference is this/it and what they return.              │
└───────────────────────────────────────────────────────────────────────┘
```

---

*← [Phase 3 — Generics & Variance](03_generics_and_variance.md) | [Phase 5 — Properties & Delegation →](05_properties_and_delegation.md)*
