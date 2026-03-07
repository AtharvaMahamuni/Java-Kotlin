# Phase 6 — Extension Functions

> Extension functions look like member methods. They are static methods with the receiver as the first parameter. The illusion is perfect at the call site — and completely transparent at the bytecode level.

## Navigation

[← Phase 5 — Properties and Delegation](05_properties_and_delegation.md) | [→ Phase 7 — Collections and Sequences](07_collections_and_sequences.md)

## Questions in This File

- [Q6.1 — Compilation and Dispatch](#q61--compilation-and-dispatch)
- [Q6.2 — Resolution Rules and Precedence](#q62--resolution-rules-and-precedence)
- [Q6.3 — Extension Functions as API Design](#q63--extension-functions-as-api-design)
- [Q6.4 — Extension Properties](#q64--extension-properties)
- [Q6.5 — Extension Lambdas and DSLs](#q65--extension-lambdas-and-dsls)

---

# Q6.1 — Compilation and Dispatch

> **Builds on:** [Q0.4 (INVOKESTATIC vs INVOKEVIRTUAL)](phase0_jvm_mental_model_v3.md#q04--the-jvm-call-stack)
> **Connects to:** [Q6.2 (member beats extension)](#q62--resolution-rules-and-precedence) · [Q3.4 (reified extension functions)](03_generics_and_variance.md#q34--reified-type-parameters)

---

## The Core Transformation

```kotlin
fun String.greet(): String = "Hello, $this!"
"World".greet()
```

```
Kotlin view:                        JVM view:
"World".greet()         ──►         StringExtensionsKt.greet("World")
                                    INVOKESTATIC — not virtual!
                                    receiver = first parameter
```

The receiver (`"World"`) is NOT the JVM `this`. Inside the generated static method it is a regular parameter named `$this$greet`. The JVM never does a vtable lookup. Dispatch is decided entirely at **compile time** based on the declared type.

---

## Decompiled Bytecode — and the `Kt` Suffix

```kotlin
// File: StringExtensions.kt, package com.example
fun String.greet(): String = "Hello, $this!"
```

```java
// Decompiled — compiler creates a class named after the file:
public final class StringExtensionsKt {            // filename + "Kt" suffix
    public static String greet(String $this$greet) {
        return "Hello, " + $this$greet + "!";
    }
}
```

**Why `Kt` suffix?** The class name must not clash with any class in the same package. If you have a `StringExtensions` class, the compiler would collide with it. The `Kt` suffix makes the generated class uniquely identifiable and importable from Java.

```
Call site:
  "World".greet()
     ↓
  LDC "World"
  INVOKESTATIC StringExtensionsKt.greet (Ljava/lang/String;)Ljava/lang/String;
```

---

## Extensions Cannot Override — Dispatch Is Compile-Time

```kotlin
open class Animal
class Dog : Animal()

fun Animal.speak() = "Animal speaks"
fun Dog.speak() = "Dog speaks"     // different static method, NOT an override

fun makeSpeak(animal: Animal) {
    println(animal.speak())        // declared type = Animal → always Animal.speak
}

makeSpeak(Dog())  // prints: "Animal speaks" — NOT "Dog speaks"
```

**Why:** `animal.speak()` compiles to `AnimalExtKt.speak(animal)` — the JVM argument type is `Animal`. The JVM never inspects the runtime type.

**Compare with a member function:**

```kotlin
open class Animal { open fun speak() = "Animal speaks" }
class Dog : Animal() { override fun speak() = "Dog speaks" }

makeSpeak(Dog())  // "Dog speaks" — INVOKEVIRTUAL → vtable → runtime type wins
```

| | Extension function | Member function |
|---|---|---|
| JVM instruction | `INVOKESTATIC` | `INVOKEVIRTUAL` |
| Dispatch | Compile time (declared type) | Runtime (actual type) |
| Overridable? | No | Yes |

---

## Member Always Beats Extension

When a member and extension have the same name and signature, the **member always wins** — unconditionally:

```kotlin
class Printer {
    fun print() = println("Member print")
}
fun Printer.print() = println("Extension print")

Printer().print()  // "Member print" — extension is never called
```

---

## Extensions Defined Inside a Class — `this` Scoping

When an extension is defined *inside* a class body, two `this` references exist — the class instance and the extension receiver:

```kotlin
class Formatter {
    val prefix = "LOG"

    fun String.formatted(): String {
        // this@formatted = the String (extension receiver)
        // this@Formatter = the Formatter instance
        return "${this@Formatter.prefix}: $this"
    }

    fun format(s: String) = s.formatted()  // can call here — in scope
}

val f = Formatter()
// "hello".formatted()  // COMPILE ERROR outside Formatter — not in scope
```

Extensions defined inside a class are only available in that class's scope. This is how scoped APIs are built (see companion object extensions in Q6.2).

---

## Memory Trick

```
EXTENSION = static method, receiver = first parameter.

INVOKESTATIC = compile-time dispatch (declared type wins always).
INVOKEVIRTUAL = runtime dispatch (actual type, vtable lookup).

Extensions: no polymorphism, no override, no vtable.
Member always beats extension with same signature.

Filename + "Kt" suffix = generated class name.
  Reason: avoids collision with user-defined classes in the same package.

Extension inside class:
  Two `this` references: this@ExtReceiver and this@EnclosingClass
  Extension only visible within that class's scope.
```

---

## Self-Test

1. What JVM instruction does `"World".greet()` generate?
2. What is the receiver inside the JVM? Is it `this`?
3. Why does `fun Dog.speak()` print "Animal speaks" when called through an `Animal` reference?
4. What happens when a member and extension have identical signatures?
5. Why does the compiler add `Kt` to the generated class name?
6. If you define `fun String.shout()` inside a class, where can it be called?

---

# Q6.2 — Resolution Rules and Precedence

> **Builds on:** [Q6.1 (static dispatch)](#q61--compilation-and-dispatch)
> **Connects to:** [Q6.3 (API design patterns)](#q63--extension-functions-as-api-design)

---

## Correct Resolution Order

When Kotlin resolves a function call, it checks in this priority order:

```
1. Member function of the class          (always wins — no contest)
2. Extension in the current local scope  (current function, block, or file)
3. Explicitly imported extension         (import com.example.shout)
4. Star-imported extension               (import com.example.*)

Important: explicit imports beat star imports.
```

---

## Scope: Where Extensions Are Visible

Unlike member functions (always visible via `obj.method()`), extensions only exist **where imported or declared**:

```kotlin
// File: Extensions.kt
fun String.shout() = uppercase() + "!"

// File: Main.kt
import com.example.Extensions.shout   // explicit import ← beats star import

"hello".shout()  // OK — imported
```

Extensions defined in the **same package** as the call site don't need an import — they're visible by default, just like top-level functions.

---

## Extension in Companion Object — Scoped APIs

Extensions defined in a companion object are only callable **inside that companion's scope**:

```kotlin
class HtmlDsl {
    companion object {
        fun String.escaped() = replace("&", "&amp;").replace("<", "&lt;")
    }

    fun render(content: String) = with(Companion) {
        content.escaped()   // OK: in companion scope
    }
}

// "hello".escaped()  // COMPILE ERROR outside HtmlDsl — not in scope
```

This is how you build scoped extensions — API features available only within a specific context.

---

## Generic Extension Functions

Extensions can declare their own type parameters:

```kotlin
// Extension on any List<T> where T is Comparable
fun <T : Comparable<T>> List<T>.second(): T? = if (size >= 2) this[1] else null

listOf(3, 1, 4).second()   // 1
listOf("a", "b").second()  // "b"

// Generic swap — works on any MutableList<T>
fun <T> MutableList<T>.swap(i: Int, j: Int) {
    val tmp = this[i]; this[i] = this[j]; this[j] = tmp
}
```

The type parameter belongs to the function, not the class. This is exactly how stdlib `map`, `filter`, `sortedBy` are implemented.

---

## Memory Trick

```
RESOLUTION ORDER (highest → lowest priority):
  1. Member function       (always wins, needs no import)
  2. Local extension       (current scope/file)
  3. Explicit import       (import com.example.shout)
  4. Star import           (import com.example.*)

Explicit beats star — not the other way around.
Same-package top-level extensions: visible without import.

COMPANION EXTENSION:
  Defined in companion → only callable from within that companion's scope.
  Enables scoped/context-restricted APIs.

GENERIC EXTENSION:
  fun <T> List<T>.method() — type param on the function, not the class.
  This is how all stdlib collection operations are written.
```

---

## Self-Test

1. If a class has `fun foo()` and there's an imported extension `fun T.foo()`, which wins?
2. Does an extension from a star import beat an explicit import? Which order is correct?
3. Do extensions in the same package need an import?
4. Can you define an extension inside a companion object? Where can it be called?
5. Write `fun <T> List<T>.second(): T?`.

---

# Q6.3 — Extension Functions as API Design

> **Builds on:** [Q6.1 (static dispatch, no polymorphism)](#q61--compilation-and-dispatch)
> **Connects to:** [Q6.5 (DSL pattern)](#q65--extension-lambdas-and-dsls)

---

## Three Patterns Where Extensions Excel

**1. You don't own the class:**

```kotlin
// String is final — can't subclass. Can't modify stdlib.
fun String.toSlug() = lowercase().replace(" ", "-").replace(Regex("[^a-z0-9-]"), "")
"Hello World!".toSlug()  // "hello-world"
```

**2. Domain logic outside the core type:**

```kotlin
// RecyclerView.setup() is YOUR domain concept — it has no business being in RecyclerView itself
fun RecyclerView.setup(adapter: RecyclerView.Adapter<*>, columns: Int = 1) {
    this.adapter = adapter
    layoutManager = GridLayoutManager(context, columns)
    setHasFixedSize(true)
}
recyclerView.setup(myAdapter, columns = 2)
```

**3. Nullable receiver — null handled inside:**

```kotlin
// Extension on nullable receiver — no ?. required at call site
fun String?.orEmpty(): String = this ?: ""
fun String?.isNullOrBlank(): Boolean = this == null || this.isBlank()

val name: String? = getName()
println(name.orEmpty())        // safe — no ?.  needed
```

```java
// Why null-receiver extensions are safe — decompiled:
public static String orEmpty(String $receiver) {
    return $receiver != null ? $receiver : "";
}
// Called as: StringExtKt.orEmpty(name)
// null is passed as the argument — no NullPointerException, handled inside
```

---

## Why Extensions Cannot Access Private Members — From First Principles

```kotlin
class BankAccount(private val balance: Double) {
    // CORRECT: member function — has access to private fields
    fun canAfford(amount: Double) = balance >= amount
}

// ERROR: extension cannot access private balance
fun BankAccount.canAfford(amount: Double) = balance >= amount  // COMPILE ERROR
```

The reason is the compilation model:

```
Member function:                 Extension function:
  Generated as instance method     Generated as static method
  in BankAccount's class file       in BankAccountExtKt class file

BankAccountExtKt is a            BankAccountExtKt is a completely
completely separate class         different class from BankAccount

Java visibility rules:
  private members of BankAccount  → accessible to BankAccount only
  BankAccountExtKt                → external class, no access to private fields
```

An extension is physically in a different class at the bytecode level. Java's private visibility prevents it from reaching into `BankAccount`'s private fields, just like any other external class.

---

## When NOT to Use Extensions

```kotlin
// Don't use when you need private state:
fun BankAccount.canAfford(amount: Double) = balance >= amount  // can't access balance

// Don't use when you need polymorphism:
fun Animal.sound() = "..."   // can't be overridden by Dog, Cat, etc.
// Use a member function with open/override instead

// Don't use when behaviour belongs in the class:
// If 80% of callers would use this method, it belongs as a member, not an extension
```

---

## Memory Trick

```
USE EXTENSIONS WHEN:
  ✓ Don't own the class (final, 3rd party, stdlib)
  ✓ Domain-specific logic that doesn't belong in the class
  ✓ Nullable receiver — handle null inside the extension
  ✓ Adding behaviour without subclassing

DON'T USE WHEN:
  ✗ Need private member access (extension is in a different class → no access)
  ✗ Need polymorphism (extensions are INVOKESTATIC → no override)
  ✗ The behaviour fundamentally belongs in the class

WHY NO PRIVATE ACCESS (first principles):
  Extension compiles to static method in a SEPARATE generated class.
  Java private = accessible to the declaring class only.
  The generated class is external → no access.

Nullable receiver:
  null passed as first param to static method → handled inside → no NPE at call site.
```

---

## Self-Test

1. Can an extension function access private members? Explain from the bytecode level why not.
2. Why is `fun String?.orEmpty()` safe to call on a `null` reference?
3. When would you use an extension vs subclassing vs a member function?
4. Write a `RecyclerView.setupWith(adapter, columns)` extension.

---

# Q6.4 — Extension Properties

> **Builds on:** [Q6.1 (static dispatch)](#q61--compilation-and-dispatch) · [Q0.1 (heap — backing fields live on the heap)](phase0_jvm_mental_model_v3.md#q01--primitives-vs-references-the-two-worlds)
> **Connects to:** [Q5.3 (external storage via delegates)](05_properties_and_delegation.md#q53--property-delegates)

---

## The Core Rule: No Backing Field

An extension is a static method in a separate class file. There is no `this` object to attach a new field to. Extension properties can only **compute** from the receiver or use **external storage**.

```kotlin
// ✓ Computed from receiver — no storage needed:
val String.wordCount: Int
    get() = split(" ").count { it.isNotEmpty() }

// ✓ Read/write computed from receiver state:
var View.isVisible: Boolean
    get() = visibility == View.VISIBLE
    set(value) { visibility = if (value) View.VISIBLE else View.GONE }

// ✗ COMPILE ERROR — no backing field possible:
var String.tag: String = ""   // ERROR: Extension property cannot have an initializer
```

---

## Decompiled: Extension Property vs Member Property

```kotlin
// Member property:
class User(val name: String) {
    val displayName: String get() = name.uppercase()
}
// → String getDisplayName() { return this.name.toUpperCase(); }  ← instance method

// Extension property:
val User.displayName: String get() = name.uppercase()
// → static String getDisplayName(User $this$displayName) { return $this.name.toUpperCase(); }
```

The only JVM difference: parameter vs `this`.

---

## External Storage — Adding State to Classes You Don't Own

When you need mutable state on an existing class (like `View`), use an external map:

```kotlin
// WeakHashMap: key = View instance, value = String tag
private val viewTags = WeakHashMap<View, String>()

var View.customTag: String?
    get() = viewTags[this]
    set(value) {
        if (value != null) viewTags[this] = value
        else viewTags.remove(this)
    }

myButton.customTag = "submit-button"
println(myButton.customTag)  // "submit-button"
```

**Why `WeakHashMap` and not `HashMap`:**

```
HashMap<View, String>:
  Map holds STRONG reference to View as key
  View cannot be GC'd while it's a key in the map
  → View is destroyed (Activity finishes) but still referenced → memory leak

WeakHashMap<View, String>:
  Map holds WEAK reference to View as key
  Weak ref does NOT count for GC — View CAN be collected
  When View is GC'd → entry automatically removed from map
  → No memory leak ✓
```

---

## Property vs Function — Semantic Rule

```kotlin
// Property: characteristic of the object — O(1), no side effects
val String.wordCount: Int get() = split(" ").size         // characteristic
val View.isVisible: Boolean get() = visibility == View.VISIBLE

// Function: action, potentially expensive, or has side effects
fun String.parseAsUser(): User { ... }                    // action, parsing cost
fun ImageView.loadImage(url: String) { Glide.with(this).load(url).into(this) }  // side effects
```

**Rule:** If the answer is "what is this object like?" → property. If the answer is "do something with this object" → function.

---

## Memory Trick

```
EXTENSION PROPERTY = computed getter/setter. NO backing field. EVER.
  Reason: extension is a static method in a different class — no object to put a field on.

CAN:
  val String.wordCount get() = split(" ").size   ← computed
  var View.isVisible get/set via visibility      ← computed
  var View.tag via WeakHashMap                   ← external storage

CANNOT:
  var String.tag = ""    ← COMPILE ERROR: no field possible

WeakHashMap pattern:
  Strong map → holds View as key → prevents GC → leak
  Weak map   → View can be GC'd → entry auto-removed → no leak

property vs function semantic rule:
  Property: characteristic, O(1), no side effects ("what is it?")
  Function: action, may be slow, may have side effects ("do something")
```

---

## Self-Test

1. Why can't extension properties have backing fields? Explain from the bytecode level.
2. What is the JVM difference between an extension property getter and a member property getter?
3. Why use `WeakHashMap` for external state storage? What happens with a regular `HashMap`?
4. When would you choose an extension property vs an extension function?

---

# Q6.5 — Extension Lambdas and DSLs

> **Builds on:** [Q6.1 (extension dispatch)](#q61--compilation-and-dispatch) · [Q4.3 (inline functions)](04_functions_lambdas_inlining.md#q43--inline-noinline-crossinline)
> **Connects to:** [Q4.5 (scope functions use this pattern)](04_functions_lambdas_inlining.md#q45--scope-functions)

---

## Function Type with Receiver — The Mechanism

A **function type with receiver** is a lambda where `this` is set to a specific object when the block runs:

```kotlin
// Regular lambda: this = enclosing class
val action: () -> Unit = { println("hello") }

// Lambda with receiver: this = the String
val greet: String.() -> String = { "Hello, $this!" }

"World".greet()        // "Hello, World!" — this = "World" inside the block
greet("World")         // equivalent — receiver is first argument
```

The type `String.() -> String` means: "a lambda that, when invoked, has `this` set to a `String` and returns a `String`."

At the JVM level: same as an extension function — static method with String as first parameter.

---

## Building a DSL with Extension Lambdas

This is how all Kotlin builder APIs work: `apply`, `buildString`, `AlertDialog`, HTML builders.

```kotlin
class HtmlBuilder {
    private val parts = mutableListOf<String>()
    fun h1(text: String) { parts.add("<h1>$text</h1>") }
    fun p(text: String)  { parts.add("<p>$text</p>") }
    fun build() = parts.joinToString("\n")
}

fun html(block: HtmlBuilder.() -> Unit): String {
    val builder = HtmlBuilder()
    builder.block()       // runs block with builder as `this`
    return builder.build()
}

val page = html {
    h1("Welcome")         // this = HtmlBuilder, calls builder.h1()
    p("Hello world")
}
```

```
html { ... }:
  1. Create HtmlBuilder
  2. Call block with HtmlBuilder as `this`
  3. Inside block: h1() means builder.h1()
  4. Return builder.build()
```

---

## `apply` Is Exactly This Pattern

```kotlin
public inline fun <T> T.apply(block: T.() -> Unit): T {
    block()     // calls block with this = the receiver T
    return this
}

TextView(context).apply {
    text = "Hello"    // this = TextView
    textSize = 16f    // this.textSize = 16f
}
```

`block` is a `TextView.() -> Unit`. When `block()` runs, `this` inside is the `TextView`. That's the entire mechanism.

---

## Type-Safe Nested Builders

Extension lambdas enable deeply nested, type-safe builders where each nesting level restricts what methods are available:

```kotlin
class Row { val cells = mutableListOf<String>() }
class Table { val rows = mutableListOf<Row>() }

fun table(block: Table.() -> Unit): Table = Table().also { it.block() }
fun Table.row(block: Row.() -> Unit) = Row().also { it.block(); rows.add(it) }
fun Row.cell(text: String) { cells.add(text) }

table {
    row {
        cell("Name")   // this = Row — only Row methods available
        cell("Age")
    }
}
```

At each nesting level, `this` changes — the compiler knows which `this` is in scope and enforces it.

---

## `@DslMarker` — Preventing Wrong-Scope Calls

Without `@DslMarker`, you can accidentally call an outer DSL method from inside an inner block:

```kotlin
// WITHOUT @DslMarker — this bug compiles and runs silently:
table {
    row {
        row {             // BUG: adds a row inside a Row — wrong!
            cell("Alice") // but this is Table.row, called from Row's context
        }
    }
}
```

The problem: inside `row { }`, both `Row`'s methods AND `Table`'s methods (from outer `this`) are in scope. You can accidentally call `Table.row` from inside a `Row` block.

**Fix: `@DslMarker` annotation:**

```kotlin
@DslMarker
annotation class HtmlDsl

@HtmlDsl
class Table { ... }

@HtmlDsl
class Row { ... }

table {
    row {
        row { ... }   // COMPILE ERROR: can't call outer-scope row here
                      // @DslMarker: only the nearest @HtmlDsl scope's methods are accessible
    }
}
```

`@DslMarker` creates a family of DSL annotations. The rule: within a lambda with receiver, you can only implicitly call methods from the **nearest** class that has the same `@DslMarker` annotation. Outer scopes are blocked unless accessed explicitly via `this@Table.row { }`.

---

## `buildString` — Standard Library Example

```kotlin
val result = buildString {         // this = StringBuilder
    append("Hello")
    append(", ")
    appendLine("World!")
}

// Stdlib implementation:
public inline fun buildString(builderAction: StringBuilder.() -> Unit): String =
    StringBuilder().apply(builderAction).toString()
```

---

## Memory Trick

```
FUNCTION TYPE WITH RECEIVER: String.() -> Unit
  = lambda where `this` = String inside the block
  JVM: same as extension function — static method, String as first param

DSL PATTERN:
  1. Create context/builder class
  2. Entry function: fun html(block: HtmlBuilder.() -> Unit)
  3. Create instance, call block() → this = instance inside
  4. Return result

SCOPE FUNCTIONS use this exact pattern:
  apply { }  → T.() → Unit  (this = T, returns T)
  run   { }  → T.() → R     (this = T, returns R)
  with(t){ } → T.() → R     (this = T, non-extension, returns R)

@DslMarker:
  Problem: outer DSL methods leak into inner scopes → silent bugs
  Fix: @DslMarker on annotation class, annotation on DSL classes
  Effect: only nearest @DslMarker-annotated scope's methods available implicitly
  Access outer explicitly: this@Table.row { } still works

Extension lambda = type-safe replacement for Java Builder pattern.
```

---

## Self-Test

1. What is `String.() -> Unit`? How does `this` inside the block differ from a regular lambda?
2. How does `apply` use function types with receivers? Show the signature.
3. Build a `buildList { add(...) }` function using a `MutableList<T>` receiver lambda.
4. What is the type-safety bug that `@DslMarker` prevents? Show an example of the bug.
5. How does `@DslMarker` fix it? What rule does it enforce?

---

# Master Summary: Phase 6

> Extensions are static methods in disguise. The JVM never does a vtable lookup for them. That's their limitation (no polymorphism) and their power (no overhead, no subclassing needed).

**1. Compilation** (Q6.1)
Extension = static method, receiver = first parameter, `FILENAMEKt` class. `INVOKESTATIC` at call site. Compile-time dispatch — declared type always wins. Members always beat extensions. Extensions inside a class create scoped APIs with two `this` references.

**2. Resolution Rules** (Q6.2)
Member > local extension > explicit import > star import. Extensions in same package need no import. Companion object extensions are scoped to that companion.

**3. API Design** (Q6.3)
Use for: classes you don't own, domain logic, nullable receivers. Can't access private members — extension is a different class at bytecode level; Java private blocks access. Can't override — `INVOKESTATIC` has no vtable.

**4. Extension Properties** (Q6.4)
No backing field — extension has no object to attach a field to. Only computed getters/setters or external `WeakHashMap` storage. `WeakHashMap` prevents memory leaks (weak keys allow GC). Property = characteristic; function = action.

**5. Extension Lambdas + DSLs** (Q6.5)
`T.() -> R` = lambda with `this = T`. Enables builder DSLs. `@DslMarker` prevents outer-scope method leakage in nested builders. All scope functions (`apply`, `run`, `with`) use this exact mechanism.

---

## Master Chain: Extensions

```
Extension function = static method (INVOKESTATIC)
      │
      ├── receiver = first parameter ($this$methodName)
      ├── dispatch: compile-time (declared type always wins)
      ├── members always beat extensions (same signature)
      ├── generated class = FILENAMEKt (avoids collision with user classes)
      │
      ├── resolution order:
      │     member > local > explicit import > star import
      │     same package → no import needed
      │
      ├── no private access:
      │     extension is in a different class → Java private blocks it
      │
      ├── extension property = static getter/setter, NO backing field
      │     external state → WeakHashMap (weak keys = no GC leak)
      │
      ├── nullable receiver:
      │     null passed as first arg to static method → safe, handled inside
      │
      └── function type with receiver: T.() -> R
                │
                ├── this = T inside the block
                ├── apply, run, with, buildString all use this
                ├── DSL: entry fn creates context, calls block with it as this
                └── @DslMarker: restricts implicit this to nearest annotated scope
```

---

*← [Phase 5 — Properties and Delegation](05_properties_and_delegation.md) | [Phase 7 — Collections and Sequences →](07_collections_and_sequences.md)*