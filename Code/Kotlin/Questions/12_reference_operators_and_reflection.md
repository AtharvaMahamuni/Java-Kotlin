# Phase 12 — Reference Operators and Reflection

> The `::` operator doesn't call a function — it wraps it in an anonymous class. `KClass` is Kotlin's reflection mirror that exposes metadata the JVM's `Class` never had. Both topics follow directly from how anonymous classes and type erasure work.

## Navigation

[← Phase 11 — Flow](11_flow.md) | [→ Phase 13 — Android Architecture](13_android_architecture.md)

## Questions in This File

- [Q12.1 — `::` Function and Property References](#q121----function-and-property-references)
- [Q12.2 — `KClass` vs `Class`](#q122--kclass-vs-class)

---

# Q12.1 — `::` Function and Property References

> **Builds on:** [Q4.1 (lambda = anonymous class)](04_functions_lambdas_inlining.md#q41--lambda-compilation) · [Q4.3 (inline eliminates the object)](04_functions_lambdas_inlining.md#q43--inline-noinline-crossinline)
> **Connects to:** [Q3.3 (reified uses T::class)](03_generics_and_variance.md#q33--reified-type-parameters) · [Q12.2 (KClass)](#q122--kclass-vs-class)

---

## The Core Rule

```
::greet == { s -> greet(s) }
Both compile to an anonymous class implementing FunctionN.
The only difference: :: names an existing function; lambda has its own body.
```

---

## What `::` Compiles To

```kotlin
fun greet(name: String): String = "Hello, $name!"
val ref = ::greet
```

```java
// Decompiled — same structure as a lambda:
Function1<String, String> ref = new Function1<String, String>() {
    @Override
    public String invoke(String name) {
        return GreetingKt.greet(name);   // delegates to the actual function
    }
};
```

Non-capturing function references are **singletons** — the compiler emits one instance per reference and reuses it:

```kotlin
val a = ::greet
val b = ::greet
// a === b → true (same singleton object)
```

Capturing references (bound to an instance) are **new objects per use**:

```kotlin
val a = myObj::method   // captures myObj → new object
val b = myObj::method   // different object
// a === b → false
```

---

## Bound vs Unbound — The Arity Rule

The rule: unbound adds the receiver as the first parameter.

```
UNBOUND: String::length     → (String) -> Int      arity = 1
BOUND:   "hello"::length    → () -> Int             arity = 0 (receiver captured)
```

```kotlin
// Unbound — receiver becomes the parameter:
val strLength: (String) -> Int = String::length
strLength("hello")  // 5

// Bound — receiver is captured:
val boundLength: () -> Int = "hello"::length
boundLength()       // 5, always "hello".length
```

```
UNBOUND:  String::length              BOUND:  "hello"::length
┌─────────────────────┐               ┌─────────────────────┐
│  (String) → Int     │               │  () → Int           │
│  receiver = param   │               │  receiver captured  │
│  arity = 1          │               │  arity = 0          │
└─────────────────────┘               └─────────────────────┘
```

**Practical usage:**

```kotlin
val names = listOf("Alice", "Bob", "Charlie")

names.map(String::uppercase)       // unbound — each String is the receiver
names.sortedBy(String::length)     // unbound — each String is the receiver

val fmt = DateTimeFormatter.ofPattern("yyyy-MM-dd")
dates.map(fmt::format)             // bound — fmt captured as receiver
```

---

## Property References — `KProperty1`

```kotlin
data class Box(val value: Int)

val ref: KProperty1<Box, Int> = Box::value
//       KProperty1<T, R>:  T = receiver type, R = return type

val box = Box(42)
ref.get(box)    // 42 — calls the getter
```

`KProperty` hierarchy at a glance:

```
KProperty0<R>       — top-level property or property with no receiver
KProperty1<T, R>    — member property (T = the object, R = the type)
KProperty2<D, E, R> — extension property with explicit receiver
```

For `var` properties, `KMutableProperty1.set(box, newValue)` calls the setter.

---

## `inline` + `::` — Zero Allocation

```kotlin
inline fun <T> List<T>.myFilter(pred: (T) -> Boolean): List<T> = filter(pred)

fun isEven(n: Int) = n % 2 == 0

val result = listOf(1, 2, 3, 4).myFilter(::isEven)
// myFilter is inline → pred body pasted at call site
// ::isEven anonymous class is NEVER created
```

When the function receiving `::` is `inline`, the reference object is eliminated entirely. This is the primary reason to prefer passing `::method` over lambdas to inline functions.

---

## Kotlin `::` vs Java `::` — Bytecode Difference

```
Kotlin ::   → anonymous class implementing FunctionN (heap object)
Java   ::   → INVOKEDYNAMIC + LambdaMetafactory (JVM creates at runtime via method handles)
```

Java's approach can be more GC-efficient. Kotlin chose anonymous classes for Android compatibility (pre-Java-8 ART) and compensates with `inline`.

---

## ## Traps

**Trap 1 — Bound reference captures instance; can prevent GC:**

```kotlin
class HeavyObject {
    val ref = this::someMethod   // captures `this` → HeavyObject can't be GC'd
}
```

**Trap 2 — Unbound vs bound arity confusion in higher-order functions:**

```kotlin
// WRONG — type mismatch:
val fn: () -> Int = String::length   // needs (String) -> Int, not () -> Int

// CORRECT — bind first:
val fn: () -> Int = "hello"::length
```

**Trap 3 — Non-capturing singleton only applies to TOP-LEVEL non-capturing references. Member references are not singletons:**

```kotlin
val a = String::length   // top-level/unbound → likely singleton
val b = obj::method      // bound → new object
```

---

## Memory Trick

```
:: = anonymous class FunctionN (same as lambda, different body).
  Non-capturing → singleton (compiler shares one instance).
  Capturing (bound) → new object per use.

UNBOUND: Type::member   → receiver becomes first parameter (arity +1).
BOUND:   obj::member    → receiver captured (arity stays same).

inline + :: = zero allocation (body pasted, object never created).

Property reference: Box::value → KProperty1<Box, Int>.
  .get(box) → calls getter.
  .set(box, v) → calls setter (only if KMutableProperty1).
```

---

## Self-Test

1. What JVM construct does `::greet` compile to? How does it differ from `{ s -> greet(s) }`?
2. Why does `String::length` have arity 1 but `"hello"::length` have arity 0?
3. `names.map(String::uppercase)` — is `String::uppercase` a new object per call? Why or why not?
4. When does passing `::` to a function result in zero allocation? What's the mechanism?
5. What is `KProperty1<Box, Int>` and how do you read and write through it?

---

# Q12.2 — `KClass` vs `Class`

> **Builds on:** [Q12.1 (:: creates objects)](12_reference_operators_and_reflection.md#q121----function-and-property-references) · [Q3.3 (reified delivers T::class)](03_generics_and_variance.md#q33--reified-type-parameters)
> **Connects to:** [Q3.1 (type erasure — reflection defeats it)](03_generics_and_variance.md#q31--type-erasure)

---

## The Core Rule

```
T::class        → KClass<T>   (Kotlin reflection — Kotlin-specific metadata)
T::class.java   → Class<T>    (Java reflection  — available everywhere)

Same underlying class, two different mirrors.
```

---

## What Each Exposes

```kotlin
val kc = User::class     // KClass<User>
val jc = User::class.java  // Class<User>
```

**KClass only** (Kotlin metadata — not in Class):

```kotlin
kc.isData           // true — it's a data class
kc.isSealed         // false
kc.isOpen           // false (final by default)
kc.isAbstract       // false
kc.isCompanion      // false
kc.objectInstance   // null (not an object singleton)
kc.primaryConstructor    // KFunction — the primary constructor
kc.memberProperties      // all Kotlin properties as KProperty set
kc.sealedSubclasses      // only on sealed — list of all subclasses
```

**Class only** (Java APIs):

```kotlin
jc.getDeclaredMethods()           // raw Java methods
jc.getDeclaredFields()            // raw Java fields
jc.getAnnotation(Foo::class.java) // Java annotation access
jc.isEnum()
```

---

## Instance vs Type Reference — Runtime vs Compile-Time

```kotlin
class Widget
class Button : Widget()

val btn: Widget = Button()    // declared as Widget, actual is Button

btn::class      // KClass<Button>  — RUNTIME type (the actual object)
Widget::class   // KClass<Widget>  — COMPILE-TIME type (declared type)
```

This follows the same rule as Java's `getClass()`:

```java
Widget btn = new Button();
btn.getClass()   // → Button.class (runtime type, not Widget.class)
```

**Why covariant?** `btn::class` returns `KClass<out Button>`. Because `btn` is declared as `Widget`, the compiler can only guarantee the runtime class is *at most* `Button` — it could be a deeper subtype.

---

## Decompiled — How `T::class` Works

```kotlin
val kc: KClass<String> = String::class
```

```java
// Decompiled:
KClass<String> kc = Reflection.getOrCreateKotlinClass(String.class);
// KClass is a wrapper around Class that adds Kotlin metadata.
// Kotlin reflection adds metadata via a separate .kotlin_module file + annotations.
```

`KClass<T>` is backed by the same `Class<T>` — it's a Kotlin wrapper that reads extra metadata stored in annotations generated by the Kotlin compiler.

---

## Which to Use — Library Decision Table

| Library / Use | Needs | How |
|---|---|---|
| Gson | `Class<T>` | `T::class.java` |
| Retrofit | `Class<T>` | `T::class.java` |
| Hilt/Dagger | `Class<T>` | `T::class.java` |
| Kotlin Serialization | `KClass<T>` / `KSerializer<T>` | `T::class` or `serializer()` |
| Kotlin Reflect API | `KClass<T>` | `T::class` |
| `isData`, `isSealed` checks | `KClass<T>` | `T::class` |

---

## ## Traps

**Trap 1 — Using `KClass` with Java-only APIs:**

```kotlin
// WRONG — Gson expects Class, not KClass:
Gson().fromJson(json, User::class)       // compile error

// CORRECT:
Gson().fromJson(json, User::class.java)  // Class<User>
```

**Trap 2 — Instance `::class` is the runtime type, not the declared type:**

```kotlin
fun printType(w: Widget) = println(w::class.simpleName)
printType(Button())    // prints "Button", not "Widget"
// Interviewers love this — it surprises people who expect Widget
```

**Trap 3 — Reflection requires `kotlin-reflect` dependency. `KClass` without it is limited:**

```kotlin
User::class.primaryConstructor   // throws if kotlin-reflect is not on classpath
User::class.isData               // same — metadata access requires kotlin-reflect
User::class.java                 // always works — no extra dependency
```

---

## Memory Trick

```
KClass = KOTLIN metadata wrapper.  T::class → KClass<T>.
Class  = JAVA reflection.          T::class.java → Class<T>.

KClass-only: isData, isSealed, sealedSubclasses, primaryConstructor, memberProperties.
Class-only:  getDeclaredMethods(), Java annotations, isEnum().

INSTANCE::class → runtime type (actual object's class). Like Java's getClass().
TYPE::class     → compile-time type (declared class).

Library rule: Java libs (Gson, Retrofit, Hilt) → need Class → use .java
              Kotlin libs (kotlinx.serialization, Reflect) → need KClass → use ::class

kotlin-reflect needed for: primaryConstructor, memberProperties, isData, isSealed.
```

---

## Self-Test

1. What is the difference between `btn::class` and `Widget::class` when `btn` is declared as `Widget` but holds a `Button`?
2. `User::class.isData` — does this work without `kotlin-reflect` on the classpath?
3. You're integrating with Gson. Do you pass `User::class` or `User::class.java`? Why?
4. At the JVM level, is `KClass<String>` the same object as `Class<String>`? What is `KClass` built on top of?
5. What does `Result::class.sealedSubclasses` return? Why does this require `KClass` and not `Class`?

---

## Phase 12 — Summary

```
┌──────────────────────────────────────────────────────────────────┐
│  :: = anonymous class FunctionN.                                 │
│    Non-capturing → singleton. Capturing/bound → new object.     │
│    inline + :: = zero allocation.                               │
│                                                                  │
│  Bound: obj::method   arity stays same. Receiver captured.     │
│  Unbound: Type::method arity +1. Receiver is first parameter.  │
│                                                                  │
│  KClass = Kotlin metadata mirror of Class.                      │
│    T::class → KClass. T::class.java → Class.                   │
│    KClass adds: isData, isSealed, primaryConstructor, etc.     │
│    Requires kotlin-reflect for most metadata operations.       │
│                                                                  │
│  INSTANCE::class → runtime type (like getClass()).             │
│  TYPE::class     → compile-time declared type.                 │
└──────────────────────────────────────────────────────────────────┘
```

---

*← [Phase 11 — Flow](11_flow.md) | [Phase 13 — Android Architecture →](13_android_architecture.md)*