# Phase 2.5: Initialization and Construction Mechanics

> **Core Rule:** JVM initializes **top-to-bottom, superclass-before-subclass, delegation-before-body**. Every trap in this section comes from this single rule.

## Navigation
| Phase | File |
|-------|------|
| 0 — JVM Mental Model | [00_jvm_mental_model.md](00_jvm_mental_model.md) |
| 1 — Type System | [01_type_system_foundations.md](01_type_system_foundations.md) |
| 2 — Classes & Objects | [02_classes_and_objects.md](02_classes_and_objects.md) |
| **2.5 — Initialization** | ← You are here |
| 3 — Generics & Variance | [03_generics_and_variance.md](03_generics_and_variance.md) |
| 4 — Functions & Lambdas | [04_functions_lambdas_inlining.md](04_functions_lambdas_inlining.md) |
| 5 — Properties & Delegation | [05_properties_and_delegation.md](05_properties_and_delegation.md) |
| Master Chains | [master_chains.md](master_chains.md) |

---

## Q2.5.1 — Primary Constructor vs `init` Block

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

> **This section contains the most dangerous trap in all of Kotlin.**

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

### How `final` Removes the Danger

If `Animal` is `final` (or `sound()` is `final`/`private`), the compiler uses `INVOKESPECIAL` (direct call) instead of `INVOKEVIRTUAL` (virtual dispatch). There's no override possible, so the call in `init` always resolves to the base class method — which IS fully initialized.

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

`const val` is **inlined at the call site** at compile time — the compiler replaces `Config.TAG` with the literal `"Config"`. The JVM never needs to load the `Config` class or its companion, so the static initializer never runs.

This is proven by looking at the bytecode:
```bytecode
; Log.d(Config.TAG, "message"):
LDC "Config"        ; literal constant — no GETSTATIC, no class loading
LDC "message"
INVOKESTATIC android/util/Log.d
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

### `const val` vs Regular `val` — Initialization Timing

```kotlin
object Config {
    const val VERSION = "1.0"    // Compile-time: inlined at call sites, no runtime cost
    val BUILD_DATE = getDate()   // Runtime: initialized in <clinit> on first access
}
```

`const val` is never "assigned" at runtime — its value is baked directly into bytecodes that reference it. Regular `val` is assigned in `<clinit>` (static initializer) when the class loads.

### `lazy` vs Eager `val` — Timing

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

### Private Constructor + Factory Pattern

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
