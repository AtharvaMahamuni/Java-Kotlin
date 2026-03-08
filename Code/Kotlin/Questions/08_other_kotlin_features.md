# Phase 8: Other Kotlin Features

## Navigation
[← Phase 7 — Collections and Sequences](07_collections_and_sequences.md) | [→ Phase 9 — Coroutines: Execution Mechanics](09_coroutines_execution_mechanics.md)

## Questions in This File
- [Q8.1 — Destructuring](#q81--destructuring)
- [Q8.2 — String Templates and Operators](#q82--string-templates-and-operators)
- [Q8.3 — SAM Conversions](#q83--sam-conversions)

---

## Q8.1 — Destructuring

> **Builds on:** [Q2.2 — Data Classes](02_classes_and_objects.md#q22--data-classes) · [Q4.1 — Lambda parameters](04_functions_lambdas_inlining.md#q41--lambda-compilation)
> **Connects to:** [Q8.2 — Operators](#q82--string-templates-and-operators) · [Q7.1 — Collection iteration patterns](07_collections_and_sequences.md#q71--kotlins-collection-hierarchy)

---

### The Core Mechanism — `componentN()` Calls

Destructuring is syntactic sugar. The compiler translates each binding position into a numbered `componentN()` call, in order:

```kotlin
val user = User("Alice", 30, "alice@ex.com")
val (name, age, email) = user

// Compiles EXACTLY to:
val name  = user.component1()   // "Alice"
val age   = user.component2()   // 30
val email = user.component3()   // "alice@ex.com"
```

**Decompiled Java — what the JVM executes:**
```java
User user = new User("Alice", 30, "alice@ex.com");
String name  = user.component1();
int    age   = user.component2();   // unboxed — int, not Integer
String email = user.component3();
```

Any class that provides `operator fun component1()`, `operator fun component2()` etc. supports destructuring. The `operator` keyword is required — it is the compile-time contract that makes this function eligible for destructuring use. Without `operator`, the function exists but the destructuring syntax won't resolve to it.

---

### How `data class` Provides `componentN()` — Derived From Its Identity Contract

A `data class` generates `componentN()` functions for every **primary constructor property**, in declaration order. Body properties are NOT included.

**Why only primary constructor properties?**

The primary constructor defines the identity of a `data class` — `equals()`, `hashCode()`, `copy()`, and `toString()` all operate exclusively on primary constructor properties. The compiler uses the same canonical set for `componentN()`. Properties defined in the body are implementation details, not part of the declared "data" — including them would make destructuring inconsistent with the equality model.

```kotlin
data class User(val name: String, val age: Int) {
    val slug = name.lowercase()  // body property — NOT in componentN
}
```

**What the compiler actually generates (decompiled Java):**
```java
public final class User {
    private final String name;
    private final int age;

    // Generated componentN for PRIMARY CONSTRUCTOR properties only:
    public final String component1() { return this.name; }
    public final int    component2() { return this.age; }
    // No component3() for slug — body property excluded

    // equals/hashCode/copy/toString also use ONLY name and age
    @Override public boolean equals(Object o) { ... uses name, age ... }
    @Override public int hashCode() { ... uses name, age ... }
}
```

```kotlin
val (n, a) = User("Alice", 30)        // works: component1(), component2()
// val (n, a, s) = User("Alice", 30)  // COMPILE ERROR: component3() does not exist
```

---

### The `_` Placeholder — What the Compiler Actually Does

`_` tells the compiler: "skip this position — I don't need this value."

Per the Kotlin specification, when `_` is used at a position, **the compiler does NOT generate the `componentN()` call** for that position. The call is omitted entirely:

```kotlin
data class Triple(val a: Int, val b: Int, val c: Int)
val (x, _, z) = Triple(1, 2, 3)

// Compiles to:
val x = triple.component1()    // generated
// component2() is NOT called  ← _ suppresses the call: no variable, no call
val z = triple.component3()    // generated
```

**Decompiled Java:**
```java
Triple triple = new Triple(1, 2, 3);
int x = triple.component1();
// (no call to component2)
int z = triple.component3();
```

**Important nuance:** If you manually write a `component2()` with side effects, `_` will suppress that call — the side effect will NOT run. Always write `componentN()` as pure getters. `_` means "the compiler may skip this entirely."

---

### Destructuring in Lambda Parameters and Loops

The same `componentN()` mechanism applies inside lambda parameter lists and `for` loops:

```kotlin
val pairs = listOf("Alice" to 30, "Bob" to 25)

// Without destructuring:
pairs.forEach { pair -> println("${pair.first}: ${pair.second}") }

// With destructuring — compiler inserts componentN() calls:
pairs.forEach { (name, age) -> println("$name: $age") }
// Generates: { entry -> val name = entry.component1(); val age = entry.component2(); ... }

// Map.Entry — works because Map.Entry has component1() = key, component2() = value:
val scores = mapOf("Alice" to 95, "Bob" to 87)
scores.forEach { (name, score) -> println("$name scored $score") }

// For loop over map:
for ((key, value) in scores) { println("$key → $value") }

// withIndex() — IndexedValue.component1() = index, component2() = value:
list.forEachIndexed { index, item -> }
for ((index, item) in list.withIndex()) { }
```

---

### ## Trap: Destructuring Is Position-Based, NOT Name-Based

This is the most dangerous property of destructuring. The binding is determined by **position** (component1, component2, ...), not by property name. Reordering primary constructor parameters silently breaks all destructuring call sites:

```kotlin
// BEFORE refactor:
data class Point(val x: Int, val y: Int)
val (x, y) = Point(1, 2)  // x=1, y=2 — correct

// AFTER refactor — swapped constructor order:
data class Point(val y: Int, val x: Int)  // ← swapped!
val (x, y) = Point(1, 2)
// Now: x = component1() = y_field = 1 (the y value!)
//      y = component2() = x_field = 2 (the x value!)
// No compile error. Silently wrong values.
```

**Safe patterns:**
- Prefer named property access (`point.x`, `point.y`) for non-trivial data classes
- Destructuring is safest with small, stable data classes (`Pair`, `Map.Entry`, `Result`)
- Add a test that destructures and checks values if the constructor order is meaningful

---

### Adding Destructuring to Any Class

You can add `componentN()` to classes you don't own via extension functions:

```kotlin
// Third-party class with no componentN:
operator fun android.graphics.Rect.component1() = left
operator fun android.graphics.Rect.component2() = top
operator fun android.graphics.Rect.component3() = right
operator fun android.graphics.Rect.component4() = bottom

val rect = Rect(0, 10, 100, 200)
val (l, t, r, b) = rect   // now works — calls the extension componentN functions
```

**Decompiled Java for the extension call:**
```java
int l = RectExtKt.component1(rect);   // extension → static call on companion file
int t = RectExtKt.component2(rect);
int r = RectExtKt.component3(rect);
int b = RectExtKt.component4(rect);
```

---

### Memory Trick

```
DESTRUCTURING = sequential componentN() calls by POSITION.
  val (a, b) = obj  →  val a = obj.component1(); val b = obj.component2()
  operator keyword required. Without it, function exists but destructuring won't resolve it.

data class generates componentN() for PRIMARY CONSTRUCTOR properties ONLY.
  Body properties → NO componentN → can't destructure.
  Reason: primary constructor = identity (equals/hashCode/copy use same set).
  data class User(val name, val age) { val slug = ... }
    → component1()=name, component2()=age. slug has no componentN.

_ placeholder:
  Compiler OMITS the componentN() call entirely (no variable, no call, no side effects).

## TRAP: POSITION-BASED, NOT NAME-BASED.
  Reordering constructor params = silently wrong values. No compile error.
  val (x, y) = Point after swapping Point(y, x) → x gets y's value.
  Prefer .x, .y property access for non-trivial data classes.

IN LAMBDAS and FOR:
  { (key, value) -> } = { e -> val key=e.component1(); val value=e.component2() }
  Same mechanism, same bytecode.

Custom: operator fun T.componentN() as extension → static call in bytecode.
```

### Self-Test

1. `val (a, b) = Pair(1, 2)` — write the decompiled Java including any type information.
2. Why does `data class User(val name: String) { val slug = name.lowercase() }` not allow `val (n, s) = user`? Trace the reason back to the identity contract.
3. Does `_` call the corresponding `componentN()` function? Write the decompiled Java for `val (x, _, z) = triple`.
4. Show the silent bug: a `data class` refactor that swaps two `Int` constructor params and breaks a destructuring call site with no compile error.
5. `scores.forEach { (name, score) -> }` — what makes `Map.Entry` destructurable? Is there a `component1()` method on `Map.Entry`?

---

## Q8.2 — String Templates and Operators

> **Builds on:** [Q0.1 — heap allocation](phase0_jvm_mental_model_v3.md#q01--primitives-vs-references) · [Q4.1 — lambdas and invoke](04_functions_lambdas_inlining.md#q41--lambda-compilation)
> **Connects to:** [Q8.3 — SAM / invoke](#q83--sam-conversions) · [Q8.1 — operator keyword](08_other_kotlin_features.md#q81--destructuring)

---

### String Templates — What They Compile To

String templates compile to `StringBuilder` operations — **NOT `String.format()`**. The template structure is resolved at compile time, not at runtime.

```kotlin
val name = "Alice"
val age = 30
val msg = "Hello $name, you are $age years old"
```

**Decompiled Java:**
```java
// Kotlin compiler generates:
String msg = new StringBuilder()
    .append("Hello ")
    .append(name)          // String.append(String) — no toString() needed
    .append(", you are ")
    .append(age)           // int.append(int) — no Integer boxing, no toString()
    .append(" years old")
    .toString();
```

**Why not `String.format()`?**
`String.format` parses the format string at runtime (reads `%s`, `%d` tokens character-by-character). `StringBuilder.append` chain has zero runtime parsing — the structure is determined entirely at compile time. This makes string templates faster and allocation-cheaper than `String.format`.

**Complex expression `${expr}`:**
```kotlin
"Length is ${list.size * 2}"
// → new StringBuilder().append("Length is ").append(list.size() * 2).toString()
// Arithmetic is evaluated inline. toString() called only for non-primitive results.

"Result: ${if (x > 0) "positive" else "negative"}"
// → conditional expression evaluated, result appended — single StringBuilder
```

**Decompiled Java for `${expr}` with a non-primitive:**
```java
// "$user" where user is a User object:
sb.append(user != null ? user.toString() : "null");
// Kotlin null-safely calls toString(), never throws NPE even for nullable types
```

---

### Operator Overloading — The Naming Contract

Every Kotlin operator maps to a specific function name. The `operator` keyword marks the function as part of the operator contract — without it, the function exists but the operator syntax won't resolve to it.

| Operator | Function | JVM bytecode |
|---|---|---|
| `a + b` | `a.plus(b)` | `INVOKEVIRTUAL plus` |
| `a - b` | `a.minus(b)` | `INVOKEVIRTUAL minus` |
| `a * b` | `a.times(b)` | `INVOKEVIRTUAL times` |
| `a / b` | `a.div(b)` | `INVOKEVIRTUAL div` |
| `a % b` | `a.rem(b)` | `INVOKEVIRTUAL rem` |
| `a += b` | `a.plusAssign(b)` | `INVOKEVIRTUAL plusAssign` |
| `a[i]` | `a.get(i)` | `INVOKEVIRTUAL get` |
| `a[i] = v` | `a.set(i, v)` | `INVOKEVIRTUAL set` |
| `a in b` | `b.contains(a)` | `INVOKEVIRTUAL contains` |
| `a..b` | `a.rangeTo(b)` | `INVOKEVIRTUAL rangeTo` |
| `-a` | `a.unaryMinus()` | `INVOKEVIRTUAL unaryMinus` |
| `a++` | `a.inc()` | `INVOKEVIRTUAL inc` |
| `a()` | `a.invoke()` | `INVOKEVIRTUAL invoke` |
| `a == b` | `a?.equals(b) ?: (b === null)` | null-safe equals |
| `a === b` | referential equality | JVM `if_acmpeq` instruction |

```kotlin
data class Vector(val x: Double, val y: Double) {
    operator fun plus(other: Vector)  = Vector(x + other.x, y + other.y)
    operator fun times(scalar: Double) = Vector(x * scalar, y * scalar)
    operator fun unaryMinus()         = Vector(-x, -y)
    operator fun get(i: Int) = if (i == 0) x else y  // v[0] and v[1]
}

val v1 = Vector(1.0, 2.0)
v1 + Vector(3.0, 4.0)  // → v1.plus(Vector(3.0, 4.0))   → Vector(4.0, 6.0)
v1 * 2.0               // → v1.times(2.0)                → Vector(2.0, 4.0)
-v1                    // → v1.unaryMinus()              → Vector(-1.0, -2.0)
v1[0]                  // → v1.get(0)                    → 1.0
```

---

### The `invoke` Operator — Making Objects Callable

`operator fun invoke(...)` lets an object be called with `()` syntax. `obj(args)` compiles to `obj.invoke(args)`:

```kotlin
class Validator(val rule: (String) -> Boolean) {
    operator fun invoke(value: String): Boolean = rule(value)
}

val emailCheck = Validator { it.contains("@") }
emailCheck("alice@ex.com")   // → emailCheck.invoke("alice@ex.com")
```

**Decompiled Java:**
```java
emailCheck.invoke("alice@ex.com");  // INVOKEVIRTUAL Validator.invoke
```

**This is how all lambdas and function references work at the JVM level:**

```kotlin
val fn: (Int) -> Int = { it * 2 }
fn(5)     // → fn.invoke(5)
```

**Decompiled Java:**
```java
// fn is an object of an anonymous class implementing Function1:
Function1 fn = new Function1() {
    @Override public Integer invoke(Integer p) { return p * 2; }
};
fn.invoke(Integer.valueOf(5));
// Every lambda call = INVOKEVIRTUAL Function1.invoke
```

Every lambda is an object implementing `FunctionN<P1,...,Pn,R>` with a single `invoke()` method. The `()` call syntax on any lambda, function reference, or `operator fun invoke` object compiles to `INVOKEVIRTUAL invoke`. See [Q4.1](04_functions_lambdas_inlining.md#q41--lambda-compilation).

---

### `==` vs `===` — Bytecode Level

```kotlin
a == b    // → a?.equals(b) ?: (b === null)    structural equality, null-safe
a === b   // → referential equality            JVM: if_acmpeq instruction
```

**Decompiled Java for `a == b`:**
```java
// Kotlin: a == b
// Java:
a == null ? b == null : a.equals(b)
// null-safe: if a is null, checks if b is also null
// if a is non-null, calls a.equals(b)
// NEVER throws NullPointerException regardless of a or b
```

`===` compiles to the JVM `if_acmpeq` instruction — comparing the raw heap addresses of two references. Two variables hold `===` true only if they point to the exact same object on the heap.

```kotlin
val a = "hello"
val b = "hello"
a == b    // true  — a.equals(b) compares content
a === b   // true  — JVM string interning: both point to same String literal

val c = StringBuilder("hello").toString()
a == c    // true  — content equal
a === c   // false — different heap objects
```

---

### ## Trap: Mutable `var` in `data class` Corrupts Hash-Based Collections

`data class` generates `hashCode()` from primary constructor properties. Mutating a `var` property after insertion into a hash-based collection changes the hash — the entry is now in the wrong bucket:

```kotlin
data class Point(var x: Int, var y: Int)  // mutable var — dangerous!

val p = Point(1, 2)
val set = hashSetOf(p)
// p stored in bucket: hash(1, 2) % tableSize

println(p in set)    // true — found in correct bucket

p.x = 99             // hashCode now = hash(99, 2) — DIFFERENT from hash(1, 2)!

println(p in set)    // false!
// contains() looks in bucket: hash(99, 2) % tableSize — different bucket!
// p is still physically in the old bucket but the hash lookup misses it.
// The set is now permanently corrupted for this entry.
```

**Decompiled Java for `data class Point(var x: Int, var y: Int)`:**
```java
@Override public int hashCode() {
    return 31 * Integer.hashCode(x) + Integer.hashCode(y);
    // hashCode changes when x or y changes — used as bucket key
}
```

Rule: never use `var` in a `data class` when instances will be stored in `HashSet`, `HashMap`, or `LinkedHashSet`/`LinkedHashMap`. Declare identity-defining properties as `val`.

---

### `rangeTo` and `in 1..10` — Bytecode Optimisation

```kotlin
1..10          // → IntRange(1, 10)    — created by (1).rangeTo(10)
5 in 1..10     // → (1..10).contains(5)  → 1 <= 5 && 5 <= 10
```

**For `for` loops, the compiler eliminates the `IntRange` object entirely:**

```kotlin
for (i in 1..10) { println(i) }
```

**Decompiled Java:**
```java
// No IntRange allocated:
for (int i = 1; i <= 10; i++) {
    System.out.println(i);
}
// Bytecode: ISTORE i, ILOAD i, IF_ICMPGT (loop condition), IINC (increment)
// Three primitive JVM variables: start=1, end=10, step=1 — no heap allocation
```

This optimisation applies to `Int`, `Long`, `Char` ranges in `for` loops. The compiler recognises the `..` in a `for` statement and compiles directly to a primitive counter loop. At runtime: zero object allocation.

**However, `in 1..10` outside a `for` loop DOES allocate:**
```kotlin
val range = 1..10          // → IntRange object allocated on heap
val contains = 5 in range  // → range.contains(5) → method call
```

The optimisation is specific to `for (x in a..b)` pattern — not general range usage.

---

### Memory Trick

```
STRING TEMPLATE = compile-time StringBuilder.append chain. NOT String.format.
  $var     → .append(var)           (no extra overhead for primitives)
  ${expr}  → .append(evaluate expr) (toString() if non-primitive, null-safe)
  Structure resolved at compile time: no runtime format-string parsing.

OPERATOR = named function contract (operator keyword required at declaration):
  +  → plus     -  → minus    *  → times    /  → div
  [] → get/set  () → invoke   in → contains  ..  → rangeTo
  == → a?.equals(b) ?: (b===null)   (null-safe, never NPE, compiled via ternary)
  === → JVM if_acmpeq (raw reference/address comparison)

INVOKE = the mechanism behind ALL lambda calls:
  fn(5) → fn.invoke(5) → INVOKEVIRTUAL Function1.invoke
  () on any object calls invoke(). Lambda = object with invoke().

## TRAP: var in data class + HashSet = corruption:
  hashCode() uses var field. Mutation changes hashCode → wrong bucket → element lost.
  Rule: data class identity properties must be val.

rangeTo in for loop: NO IntRange allocated → primitive counter loop (JVM optimisation).
rangeTo outside for loop: IntRange IS allocated → method call.
```

### Key Takeaways — Q8.2

| Concept | Compile-time result | JVM reality |
|---|---|---|
| `"$name"` | `StringBuilder.append(name)` | No format-string parsing |
| `a + b` (custom class) | `a.plus(b)` | `INVOKEVIRTUAL plus` |
| `fn(5)` | `fn.invoke(5)` | `INVOKEVIRTUAL invoke` |
| `a == b` | `a?.equals(b) ?: (b===null)` | Null-safe, never NPE |
| `a === b` | reference equality | `if_acmpeq` JVM instruction |
| `for (i in 1..10)` | primitive counter loop | No `IntRange` allocated |
| `val r = 1..10` | `IntRange(1, 10)` | Object allocated on heap |

### Self-Test

1. `"Hello $name, age $age"` — write the complete decompiled Java. Why is this faster than `String.format`?
2. `a + b` where `a` is your custom class — what function is called? What JVM bytecode instruction is emitted? What keyword is required on the function?
3. `fn(5)` where `fn: (Int) -> Int` — what is actually called at the JVM level? Write the decompiled Java for the lambda object and call.
4. `a == b` — write the decompiled Java. Can it throw NPE? What about `a === b` — what JVM instruction?
5. Show with code how a mutable `var` in a `data class` corrupts a `HashSet`. Trace the `hashCode()` change.
6. `for (i in 1..10)` — does an `IntRange` get allocated? What about `val r = 1..10`? Why the difference?

---

## Q8.3 — SAM Conversions

> **Builds on:** [Q4.1 — lambda = anonymous class](04_functions_lambdas_inlining.md#q41--lambda-compilation) · [Q4.2 — inline + SAM](04_functions_lambdas_inlining.md#q42--inline-noinline-crossinline)
> **Connects to:** [Q8.2 — operator fun invoke](#q82--string-templates-and-operators)

---

### What SAM Is — First Principles

**SAM = Single Abstract Method.** A functional interface — exactly one abstract method. The JVM has no native concept of "a lambda" — it only knows objects and interfaces. When you write a lambda where a SAM interface is expected, the Kotlin compiler generates an **anonymous class** implementing that interface, with the lambda body as the single method's implementation.

```kotlin
Thread { println("running") }

// Compiler generates:
Thread(object : Runnable {
    override fun run() { println("running") }
})
```

**Decompiled Java:**
```java
new Thread(new Runnable() {
    @Override
    public void run() {
        System.out.println("running");
    }
});
```

**Allocation rules — same as regular lambdas ([Q4.1](04_functions_lambdas_inlining.md#q41--lambda-compilation)):**

```kotlin
// Non-capturing SAM → compiler generates a SINGLETON (allocated once, reused forever):
executor.execute { doStatelessWork() }
// → ExecutorKt$execute$1.INSTANCE  (static final field, allocated at class load)

// Capturing SAM → NEW object per creation (closes over captured variable):
val prefix = "LOG"
executor.execute { println("$prefix: done") }
// → new Runnable$1(prefix)  (new object each time this line executes)
```

```
Non-capturing: captured variables = none → same lambda body every time
               → compiler creates one static singleton instance
               → zero runtime allocation

Capturing: captured variables = runtime values → body differs per creation
           → must create new object to hold closed-over values
           → one heap allocation per SAM creation site execution
```

---

### The Three Rules — When SAM Conversion Works

**Rule 1: Java interface with one abstract method → automatic SAM conversion, always.**

The Kotlin compiler automatically generates the anonymous class when assigning a lambda to a Java functional interface:

```kotlin
button.setOnClickListener { view -> handleClick(view) }  // View.OnClickListener — Java
Thread { doWork() }                                        // Runnable — Java
list.sortWith { a, b -> a.length - b.length }              // Comparator<String> — Java
executor.execute { doWork() }                              // Runnable — Java
```

**Rule 2: Regular Kotlin `interface` → NO automatic SAM conversion.**

```kotlin
interface Validator {
    fun validate(s: String): Boolean
}

val v: Validator = { it.isNotEmpty() }   // COMPILE ERROR: no SAM conversion
```

**Why?** Kotlin interfaces can have default method implementations, property declarations, and can inherit from multiple supertypes. "Exactly one abstract method" is not trivially determined from a single interface declaration — a library could add a default method to a dependency, silently changing the abstract method count. The language designers required an explicit opt-in (`fun interface`) rather than inference that could break silently.

**Rule 3: `fun interface` → explicit opt-in SAM for Kotlin, compiler-verified.**

```kotlin
fun interface Validator {
    fun validate(s: String): Boolean   // exactly ONE abstract method — compiler enforces
}

val v: Validator = { it.isNotEmpty() }  // works ✓ — SAM conversion applied
val result = v.validate("hello")        // calls the generated anonymous class's validate()
```

`fun interface` is a compiler-enforced contract: "this interface has exactly one abstract method and is intended for lambda use." Adding a second abstract method is a compile error.

---

### Bytecode — What SAM Generates

**Non-capturing `fun interface` lambda:**

```kotlin
fun interface Predicate { fun test(s: String): Boolean }
val p: Predicate = { it.isNotEmpty() }
```

**Decompiled Java:**
```java
// Non-capturing → singleton:
static final Predicate p = new Predicate() {
    @Override
    public boolean test(String s) {
        return !s.isEmpty();
    }
};
// Or if Kotlin uses invokedynamic (JVM 8+): LambdaMetafactory.metafactory(...)
// Either way: zero runtime allocation after class load
```

**Capturing `fun interface` lambda:**

```kotlin
val prefix = "LOG"
val p: Predicate = { it.startsWith(prefix) }
```

**Decompiled Java:**
```java
// Capturing → new object per creation:
final String prefix = "LOG";
Predicate p = new Predicate() {
    @Override
    public boolean test(String s) {
        return s.startsWith(prefix);   // closes over captured 'prefix'
    }
};
// New Predicate object allocated every time this code executes
```

---

### When SAM Conversion Does NOT Work — The Traps

```kotlin
// Trap 1: Regular Kotlin interface — not fun interface:
interface Callback { fun onResult(value: Int) }
val cb: Callback = { println(it) }   // COMPILE ERROR

// Trap 2: Abstract class — SAM only works for interfaces:
abstract class Handler { abstract fun handle() }
val h: Handler = { }                  // COMPILE ERROR — abstract classes never SAM

// Trap 3: Two abstract methods — fun interface enforces one:
fun interface Bad {
    fun method1()
    fun method2()   // COMPILE ERROR — fun interface must have exactly one abstract method
}

// Trap 4: Default methods do NOT count toward abstract method limit:
fun interface Transformer {
    fun transform(s: String): String                              // abstract — counts as 1
    fun transformAll(list: List<String>) = list.map(::transform)  // default — doesn't count
}
val upper: Transformer = { it.uppercase() }  // works ✓ — still one abstract method
```

**Why default methods don't count:** Only _abstract_ methods must be implemented. A default method already has a body — the implementer doesn't need to provide one. SAM only applies to the abstract method count.

---

### SAM vs Function Type — When to Use Each

```kotlin
// Option A: fun interface (named type)
fun interface OnComplete { fun onComplete(result: String) }
fun doWork(callback: OnComplete) { callback.onComplete("done") }
doWork { println(it) }   // SAM conversion — creates anonymous class

// Option B: function type (idiomatic Kotlin)
fun doWork(callback: (String) -> Unit) { callback("done") }
doWork { println(it) }   // lambda — creates Function1 anonymous class
```

Both options accept a lambda at the call site. The key differences:

| | `fun interface` | Function type `(T) -> R` |
|---|---|---|
| Java callers | Can implement as anonymous class | Awkward (`FunctionN.invoke`) |
| Semantic name | Yes — `OnComplete` documents intent | No — `(String) -> Unit` is generic |
| Reference equality | Objects have identity (two separate creations ≠ equal) | Same — two lambda objects not equal |
| Kotlin idiomatic? | Preferred for Java interop or named semantics | Preferred for pure Kotlin APIs |

**Prefer function types for pure Kotlin APIs.** Use `fun interface` when:
- Java callers need to implement the callback
- The interface name carries documentation value
- You need to store callbacks in a collection and compare by reference

---

### Memory Trick

```
SAM = Single Abstract Method = interface that can be replaced by a lambda.
Compiler generates anonymous class implementing the interface.
  Non-capturing → SINGLETON (static final field — allocated once at class load)
  Capturing     → NEW OBJECT per creation (holds closed-over variables)

THREE RULES:
  Java interface (1 abstract method)  → automatic SAM, always
  Kotlin interface                    → NO auto-SAM (explicit opt-in needed)
  Kotlin fun interface                → opt-in SAM (compiler verifies 1 abstract method)

WHY no auto-SAM for Kotlin interface:
  Default methods, properties, multiple supertypes = "1 abstract method" is non-trivial.
  A library adding a default method could silently break auto-SAM inference.
  fun interface = explicit: "I designed this for lambda use, compiler please enforce."

DEFAULT METHODS don't count toward abstract method limit.
Abstract classes: NEVER work for SAM (interface contract only).
2+ abstract methods: COMPILE ERROR for fun interface.

Prefer (T) -> R for Kotlin APIs.
Use fun interface when: Java interop, named semantic, reference equality needed.
```

### Key Takeaways — Q8.3

| Concept | Fact |
|---|---|
| Java interface + lambda | Automatic SAM — always works |
| Kotlin `interface` + lambda | No SAM — compile error |
| Kotlin `fun interface` + lambda | Opt-in SAM — compiler verifies 1 abstract method |
| Non-capturing SAM | Singleton — zero runtime allocation |
| Capturing SAM | New object per creation — one heap allocation |
| Default methods | Do NOT count toward abstract method limit |
| Abstract classes | Never eligible for SAM |

### Self-Test

1. `Thread { println("running") }` — write the complete decompiled Java anonymous class. Is it a singleton?
2. Why doesn't SAM conversion work for a regular Kotlin `interface`? What risk does it avoid?
3. Does a `fun interface` with one abstract method and three default methods compile? Why?
4. Non-capturing SAM lambda vs capturing SAM lambda — what is the allocation difference? Show the bytecode difference.
5. When would you prefer `fun interface` over a plain `(String) -> Boolean` function type parameter? Give three concrete reasons.
6. Write a generic `fun interface Predicate<T>` that tests a value and returns `Boolean`. Instantiate it with a lambda for `String` length > 5.

---

## Master Summary: Other Kotlin Features

```
1. DESTRUCTURING
   val (a, b) = obj → obj.component1(), obj.component2()  (position-based, NOT name-based)
   data class generates componentN() for PRIMARY CONSTRUCTOR properties only
   Body properties → no componentN. Reason: same set as equals/hashCode/copy.
   _ → compiler OMITS the componentN() call entirely (no variable, no call, no side effects)
   Works in lambdas: { (k, v) -> } = { e -> component1(), component2() }
   Add to any class via operator extension → compiles to static call

   ## TRAP: reordering constructor params silently swaps destructured values — no compile error.

2. STRING TEMPLATES + OPERATORS
   "$name" → StringBuilder.append chain (NOT String.format — no runtime parsing)
   ${expr} → expression evaluated inline; toString() only for non-primitives, null-safe
   Operators = named function contract (operator keyword required):
     + → plus    [] → get/set   () → invoke   in → contains   .. → rangeTo
   == → a?.equals(b) ?: (b===null)  (null-safe ternary, never NPE)
   === → JVM if_acmpeq (raw reference/heap address comparison)
   invoke = mechanism behind ALL lambda calls: fn(5) → fn.invoke(5) → INVOKEVIRTUAL
   for (i in 1..10): NO IntRange allocated → primitive counter loop
   val r = 1..10: IntRange IS allocated → object on heap

   ## TRAP: var in data class + HashSet = hashCode changes after mutation → wrong bucket → lost entry.

3. SAM CONVERSIONS
   SAM = Single Abstract Method = interface replaceable by a lambda.
   Java interface → automatic SAM (always). Kotlin interface → NO. fun interface → opt-in.
   Compiler generates anonymous class: non-capturing → singleton; capturing → new object.
   Default methods don't count. Abstract classes never eligible.
   Prefer (T) -> R for Kotlin APIs. fun interface for Java interop, named semantics, reference equality.
```

---

*← [Phase 7 — Collections and Sequences](07_collections_and_sequences.md) | [Phase 9 — Coroutines: Execution Mechanics →](09_coroutines_execution_mechanics.md)*