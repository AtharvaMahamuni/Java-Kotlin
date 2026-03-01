# Phase 3: Generics and Variance

## Navigation
[← Master Index](master_chains.md)

## Questions in This File
- [Q3.1 — Type Erasure](#q31--type-erasure)
- [Q3.2 — Variance](#q32--variance)
- [Q3.3 — Reified Type Parameters](#q33--reified-type-parameters)
- [Q3.4 — Type Parameter Bounds](#q34--type-parameter-bounds)

---

## Q3.1 — Type Erasure

> **Builds on:** [Q0.2 — JVM Type Mapping](00_jvm_mental_model.md#q02--jvm-type-mapping)
> **Connects to:** [Q3.3 (reified defeats erasure)](03_generics_and_variance.md#q33--reified-type-parameters) · [Q1.4 (is checks)](01_type_system_foundations.md#q14--smart-casts)

### First Principles: Why Does Erasure Exist?

**The historical constraint:** Java 1.0 (1995) had no generics — you wrote `List` and stored `Object` references. When Java 5 added generics in 2004, the JVM bytecode format was already deployed on millions of machines. Changing the bytecode format to carry type parameters would have broken backward compatibility with every existing Java program and library.

The solution: **type erasure**. Generic types are a **compile-time fiction**. At compile time, `List<String>` and `List<Integer>` are different types with full type safety. At runtime, they are both just `List` — the type parameters are erased from bytecode entirely.

```
Compile Time:                              Runtime (JVM bytecode):
┌─────────────────────────────┐            ┌─────────────────────────────┐
│  List<String>               │            │  List                       │
│  List<Integer>              │  ──────►   │  List                       │
│  Map<String, List<User>>    │  ERASE     │  Map                        │
│  These are DISTINCT types   │            │  These are THE SAME type    │
└─────────────────────────────┘            └─────────────────────────────┘
```

### What Happens at Bytecode Level

```kotlin
val strings: List<String> = listOf("a", "b", "c")
val ints: List<Int> = listOf(1, 2, 3)
```

```bytecode
; Both have the same descriptor at bytecode level:
; (Ljava/util/List;)V
; The <String> and <Int> type arguments are gone!
```

The JVM class file stores only `List`, not `List<String>`. The compiler inserts automatic **casts** at the call site where needed:

```kotlin
val first: String = strings[0]
```

```bytecode
ALOAD strings
ICONST_0
INVOKEINTERFACE List.get (I)Ljava/lang/Object;  ; returns Object (erased!)
CHECKCAST java/lang/String                       ; cast inserted by compiler
ASTORE first
```

### Why `list is List<String>` Fails at Runtime

```kotlin
val list: Any = listOf("hello", "world")

if (list is List<String>) {  // COMPILE ERROR: Cannot check for erased type
    // The JVM would need to inspect: are all elements String?
    // But List's type parameter doesn't exist at runtime!
}
```

The compiler **refuses to compile** this because it would always succeed (since `List<String>` and `List<Int>` are both just `List` at runtime). The check would be meaningless.

**What you CAN check:**
```kotlin
if (list is List<*>) {        // OK: checks if it's a List (any element type)
    val item = list[0]        // item has type Any? (we don't know element type)
}
```

### The Four List Type Variants

These four are all distinct in Kotlin but behave differently:

```kotlin
// 1. List<String> — read-only list, elements must be String
val a: List<String> = listOf("hello")
a[0].length      // String method — safe
// a.add("x")   // ERROR: read-only

// 2. List<Any?> — read-only list, elements can be anything including null
val b: List<Any?> = listOf("hello", 42, null)
// b[0].length  // ERROR: Any? doesn't have length

// 3. List<out Any> — covariant projection, same as List<Any?>
// (means: a List that produces elements that are at least Any)
val c: List<out Any> = listOf("hello", 42)

// 4. Raw Java List — equivalent to List<*> in Kotlin
// In Kotlin, raw types are forbidden (unlike Java)
```

```
┌────────────────────────────────────────────────────────────┐
│  WHAT YOU CAN DO                │ List<String> │ List<*>   │
│─────────────────────────────────│──────────────│───────────│
│  read element as String         │     YES      │    NO     │
│  read element as Any?           │     YES      │    YES    │
│  pass where List<String> needed │     YES      │    NO     │
│  pass where List<Any?> needed   │     NO*      │    YES    │
│  (*only via out-projection)     │              │           │
└────────────────────────────────────────────────────────────┘
```

### Why Kotlin Forbids Raw Types

Java allows writing `List` without a type argument (a "raw type"). This bypasses type safety entirely:

```java
// Java — raw type causes runtime crash:
List rawList = new ArrayList<String>();
rawList.add(42);           // compiles with warning — you're adding int to String list!
String s = (String) rawList.get(0); // ClassCastException at runtime
```

Kotlin prohibits raw types. Every generic type must have either a type argument or a wildcard (`*`). This eliminates an entire class of runtime type errors.

> **Interview Answer:** Type erasure exists because Java 5 had to be backward-compatible with Java 1.0 bytecode. The JVM never learned about generic types — they're compile-time only. The Kotlin compiler erases them and inserts casts. This is why `is List<String>` fails: there's no type parameter at runtime to check against.

---

## Q3.2 — Variance

> **Builds on:** [Q2.1 — Liskov Substitution](02_classes_and_objects.md#q21--class-modifiers) · [Q0.2 — boxing](00_jvm_mental_model.md#q02--jvm-type-mapping)
> **Connects to:** [Q2.2 (@UnsafeVariance)](02_classes_and_objects.md#q22--data-classes) · [Q7.1 (List covariance)](07_collections_and_sequences.md)

### First Principles: The Liskov Substitution Principle

Before diving into variance, we need to understand the **Liskov Substitution Principle (LSP)**: if `Dog` is a subtype of `Animal`, you should be able to use a `Dog` wherever an `Animal` is expected, without breaking the program.

```kotlin
fun feed(animal: Animal) { animal.eat() }

feed(Dog())  // Dog IS-A Animal → safe
feed(Cat())  // Cat IS-A Animal → safe
```

Now the question variance answers: **if `Dog` is a subtype of `Animal`, is `Container<Dog>` a subtype of `Container<Animal>`?**

The answer depends on what `Container` can DO with its type parameter.

---

### The Problem: Why Generic Types Can't Just Be Covariant

Imagine `MutableList<Dog>` were a subtype of `MutableList<Animal>`:

```kotlin
val dogs: MutableList<Dog> = mutableListOf(Dog("Rex"))
val animals: MutableList<Animal> = dogs  // IF THIS WERE ALLOWED...

animals.add(Cat("Whiskers"))  // Adding a Cat to a "Animal" list
// BUT `animals` IS `dogs`! We just added a Cat to a list of Dogs!

val myDog: Dog = dogs[1]  // ClassCastException! It's a Cat!
```

This would **corrupt the type system**. This is why `MutableList<Dog>` is NOT a subtype of `MutableList<Animal>` — the compiler forbids the assignment on line 2.

The root cause: `MutableList` can both **read** and **write** elements. Writing a `Cat` into a `Dog` list is unsafe.

---

### The Three Variance Options

```
INVARIANT (default):     MutableList<Dog>
                         Neither subtype nor supertype of MutableList<Animal>
                         Can READ Dogs AND WRITE Dogs

COVARIANT (out T):       List<Dog>
                         IS a subtype of List<Animal>
                         Can only READ — writing is forbidden

CONTRAVARIANT (in T):    Comparator<Animal>
                         IS a subtype of Comparator<Dog>
                         Can only WRITE (consume) — reading is forbidden
```

---

### Covariance: `out T` — The Producer

**The rule:** If a class only ever **produces** (returns) values of type `T` — never consumes (stores) them — then it is safe to say `Container<Dog>` IS-A `Container<Animal>`.

```kotlin
interface List<out E> {      // out = covariant = producer
    fun get(index: Int): E   // E is in "out" position (returned)
    // fun add(element: E)   // This would be COMPILE ERROR! E in "in" position
}
```

Why is it safe?
```kotlin
val dogs: List<Dog> = listOf(Dog("Rex"), Dog("Spot"))
val animals: List<Animal> = dogs  // SAFE! List<Dog> is-a List<Animal>

val first: Animal = animals[0]    // reads a Dog, returns it as Animal → safe
// animals.add(Cat())             // IMPOSSIBLE — List has no add() method
```

Because `List` can only READ elements, and every `Dog` IS-AN `Animal`, reading from `List<Dog>` and treating it as `List<Animal>` is perfectly safe.

```
out T (Covariant) — Mental Model:
┌──────────────────────────────────────┐
│  Container<out T>                    │
│                                      │
│  T can COME OUT (be returned)    ✓   │
│  T can NOT GO IN (be stored)     ✗   │
│                                      │
│  Container<Dog> IS-A Container<Animal>│
│  Because: Dog IS-A Animal            │
│  Subtype flows in the SAME direction │
└──────────────────────────────────────┘
```

```
Class hierarchy:                    Covariant container hierarchy:
    Animal                              List<Animal>
      │                                    │
      Dog ← IS-A                           List<Dog> ← IS-A (same direction)
```

**Forbidden in `out` positions:**
```kotlin
interface MyList<out T> {
    fun get(): T         // ✓ T in out position — allowed
    fun add(item: T)     // ✗ T in in position — COMPILE ERROR!
                         // If allowed: List<Dog> assigned to List<Animal>
                         // then add(Cat) called — Cat stored in Dog list!
}
```

---

### Contravariance: `in T` — The Consumer

**The rule:** If a class only ever **consumes** (accepts as input) values of type `T` — never produces them — then it is safe to say `Container<Animal>` IS-A `Container<Dog>`.

```kotlin
interface Comparator<in T> {  // in = contravariant = consumer
    fun compare(a: T, b: T): Int   // T is in "in" position (parameter)
    // fun produce(): T            // COMPILE ERROR! T in "out" position
}
```

Why is it safe?
```kotlin
val animalComparator: Comparator<Animal> = Comparator { a, b -> a.weight - b.weight }
val dogComparator: Comparator<Dog> = animalComparator  // SAFE! Comparator<Animal> is-a Comparator<Dog>

dogComparator.compare(Dog("Rex"), Dog("Spot"))
// Passes two Dogs → animalComparator receives them as Animals → safe!
// Every Dog IS-AN Animal, so the comparator works fine on dogs
```

```
in T (Contravariant) — Mental Model:
┌──────────────────────────────────────┐
│  Container<in T>                     │
│                                      │
│  T can GO IN (be accepted)       ✓   │
│  T can NOT COME OUT (be returned) ✗  │
│                                      │
│  Container<Animal> IS-A Container<Dog>│
│  Because: Dog IS-A Animal            │
│  Subtype flows in OPPOSITE direction │
└──────────────────────────────────────┘
```

```
Class hierarchy:                    Contravariant container hierarchy:
    Animal                              Comparator<Animal> ← IS-A Comparator<Dog>
      │                                    │                   (flipped!)
      Dog ← IS-A                           Comparator<Dog>
```

**Real example — `Action<in T>`:**
```kotlin
interface Action<in T> {
    fun execute(item: T)
}

val processAnimal: Action<Animal> = object : Action<Animal> {
    override fun execute(item: Animal) { println("Processing ${item.name}") }
}

val processDog: Action<Dog> = processAnimal  // Action<Animal> IS-A Action<Dog> ✓
processDog.execute(Dog("Rex"))  // Dog passed to Action<Animal> — safe, Dog IS-A Animal
```

---

### Variance in Bytecode: Does It Survive?

**No.** `out` and `in` modifiers are **compile-time only**. They don't exist in bytecode:

```kotlin
fun <T> copy(from: List<out T>, to: MutableList<T>) { ... }
```

```bytecode
; Bytecode signature:
copy(Ljava/util/List;Ljava/util/List;)V
; No `out` anywhere — both are just List at JVM level
```

The compiler uses `out`/`in` to enforce restrictions at the call site. At runtime, both types are just their raw JVM class.

---

### Declaration-Site vs Use-Site Variance

**Declaration-site variance** (`out T` / `in T` on the class itself):

```kotlin
// Declared on the class — applies everywhere this type is used
class Producer<out T>(private val value: T) {
    fun get(): T = value   // T can only be in out positions
}
```

**Use-site variance** (projections — `out T` / `in T` at the call site):

```kotlin
// Declared at the usage site — one-time restriction
fun copy(src: MutableList<out Number>, dst: MutableList<Number>) {
    // src: can only READ from (out projection), even though MutableList is invariant
    for (item in src) dst.add(item)
}

copy(mutableListOf(1, 2, 3), mutableListOf())  // OK: Int IS-A Number
```

Use-site variance lets you project an invariant type as covariant or contravariant for a specific call.

---

### `@UnsafeVariance` — Breaking the Rules Safely

`List` is declared `out E` (covariant). But `contains` takes `E` as a parameter (in-position), which normally violates covariance:

```kotlin
interface List<out E> {
    // Problem: E is in an "in" position here!
    fun contains(element: @UnsafeVariance E): Boolean
}
```

`@UnsafeVariance` tells the compiler: "I know this looks wrong, but I'm taking responsibility for safety." It's safe here because `contains` only **reads** the element to compare it — it doesn't store it in the list. The variance concern (you could add a Cat to a Dog list) doesn't apply to a read-only comparison.

---

### Java Arrays: The Covariant Disaster

Java made arrays covariant (`String[]` IS-A `Object[]`) — and this was a mistake:

```java
// Java — arrays are covariant but NOT type-safe:
String[] strings = new String[]{"hello", "world"};
Object[] objects = strings;  // Java allows this (covariant arrays)

objects[0] = 42;  // RUNTIME ArrayStoreException! 42 is not a String
```

Java added a runtime check (`ArrayStoreException`) to catch this. Kotlin fixed the design: arrays are **invariant** (`Array<String>` is NOT a subtype of `Array<Any>`), so this crash cannot happen.

> **Interview Answer:** `MutableList<Dog>` is not a subtype of `MutableList<Animal>` because it can WRITE — and writing a Cat into a Dog list would corrupt the type system. `List<Dog>` IS a subtype of `List<Animal>` because `List` is `out E` (covariant) — it can only READ elements. Reads are safe because every Dog IS an Animal.

---

## Q3.3 — Reified Type Parameters

> **Builds on:** [Q3.1 (type erasure)](03_generics_and_variance.md#q31--type-erasure) · [Q4.2 (inline)](04_functions_lambdas_inlining.md#q42--inline-noinline-crossinline)
> **Reference:** [Kotlin Docs — Reified type parameters](https://kotlinlang.org/docs/inline-functions.html#reified-type-parameters)

### First Principles: The Problem Reified Solves

Because of type erasure, you normally cannot do this:

```kotlin
fun <T> checkIfString(list: List<*>): Boolean {
    return list is List<T>  // COMPILE ERROR: Cannot check erased type
}

fun <T> getFirst(list: List<*>): T? {
    return list[0] as? T  // WARNING: Unchecked cast — T is erased!
}
```

The traditional Java workaround is to pass the `Class<T>` explicitly:

```java
// Java pattern: pass Class<T> to work around erasure
public <T> T parseJson(String json, Class<T> clazz) {
    return gson.fromJson(json, clazz);
}

// Call site — awkward!
User user = parseJson(json, User.class);
```

```kotlin
// Kotlin equivalent — still ugly:
fun <T> parseJson(json: String, clazz: Class<T>): T = gson.fromJson(json, clazz)
val user: User = parseJson(json, User::class.java)
```

### The Exact Mechanism: `inline` + `reified`

`reified` only works with `inline` functions. Here's why:

**`inline` functions** are pasted directly at the call site. The compiler doesn't just call the function — it substitutes the entire function body at every call site. This means it knows the exact type arguments used at each call site!

At the call site `doSomething<User>()`, the compiler knows `T = User`. When it inlines the function, it substitutes `T` with the actual type `User` everywhere in the function body.

```kotlin
inline fun <reified T> isInstanceOf(value: Any): Boolean {
    return value is T  // T is concrete at the call site — this works!
}

// Call site:
val result = isInstanceOf<String>("hello")
```

The compiler inlines this as:
```kotlin
// What the compiler actually generates at the call site:
val result = "hello" is String  // T has been replaced with String!
```

```bytecode
; At the call site:
ALOAD "hello"
INSTANCEOF java/lang/String   ; T = String, substituted by compiler
ISTORE result
```

No erasure! The type `String` is baked directly into the call site.

### `T::class` Inside vs Outside a Reified Function

```kotlin
// OUTSIDE reified context — T is erased, ::class doesn't know T:
fun <T> getClass(): KClass<T> {
    return T::class  // COMPILE ERROR: Cannot use 'T' as reified type parameter
}

// INSIDE reified inline function — T is concrete:
inline fun <reified T> getClass(): KClass<T> {
    return T::class  // WORKS! Compiler substitutes T at call site
}

// Usage:
val clazz = getClass<User>()  // Returns KClass<User>
```

### Java `Class<T>` Pattern vs Reified — Bytecode Comparison

**Java / Kotlin without reified:**
```kotlin
fun <T> parseJson(json: String, type: Class<T>): T {
    return gson.fromJson(json, type)
}

// Call site: must pass Class explicitly
val user = parseJson(json, User::class.java)
```

```bytecode
; Call site bytecode — must load Class object:
LDC Lcom/example/User;.class    ; load Class<User> as argument
INVOKESTATIC parseJson
```

**Kotlin with reified:**
```kotlin
inline fun <reified T> parseJson(json: String): T {
    return gson.fromJson(json, T::class.java)
}

// Call site: no Class argument needed!
val user = parseJson<User>(json)
```

```bytecode
; Inlined call site bytecode:
LDC Lcom/example/User;.class    ; compiler inserts this from the reified type!
; ... gson.fromJson called with User.class
```

The bytecode is similar, but from the caller's perspective it's far cleaner — no manual `Class` passing.

### `startActivity<DetailActivity>()` Extension Pattern

This is the most common reified pattern on Android:

```kotlin
// Without reified:
fun startActivity(clazz: Class<out Activity>) {
    val intent = Intent(this, clazz)
    startActivity(intent)
}
startActivity(DetailActivity::class.java)  // ugly

// WITH reified — clean syntax!
inline fun <reified T : Activity> Context.startActivity() {
    val intent = Intent(this, T::class.java)  // T is concrete here!
    startActivity(intent)
}

startActivity<DetailActivity>()  // clean!
```

How it works:
```kotlin
// What the compiler generates at startActivity<DetailActivity>() call:
val intent = Intent(this, DetailActivity::class.java)  // T = DetailActivity
startActivity(intent)
```

### Why `reified` Cannot Be on Class Type Parameters

```kotlin
// CANNOT do this:
class Box<reified T> {    // COMPILE ERROR
    fun check(value: Any) = value is T  // would need T at runtime
}
```

`reified` requires `inline`, and `inline` is a property of **functions** — classes don't get inlined. Every class instantiation creates a new object; there's no "inlining" of a class. The type parameter on a class is always erased at runtime.

**Only functions can be `inline`** → **only function type parameters can be `reified`**.

```
reified requires:
1. inline function → body pasted at call site
2. Type argument known at call site
3. Compiler can substitute T with concrete type in pasted code

This chain is impossible for classes:
- Classes aren't inlined — they're instantiated
- JVM doesn't know T at object creation time
- Cannot substitute T in class body
```

> **Key Takeaway:** Reified type parameters are a compiler trick: `inline` causes the function body to be copy-pasted at each call site, and at each call site the concrete type is known. The compiler substitutes the concrete type for `T` in the pasted body. This defeats erasure for that specific call site.

---

## Q3.4 — Type Parameter Bounds

> **Builds on:** [Q3.1 — Type Erasure](03_generics_and_variance.md#q31--type-erasure) · [Q3.2 — Variance](03_generics_and_variance.md#q32--variance)
> **Connects to:** [Q3.3 — Reified](03_generics_and_variance.md#q33--reified-type-parameters) · [Q1.3 — Nothing and Any](01_type_system_foundations.md#q13--nothing-unit-and-the-type-hierarchy)

### What Are Type Parameter Bounds?

By default, a type parameter `T` can be substituted with *any* Kotlin type — `String`, `Int`, `UserActivity`, anything. But often you need to restrict what types callers can use. **Type parameter bounds** let you say "T must be a subtype of X".

```kotlin
// Unrestricted: T can be anything
fun <T> identity(value: T): T = value

// Bounded: T must be a subtype of Number
fun <T : Number> double(value: T): Double = value.toDouble() * 2
```

Without the bound, `value.toDouble()` would be a compile error — `Any` doesn't have `toDouble()`. With `T : Number`, the compiler knows T has all of Number's methods.

---

### Upper Bounds: `T : SomeType`

An **upper bound** means T must be `SomeType` itself or a subtype of it:

```kotlin
fun <T : Comparable<T>> max(a: T, b: T): T {
    return if (a > b) a else b   // OK: Comparable has compareTo(), so > works
}

max(3, 5)            // T = Int, Int : Comparable<Int> ✓
max("apple", "fig")  // T = String, String : Comparable<String> ✓
max(listOf(1), listOf(2))  // COMPILE ERROR: List is not Comparable
```

**The implicit default bound:** When you write `<T>` with no bound, the implicit bound is `T : Any?` — T can be any type including nullable types. If you write `<T : Any>`, T cannot be nullable:

```kotlin
fun <T> acceptsNull(value: T) { }
acceptsNull<String?>(null)  // OK — T : Any? by default, nullable allowed

fun <T : Any> refusesNull(value: T) { }
refusesNull<String?>(null)  // COMPILE ERROR: String? doesn't satisfy T : Any
refusesNull<String>("hello")  // OK — String : Any ✓
```

This is why generic functions that call `value.hashCode()` or do null-unsafe operations need `T : Any`.

---

### Multiple Upper Bounds: `where T : A, T : B`

A type parameter can only have ONE bound in the `<T : Bound>` syntax. For multiple bounds, use the `where` clause:

```kotlin
// T must be both Serializable AND Comparable<T>:
fun <T> sortAndSave(list: List<T>): List<T>
        where T : Serializable,
              T : Comparable<T> {
    return list.sorted()     // OK: Comparable<T> provides sorted()
    // and then serialize... // OK: Serializable interface available
}
```

At the call site, T must satisfy ALL constraints:
```kotlin
sortAndSave(listOf(1, 2, 3))     // Int : Serializable AND Int : Comparable<Int> ✓
sortAndSave(listOf(File(".")))   // File : Serializable AND File : Comparable<File>?
                                 // File is Comparable<File> ✓
sortAndSave(listOf(listOf(1)))   // List is NOT Serializable → COMPILE ERROR
```

---

### Recursive (Self-Referential) Bounds

Some bounds reference the type parameter itself. The most common pattern is `T : Comparable<T>` — "T can be compared with itself":

```kotlin
fun <T : Comparable<T>> clamp(value: T, min: T, max: T): T {
    return when {
        value < min -> min   // uses Comparable<T>.compareTo
        value > max -> max
        else -> value
    }
}

clamp(5, 1, 10)         // T = Int, uses Int.compareTo(Int)
clamp("c", "a", "z")    // T = String, uses String.compareTo(String)
```

Another common pattern in builder DSLs:
```kotlin
// Builder pattern: each method returns THIS type (not the base Builder type)
abstract class Builder<T : Builder<T>> {
    abstract fun self(): T

    fun setName(name: String): T {
        this.name = name
        return self()  // returns the concrete subtype, not Builder<T>
    }
}

class UserBuilder : Builder<UserBuilder>() {
    override fun self() = this
}

UserBuilder()
    .setName("Alice")  // returns UserBuilder (not Builder<UserBuilder>)
    .build()
```

---

### Bounds in JVM Bytecode: The Erased Type

At runtime, bounds are erased just like all generic information. The JVM sees the **upper bound type** (or `Object` if no bound):

```kotlin
// Source:
fun <T : Number> process(value: T): Double = value.toDouble()
```

```bytecode
; Compiled bytecode:
process(Ljava/lang/Number;)D    ; T erased to its bound: Number
; NOT process(Ljava/lang/Object;)D  -- the bound determines the erasure!
```

This means:
- With `T : Number` → T erases to `Number`
- With `T : Any` → T erases to `Object`
- With no bound (implicit `T : Any?`) → T erases to `Object`
- With `T : Serializable` → T erases to `Serializable`

The erased type is what the JVM uses for casting and method lookup. Using `T : Number` means the JVM can call `Number` methods directly without any cast.

---

### Use Case: Bounds in Android/Kotlin APIs

```kotlin
// Real pattern: bound ensures the ViewModel is properly typed
inline fun <reified VM : ViewModel> Fragment.viewModels(): VM {
    // VM must be a ViewModel or subclass — ensures lifecycle attachment
    return ViewModelProvider(this)[VM::class.java]
}

// Usage:
val viewModel: MyViewModel by viewModels()
// T = MyViewModel, MyViewModel : ViewModel ✓
```

```kotlin
// Bound to ensure we can log anything that has a tag:
interface Loggable { val tag: String }

fun <T : Loggable> logAll(items: List<T>) {
    items.forEach { println("[${it.tag}] $it") }  // .tag available because T : Loggable
}
```

---

### Star Projection vs Bound — When to Use Each

```kotlin
// Star projection: I don't care what T is, I won't produce or use T
fun printList(list: List<*>) {
    list.forEach { println(it) }  // item is Any? — minimal info
}

// Bounded: I need T to have specific capabilities
fun sumList(list: List<out Number>): Double {
    return list.sumOf { it.toDouble() }  // .toDouble() available because : Number
}
```

| | Star Projection `List<*>` | Bounded `List<out Number>` |
|---|---|---|
| Element type available as | `Any?` | `Number` |
| Can call Number methods | No | Yes |
| Caller can pass | `List<String>`, `List<Int>`, anything | Only `List<Number>` or subtypes |
| Use when | Don't care about element type | Need element behavior |

> **Key Takeaway:** Type bounds are what let generic functions be useful rather than just holding `Any?`. `T : Number` means "I can call Number's methods on T"; `T : Comparable<T>` means "T can be sorted"; `T : Any` means "T is guaranteed non-null". At the JVM level, T erases to its upper bound — so `T : Number` compiles to use `Number` as the static type, with no cast needed.

---

## Master Summary: Generics and Variance in 6 Points

```
┌──────────────────────────────────────────────────────────────────────┐
│  1. TYPE ERASURE: List<String> and List<Int> are both just List at  │
│     runtime. The JVM doesn't see type parameters.                   │
│                                                                      │
│  2. COVARIANCE (out T): Container<Dog> IS-A Container<Animal>.      │
│     Safe because the container can only READ elements.              │
│     Dog IS-A Animal, so reading Dog gives Animal — fine.            │
│                                                                      │
│  3. CONTRAVARIANCE (in T): Container<Animal> IS-A Container<Dog>.   │
│     Safe because the container can only WRITE (accept) elements.    │
│     Writing a Dog to an Animal-acceptor is safe: Dog IS-A Animal.   │
│                                                                      │
│  4. INVARIANCE (default): MutableList<Dog> is neither subtype nor   │
│     supertype of MutableList<Animal>. Can both read and write.      │
│                                                                      │
│  5. REIFIED: Inline function pasted at call site → T is concrete    │
│     there → compiler substitutes T → defeats erasure locally.       │
│                                                                      │
│  6. TYPE BOUNDS constrain what T can be substituted with.          │
│     T : Number gives T all of Number's methods; T : Any forbids    │
│     nullable. Multiple bounds use `where`. T erases to its upper   │
│     bound in bytecode, not to Object.                              │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Master Chain D — Generics to Reified

```
Type erasure: List<String> == List at runtime
   │
   └── is List<String> fails (erased type check)
        │
        └── out/in are compile-time only (erased in bytecode)
             │
             └── reified requires inline
                  │
                  └── inline pastes body at call site
                       │
                       └── T is concrete at call site
                            │
                            └── startActivity<T>() pattern
```

---

*← [Phase 2.5 — Initialization](02_5_initialization_mechanics.md) | [Phase 4 — Functions & Lambdas →](04_functions_lambdas_inlining.md)*
