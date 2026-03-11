# Section 4 — Kotlin Basics, Classes & Functional (Q53–Q82)

---

## Kotlin Basics (Q53–Q61)

### Q53. What is Kotlin?
**Definition:** A statically-typed, JVM (and multiplatform) language by JetBrains. Google's preferred language for Android since 2019.
**Core Idea:** 100% interoperable with Java. More concise, safer (null safety), and expressive.
**How it Works:** Kotlin code compiles to JVM bytecode (same as Java) via the Kotlin compiler (`kotlinc`).
**Example:** No semicolons, `val`/`var` instead of type declarations, null safety built-in.
**Interview Insight:** Kotlin is not just "better Java" — coroutines, extension functions, and data classes solve real Android pain points. Know WHY Kotlin was chosen.

---

### Q54. What is null safety?
**Definition:** Kotlin's type system distinguishes between nullable and non-nullable types at compile time.
**Core Idea:** `String` cannot be null. `String?` can be null. The compiler forces you to handle null.
**How it Works:** Nullable types require explicit handling: safe call `?.`, Elvis `?:`, or non-null assertion `!!`.
**Example:** `val name: String = null` → compile error. `val name: String? = null` → OK, but must handle null before use.
**Interview Insight:** Null safety eliminates NullPointerExceptions at compile time — the #1 cause of Android crashes. `!!` is a code smell; only use it when you're 100% sure.

---

### Q55. What is a nullable type?
**Definition:** A type suffixed with `?` that explicitly allows `null` values.
**Core Idea:** `String?` = "a String or null." Forces the developer to handle the null case.
**How it Works:** The compiler tracks nullability. You can't use a `String?` where a `String` is expected without a null check.
**Example:** `fun getName(): String? = if (loggedIn) userName else null`
**Interview Insight:** When calling Java code from Kotlin, Java types appear as "platform types" (e.g., `String!`) — Kotlin can't know if they're nullable. Assign them to a typed variable to get a compile-time check.

---

### Q56. What is the `!!` operator?
**Definition:** Non-null assertion. Converts `T?` to `T`. Throws `NullPointerException` if the value is null.
**Core Idea:** "I'm sure this is not null — trust me." If you're wrong, you get an NPE.
**How it Works:** `name!!.length` — if `name` is null, throws `KotlinNullPointerException`.
**Example:** `val len = name!!.length` — use only when you've already verified `name` is non-null by logic.
**Interview Insight:** `!!` is a code smell. In a code review, every `!!` should be questioned. Prefer `?: throw IllegalStateException(...)` to give a meaningful error.

---

### Q57. What is the safe call operator `?.`?
**Definition:** Calls a method or accesses a property only if the receiver is non-null. Returns `null` if receiver is null.
**Core Idea:** Shortcut for `if (x != null) x.method() else null`.
**How it Works:** `name?.length` returns `Int?` — either the length or null. No NPE.
**Example:** `user?.address?.city` — safely navigates a chain of nullable types. Returns null at the first null in the chain.
**Interview Insight:** Safe calls can be chained. They return a nullable type. Combine with Elvis `?:` to provide a default: `user?.name ?: "Unknown"`.

---

### Q58. What is the Elvis operator `?:`?
**Definition:** Returns the left-hand side if it's non-null, otherwise returns the right-hand side.
**Core Idea:** `a ?: b` = "give me `a`, or if that's null, give me `b`."
**How it Works:** `val name = user?.name ?: "Anonymous"` — if `user` is null or `name` is null, use "Anonymous".
**Example:** `val length = name?.length ?: 0` — returns 0 if name is null.
**Interview Insight:** The right side of `?:` can be `throw` or `return`. `val user = findUser() ?: return` is idiomatic Kotlin for early return on null.

---

### Q59. What is type inference?
**Definition:** The compiler automatically deduces a variable's type from its value — you don't have to declare it explicitly.
**Core Idea:** `val x = 42` — compiler infers `x` is `Int`. Less boilerplate, same type safety.
**How it Works:** Works for `val`/`var`, lambda parameters, and function return types (in some cases).
**Example:** `val name = "Alice"` — compiler infers `String`. `val list = listOf(1, 2, 3)` — infers `List<Int>`.
**Interview Insight:** Type inference does NOT mean Kotlin is dynamically typed. The type is still fixed at compile time; you just don't have to write it.

---

### Q60. What is a primary constructor?
**Definition:** The main constructor declared in the class header, directly after the class name.
**Core Idea:** The shortest and most common way to define a constructor in Kotlin.
**How it Works:** `class Person(val name: String, var age: Int)` — `name` and `age` are both constructor parameters AND properties.
**Example:** `class Dog(val name: String, val breed: String)`. Instantiate: `Dog("Rex", "Labrador")`.
**Interview Insight:** In the primary constructor, `val`/`var` makes the parameter a property. Without `val`/`var`, it's just a constructor parameter (not accessible as a property).

---

### Q61. What is a secondary constructor?
**Definition:** Additional constructors defined with the `constructor` keyword inside the class body.
**Core Idea:** Used when you need multiple ways to construct an object, with different parameters.
**How it Works:** Must call the primary constructor via `this(...)`. Less common in Kotlin — default parameter values often replace them.
**Example:** `constructor(name: String) : this(name, 0)` — calls primary constructor with default age.
**Interview Insight:** Prefer default parameter values over secondary constructors: `class Dog(val name: String, val age: Int = 0)` is cleaner.

---

## Classes (Q62–Q69)

### Q62. What is a data class?
**Definition:** A class primarily used to hold data. Kotlin auto-generates `equals()`, `hashCode()`, `toString()`, `copy()`, and `componentN()` functions.
**Core Idea:** Reduces boilerplate for POJOs. Immutable by convention (`val` properties).
**How it Works:** Declare with `data class`. Properties in the primary constructor are used for all generated functions.
**Example:** `data class User(val id: Int, val name: String)`
**Interview Insight:** Data class `==` checks structural equality (compares field values), not reference equality. Use `copy()` to create modified versions: `user.copy(name = "Bob")`.

---

### Q63. What methods are automatically generated in a data class?
**Definition:** `equals()`, `hashCode()`, `toString()`, `copy()`, and `componentN()` (for destructuring).
**Core Idea:** All of these are based on the properties declared in the PRIMARY constructor.
**How it Works:**
- `equals()`: compares all primary constructor properties
- `hashCode()`: based on all primary constructor properties
- `toString()`: `"User(id=1, name=Alice)"`
- `copy()`: creates a copy with optionally changed fields
- `component1()`, `component2()`: enables `val (id, name) = user`
**Example:** `val (id, name) = user` — uses `component1()` and `component2()`.
**Interview Insight:** Properties declared in the class BODY (not primary constructor) are NOT included in `equals`/`hashCode`. This is a common source of bugs.

---

### Q64. What is a sealed class?
**Definition:** A class with a restricted hierarchy — all subclasses must be defined in the same file/package.
**Core Idea:** Represents a closed set of types. Enables exhaustive `when` expressions without an `else` branch.
**How it Works:** `sealed class Result`. Subclasses: `data class Success(val data: T)`, `data class Error(val msg: String)`, `object Loading`.
**Example:** `when (result) { is Success -> show(it.data); is Error -> showError(it.msg); is Loading -> showSpinner() }` — compiler verifies all cases.
**Interview Insight:** Sealed classes are the Kotlin idiom for representing states (UiState) or results (Success/Error/Loading). No `else` needed in `when` → compiler enforces all cases are handled.

---

### Q65. What is an enum class?
**Definition:** A class representing a fixed set of named constants.
**Core Idea:** Type-safe named constants with optional properties and methods.
**How it Works:** `enum class Direction { NORTH, SOUTH, EAST, WEST }`. Each constant is an instance of the enum class.
**Example:** `enum class Status(val code: Int) { OK(200), NOT_FOUND(404), ERROR(500) }`
**Interview Insight:** Prefer `sealed class` over `enum` when each variant needs different data. `enum` constants all share the same structure; `sealed class` subclasses can have different shapes.

---

### Q66. What is an object declaration?
**Definition:** A way to create a singleton — a class with exactly one instance, created lazily on first access.
**Core Idea:** `object MySingleton { ... }` — thread-safe, lazily initialized singleton.
**How it Works:** Kotlin generates a class with a `INSTANCE` field (equivalent to a Java singleton pattern). No constructor needed.
**Example:** `object DatabaseManager { fun connect() { ... } }` — called as `DatabaseManager.connect()`.
**Interview Insight:** Object declarations are initialized lazily and thread-safely. They replace the Java singleton boilerplate pattern entirely.

---

### Q67. What is a companion object?
**Definition:** An object tied to a class (not an instance). Accessed via the class name. Equivalent to Java's static members.
**Core Idea:** Kotlin has no `static` keyword. Companion objects fill that role.
**How it Works:** `companion object { const val TAG = "MyActivity"; fun create() = MyActivity() }`. Accessed as `MyActivity.TAG`.
**Example:** `companion object { fun newInstance(): MyFragment = MyFragment().apply { ... } }` — factory method pattern.
**Interview Insight:** Companion object members are NOT truly static at the JVM level. Use `@JvmStatic` if you need to call them from Java as static methods.

---

### Q68. What are nested classes?
**Definition:** A class defined inside another class. By default in Kotlin, nested classes do NOT hold a reference to the outer class.
**Core Idea:** Kotlin's default: nested class = Java's `static` inner class. No implicit outer reference.
**How it Works:** `class Outer { class Nested { } }` — `Nested` can be created without an `Outer` instance.
**Example:** `val nested = Outer.Nested()` — note: `Outer` instance not needed.
**Interview Insight:** Kotlin flips the Java default: Java inner classes ARE non-static by default (hold outer reference = memory leak risk). Kotlin nested classes do NOT hold the reference by default — safer.

---

### Q69. What are inner classes?
**Definition:** A nested class marked with `inner` keyword — holds a reference to the outer class instance.
**Core Idea:** Opposite of a nested class. Can access the outer class's members.
**How it Works:** `class Outer { inner class Inner { fun greet() = "Hello from ${this@Outer}" } }`. Requires an `Outer` instance to create.
**Example:** `val inner = Outer().Inner()`
**Interview Insight:** `inner` class holds a reference to the outer class — potential memory leak if the inner class outlives the outer (like anonymous Runnables in Android holding Activity reference).

---

## Functional Features (Q70–Q74)

### Q70. What is a lambda expression?
**Definition:** An anonymous function that can be passed as a value or stored in a variable.
**Core Idea:** Functions are first-class citizens in Kotlin. A lambda is a function value.
**How it Works:** `{ params -> body }`. If one parameter, use `it`. Last parameter rule: lambda can be moved outside parens.
**Example:** `list.filter { it > 5 }` — the `{ it > 5 }` is a lambda.
**Interview Insight:** Lambdas in Kotlin that capture variables from outer scope create closures. Non-inline lambdas create object instances (small allocation). Use `inline` functions to avoid this.

---

### Q71. What is a higher-order function?
**Definition:** A function that takes another function as a parameter or returns a function.
**Core Idea:** Enables abstraction over behavior, not just data. `map`, `filter`, `forEach` are all higher-order functions.
**How it Works:** `fun doWork(action: () -> Unit) { action() }` — takes a lambda and invokes it.
**Example:** `fun repeat(n: Int, action: (Int) -> Unit) { for (i in 0..n) action(i) }`
**Interview Insight:** Higher-order functions with lambdas create new objects at runtime (allocation). Use `inline` to eliminate this overhead — the lambda code is copy-pasted into the call site.

---

### Q72. What is an inline function?
**Definition:** A function where the compiler copy-pastes the function body (and its lambda args) at each call site, eliminating object creation.
**Core Idea:** `inline` avoids the allocation cost of lambdas. Used extensively in Kotlin stdlib (`let`, `run`, `apply`, `filter`, `map`).
**How it Works:** Compiler replaces the function call with the actual code. No `Function` object created.
**Example:** `inline fun measure(block: () -> Unit) { val start = System.nanoTime(); block(); println(System.nanoTime() - start) }`
**Interview Insight:** `inline` increases bytecode size (code is duplicated). Worth it for hot paths (called in loops) or reified generics. Cannot store an inline lambda in a variable.

---

### Q73. What is `crossinline`?
**Definition:** Marks a lambda parameter that must NOT use non-local returns — the lambda may be called in a different execution context (e.g., in another lambda or runnable).
**Core Idea:** Allows passing the lambda to a context where non-local return would be illegal (like a Runnable).
**How it Works:** `inline fun doAsync(crossinline action: () -> Unit) { Thread { action() }.start() }` — the lambda runs in a Thread; `return` would be confusing here.
**Example:** Without `crossinline`: could `return` from the outer function inside a Thread — dangerous.
**Interview Insight:** Use `crossinline` when you inline a lambda but pass it to another execution context. The lambda can still use `return` — but it's a local return from the lambda, not a non-local return.

---

### Q74. What is `noinline`?
**Definition:** Marks a specific lambda parameter of an inline function as NOT inlined — it's treated as a regular function object.
**Core Idea:** When you need to store a lambda in a variable or pass it to a non-inline function.
**How it Works:** `inline fun process(action1: () -> Unit, noinline action2: () -> Unit) { savedAction = action2; action1() }` — `action2` is stored, so it can't be inlined.
**Example:** Needed when you have multiple lambda params and one needs to be stored (e.g., a callback).
**Interview Insight:** `noinline` lets you mix: inline some lambdas for performance, non-inline others for flexibility (storing them). You rarely use this directly but need to know it for interviews.

---

## Type System (Q75–Q78)

### Q75. What is covariance?
**Definition:** `out T` — a type parameter that can only be PRODUCED (read), not consumed (written). Enables subtype substitution.
**Core Idea:** If `Dog` is a subtype of `Animal`, then `Producer<Dog>` is a subtype of `Producer<Animal>`.
**How it Works:** `class Box<out T>(val value: T)` — T can only appear in `out` position (return type). You can read T but not write T.
**Example:** `List<out Animal>` — you can assign `List<Dog>` to it. You can read Animals from it, but can't add to it.
**Interview Insight:** `List<T>` in Kotlin is `List<out T>` — covariant. That's why you can assign `List<Dog>` to `List<Animal>`. `MutableList<T>` is invariant.

---

### Q76. What is contravariance?
**Definition:** `in T` — a type parameter that can only be CONSUMED (written), not produced (read).
**Core Idea:** If `Dog` is a subtype of `Animal`, then `Consumer<Animal>` is a subtype of `Consumer<Dog>`.
**How it Works:** `class Trainer<in T> { fun train(t: T) { } }` — T appears in `in` position only (parameter). You can write T but not read it.
**Example:** `Comparable<T>` is contravariant — a `Comparable<Animal>` can compare `Dog`s (since Dog IS-A Animal).
**Interview Insight:** PECS rule: Producer = `out` (covariant), Consumer = `in` (contravariant). `Comparator<T>` is `in T` — a `Comparator<Animal>` works for `Dog`.

---

### Q77. What is invariance?
**Definition:** The default. A type parameter that is neither covariant nor contravariant — no substitution allowed.
**Core Idea:** `Box<Dog>` is NOT a subtype of `Box<Animal>`. They are completely unrelated types.
**How it Works:** `MutableList<T>` is invariant — can't assign `MutableList<Dog>` to `MutableList<Animal>` because you could add a `Cat` through the `Animal` reference.
**Example:** `MutableList<Dog>` cannot be assigned to `MutableList<Animal>` — invariant.
**Interview Insight:** Invariance is the safe default for mutable containers. If you could assign `MutableList<Dog>` to `MutableList<Animal>`, you could call `list.add(Cat())` and corrupt it.

---

### Q78. What is star projection?
**Definition:** `*` — used when you don't know or don't care about the type parameter. Similar to Java's raw type but safer.
**Core Idea:** `List<*>` = "a list of some unknown type." You can read elements as `Any?` but can't add elements.
**How it Works:** `<*>` is equivalent to `<out Any?>` for reading and `<in Nothing>` for writing.
**Example:** `fun printList(list: List<*>) { list.forEach { println(it) } }` — works for any List type.
**Interview Insight:** Star projection is for when you need to work with a generic type but don't care about the type parameter. Safer than raw types in Java.

---

## Kotlin Features (Q79–Q82)

### Q79. What are extension functions?
**Definition:** Functions added to an existing class without modifying it or inheriting from it.
**Core Idea:** Syntactic sugar — adds methods to classes you don't own (like `String`, Android classes).
**How it Works:** `fun String.isPalindrome(): Boolean = this == this.reversed()`. Compiled to a static method with the receiver as first parameter.
**Example:** `fun Context.toast(msg: String) = Toast.makeText(this, msg, Toast.LENGTH_SHORT).show()`
**Interview Insight:** Extension functions do NOT modify the class. They're resolved statically (at compile time) based on the reference type, not the actual object type — they cannot be overridden.

---

### Q80. What are extension properties?
**Definition:** Properties added to an existing class via extension syntax. Cannot have a backing field.
**Core Idea:** Like extension functions, but accessed as properties. Must define a getter (and optionally setter).
**How it Works:** `val String.wordCount: Int get() = this.split(" ").size`
**Example:** `val View.isVisible: Boolean get() = visibility == View.VISIBLE` — common Android extension.
**Interview Insight:** Extension properties cannot store state (no backing field). They're just syntactic shortcuts for functions. `view.isVisible = true` is just calling a setter function.

---

### Q81. What are scope functions?
**Definition:** Functions that execute a block of code within the context of an object: `let`, `run`, `apply`, `also`, `with`.
**Core Idea:** Reduce boilerplate when operating on an object. The object is available inside the block.
**How it Works:** Differ in: what `this`/`it` refers to inside, and what they return.
**Example:** `user?.let { showProfile(it) }` — only runs if user is non-null.
**Interview Insight:** Know the quick rule: `apply`/`also` return the object; `let`/`run`/`with` return the lambda result. `apply`/`run`/`with` use `this`; `let`/`also` use `it`.

---

### Q82. Difference between `let`, `run`, `apply`, `also`, and `with`?

| Function | Receiver | Returns       | Use case                           |
|----------|----------|---------------|------------------------------------|
| `let`    | `it`     | Lambda result | Null check, transform object       |
| `run`    | `this`   | Lambda result | Object config + compute result     |
| `apply`  | `this`   | The object    | Object initialization/builder      |
| `also`   | `it`     | The object    | Side effects (logging, validation) |
| `with`   | `this`   | Lambda result | Multiple calls on same object      |

**Example:**
```kotlin
val user = User().apply { name = "Alice"; age = 30 }  // init
user.also { log(it) }  // side effect, returns user
val name = user.let { it.name.uppercase() }  // transform
```
**Interview Insight:** Memory trick: `apply` = "apply these properties to me" (builder). `let` = "let me do something with this value." `also` = "also do this (side effect) while I'm at it."

---

← [03 Serialization & Concurrency](03_java_serialization_concurrency.md) | [05 Kotlin Collections & Coroutines →](05_kotlin_collections_coroutines.md)
