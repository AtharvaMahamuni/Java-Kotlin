# Phase 2 — Classes, Objects, and Initialization

> Kotlin's class system is `final` by default, exhaustive by design, and thread-safe through the JVM. **Core initialization rule: JVM initializes top-to-bottom, superclass-before-subclass, delegation-before-body.** Every trap in this phase comes from one of these two principles.

## Navigation

[← Phase 1 — Type System Foundations](01_type_system_foundations.md) | [→ Phase 3 — Generics and Variance](03_generics_and_variance.md)

## Questions in This File

- [Q2.1 — Class Modifiers](#q21--class-modifiers)
- [Q2.2 — Constructor Mechanics: `init`, Primary, Secondary](#q22--constructor-mechanics-init-primary-secondary)
- [Q2.3 — Inheritance Initialization Order](#q23--inheritance-initialization-order)
- [Q2.4 — Data Classes](#q24--data-classes)
- [Q2.5 — Sealed Classes and Interfaces](#q25--sealed-classes-and-interfaces)
- [Q2.6 — The `object` Keyword and Companion Initialization](#q26--the-object-keyword-and-companion-initialization)
- [Q2.7 — Property Initializer Order Traps](#q27--property-initializer-order-traps)
- [Q2.8 — Constructor Visibility and Factory Patterns](#q28--constructor-visibility-and-factory-patterns)
- [Q2.9 — Value Classes (Deep Dive)](#q29--value-classes-deep-dive)

---

# Q2.1 — Class Modifiers

> **Builds on:** [Q0.4 (virtual dispatch cost, vtable)](phase0_jvm_mental_model_v3.md#q04--the-jvm-call-stack)
> **Connects to:** [Q2.3 (open function in init is dangerous)](#q23--inheritance-initialization-order) · [Q3.2 (final enables devirtualization)](03_generics_and_variance.md#q32--variance)

---

## The Three Modifiers

```
final (default):    class Calculator { }
                         │
                         └── Nobody can extend this. Period.
                             JIT sees ONE implementation → can devirtualize.

open:               open class Calculator { open fun add() { } }
                         │
                         ├── Subclass A can override add()
                         └── Subclass B can override add()
                             JIT must keep vtable lookup.

abstract:           abstract class Animal { abstract fun sound(): String }
                         │
                         └── Can't instantiate Animal directly.
                             Subclass MUST implement sound().
```

---

## Why `final` by Default?

Java's open-by-default caused a systemic problem: the **fragile base class problem**.

```java
// Java base class
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
    // addAll internally calls add() 5 times, and add() is overridden
}
```

When the base class changes how it calls its own internal methods, subclasses that override those methods break — even if their logic is correct in isolation. You must document every self-call for safe subclassing (Effective Java §19).

Kotlin's solution: **`final` by default**. You must explicitly opt in with `open`. This forces API designers to think carefully about what they're allowing.

---

## `open` vs `final` — Vtable Difference

A **vtable** (virtual method table) is a data structure the JVM maintains per class — it maps method names to their implementations. On a virtual call, the JVM looks up the vtable at runtime to find the right method. For `final` classes, the JVM knows there's only one possible implementation and can skip this lookup entirely.

```kotlin
// final class (default):
class Calculator {
    fun add(a: Int, b: Int) = a + b
}
// INVOKEVIRTUAL → JIT sees Calculator is final → only ONE implementation
// JIT devirtualizes → replaces vtable lookup with a direct jump → zero overhead
```

```kotlin
// open class:
open class Calculator {
    open fun add(a: Int, b: Int) = a + b
}
// INVOKEVIRTUAL → unknown subclass might override add()
// vtable lookup on every call → slower
```

```
final class vtable:          open class vtable:
┌─────────────────┐          ┌──────────────────────────────┐
│ [JVM internals] │          │ [JVM internals]              │
└─────────────────┘          │ Calculator.add → Calculator  │
  (JIT removes lookup)       │ (subclass can replace this)  │
                             └──────────────────────────────┘
```

See [Q0.4](phase0_jvm_mental_model_v3.md#q04--the-jvm-call-stack) for full dispatch cost breakdown.

---

## `abstract` vs `open` — Architectural Choice

| Modifier | Can Instantiate? | Must Override? | Use When |
|---|---|---|---|
| `final` (default) | Yes | N/A | No subclassing intended |
| `open` | Yes | No | Subclassing allowed, base has default behavior |
| `abstract` | **No** | **Yes** (for abstract members) | Subclassing required; base defines contract |

```kotlin
// abstract: Animal is conceptually incomplete — can't exist without a concrete form
abstract class Animal {
    abstract fun sound(): String      // must override
    fun breathe() = println("...")    // shared behavior
}

// open: Button has sensible defaults but can be customized
open class Button {
    open fun onClick() { /* default: nothing */ }
}
```

Choose `abstract` when the base class has no meaningful standalone behavior.
Choose `open` when the base class works fine on its own but permits extension.

---

## Memory Trick

```
final   → WALL. Nobody gets through. Default in Kotlin.
open    → DOOR. You chose to open it. JIT pays vtable cost.
abstract → TEMPLATE. Door is open AND required. Can't instantiate.

Performance direction:
  final     → JIT devirtualizes → fastest
  open      → vtable lookup → slower
  interface → INVOKEINTERFACE → slowest

"Kotlin is final by default" = performance AND safety by default.
```

---

## Self-Test

1. Why are Kotlin classes `final` by default? What Java problem does this solve?
2. What JVM instruction handles a call to an `open` method? What does the JIT do with a `final` one?
3. Can you instantiate an `abstract` class directly?
4. A library ships `open class Base` with `fun methodA()` calling `methodB()` internally. A subclass overrides `methodB()`. What breaks if the library changes `methodA()`?
5. What is a vtable and why does `final` let the JIT eliminate it?

---

# Q2.2 — Constructor Mechanics: `init`, Primary, Secondary

> **Builds on:** [Q0.3 (class loading, `<clinit>`)](phase0_jvm_mental_model_v3.md#q03--class-loading-and-init--in-object)
> **Connects to:** [Q2.3 (inheritance uses this order)](#q23--inheritance-initialization-order) · [Q2.7 (property order traps)](#q27--property-initializer-order-traps) · [Q2.8 (constructor visibility)](#q28--constructor-visibility-and-factory-patterns)

---

## Two JVM Methods You Need to Know

Before anything else — the JVM has two initializer methods:

```
<clinit> = class initializer (static initializer)
           Runs ONCE when the class is first loaded.
           Where: companion object init {}, top-level object init {}
           Guaranteed thread-safe by the JVM spec.

<init>   = instance initializer (constructor)
           Runs every time you create a new object: new User("Alice")
           Where: primary constructor + property initializers + init blocks — ALL merged here
           Called per instance, not per class.
```

Everything in this section is about `<init>`.

---

## Primary Constructor + `init` Block = One Method

Three things in a class body — constructor params, property initializers, `init` blocks — all merge into ONE `<init>` method, in **declaration order**:

```kotlin
class User(val name: String) {
    val greeting = "Hello, $name"  // property initializer
    init { println("1: $name") }   // init block
    val bio = "$name!"             // property initializer
    init { println("2: $bio") }    // init block
}
```

Execution order is exactly the order you wrote them:

```
User("Alice"):
  → name = "Alice"            (constructor param, always first)
  → greeting = "Hello, Alice" (property initializer)
  → println("1: Alice")       (init block)
  → bio = "Alice!"            (property initializer)
  → println("2: Alice!")      (init block)
```

Not "all properties first, then all `init` blocks." One unified top-to-bottom sequence.

---

## Decompiled `<init>` Method

```kotlin
class User(val name: String, val age: Int) {
    val greeting = "Hello, $name"
    init { println("init 1: name=$name") }
    val bio = "$name is $age"
    init { println("init 2: bio=$bio") }
}
```

```java
// Generated <init> — everything interleaved in declaration order:
public User(String name, int age) {
    this.name = name;                              // 1. constructor param
    this.age = age;                                // 1. constructor param
    this.greeting = "Hello, " + name;             // 2. property initializer
    System.out.println("init 1: name=" + name);   // 3. init block
    this.bio = name + " is " + age;               // 4. property initializer
    System.out.println("init 2: bio=" + bio);     // 5. init block
}
```

"Primary constructor vs `init` block" is a false distinction at the bytecode level — they're both just parts of `<init>`, executed in order.

---

## Why Interleaved Order Matters

If all properties ran first, then all `init` blocks, this bug would be hidden:

```kotlin
class Example {
    val computed = processName()  // runs first — name is still null!
    val name = "Alice"            // runs second

    private fun processName() = name.uppercase()  // crashes: null.uppercase()
}
```

With strict declaration-order execution, `processName()` is called when `name` is still `null` — making the bug visible immediately. Order-of-declaration enforces discipline.

---

## Secondary Constructors — Delegation Chain

A secondary constructor **must** delegate to the primary via `this(...)`. This is a JVM requirement: every `<init>` must call another `<init>` as its first action (via `INVOKESPECIAL` — a direct, non-virtual call to a specific constructor).

```kotlin
class User(val name: String, val age: Int) {
    constructor(name: String) : this(name, 0) {  // delegates to primary
        println("Secondary body")
    }
}
```

Execution order:

```
new User("Alice")
  ├── 1. this("Alice", 0) → primary <init> called first
  │       ├── name = "Alice", age = 0
  │       ├── [all property initializers]
  │       └── [all init blocks]         ← init blocks are part of primary
  └── 2. Secondary body: println("Secondary body")  ← runs AFTER everything above
```

**The trap:** `init` blocks run as part of the primary constructor, **before** the secondary constructor body. Many developers assume `init` runs after the secondary body.

---

## Secondary Constructor vs Default Parameters

```kotlin
// Prefer this: default parameter (Kotlin idiomatic)
class User(val name: String, val age: Int = 0)

// Over this: secondary constructor (more verbose, same result)
class User(val name: String, val age: Int) {
    constructor(name: String) : this(name, 0)
}
```

**When to use secondary constructors:**
- Java interop requiring distinct constructor signatures (`@JvmOverloads` handles most cases, but secondary constructors give finer control)
- Different initialization logic per constructor path
- The constructor parameters genuinely differ in kind, not just in defaults

---

## Memory Trick

```
<clinit> = class level  (once, thread-safe, static initializer)
<init>   = instance level (every new object, constructor)

INIT ORDER = TOP-TO-BOTTOM, no exceptions.
  Constructor params → then everything interleaved as written.
  "Primary vs init block" = same method, same sequence.

SECONDARY CONSTRUCTOR rule:
  Must call this() first (primary is "the real init").
  Secondary body runs AFTER all of primary (including all init blocks).
  Prefer default parameters over secondary constructors.
```

---

## Self-Test

1. What is the difference between `<clinit>` and `<init>` in the JVM?
2. `class Foo { val x = 1; init { println(x) }; val y = 2; init { println(y) } }` — what prints?
3. Why must a secondary constructor call `this(...)` before its own body?
4. `init` blocks — do they run before or after the secondary constructor body?
5. When would you choose a secondary constructor over a default parameter?

---

# Q2.3 — Inheritance Initialization Order

> **Builds on:** [Q2.2 (init block order)](#q22--constructor-mechanics-init-primary-secondary) · [Q2.1 (open/final modifiers)](#q21--class-modifiers)
> **Connects to:** [Q0.4 (INVOKEVIRTUAL dispatch)](phase0_jvm_mental_model_v3.md#q04--the-jvm-call-stack)

> **This section contains the most dangerous trap in Kotlin.**

---

## The Rule

```
Superclass <init> runs FIRST, then subclass <init>.
Always. No exceptions.
```

```
new Child()
├── 1. super() — Base <init> runs entirely:
│       ├── Base property initializers
│       ├── Base init blocks (interleaved with above)
│       └── Base primary constructor body
├── 2. Child property initializers
├── 3. Child init blocks (interleaved with above)
└── 4. Child primary constructor body completes
   └── Object fully constructed
```

---

## The Fatal Trap: `open` Method Called in `init`

When a superclass `init` block calls an `open` method, the JVM uses `INVOKEVIRTUAL` — virtual dispatch. This means it calls the **overridden version** in the subclass. But the subclass hasn't run its `<init>` yet. Its fields are still `null`/`0`.

```kotlin
open class Base {
    open val message: String = "from Base"

    init {
        println(message)  // ← calls Child.getMessage() via INVOKEVIRTUAL
    }
}

class Child : Base() {
    override val message: String = "from Child"
    // This assignment is in Child's <init> — which runs AFTER Base's <init>!
}

Child()  // prints: null  ← NOT "from Child"
```

Step-by-step execution:

```
new Child()
├── Child.<init> starts
│   ├── Calls Base.<init> first (super())
│   │   ├── Base.message field = "from Base"
│   │   │   BUT: Child OVERRIDES message!
│   │   │   JVM: INVOKEVIRTUAL → calls Child.getMessage()
│   │   │   Child.message field = null  (Child.<init> hasn't run yet!)
│   │   ├── init block: println(message) → Child.getMessage() → null  ← BUG
│   │   └── Base.<init> done
│   ├── Child.message = "from Child"  ← TOO LATE — Base already used it
│   └── Child.<init> done
```

The same bug with a method:

```kotlin
open class Animal {
    init { sound() }              // calls overridden version — dangerous
    open fun sound() { println("...") }
}

class Dog : Animal() {
    private val bark = "Woof"
    override fun sound() { println(bark) }  // bark is null here!
}

Dog()  // prints: null (not "Woof")
```

---

## How `final` Removes the Danger

If the method is `final` or `private`, the compiler uses `INVOKESPECIAL` (direct call to a specific method, no vtable lookup, no override possible). The call in `init` always resolves to the base class method — which IS fully initialized at that point.

```kotlin
class Animal {         // final by default
    private val sound = "..."
    init { printSound() }
    private fun printSound() = println(sound)  // private → INVOKESPECIAL → always safe
}
```

`INVOKESPECIAL` vs `INVOKEVIRTUAL`:

```
INVOKESPECIAL = "call this exact method, no overrides" (private, super, constructor)
INVOKEVIRTUAL = "check vtable at runtime, call whatever's overridden"

final/private method in init → INVOKESPECIAL → safe
open method in init           → INVOKEVIRTUAL → subclass version called → null/0
```

---

## The "Leaked `this`" Problem

A related trap — passing `this` out of a constructor before construction is complete:

```kotlin
class EventManager {
    init {
        EventBus.register(this)  // `this` is NOT fully constructed yet!
        // If another thread fires an event now, handle() may see uninitialized fields
    }
    fun handle(event: Event) { ... }
}
```

Between `EventBus.register(this)` and the end of `<init>`, the object is partially initialized. Another thread receiving an event and calling `handle()` may access fields that haven't been assigned yet.

---

## Memory Trick

```
INHERITANCE INIT ORDER = SUPER BEFORE SUB, always.

THE FATAL COMBINATION:
  open class Base  +  open fun called in init  +  Child overrides that fun
  = Base's init calls Child's version via INVOKEVIRTUAL
  = Child's fields are null/0 (Child.<init> hasn't run yet)
  = silent null or 0 in output

MENTAL CHECK before writing any open class:
  "Does my init block call any open method?"
  If YES → risk of seeing null/0 from uninitialized subclass fields.

SAFE ALTERNATIVES:
  1. Make the method private/final → INVOKESPECIAL → no override possible
  2. Don't call overridable methods in init
  3. Move post-construction logic to a factory function

LEAKED THIS:
  Passing `this` from init → object not yet fully constructed
  → other threads may see partially initialized state
```

---

## Self-Test

1. What is the full initialization order for `class Child : Base()`?
2. Why does calling an `open` method in a superclass `init` block produce `null`?
3. What's the difference between `INVOKEVIRTUAL` and `INVOKESPECIAL`, and which one makes the open-in-init bug happen?
4. How does making a method `private` or `final` fix the open-in-init bug?
5. What is the "leaked `this`" problem and why is it dangerous with multiple threads?

---

# Q2.4 — Data Classes

> **Builds on:** [Q0.1 (primitives, hashing)](phase0_jvm_mental_model_v3.md#q01--primitives-vs-references-the-two-worlds)
> **Connects to:** [Q3.2 (@UnsafeVariance in covariant types)](03_generics_and_variance.md#q32--variance) · [Q7.1 (List covariance)](07_collections_and_sequences.md#q71--kotlins-collection-hierarchy)

---

## The Core Rule

`data class` auto-generates: `equals` / `hashCode` / `copy` / `componentN` / `toString`.

**Only from primary constructor properties. Body properties are invisible to all of these.**

---

## The Concrete Picture

```kotlin
data class User(
    val id: Int,       // ← PRIMARY CONSTRUCTOR → included in equals/hashCode/copy
    val name: String   // ← PRIMARY CONSTRUCTOR → included in equals/hashCode/copy
) {
    var lastLogin: Long = 0  // ← BODY PROPERTY → EXCLUDED from equals/hashCode/copy
}
```

```kotlin
val u1 = User(1, "Alice").also { it.lastLogin = 100 }
val u2 = User(1, "Alice").also { it.lastLogin = 999 }

u1 == u2     // true  — lastLogin not compared
u1.copy()    // copies id and name only; lastLogin resets to 0
```

---

## Generated `equals` in Bytecode

```java
public boolean equals(Object other) {
    if (this == other) return true;
    if (!(other instanceof User)) return false;
    User o = (User) other;
    return id == o.id && name.equals(o.name);
    // lastLogin is NOT compared
}
```

---

## The Mutable `var` + HashSet Corruption

```kotlin
data class User(val id: Int, var name: String)  // mutable name!

val set = HashSet<User>()
val user = User(1, "Alice")
set.add(user)
// hashCode = hash(1, "Alice") → stored in bucket #42

user.name = "Bob"  // MUTATION: hashCode changes!
// hashCode = hash(1, "Bob") → would go in bucket #17

println(set.contains(user))  // false — looks in bucket #17, not found
println(set.size)             // 1 — it IS there, lost in bucket #42
```

```
HashSet after mutation:
  Bucket #42: [User(1, "Bob")]  ← object lives here
  Bucket #17: []                ← hashCode() now points here

contains() → looks in #17 → empty → returns false
```

A **HashSet** stores objects in "buckets" based on their `hashCode()`. When you call `contains()`, it computes the hashCode and looks only in that bucket. If the object mutated after insertion, its hashCode changed, so `contains()` looks in the wrong bucket.

**Rule: never use `var` properties in data classes stored in `HashSet` or `HashMap`.**

---

## `copy()` Is Shallow — The MutableList Trap

```kotlin
data class Config(val settings: MutableList<String>)

val original = Config(mutableListOf("dark_mode", "notifications"))
val copy = original.copy()

copy.settings.add("analytics")   // modifies the shared list!
println(original.settings)       // [dark_mode, notifications, analytics] ← original changed!
```

```
After copy():
  original.settings ──┐
                       ▼
  copy.settings    ──→ [MutableList on heap]   ← SAME object, two references
```

`copy()` copies the reference, not the contents. Both `original` and `copy` point to the same `MutableList`.

**Fix — deep copy:**

```kotlin
val deepCopy = original.copy(settings = original.settings.toMutableList())
```

---

## `@UnsafeVariance` in `List.contains()`

[`List<out E>`](07_collections_and_sequences.md#q71--kotlins-collection-hierarchy) is covariant — `E` only appears in "out" (producer) positions. But `contains(element: E)` takes `E` as input (in position), which violates covariance rules.

The stdlib uses `@UnsafeVariance` to override this restriction:

```kotlin
interface List<out E> {
    fun contains(element: @UnsafeVariance E): Boolean
    // Without @UnsafeVariance: COMPILE ERROR — E in contravariant position
}
```

It's safe here because `contains` only **reads** `element` to compare it — it never stores `element` into the list. The type system's concern (you might put a `Cat` into a `List<Dog>`) doesn't apply to a read-only comparison. Full explanation at [Q3.2](03_generics_and_variance.md#q32--variance).

---

## Memory Trick

```
DATA CLASS = auto-generates equals / hashCode / copy / componentN / toString
             ONLY from PRIMARY CONSTRUCTOR properties.
             Body properties are invisible to all generated functions.

TWO CLASSIC TRAPS:
  1. var + HashSet = CORRUPTION
     Mutation changes hashCode → object found in wrong bucket → contains() = false
     Rule: data class + hash collection = val only.

  2. copy() is SHALLOW
     copy.settings and original.settings point to the SAME object
     Mutation through one affects the other.
     Fix: copy(settings = original.settings.toMutableList())
```

---

## Self-Test

1. `data class User(val id: Int) { var lastLogin: Long = 0 }` — does `lastLogin` affect `equals`?
2. What happens when you mutate a `var` property of a data class stored in a `HashSet`?
3. Why is `copy()` shallow? How do you deep-copy a `MutableList` field?
4. What does the generated `equals` for `data class Point(val x: Int, val y: Int)` look like?
5. Why does `List<out E>` need `@UnsafeVariance` on `contains(element: E)`?

---

# Q2.5 — Sealed Classes and Interfaces

> **Builds on:** [Q1.3 (Nothing, Unit)](01_type_system_foundations.md#q13--type-hierarchy-any-nothing-unit) · [Q2.1 (class modifiers)](#q21--class-modifiers)
> **Connects to:** [Q1.6 (smart casts in when)](01_type_system_foundations.md#q16--smart-casts)

---

## The Core Idea

```
Enum:
  Status.LOADING, Status.SUCCESS, Status.ERROR
  All variants carry the same fields (or none). Fixed structure.

Sealed class:
  Loading          → no data
  Success<T>       → carries T
  Error            → carries message: String + retryable: Boolean
  Each variant has its OWN shape.

Sealed = "compiler knows ALL subtypes at compile time."
when on sealed = "compiler checks ALL cases are handled."
```

---

## The Concrete Picture — Compile-Time Safety Net

```kotlin
sealed class Result {
    // You add: data class Cancelled : Result()
}

fun handle(r: Result): String = when (r) {
    is Success -> "..."
    is Error   -> "..."
    is Loading -> "..."
    // COMPILE ERROR: 'when' expression must be exhaustive.
    // Add an else branch or handle Cancelled.
}
```

The compiler is the safety net. Every `when` on a sealed class used as an **expression** must handle all known subtypes.

---

## What `sealed class` Compiles To

```kotlin
sealed class Result<out T> {
    data class Success<T>(val data: T) : Result<T>()
    data class Error(val message: String) : Result<Nothing>()
    object Loading : Result<Nothing>()
}
```

Decompiles to:

```java
public abstract class Result {
    private Result() {}  // package-private constructor → prevents external subclassing

    public static final class Success extends Result { ... }
    public static final class Error extends Result { ... }
    public static final class Loading extends Result { ... }
}
```

The **private constructor** prevents anyone outside the sealed hierarchy from subclassing `Result`. The compiler uses the known fixed set of subclasses to enforce exhaustiveness.

Note: `Error` uses `Result<Nothing>` — `Nothing` is the bottom type, so `Result<Nothing>` IS-A `Result<T>` for any T. See [Q1.3](01_type_system_foundations.md#q13--type-hierarchy-any-nothing-unit).

---

## How `when` Achieves Exhaustiveness

```kotlin
fun handleResult(result: Result<User>): String = when (result) {
    is Result.Success -> "Data: ${result.data}"
    is Result.Error   -> "Error: ${result.message}"
    is Result.Loading -> "Loading..."
    // Remove any branch → COMPILE ERROR
}
```

```
Compiler at compile time:
  Result subclasses = {Success, Error, Loading}
  when branches     = {Success, Error, Loading}
  All covered? YES → no else required

Add Cancelled → subclasses = {Success, Error, Loading, Cancelled}
  when branches = {Success, Error, Loading}
  Missing: Cancelled → COMPILE ERROR in every when expression
```

**Statement vs expression:**

```kotlin
// EXPRESSION (assigned to val) → must be exhaustive — compile error if not
val msg: String = when (result) { ... }

// STATEMENT (standalone) → else optional — dangerous, missing branches silently ignored
when (result) { ... }
```

---

## Sealed Class vs Sealed Interface vs Enum

| Feature | `enum class` | `sealed class` | `sealed interface` |
|---|---|---|---|
| Different data per variant | No (shared fields) | Yes | Yes |
| Multiple instances per variant | No | Yes | Yes |
| Can extend another class | No | One superclass | Can implement multiple interfaces |
| Zero-overhead (no data) | Yes | No (class header) | No |
| Best for | Simple variants, ordinals | Rich state variants | Mixin hierarchies |

```kotlin
// sealed interface: multi-inheritance in the hierarchy
sealed interface Clickable
sealed interface Draggable
class Button : Clickable, Draggable  // implements both — impossible with sealed class
```

---

## Kotlin 1.5: Subclass Location Change

**Before 1.5:** All subclasses must be in the **same file**.

**1.5+:** Subclasses can be in **different files within the same package and module**.

```kotlin
// Result.kt
sealed class Result<out T>

// SuccessResult.kt (same package, same module)
data class Success<T>(val data: T) : Result<T>()

// ErrorResult.kt (same package, same module)
data class Error(val msg: String) : Result<Nothing>()
```

---

## Memory Trick

```
SEALED = "closed world assumption" for the compiler.
  Compiler knows ALL subtypes → enforces exhaustive when.

sealed class  vs  enum:
  enum:   fixed variants, same fields  → cheap, rigid
  sealed: fixed variants, own fields   → flexible, full classes

sealed class  vs  sealed interface:
  sealed class     → single inheritance (Kotlin rule)
  sealed interface → multi-inheritance (Button : Clickable, Draggable)

EXHAUSTIVENESS:
  when as EXPRESSION → must be exhaustive (compile error if not)
  when as STATEMENT  → else optional (dangerous — missing branches silently ignored)
```

---

## Self-Test

1. What makes `when` exhaustive on a sealed class? What happens when you add a new subclass?
2. `sealed class` compiles to `abstract class` with what constructor visibility? Why?
3. Why does `data class Error(...) : Result<Nothing>()` typecheck for any `Result<T>`?
4. `when` as a statement vs expression — does exhaustiveness apply to both?
5. When would you choose `sealed interface` over `sealed class`?

---

# Q2.6 — The `object` Keyword and Companion Initialization

> **Builds on:** [Q0.3 (JVM class loading, `<clinit>`)](phase0_jvm_mental_model_v3.md#q03--class-loading-and-init--in-object)
> **Connects to:** [Q2.2 (init block timing)](#q22--constructor-mechanics-init-primary-secondary) · [Q1.1 (const val inlining)](01_type_system_foundations.md#q11--val-vs-const-val)

---

## Three Uses of `object`

```kotlin
object AppConfig { }                          // 1. Top-level singleton
class Foo { companion object { } }            // 2. "static" members attached to class
val handler = object : ClickListener {        // 3. Anonymous one-time implementation
    override fun onClick() { }
}
```

Same keyword. Three different purposes.

---

## How the Singleton Works

```
First access to DatabaseManager.URL:
  JVM: Is DatabaseManager loaded? NO
  → Load class → run <clinit> → INSTANCE = new DatabaseManager()
  → Store INSTANCE in static field
  ← All other threads WAITED. JVM held the class init lock.

Second access:
  JVM: Is DatabaseManager loaded? YES
  → Return INSTANCE immediately (no lock needed)
```

Thread safety is free. No `synchronized`. No `volatile`. No double-checked locking. The JVM spec (§5.5) guarantees `<clinit>` runs exactly once, on one thread, with all other threads blocked until it completes.

---

## Bytecode for `object`

```kotlin
object Singleton {
    val value = 42
}
```

Decompiles to:

```java
public final class Singleton {
    public static final Singleton INSTANCE;

    static {  // <clinit> — JVM: single thread, others wait
        Singleton var0 = new Singleton();
        INSTANCE = var0;
    }

    private Singleton() { }  // private — prevents: new Singleton()

    public final int getValue() { return 42; }
}
```

JVM class loading IS the singleton pattern. See [Q0.3](phase0_jvm_mental_model_v3.md#q03--class-loading-and-init--in-object).

---

## `object` vs `companion object` vs Anonymous `object`

| | `object MySingleton` | `companion object` | `object : Interface { }` |
|---|---|---|---|
| Named? | Yes | Optional | No |
| Lifetime | Application-wide | Bound to outer class | As long as reference held |
| JVM type | Full class | Nested static class | Anonymous inner class |
| Can implement interface | Yes | Yes | Yes |
| Thread-safe init | Yes (`<clinit>`) | Yes (`<clinit>`) | N/A (new each time) |

---

## `companion object` vs Java `static`

```kotlin
class UserRepository {
    companion object {
        const val TABLE_NAME = "users"
        fun create(): UserRepository = UserRepository()
    }
}
```

Decompiles to:

```java
public final class UserRepository {
    public static final String TABLE_NAME = "users";  // const val bypasses Companion
    public static final UserRepository.Companion Companion = new Companion();

    public static final class Companion {
        public final UserRepository create() { return new UserRepository(); }
    }
}
```

From Java: `UserRepository.Companion.create()` — unless you add `@JvmStatic`:

```kotlin
companion object {
    @JvmStatic fun create() = UserRepository()  // Java: UserRepository.create()
}
```

`const val` bypasses the `Companion` wrapper entirely — inlined as a literal at every call site. See [Q1.1](01_type_system_foundations.md#q11--val-vs-const-val).

**`companion object` CAN implement interfaces** — impossible with Java `static`:

```kotlin
class Parser {
    companion object : Factory<Parser> {
        override fun create() = Parser()
    }
}
```

---

## When Does a `companion object` Initialize?

A `companion object` is initialized **lazily** — on the first access to any of its non-const members.

```kotlin
class Config {
    companion object {
        val URL = "https://api.example.com"  // triggers companion init on first access
        const val TAG = "Config"             // does NOT trigger companion init
    }
}

val url = Config.URL     // triggers <clinit> of companion → URL is computed
Log.d(Config.TAG, "x")  // bytecode: LDC "Config" — Config class never loaded
```

`const val` is inlined at the call site at compile time — the JVM never needs to load `Config` or its companion for that line.

---

## Circular Initialization Deadlock

Two `object`s that reference each other during initialization can deadlock:

```kotlin
object A {
    val ref = B.value  // triggers B to initialize during A's <clinit>
    val name = "A"
}

object B {
    val ref = A.name   // triggers A to initialize during B's <clinit>
    val value = 42
}

// Thread 1: accesses A → A's <clinit> starts → needs B → waits for B's class lock
// Thread 2: accesses B → B's <clinit> starts → needs A → waits for A's class lock
// DEADLOCK — both threads hold their class lock, waiting for the other forever
```

Fix: avoid cross-singleton dependencies during initialization. Initialize lazily or restructure the dependency.

---

## Anonymous Object Memory Leak

```kotlin
class MyActivity : Activity() {
    fun setupListener() {
        button.setOnClickListener(object : View.OnClickListener {
            override fun onClick(v: View) {
                doSomething()  // anonymous object implicitly captures MyActivity
            }
        })
        // If button outlives Activity, anonymous object outlives Activity,
        // anonymous object holds MyActivity → LEAK
    }
}
```

```
Memory leak chain:
  Button (long-lived)
    → OnClickListener (anonymous object)
        → implicit this$0 reference
            → MyActivity (should be dead)
                → all views, Context, bitmaps...
```

**Fix:** Use a top-level or static reference, weak reference, or clean up in `onDestroy`.

---

## Memory Trick

```
object = class + static INSTANCE field + <clinit> = free thread-safe singleton.

THREE uses:
  object Foo { }               → singleton (lives forever)
  companion object { }         → "static" members attached to class
  object : Interface { }       → anonymous one-time implementation

COMPANION INIT is LAZY:
  const val → inlined at call site → companion NEVER loaded for that access
  val       → runtime access → companion <clinit> runs on first touch

@JvmStatic:
  Without → Java: Foo.Companion.create()
  With    → Java: Foo.create()

CIRCULAR DEADLOCK:
  object A uses B during init + object B uses A during init = deadlock

ANONYMOUS OBJECT LEAK:
  captures outer class → if stored in long-lived object → outer can't be GC'd
  Fix: top-level reference or weak reference
```

---

## Self-Test

1. How does JVM class loading give `object` thread safety for free?
2. What does `object Singleton` decompile to in Java?
3. `companion object` member from Java — call syntax without `@JvmStatic`? With?
4. `const val` inside `companion object` — does it go through the `Companion` class at the call site?
5. Describe the circular initialization deadlock and how to fix it.
6. Describe the anonymous object memory leak pattern and one fix.

---

# Q2.7 — Property Initializer Order Traps

> **Builds on:** [Q2.2 (interleaved init order)](#q22--constructor-mechanics-init-primary-secondary)
> **Connects to:** [Q5.2 (lazy defers initialization)](05_properties_and_delegation.md#q52--lazy-internals) · [Q5.1 (lateinit internals)](05_properties_and_delegation.md#q51--lateinit-internals)

---

## The Core Trap

Declaration order = execution order. Reference a property declared **below** you = it's still `null`.

```kotlin
class Example {
    val length = name.length   // runs first — name is null here! → NPE
    val name = "Alice"         // runs second
}
```

This **compiles** — the compiler does not check cross-property reference order. At runtime:

```java
// Generated <init>:
this.length = this.name.length();  // name is null → NPE
this.name = "Alice";               // assigned AFTER — too late
```

The compiler won't catch it. It crashes at runtime.

---

## `lazy` as the Safe Alternative

```kotlin
class Example {
    val length by lazy { name.length }  // deferred until first access
    val name = "Alice"
}
```

The `lazy` block doesn't execute until the first time `length` is accessed. By that point, the entire constructor has finished — `name` is fully initialized.

```
Screen()
├── name = "Alice"       (constructor runs, length not touched)
└── [constructor done]

screen.length            ← FIRST ACCESS
└── lazy block: "Alice".length → 5 (cached, subsequent accesses return 5)
```

---

## `const val` vs `val` — Initialization Timing

```kotlin
object Config {
    const val VERSION = "1.0"    // compile-time: inlined at call sites, never "assigned"
    val BUILD_DATE = getDate()   // runtime: assigned in <clinit> when class loads
}
```

`const val` is never assigned at runtime — its value is baked directly into bytecodes that reference it. Regular `val` in an `object` is assigned in `<clinit>` on first class access.

---

## `lazy` vs Eager `val` — Timing

```kotlin
class Screen {
    val eagerData = loadData()          // called immediately when Screen is constructed
    val lazyData by lazy { loadData() } // called on first access to lazyData
}
```

```
new Screen()
├── eagerData: loadData() called NOW
└── lazyData: NOT called (lazy block not triggered)

screen.lazyData  ← first access
└── lazy block: loadData() called, result cached
    subsequent accesses: return cached value, no re-computation
```

---

## Memory Trick

```
PROPERTY ORDER TRAP:
  Declaration order = execution order.
  Reference a property BELOW your current line = it's still null.
  Compiler won't catch this. Crashes at runtime.

SAFE PATTERN when order is ambiguous: use lazy { }
  Lazy block defers until first access.
  By then, the entire constructor has finished.
  Safe to reference any other property of the same object.

eager val  → initialized at construction time (order matters!)
lazy val   → initialized at first access (order doesn't matter)

const val  → never initialized at runtime (inlined by compiler)
```

---

## Self-Test

1. `class Foo { val a = b.length; val b = "hi" }` — does this compile? What happens at runtime?
2. Why does `by lazy { }` fix the forward-reference trap?
3. What's the difference between `const val` and `val` in terms of when the value is assigned?
4. `val eagerData = loadData()` vs `val lazyData by lazy { loadData() }` — when does each call `loadData()`?

---

# Q2.8 — Constructor Visibility and Factory Patterns

> **Builds on:** [Q2.2 (secondary constructors)](#q22--constructor-mechanics-init-primary-secondary) · [Q2.6 (object singleton)](#q26--the-object-keyword-and-companion-initialization)
> **Connects to:** [Q13.5 (dependency injection)](13_android_architecture.md#q135--dependency-injection)

---

## The Concrete Picture

Private constructor = you control every entry point into the object:

```kotlin
class Database private constructor(val url: String)

// From outside: Database("url") → COMPILE ERROR
// Only way in: through a factory method you provide
val db = Database.getInstance("jdbc:sqlite:app.db")
```

```
Public constructor:   anyone creates instances → no control
Private constructor:  only factory methods create instances → full control:
  - Return cached instance (singleton)
  - Validate params before construction
  - Return subclass based on params
  - Named constructors: Database.inMemory() vs Database.persistent()
```

---

## Private Constructor + Factory Pattern

```kotlin
class Database private constructor(val url: String) {
    companion object {
        @Volatile private var instance: Database? = null

        fun getInstance(url: String): Database {
            return instance ?: synchronized(this) {
                instance ?: Database(url).also { instance = it }
            }
        }
    }
}
```

Three terms in this pattern that need explanation:

**`@Volatile`** — marks a field so that every read and write goes directly to main memory rather than a thread's local CPU cache. Without it, Thread A might write a new `instance` value that Thread B never sees because Thread B is reading from its cached copy. `@Volatile` guarantees visibility across threads.

**`synchronized(this)`** — acquires a lock on the object so only one thread can execute the block at a time. Prevents two threads from both passing the `instance ?: ...` check simultaneously and creating two instances.

**Double-checked locking** — the pattern `instance ?: synchronized { instance ?: create() }`:
- Outer `?:` — fast path: if `instance` is non-null (common case after first creation), skip the lock entirely. No synchronization overhead.
- Inner `?:` — slow path: inside the lock, check again. Two threads might both pass the outer check before either creates the instance. The inner check ensures only one of them actually creates it.

```
Thread 1: instance == null → enters synchronized
Thread 2: instance == null → waits at synchronized

Thread 1: creates Database, assigns instance, exits lock
Thread 2: enters lock → instance != null → returns existing
```

---

## `@JvmOverloads` — Generating Java-Compatible Constructors

Kotlin's default parameters don't generate separate constructor signatures for Java. `@JvmOverloads` fixes that:

```kotlin
class Button @JvmOverloads constructor(
    val text: String,
    val color: Int = 0xFF0000,
    val size: Float = 14f
)
```

With `@JvmOverloads`, the compiler generates **N+1 constructors** for N default parameters:

```java
// Generated for Java callers:
Button(String text)                        // uses all defaults
Button(String text, int color)             // uses size default
Button(String text, int color, float size) // no defaults used
```

The Kotlin compiler also generates a synthetic `$default` method internally — a single function with a **bitmask** parameter. A **bitmask** is an integer where each bit acts as a flag: bit 0 set means "use default for first param," bit 1 set means "use default for second param," etc. This is how Kotlin callers use default params — they call `$default` with the appropriate bitmask rather than N+1 separate functions.

```java
// Internal (not for direct use):
Button$default(String text, int color, float size, int mask, Object marker)
// mask bit 0 = use default for color
// mask bit 1 = use default for size
// Java callers use the @JvmOverloads-generated constructors instead
```

---

## `@Inject constructor` and Hilt DI

```kotlin
class UserRepository @Inject constructor(
    private val api: UserApi,
    private val db: UserDao
) {
    init {
        println("Repository ready")  // runs AFTER api and db are assigned
    }
}
```

Hilt (the dependency injection framework) determines what values to provide for `api` and `db`, then calls `UserRepository(api, db)`. Inside `<init>`: parameters are assigned first (`this.api = api`, `this.db = db`), then `init` block runs — so `init` sees fully initialized dependencies.

Hilt constructor injection is NOT magic — it's just calling the constructor with the right arguments. Field injection (`@Inject var field`) is different and does inject after construction.

---

## Memory Trick

```
PRIVATE CONSTRUCTOR = "only I decide how to be born."
  Use when: singleton, validation on construction, named factory variants.

@JvmOverloads = generates N+1 Java constructors from N default params.
  Kotlin callers: one function with defaults (compiler uses bitmask internally)
  Java callers: need actual separate constructors (@JvmOverloads provides them)

DOUBLE-CHECKED LOCKING = thread-safe lazy singleton when you can't use object:
  @Volatile instance: T? = null         ← ensures visibility across threads
  ?: synchronized(lock) {               ← fast path: skip lock if already created
    instance ?: create().also { instance = it }  ← slow path: create once
  }
```

---

## Self-Test

1. What does `private constructor` prevent, and what does it enable?
2. Why is `@Volatile` needed on `instance` in the double-checked locking pattern?
3. Explain what double-checked locking is and why there are two null checks.
4. What does `@JvmOverloads` generate for `class Foo @JvmOverloads constructor(a: Int, b: Int = 0, c: Int = 0)`?
5. With `@Inject constructor`, when does the `init` block run relative to the injected fields being assigned?

---

# Q2.9 — Value Classes (Deep Dive)

> **Builds on:** [Q0.2 (boxing)](phase0_jvm_mental_model_v3.md#q02--jvm-type-mapping-when-does-kotlin-box) · [Q1.7 (value class basics)](01_type_system_foundations.md#q17--value-classes) · [Q3.1 (type erasure)](03_generics_and_variance.md#q31--type-erasure)
> **Connects to:** [Q3.1 (erased at runtime)](03_generics_and_variance.md#q31--type-erasure)

*Q1.7 covers the basics: concept, when boxing happens, name mangling (brief), typealias comparison. This section adds the decompiled bytecode, the full boxing scenario table with reasons, and the exact collision problem that makes mangling necessary.*

---

## The Concrete Picture

```kotlin
@JvmInline value class UserId(val id: String)
@JvmInline value class OrderId(val id: String)
```

At compile time — fully distinct types:

```kotlin
fun getUser(id: UserId) { ... }
fun getOrder(id: OrderId) { ... }

getUser(OrderId("123"))  // ❌ COMPILE ERROR: type mismatch
```

At runtime — wrapper disappears:

```
JVM bytecode:
  getUser-ABCD1234(String id)   // UserId erased to String + hash suffix
  getOrder-EFGH5678(String id)  // OrderId erased to String + hash suffix
```

---

## What "Erased at Runtime" Means in Bytecode

```kotlin
@JvmInline
value class UserId(val id: String)

fun getUser(id: UserId): User { ... }
```

Decompiles to:

```java
// At runtime, UserId is completely gone:
public static final User getUser-HASHCODE(String id) {
    // No UserId wrapper object exists at the JVM level
}
```

The JVM sees `String` directly. No allocation of a `UserId` wrapper. Compile-time type safety, zero runtime cost.

---

## The Four Boxing Scenarios

| Scenario | Example | Why |
|---|---|---|
| Nullable | `val x: UserId? = null` | null needs an object; erased types can't hold null |
| Generic position | `val list: List<UserId>` | Generics erase to `Object` — must be a reference |
| Interface type | `val x: Comparable<UserId> = userId` | Interface dispatch needs an object reference |
| `is` type check | `x is UserId` | Runtime check requires an actual object to inspect |

```kotlin
val a: UserId  = UserId("123")       // ✅ no boxing — erased to String
val b: UserId? = UserId("123")       // ❌ boxing — nullable forces object
val list: List<UserId> = listOf(...) // ❌ boxing — List<Object>
```

Same rules as primitive boxing in [Q0.2](phase0_jvm_mental_model_v3.md#q02--jvm-type-mapping-when-does-kotlin-box).

---

## Why the Compiler Mangles Method Names

Without mangling, there would be a JVM collision:

```kotlin
fun greet(id: UserId) = println("Hello $id")  // erases to: greet(String)
fun greet(name: String) = println("Hello $name")  // also: greet(String)
// JVM sees two methods with identical signatures → compilation error
```

The compiler appends a hash suffix to the value-class-parameterized function:

```kotlin
fun greet(id: UserId) = println("Hello $id")
// Compiles to: greet-HASHCODE(String id)
```

This makes the function invisible to Java callers (the `-` in the name is illegal in Java identifiers). Use `@JvmName("greet")` to provide a clean name for Java interop.

---

## `typealias` vs `value class` — The Safety Difference

```kotlin
typealias UserId = String
typealias ProductId = String

fun process(userId: UserId, productId: ProductId) { }
process(productId, userId)  // ✅ compiles — both are just String to the compiler
```

```kotlin
@JvmInline value class UserId(val id: String)
@JvmInline value class ProductId(val id: String)

fun process(userId: UserId, productId: ProductId) { }
process(productId, userId)  // ❌ COMPILE ERROR — type mismatch
```

`typealias` is documentation. `value class` is enforcement.

---

## Memory Trick

```
value class = TYPE-SAFE TYPEDEF that vanishes at runtime.

typealias UserId = String          → NO safety (UserId IS String, interchangeable)
value class UserId(val id: String) → SAFE at compile time, String at runtime

BOXES when (same rules as primitives):
  UserId?              → nullable
  List<UserId>         → generic position
  Comparable<UserId>   → interface type
  x is UserId          → type check

DOESN'T box when:
  fun doThing(id: UserId) → JVM sees: doThing-HASH(String id)
  val id: UserId = ...    → JVM sees: val id: String = ...
  Zero allocation. Zero overhead.

NAME MANGLING:
  Prevents JVM collision when value class erases to same underlying type.
  The '-' in the mangled name is illegal in Java → function invisible to Java.
  Fix: @JvmName("yourMethodName")
```

---

## Self-Test

1. What does `fun getUser(id: UserId)` decompile to in Java bytecode?
2. Name all four scenarios where a value class gets boxed. Give one example each.
3. Why does the compiler mangle method names for value class parameters?
4. `val a: UserId = UserId("x")` vs `val b: UserId? = UserId("x")` — which allocates an object?
5. `typealias UserId = String` vs `value class UserId(val id: String)` — what's the type-safety difference?

---

# Master Summary: Phase 2

> Kotlin's class system enforces correctness at the language level: `final` prevents the fragile base class problem, initialization order is strictly top-down with super before sub, `sealed` enforces exhaustive handling, `object` gives free thread-safe singletons, and `value class` gives type safety at zero cost.

**1. Class Modifiers** (Q2.1)
`final` by default — prevents fragile base class problem and enables JIT devirtualization.
`open` = vtable lookup. `abstract` = incomplete, must subclass.
→ [Q0.4: dispatch cost](phase0_jvm_mental_model_v3.md#q04--the-jvm-call-stack)

**2. Constructor Mechanics** (Q2.2)
`<init>` = instance initializer. `<clinit>` = class initializer. They are different methods.
`init` blocks + property initializers = one interleaved top-to-bottom `<init>`.
Secondary constructor must delegate to primary. Its body runs after all of primary.

**3. Inheritance Initialization Order** (Q2.3)
Superclass `<init>` runs entirely before subclass `<init>`.
`open` method called in `init` → `INVOKEVIRTUAL` → calls subclass override → subclass fields are null.
Fix: `private`/`final` methods in `init` → `INVOKESPECIAL` → no override possible.

**4. Data Classes** (Q2.4)
Auto-generates `equals`/`hashCode`/`copy`/`componentN` from primary constructor only.
`var` + `HashSet` = corruption. `copy()` = shallow.
→ [Q3.2: @UnsafeVariance](03_generics_and_variance.md#q32--variance)

**5. Sealed Classes** (Q2.5)
Compiler knows all subtypes → exhaustive `when`. Private constructor prevents external subclassing.
`sealed class` = single inheritance. `sealed interface` = multi-inheritance.
→ [Q1.3: Nothing in sealed subtypes](01_type_system_foundations.md#q13--type-hierarchy-any-nothing-unit)

**6. `object` Keyword + Companion Init** (Q2.6)
`<clinit>` = free thread-safe singleton via JVM class loading.
`companion object` members live in `Companion` class. `@JvmStatic` generates real static methods.
Companion `val` is lazy. `const val` never triggers class loading. Circular init = deadlock.
Anonymous objects capture outer class — memory leak risk.
→ [Q0.3: class loading](phase0_jvm_mental_model_v3.md#q03--class-loading-and-init--in-object)

**7. Property Initializer Order** (Q2.7)
Declaration order = execution order. Forward references to not-yet-assigned properties = NPE.
`by lazy { }` defers until first access — safe to reference any other property.

**8. Constructor Visibility + Factory** (Q2.8)
Private constructor → factory methods control creation. Enables singleton, validation, named constructors.
`@Volatile` = memory visibility. Double-checked locking = fast singleton with thread safety.
`@JvmOverloads` = generates N+1 Java constructors. `@Inject constructor` = DI provides args at construction time.

**9. Value Classes** (Q2.9)
Erased to underlying type at runtime. Type-safe at compile time. Boxes in 4 scenarios.
Name mangling prevents JVM collision. `typealias` = no safety. `value class` = enforcement.
→ [Q0.2: boxing](phase0_jvm_mental_model_v3.md#q02--jvm-type-mapping-when-does-kotlin-box)

---

## Final Self-Test: All of Phase 2

1. **(Q2.1)** What is the fragile base class problem? How does Kotlin's `final` default solve it?
2. **(Q2.2)** `class Foo { val x = 1; init { println(x) }; val y = 2 }` — what's the `<init>` execution order?
3. **(Q2.3)** `open class Base { init { doWork() }; open fun doWork() {} }` — `class Child : Base() { val result = "done"; override fun doWork() { println(result) } }` — what prints when you call `Child()`? Why?
4. **(Q2.4)** `data class Config(val items: MutableList<String>)` — `val copy = config.copy()`. Is `copy.items` the same object as `config.items`?
5. **(Q2.5)** Why does `data class Error(...) : Result<Nothing>()` work for `sealed class Result<out T>`?
6. **(Q2.6)** Two threads access a Kotlin `object` singleton simultaneously for the first time. What happens?
7. **(Q2.7)** `class Foo { val a = b.length; val b = "hi" }` — compiles or crashes? When?
8. **(Q2.8)** Why are two null checks needed in double-checked locking? What does `@Volatile` do?
9. **(Q2.9)** `@JvmInline value class Email(val value: String)` — when is this NOT erased to `String` at runtime?

---

*← [Phase 1 — Type System Foundations](01_type_system_foundations.md) | [Phase 3 — Generics and Variance →](03_generics_and_variance.md)*