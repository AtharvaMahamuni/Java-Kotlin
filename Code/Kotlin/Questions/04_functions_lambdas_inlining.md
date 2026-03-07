# Phase 4 — Functions, Lambdas, and Inlining

> On the JVM, functions are not values — objects are. Every lambda becomes an anonymous class. Every `inline` keyword eliminates that class entirely. This phase is about what your function calls actually cost.

## Navigation

[← Phase 3 — Generics and Variance](03_generics_and_variance.md) | [→ Phase 5 — Properties and Delegation](05_properties_and_delegation.md)

## Questions in This File

- [Q4.1 — Lambda Compilation](#q41--lambda-compilation)
- [Q4.2 — Function References and SAM Conversions](#q42--function-references-and-sam-conversions)
- [Q4.3 — `inline`, `noinline`, `crossinline`](#q43--inline-noinline-crossinline)
- [Q4.4 — `suspend` in Higher-Order Functions](#q44--suspend-in-higher-order-functions)
- [Q4.5 — Scope Functions](#q45--scope-functions)
- [Q4.6 — Named and Default Parameters](#q46--named-and-default-parameters)

---

# Q4.1 — Lambda Compilation

> **Builds on:** [Q0.1 (heap allocation)](phase0_jvm_mental_model_v3.md#q01--primitives-vs-references-the-two-worlds)
> **Connects to:** [Q4.3 (inline eliminates the anonymous class)](#q43--inline-noinline-crossinline)

---

## The Core Rule

```
You write a lambda.
The JVM sees an anonymous class with an invoke() method.
```

The JVM instruction set has no concept of "a function as a value." To pass a function around, Kotlin wraps it in an object — an instance of an anonymous class that implements one of the `FunctionN` interfaces.

---

## The `FunctionN` Interfaces — Why `in` and `out`?

```kotlin
interface Function0<out R>              { operator fun invoke(): R }
interface Function1<in P1, out R>       { operator fun invoke(p1: P1): R }
interface Function2<in P1, in P2, out R>{ operator fun invoke(p1: P1, p2: P2): R }
// ... up to Function22
```

The variance annotations are the same rule as any generic container ([Q3.2](03_generics_and_variance.md)):

- **`out R`** — the function *produces* a result. A `Function1<String, Dog>` can safely be used where `Function1<String, Animal>` is expected, because returning a `Dog` is fine when the caller wants an `Animal`. (Covariant return.)
- **`in P1`** — the function *consumes* a parameter. A `Function1<Animal, Int>` can safely be used where `Function1<Dog, Int>` is expected, because accepting any `Animal` is safe when only `Dog`s are passed in. (Contravariant parameter.)

This is why a `(Dog) -> Animal` is a subtype of `(Animal) -> Dog` in Kotlin.

---

## What a Lambda Compiles To

```kotlin
doSomething { println("hello") }
```

```java
// Compiler generates this class:
final class Lambda$1 implements Function0<Unit> {
    static final Lambda$1 INSTANCE = new Lambda$1(); // singleton: no captured vars

    @Override
    public Unit invoke() {
        System.out.println("hello");
        return Unit.INSTANCE;
    }
}

// At the call site:
doSomething(Lambda$1.INSTANCE);
// Inside doSomething: action.invoke()
```

**Lambda vs anonymous object — they are the same thing:**

```kotlin
// Lambda syntax — compiler generates the anonymous class for you:
val fn: () -> Unit = { println("hello") }

// Anonymous object syntax — you write it explicitly:
val fn: () -> Unit = object : Function0<Unit> {
    override fun invoke() { println("hello") }
}
```

Both produce the same bytecode. Lambda syntax is compiler sugar. The important difference is that the **compiler automatically makes non-capturing lambdas into singletons** — you'd have to do that manually with anonymous objects.

---

## Non-Capturing vs Capturing Lambdas

```kotlin
// NON-CAPTURING — uses no variable from outside the lambda
nums.filter { it > 3 }

// CAPTURING — closes over `threshold` from the enclosing function
fun filterAbove(list: List<Int>, threshold: Int): List<Int> {
    return list.filter { it > threshold }  // captures threshold!
}
```

```
NON-CAPTURING { it > 3 }:          CAPTURING { it > threshold }:

SINGLETON                           NEW OBJECT per call
One instance, allocated once        threshold becomes a field on the object
No GC pressure                      GC must collect one object per call

Heap cost: 0 after class load       Heap cost: 1 object per filterAbove() call
```

```java
// Capturing lambda — the captured variable becomes a constructor field:
new Function1<Integer, Boolean>() {
    private final int threshold;
    // constructor called once per filterAbove() call, stores threshold
    {  this.threshold = outerThreshold;  }
    public Boolean invoke(Integer it) { return it > this.threshold; }
};
// Each call to filterAbove() → new object → GC pressure
```

In a hot path doing 1,000,000 iterations: 1M objects allocated, 1M GC candidates. This is why capturing lambdas inside tight loops cause GC pauses and frame drops on Android.

---

## Why Not `invokedynamic`?

Java 8 added `invokedynamic` for lambdas — a JVM instruction that creates lambda implementations at runtime, potentially reusing objects. Kotlin chose anonymous classes because:

1. **Android** — early Dalvik/ART didn't support `invokedynamic` well
2. **`inline` is strictly better** — inlining eliminates the object entirely; `invokedynamic` still creates one
3. **Predictability** — anonymous class behaviour is well-understood

Kotlin uses `invokedynamic` when targeting JVM 8+ with `-jvm-target 1.8`. On Android (D8/R8 toolchain), anonymous classes remain dominant.

---

## Memory Trick

```
LAMBDA = anonymous class (FunctionN) + one instance of it.

FunctionN variance (same rule as all generics):
  in P  = consumes parameter  = contravariant
  out R = produces result     = covariant

NON-CAPTURING → compiler makes it a singleton → 0 allocation after class load
CAPTURING     → new instance per call → GC pressure in hot paths

Hot path fix: make the higher-order function `inline` → no object at all (Q4.3)
```

---

## Self-Test

1. What JVM construct does a Kotlin lambda compile to?
2. Why is `Function1` declared as `Function1<in P1, out R>` and not `Function1<P1, R>`?
3. What makes a lambda "non-capturing"? Why does it become a singleton?
4. Why does a capturing lambda create a new object on every call?
5. Why did Kotlin prefer anonymous classes over `invokedynamic` on Android?

---

# Q4.2 — Function References and SAM Conversions

> **Builds on:** [Q4.1 (lambdas compile to anonymous classes)](#q41--lambda-compilation)
> **Connects to:** [Q4.3 (inline eliminates these too)](#q43--inline-noinline-crossinline)

---

## Function References: `::method`

A function reference is a lambda whose entire body is a single call to an existing named function. The compiler generates the same anonymous class, but the `invoke` body just delegates:

```kotlin
fun isPositive(x: Int): Boolean = x > 0

// Lambda with a wrapper body:
listOf(-1, 2, -3, 4).filter { x -> isPositive(x) }

// Function reference — same behaviour, no wrapper body:
listOf(-1, 2, -3, 4).filter(::isPositive)
```

Both produce an anonymous class implementing `Function1<Int, Boolean>`. The reference form is slightly cleaner and avoids one level of indirection.

---

## Five Kinds — and Which Allocate

```kotlin
// 1. Top-level function — no receiver, no capture → SINGLETON
::println                      // KFunction1<Any?, Unit>

// 2. Member function, UNBOUND — receiver provided at call time → SINGLETON
String::uppercase              // KFunction1<String, String>
listOf("a", "b").map(String::uppercase)  // → ["A", "B"]

// 3. Member function, BOUND — specific instance captured → NEW OBJECT per use
val s = "hello"
s::uppercase                   // KFunction0<String> — captures s
val fn = s::uppercase          // allocates once (captures s here)
fn()  // "HELLO"

// 4. Constructor reference — non-capturing → SINGLETON
::User                         // KFunction2<String, Int, User>

// 5. Property getter reference — non-capturing → SINGLETON
User::name                     // KProperty1<User, String>
```

**The allocation rule:**
- No instance captured → the reference itself is stateless → **singleton**
- An instance is captured (bound ref like `s::uppercase`) → new object holds that instance → **one allocation per creation**

---

## SAM Conversions — Java Functional Interface Integration

**SAM = Single Abstract Method.** A Java interface with exactly one abstract method. Kotlin auto-converts lambdas to SAM interfaces when calling Java APIs:

```java
// Java SAM interfaces:
public interface Runnable       { void run(); }
public interface Comparator<T>  { int compare(T a, T b); }
public interface View.OnClickListener { void onClick(View v); }
```

```kotlin
// Kotlin lambda auto-converts to the required SAM type:
Thread { println("running") }              // lambda → Runnable
button.setOnClickListener { handleClick(it) }  // lambda → OnClickListener
```

```java
// What the compiler actually generates:
new Runnable() {
    @Override public void run() { System.out.println("running"); }
}
```

---

## The Trap: SAM Does NOT Work for Regular Kotlin Interfaces

**This is the most common mistake.** SAM auto-conversion only applies to **Java interfaces**. A regular Kotlin interface does not get it:

```kotlin
// Regular Kotlin interface — lambda syntax FAILS:
interface Validator {
    fun validate(s: String): Boolean
}
val v: Validator = { it.contains("@") }  // COMPILE ERROR
```

Why? Kotlin interfaces can have multiple abstract methods from supertypes, default implementations, and other Kotlin-specific features that make automated SAM inference ambiguous. The language requires you to be explicit.

**Fix: `fun interface` — explicit opt-in SAM for Kotlin:**

```kotlin
fun interface Validator {
    fun validate(s: String): Boolean
}
val v: Validator = { it.contains("@") }  // NOW compiles ✓
v.validate("user@example.com")           // true
```

`fun interface` is a contract: "this interface has exactly one abstract method and is designed to be used as a lambda."

---

## Memory Trick

```
FUNCTION REFERENCE = lambda delegating to an existing function.

ALLOCATION RULE:
  No instance captured (::fn, Type::method, ::Constructor) → SINGLETON
  Instance captured (obj::method)                          → 1 object per creation

SAM = Java interface with 1 abstract method.
  Java SAM  → lambda auto-conversion always works
  Kotlin interface → NO auto-conversion → must use object : ...
  fun interface  → OPT-IN → enables lambda syntax for Kotlin interfaces

Common Android SAMs: Runnable, OnClickListener, Comparator, Callable
```

---

## Self-Test

1. `String::uppercase` vs `"hello"::uppercase` — which allocates a new object per use? Why?
2. Why does `Thread { println("hi") }` compile without `object : Runnable { ... }`?
3. You define `interface Action { fun run() }` in Kotlin. Can you pass a lambda as an `Action`? What must you change?
4. What does `fun interface` guarantee that a regular `interface` doesn't?
5. Is `::isPositive` (top-level fn reference) a singleton? Explain why.

---

# Q4.3 — `inline`, `noinline`, `crossinline`

> **Builds on:** [Q4.1 (lambda = anonymous class)](#q41--lambda-compilation) · [Q0.4 (method dispatch)](phase0_jvm_mental_model_v3.md#q04--the-jvm-call-stack)
> **Connects to:** [Q3.4 (reified requires inline)](03_generics_and_variance.md#q34--reified-type-parameters)

---

## The Core Idea

`inline` pastes both the **function body** and the **lambda body** directly at the call site. No anonymous class. No method call.

```kotlin
inline fun doWork(action: () -> Unit) {
    println("Before")
    action()
    println("After")
}

doWork { println("Working") }
```

After inlining, the call is entirely replaced with:

```kotlin
println("Before")
println("Working")  // lambda body pasted here — no Function0 ever created
println("After")
// No doWork() call frame. No anonymous class. All flattened.
```

```
BEFORE inlining:                    AFTER inlining:
────────────────────────────────    ────────────────────────────────
INVOKESTATIC doWork(Function0)      LDC "Before"
  → creates Function0 object        INVOKEVIRTUAL println
  → passes it to doWork             LDC "Working"
  → doWork calls invoke()           INVOKEVIRTUAL println
                                    LDC "After"
                                    INVOKEVIRTUAL println
```

---

## Three Keywords, Three Behaviours

```
inline      → body pasted, lambda pasted          → no object, non-local return OK
noinline    → body pasted, lambda NOT pasted       → lambda stays as Function object
crossinline → body pasted, lambda pasted BUT       → non-local return FORBIDDEN
              moved into a nested execution context
```

---

## Non-Local `return` — Only Possible With `inline`

Non-local means: a `return` that exits the **enclosing named function**, not just the lambda.

```kotlin
fun findFirst(list: List<Int>): Int? {
    list.forEach { item ->          // forEach is inline
        if (item > 5) return item   // exits findFirst, NOT the forEach lambda
    }
    return null
}
```

This works because `forEach` inlines its lambda body *into* `findFirst`. The compiler sees this after inlining:

```kotlin
fun findFirst(list: List<Int>): Int? {
    for (item in list) {            // forEach body pasted as a loop
        if (item > 5) return item   // return is now inside findFirst — valid
    }
    return null
}
```

**Without inline:** the lambda has its own separate stack frame. A `return` exits *that* frame, not `findFirst`'s:

```kotlin
fun findFirst(list: List<Int>): Int? {
    list.forEach(fun(item) {        // anonymous function = own stack frame
        if (item > 5) return item   // LOCAL return — exits only the anon fn
    })
    return null  // always reached
}
```

---

## `crossinline` — When the Lambda Runs in a Different Context

`crossinline` is needed when an inlined lambda is passed into a **nested execution context** — a `Thread`, `Runnable`, `Handler.post`, coroutine builder — where it runs *after the outer function has already returned*.

```kotlin
inline fun startAsync(action: () -> Unit) {
    Thread { action() }.start()  // COMPILE ERROR without crossinline
}
```

**Why this is a problem — call stack argument:**

```
When the thread eventually runs action():

  Thread call stack:
    Thread.run()       ← active frame
      action()         ← lambda body would be pasted here

  Main call stack:
    startAsync()       ← ALREADY RETURNED — this frame is GONE
    callerFn()         ← expecting a return? The frame no longer exists!
```

`startAsync()` returns immediately after calling `.start()`. The thread runs the lambda later — in a completely different call stack. If `action` contained a non-local `return`, there is no valid stack frame to return to. The JVM has no way to "jump back" to a dead frame.

**The fix:**

```kotlin
inline fun startAsync(crossinline action: () -> Unit) {
    Thread { action() }.start()  // OK — crossinline makes non-local return a compile error
}

startAsync {
    println("async work")
    // return  // COMPILE ERROR: non-local return forbidden in crossinline lambda
}
```

`crossinline` says: "paste this lambda into the nested context, but ban non-local return." The lambda body is still inlined (no object allocation), but the unsafe escape is forbidden at compile time.

---

## `noinline` — Keeping a Lambda as an Object

Sometimes you need one lambda to remain a real `Function` object — to store it in a list, return it, or pass it to a non-inline function:

```kotlin
inline fun buildAndRun(
    noinline setup: () -> Unit,  // stays as Function0 object
    work: () -> Unit             // inlined as normal
) {
    callbacks.add(setup)         // OK: setup is a real object, can be stored
    work()                       // pasted inline — no object
}

// Without noinline this fails:
inline fun broken(action: () -> Unit) {
    val stored = action  // COMPILE ERROR: can't store an inline lambda as a variable
}
```

---

## `inline` Without a Lambda — Usually Pointless

You *can* mark a function `inline` even with no lambda parameters. The body is pasted (saves one method call) but there is no lambda object to eliminate. The compiler warns:

```kotlin
inline fun square(x: Int) = x * x
// Warning: Expected performance impact from inlining is insignificant.
```

Duplicates bytecode at every call site. Only worthwhile for extremely small, extremely hot utility functions.

---

## When `inline` Is Harmful

**1. Large body × many call sites = APK bloat:**

```kotlin
// 200 lines inlined at 50 call sites = 10,000 lines of duplicated bytecode
inline fun processComplexData(data: List<Any>, transform: (Any) -> Any): List<Any> { ... }
```

**2. Library binary compatibility:**

```
v1.0 library: inline fun format() = "format-v1: $value"
              → callers compile this string into THEIR bytecode

v1.1 library: inline fun format() = "format-v1.1: $value"  ← changed!
              → callers who haven't recompiled still have the OLD string baked in
              → they must recompile to pick up the change

Non-inline:   callers call the function → always get the current version
```

---

## Memory Trick

```
INLINE = "copy-paste the body here."
  Eliminates: the anonymous class, the method call overhead.

NON-LOCAL RETURN — only works in inlined lambdas:
  Reason: after inlining, the lambda IS the outer function's body.
  Without inline: lambda has its own stack frame → return exits only that frame.

crossinline = "paste the lambda, but ban non-local return"
  Use when: lambda runs in Thread { }, Runnable { }, Handler.post { }
  Why: outer function's stack frame is gone by the time the lambda runs.

noinline = "keep this lambda as a Function object"
  Use when: you need to store it, add to a list, or pass to non-inline fn.

inline with no lambda: body pasted, no object eliminated → minor benefit, compiler warns.

HARMFUL:
  Large body × many sites → APK bloat.
  Published library inline fn → callers bake old body → breaks binary compat.
```

---

## Self-Test

1. What does `inline` do to both the function body and the lambda body?
2. Why does non-local `return` work in `forEach { }` but not in a regular lambda?
3. Explain *using the call stack* why `crossinline` is needed when a lambda runs inside `Thread { action() }`.
4. What is `noinline` for? Give one concrete situation requiring it.
5. Why are stdlib `map`, `filter`, `let` all `inline`?
6. Why is `inline` on a no-lambda function usually pointless?

---

# Q4.4 — `suspend` in Higher-Order Functions

> **Builds on:** [Q4.1 (lambda compilation)](#q41--lambda-compilation) · [Q4.3 (inline)](#q43--inline-noinline-crossinline)
> **Connects to:** [Q9.1 (CPS transformation)](09_coroutines_execution_mechanics.md) · [Q10.3 (CancellationException)](10_structured_concurrency.md)

---

## What is a `Continuation`? (First Principles)

Normal function calls are synchronous: you call `foo()`, it runs, it returns, you continue. The JVM manages this with a call stack — each function has a stack frame, and `return` pops that frame.

`suspend` functions break this model. They need to be able to **pause mid-execution** (at an `await`, `delay`, network call) and **resume later**, possibly on a different thread. The call stack can't hold paused state — stack frames are destroyed when a function returns.

The solution is **CPS (Continuation-Passing Style)**. Instead of returning a value directly, the compiler transforms every `suspend` function to accept a `Continuation<T>` callback:

```kotlin
// What you write:
suspend fun fetchUser(id: Int): User

// What the compiler generates:
fun fetchUser(id: Int, continuation: Continuation<User>): Any?
//                     ↑ "when you have the result, call me back with it"
//                                                              ↑ returns either:
//                                                                value directly (if no suspension)
//                                                                COROUTINE_SUSPENDED sentinel
```

The `Continuation<T>` holds the paused coroutine's local variables and the "what to do next" code. It is stored on the heap — not the stack — so it survives across thread boundaries.

---

## `suspend` Lambda vs Regular Lambda — Different JVM Types

The `suspend` modifier changes the JVM interface a lambda implements and adds the hidden `Continuation` parameter:

```kotlin
val regular:   () -> String           // JVM: Function0<String>
                                      //   invoke(): String

val suspended: suspend () -> String   // JVM: SuspendFunction0<String>
                                      //   invoke(continuation: Continuation<String>): Any?
```

**These types are not interchangeable:**

```kotlin
fun doWork(action: () -> Unit) { action() }

suspend fun caller() {
    doWork { delay(100) }  // COMPILE ERROR: delay is suspend, doWork expects regular lambda
}
// Must change to: suspend fun doWork(action: suspend () -> Unit)
```

---

## `Thread.sleep` vs `delay` vs `withContext`

Three tools — radically different behaviour on threads:

```kotlin
suspend fun example() {
    Thread.sleep(1000)                       // BAD: blocks the thread
    delay(1000)                              // GOOD: suspends the coroutine
    withContext(Dispatchers.IO) { doIO() }   // GOOD: runs blocking work on IO pool
}
```

```
Thread.sleep(1000):
  OS puts the thread to sleep
  Thread: BLOCKED — unavailable for 1 full second
  Other coroutines on this thread: ALSO BLOCKED
  Dispatcher: can schedule nothing on this thread

delay(1000):
  Coroutine saves its state (Continuation) to heap
  Returns COROUTINE_SUSPENDED to the dispatcher
  Thread: FREED — dispatcher runs other coroutines on it
  After 1s: timer fires → dispatcher resumes this coroutine

withContext(Dispatchers.IO) { doIO() }:
  Current coroutine suspends on current thread
  doIO() runs on the IO thread pool (designed for blocking calls)
  When done: coroutine resumes on original dispatcher
  Use for: database queries, file I/O, network calls
```

**Rule: never `Thread.sleep` inside a coroutine. Use `delay` for waiting, `withContext(Dispatchers.IO)` for blocking I/O.**

---

## `CancellationException` Must Always Be Re-Thrown

When `job.cancel()` is called, the runtime throws `CancellationException` at the next suspension point. If you catch it without re-throwing, the coroutine never stops — it runs forever (zombie coroutine).

```kotlin
// WRONG — generic catch swallows CancellationException:
suspend fun badRetry(block: suspend () -> String): String {
    while (true) {
        try {
            return block()
        } catch (e: Exception) {    // catches CancellationException too!
            delay(100)              // delay ALSO throws CancellationException
                                    // → caught again → infinite loop
        }
    }
}

// CORRECT — always re-throw CancellationException first:
suspend fun goodRetry(times: Int, block: suspend () -> String): String {
    repeat(times) { attempt ->
        try {
            return block()
        } catch (e: CancellationException) {
            throw e                 // ALWAYS re-throw
        } catch (e: Exception) {
            if (attempt == times - 1) throw e
            delay(100L * (attempt + 1))
        }
    }
    throw IllegalStateException("Exhausted retries")
}
```

```
job.cancel()
    │
    ▼
Runtime sets cancellation flag
    │
    ▼
Next suspension point (delay / withContext / await / yield)
    │
    ▼
Throws CancellationException
    │
    ├── re-thrown → propagates up → coroutine stops cleanly ✓
    └── swallowed → coroutine continues running → zombie ✗
                    next delay also throws CE → caught again → ∞ loop
```

---

## Memory Trick

```
Continuation<T> = "the rest of the program" stored on the heap.
  Holds: local variables at suspension point + "what to run next"
  Survives across threads because it's on the heap, not the stack.

suspend lambda → invoke(continuation: Continuation<T>): Any?
  Returns value directly  → completed without suspending
  Returns COROUTINE_SUSPENDED → caller should wait; resume() called later

Thread.sleep vs delay vs withContext:
  sleep        → OS blocks thread → nothing runs on it → jank
  delay        → coroutine suspends → thread freed for others
  withContext  → switch to correct dispatcher for blocking I/O

CancellationException = "please stop" signal.
  catch (e: CancellationException) { throw e }  ← MANDATORY pattern
  catch (e: Exception) catches CE too — always check CE first.
  Zombie = coroutine where CE was swallowed → runs forever.
```

---

## Self-Test

1. What is a `Continuation<T>`? Why does it live on the heap instead of the stack?
2. What is CPS transformation? What hidden parameter does the compiler add to every `suspend` function?
3. What is the JVM type of `suspend () -> String`? How does its `invoke` differ from `() -> String`'s?
4. Why does `Thread.sleep(1000)` block other coroutines but `delay(1000)` doesn't?
5. When would you use `withContext(Dispatchers.IO)` instead of `delay`?
6. Why does catching `Exception` broadly in a coroutine create a zombie?

---

# Q4.5 — Scope Functions

> **Builds on:** [Q4.3 (all scope functions are inline)](#q43--inline-noinline-crossinline) · [Q6.1 (extension functions)](06_extension_functions.md#q61--compilation-and-dispatch)
> **Connects to:** [Q6.5 (extension lambdas — the mechanism scope functions use)](06_extension_functions.md#q65--extension-lambdas-and-dsls)

---

## Two Axes, Five Functions

Two questions determine which scope function to use:

```
Q1: How does the block access the object?
    this → block is an extension lambda on the object (obj.run { this.field })
           "this" is the object — you're "inside" it
    it   → block is a regular lambda receiving the object as a parameter
           "it" is the object — you're "looking at" it from outside

Q2: What does the function return?
    block result → the last expression of the block
    the object   → the same object that was the receiver/argument
```

```
              │  Access via THIS  │  Access via IT
──────────────┼───────────────────┼──────────────────
RETURNS block │   run { }         │   let { }
result        │   with(obj) { }   │
──────────────┼───────────────────┼──────────────────
RETURNS the   │   apply { }       │   also { }
object        │                   │
```

All five are `inline` — zero overhead at runtime.

---

## `with` Is NOT an Extension Function — Why This Matters

`let`, `run`, `apply`, `also` are extension functions: `obj.let { }`, `obj.apply { }`.

`with` is a **top-level function** taking the object as its first regular argument:

```kotlin
// Actual signatures:
inline fun <T, R> T.let(block: (T) -> R): R            // extension on T
inline fun <T, R> T.run(block: T.() -> R): R            // extension on T
inline fun <T>    T.apply(block: T.() -> Unit): T       // extension on T
inline fun <T>    T.also(block: (T) -> Unit): T         // extension on T

inline fun <T, R> with(receiver: T, block: T.() -> R): R  // NOT an extension!
```

**Why this matters for null safety:**

```kotlin
val obj: MyClass? = getObj()

obj?.let { it.doSomething() }   // ✓ safe — let is an extension, ?. short-circuits
obj?.run { doSomething() }      // ✓ safe — run is an extension, ?. short-circuits

with(obj) { doSomething() }     // ✗ UNSAFE — obj is a regular argument
                                //   null is passed in, no ?. short-circuit
                                //   NullPointerException if obj is null
```

`with` is designed for non-null objects you already have. Use it for multiple operations on a known-non-null value.

---

## Standalone `run { }` — Complex `val` Initialisation

`run` has two forms. The extension form `obj.run { }` sets `this = obj`. The standalone form `run { }` has no receiver — it just runs a block and returns its result:

```kotlin
// Extension form: this = someObject
val result = someObject.run { process() }

// Standalone form: scoped computation — useful for complex val initialisation
val config = run {
    val host = System.getenv("HOST") ?: "localhost"
    val port = System.getenv("PORT")?.toInt() ?: 8080
    ServerConfig(host, port)   // last expression = returned value
}
// config is a ServerConfig, cleanly initialised without temp vars leaking into scope
```

Standalone `run` is the idiomatic way to initialise a `val` that requires several intermediate steps.

---

## Each Function With Concrete Use

```kotlin
// let — transform; null-safe chain (it, returns block result)
val len: Int = "hello".let { it.length }            // 5
val upper = nullableStr?.let { it.uppercase() }     // only runs if non-null

// run — compute something using this (this, returns block result)
val result = "  hello  ".run {
    val trimmed = trim()           // this = the string
    trimmed.uppercase()            // → "HELLO"
}

// apply — configure an object and return it (this, returns the object)
val view = TextView(context).apply {
    text = "Hello"                 // this = TextView
    textSize = 16f
    setTextColor(Color.RED)
}  // view = the configured TextView

// also — side effect without interrupting a chain (it, returns the object)
val users = loadUsers()
    .also { println("Loaded ${it.size} users") }  // log, chain continues
    .also { analytics.track("loaded") }

// with — multiple calls on a known non-null object (this, returns block result)
val summary = with(user) {        // user must be non-null
    "$name is $age years old"     // this = user
}
```

---

## The Classic Logic Bugs

```kotlin
// BUG 1: let returns the block result — used apply's job
val user = User("Alice").let {
    it.name = "Bob"
    "Done"            // let returns "Done" — user is now a String, not a User!
}

// CORRECT: apply returns the object
val user = User("Alice").apply {
    name = "Bob"      // this = User — apply returns the User
}

// BUG 2: also returns the original object — used let's job
val len = "hello".also { it.length }   // len = "hello", not 5

// CORRECT: let returns the block result
val len = "hello".let { it.length }    // len = 5
```

---

## Decision Guide

```
Transform a value?              → let { }       (it, block result)
Configure and return object?    → apply { }     (this, object)
Side effect, keep chain going?  → also { }      (it, object)
Compute using this, need result?→ run { }       (this, block result)
Multiple ops on known non-null? → with(obj) {}  (this, block result)
Complex val initialisation?     → run { }       (standalone, no receiver)
Null-safe operation?            → ?.let { }     (runs only if non-null)
```

---

## Memory Trick

```
TWO QUESTIONS to pick the right scope function:
  Q1: this (object is the context) or it (object is a named argument)?
      this: run, apply, with
      it:   let, also

  Q2: returns block result or the original object?
      block result: let, run, with
      the object:   apply, also

KEY GOTCHAS:
  with = top-level function, NOT extension → unsafe with nullable objects
  run  = two forms: obj.run { } (extension) and run { } (standalone)
  let returns the block — don't use it when you want the object back
  also returns the object — don't use it when you want the block result

All five: INLINE → zero overhead.
```

---

## Self-Test

1. What does `apply` return? What does `let` return?
2. `"hello".also { it.uppercase() }` — what is the result and type? Why?
3. Why is `with(nullableObj) { ... }` unsafe while `nullableObj?.let { ... }` is safe?
4. What is standalone `run { }` useful for? Write an example.
5. Configure a `TextView` using `apply`.
6. `user.let { it.name }` vs `user.run { name }` — same result, different style. When would you prefer each?

---

# Q4.6 — Named and Default Parameters

> **Builds on:** [Q2.8 (@JvmOverloads)](02_classes_and_objects.md#q28--constructor-visibility-and-factory-patterns)
> **Connects to:** [Q4.2 (SAM — default params invisible across SAM boundaries)](#q42--function-references-and-sam-conversions)

---

## The Core Mechanism: Bitmask Encoding

Default parameters compile to a synthetic `$default` method that uses an integer bitmask to track which arguments were omitted.

**What is a bitmask?** A single integer where each bit encodes one boolean fact. Bit position 0 = "was the 1st default param omitted?", bit position 1 = "was the 2nd?", etc.

```
fun connect(host: String, port: Int = 443, ssl: Boolean = true)
                                 ↑               ↑
                               bit 0           bit 1

connect("h")             → port omitted, ssl omitted
                           bit 0 = 1, bit 1 = 1
                           mask = 0b11 = 1 + 2 = 3

connect("h", 8080)       → only ssl omitted
                           bit 0 = 0, bit 1 = 1
                           mask = 0b10 = 2

connect("h", 8080, false)→ nothing omitted
                           no $default call — full method called directly
```

---

## What the Compiler Generates

```kotlin
fun connect(host: String, port: Int = 443, ssl: Boolean = true) {
    println("$host:$port ssl=$ssl")
}
```

```java
// 1. Full method — all params explicit:
public static void connect(String host, int port, boolean ssl) { ... }

// 2. Synthetic $default — reads bitmask, fills defaults, calls full method:
public static void connect$default(String host, int port, boolean ssl,
                                    int mask, Object marker) {
    if ((mask & 1) != 0) port = 443;   // bit 0 set → port was omitted
    if ((mask & 2) != 0) ssl  = true;  // bit 1 set → ssl was omitted
    connect(host, port, ssl);
}
// `marker` is always null — exists only to give $default a unique JVM signature
// so it never accidentally clashes with a user-defined overload.
```

Call sites generated by the compiler:

```
connect("h")
  → connect$default("h", 0, false, 3, null)
    mask=3 = 0b011: bit 0 → port=443, bit 1 → ssl=true

connect("h", 8080)
  → connect$default("h", 8080, false, 2, null)
    mask=2 = 0b010: bit 0 clear (port=8080 kept), bit 1 → ssl=true
```

---

## Named Parameters — Reorder and Skip

Named params let you supply arguments in any order and **skip middle params**, which is impossible with positional-only args:

```kotlin
class Button(
    val text: String,
    val color: Color = Color.BLACK,
    val size: Int = 14
)

Button("Ok")                         // both defaults
Button("Ok", Color.RED)              // size default
Button("Ok", Color.RED, 18)          // all explicit
Button("Ok", size = 18)              // ← SKIP color — impossible without named params
```

Also essential for safety when multiple params share the same type:

```kotlin
fun configure(timeout: Int, retries: Int, maxSize: Int) { }
configure(5000, 3, 100)                                 // which is which? Easy to swap
configure(timeout = 5000, retries = 3, maxSize = 100)   // unambiguous
```

---

## `@JvmOverloads` for Java Callers

Java sees only the full method signature — no default params. `@JvmOverloads` generates real Java overloads:

```kotlin
@JvmOverloads
fun connect(host: String, port: Int = 443, ssl: Boolean = true) { }
```

```java
// Generated — N+1 overloads for N default params:
void connect(String host)
void connect(String host, int port)
void connect(String host, int port, boolean ssl)
```

Always add `@JvmOverloads` on public APIs that Java code calls.

---

## Memory Trick

```
DEFAULT PARAMS = compiler generates $default(args..., mask, null).
  Each omitted arg → its bit SET in mask.
  $default reads each bit → fills default → calls full method.

Bit positions:
  1st default param → bit 0  (mask value 1)
  2nd default param → bit 1  (mask value 2)
  3rd default param → bit 2  (mask value 4)
  All 3 omitted     → 1 + 2 + 4 = 7

The `marker` null Object:
  Always null. Makes $default JVM signature unique.
  Prevents accidental clash with real overloads.

NAMED PARAMS:
  Reorder freely. Skip middle params. Explicit intent.
  Essential when multiple params share the same type.

@JvmOverloads:
  Without: Java sees only the full method.
  With: generates N+1 real Java overloads.

DEFAULT PARAMS > secondary constructors (unless init logic truly differs).
```

---

## Self-Test

1. What two methods does the compiler generate for a function with default params?
2. `connect("h")` where `connect(host, port=443, ssl=true)` — what bitmask? Show the binary.
3. What is the `marker` Object parameter in `$default` for?
4. Why can Java not see Kotlin default params without `@JvmOverloads`?
5. What does `@JvmOverloads` generate for 3 default params?
6. When would you still choose a secondary constructor over default params?

---

# Master Summary: Phase 4

**1. Lambda Compilation** (Q4.1)
Lambda = anonymous class implementing `FunctionN<in P, out R>`. Non-capturing → singleton. Capturing → new object per call → GC. Variance: `in P` consumes, `out R` produces.

**2. Function References + SAM** (Q4.2)
`::fn` = lambda delegating to existing function. Unbound/constructor refs → singletons. Bound refs (instance::fn) → capture instance → allocate. Java SAM: auto-conversion. Kotlin interface: no auto-conversion. `fun interface`: opt-in SAM.

**3. `inline`** (Q4.3)
Pastes both bodies at call site. No anonymous class. Enables non-local return (lambda IS the outer body). `crossinline` = paste but ban non-local return (outer frame gone at execution time). `noinline` = keep as object. Harmful: large body bloat, library binary compat.

**4. `suspend` lambdas** (Q4.4)
`Continuation<T>` = heap-stored callback holding paused state. `suspend () -> T` adds hidden continuation param (CPS). `Thread.sleep` blocks thread. `delay` suspends coroutine, frees thread. `withContext` switches dispatcher for blocking I/O. `CancellationException` = always re-throw.

**5. Scope Functions** (Q4.5)
All inline. `this` (run/apply/with) vs `it` (let/also). Returns block result (let/run/with) vs object (apply/also). `with` = not an extension → unsafe with nullable. Standalone `run { }` for complex `val` init.

**6. Default + Named Parameters** (Q4.6)
Compiler generates `$default(args, mask, null)`. Bitmask: each omitted param sets its bit. Named params: reorder, skip middle args. `@JvmOverloads` = N+1 Java overloads.

---

## Master Chain: Functions

```
Lambda = anonymous class (FunctionN<in P, out R>)
      │
      ├── non-capturing → singleton (zero alloc after class load)
      │   capturing    → new object per call (GC pressure)
      │
      ├── inline → pastes both bodies at call site → no object
      │         │
      │         ├── enables non-local return (body IS in outer scope)
      │         ├── enables reified (T known at paste site — Q3.4)
      │         ├── crossinline → paste + ban non-local return
      │         │   (outer stack frame is gone by execution time)
      │         └── noinline → keep as Function object
      │               (for storing, passing to non-inline, returning)
      │
      ├── ::method → function reference
      │   no capture  → singleton
      │   bound x::fn → captures x → allocates
      │   Java interface → SAM auto-conversion
      │   fun interface  → Kotlin opt-in SAM
      │
      └── suspend lambda → invoke(Continuation<T>): Any?
                │
                ├── Continuation = paused state on heap (CPS transform)
                ├── delay → suspend, free thread
                ├── Thread.sleep → block thread (NEVER in coroutines)
                ├── withContext → switch dispatcher for blocking I/O
                └── CancellationException → always re-throw
```

---

*← [Phase 3 — Generics and Variance](03_generics_and_variance.md) | [Phase 5 — Properties and Delegation →](05_properties_and_delegation.md)*