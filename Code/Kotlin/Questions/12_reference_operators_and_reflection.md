# Phase 12: Reference Operators and Reflection

## Navigation
| Phase | File |
|-------|------|
| 11 — Flow | [11_flow.md](11_flow.md) |
| **12 — Reference Operators & Reflection** | ← You are here |
| 13 — Android Architecture | [13_android_architecture.md](13_android_architecture.md) |

---

## Q12.1 — `::` Operators

> **Builds on:** [Q4.1 — Lambda anonymous class](04_functions_lambdas_inlining.md#q41--lambda-compilation) · [Q4.2 — inline](04_functions_lambdas_inlining.md#q42--inline-noinline-crossinline)
> **Reference:** [Kotlin Docs — Callable References](https://kotlinlang.org/docs/reflection.html#callable-references)

### First Principles: What Is a Function Reference?

A function reference (`::myFun`) is a way to treat a function as a first-class value — to pass it around without calling it. It's essentially a shorthand for creating a lambda that calls the function:

```kotlin
fun double(x: Int) = x * 2

// Lambda (creates new object each time if capturing):
val d1: (Int) -> Int = { x -> double(x) }

// Function reference (more efficient, expresses intent clearly):
val d2: (Int) -> Int = ::double
```

### What Anonymous Class Does a Function Reference Compile To?

```kotlin
fun greet(name: String): String = "Hello, $name!"
val ref = ::greet
```

**Decompiled Java:**
```java
// Function reference compiles to the same FunctionN anonymous class as a lambda:
Function1<String, String> ref = new Function1<String, String>() {
    @Override
    public String invoke(String name) {
        return GreetingKt.greet(name);  // delegates to the actual function
    }
};
```

Like lambdas, non-capturing function references can be **singletons** — the compiler may share one instance:

```kotlin
// top-level non-capturing function reference — likely a singleton:
val ref1 = ::greet
val ref2 = ::greet
// ref1 === ref2 may be true (same singleton object)
```

### Bound vs Unbound References — The Arity Difference

**Unbound reference** — the receiver must be provided explicitly (adds one parameter):

```kotlin
// Unbound: String is NOT bound to a specific instance
val strLength: (String) -> Int = String::length
// Has arity 1: you must pass the String
strLength("hello")  // 5
strLength("world")  // 5
```

**Bound reference** — the receiver is fixed to a specific instance:

```kotlin
val hello = "hello"
val boundLength: () -> Int = hello::length  // receiver IS "hello"
// Has arity 0: no argument needed — receiver is already bound
boundLength()  // 5 — always "hello".length
```

```
Unbound: String::length           Bound: "hello"::length
┌──────────────────────┐          ┌──────────────────────┐
│  (String) → Int      │          │  () → Int             │
│  receiver as param   │          │  receiver captured    │
│  String::length("hi")│          │  "hello"::length()   │
└──────────────────────┘          └──────────────────────┘
Arity = 1                         Arity = 0
```

**Practical example:**
```kotlin
val names = listOf("Alice", "Bob", "Charlie")

// Unbound — provides method reference; each String is the receiver:
names.map(String::uppercase)       // ["ALICE", "BOB", "CHARLIE"]
names.sortedBy(String::length)     // ["Bob", "Alice", "Charlie"]

// Bound — specific object's method:
val formatter = DateTimeFormatter.ofPattern("yyyy-MM-dd")
dates.map(formatter::format)       // formatter is bound receiver
```

### Property References — `KProperty1`

Property references use the `KProperty` hierarchy:

```kotlin
data class Box(val value: Int)

// Property reference:
val valueRef: KProperty1<Box, Int> = Box::value
//            ^ KProperty1<T, R> — T = receiver type, R = property type

val box = Box(42)
valueRef.get(box)  // 42 — calls the getter
```

`KProperty1` vs `KProperty0`:
- `KProperty0` — top-level property or property with no receiver: `::someTopLevelProp`
- `KProperty1<T, R>` — member property: `T::property` (needs a receiver of type T to get)
- `KProperty2<D, E, R>` — extension property with explicit receiver

### Kotlin `::` vs Java `::` — Bytecode Difference

**Kotlin `::` → anonymous class** (as described above)

**Java `::` → `invokedynamic` + `LambdaMetafactory`**:
```java
// Java 8+:
Function<String, Integer> ref = String::length;
// Compiles to INVOKEDYNAMIC — the JVM creates the lambda object lazily,
// potentially using method handles, not an anonymous class
```

Kotlin chose anonymous classes for predictability and to support pre-Java-8 (Android). The JVM's `LambdaMetafactory` approach can be more efficient for GC but Kotlin compensates with `inline`.

### When Passing `::function` to an `inline` Function Eliminates the Object

```kotlin
inline fun <T> List<T>.myFilter(predicate: (T) -> Boolean): List<T> {
    return filter(predicate)  // inline — predicate is pasted, not an object
}

fun isEven(n: Int) = n % 2 == 0

val result = listOf(1, 2, 3, 4).myFilter(::isEven)
// Because myFilter is inline, ::isEven's anonymous class is never created!
// The predicate call is inlined as: if (isEven(it)) ...
```

---

## Q12.2 — `KClass` vs `Class`

> **Reference:** [Kotlin Docs — Reflection](https://kotlinlang.org/docs/reflection.html)

### `KClass<T>` vs `Class<T>` — The Difference

`Class<T>` is the Java reflection API — it's been in Java since version 1.1. `KClass<T>` is Kotlin's reflection API that adds Kotlin-specific metadata that `Class` doesn't have.

```kotlin
val kotlinClass: KClass<String> = String::class       // Kotlin's KClass
val javaClass: Class<String> = String::class.java     // Java's Class
// Or:
val javaClass2: Class<String> = String.javaClass       // from an instance
```

### What `KClass` Exposes That `Class` Doesn't

```kotlin
data class User(val name: String, val age: Int)
sealed class Result<out T>

val userKClass = User::class

// Kotlin-specific metadata (not in Java Class):
userKClass.isData          // true — data class!
userKClass.isSealed        // false
userKClass.isOpen          // false (final by default)
userKClass.isAbstract      // false
userKClass.isCompanion     // false
userKClass.objectInstance  // null (not an object)
userKClass.primaryConstructor  // KFunction — the primary constructor!
userKClass.memberProperties    // Set of all properties

val resultKClass = Result::class
resultKClass.isSealed          // true!
resultKClass.sealedSubclasses  // [KClass<Result.Success>, KClass<Result.Error>, ...]
```

These are impossible to get from Java's `Class`:
```java
// Java Class API:
Class<User> userClass = User.class;
userClass.isEnum();        // false
userClass.isInterface();   // false
// No isData(), isSealed(), primaryConstructor()!
```

### `widget::class` vs `Widget::class`

```kotlin
class Widget
class Button : Widget()

val btn = Button()

// Instance reference — gets the ACTUAL runtime type:
val instanceClass = btn::class  // KClass<Button> (Button, not Widget!)

// Type reference — gets the declared type:
val typeClass = Widget::class   // KClass<Widget>
```

The instance reference uses the **actual runtime type** (most specific class). This follows the same principle as `getClass()` in Java:

```java
Widget btn = new Button();
btn.getClass()  // → Button.class (runtime type, not declared type)
```

**Covariance:** `btn::class` returns `KClass<out Button>` (covariant), because you can get a more specific type from an instance typed as a supertype.

### When Do You Need `KClass` vs `Class`?

| Library/Use Case | Needs | How to get |
|-----------------|-------|-----------|
| Gson | `Class<T>` | `T::class.java` |
| Moshi | Either (reflection = Class, codegen = KClass) | varies |
| Retrofit | `Class<T>` | `T::class.java` |
| Kotlin Serialization | `KClass<T>` or `KSerializer<T>` | `T::class` or `serializer()` |
| Hilt/Dagger | `Class<T>` (Java DI) | `T::class.java` |
| Kotlin Reflect | `KClass<T>` | `T::class` |

```kotlin
// Common pattern: get both easily
val kClass = User::class          // KClass<User>
val jClass = User::class.java     // Class<User>
// or
val jClass2 = javaClass<User>()   // alternative
```

---

## Master Summary: References and Reflection in 4 Points

```
┌──────────────────────────────────────────────────────────────────────┐
│  1. `::fun` creates an anonymous class implementing FunctionN.       │
│     Bound references (instance::method) have N-1 arity.             │
│     Unbound references (Type::method) have N arity (receiver first). │
│                                                                       │
│  2. Property references implement KProperty1<T, R> — need a          │
│     receiver to get the value. Use .get(instance) to access.        │
│                                                                       │
│  3. KClass is Kotlin's reflection type: exposes isData, isSealed,   │
│     primaryConstructor, sealedSubclasses — unavailable in Class.    │
│     Get it with T::class; get Class with T::class.java.             │
│                                                                       │
│  4. Instance::class returns the RUNTIME type. Type::class returns    │
│     the COMPILE-TIME type. This matters for polymorphic objects.    │
└──────────────────────────────────────────────────────────────────────┘
```

---

*← [Phase 11 — Flow](11_flow.md) | [Phase 13 — Android Architecture →](13_android_architecture.md)*
