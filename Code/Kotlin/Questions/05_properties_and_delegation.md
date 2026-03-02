# Phase 5: Properties and Delegation

## Navigation
[← Master Index](master_chains.md)

## Questions in This File
- [Q5.1 — `lateinit` Internals](#q51--lateinit-internals)
- [Q5.2 — `lazy` Internals](#q52--lazy-internals)
- [Q5.3 — Delegates](#q53--delegates)

---

## Q5.1 — `lateinit` Internals

> **Builds on:** [Q0.1 — primitives vs references](00_jvm_mental_model.md#q01--primitives-vs-references) · [Q1.2 — nullability](01_type_system_foundations.md#q12--nullability-at-the-type-level)
> **Reference:** [Kotlin Docs — Late-initialized properties](https://kotlinlang.org/docs/properties.html#late-initialized-properties-and-variables)

### The Concrete Picture

You want a non-nullable property you can't initialize yet:

```kotlin
class MyActivity : Activity() {
    lateinit var binding: ActivityMainBinding   // declared non-nullable
    // Can't initialize here — need inflater, which needs context from onCreate()

    override fun onCreate(...) {
        binding = ActivityMainBinding.inflate(layoutInflater)  // initialized here
    }
}
```

How lateinit tracks "not yet initialized":
```
Before onCreate():          After onCreate():
binding field = null        binding field = 0x7f3a──► ActivityMainBinding object
(JVM zero-init)             (set by you)

Read binding before init:
  getter checks: is backing field null?
  YES → throw UninitializedPropertyAccessException (not NPE!)
  NO  → return the value
```

`null` IS the sentinel. That's why `lateinit var count: Int` is IMPOSSIBLE:
`Int` → JVM `int` (primitive) → can't be null → no sentinel → no lateinit.

### First Principles: The Problem `lateinit` Solves

Kotlin's null safety requires every property to be initialized at declaration time OR be declared nullable (`String?`). But some properties genuinely cannot be initialized in a constructor — for example:

- Android `Activity` properties that need `onCreate()` to run first
- Test class properties that need the test framework to inject
- DI (Dependency Injection) fields injected post-construction

Without `lateinit`, you'd have to write `var name: String? = null` — and then use `name!!` or `name?.` everywhere, losing null safety for a property you *know* will be non-null once initialized.

`lateinit` bridges this gap: declare as non-nullable, initialize later, get an informative error if accessed before initialization.

### The Sentinel Value — How `lateinit` Works Internally

`lateinit var` uses the **null reference as its uninitialized sentinel**. The backing field is left `null` by the JVM's zero-initialization, and `lateinit` uses this to track whether the property has been set.

```kotlin
class MyActivity : Activity() {
    lateinit var binding: ActivityMainBinding

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
    }
}
```

**Decompiled Java:**
```java
public class MyActivity extends Activity {
    // The backing field — initially null (JVM zero-initializes):
    public ActivityMainBinding binding;  // null = uninitialized sentinel

    @Override
    public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        binding = ActivityMainBinding.inflate(getLayoutInflater());
    }

    // Generated getter with null check:
    public final ActivityMainBinding getBinding() {
        ActivityMainBinding var = this.binding;
        if (var == null) {
            // throw UninitializedPropertyAccessException (not NullPointerException!)
            throw new UninitializedPropertyAccessException(
                "lateinit property binding has not been initialized"
            );
        }
        return var;
    }
}
```

```
MEMORY MODEL:
                                    Heap
┌──────────────────────────┐       ┌─────────────────────────────┐
│  MyActivity object       │       │  ActivityMainBinding object  │
│                          │       └─────────────────────────────┘
│  binding ──────────────────────►  (set after onCreate)
│                          │
│  [before onCreate]       │
│  binding = null ◄──────────  sentinel: property not initialized yet
└──────────────────────────┘
```

### Why `lateinit var count: Int` Fails

`Int` in Kotlin maps to the JVM primitive `int`. The JVM primitive `int` **cannot be null** — it's a value, not a reference.

The `lateinit` sentinel is `null`. If there's no `null`, there's no sentinel. There's no way to represent "this `int` has not been initialized yet."

```
Reference type (String):        Primitive type (int):
┌──────────────────────┐        ┌──────────────────────┐
│  null = no object    │        │  0 = valid value!    │
│       = uninitialized│        │  Cannot distinguish   │
│       → perfect      │        │  "not initialized"   │
│         sentinel     │        │  from "value is 0"   │
└──────────────────────┘        └──────────────────────┘
      lateinit works ✓                 lateinit FAILS ✗
```

**The alternative for primitives:** `Delegates.notNull<Int>()` — stores the value as `Any?`, using `null` as the sentinel but boxing the int when it IS initialized. (See Q5.3)

### Why `UninitializedPropertyAccessException` and NOT `NullPointerException`

This is a design choice about information quality:
- `NullPointerException` tells you: "something was null"
- `UninitializedPropertyAccessException` tells you: "property X of class Y was not initialized"

The exception message explicitly names the property:
```
UninitializedPropertyAccessException: lateinit property binding has not been initialized
```

This is infinitely more debuggable than a generic NPE with no context.

**Contract expressed:** "`lateinit` is a promise that you'll initialize before first use. If you break that promise, you get a descriptive error, not a mysterious null."

### `::property.isInitialized` — Null Check Under the Hood

```kotlin
if (::binding.isInitialized) {
    binding.doSomething()
}
```

**Decompiled:**
```java
if (this.binding != null) {  // just a null check! No reflection!
    this.getBinding().doSomething();
}
```

`isInitialized` compiles to a simple `!= null` check on the backing field. No reflection API involved. It's as cheap as a null check.

### Memory Trick

```
LATEINIT = "I promise I'll initialize this before using it."
  Mechanism: null as sentinel on the backing field.
  Read before init: throws UninitializedPropertyAccessException (NOT NullPointerException).

WHY NOT INT?
  int is a JVM primitive → can't be null → no sentinel possible.
  String/Object can be null → null = "not yet set" → lateinit works.

::property.isInitialized:
  NOT reflection. Just a null check on the backing field.
  Available only within the same class (to prevent race conditions from outside).
```

### Why `isInitialized` Is Class-Private

`::property.isInitialized` can only be called from **within the same class** (or its `companion object`).

**Reason:** `isInitialized` accesses the backing field directly (bypasses the getter's null check). Allowing this from outside the class would:
1. Expose implementation detail (the null sentinel)
2. Create TOCTOU (Time-Of-Check-Time-Of-Use) race conditions in multi-threaded code
3. Encourage bad patterns: "check from outside, then access" — the check and use should be atomic within the owning class

---

## Q5.2 — `lazy` Internals

> **Builds on:** [Q0.1 — Heap allocation](00_jvm_mental_model.md#q01--primitives-vs-references) · [Q0.3 — Class loading timing](00_jvm_mental_model.md#q03--class-loading-and-the-static--block)
> **Connects to:** [Q5.3 — Delegates](05_properties_and_delegation.md#q53--delegates) · [Q2.5.5 — lazy vs eager init](02_5_initialization_mechanics.md#q255--property-initializer-order-traps)
> **Reference:** [Kotlin Docs — Lazy properties](https://kotlinlang.org/docs/delegated-properties.html#lazy-properties)

### The Concrete Picture

Expensive property. You only want to compute it once, and only if needed:

```kotlin
class Screen {
    val data by lazy { loadFromDatabase() }  // expensive
}

val s = Screen()     // loadFromDatabase() NOT called yet
s.doOtherWork()      // still not called
val d = s.data       // NOW loadFromDatabase() called — result cached
val d2 = s.data      // cached result returned — NO second call
```

How the thread-safe version works (two-check pattern):
```
First read:
  Check 1 (no lock): value = UNINITIALIZED? → yes → go to slow path
  Acquire lock
  Check 2 (inside lock): still UNINITIALIZED? → yes → run initializer → cache → return

Second read from another thread:
  Check 1 (no lock): value = result (already set) → return immediately → no lock
```

The double-check avoids locking on every read after initialization.

### First Principles: What Problem Does `lazy` Solve?

Some properties are expensive to compute (database queries, network calls, parsing). If they're always initialized eagerly in the constructor, you pay the cost even if they're never used. `lazy` defers initialization to first access and caches the result.

```kotlin
class ProfileScreen {
    // Computed immediately when ProfileScreen is created:
    val eagerUserData = loadUserFromDatabase()  // runs now, even if unused!

    // Computed only when first accessed:
    val lazyUserData by lazy { loadUserFromDatabase() }  // runs on first access
}
```

### The `lazy` Implementation — Double-Checked Locking

`LazyThreadSafetyMode.SYNCHRONIZED` (the default) uses **double-checked locking**:

```kotlin
// From Kotlin stdlib — simplified:
class SynchronizedLazyImpl<out T>(val initializer: () -> T) : Lazy<T> {
    @Volatile private var _value: Any? = UNINITIALIZED_VALUE  // sentinel

    override val value: T
        get() {
            // First check: no lock — fast path
            val v1 = _value
            if (v1 !== UNINITIALIZED_VALUE) {
                @Suppress("UNCHECKED_CAST")
                return v1 as T
            }

            // Slow path: acquire lock
            return synchronized(this) {
                // Second check inside lock: another thread may have initialized it
                val v2 = _value
                if (v2 !== UNINITIALIZED_VALUE) {
                    v2 as T
                } else {
                    val typedValue = initializer()   // run the block
                    _value = typedValue              // cache it
                    typedValue
                }
            }
        }
}
```

**Why two checks?**
- First check (no lock): fast path for the common case. If already initialized, just return — no synchronization overhead.
- Second check (inside lock): after acquiring the lock, verify again. Another thread may have initialized between the first check and lock acquisition.

```
Thread 1                          Thread 2
────────────────────────────────  ────────────────────────────────
reads _value = UNINITIALIZED      reads _value = UNINITIALIZED
acquires lock                     tries to acquire lock → WAITS
reads _value = UNINITIALIZED
calls initializer()
_value = result
releases lock                     ← Thread 2 acquires lock
                                  reads _value = result (initialized!)
                                  returns result (no re-initialization!)
                                  releases lock
```

The `@Volatile` annotation ensures `_value` is written to/read from main memory, not a CPU cache — this is what makes the first check (without lock) safe to read.

### What Happens If the `lazy` Block Throws?

```kotlin
val data by lazy {
    throw IOException("Cannot load data")  // throws on first access
}

try {
    data  // IOException thrown here
} catch (e: IOException) {
    println("Failed")
}

data  // IOException thrown AGAIN — the result was NOT cached!
```

**If the initializer throws, the value is NOT cached.** On the next access, the initializer runs again. The `_value` remains `UNINITIALIZED_VALUE` until the initializer completes successfully.

This means: if the first access fails, subsequent accesses retry. Each access has a chance to succeed (good for transient failures). But it also means repeated expensive work on repeated failures.

### Why `lazy` Requires `val` Not `var`

`lazy` provides a **caching contract**: compute once, return the same value every time. If `lazy` allowed `var`, you could reassign the property — breaking the caching contract and creating confusion about which value "the lazy value" refers to.

The `Lazy<T>` interface only has `value: T` getter and `isInitialized()` — no setter. This reflects the immutability contract.

### `LazyThreadSafetyMode.NONE` — The Unsafe Option

```kotlin
val cache by lazy(LazyThreadSafetyMode.NONE) {
    expensiveComputation()
}
```

`NONE` has no synchronization — no locks, no `@Volatile`. This is the fastest mode, but only safe when:
1. The property is accessed from a single thread (common for UI-only properties)
2. You've verified there's no concurrent access

**The concurrency bug:**
```kotlin
// TWO threads access simultaneously (NONE mode):
Thread 1: reads _value = UNINITIALIZED
Thread 2: reads _value = UNINITIALIZED
Thread 1: calls expensiveComputation()
Thread 2: calls expensiveComputation()  ← runs TWICE! Double initialization!
Thread 1: _value = result1
Thread 2: _value = result2  ← overwrites Thread 1's result!
// result1 and result2 may be different! (especially if computation has side effects)
```

### The `lazy` in Fragment — Destroyed View Leak

```kotlin
class MyFragment : Fragment() {
    // lazy initializes on first access and CACHES FOREVER:
    private val adapter by lazy { MyAdapter() }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        recyclerView.adapter = adapter  // adapter is created here, cached
    }

    // Fragment is hidden, view is destroyed, but adapter is still cached in `lazy`
    // When fragment is shown again:
    override fun onCreateView(...): View {
        // lazy still returns the OLD adapter with reference to OLD views!
    }
}
```

**Why Fragment views are destroyed on backstack (not just rotation):** When a Fragment is placed on the back stack, Android calls `onDestroyView()` — destroying the Fragment's entire View hierarchy to reclaim memory — but **keeps the Fragment instance alive** (`onDestroy()` is NOT called). When the user navigates back, `onCreateView()` runs again, creating a fresh View hierarchy. This is by design: the Fragment object acts as a controller that outlives its views.

```
Back stack navigation lifecycle:
                                                  Fragment instance: ALIVE throughout
                                                          │
navigate forward   ──►  onPause → onStop → onDestroyView()    ← view destroyed!
navigate back      ──►  onCreateView() → onViewCreated()      ← fresh view created
```

This means anything held in a `lazy` property on the Fragment object **persists across backstack transitions** — but the Views it captured are gone (detached, null window token).

**The problem:** `lazy` caches the first value forever. When a Fragment's view is destroyed and recreated (see [Q16.1 — Fragment Lifecycle](16_android_system_internals.md#q161--activity-and-fragment-lifecycle)), the cached adapter may hold references to the destroyed views. This is both a memory leak and a functional bug.

**Fix:** Use `viewLifecycleOwner.lifecycleScope` and re-create view-related objects, or use `viewBinding` which is reset properly.

### Memory Trick

```
LAZY = "compute once, cache forever."
  Default mode: SYNCHRONIZED = double-checked locking = thread-safe.
  NONE mode: no locks = fastest, but only safe for single-threaded access.

IF THE BLOCK THROWS:
  Result is NOT cached. Next access retries. Good for transient failures.
  Bad for expensive operations that always fail → infinite cost on every access.

REQUIRES val: lazy's contract is "same value every time."
  Allowing var would break that contract.

FRAGMENT LEAK with lazy:
  lazy caches FOREVER on the Fragment object.
  Fragment view is destroyed and recreated (back stack navigation).
  Cached adapter holds references to old (destroyed) views.
  Fix: use viewLifecycleOwner or reset in onDestroyView.
```

---

## Q5.3 — Delegates

> **Builds on:** [Q5.1 — lateinit internals](05_properties_and_delegation.md#q51--lateinit-internals) · [Q0.1 — primitives vs references](00_jvm_mental_model.md#q01--primitives-vs-references)
> **Connects to:** [Q5.1 — why primitives can't use lateinit](05_properties_and_delegation.md#q51--lateinit-internals) · [Q0.2 — boxing](00_jvm_mental_model.md#q02--jvm-type-mapping)
> **Reference:** [Kotlin Docs — Delegated Properties](https://kotlinlang.org/docs/delegated-properties.html)

### The Concrete Picture

`by` redirects the property's getter/setter to another object:

```kotlin
var value: String by SomeDelegate()
```

What happens at every read/write:
```
val x = obj.value     → calls  SomeDelegate.getValue(obj, ::value)
obj.value = "new"     → calls  SomeDelegate.setValue(obj, ::value, "new")

The compiler generates a getter and setter that forward to the delegate.
Your property is just a thin façade.
```

Real example — property that logs every access:
```
config.timeout         → prints "Getting timeout: 5000"  → returns 5000
config.timeout = 3000  → prints "Setting timeout = 3000 (was 5000)"
```

### First Principles: What Is Delegation?

Delegation is the pattern where an object hands off responsibility for some behavior to another object. In Kotlin property delegation, the **property's getter and setter are delegated to another object** (the delegate).

```kotlin
class MyClass {
    var value: String by SomeDelegate()
    //                ^^ `by` = delegate getter/setter to this object
}
```

When you write `obj.value`, the compiler calls `SomeDelegate.getValue(obj, property)`. When you write `obj.value = "x"`, it calls `SomeDelegate.setValue(obj, property, "x")`.

### How `by` Compiles — The Required Interface

A delegate must implement `getValue` (and `setValue` for mutable properties):

```kotlin
// Read-only delegate:
interface ReadOnlyProperty<in ThisRef, out V> {
    operator fun getValue(thisRef: ThisRef, property: KProperty<*>): V
}

// Read-write delegate:
interface ReadWriteProperty<in ThisRef, V> {
    operator fun getValue(thisRef: ThisRef, property: KProperty<*>): V
    operator fun setValue(thisRef: ThisRef, property: KProperty<*>, value: V)
}
```

**Example custom delegate:**
```kotlin
class LoggingDelegate<T>(private var value: T) {
    operator fun getValue(thisRef: Any?, property: KProperty<*>): T {
        println("Getting ${property.name}: $value")
        return value
    }
    operator fun setValue(thisRef: Any?, property: KProperty<*>, newValue: T) {
        println("Setting ${property.name} = $newValue (was $value)")
        value = newValue
    }
}

class Config {
    var timeout: Int by LoggingDelegate(5000)
}

val config = Config()
config.timeout        // prints: Getting timeout: 5000
config.timeout = 3000 // prints: Setting timeout = 3000 (was 5000)
```

**Decompiled Java (how the compiler generates it):**
```java
public class Config {
    private final LoggingDelegate timeout$delegate = new LoggingDelegate(5000);

    public int getTimeout() {
        return timeout$delegate.getValue(this, $$delegatedProperties[0]);
    }
    public void setTimeout(int value) {
        timeout$delegate.setValue(this, $$delegatedProperties[0], value);
    }
}
```

### `Delegates.notNull<Int>()` — The `lateinit` Workaround for Primitives

Recall: [`lateinit`](05_properties_and_delegation.md#q51--lateinit-internals) can't work with `Int` because `Int` maps to primitive `int` and there's no null sentinel.

`Delegates.notNull<Int>()` stores the value as `Any?` internally ([boxing](00_jvm_mental_model.md#q02--jvm-type-mapping) the int), using `null` as the sentinel:

```kotlin
class Counter {
    var count: Int by Delegates.notNull()  // works! Even for Int!

    fun initialize(value: Int) {
        count = value
    }
}

Counter().count  // throws BEFORE initialize() is called
```

**Decompiled equivalent:**
```java
public class NotNullVar<T> {
    private Object value = null;  // nullable — can store null sentinel

    public T getValue() {
        if (value == null) {
            throw new IllegalStateException("Property has not been initialized");
        }
        return (T) value;  // cast back to T (unboxing if needed)
    }

    public void setValue(T newValue) {
        value = newValue;  // stores the int as Integer (boxed)
    }
}
```

### `lateinit` vs `Delegates.notNull()` — Exception Type Difference

| Situation | `lateinit` | `Delegates.notNull()` |
|-----------|-----------|----------------------|
| Access before init | `UninitializedPropertyAccessException` | `IllegalStateException` |
| Exception message | "lateinit property X has not been initialized" | "Property X should be initialized before get" |
| Debugging clarity | ✓ Clear, specific | ✗ More generic |
| Works with primitives | ✗ No | ✓ Yes |
| Overhead | Zero (null check on field) | Slight (boxing + delegate call) |

### `by map` Delegation — JSON Deserialization Pattern

Property delegation to a `Map` lets you expose map keys as typed properties:

```kotlin
class User(val map: Map<String, Any?>) {
    val name: String by map    // reads map["name"]
    val age: Int by map        // reads map["age"]
    val email: String by map   // reads map["email"]
}

val data = mapOf("name" to "Alice", "age" to 30, "email" to "alice@example.com")
val user = User(data)
println(user.name)  // "Alice" — reads from map
println(user.age)   // 30
```

This is the foundation of JSON deserialization libraries. A JSON object is parsed into a `Map<String, Any?>`, then typed properties access the values by key.

```kotlin
// MutableMap for mutable properties:
class MutableUser(val map: MutableMap<String, Any?>) {
    var name: String by map
    var age: Int by map
}

val user = MutableUser(mutableMapOf("name" to "Alice", "age" to 30))
user.name = "Bob"  // modifies map["name"]
println(user.map)  // {name=Bob, age=30}
```

### Memory Trick

```
DELEGATE = object that handles the property's get/set.
`by` = "give this property's behavior to this delegate."

Compiler generates:
  val p$delegate = SomeDelegate()
  fun getP() = p$delegate.getValue(this, ::p)
  fun setP(v) = p$delegate.setValue(this, ::p, v)

COMMON DELEGATES:
  lazy    → deferred initialization, cached
  notNull → lateinit for primitives (boxes them as Any?)
  by map  → reads/writes from a Map (JSON pattern)
  observable → callback on every change (Delegates.observable)

lateinit vs notNull:
  lateinit    → null sentinel, no boxing, better error message (UIAPE)
  notNull<Int> → null sentinel on boxed value, generic error (IllegalStateException)
  Use lateinit when you can (non-primitive), notNull for primitives.
```

### `ReadOnlyProperty` vs `ReadWriteProperty`

```kotlin
// ReadOnlyProperty: 1 method (getValue)
interface ReadOnlyProperty<in ThisRef, out V> {
    operator fun getValue(thisRef: ThisRef, property: KProperty<*>): V
}

// ReadWriteProperty: 2 methods (getValue + setValue)
interface ReadWriteProperty<in ThisRef, V> : ReadOnlyProperty<ThisRef, V> {
    override operator fun getValue(thisRef: ThisRef, property: KProperty<*>): V
    operator fun setValue(thisRef: ThisRef, property: KProperty<*>, value: V)
}
```

- Use `ReadOnlyProperty` for `val` delegates (read-only properties)
- Use `ReadWriteProperty` for `var` delegates (mutable properties)
- Note: `ReadWriteProperty` extends `ReadOnlyProperty` in Kotlin 1.6+

---

## Master Summary: Properties and Delegation in 5 Points

```
┌────────────────────────────────────────────────────────────────────────┐
│  1. `lateinit` uses null as the uninitialized sentinel.               │
│     That's why Int (primitive, can't be null) is forbidden.           │
│     Throws UninitializedPropertyAccessException, not NPE.            │
│                                                                        │
│  2. `lazy` uses double-checked locking by default (SYNCHRONIZED).     │
│     If the block throws, the value is NOT cached — next access retries│
│     `lazy` requires `val` to enforce its caching contract.            │
│                                                                        │
│  3. Delegates compile to getValue/setValue method calls on the        │
│     delegate object. The `by` keyword is syntactic sugar.             │
│                                                                        │
│  4. `Delegates.notNull<Int>()` works for primitives by boxing the     │
│     value as Any? and using null as the sentinel.                     │
│                                                                        │
│  5. `by map` lets you use a Map as backing storage for typed          │
│     properties — the foundation of JSON deserialization patterns.     │
└────────────────────────────────────────────────────────────────────────┘
```

---

*← [Phase 4 — Functions & Lambdas](04_functions_lambdas_inlining.md) | [Phase 6 — Extension Functions →](06_extension_functions.md)*
