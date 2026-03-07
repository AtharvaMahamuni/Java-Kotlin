# Phase 3 — Generics and Variance

> Generics exist at compile time. The JVM sees none of it. **Type erasure** is not a bug — it was a deliberate compatibility choice. Every feature in this phase is a response to that single constraint.

## Navigation

[← Phase 2 — Classes and Objects](02_classes_and_objects.md) | [→ Phase 4 — Functions and Lambdas](04_functions_lambdas_inlining.md)

## Questions in This File

- [Q3.1 — Type Erasure](#q31--type-erasure)
- [Q3.2 — Variance: `out`, `in`, Invariant](#q32--variance-out-in-invariant)
- [Q3.3 — Star Projection and Wildcards](#q33--star-projection-and-wildcards)
- [Q3.4 — Reified Type Parameters](#q34--reified-type-parameters)
- [Q3.5 — Type Parameter Bounds](#q35--type-parameter-bounds)

---

# Q3.1 — Type Erasure

> **Builds on:** [Q0.2 (JVM type mapping)](phase0_jvm_mental_model_v3.md#q02--jvm-type-mapping-when-does-kotlin-box)
> **Connects to:** [Q3.3 (star projection works because of erasure)](#q33--star-projection-and-wildcards) · [Q3.4 (reified defeats erasure)](#q34--reified-type-parameters)

---

## The Core Rule

```
Compile time:          Runtime (JVM bytecode):
List<String>    →      List
List<Int>       →      List
Map<String, User> →    Map

Type parameters are erased at the class file boundary.
The JVM has never known about <String>, <Int>, etc.
```

---

## Why Does Erasure Exist?

Java 1.0 (1995) had no generics. You wrote `List` and stored `Object`. When Java 5 added generics in 2004, the JVM bytecode format was already deployed on millions of machines. Changing it would have broken every existing Java library.

The solution: **type parameters are compile-time only**. At compile time, `List<String>` and `List<Int>` are distinct types with full safety. At runtime, both are just `List`.

```
Compile Time:                              Runtime:
┌────────────────────────┐                ┌──────────────────┐
│  List<String>          │                │  List            │
│  List<Int>             │  ──ERASE──►    │  List            │
│  Map<String, User>     │                │  Map             │
│  (distinct types)      │                │  (same raw type) │
└────────────────────────┘                └──────────────────┘
```

---

## What the Compiler Inserts Instead

Erasure removes type parameters. The compiler inserts **casts** at every read point to compensate:

```kotlin
val strings: List<String> = listOf("a", "b")
val first: String = strings[0]
```

```
ALOAD strings
ICONST_0
INVOKEINTERFACE List.get (I)Ljava/lang/Object;   ← returns Object (erased!)
CHECKCAST java/lang/String                        ← cast inserted by compiler
ASTORE first
```

You write `strings[0]` as if it returns `String`. The JVM returns `Object`. The compiler inserts a `CHECKCAST` that throws `ClassCastException` if it's wrong. This is what "type safe at compile time, erased at runtime" means concretely.

---

## `is List<String>` Fails — The Erasure Consequence

```kotlin
val list: Any = listOf("hello")
if (list is List<String>) { }  // COMPILE ERROR — cannot check erased type
if (list is List<*>) { }       // OK — just checking "is it a List?"
```

`List<String>` and `List<Int>` are both just `List` at runtime. There is nothing for the JVM to check against. The compiler refuses to compile `is List<String>` because the check would be meaningless.

**Unchecked cast warning:**

```kotlin
val raw: Any = listOf("hello")
val strings = raw as List<String>  // UNCHECKED CAST WARNING — compiles but risky
// Compiler: "I can check that it's a List, but not that elements are String"
// ClassCastException happens later, when you read an element, not here
```

An unchecked cast is a promise to the compiler: "I know what this is, trust me." If you're wrong, you get a `ClassCastException` at the read site, not here.

---

## Why Kotlin Forbids Raw Types

Java allows writing `List` without a type argument (a "raw type") — bypassing type safety entirely:

```java
// Java — raw type causes runtime crash:
List rawList = new ArrayList<String>();
rawList.add(42);              // compiles — no safety!
String s = (String) rawList.get(0); // ClassCastException at runtime
```

Kotlin prohibits raw types. You must write `List<String>`, `List<*>`, or `List<Any?>` — never bare `List`. This eliminates an entire class of runtime errors.

---

## Memory Trick

```
TYPE ERASURE = "compiler draws a curtain at the class file boundary."
  Left (compile): full generics — List<String>, Map<String, User>
  Right (runtime): raw types only — List, Map

WHAT GETS INSERTED INSTEAD:
  Compiler adds CHECKCAST at every read point.
  list.get(0) returns Object → compiler casts to String for you.

is List<String>  → COMPILE ERROR (erased, nothing to check)
is List<*>       → OK (checks "is it a List" — no type param)
as List<String>  → UNCHECKED CAST WARNING (you're trusting, not verified)
                   ClassCastException happens at the READ SITE, not here
```

---

## Self-Test

1. Why were type parameters not stored in JVM bytecode?
2. What does the compiler insert in place of erased type info?
3. Why does `if (list is List<String>)` fail to compile?
4. What is an unchecked cast warning and when does the exception actually throw?
5. What's the difference between `List<*>` and `List<Any?>`?

---

# Q3.2 — Variance: `out`, `in`, Invariant

> **Builds on:** [Q3.1 (erasure — variance annotations are compile-time only)](#q31--type-erasure)
> **Connects to:** [Q2.4 (@UnsafeVariance in List.contains)](02_classes_and_objects.md#q24--data-classes) · [Q7.1 (List covariance)](07_collections_and_sequences.md)

---

## The Core Question

```
Dog IS-A Animal.
Is List<Dog> IS-A List<Animal>?
```

The answer depends on what the container can DO with its type parameter.

---

## Why Generics Can't Just Be Covariant

If `MutableList<Dog>` were a subtype of `MutableList<Animal>`:

```kotlin
val dogs: MutableList<Dog> = mutableListOf(Dog("Rex"))
val animals: MutableList<Animal> = dogs  // IF THIS WERE ALLOWED...

animals.add(Cat("Whiskers"))   // adding Cat to "Animal list"...
                               // but animals IS dogs!

val myDog: Dog = dogs[1]       // ClassCastException! It's a Cat!
```

The type system would be corrupted. This is why `MutableList<Dog>` is **NOT** a subtype of `MutableList<Animal>` — and why the default is **invariant**.

---

## The Three Variance Options

```
INVARIANT (default):
  MutableList<Dog>
  Neither subtype nor supertype of MutableList<Animal>
  Can READ Dogs AND WRITE Dogs — both operations

COVARIANT (out T):
  List<Dog>  IS-A  List<Animal>
  Can only READ — writing is forbidden by the compiler

CONTRAVARIANT (in T):
  Comparator<Animal>  IS-A  Comparator<Dog>
  Can only WRITE (consume/accept) — reading as T is forbidden
```

---

## Covariance: `out T` — The Producer

If a class only **produces** (returns) values of type T — never stores them — it is safe to go UP the hierarchy.

```kotlin
interface List<out E> {        // out = covariant = producer
    fun get(index: Int): E     // E in "out" position — returned
    // fun add(element: E)     // COMPILE ERROR: E in "in" position — forbidden
}
```

```kotlin
val dogs: List<Dog> = listOf(Dog("Rex"))
val animals: List<Animal> = dogs   // SAFE — List<Dog> IS-A List<Animal>

val first: Animal = animals[0]     // reads Dog, receives it as Animal — fine
```

Why safe: every Dog IS-AN Animal. Reading a Dog from `List<Dog>` and treating it as `Animal` is always correct.

```
Hierarchy:     Covariant container:
  Animal           List<Animal>
    │                    │
   Dog ← IS-A       List<Dog> ← IS-A  (same direction!)
```

**The `out` position rule:**

```kotlin
interface Producer<out T> {
    fun get(): T              // ✓ T in out position — can return T
    fun set(item: T)          // ✗ T in in position — COMPILE ERROR
}
// If set() were allowed: Producer<Dog> assigned to Producer<Animal>
// then set(Cat) called → Cat stored in Dog container → corruption
```

---

## Contravariance: `in T` — The Consumer

If a class only **consumes** (accepts as input) values of type T — never produces them — it is safe to go DOWN the hierarchy.

```kotlin
interface Comparator<in T> {    // in = contravariant = consumer
    fun compare(a: T, b: T): Int  // T in "in" position — accepted
    // fun produce(): T            // COMPILE ERROR: T in "out" position
}
```

```kotlin
val animalCmp: Comparator<Animal> = compareBy { it.weight }
val dogCmp: Comparator<Dog> = animalCmp  // SAFE — Comparator<Animal> IS-A Comparator<Dog>

dogCmp.compare(Dog("Rex"), Dog("Spot"))
// Passes Dogs → received as Animals → Dog IS-A Animal → safe
```

Why safe: you're passing Dogs into something that accepts Animals. Since Dog IS-A Animal, an Animal-acceptor can handle Dogs.

```
Hierarchy:     Contravariant container:
  Animal           Comparator<Animal> ← IS-A Comparator<Dog>  (FLIPPED!)
    │
   Dog ← IS-A
```

---

## Java PECS — Same Concept, Different Syntax

Java's wildcards express the same idea. The mnemonic is **PECS: Producer Extends, Consumer Super**:

```java
// Java                           // Kotlin equivalent
List<? extends Animal>      →     List<out Animal>    // can read Animal
List<? super Dog>           →     List<in Dog>        // can accept Dog

void copy(List<? extends T> src,  →  fun <T> copy(src: List<out T>,
          List<? super T> dst)              dst: MutableList<in T>)
```

In Kotlin: `out` = Java `? extends`, `in` = Java `? super`.

---

## Declaration-Site vs Use-Site Variance

**Declaration-site** — annotate the class itself. Applies everywhere:

```kotlin
// Declared on the class — T is always out
class Producer<out T>(private val value: T) {
    fun get(): T = value    // only out positions allowed
}
```

**Use-site** — project an invariant type at the call site. One-time restriction:

```kotlin
// MutableList is invariant, but we project it as out for this one call
fun copy(src: MutableList<out Number>, dst: MutableList<Number>) {
    for (item in src) dst.add(item)
    // src: can only READ (out projection applied)
}

copy(mutableListOf(1, 2, 3), mutableListOf())  // Int IS-A Number ✓
```

---

## Variance Annotations Are Compile-Time Only

`out` and `in` don't survive to bytecode:

```kotlin
fun <T> copyAll(from: List<out T>, to: MutableList<T>) { ... }
```

```
Bytecode:
  copyAll(Ljava/util/List;Ljava/util/List;)V
  No "out" anywhere — both are just List at JVM level
```

The compiler uses `out`/`in` to enforce restrictions. At runtime, both are raw types.

---

## Java Arrays: The Covariant Disaster

Java made arrays covariant — and this was a mistake:

```java
String[] strings = {"hello"};
Object[] objects = strings;   // Java allows — covariant arrays
objects[0] = 42;              // RUNTIME ArrayStoreException — not compile error!
```

Kotlin fixed this: `Array<String>` is **NOT** a subtype of `Array<Any>`. The runtime error is impossible because the compile error catches it first.

---

## Memory Trick

```
OUT = things come OUT = Producer = reads only = goes UP hierarchy
IN  = things go IN   = Consumer = writes only = goes DOWN hierarchy

Quick check: what can the container DO with T?
  Only RETURN T  → out (covariant)   → Container<Dog> IS-A Container<Animal>
  Only ACCEPT T  → in (contravariant)→ Container<Animal> IS-A Container<Dog>
  BOTH           → invariant         → no subtyping at all

Java PECS = same thing:
  Producer Extends = out = ? extends
  Consumer Super   = in  = ? super

MutableList: reads AND writes → invariant → no subtyping
List:        reads only       → covariant → List<Dog> IS-A List<Animal>

Variance annotations: compile-time only. Erased from bytecode.
```

---

## Self-Test

1. Why is `MutableList<Dog>` NOT a subtype of `MutableList<Animal>`?
2. Why is `List<Dog>` IS-A `List<Animal>`?
3. What does `out T` restrict the class from doing?
4. What does `in T` restrict the class from doing?
5. What is PECS and how does it map to Kotlin's `out`/`in`?
6. Declaration-site vs use-site variance — what's the difference?

---

# Q3.3 — Star Projection and Wildcards

> **Builds on:** [Q3.1 (erasure)](#q31--type-erasure) · [Q3.2 (variance)](#q32--variance-out-in-invariant)
> **Connects to:** [Q7.1 (Collections)](07_collections_and_sequences.md)

---

## The Core Idea

`List<*>` means: "a List of some type, but I don't know which."

```kotlin
val list: List<*> = listOf("hello", 42, null)

// What you can do:
val item: Any? = list[0]     // read as Any? — safe, that's the most we can guarantee
list.size                    // structural operations still work

// What you can't do:
list[0].length               // COMPILE ERROR — element is Any?, not String
```

---

## Star Projection Expands to Bounds

`*` is shorthand — it expands to the declared bound:

```kotlin
List<*>            expands to    List<out Any?>   // can read, gets Any?
MutableList<*>     expands to    MutableList<out Nothing>
                                 // can read as Any?, CANNOT write at all
```

`MutableList<*>` blocks writes entirely. If you don't know what type is in the list, you can't safely add anything (except `null` to nullable types, which the compiler also blocks here).

```kotlin
val ml: MutableList<*> = mutableListOf("a", "b")
val item: Any? = ml[0]   // ✓ read as Any?
ml.add("c")              // ✗ COMPILE ERROR — cannot add to MutableList<*>
ml.add(null)             // ✗ COMPILE ERROR — still blocked
```

---

## Star vs Bounded: When to Use Each

```kotlin
// Star: "I don't care what's inside, I won't use the elements typed"
fun printSize(list: List<*>) {
    println(list.size)    // only structural operation
    // list[0] is Any? — minimal info
}

// Bounded: "I need elements to have specific capabilities"
fun sumList(list: List<out Number>): Double {
    return list.sumOf { it.toDouble() }  // .toDouble() available
}
```

| | `List<*>` | `List<out Number>` |
|---|---|---|
| Element type | `Any?` | `Number` |
| Can call Number methods | No | Yes |
| Caller can pass | Any `List<T>` | Only `List<Number>` or subtypes |
| Use when | Don't need element type | Need element behavior |

---

## Java Wildcards vs Kotlin Star

```
Java                Kotlin equivalent
List<?>         →   List<*>
List<? extends Number> →  List<out Number>
List<? super String>   →  List<in String>
```

Kotlin's `*` is Java's `?` — unbounded wildcard. Both mean "some type, unknown which."

---

## Memory Trick

```
List<*>  = "a List of something — I don't know what"
  Reads: Any?
  Writes: BLOCKED

MutableList<*>  = out Nothing on the write side
  "Nothing can be safely added — we don't know the element type"

Star expands to:
  For <out T>-declared:  * = out T (can read as T, can't write)
  For <in T>-declared:   * = in Nothing (can write Nothing = nothing, can read Any?)
  For invariant:         * = out Any? for reads, in Nothing for writes

When to use *:    structural operations only (size, isEmpty, contains)
When to use bound: you need element behavior (sumOf, sorted, etc.)
```

---

## Self-Test

1. What does `List<*>` mean? What type do you get when you read from it?
2. Why can't you add to `MutableList<*>`?
3. What does `List<*>` expand to internally?
4. `List<*>` vs `List<Any?>` — what's the difference?

---

# Q3.4 — Reified Type Parameters

> **Builds on:** [Q3.1 (type erasure)](#q31--type-erasure) · [Q4.2 (inline functions)](04_functions_lambdas_inlining.md#q42--inline-noinline-crossinline)
> **Connects to:** [Q3.5 (bounds + reified)](##q35--type-parameter-bounds)

---

## The Core Idea

Normal generic function: T is erased. You can't ask "what is T?" at runtime.

```kotlin
fun <T> check(list: List<*>): Boolean = list is List<T>
// COMPILE ERROR — T is erased, nothing to check against
```

`inline` + `reified`: the function body is **copy-pasted** at every call site. At the call site, T is KNOWN. The compiler substitutes it:

```kotlin
inline fun <reified T> check(list: List<*>): Boolean = list is List<T>

// Call site: check<String>(myList)
// Compiler pastes body with T = String:
//   myList is List<String>  ← concrete type, no erasure
```

---

## Why Reified Requires `inline`

The chain:

```
ERASURE:  T is gone at runtime in normal generic functions
INLINE:   function body is copy-pasted at every call site
REIFIED:  at the call site, the concrete type is known
          → compiler substitutes T with the actual type in the pasted body
```

Without `inline`, there is no call site paste — the function runs as a normal method with T erased.

```kotlin
// What happens at check<String>(myList):
// Compiler pastes the body here:
val result = myList is List<String>   // T replaced by String!

// Bytecode at call site:
ALOAD myList
INSTANCEOF java/util/List   // the element type is checked differently
// actually: reified enables full is-check on the generic type
```

---

## What `reified` Enables

```kotlin
inline fun <reified T> isInstanceOf(value: Any): Boolean = value is T
inline fun <reified T> getClass(): KClass<T> = T::class
inline fun <reified T> parseJson(json: String): T = gson.fromJson(json, T::class.java)

// Without reified — ugly Java-style workaround:
fun <T> parseJson(json: String, clazz: Class<T>): T = gson.fromJson(json, clazz)
val user = parseJson(json, User::class.java)   // manual Class passing

// With reified — clean:
val user: User = parseJson(json)               // type inferred from return type
```

---

## `T::class` Inside vs Outside Reified

```kotlin
// Outside reified context — T is erased:
fun <T> getClass(): KClass<T> {
    return T::class  // COMPILE ERROR: Cannot use T as reified
}

// Inside reified inline — T is concrete at each call site:
inline fun <reified T> getClass(): KClass<T> {
    return T::class  // Works! Compiler substitutes T
}

val clazz = getClass<User>()   // KClass<User>
```

---

## Android Pattern: `startActivity<T>()`

The most common Android use of reified:

```kotlin
// Without reified:
fun startActivity(clazz: Class<out Activity>) {
    startActivity(Intent(this, clazz))
}
startActivity(DetailActivity::class.java)   // ugly

// WITH reified:
inline fun <reified T : Activity> Context.startActivity() {
    startActivity(Intent(this, T::class.java))
}

startActivity<DetailActivity>()  // clean!

// What the compiler generates at call site:
val intent = Intent(this, DetailActivity::class.java)  // T substituted
startActivity(intent)
```

---

## Why `reified` Cannot Be on Class Type Parameters

```kotlin
class Box<reified T> {    // COMPILE ERROR
    fun check(v: Any) = v is T
}
```

`reified` requires `inline`. `inline` is a property of **functions** — bodies are pasted at call sites. Classes are not inlined — they're instantiated. The JVM creates an object at runtime; there's no "paste" to substitute T into.

```
Function inline:  doWork<String>() → body pasted with T=String → T known
Class instantiate: Box<String>()   → new object created → T erased like always

Only FUNCTIONS can be inline → only FUNCTION type params can be reified
```

---

## Memory Trick

```
REIFIED requires INLINE. Always.

Chain:
  ERASURE  → T is gone at runtime (normal generics)
  INLINE   → body pasted at call site (function disappears)
  REIFIED  → T known at paste site → compiler substitutes → no erasure there

Cannot use reified on CLASS type params:
  class Box<reified T> → COMPILE ERROR
  Classes instantiate, not inline. No paste. T erased as always.

T::class   outside reified → COMPILE ERROR
T::class   inside reified  → works (substituted to concrete KClass)
T::class.java inside reified → works (substituted to concrete Class<T>)
```

---

## Self-Test

1. Why does `reified` require `inline`?
2. `inline fun <reified T> isA(v: Any) = v is T` — what bytecode does the call `isA<String>(x)` generate?
3. Why can't `class Box<reified T>` compile?
4. `T::class` inside a non-reified function — what happens?
5. Write the `startActivity<T>()` pattern from memory.

---

# Q3.5 — Type Parameter Bounds

> **Builds on:** [Q3.1 (erasure determines what T erases to)](#q31--type-erasure) · [Q1.3 (Any vs Any?)](01_type_system_foundations.md#q13--type-hierarchy-any-nothing-unit)
> **Connects to:** [Q3.4 (bounds + reified)](#q34--reified-type-parameters)

---

## The Core Idea

No bound: T is `Any?` — you can't call ANY methods on it.

```kotlin
fun <T> process(x: T) {
    x.toDouble()  // COMPILE ERROR: Any? doesn't have toDouble()
}
```

With a bound: T borrows all of the bound's methods.

```kotlin
fun <T : Number> process(x: T): Double {
    return x.toDouble()  // OK — compiler knows T has Number's methods
}
```

The bound is what T "inherits" at compile time. Tighter bound = more methods available.

---

## Upper Bounds: `T : SomeType`

```kotlin
fun <T : Comparable<T>> max(a: T, b: T): T {
    return if (a > b) a else b   // > works because Comparable has compareTo
}

max(3, 5)            // T = Int, Int : Comparable<Int> ✓
max("apple", "fig")  // T = String, String : Comparable<String> ✓
max(listOf(1), listOf(2))  // COMPILE ERROR: List is not Comparable
```

---

## The Default Implicit Bound: `T : Any?` vs `T : Any`

```kotlin
// Default: T : Any? — nullable allowed
fun <T> acceptsNull(value: T) { }
acceptsNull<String?>(null)   // OK

// T : Any — nullable forbidden
fun <T : Any> refusesNull(value: T) { }
refusesNull<String?>(null)   // COMPILE ERROR: String? doesn't satisfy T : Any
refusesNull<String>("hi")    // OK
```

Use `T : Any` when you need to call methods that don't exist on `Any?` — like `hashCode()` without null-check.

---

## Multiple Bounds: `where`

One bound in `<T : Bound>`. For multiple, use `where`:

```kotlin
fun <T> sortAndSave(list: List<T>): List<T>
        where T : Serializable,
              T : Comparable<T> {
    return list.sorted()   // Comparable<T> provides this
    // serialization can happen too — Serializable available
}

sortAndSave(listOf(1, 2, 3))      // Int : Serializable AND Comparable<Int> ✓
sortAndSave(listOf(listOf(1)))    // List: not Serializable → COMPILE ERROR
```

---

## Recursive Bounds: `T : Comparable<T>`

The most common recursive bound — "T can be compared with itself":

```kotlin
fun <T : Comparable<T>> clamp(value: T, min: T, max: T): T {
    return when {
        value < min -> min
        value > max -> max
        else -> value
    }
}

clamp(5, 1, 10)        // T = Int, uses Int.compareTo(Int)
clamp("c", "a", "z")  // T = String, uses String.compareTo(String)
```

Builder DSL pattern uses `T : Builder<T>` for fluent return types — each chained call returns the concrete subtype, not the base type.

---

## What T Erases to in Bytecode

At runtime, T erases to its **upper bound** — not to `Object`:

```kotlin
fun <T : Number> process(value: T): Double = value.toDouble()
```

```
Bytecode:
  process(Ljava/lang/Number;)D      ← T erases to Number, not Object!
```

| Bound | T erases to |
|---|---|
| `<T : Number>` | `Number` |
| `<T : Any>` | `Object` |
| `<T>` (no bound, implicit `Any?`) | `Object` |
| `<T : Serializable>` | `Serializable` |

With `T : Number`, the JVM can call `Number` methods directly on T without an extra cast. This is why bounds matter at the bytecode level, not just for compile-time checking.

---

## Android/Kotlin API Patterns

```kotlin
// ViewModel factory — bound ensures lifecycle attachment
inline fun <reified VM : ViewModel> Fragment.viewModels(): VM {
    return ViewModelProvider(this)[VM::class.java]
}

// Bound ensures we can log anything with a tag
interface Loggable { val tag: String }

fun <T : Loggable> logAll(items: List<T>) {
    items.forEach { println("[${it.tag}] $it") }  // .tag available
}
```

---

## Memory Trick

```
BOUND = "T must be AT LEAST this type — and gets all its methods."
  <T : Number>         → T has toDouble(), toInt(), etc.
  <T : Comparable<T>>  → T can compare with itself (sortable)
  <T : Any>            → T is non-null (Any excludes null, Any? includes null)
  <T>                  → implicit T : Any? (nullable allowed, minimal methods)

MULTIPLE BOUNDS:
  fun <T> save(list: List<T>) where T : Serializable, T : Comparable<T>

AT RUNTIME: T erases to its upper bound:
  <T : Number>  → erases to Number (not Object)
  <T>           → erases to Object

Why it matters: <T : Number> lets JVM call Number methods without extra cast.
```

---

## Self-Test

1. `fun <T> fn(x: T) { x.hashCode() }` — does this compile? Why?
2. What is the implicit bound when you write `<T>` with no explicit bound?
3. `<T : Any>` vs `<T : Any?>` — what does each allow?
4. How do you express "T must implement both A and B"?
5. `fun <T : Number> process(v: T)` — what does T erase to in bytecode?

---

# Master Summary: Phase 3

> Generics are compile-time. The JVM erases all type parameters. Every feature in this phase is a tool to work within that constraint safely.

**1. Type Erasure** (Q3.1)
`List<String>` and `List<Int>` are both just `List` at runtime. Compiler inserts `CHECKCAST` at read sites. `is List<String>` fails — erased. `is List<*>` works — checks raw type.

**2. Variance** (Q3.2)
`out T` = covariant = producer = `Container<Dog>` IS-A `Container<Animal>`.
`in T` = contravariant = consumer = `Container<Animal>` IS-A `Container<Dog>`.
Invariant (default) = can read AND write = no subtyping. Variance annotations compile-time only.

**3. Star Projection** (Q3.3)
`List<*>` = "some List, unknown type." Reads as `Any?`. `MutableList<*>` blocks writes entirely. Use `*` for structure-only operations; use bounds when you need element behavior.

**4. Reified** (Q3.4)
`inline` pastes body at call site. At call site, T is known. `reified` = compiler substitutes T in pasted body. Defeats erasure locally. Cannot be on class type params — classes are not inlined.

**5. Type Bounds** (Q3.5)
`T : Number` gives T all of Number's methods. `T : Any` forbids null. `where` for multiple bounds. T erases to its upper bound in bytecode — `T : Number` erases to `Number`, not `Object`.

---

## Master Chain: Generics

```
Type erasure: List<String> == List at runtime
      │
      ├── is List<String> fails → is List<*> works
      │
      ├── out/in are compile-time only → erased in bytecode
      │         │
      │         └── MutableList invariant (reads+writes)
      │             List covariant (reads only)
      │
      ├── star projection: * = out Any? for reads, in Nothing for writes
      │
      └── reified requires inline
                │
                └── body pasted at call site → T known → substituted
                          │
                          └── T::class works → startActivity<T>() pattern
```

---

*← [Phase 2 — Classes and Objects](02_classes_and_objects.md) | [Phase 4 — Functions and Lambdas →](04_functions_lambdas_inlining.md)*