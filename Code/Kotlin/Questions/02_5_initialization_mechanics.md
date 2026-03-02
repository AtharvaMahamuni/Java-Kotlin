# Phase 2.5: Initialization and Construction Mechanics

> **Core Rule:** JVM initializes **top-to-bottom, superclass-before-subclass, delegation-before-body**. Every trap in this section comes from this single rule.

## Navigation
[← Master Index](master_chains.md)

## Questions in This File
- [Q2.5.1 — Primary Constructor vs `init` Block](#q251--primary-constructor-vs-init-block)
- [Q2.5.2 — Primary vs Secondary Constructors](#q252--primary-vs-secondary-constructors)
- [Q2.5.3 — Inheritance Initialization Order](#q253--inheritance-initialization-order)
- [Q2.5.4 — Companion Object and Object Initialization](#q254--companion-object-and-object-initialization)
- [Q2.5.5 — Property Initializer Order Traps](#q255--property-initializer-order-traps)
- [Q2.5.6 — Constructor Visibility and Factory Patterns](#q256--constructor-visibility-and-factory-patterns)

---

## Q2.5.1 — Primary Constructor vs `init` Block

> **Builds on:** [Q0.3 — Class Loading (`<init>` method)](00_jvm_mental_model.md#q03--class-loading-and-the-static--block)
> **Connects to:** [Q2.5.2 (secondary constructors)](02_5_initialization_mechanics.md#q252--primary-vs-secondary-constructors) · [Q2.5.3 (inheritance order)](02_5_initialization_mechanics.md#q253--inheritance-initialization-order)

### The Concrete Picture

Three things in a class body: constructor params, property initializers, init blocks. They all merge into ONE method (`<init>`), in declaration order:

```kotlin
class User(val name: String) {   // ← constructor param
    val greeting = "Hello, $name"  // ← property initializer
    init { println("1: $name") }   // ← init block
    val bio = "$name!"             // ← property initializer
    init { println("2: $bio") }    // ← init block
}
```

The execution order is exactly the order you WROTE them:
```
User("Alice"):
  → name = "Alice"           (constructor param, always first)
  → greeting = "Hello, Alice" (property initializer)
  → println("1: Alice")      (init block)
  → bio = "Alice!"           (property initializer)
  → println("2: Alice!")     (init block)
```

Not: "all properties, then all init blocks." It's: **one unified top-to-bottom sequence**.

### Are They the Same at the Bytecode Level?

**Yes, and no.** Both compile into the **same `<init>` method**. The primary constructor's parameters become local variables inside `<init>`, and both property initializers and `init` blocks are **interleaved in declaration order** into the body of `<init>`.

```kotlin
class User(val name: String, val age: Int) {
    val greeting = "Hello, $name"  // property initializer 1

    init {
        println("init block 1: name=$name")  // init block 1
    }

    val bio = "$name is $age years old"  // property initializer 2

    init {
        println("init block 2: bio=$bio")  // init block 2
    }
}
```

**Decompiled `<init>` method (simplified):**
```java
public User(String name, int age) {
    // 1. Primary constructor params available as locals
    this.name = name;
    this.age = age;

    // 2. Property initializer 1 (in declaration order)
    this.greeting = "Hello, " + name;

    // 3. init block 1 (in declaration order)
    System.out.println("init block 1: name=" + name);

    // 4. Property initializer 2 (in declaration order)
    this.bio = name + " is " + age + " years old";

    // 5. init block 2 (in declaration order)
    System.out.println("init block 2: bio=" + bio);
}
```

**Execution order:**
```
User("Alice", 30) called
├── 1. name = "Alice", age = 30       [constructor params assigned]
├── 2. greeting = "Hello, Alice"      [property initializer]
├── 3. "init block 1: name=Alice"     [init block]
├── 4. bio = "Alice is 30 years old"  [property initializer]
└── 5. "init block 2: bio=Alice..."   [init block]
```

### Memory Trick

```
INIT ORDER = TOP-TO-BOTTOM declaration order. No exceptions.
Constructor params → then everything interleaved as written.

"Primary constructor vs init block" — same method (<init>), same sequence.
They're not two separate phases. It's one continuous top-down execution.
```

### Why Interleaved Order Matters

**The Bug If Properties Ran First, Then All `init` Blocks:**

```kotlin
class Example {
    val computed = processName()  // property initializer

    val name = "Alice"            // property declared AFTER computed

    init {
        println(name)  // would print "Alice" if init ran after all properties
    }

    private fun processName() = name.uppercase()  // BUG: name is "" here!
}
```

With declaration-order interleaving, `processName()` is called when `name` is still empty/null — making the bug visible early. If properties ran first, `name` would be set, hiding the problem in some orderings.

---

## Q2.5.2 — Primary vs Secondary Constructors

> **Builds on:** [Q2.5.1 — Primary Constructor](02_5_initialization_mechanics.md#q251--primary-constructor-vs-init-block)
> **Connects to:** [Q4.5 — Default Parameters (prefer over secondary constructors)](04_functions_lambdas_inlining.md#q45--named-and-default-parameters) · [Q2.5.6 — Constructor Visibility](02_5_initialization_mechanics.md#q256--constructor-visibility-and-factory-patterns)

### The Concrete Picture

Secondary constructor must chain to primary. Think of it as a delegation chain — the primary does the real work, secondary just adds on top:

```
new User("Alice")              → secondary called
  ├── this("Alice", 0) → primary called
  │     ├── name = "Alice"
  │     ├── age = 0
  │     ├── [all property initializers run]
  │     └── [all init blocks run]
  └── secondary body runs  ← AFTER all of the above
```

Primary always runs first. Secondary body runs last. init blocks are part of primary, not secondary.

### Why Must Secondary Constructors Delegate to Primary?

The JVM `<init>` method **must** call another `<init>` as its first action (via `INVOKESPECIAL`) — either a superclass `<init>` or another constructor in the same class. This is a JVM specification requirement.

The primary constructor is the "root" `<init>` that sets up all the properties. Secondary constructors must go through it to ensure all properties are initialized.

```kotlin
class User(val name: String, val age: Int) {
    // Secondary constructor MUST delegate via this()
    constructor(name: String) : this(name, 0) {
        println("Secondary constructor body")
    }
}
```

### Execution Order: Delegation First, Then Body

```
new User("Alice")  →  secondary constructor called
├── 1. this("Alice", 0) delegation → calls primary constructor
│   ├── name = "Alice"
│   ├── age = 0
│   ├── [property initializers run]
│   └── [init blocks run]
└── 2. Secondary constructor body runs AFTER
       "Secondary constructor body"
```

```
⚠️ TRAP: init blocks run as part of the primary constructor,
BEFORE the secondary constructor body!
```

### Memory Trick

```
SECONDARY CONSTRUCTOR rule: must call this() first (primary).
The primary is "the real init." Secondary body is just an afterthought.

INIT BLOCK vs SECONDARY BODY order:
  init blocks  → run as part of PRIMARY (before secondary body)
  secondary body → runs AFTER everything in primary

PREFER default parameters over secondary constructors:
  class User(val name: String, val age: Int = 0)   // cleaner
  vs
  constructor(name: String) : this(name, 0) { }    // more verbose
  Use secondary only when logic differs per constructor path.
```

### Secondary Constructor vs Default Parameters

```kotlin
// Option 1: Default parameter (preferred in Kotlin)
class User(val name: String, val age: Int = 0)

// Option 2: Secondary constructor (needed for Java interop or complex logic)
class User(val name: String, val age: Int) {
    constructor(name: String) : this(name, 0)
}
```

**When to use secondary constructors:**
1. **Java interop**: `@JvmOverloads` generates multiple Java constructors from default params, but secondary constructors give finer control
2. **Different initialization logic**: secondary constructor body can run additional code
3. **No common primary**: when different constructor paths need different parameter validation

---

## Q2.5.3 — Inheritance Initialization Order

> **Builds on:** [Q2.5.1 — init Block Order](02_5_initialization_mechanics.md#q251--primary-constructor-vs-init-block) · [Q2.1 — open/final Modifiers](02_classes_and_objects.md#q21--class-modifiers)
> **Connects to:** [Q0.4 — INVOKEVIRTUAL dispatch](00_jvm_mental_model.md#q04--the-jvm-call-stack) · [Q2.1 — Why final is safe](02_classes_and_objects.md#q21--class-modifiers)

> **This section contains the most dangerous trap in all of Kotlin.**

### The Concrete Picture

Two classes. Parent runs BEFORE child. Now imagine parent calls a method that child overrides:

```
class Child : Base()

Base.init runs → calls message → JVM dispatches to Child.getMessage()
                                  → Child.message not yet assigned!
                                  → returns null
Child.init runs → message = "from Child"  ← TOO LATE
```

The bug step by step:
```
new Child()
  ├── 1. Base.<init> starts
  │   ├── Base properties initialize
  │   ├── Base init block: println(message)
  │   │           message calls → INVOKEVIRTUAL → Child.getMessage()
  │   │           Child.message field = null (Child hasn't run yet)
  │   │           prints: null  ← BUG
  │   └── Base.<init> done
  └── 2. Child.<init> starts
      ├── Child.message = "from Child"  ← would have been fine if Base hadn't read it
      └── Child.<init> done
```

Parent already finished using `message` before child got to initialize it.

### The Exact Execution Order for Subclass Instantiation

```
Superclass <init> runs FIRST, THEN subclass <init>
```

```
new Child() called
├── 1. Child's <init> starts
│   ├── Calls super() (superclass <init>) FIRST — JVM requirement
│   │   ├── Superclass property initializers
│   │   ├── Superclass init blocks
│   │   └── Superclass primary constructor body
│   ├── Child property initializers
│   ├── Child init blocks
│   └── Child primary constructor body
└── Object fully constructed
```

### The Open Function in `init` — The Exact Bug

This is an infamous trap that silently produces `null` or `0`:

```kotlin
open class Base {
    open val message: String = "from Base"

    init {
        // Called DURING Base's <init>, BEFORE Child's <init>
        println(message)  // Prints: null  ← BUG!
    }
}

class Child : Base() {
    override val message: String = "from Child"
    // This assignment happens in Child's <init>
    // But Base's init already ran BEFORE Child's <init>!
}

fun main() {
    Child()
    // Output: null  (not "from Child"!)
}
```

**Step-by-step execution trace:**
```
new Child()
├── Child.<init> starts
│   ├── Calls Base.<init> (superclass first)
│   │   ├── Base.message backing field = "from Base"
│   │   │   Wait — Child OVERRIDES message!
│   │   │   JVM calls the OVERRIDDEN getter (Child.getMessage())
│   │   │   Child.message field = ??? — not yet assigned! = null
│   │   ├── init block: println(message) → calls Child.getMessage() → null
│   │   └── Base.<init> completes
│   ├── Child.message = "from Child"  ← TOO LATE!
│   └── Child.<init> completes
```

**The override causes the superclass init to see the NOT-YET-INITIALIZED subclass field.**

**The same bug with a function:**
```kotlin
open class Animal {
    init {
        sound()  // calls overridden version — dangerous!
    }
    open fun sound() { println("...") }
}

class Dog : Animal() {
    private val bark = "Woof"
    override fun sound() { println(bark) }  // bark is null when called from Animal.init!
}

Dog()  // prints: null (not "Woof")
```

### Memory Trick

```
INHERITANCE INIT ORDER = SUPER BEFORE SUB, always.

THE FATAL COMBINATION:
  open class Base  +  open fun in init  +  Child overrides that fun
  = Base's init calls Child's version = Child's fields not yet initialized = null/0

MENTAL CHECK before writing any open class:
  "Does my init block call any open method?"
  If YES → risk of seeing null/0 from subclass fields.

SAFE alternatives:
  1. Make the method final/private (compiler uses INVOKESPECIAL, no override)
  2. Don't call overridable methods in init
  3. Move logic to a factory function that runs after construction
```

### How `final` Removes the Danger

If `Animal` is `final` (or `sound()` is `final`/`private`), the compiler uses `INVOKESPECIAL` (direct call) instead of [`INVOKEVIRTUAL`](00_jvm_mental_model.md#q04--the-jvm-call-stack) (virtual dispatch). There's no override possible, so the call in `init` always resolves to the base class method — which IS fully initialized.

```kotlin
class Animal {  // final by default!
    private val sound = "..."
    init {
        printSound()  // calls THIS class's printSound — always safe
    }
    private fun printSound() = println(sound)  // private = no override possible
}
```

### The "Leaked `this`" Problem

```kotlin
class EventManager {
    init {
        EventBus.register(this)  // `this` is NOT fully constructed yet!
        // Another thread might call handle() before the rest of init completes
    }
    fun handle(event: Event) { ... }
}
```

**Why it's dangerous:** Between `EventBus.register(this)` and the end of `<init>`, the object is partially initialized. If another thread receives an event and calls `handle()`, it may access fields that haven't been initialized yet.

---

## Q2.5.4 — Companion Object and Object Initialization

> **Builds on:** [Q0.3 — Class Loading and `<clinit>`](00_jvm_mental_model.md#q03--class-loading-and-the-static--block) · [Q2.4 — The `object` Keyword](02_classes_and_objects.md#q24--the-object-keyword)
> **Connects to:** [Q1.1 — const val inlining](01_type_system_foundations.md#q11--val-vs-const-val) · [Q2.5.1 — init block timing](02_5_initialization_mechanics.md#q251--primary-constructor-vs-init-block)

### The Concrete Picture

Two accesses. One triggers class loading. One doesn't:

```kotlin
class Config {
    companion object {
        const val TAG = "Config"          // compile-time constant
        val URL = "https://api.example.com"  // runtime value
    }
}

Log.d(Config.TAG, "hi")    // bytecode: LDC "Config"  ← no class loading!
val url = Config.URL        // bytecode: GETSTATIC + INVOKEVIRTUAL ← class loaded here
```

Direction of dependency:
```
const val  → compiler INLINES it → Config class never touched for that line
val        → compiler READS it at runtime → Config's companion must be initialized first
```

### When Does a `companion object` Get Initialized?

A `companion object` is initialized **lazily** — on the first access to any of its non-const members.

```kotlin
class Config {
    companion object {
        val URL = "https://api.example.com"  // triggers companion init on first access
        const val TAG = "Config"             // const val: NO companion init triggered!
    }
}

// This triggers companion object initialization:
val url = Config.URL

// This does NOT trigger companion initialization (const val is inlined):
Log.d(Config.TAG, "message")  // → Log.d("Config", "message") — no class loading
```

### Why `const val` Doesn't Trigger Companion Initialization

[`const val`](01_type_system_foundations.md#q11--val-vs-const-val) is **inlined at the call site** at compile time — the compiler replaces `Config.TAG` with the literal `"Config"`. The JVM never needs to load the `Config` class or its companion, so the static initializer never runs.

This is proven by looking at the bytecode:
```bytecode
; Log.d(Config.TAG, "message"):
LDC "Config"        ; literal constant — no GETSTATIC, no class loading
LDC "message"
INVOKESTATIC android/util/Log.d
```

### Memory Trick

```
COMPANION INIT is LAZY — triggered on first NON-CONST access.
const val → inlined at call site → companion NEVER initialized for that access.
val       → runtime access → companion initialized on first touch.

CIRCULAR INIT DEADLOCK:
  object A uses B during init, object B uses A during init.
  Thread 1: initializing A → needs B → waits for B's init lock
  Thread 2: initializing B → needs A → waits for A's init lock
  DEADLOCK — both threads wait forever.
  Fix: avoid cross-singleton dependencies during initialization.
```

### Circular Initialization Deadlock Risk

```kotlin
object A {
    val ref = B.value  // triggers B to initialize during A's initialization
    val name = "A"
}

object B {
    val ref = A.name   // triggers A to initialize during B's initialization
    val value = 42
}

// Thread 1: accesses A → A starts initializing → tries to access B
// Thread 2: accesses B → B starts initializing → tries to access A
// DEADLOCK: both threads hold their class's init lock, waiting for the other
```

---

## Q2.5.5 — Property Initializer Order Traps

> **Builds on:** [Q2.5.1 — Interleaved Init Order](02_5_initialization_mechanics.md#q251--primary-constructor-vs-init-block)
> **Connects to:** [Q5.2 — lazy defers initialization](05_properties_and_delegation.md#q52--lazy-internals) · [Q5.1 — lateinit internals](05_properties_and_delegation.md#q51--lateinit-internals)

### The Concrete Picture

Declaration order is execution order. Reference something below you = NPE:

```kotlin
class Example {
    val length = name.length   // runs first — name is null here!  → NPE
    val name = "Alice"         // runs second
}
```

The compiler doesn't warn you. It compiles fine. You only find out at runtime.

Compare with `lazy`:
```kotlin
class Example {
    val length by lazy { name.length }  // runs only when accessed, AFTER construction
    val name = "Alice"
}
// length is safe — lazy block runs after entire constructor finishes
```

### Can a Property Reference One Declared Below It?

```kotlin
class Example {
    val length = name.length  // BUG: name not yet initialized!
    val name = "Alice"
}
```

This **compiles** — the compiler doesn't check cross-property reference order. But at runtime:
- `length` is initialized first (declared first)
- At that point, `name` is still `null` (reference not yet assigned)
- `null.length` → **NullPointerException at runtime**

**Bytecode reveals the order:**
```java
// Generated <init>:
this.length = this.name.length();  // name is null here → NPE!
this.name = "Alice";               // assigned AFTER!
```

### Memory Trick

```
PROPERTY ORDER TRAP:
  Rule: declaration order = execution order.
  Reference a property BELOW your current line = it's still null.
  Compiler won't catch this. It compiles. It crashes at runtime.

SAFE PATTERN when order is ambiguous: use lazy { }
  lazy block defers until first access.
  By that time, the entire constructor has finished.
  Safe reference to any other property of the same object.

eager val  → initialized at construction time (order matters!)
lazy val   → initialized at first access (order doesn't matter)
```

### `const val` vs Regular `val` — Initialization Timing

```kotlin
object Config {
    const val VERSION = "1.0"    // Compile-time: inlined at call sites, no runtime cost
    val BUILD_DATE = getDate()   // Runtime: initialized in <clinit> on first access
}
```

`const val` is never "assigned" at runtime — its value is baked directly into bytecodes that reference it. Regular `val` is assigned in `<clinit>` (static initializer) when the class loads.

### [`lazy`](05_properties_and_delegation.md#q52--lazy-internals) vs Eager `val` — Timing

```kotlin
class Screen {
    val eagerData = loadData()    // initialized when Screen is constructed
    val lazyData by lazy { loadData() }  // initialized on first access to lazyData
}
```

```
Screen()
├── eagerData: loadData() called immediately
└── lazyData: NOT called yet

screen.lazyData  ← FIRST ACCESS
└── lazy block: loadData() called now, result cached
```

---

## Q2.5.6 — Constructor Visibility and Factory Patterns

> **Builds on:** [Q2.5.2 — Secondary Constructors](02_5_initialization_mechanics.md#q252--primary-vs-secondary-constructors) · [Q2.4 — object singleton pattern](02_classes_and_objects.md#q24--the-object-keyword)
> **Connects to:** [Q13.5 — Dependency Injection](13_android_architecture.md#q135--dependency-injection)

### The Concrete Picture

Private constructor = you control every entry point into the object:

```kotlin
class Database private constructor(val url: String)

// From outside: can't do Database("url")  → COMPILE ERROR
// Only way in:
val db = Database.getInstance("jdbc:sqlite:app.db")
```

Why this matters:
```
Public constructor:   anyone creates instances → no control
Private constructor:  only factory methods create instances → full control:
  - Return cached instance (singleton)
  - Validate params before construction
  - Return subclass based on params
  - Give meaningful names: Database.inMemory() vs Database.persistent()
```

### Private Constructor + Factory Pattern

```kotlin
class Database private constructor(val url: String) {
    companion object {
        @Volatile private var instance: Database? = null  // @Volatile ensures visibility across threads (see [Q5.2 — lazy internals](05_properties_and_delegation.md#q52--lazy-internals))

        fun getInstance(url: String): Database {
            return instance ?: synchronized(this) {
                instance ?: Database(url).also { instance = it }
            }
        }
    }
}

// Can't do: Database("url") → compile error: constructor is private
val db = Database.getInstance("jdbc:sqlite:app.db")
```

**Why factory over public constructor:**
- Control instance creation (singleton, pooling, validation)
- Named constructors are more descriptive than positional params
- Can return a subclass or cached instance

### `@JvmOverloads` Bytecode

```kotlin
class Button @JvmOverloads constructor(
    val text: String,
    val color: Int = 0xFF0000,
    val size: Float = 14f
)
```

With `@JvmOverloads`, the compiler generates **N+1 constructors** for N default parameters:

```java
// Generated (for Java callers):
Button(String text)                              // uses all defaults
Button(String text, int color)                  // uses size default
Button(String text, int color, float size)      // no defaults
```

The Kotlin compiler also generates a synthetic `$default` method with a bitmask:
```java
// Internal: Button$default(String text, int color, float size, int mask, Object defaultConstructorMarker)
// mask bit 0 = use default for color
// mask bit 1 = use default for size
```

### Memory Trick

```
PRIVATE CONSTRUCTOR = "only I decide how to be born."
  Use when: singleton, validation on construction, named factory variants.

@JvmOverloads = generates N+1 Java constructors from N default params.
  Kotlin callers: one function with defaults (no overloads needed)
  Java callers:   need actual separate constructors (@JvmOverloads provides them)

DOUBLE-CHECKED LOCKING = for thread-safe lazy singleton when you can't use object:
  @Volatile var instance: T? = null
  ?: synchronized(lock) { instance ?: create().also { instance = it } }
  Outer ?: avoids lock after first creation.
  Inner ?: handles race condition between two threads entering synchronized.
```

### `@Inject constructor` and Hilt DI

```kotlin
class UserRepository @Inject constructor(
    private val api: UserApi,
    private val db: UserDao
) {
    init {
        println("Repository ready")  // Runs AFTER Hilt injects api and db
    }
}
```

**Execution order with DI:**
1. Hilt (DI framework) determines what `api` and `db` values to provide
2. Hilt calls `UserRepository(api, db)` — the `@Inject` constructor
3. Inside `<init>`: parameters are assigned (`this.api = api`, etc.), then `init` block runs
4. The `init` block sees fully initialized `api` and `db`

Hilt does NOT magically inject fields after construction — it provides constructor arguments at construction time. Field injection (`@Inject var field`) is different and does inject post-construction.

---

## Initialization Order — Master Reference

```
Complete initialization sequence for: class Child(val x: Int) : Base(x)

1.  Child's <init> called
2.  super(x) — Base's <init> called:
    a. Base's property initializers (declaration order)
    b. Base's init blocks (interleaved with above, declaration order)
    c. Base's primary constructor body completes
3.  Child's property initializers (declaration order)
4.  Child's init blocks (interleaved with above, declaration order)
5.  Child's primary constructor body completes
6.  Object fully constructed

⚠️ Any `open` method called in Base's init (step 2b) sees Child's
   uninitialized fields (step 3 hasn't run yet)!
```

---

*← [Phase 2 — Classes and Objects](02_classes_and_objects.md) | [Phase 3 — Generics and Variance →](03_generics_and_variance.md)*
