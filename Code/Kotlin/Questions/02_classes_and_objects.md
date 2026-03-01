# Phase 2: Classes and Objects

## Navigation
[← Master Index](master_chains.md)

## Questions in This File
- [Q2.1 — Class Modifiers](#q21--class-modifiers)
- [Q2.2 — Data Classes](#q22--data-classes)
- [Q2.3 — Sealed Classes and Interfaces](#q23--sealed-classes-and-interfaces)
- [Q2.4 — The `object` Keyword](#q24--the-object-keyword)
- [Q2.5 — Value Classes](#q25--value-classes)

---

## Q2.1 — Class Modifiers

> **Builds on:** [Q0.4 — Virtual dispatch](00_jvm_mental_model.md#q04--the-jvm-call-stack)
> **Connects to:** [Q2.5.3 (open function in init is dangerous)](02_5_initialization_mechanics.md#q253--inheritance-initialization-order) · [Q3.2 (final enables devirtualization)](03_generics_and_variance.md#q32--variance)

### Why Are Kotlin Classes `final` by Default?

In Java, all classes are **open by default** — any class can be subclassed unless explicitly marked `final`. This caused a systemic problem: the **fragile base class problem**.

**The Fragile Base Class Problem:**
When a library ships an open class, subclasses can override methods in ways the base class author never intended. When the base class changes its internal method calls (e.g., `methodA()` now internally calls `methodB()`), a subclass that overrides `methodB()` to do extra work suddenly gets that extra work called in unexpected contexts.

```java
// Java base class — intended for inheritance
public class AbstractList {
    public void add(Object e) { ... }
    public void addAll(Collection c) {
        for (Object e : c) add(e);  // calls add() internally
    }
}

// Java subclass — counts adds
public class CountingList extends AbstractList {
    int addCount = 0;
    @Override public void add(Object e) { addCount++; super.add(e); }
    // BUG: addAll(5 items) → addCount becomes 10, not 5!
    // Because addAll calls add() 5 times, and add() is overridden
}
```

Kotlin's solution: **classes are `final` by default**. To allow subclassing, you must explicitly opt in with `open`. This forces API designers to think carefully about what they're allowing.

### `open` vs `final` — Vtable Difference

```kotlin
// Final class (default):
class Calculator {
    fun add(a: Int, b: Int) = a + b
}
```
```bytecode
INVOKEVIRTUAL Calculator.add (II)I
; JIT sees: Calculator is final → only ONE implementation possible
; JIT can devirtualize → INVOKESPECIAL or inline → zero vtable lookup
```

```kotlin
// Open class:
open class Calculator {
    open fun add(a: Int, b: Int) = a + b
}
```
```bytecode
INVOKEVIRTUAL Calculator.add (II)I
; JIT must keep virtual dispatch — unknown subclass might override add()
; vtable lookup on every call
```

**Vtable structure:**
```
final class vtable:          open class vtable:
┌─────────────────┐          ┌─────────────────────────────┐
│ [JVM internals] │          │ [JVM internals]             │
└─────────────────┘          │ Calculator.add → Calculator │
                             │ (subclass can replace this) │
                             └─────────────────────────────┘
```

**Why Kotlin's `final` default matters:** When a class is `final`, the JIT compiler knows there's only ONE possible implementation. It can devirtualize the call (see [Q0.4 — The JVM Call Stack](00_jvm_mental_model.md#q04--the-jvm-call-stack) for vtable details).

### `abstract` vs `open` — Architectural Choice

| Modifier | Can Instantiate? | Must Override? | Use When |
|----------|-----------------|----------------|----------|
| `final` (default) | Yes | N/A | No subclassing intended |
| `open` | Yes | No | Subclassing allowed, base has default behavior |
| `abstract` | **No** | **Yes** (for abstract members) | Subclassing required; base defines contract |

Choose `abstract` when:
- The base class has no meaningful standalone behavior
- You want to **force** subclasses to implement specific methods
- The concept is inherently incomplete without customization

```kotlin
// abstract: Animal is conceptually incomplete — can't speak/move without a body
abstract class Animal {
    abstract fun sound(): String      // must override
    fun breathe() = println("...")    // shared behavior — can override if needed
}

// open: Button has sensible defaults but can be customized
open class Button {
    open fun onClick() { /* default: nothing */ }
}
```

---

## Q2.2 — Data Classes

> **Builds on:** [Q0.1 — Primitives, hashing](00_jvm_mental_model.md#q01--primitives-vs-references)
> **Connects to:** [Q3.2 (UnsafeVariance in covariant types)](03_generics_and_variance.md#q32--variance) · [Q7.1 (List covariance)](07_collections_and_sequences.md#q71--kotlins-collection-hierarchy)

### Which Properties Are Included in Generated Functions?

**Only properties in the primary constructor** are included in `equals`, `hashCode`, `copy`, and `componentN` functions.

```kotlin
data class User(
    val id: Int,        // ← included in equals/hashCode/copy/component1
    val name: String    // ← included in equals/hashCode/copy/component2
) {
    var lastLogin: Long = 0  // ← EXCLUDED — body property, not primary constructor
    val displayName get() = name.uppercase()  // ← EXCLUDED
}
```

```java
// Generated equals (only id and name):
public boolean equals(Object other) {
    if (this == other) return true;
    if (!(other instanceof User)) return false;
    User o = (User) other;
    return id == o.id && name.equals(o.name);
    // lastLogin is NOT compared!
}
```

### The Mutable `var` in Data Class — HashSet Corruption

This is a classic production bug. Here's the **exact sequence**:

```kotlin
data class User(val id: Int, var name: String)  // mutable name!

val set = HashSet<User>()
val user = User(1, "Alice")
set.add(user)
// hashCode = hash(1, "Alice") → bucket #42

user.name = "Bob"  // MUTATION: hashCode changes!
// hashCode = hash(1, "Bob") → bucket #17

// Now: user is in bucket #42, but its hashCode points to #17
println(set.contains(user))  // FALSE — looked in bucket #17, not found!
println(set.size)             // 1 — user IS there, but "lost" in bucket #42
```

```
HashSet Internal State After Mutation:
┌──────────────────────────────────────────┐
│ Bucket #42: [User(1, "Bob")]  ← it's here│
│ Bucket #17: []                ← looked here│
└──────────────────────────────────────────┘
hashCode() says: bucket #17
contains() looks in bucket #17 → empty → returns false!
```

**Rule:** Never use `var` properties in data classes that will be stored in `HashSet`, `HashMap`, or any hash-based collection.

### `copy()` Is Shallow — The MutableList Trap

```kotlin
data class Config(val settings: MutableList<String>)

val original = Config(mutableListOf("dark_mode", "notifications"))
val copy = original.copy()

copy.settings.add("analytics")  // modifies the shared list!

println(original.settings)  // [dark_mode, notifications, analytics] — original changed!
```

```
After copy():
original.settings ──────┐
                         ▼
copy.settings    ──── [MutableList in heap]
                        Both point to the SAME object!
```

**Fix — deep copy:**
```kotlin
val deepCopy = original.copy(settings = original.settings.toMutableList())
```

### `@UnsafeVariance` in `List.contains()`

[`List<out E>`](07_collections_and_sequences.md#q71--kotlins-collection-hierarchy) is [covariant](03_generics_and_variance.md#q32--variance) — `E` only appears in "out" (producer) positions. But `contains(element: E)` takes `E` as a parameter (in position), which violates covariance.

The Kotlin stdlib uses `@UnsafeVariance` to override this restriction:

```kotlin
interface List<out E> {
    fun contains(element: @UnsafeVariance E): Boolean
    // Without @UnsafeVariance: COMPILE ERROR — E in contravariant position
}
```

It's "safe" here because `contains` only **reads** `element` to compare it — it never stores `element` into the list. The type system's concern (you might put a Cat into a List<Dog>) doesn't apply to a read-only comparison.

---

## Q2.3 — Sealed Classes and Interfaces

> **Builds on:** [Q1.3 — Nothing, Unit](01_type_system_foundations.md#q13--nothing-unit-and-the-type-hierarchy) · [Q2.1 — Class Modifiers (final/open)](02_classes_and_objects.md#q21--class-modifiers)
> **Connects to:** [Q1.3 (Nothing in sealed subtypes)](01_type_system_foundations.md#q13--nothing-unit-and-the-type-hierarchy) · [Q1.4 (when exhaustiveness)](01_type_system_foundations.md#q14--smart-casts)

### What Bytecode Does `sealed class` Compile To?

```kotlin
sealed class Result<out T> {
    data class Success<T>(val data: T) : Result<T>()
    data class Error(val message: String) : Result<Nothing>()
    object Loading : Result<Nothing>()
}
```

```java
// Decompiled sealed class:
public abstract class Result {
    // Constructor is package-private (not private!) — allows subclasses in same package
    private Result() {}
    // Kotlin 1.5+: subclasses can be in different files in same package/module

    public static final class Success extends Result { ... }
    public static final class Error extends Result { ... }
    public static final class Loading extends Result { ... }
}
```

The **private constructor** prevents subclassing from outside the sealed hierarchy. The compiler tracks all subclasses and uses this knowledge for exhaustiveness checking.

### How `when` Achieves Compile-Time Exhaustiveness

The compiler knows all subclasses at compile time (they're declared in the same file/package). A `when` on a sealed class **requires handling all branches** when used as an expression.

```kotlin
fun handleResult(result: Result<User>): String = when (result) {
    is Result.Success -> "Data: ${result.data}"
    is Result.Error -> "Error: ${result.message}"
    is Result.Loading -> "Loading..."
    // If you remove any branch → COMPILE ERROR: 'when' expression must be exhaustive
}
```

```
Compiler's knowledge at compile time:
Result subclasses = {Success, Error, Loading}
when branches covered = {Success, Error, Loading}
All covered? YES → no else required, exhaustive!
```

Adding a new subclass to the sealed class → compile error in all `when` expressions → forces you to handle it. This is the key advantage over `enum` (can't carry data) and open classes (can't know all subclasses).

### Sealed Class vs Sealed Interface vs Enum Class

| Feature | `enum class` | `sealed class` | `sealed interface` |
|---------|--------------|-----------------|-------------------|
| Can carry different data per subtype | No (shared fields) | Yes | Yes |
| Can have multiple instances per subtype | No (one per variant) | Yes | Yes |
| Can extend other classes | No | Only one superclass | Can implement multiple interfaces |
| Subtype can extend other class | No | Yes | Yes |
| Zero-overhead when no data | Yes | No (class header) | No |
| Best for | Simple variants, ordinals | Rich state variants | Mixin-style hierarchies |

```kotlin
// enum: can't have Success with data AND Error with different data
enum class Status { LOADING, SUCCESS, ERROR }

// sealed class: each variant can have its own fields
sealed class UiState {
    object Loading : UiState()
    data class Content(val items: List<Item>) : UiState()
    data class Error(val message: String, val retryable: Boolean) : UiState()
}

// sealed interface: allows multi-inheritance in the hierarchy
sealed interface Clickable
sealed interface Draggable
class Button : Clickable, Draggable  // implements both
```

### Kotlin 1.5 Change: Sealed Subclass Location

**Before Kotlin 1.5:** All subclasses of a sealed class must be in the **same file**.

**Kotlin 1.5+:** Subclasses can be in **different files within the same package and module** (compilation unit). This enables better organization for large sealed hierarchies.

```kotlin
// Result.kt
sealed class Result<out T>

// SuccessResult.kt (same package)
data class Success<T>(val data: T) : Result<T>()  // OK in Kotlin 1.5+

// ErrorResult.kt (same package)
data class Error(val msg: String) : Result<Nothing>()  // OK in Kotlin 1.5+
```

---

## Q2.4 — The `object` Keyword

> **Builds on:** [Q0.3 — JVM class loading](00_jvm_mental_model.md#q03--class-loading-and-the-static--block)
> **Builds on:** [Q0.1 — reference capture](00_jvm_mental_model.md#q01--primitives-vs-references)

### How JVM Class Loading Guarantees Thread-Safe Singleton

The JVM specification guarantees that `<clinit>` (the static initializer block) is executed by **only one thread**, and all other threads that try to access the class block until initialization completes. This is the "Initialization-On-Demand Holder" pattern — for free.

```kotlin
object DatabaseManager {
    val connection = createConnection()
    init { println("Initializing DatabaseManager") }
}
```

```java
// What JVM sees — thread-safe by JVM spec:
public final class DatabaseManager {
    public static final DatabaseManager INSTANCE;

    static {  // <clinit> — JVM guarantees: single thread, others wait
        INSTANCE = new DatabaseManager();
        INSTANCE.connection = INSTANCE.createConnection();
    }
}
```

No `synchronized`, no `volatile`, no double-checked locking. The JVM does it all.

### Exact Bytecode for `object`

```kotlin
object Singleton {
    val value = 42
}
```

```java
// Decompiled:
public final class Singleton {
    private static final int value = 42;
    @NotNull public static final Singleton INSTANCE;  // ← THE INSTANCE field

    static {  // <clinit>
        Singleton var0 = new Singleton();  // private constructor call
        INSTANCE = var0;
        // value initialized in <init>
    }

    private Singleton() { value = 42; }  // <init>

    public final int getValue() { return value; }  // getter
}
```

### `object` vs `companion object` vs Anonymous `object`

| Feature | `object MySingleton` | `companion object` | Anonymous `object { }` |
|---------|---------------------|-------------------|------------------------|
| Named? | Yes | Optional (`companion object Companion`) | No |
| Lifetime | Application-wide | Bound to outer class | As long as reference held |
| JVM type | Full class | Nested static class | Inner/local anonymous class |
| Can implement interface | Yes | Yes | Yes |
| Thread-safe init | Yes (class loading) | Yes (class loading) | N/A (new object each time) |
| Static methods in Java | No (need `@JvmStatic`) | No (need `@JvmStatic`) | N/A |

### Anonymous Object Memory Leak

```kotlin
class MyActivity : Activity() {
    fun setupListener() {
        val button = Button(this)
        button.setOnClickListener(object : View.OnClickListener {
            override fun onClick(v: View) {
                // This anonymous object implicitly holds a reference to MyActivity!
                doSomething()  // closes over outer class
            }
        })
        // If button outlives the Activity, the anonymous object outlives it,
        // and the anonymous object holds MyActivity → LEAK!
    }
}
```

```
Memory leak chain:
Button (long-lived) → OnClickListener (anonymous object)
                           │
                           └──→ implicit this$0 → MyActivity (should be dead)
                                                    └──→ all its views, Context...
```

**Fix:** Use a static/top-level reference, weak reference, or ensure proper cleanup in `onDestroy`.

### `companion object` vs Java `static`

```kotlin
class UserRepository {
    companion object {
        const val TABLE_NAME = "users"

        fun create(): UserRepository = UserRepository()
    }
}
```

```java
// Decompiled:
public final class UserRepository {
    public static final String TABLE_NAME = "users";  // const val is truly static
    public static final UserRepository.Companion Companion = new UserRepository.Companion();

    public static final class Companion {
        // Non-const members live here — accessed via INSTANCE
        public final UserRepository create() { return new UserRepository(); }
    }
}
```

**Key difference:** `companion object` members live in a `Companion` class. From Java, you call `UserRepository.Companion.create()` unless annotated with `@JvmStatic`, which generates a real static delegating method. Note that [`const val`](01_type_system_foundations.md#q11--val-vs-const-val) is truly static — it is inlined directly into the class, bypassing the `Companion` wrapper entirely.

```kotlin
companion object {
    @JvmStatic fun create() = UserRepository()  // now callable as UserRepository.create() from Java
}
```

**`companion object` CAN implement interfaces** — this is impossible with Java `static`:
```kotlin
class Parser {
    companion object : Factory<Parser> {
        override fun create() = Parser()
    }
}
```

---

## Q2.5 — Value Classes

> **Builds on:** [Q0.2 — JVM Type Mapping](00_jvm_mental_model.md#q02--jvm-type-mapping) · [Q3.1 — Type Erasure](03_generics_and_variance.md#q31--type-erasure)
> **Connects to:** [Q3.1 (erased at runtime)](03_generics_and_variance.md#q31--type-erasure) · [Q0.2 (boxing scenarios)](00_jvm_mental_model.md#q02--jvm-type-mapping)

### What "Erased at Runtime" Means

```kotlin
@JvmInline
value class UserId(val id: String)

fun getUser(id: UserId): User { ... }
```

```java
// Decompiled — at runtime, UserId is completely gone:
public static final User getUser-HASHCODE(String id) {
    // The UserId wrapper doesn't exist at the JVM level!
}
```

The JVM sees `String` directly — no allocation of `UserId` wrapper object. This is the "erased" part: the value class is a compile-time wrapper for type safety, but it vanishes at runtime.

### The Four Scenarios Where Value Classes Box

| Scenario | Example | Why |
|----------|---------|-----|
| Nullable | `val x: UserId? = null` | Null needs object; primitives can't be null |
| Generic type | `val list: List<UserId>` | Generics [erase to Object](03_generics_and_variance.md#q31--type-erasure) — must be a reference |
| Interface implementation | `val x: Comparable<UserId> = userId` | Interface needs object reference |
| Return from inline function | `inline fun <reified T> create(): T` | T must be Object at runtime |

```kotlin
@JvmInline value class UserId(val id: String)

val a: UserId = UserId("123")   // ← NO boxing: erased to String
val b: UserId? = UserId("123")  // ← BOXING: needs null-capable reference
val list: List<UserId> = listOf(UserId("123"))  // ← BOXING: List<Object>
```

### Why the Compiler Mangles Method Names

```kotlin
@JvmInline value class UserId(val id: String)

fun greet(id: UserId) = println("Hello $id")
// Compiles to: greet-HASHCODE(String id) — name mangled with hash!
```

**The problem without mangling:**
```java
// If the compiler generated: greet(String id) — clashes with:
fun greet(name: String) = println("Hello $name")
// Both would decompile to: greet(String) → compile error in JVM!
```

The hash suffix prevents naming collisions between value class methods and regular String/Int methods that have the same erased signature.

### Value Class vs Typealias — Safety Difference

```kotlin
typealias UserId = String       // NO type safety — UserId IS String
typealias ProductId = String    // ProductId IS also String

fun process(userId: UserId, productId: ProductId) { }
process(productId, userId)  // compiles! arguments are just Strings — no error

// vs:
@JvmInline value class UserId(val id: String)
@JvmInline value class ProductId(val id: String)

fun process(userId: UserId, productId: ProductId) { }
process(productId, userId)  // COMPILE ERROR: type mismatch — safety!
```

> **Key Takeaway:** Value classes give you the type safety of a wrapper class with zero runtime overhead (when not boxed). Typealias is just an alias — no type safety. Choose value class when you want to prevent mixing incompatible IDs, tokens, or domain primitives.

---

*← [Phase 1 — Type System](01_type_system_foundations.md) | [Phase 2.5 — Initialization Mechanics →](02_5_initialization_mechanics.md)*
