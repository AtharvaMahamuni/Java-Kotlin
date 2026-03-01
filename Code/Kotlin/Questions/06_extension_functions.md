# Phase 6: Extension Functions

## Navigation
| Phase | File |
|-------|------|
| 5 — Properties & Delegation | [05_properties_and_delegation.md](05_properties_and_delegation.md) |
| **6 — Extension Functions** | ← You are here |
| 7 — Collections & Sequences | [07_collections_and_sequences.md](07_collections_and_sequences.md) |

---

## Q6.1 — Compilation and Dispatch

> **Reference:** [Kotlin Docs — Extension Functions](https://kotlinlang.org/docs/extensions.html)

### First Principles: How Can You Add Methods to a Class You Don't Own?

In Java, if you want extra behavior on `String`, you must:
1. Subclass it (impossible — `String` is `final`)
2. Create a utility class with static methods: `StringUtils.capitalize(str)`

Kotlin extension functions look like member methods but are **syntactic sugar** for static calls. The compiler translates them so you get clean call syntax while the JVM sees a plain static method.

### What Does `fun String.greet()` Look Like in Bytecode?

```kotlin
// In file: StringExtensions.kt (package com.example)
fun String.greet(): String = "Hello, $this!"
```

**Decompiled Java equivalent:**
```java
// The extension becomes a STATIC method in a file-level class:
public final class StringExtensionsKt {
    public static String greet(String $receiver) {  // receiver is a parameter!
        return "Hello, " + $receiver + "!";
    }
}
```

**The receiver is NOT `this` in the JVM sense — it's the FIRST PARAMETER.**

**Call site:**
```kotlin
"World".greet()
```

```bytecode
LDC "World"                                ; push receiver
INVOKESTATIC StringExtensionsKt.greet (Ljava/lang/String;)Ljava/lang/String;
; Static call! Not a virtual dispatch on String.
```

```
Kotlin source view:            JVM bytecode view:
┌─────────────────────┐       ┌─────────────────────────────────────┐
│ "World".greet()     │  ──►  │  StringExtensionsKt.greet("World")  │
│                     │       │  INVOKESTATIC (no vtable!)           │
└─────────────────────┘       └─────────────────────────────────────┘
```

### Why Extension Functions Cannot Override Member Functions

**Dispatch is decided at compile time based on the declared type — not at runtime based on the actual type.**

```kotlin
open class Animal
class Dog : Animal()

fun Animal.speak() = "Animal speaks"
fun Dog.speak() = "Dog speaks"    // extension on Dog, not override!

fun makeSpeak(animal: Animal) {
    println(animal.speak())  // always calls Animal.speak()!
}

makeSpeak(Dog())  // prints: "Animal speaks" — NOT "Dog speaks"!
```

**Why?** `animal.speak()` compiles to `AnimalExtKt.speak(animal)` — a **static call** where the type is `Animal`. The JVM never does a vtable lookup. The concrete type of the argument at runtime doesn't matter.

**Compare with a member function:**
```kotlin
open class Animal {
    open fun speak() = "Animal speaks"
}
class Dog : Animal() {
    override fun speak() = "Dog speaks"
}

fun makeSpeak(animal: Animal) {
    println(animal.speak())  // calls Dog.speak() if passed a Dog!
}
makeSpeak(Dog())  // "Dog speaks" — virtual dispatch works
```

The key difference: **member functions use `INVOKEVIRTUAL` (runtime type dispatch); extension functions use `INVOKESTATIC` (compile-time type dispatch).**

### What Happens When a Member and Extension Have the Same Name?

```kotlin
class Printer {
    fun print() = println("Member print")
}

fun Printer.print() = println("Extension print")

val p = Printer()
p.print()  // "Member print" — member ALWAYS wins over extension
```

**Rule:** If a member function and an extension function have the same signature, the **member function always takes priority**. The extension is never called.

---

## Q6.2 — Extension Functions as API Design

### When Do Extension Functions Make Sense?

Use extension functions when:
1. **You don't own the class** (third-party class, standard library class)
2. **The functionality is domain-specific** and shouldn't pollute the core class
3. **The class is final** and can't be subclassed

```kotlin
// You don't own RecyclerView — can't add methods to it
// But you can extend it:
fun RecyclerView.setup(adapter: RecyclerView.Adapter<*>, layoutManager: LayoutManager) {
    this.adapter = adapter
    this.layoutManager = layoutManager
    setHasFixedSize(true)
}

// Usage:
recyclerView.setup(myAdapter, LinearLayoutManager(context))
```

vs. adding to the class itself:
```kotlin
// Would only make sense if RecyclerView were yours:
class RecyclerView {
    fun setup(...) { }  // belongs in the class — has access to private state
}
```

### `RecyclerView` Extension with `apply` for Method Chaining

```kotlin
fun RecyclerView.onScrolledToEnd(action: () -> Unit) {
    addOnScrollListener(object : RecyclerView.OnScrollListener() {
        override fun onScrolled(recyclerView: RecyclerView, dx: Int, dy: Int) {
            val layoutManager = layoutManager as? LinearLayoutManager ?: return
            val last = layoutManager.findLastCompletelyVisibleItemPosition()
            val total = layoutManager.itemCount - 1
            if (last >= total) action()
        }
    })
}

// With apply for fluent chaining (← Q4.4):
recyclerView.apply {
    adapter = myAdapter
    layoutManager = LinearLayoutManager(context)
    onScrolledToEnd { loadNextPage() }
    setHasFixedSize(true)
}
```

**Why this avoids subclassing:**
- You get all the behavior without creating `class PaginatingRecyclerView : RecyclerView()`
- No vtable changes, no inheritance hierarchy to maintain
- Extensions are addable/removable without changing the class hierarchy

### Null-Safety Advantage on Nullable Receivers

```kotlin
// Extension on nullable String?:
fun String?.orEmpty(): String = this ?: ""
fun String?.isNullOrBlank(): Boolean = this == null || this.isBlank()

// Usage — call on nullable without null check:
val name: String? = getName()
println(name.orEmpty())       // "Bob" or "" — no NPE, no ?. needed
println(name.isNullOrBlank()) // true/false
```

**Compiled to:**
```java
public static String orEmpty(String $receiver) {
    return $receiver != null ? $receiver : "";
}
```

The null check happens **inside** the extension function, so calling it on `null` is safe.

---

## Q6.3 — Extension Properties

> **Reference:** [Kotlin Docs — Extension Properties](https://kotlinlang.org/docs/extensions.html#extension-properties)

### The Backing Field Restriction

Extension properties **cannot have backing fields**. This is because an extension is compiled to a static method — there's no object to store extra fields on.

```kotlin
// COMPILE ERROR — backing field not allowed on extension:
var String.tag: String = ""    // ERROR: Extension property cannot have backing field
```

**Why?** An extension property is compiled to getter/setter methods. There's no way to add an extra field to the `String` class (which lives in the JVM core). You can't inject new state into an existing class.

```kotlin
// Extension property MUST compute from the receiver or use external storage:

// OK: Computed from receiver (read-only):
val String.wordCount: Int
    get() = this.split(" ").count { it.isNotEmpty() }

// OK: Backed by a Map (external storage):
private val viewTags = WeakHashMap<View, String>()
var View.customTag: String?
    get() = viewTags[this]
    set(value) { viewTags[this] = value }
```

### How Extension Property Compiles vs Member Property

**Member property:**
```kotlin
class User {
    val displayName: String get() = name.uppercase()
    // Compiled: class User { String getDisplayName() { return name.uppercase(); } }
}
```

**Extension property:**
```kotlin
val User.displayName: String get() = name.uppercase()
// Compiled: static String getDisplayName(User $receiver) { return $receiver.name.uppercase(); }
```

The only difference in bytecode: the receiver is `$receiver` parameter (static) vs `this` (instance method).

### Extension Property vs Extension Function — Semantic Difference

Use an **extension property** when the concept is logically a property (has no side effects, computationally cheap, represents a characteristic of the object):

```kotlin
// PROPERTY: "count of words" is a characteristic
val String.wordCount: Int get() = split(" ").size

// FUNCTION: "parse into User" involves transformation, may throw
fun String.parseAsUser(): User { ... }  // action/transformation → function
```

**Rules of thumb:**
- Properties represent **characteristics** (what the object IS)
- Functions represent **actions** (what the object DOES)
- If it's expensive, prefer a function — properties imply O(1) cheap access

---

## Master Summary: Extension Functions in 4 Points

```
┌──────────────────────────────────────────────────────────────────────┐
│  1. Extension functions compile to STATIC methods on the JVM.        │
│     The receiver is the FIRST PARAMETER, not `this`.                 │
│     Call: "hello".greet() → StringExtKt.greet("hello")              │
│                                                                       │
│  2. Extensions CANNOT override members — dispatch is compile-time    │
│     (INVOKESTATIC), not runtime (INVOKEVIRTUAL).                     │
│     Member functions always win over extensions with same name.      │
│                                                                       │
│  3. Extensions on nullable receivers allow safe null handling        │
│     without ?. at the call site.                                     │
│                                                                       │
│  4. Extension properties cannot have backing fields — they can only  │
│     compute values from the receiver or use external storage.        │
└──────────────────────────────────────────────────────────────────────┘
```

---

*← [Phase 5 — Properties & Delegation](05_properties_and_delegation.md) | [Phase 7 — Collections & Sequences →](07_collections_and_sequences.md)*
