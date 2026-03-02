# Phase 8: Other Kotlin Features

## Navigation
[← Master Index](master_chains.md)

## Questions in This File
- [Q8.1 — Destructuring](#q81--destructuring)
- [Q8.2 — String Templates and Operators](#q82--string-templates-and-operators)
- [Q8.3 — SAM Conversions](#q83--sam-conversions)

---

## Q8.1 — Destructuring

> **Builds on:** [Q2.2 — Data Classes (componentN generation)](02_classes_and_objects.md#q22--data-classes)
> **Connects to:** [Q8.2 — Operators](08_other_kotlin_features.md#q82--string-templates-and-operators)
> **Reference:** [Kotlin Docs — Destructuring declarations](https://kotlinlang.org/docs/destructuring-declarations.html)

### The Concrete Picture

Destructuring = compiler calls `componentN()` functions for you:

```kotlin
val (name, age) = User("Alice", 30)
// Compiler sees this as:
val name = user.component1()   // "Alice"
val age  = user.component2()   // 30
```

Where do `component1()`, `component2()` come from?
- `data class` → auto-generated for every primary constructor property
- `Pair`, `Triple` → built-in
- Any class → you can write `operator fun component1()` manually

`_` = "I don't want this one" (componentN not called at all):
```kotlin
val (_, age) = User("Alice", 30)   // component1() skipped entirely
```

### First Principles: What Is Destructuring?

Destructuring is a way to unpack multiple values from an object into separate variables in a single statement. Instead of:

```kotlin
val pair = Pair("Alice", 30)
val name = pair.first
val age = pair.second
```

You write:
```kotlin
val (name, age) = Pair("Alice", 30)  // unpack in one statement
```

Under the hood, this calls **`componentN()` functions** — the compiler translates each position in the destructuring to a numbered `component` call.

### What `componentN()` Functions Are Called

```kotlin
val (a, b, c) = someObject
// Compiles to:
val a = someObject.component1()
val b = someObject.component2()
val c = someObject.component3()
```

### How `data class` Provides `componentN()` Automatically

For any [`data class`](02_classes_and_objects.md#q22--data-classes), the compiler generates `component1()`, `component2()`, etc. for each **primary constructor property**, in declaration order:

```kotlin
data class User(val name: String, val age: Int, val email: String)

val user = User("Alice", 30, "alice@example.com")
val (name, age, email) = user
// Compiles to:
val name = user.component1()   // → "Alice"
val age = user.component2()    // → 30
val email = user.component3()  // → "alice@example.com"
```

**Properties in the body are NOT component-able:**
```kotlin
data class User(val name: String) {
    val displayName = name.uppercase()  // NOT a componentN() — no destructuring
}
```

### Destructuring in Lambda Parameters

You can destructure in lambda parameters using parentheses:

```kotlin
val pairs = listOf(Pair("Alice", 30), Pair("Bob", 25))

// Without destructuring:
pairs.forEach { pair ->
    println("${pair.first} is ${pair.second}")
}

// WITH destructuring:
pairs.forEach { (name, age) ->
    println("$name is $age")
}

// Map.Entry destructuring:
val map = mapOf("a" to 1, "b" to 2)
map.forEach { (key, value) ->
    println("$key = $value")
}
```

### The `_` Placeholder

`_` discards a destructuring component without creating a variable:

```kotlin
data class Triple(val x: Int, val y: Int, val z: Int)

val (x, _, z) = Triple(1, 2, 3)  // y is discarded — no variable created
// Compiles to:
val x = triple.component1()      // 1
// component2() NOT called at all (compiler omits it)
val z = triple.component3()      // 3
```

**In loops:**
```kotlin
list.forEachIndexed { index, _ ->   // don't care about the value
    println("Item at index $index")
}
```

### Memory Trick

```
DESTRUCTURING = syntactic sugar for componentN() calls.
  Position 1 → component1(), position 2 → component2(), etc.
  Order = primary constructor declaration order.

data class automatically generates componentN() for primary constructor only.
Body properties → no componentN() → can't destructure.

_ = skip. component not called. No variable created. Less bytecode.

IN LAMBDAS:
  .forEach { (key, value) -> }   // destructures each Map.Entry
  .map { (first, second) -> }    // destructures each Pair
```

---

## Q8.2 — String Templates and Operators

> **Builds on:** [Q0.1 — heap allocation (StringBuilder)](00_jvm_mental_model.md#q01--primitives-vs-references)
> **Connects to:** [Q8.3 — SAM Conversions](08_other_kotlin_features.md#q83--sam-conversions) · [Q4.1 — invoke operator and lambdas](04_functions_lambdas_inlining.md#q41--lambda-compilation)

### The Concrete Picture

String templates → StringBuilder, not String.format:

```kotlin
"Hello $name, you are ${name.length} chars!"

// JVM sees:
new StringBuilder()
  .append("Hello ")
  .append(name)
  .append(", you are ")
  .append(name.length())
  .append(" chars!")
  .toString()
```

Operator overloading → function name mapping:
```kotlin
v1 + v2   →  v1.plus(v2)       // a + b = a.plus(b)
v1 * 2.0  →  v1.times(2.0)     // a * b = a.times(b)
-v1       →  v1.unaryMinus()   // -a = a.unaryMinus()
obj[i]    →  obj.get(i)        // a[i] = a.get(i)
obj(arg)  →  obj.invoke(arg)   // a() = a.invoke()
```

### What `"Hello $name"` Compiles To

String templates compile to `StringBuilder` operations — NOT `String.format()`:

```kotlin
val name = "Alice"
val greeting = "Hello $name, you are ${name.length} chars!"
```

**Decompiled Java:**
```java
// Simple var reference ($name):
String greeting = "Hello " + name + ", you are " + name.length() + " chars!";
// Kotlin compiler uses string concatenation (StringBuilder under the hood)
// NOT: String.format("Hello %s, you are %d chars!", name, name.length())
```

For complex expressions (`${expr}`):
```java
StringBuilder sb = new StringBuilder();
sb.append("Hello ");
sb.append(name);
sb.append(", you are ");
sb.append(name.length());
sb.append(" chars!");
String greeting = sb.toString();
```

**Why StringBuilder and not `+`?** `+` on Strings allocates a new String for each operation. `StringBuilder` accumulates in one buffer, then converts to String once.

### Operator Overloading — Function Name Mapping

In Kotlin, operators map to specific function names. Defining that function enables the operator:

| Operator | Function | Example |
|----------|----------|---------|
| `a + b` | `plus(b)` | `operator fun plus(other: T): T` |
| `a - b` | `minus(b)` | |
| `a * b` | `times(b)` | |
| `a / b` | `div(b)` | |
| `a % b` | `rem(b)` | |
| `-a` | `unaryMinus()` | |
| `a++` | `inc()` | |
| `a[i]` | `get(i)` | |
| `a[i] = v` | `set(i, v)` | |
| `a in b` | `b.contains(a)` | |
| `a..b` | `a.rangeTo(b)` | |

```kotlin
data class Vector(val x: Double, val y: Double) {
    operator fun plus(other: Vector) = Vector(x + other.x, y + other.y)
    operator fun times(scalar: Double) = Vector(x * scalar, y * scalar)
    operator fun unaryMinus() = Vector(-x, -y)
}

val v1 = Vector(1.0, 2.0)
val v2 = Vector(3.0, 4.0)
val sum = v1 + v2         // calls v1.plus(v2)    → Vector(4.0, 6.0)
val scaled = v1 * 2.0     // calls v1.times(2.0)  → Vector(2.0, 4.0)
val negated = -v1         // calls v1.unaryMinus() → Vector(-1.0, -2.0)
```

### The `invoke` Operator — Making Objects Callable

`operator fun invoke()` makes an object callable like a [function/lambda](04_functions_lambdas_inlining.md#q41--lambda-compilation) using `()`:

```kotlin
class Validator(val rule: (String) -> Boolean) {
    operator fun invoke(value: String): Boolean = rule(value)
}

val emailValidator = Validator { it.contains("@") && it.contains(".") }

// Now you can call it like a function:
emailValidator("alice@example.com")   // true
emailValidator("notanemail")          // false

// Equivalent to:
emailValidator.invoke("alice@example.com")
```

**Real-world use: Callable objects with state:**
```kotlin
class RateLimiter(val maxCallsPerSecond: Int) {
    private var count = 0
    private var windowStart = System.currentTimeMillis()

    operator fun invoke(): Boolean {
        val now = System.currentTimeMillis()
        if (now - windowStart > 1000) {
            count = 0
            windowStart = now
        }
        return if (count < maxCallsPerSecond) {
            count++
            true  // allowed
        } else {
            false // rate limited
        }
    }
}

val limiter = RateLimiter(10)
if (limiter()) {  // callable like a function!
    makeApiCall()
}
```

### The `rangeTo` Operator and `in 1..10`

`..` creates a range using the `rangeTo` operator:

```kotlin
1..10  // calls 1.rangeTo(10) → IntRange(1, 10)
'a'..'z'  // CharRange

// The `in` operator calls `contains`:
5 in 1..10  // calls (1..10).contains(5) → true
```

```kotlin
// Custom range:
data class Version(val major: Int, val minor: Int) : Comparable<Version> {
    override fun compareTo(other: Version): Int =
        compareValuesBy(this, other, { it.major }, { it.minor })
}

operator fun Version.rangeTo(end: Version) = VersionRange(this, end)

class VersionRange(val start: Version, val end: Version) {
    operator fun contains(v: Version) = v in start..end
}
```

### Memory Trick

```
STRING TEMPLATE = StringBuilder under the hood. NOT String.format.
  "$name" → StringBuilder.append(name). One buffer, efficient.

OPERATOR = function with a specific name + operator modifier.
  Define plus() → you get + operator.
  Define invoke() → your object is callable with ().
  Define get/set() → your object supports [] access.

INVOKE OPERATOR use case: stateful callable object.
  class Validator { operator fun invoke(x: String): Boolean }
  validator("test")   // cleaner than validator.validate("test")
```

---

## Q8.3 — SAM Conversions

> **Builds on:** [Q4.1 — Lambda Compilation (anonymous class)](04_functions_lambdas_inlining.md#q41--lambda-compilation) · [Q4.2 — inline functions](04_functions_lambdas_inlining.md#q42--inline-noinline-crossinline)
> **Connects to:** [Q3.2 — Variance (functional interface covariance)](03_generics_and_variance.md#q32--variance)
> **Reference:** [Kotlin Docs — SAM conversions](https://kotlinlang.org/docs/fun-interfaces.html)

### The Concrete Picture

SAM = "Single Abstract Method." A functional interface. A lambda can pretend to be one:

```kotlin
// Java interface (e.g., Android SDK):
interface OnClickListener { fun onClick(view: View) }

// Kotlin: lambda → auto-converted to OnClickListener
button.setOnClickListener { view -> handleClick(view) }
// JVM: compiler creates anonymous OnClickListener { onClick = { view -> ... } }
```

Kotlin-defined interface: needs `fun interface` keyword:
```kotlin
interface Transformer { fun transform(x: Int): Int }  // regular interface
val t: Transformer = { it * 2 }   // COMPILE ERROR — no SAM conversion

fun interface Transformer { fun transform(x: Int): Int }  // functional interface
val t: Transformer = { it * 2 }   // WORKS!
```

### First Principles: What Is a SAM Interface?

**SAM = Single Abstract Method.** A SAM interface (also called a functional interface) has exactly one abstract method. This design makes it conceptually equivalent to a function type.

```kotlin
// SAM interface — has exactly one abstract method:
interface OnClickListener {
    fun onClick(view: View)
}

// In Java, you'd implement it with an anonymous class:
button.setOnClickListener(new OnClickListener() {
    @Override public void onClick(View v) { handleClick(v); }
});
```

### Kotlin's Automatic Lambda → SAM Conversion

When a function expects a SAM interface, Kotlin automatically converts a lambda to that interface:

```kotlin
// Java SAM interface (in the Android SDK):
// public interface OnClickListener { void onClick(View v); }

// Kotlin automatically converts lambda to OnClickListener:
button.setOnClickListener { view ->
    handleClick(view)
}
// Equivalent to:
button.setOnClickListener(object : View.OnClickListener {
    override fun onClick(v: View) { handleClick(v) }
})
```

The Kotlin compiler generates the [anonymous class](04_functions_lambdas_inlining.md#q41--lambda-compilation) implementation. This SAM conversion works automatically for **Java interfaces** when called from Kotlin.

### `fun interface` — Kotlin's Native Functional Interface

For **Kotlin-defined** interfaces, automatic SAM conversion doesn't work by default. You must explicitly declare it with `fun interface`:

```kotlin
// WITHOUT fun interface — NO automatic SAM conversion:
interface Transformer {
    fun transform(value: Int): Int
}

// This would be a compile error:
val doubler: Transformer = { it * 2 }  // ERROR: no SAM conversion!

// WITH fun interface — SAM conversion enabled:
fun interface Transformer {
    fun transform(value: Int): Int
}

val doubler: Transformer = { it * 2 }  // ✓ Lambda auto-converted
val tripler: Transformer = Transformer { it * 3 }  // ✓ Explicit conversion

// Usage:
doubler.transform(5)  // 10
```

**Why the distinction?** When Kotlin was designed, allowing implicit SAM conversion for Kotlin interfaces could create ambiguity — if a class implements multiple interfaces, which one should a lambda convert to? `fun interface` makes the intent explicit.

### When SAM Conversion Does NOT Work

1. **Kotlin interface without `fun` keyword:**
```kotlin
interface Processor {
    fun process(data: String): String
}
val p: Processor = { it.uppercase() }  // ERROR: needs `fun interface`
```

2. **Interface with more than one abstract method:**
```kotlin
fun interface TwoMethods {
    fun first()
    fun second()    // ERROR: `fun interface` must have exactly ONE abstract method
}
```

3. **Abstract class (not interface):**
```kotlin
abstract class Handler {
    abstract fun handle()
}
val h: Handler = { }  // ERROR: SAM only works for interfaces, not abstract classes
```

4. **When the interface has default methods that conflict:**
```kotlin
// Generally fine, but complex generics or default method interactions can block conversion
```

### Memory Trick

```
SAM = Single Abstract Method interface = can be replaced by a lambda.

JAVA interface → auto SAM conversion in Kotlin (works always).
KOTLIN interface → requires `fun interface` keyword to enable SAM conversion.

WHY the distinction?
  Kotlin interfaces can have multiple implementations per call site.
  `fun interface` makes "this is meant to be a lambda" EXPLICIT.

SAM conversion FAILS when:
  - More than one abstract method (needs ALL methods, lambda only gives one)
  - Abstract class (not interface)
  - Regular Kotlin interface (not `fun interface`)
```

---

## Master Summary: Other Kotlin Features in 4 Points

```
┌────────────────────────────────────────────────────────────────────────┐
│  1. Destructuring calls componentN() functions in order.              │
│     data class auto-generates them for primary constructor props.     │
│     `_` discards components without creating variables.               │
│                                                                        │
│  2. String templates compile to StringBuilder, not String.format().   │
│     Operator overloading maps operators to function names (plus,      │
│     minus, invoke, rangeTo, etc.).                                    │
│                                                                        │
│  3. `invoke` operator makes objects callable with () syntax.          │
│     Useful for callable objects with internal state.                  │
│                                                                        │
│  4. SAM conversion: Java interfaces → automatic. Kotlin interfaces    │
│     require `fun interface` keyword. Only works for single-abstract- │
│     method interfaces.                                                │
└────────────────────────────────────────────────────────────────────────┘
```

---

*← [Phase 7 — Collections & Sequences](07_collections_and_sequences.md) | [Phase 9 — Coroutines Mechanics →](09_coroutines_execution_mechanics.md)*
