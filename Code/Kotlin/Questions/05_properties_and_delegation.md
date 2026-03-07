# Phase 5 — Properties and Delegation

> A Kotlin property is not a field — it's a getter/setter pair with an optional backing field. `lateinit`, `lazy`, and `by` are all different answers to the same question: *when should initialisation happen?*

## Navigation

[← Phase 4 — Functions and Lambdas](04_functions_lambdas_inlining.md) | [→ Phase 6 — Extension Functions](06_extension_functions.md)

## Questions in This File

- [Q5.1 — `lateinit` Internals](#q51--lateinit-internals)
- [Q5.2 — `lazy` Internals](#q52--lazy-internals)
- [Q5.3 — Property Delegates](#q53--property-delegates)

---

# Q5.1 — `lateinit` Internals

> **Builds on:** [Q0.1 (primitives can't be null)](phase0_jvm_mental_model_v3.md#q01--primitives-vs-references-the-two-worlds) · [Q1.2 (nullability)](01_type_system_foundations.md#q12--nullability)
> **Connects to:** [Q5.3 (Delegates.notNull for primitives)](#q53--property-delegates) · [Q2.2 (init block timing)](02_classes_and_objects.md#q22--constructor-mechanics-init-primary-secondary)

---

## The Core Problem

Kotlin requires every non-nullable property to be initialised at declaration time. But some properties can't be initialised until a lifecycle callback runs:

```kotlin
class MyActivity : Activity() {
    val binding: ActivityMainBinding  // COMPILE ERROR — must initialise here
    // Can't: layoutInflater only available after super.onCreate()
}
```

Two alternatives, only one good:

```kotlin
var binding: ActivityMainBinding? = null  // forces ?. and !! everywhere
lateinit var binding: ActivityMainBinding // declares intent: "I will set before use"
```

---

## How `lateinit` Works — Null as Sentinel

The JVM zero-initialises all object reference fields to `null`. `lateinit` exploits this: the backing field *is* null until you assign it, and the generated getter checks for null before returning:

```java
// Decompiled lateinit var binding: ActivityMainBinding:
public class MyActivity extends Activity {
    public ActivityMainBinding binding;   // JVM zero-inits to null

    public final ActivityMainBinding getBinding() {
        ActivityMainBinding v = this.binding;
        if (v == null) {
            throw new UninitializedPropertyAccessException(
                "lateinit property binding has not been initialized"
            );
        }
        return v;
    }
}
```

```
Before onCreate():          After binding = ...:
backing field = null        backing field ──► ActivityMainBinding object

Read before set:
  getter checks: backing == null?
  YES → UninitializedPropertyAccessException (NOT NullPointerException!)
  NO  → return the value
```

---

## Why `lateinit var count: Int` Fails

`Int` maps to JVM primitive `int`. Primitives have no null bit pattern — a 32-bit int can hold values 0 through 2³²-1, and none of those means "uninitialized." There is no sentinel available.

```
Reference field (String):        Primitive field (Int → int):
null = "not yet set" ✓           0 = valid integer, same as "uninitialized 0"
     perfect sentinel                no way to distinguish
→ lateinit works                 → lateinit fails — use Delegates.notNull() (Q5.3)
```

---

## `UninitializedPropertyAccessException` vs `NullPointerException`

This is a deliberate design choice. `UIAPE` names the property in its message:

```
UninitializedPropertyAccessException: lateinit property binding has not been initialized
```

A generic NPE gives you a line number and a stack trace — but no indication of *which* variable was null. `UIAPE` tells you instantly.

---

## `::property.isInitialized` — Just a Null Check

```kotlin
if (::binding.isInitialized) {
    binding.doSomething()
}
```

```java
// Decompiled — it is literally a null check, not reflection:
if (this.binding != null) {
    this.getBinding().doSomething();
}
```

`isInitialized` accesses the backing field directly (bypassing the getter). This is why it is restricted to the **same class**: exposing it externally would:
1. Leak the implementation detail (null = uninitialized)
2. Create TOCTOU races — another thread could set/clear the property between your `isInitialized` check and your actual use

---

## `lateinit` and Threading — An Interview Trap

`lateinit` backing fields are **not `@Volatile`**. Two threads can race:

```
Thread 1: activity.binding = newBinding  // writes backing field
Thread 2: if (binding != null) ...        // may read stale null from CPU cache
                                           // even though Thread 1 already wrote!
```

`lateinit` has no thread-safety guarantee. If multiple threads may access the same `lateinit` property, you must add your own synchronisation (or `@Volatile`).

---

## Memory Trick

```
LATEINIT = null as sentinel on the backing field.
  null → uninitialized → throw UninitializedPropertyAccessException
  non-null → return value

WHY NOT PRIMITIVES:
  int has no null bit pattern → no sentinel → can't distinguish 0 from unset

::prop.isInitialized:
  = backing_field != null (not reflection, zero overhead)
  Restricted to owning class to prevent external TOCTOU races

THREADING TRAP:
  lateinit backing field is NOT @Volatile
  Multi-thread access requires explicit synchronisation

lateinit vs var: String?:
  String? forces ?. and !! everywhere
  lateinit = "I promise I'll set it before use" — compiler trusts you
```

---

## Self-Test

1. What does `lateinit` use as its uninitialized sentinel?
2. Why can't you write `lateinit var count: Int`?
3. What exception does reading an uninitialized `lateinit` throw? Why not NPE?
4. What does `::binding.isInitialized` compile to? Is it reflection?
5. Why is `isInitialized` restricted to the owning class?
6. Is `lateinit` thread-safe? What can go wrong in a multi-threaded scenario?

---

# Q5.2 — `lazy` Internals

> **Builds on:** [Q0.1 (heap allocation)](phase0_jvm_mental_model_v3.md#q01--primitives-vs-references-the-two-worlds) · [Q2.7 (property initializer order)](02_classes_and_objects.md#q27--property-initializer-order-traps)
> **Connects to:** [Q5.3 (delegates — lazy is a delegate)](#q53--property-delegates)

---

## The Core Idea

Expensive property. Compute once. Cache. Only when needed.

```kotlin
class Screen {
    val data by lazy { loadFromDatabase() }
}

val s = Screen()    // loadFromDatabase() NOT called yet
s.doOtherWork()     // still not called
val d = s.data      // NOW called — result cached in the Lazy object
val d2 = s.data     // returns cached result — no second call
```

`lazy` returns a `Lazy<T>` delegate. `by lazy { }` is just `by lazy(LazyThreadSafetyMode.SYNCHRONIZED) { }`.

---

## The `lazy` Implementation — Double-Checked Locking

Default mode (`SYNCHRONIZED`) uses double-checked locking to be thread-safe without locking on every read:

```kotlin
// Simplified from Kotlin stdlib:
class SynchronizedLazyImpl<out T>(val initializer: () -> T) : Lazy<T> {
    @Volatile private var _value: Any? = UNINITIALIZED_VALUE

    override val value: T get() {
        // CHECK 1 — fast path, no lock
        val v1 = _value
        if (v1 !== UNINITIALIZED_VALUE) return v1 as T

        // CHECK 2 — slow path, inside lock
        return synchronized(this) {
            val v2 = _value
            if (v2 !== UNINITIALIZED_VALUE) {
                v2 as T                  // another thread already initialized — return it
            } else {
                val result = initializer()
                _value = result          // store result
                result
            }
        }
    }
}
```

**Why two checks?**

```
Thread 1                            Thread 2
──────────────────────────────────  ──────────────────────────────────
Check 1: _value == UNINITIALIZED    Check 1: _value == UNINITIALIZED
Acquires lock                       Waits at synchronized

Inside lock:
  Check 2: still UNINITIALIZED?
  YES → run initializer()
  _value = result
Releases lock                       Acquires lock

                                    Inside lock:
                                      Check 2: _value == result? NO LONGER UNINITIALIZED
                                      → return cached result (no second init) ✓
                                    Releases lock
```

- **Check 1 (no lock):** After initialisation, every subsequent read takes this fast path — reads the cached value without locking.
- **Check 2 (inside lock):** Handles the race where two threads both pass Check 1. Only one runs the initializer; the other gets the cached value.

---

## `@Volatile` — Why It's Critical

`@Volatile` on `_value` means: every write to `_value` goes **directly to main memory**, and every read fetches from main memory. Without it:

```
Thread 1 writes _value = result  → stored in Thread 1's CPU cache
Thread 2 reads  _value           → reads from ITS CPU cache → still UNINITIALIZED

Result: Thread 2 sees a stale value and re-runs the initializer (double init bug)
```

With `@Volatile`:

```
Thread 1 writes _value = result  → flushed to main memory immediately
Thread 2 reads  _value           → forced to read from main memory → sees result ✓
```

`@Volatile` provides visibility across threads, not atomicity. The lock in Check 2 provides atomicity (mutual exclusion).

---

## Three Thread-Safety Modes

| Mode | Mechanism | Use case |
|---|---|---|
| `SYNCHRONIZED` (default) | Double-checked locking + `@Volatile` | Multi-threaded access — safe everywhere |
| `PUBLICATION` | `@Volatile` only, no lock | Multiple threads may init, but only one result sticks |
| `NONE` | No sync, no volatile | Single-threaded only — fastest |

**`PUBLICATION` mode:**

```kotlin
val value by lazy(LazyThreadSafetyMode.PUBLICATION) { expensiveComputation() }
```

Multiple threads can run `expensiveComputation()` concurrently, but only the **first** result is kept. All other results are discarded. Use when: initialisation is idempotent (running it twice is fine), you want to avoid the lock overhead.

**`NONE` mode — the race condition:**

```kotlin
val cache by lazy(LazyThreadSafetyMode.NONE) { expensiveComputation() }

// With two threads:
Thread 1: _value == UNINITIALIZED → runs expensiveComputation() → result1
Thread 2: _value == UNINITIALIZED → runs expensiveComputation() → result2 (ran TWICE!)
Thread 2 finishes last → _value = result2 (overwrites result1!)
// If expensiveComputation() has side effects, this is a serious bug
```

---

## If the `lazy` Block Throws — Not Cached

```kotlin
val data by lazy { throw IOException("Cannot load") }

try { data } catch (e: IOException) { }
data  // throws IOException AGAIN — throw result is NOT cached
```

If the initializer throws, `_value` stays `UNINITIALIZED_VALUE`. Next access retries. Good for transient failures; bad for operations that always fail (infinite retry).

---

## `lazy` Requires `val` — Immutability Contract

`lazy` promises "compute once, return the same value every time." A `var` would break this — you could reassign and the lazy-computed value would be gone. The `Lazy<T>` interface has no `setValue` method, so `by lazy` is only valid for `val`.

---

## Fragment View Lifecycle + `lazy` — The Memory Leak

```kotlin
class MyFragment : Fragment() {
    private val adapter by lazy { MyAdapter() }  // cached FOREVER on Fragment object

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        recyclerView.adapter = adapter  // adapter created here, holds view references
    }
}
```

**The problem:** Fragment lifecycle on the back stack:

```
Push to back stack:
  onPause → onStop → onDestroyView()   ← View hierarchy DESTROYED, Fragment ALIVE

Pop from back stack:
  onCreateView() → onViewCreated()     ← Fresh views created

  lazy adapter: still cached on Fragment object
               → holds references to the DESTROYED views
               → memory leak + wrong views displayed
```

**Why Fragment instances survive `onDestroyView()`:** Android destroys only the *view hierarchy* when pushing to the back stack (to reclaim memory), but keeps the Fragment instance alive so you can navigate back. The Fragment object persists; the views do not.

**Fix:** Null out view-related references in `onDestroyView()`. Don't use `lazy` for anything that holds view references.

---

## `lazy` vs `lateinit` — Which to Use

| | `lateinit var` | `val by lazy { }` |
|---|---|---|
| Initialised by | You, manually | Automatically on first access |
| Access style | `var` — reassignable | `val` — immutable once set |
| Primitives | ✗ No | ✓ Yes (boxed in `Lazy` wrapper) |
| Thread-safe | ✗ No (not `@Volatile`) | ✓ Yes (default mode) |
| isInitialized | ✓ `::prop.isInitialized` | ✗ Not available |
| Use when | Lifecycle callbacks, DI injection | Expensive one-time computation |

---

## Memory Trick

```
LAZY = "compute once, cache, on first access."
  Default: SYNCHRONIZED = double-checked locking = thread-safe.
  PUBLICATION: multiple inits allowed, first result wins. No lock.
  NONE: no sync = fastest, single-thread only.

@Volatile = writes go to main memory, reads come from main memory.
  Without: threads may read stale CPU-cache value.
  With: all threads see the write immediately.
  Lock = mutual exclusion (only one thread in block at a time).
  Volatile = visibility (writes immediately visible to all threads).

THROW IN BLOCK → not cached → next access retries.
REQUIRES val → "same value every time" = the contract.

FRAGMENT LEAK:
  lazy caches on Fragment object (survives view destroy/recreate)
  → adapter holds destroyed views → memory leak
  Fix: null out in onDestroyView()

lazy vs lateinit:
  lateinit = manual init, var, no thread-safety
  lazy     = auto init on first access, val, thread-safe by default
```

---

## Self-Test

1. Explain both checks in double-checked locking. Why can't you use only one check?
2. What does `@Volatile` guarantee? What does `synchronized` guarantee? Are they the same?
3. What is `LazyThreadSafetyMode.PUBLICATION`? When would you choose it over `SYNCHRONIZED`?
4. What happens if the `lazy` block throws an exception?
5. Why does `lazy` require `val`?
6. Explain the Fragment `lazy` memory leak from first principles.
7. When would you use `lateinit` vs `lazy`?

---

# Q5.3 — Property Delegates

> **Builds on:** [Q5.1 (lateinit as null-sentinel)](#q51--lateinit-internals) · [Q5.2 (lazy is a delegate)](#q52--lazy-internals)
> **Connects to:** [Q0.2 (boxing — notNull boxes primitives)](phase0_jvm_mental_model_v3.md#q02--jvm-type-mapping-when-does-kotlin-box)

---

## The Core Idea

`by` redirects every property read/write to a **delegate object**. The delegate's `getValue` and `setValue` operators handle all access:

```kotlin
var value: String by SomeDelegate()

val x = obj.value     // → SomeDelegate.getValue(obj, ::value)
obj.value = "new"     // → SomeDelegate.setValue(obj, ::value, "new")
```

The property is a façade. The delegate has all the logic.

---

## How `by` Compiles

The delegate must implement operator functions with these exact signatures:

```kotlin
class LoggingDelegate<T>(private var value: T) {
    operator fun getValue(thisRef: Any?, property: KProperty<*>): T {
        println("Reading ${property.name}: $value")
        return value
    }
    operator fun setValue(thisRef: Any?, property: KProperty<*>, newValue: T) {
        println("Writing ${property.name}: $value → $newValue")
        value = newValue
    }
}

class Config {
    var timeout: Int by LoggingDelegate(5000)
}
```

What `KProperty<*>` gives you:
- `property.name` — the property name as a String (`"timeout"`)
- `property.returnType` — the Kotlin type (`Int`)

`thisRef` — the object on which the property lives (the `Config` instance). Useful if your delegate needs to inspect the owner.

```java
// Compiler generates:
public class Config {
    private final LoggingDelegate timeout$delegate = new LoggingDelegate(5000);

    public int getTimeout() {
        return timeout$delegate.getValue(this, $$delegatedProperties[0]);
    }
    public void setTimeout(int v) {
        timeout$delegate.setValue(this, $$delegatedProperties[0], v);
    }
}
```

---

## `Delegates.notNull<Int>()` — `lateinit` for Primitives

`lateinit` can't use `Int` (no null sentinel for primitives). `Delegates.notNull<Int>()` boxes the int as `Any?` and uses `null` as the sentinel:

```kotlin
class Counter {
    var count: Int by Delegates.notNull()
}

val c = Counter()
c.count           // throws IllegalStateException: "Property count should be initialized"
c.count = 5
c.count           // 5
```

```java
// NotNullVar<T> internals:
class NotNullVar<T> {
    private Object value = null;  // null = uninitialized, Object = boxed T

    T getValue() {
        if (value == null) throw new IllegalStateException("...");
        return (T) value;         // unboxes on return
    }
    void setValue(T v) { value = v; }  // boxes int as Integer
}
```

---

## `lateinit` vs `Delegates.notNull()` — Full Comparison

| | `lateinit var` | `Delegates.notNull<T>()` |
|---|---|---|
| Works with primitives | ✗ No | ✓ Yes (boxes as `Any?`) |
| Exception type | `UninitializedPropertyAccessException` | `IllegalStateException` |
| Exception message | "lateinit property X not initialized" | "Property should be initialized" |
| Overhead | Zero (null check on backing field) | Boxing + delegate call |
| `isInitialized` | ✓ `::prop.isInitialized` | ✗ Not available |
| Use when | Non-primitive reference types | Primitives needing deferred init |

---

## `Delegates.observable` — React to Changes

```kotlin
var status: String by Delegates.observable("IDLE") { property, old, new ->
    // Callback signature: (KProperty<*>, T, T) -> Unit
    // old: T = value before change
    // new: T = value after change
    println("${property.name}: $old → $new")
    notifyListeners(new)
}

status = "LOADING"  // prints: status: IDLE → LOADING  (fires AFTER change)
status = "SUCCESS"  // prints: status: LOADING → SUCCESS
```

Callback fires **after** the value has changed. Use for: change notifications, logging, UI updates.

---

## `Delegates.vetoable` — Conditional Change

```kotlin
var age: Int by Delegates.vetoable(0) { property, old, new ->
    // Callback signature: (KProperty<*>, T, T) -> Boolean
    // return true = allow the change, false = reject it
    new >= 0
}

age = 25   // allowed: 25 >= 0 → true
age = -1   // rejected: -1 >= 0 → false, age stays 25
```

Callback fires **before** the value changes. Return `true` to allow, `false` to reject. Use for: validation, constraints.

---

## `by map` Delegation — How It Works Internally

A `Map` implements `getValue` as an operator extension, making it a valid delegate:

```kotlin
// Stdlib provides:
operator fun <V, T : V> Map<in String, V>.getValue(thisRef: Any?, property: KProperty<*>): T =
    getOrElse(property.name) { throw NoSuchElementException(property.name) } as T

// This is what makes `by map` work:
class User(val map: Map<String, Any?>) {
    val name: String by map   // → map.getValue(this, ::name) → map["name"]
    val age: Int by map       // → map.getValue(this, ::age)  → map["age"]
}

val user = User(mapOf("name" to "Alice", "age" to 30))
user.name  // "Alice"
user.age   // 30
```

```kotlin
// Mutable version — MutableMap also implements setValue:
class MutableUser(val map: MutableMap<String, Any?>) {
    var name: String by map
    var age: Int by map
}

val u = MutableUser(mutableMapOf("name" to "Alice", "age" to 30))
u.name = "Bob"
println(u.map)  // {name=Bob, age=30}
```

This is how JSON deserialisation libraries work: parse JSON into `Map<String, Any?>`, expose typed properties via map delegation.

---

## Local Delegated Properties

Delegates work inside functions too, not just classes:

```kotlin
fun loadConfig() {
    val config: ServerConfig by lazy { parseConfigFile() }  // local lazy val
    val host: String by someDelegate()                       // local delegated val

    if (needsConfig) {
        println(config.host)  // only parsed here, on first use
    }
}
```

The delegate object is created at the `val`/`var` declaration and lives for the scope of the function.

---

## `ReadOnlyProperty` and `ReadWriteProperty` Interfaces

For implementing custom delegates with proper types:

```kotlin
// For val (read-only):
interface ReadOnlyProperty<in ThisRef, out V> {
    operator fun getValue(thisRef: ThisRef, property: KProperty<*>): V
}

// For var (read-write):
interface ReadWriteProperty<in ThisRef, V> : ReadOnlyProperty<ThisRef, V> {
    operator fun setValue(thisRef: ThisRef, property: KProperty<*>, value: V)
}
```

You don't have to implement these interfaces (any class with the right operator functions works), but implementing them makes the intent explicit and enables type checking.

---

## All Built-in Delegates

| Delegate | Fires when | Use case |
|---|---|---|
| `lazy { }` | First access | Expensive one-time computation |
| `Delegates.notNull()` | Read before set | Primitive deferred init |
| `Delegates.observable(init) { }` | After every set | Change notification, logging |
| `Delegates.vetoable(init) { }` | Before every set | Validation, constraints |
| `by map` / `by mutableMap` | Every get/set | JSON/config-backed properties |

---

## Memory Trick

```
DELEGATE = object that handles get/set for a property.
`by` = "give this property's access to this object."

Compiler generates:
  val p$delegate = TheDelegate()
  fun getP() = p$delegate.getValue(this, ::p)
  fun setP(v) = p$delegate.setValue(this, ::p, v)

KProperty<*> gives you:
  property.name       → "timeout" (the property name as String)
  property.returnType → the Kotlin type
  thisRef             → the object owning the property

BUILT-IN DELEGATES:
  lazy      → deferred, cached, thread-safe by default
  notNull   → lateinit for primitives (boxes as Any?)
  observable → callback AFTER change (T, T) → Unit
  vetoable  → callback BEFORE change (T, T) → Boolean (true=allow, false=reject)
  by map    → Map.getValue extension — uses property.name as key

by map internals:
  Map<String, Any?> implements getValue via extension
  property.name becomes the map key
  MutableMap also implements setValue

LOCAL DELEGATES:
  Delegates work inside functions, not just classes.
```

---

## Self-Test

1. What two operator functions must a delegate implement for `var`?
2. What does `KProperty<*>` give you inside a delegate's `getValue`?
3. `Delegates.notNull<Int>()` — how does it handle primitives without a null reference?
4. What exception does `notNull` throw? How does it differ from `lateinit`'s exception?
5. `observable` vs `vetoable` — when does the callback fire for each? What does each return?
6. How does `by map` work internally? What stdlib function makes a `Map` a valid delegate?
7. Write a custom delegate that logs every read of a property.

---

# Master Summary: Phase 5

> `lateinit`, `lazy`, and delegates all answer "when does this initialise?" `lateinit` = I'll do it manually before use. `lazy` = automatically on first access, cached. Delegate = an external object decides everything.

**1. `lateinit`** (Q5.1)
Null sentinel on backing field. Reference types only. Getter checks null → `UninitializedPropertyAccessException`. `::prop.isInitialized` = null check, not reflection. Not thread-safe — backing field is not `@Volatile`.

**2. `lazy`** (Q5.2)
Double-checked locking (`SYNCHRONIZED`). `@Volatile` for visibility, `synchronized` for mutual exclusion. `PUBLICATION` = multiple inits OK, first wins. `NONE` = no sync, single-thread. Throw = not cached. `val` only — immutability contract. Fragment lazy = memory leak (survives view destroy).

**3. Delegates** (Q5.3)
`by` compiles to `getValue`/`setValue` on the delegate object. `KProperty<*>` gives name and type metadata. `notNull` = lateinit for primitives (boxes). `observable` = callback after change. `vetoable` = callback before (can reject). `by map` = `Map.getValue` extension uses `property.name` as key.

---

## Master Chain: Properties

```
Property = getter/setter + optional backing field
      │
      ├── eager: val x = compute()  → runs at construction time
      │
      ├── lateinit: deferred manual init
      │     → null sentinel on backing field
      │     → reference types only (primitives have no null)
      │     → UIAPE if read before set
      │     → NOT thread-safe (no @Volatile)
      │
      ├── lazy: deferred automatic init
      │     → Lazy<T> delegate created at class load
      │     → computed on first access, cached
      │     → SYNCHRONIZED: double-checked locking (default)
      │     → PUBLICATION: multiple inits OK, first wins
      │     → NONE: no sync, single-thread only
      │     → @Volatile: write goes to main memory immediately
      │     → throw = not cached, retry on next access
      │     → Fragment lazy = memory leak (view refs survive onDestroyView)
      │
      └── by delegate: external object controls all get/set
            → getValue(thisRef, KProperty<*>)
            → setValue(thisRef, KProperty<*>, value)
            → notNull (primitives, boxes as Any?)
            → observable (callback after change → notify)
            → vetoable (callback before change → validate/reject)
            → by map (Map.getValue extension, property.name = key)
```

---

*← [Phase 4 — Functions and Lambdas](04_functions_lambdas_inlining.md) | [Phase 6 — Extension Functions →](06_extension_functions.md)*