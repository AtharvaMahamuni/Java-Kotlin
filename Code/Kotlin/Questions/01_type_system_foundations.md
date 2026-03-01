# Phase 1: Type System Foundations

## Navigation
[← Master Index](master_chains.md)

## Questions in This File
- [Q1.1 — `val` vs `const val`](#q11--val-vs-const-val)
- [Q1.2 — Nullability at the Type Level](#q12--nullability-at-the-type-level)
- [Q1.3 — `Nothing`, `Unit`, and the Type Hierarchy](#q13--nothing-unit-and-the-type-hierarchy)
- [Q1.4 — Smart Casts](#q14--smart-casts)

---

## Q1.1 — `val` vs `const val`

> **Builds on:** [Q0.4 — JVM Call Stack & getter overhead](00_jvm_mental_model.md#q04--the-jvm-call-stack)
> **Connects to:** [Q2.3 (companion object and const)](02_classes_and_objects.md#q23--sealed-classes-and-interfaces) · [Q5.3 (delegates also generate methods)](05_properties_and_delegation.md#q53--delegates)

### First Principles: What is a `val`?

In Kotlin, `val` means **read-only** — you can only assign it once. But "read-only" at the language level does NOT mean "zero overhead." The compiler implements `val` as a **property with a getter** — a full method call.

### What Bytecode Does `val BASE_URL = "..."` Inside an `object` Compile To?

```kotlin
object ApiConfig {
    val BASE_URL = "https://api.example.com"
}
```

**Decompiled to Java:**
```java
public final class ApiConfig {
    private static final String BASE_URL = "https://api.example.com";
    public static final ApiConfig INSTANCE;

    static {
        INSTANCE = new ApiConfig();
        // BASE_URL is set via field initializer in <init>
    }

    // Generated getter — callers invoke this method!
    public final String getBASE_URL() {
        return BASE_URL;
    }
}
```

**Caller bytecode (Kotlin):**
```kotlin
val url = ApiConfig.BASE_URL
```
```bytecode
GETSTATIC ApiConfig.INSTANCE : LApiConfig;
INVOKEVIRTUAL ApiConfig.getBASE_URL ()Ljava/lang/String;
```

Every access to `ApiConfig.BASE_URL` invokes a getter method — a [virtual dispatch + stack frame push](00_jvm_mental_model.md#q04--the-jvm-call-stack). In a hot path (e.g., setting a header on every network request), this overhead adds up.

### What Does `const val` Emit at the Call Site?

```kotlin
object ApiConfig {
    const val BASE_URL = "https://api.example.com"
}
```

**Caller bytecode:**
```kotlin
val url = ApiConfig.BASE_URL
```
```bytecode
LDC "https://api.example.com"   ; literal string baked into the call site!
```

The string literal is copied **directly into every call site**. No class loading, no method call, no `INSTANCE` access. This is what "inlined as literal" means — the value is substituted at compile time.

### The Three Constraints on `const val`

`const val TAG = SomeClass::class.simpleName` fails because:

| Constraint | Reason | Example that fails |
|------------|--------|-------------------|
| **Must be primitive or String** | Only these types can be embedded as JVM constants (LDC instruction) | `const val obj = MyClass()` |
| **Must be initialized with a compile-time constant** | Value must be known at compile time (not at runtime) | `const val time = System.currentTimeMillis()` |
| **Must be top-level or in object/companion object** | Class-level constants only; local variables can't be const | `fun foo() { const val x = 1 }` |

`SomeClass::class.simpleName` fails constraint #2 — `simpleName` is a runtime reflection call.

### `@JvmField` vs `const val`

```kotlin
object Config {
    @JvmField val BASE_URL = "https://api.example.com"  // still NOT const
    const val TAG = "Config"                              // true constant
}
```

`@JvmField` removes the getter — it exposes the field directly in Java bytecode (`GETSTATIC`). But it still:
- Requires accessing `INSTANCE` first
- Triggers class loading on first access
- Has the value assigned at runtime (in `<clinit>`)

| Feature | `val` | `@JvmField val` | `const val` |
|---------|-------|-----------------|-------------|
| Getter generated | Yes | **No** (direct field) | **No** (inlined) |
| Class loading required | Yes | Yes | **No** |
| Runtime assignment | Yes | Yes | **No** (compile-time) |
| Java access syntax | `Config.Companion.getBASE_URL()` | `Config.BASE_URL` | `Config.TAG` |
| Allowed types | Any | Any | Primitives + String only |
| Binary compatibility | Getter can change body | Field exposed (breaking to remove `@JvmField`) | Value baked into callers (breaking to change!) |

> **Interview Trap:** `const val` inlining is a **binary compatibility hazard** for library authors. If you publish a library with `const val VERSION = "1.0"` and change it to `"2.0"`, callers that haven't recompiled will still use `"1.0"` — it was baked into their bytecode!

---

## Q1.2 — Nullability at the Type Level

> **Connects to:** [Q5.1 (lateinit null sentinel)](05_properties_and_delegation.md#q51--lateinit-internals) · [Q2.5.3 (null in open function init trap)](02_5_initialization_mechanics.md#q253--inheritance-initialization-order)

### Are `String` and `String?` Different JVM Types?

**No.** At the [JVM level](00_jvm_mental_model.md#q02--jvm-type-mapping), both are `java.lang.String`. Kotlin's null-safety is **entirely a compile-time construct**.

```kotlin
val a: String = "hello"    // JVM type: java.lang.String
val b: String? = "world"   // JVM type: java.lang.String  ← same!
val c: String? = null      // JVM type: java.lang.String reference = null
```

The difference is enforced by the Kotlin compiler:
- `String` → compiler adds `@NotNull` annotation + null-check at every assignment
- `String?` → compiler adds `@Nullable` annotation + allows null

### `@NotNull` and `@Nullable` — Compile Time vs Runtime

**Compile time:** The Kotlin compiler reads these annotations to enforce null-safety rules. `@NotNull` on a parameter means the compiler verifies you never pass null.

**Runtime:** When Kotlin code is called **from Java**, the null check is enforced by an `Intrinsics.checkNotNullParameter()` call generated at the function entry point.

```kotlin
fun greet(name: String) {  // @NotNull in bytecode
    println("Hello, $name")
}
```

```java
// Decompiled — runtime null check for Java callers:
public static final void greet(@NotNull String name) {
    Intrinsics.checkNotNullParameter(name, "name");  // throws NPE if null from Java
    System.out.println("Hello, " + name);
}
```

**Exact bytecode position — the null check is the very first instruction in the method body:**

```bytecode
; fun greet(name: String)
ALOAD_0                                                                             ; push 'name' onto the stack
LDC "name"                                                                          ; push parameter name literal
INVOKESTATIC kotlin/jvm/internal/Intrinsics.checkNotNullParameter (Ljava/lang/Object;Ljava/lang/String;)V
; ↑ executed BEFORE any local variables, BEFORE println — fail-fast position

; only if null check passes does execution continue here:
GETSTATIC java/lang/System.out : Ljava/io/PrintStream;
; ... string concatenation for "Hello, $name" ...
INVOKEVIRTUAL java/io/PrintStream.println (Ljava/lang/Object;)V
RETURN
```

The null check runs **before any work**. If `name` is `null` (passed from Java), the exception is thrown immediately with a clear message: `"Parameter specified as non-null is null: method greet, parameter name"` — pinpointing which parameter violated the contract, before any side effects occur.

**For constructors**, this means: if a non-null constructor parameter is passed `null` from Java, the exception is thrown before ANY field initialization runs — the object is never partially constructed.

### Platform Types (`String!`) — The Silent Danger

When Kotlin calls Java code, the return type is unknown — Java has no nullability annotations. Kotlin represents this as a **platform type** (`String!`), meaning "I don't know if this is nullable or not — trust the programmer."

```kotlin
// Java class:
public class JavaUser {
    public String getName() { return null; }  // no @Nullable annotation
}

// Kotlin calling it:
val user = JavaUser()
val name: String = user.getName()  // Platform type String! — compiles fine!
// At runtime: name = null → NPE when you use it later → hard to debug!

// Safe approach:
val name: String? = user.getName()  // explicit nullable — forces null handling
```

**Why it's dangerous:** The compiler trusts you. If Java returns `null` and you assigned it to `String` (non-nullable), you won't get a compile error — you'll get a NPE later, far from the source.

```
Platform Type Danger Zone:
┌─────────────────────────────────────────────────────┐
│  Java API returns String (no annotation)            │
│         │                                           │
│         ▼                                           │
│  Kotlin sees: String!  (could be null or not null)  │
│         │                                           │
│         ├─── val x: String = java.getName()  ─ ─ ─ ┤
│         │    (compiles! but NPE risk at runtime)    │
│         │                                           │
│         └─── val x: String? = java.getName() ───── │
│              (safe — forces null check)             │
└─────────────────────────────────────────────────────┘
```

### When Does `?:` Generate a Branch vs Get Eliminated?

```kotlin
// Case 1: Elvis with non-null literal — generates null check branch
val result = maybeNull ?: "default"
```

```bytecode
; bytecode for ?: "default"
ALOAD maybeNull
DUP
IFNONNULL skip_else    ; branch: if not null, skip the else branch
POP
LDC "default"
skip_else:
ASTORE result
```

```kotlin
// Case 2: Elvis where the compiler can prove non-null — eliminated
val x: String = "always here"
val result = x ?: "default"   // compiler warning: Elvis branch is always false
// Compiler eliminates the branch entirely
```

> **Key Takeaway:** `?:` is not zero-cost. It's a null check + conditional branch in bytecode. The compiler eliminates it only when it can statically prove non-nullability.

---

## Q1.3 — `Nothing`, `Unit`, and the Type Hierarchy

> **Connects to:** [Q2.3 (sealed class Error carries Nothing)](02_classes_and_objects.md#q23--sealed-classes-and-interfaces) · [Q3.2 (variance positions)](03_generics_and_variance.md#q32--variance)

### Kotlin's Complete Type Hierarchy

```
                        Any
                         │
          ┌──────────────┼──────────────────┐
          │              │                  │
        String          Int               MyClass
          │              │                  │
          │              │                  │
          └──────────────┴──────────────────┘
                         │
                    (all types)
                         │
                       null  (for nullable types: String?, Int?)
                         │
                       Nothing   ← subtype of EVERY type
```

**`Nothing` is the bottom type** — it is a subtype of every other type. No value can ever be of type `Nothing` at runtime (it's uninhabitable). It represents "this code path never returns normally."

### Why Does `throw` Have Type `Nothing`?

```kotlin
fun fail(msg: String): Nothing = throw IllegalStateException(msg)
```

`throw` never completes normally — it transfers control via exception. Its type is `Nothing` because it fits into ANY expected type:

```kotlin
val name: String = user?.name ?: throw IllegalArgumentException("no name")
//                                ↑ throw has type Nothing
//                                  Nothing is a subtype of String
//                                  So the ?: expression has type String ✓
```

This is why `throw` works in `when`, `if`, and `?:` expressions — `Nothing` is compatible with any type.

```kotlin
// when expression requiring String:
val label: String = when(result) {
    is Success -> result.data.name     // String
    is Error -> throw RuntimeException("error!")  // Nothing → compatible with String
}

// if expression requiring Int:
val count: Int = if (isValid) list.size else throw Exception()  // Nothing is-a Int
```

### `Unit` vs `void` at JVM Level

```kotlin
fun doWork(): Unit { println("working") }
```

```java
// Decompiled:
public static final void doWork() {
    System.out.println("working");
    // return void — JVM RETURN instruction with no value
}
```

**Key difference:** `Unit` is an actual **object** in Kotlin (`kotlin.Unit`), a singleton. `void` is the absence of a return value.

```kotlin
// Unit can be used as a type parameter — void cannot!
val action: () -> Unit = { println("hi") }   // works fine

// Unit as generic:
fun <T> runAndReturn(block: () -> T): T = block()
val u: Unit = runAndReturn { println("hello") }   // T = Unit — valid!
```

```bytecode
// A function returning Unit:
GETSTATIC kotlin/Unit.INSTANCE : Lkotlin/Unit;  // push Unit singleton
ARETURN                                           // return as Object
```

### Why `Nothing` Works in `out` (Covariant) Positions

```kotlin
sealed class Result<out T> {
    class Success<T>(val data: T) : Result<T>()
    object Loading : Result<Nothing>()  // Nothing works here!
    object Error : Result<Nothing>()    // Nothing works here!
}
```

`out T` means `Result` is [**covariant**](03_generics_and_variance.md#q32--variance) — `Result<Nothing>` is a subtype of `Result<T>` for any `T`. Since `Nothing` is a subtype of everything, `Result<Nothing>` is a subtype of `Result<String>`, `Result<User>`, etc.

```kotlin
fun getResult(): Result<User> {
    return Result.Loading   // type: Result<Nothing>
    // Result<Nothing> is subtype of Result<User> ✓ (covariance + Nothing)
}
```

**Why `Nothing` fails in `in` (contravariant) positions:**

```kotlin
// Imagine: interface Sink<in T> { fun accept(value: T) }
// Sink<Nothing> would mean: "I accept values of type Nothing"
// But Nothing has no values — you can never call accept()!
// This is logically broken, so the compiler forbids it.
```

> **Key Takeaway:** `Nothing` makes the type system complete. `throw` and infinite loops have type `Nothing`, enabling exhaustive `when` expressions and clean sealed class hierarchies.

---

## Q1.4 — Smart Casts

> **Connects to:** [Q2.3 (sealed class exhaustiveness)](02_classes_and_objects.md#q23--sealed-classes-and-interfaces) · [Q3.1 (type erasure breaks is checks)](03_generics_and_variance.md#q31--type-erasure)

### What Conditions Enable a Smart Cast?

The Kotlin compiler performs **flow-sensitive type analysis**. After an `is` check, it knows the type — and narrows it automatically IF the value cannot have changed.

**Requirements for smart cast:**
1. The variable is **stable** — cannot be modified between the check and the use
2. Specifically: `val` local variables, `val` properties with no custom getter

```kotlin
fun process(input: Any) {
    if (input is String) {
        // Smart cast: input is now String inside this block
        println(input.length)  // no explicit cast needed!
    }
}
```

### Why `var` Properties Break Smart Cast

```kotlin
class Container {
    var value: Any = "hello"

    fun process() {
        if (value is String) {
            // COMPILE ERROR: Smart cast to 'String' is impossible,
            // because 'value' is a mutable property that could have been
            // changed by this time
            println(value.length)  // ← error!

            // Another thread could change `value` between the check and this line
        }
    }
}
```

```kotlin
// Fix: capture in local val
fun process() {
    val v = value   // captured in local val — stable!
    if (v is String) {
        println(v.length)   // Smart cast works ✓
    }
}
```

### Smart Cast Decision Tree

```
Is the variable stable?
├── Local val → ✓ Smart cast allowed
├── Local var → check if modified between is-check and use
│   ├── Not modified → ✓ Smart cast allowed (flow analysis)
│   └── Possibly modified → ✗ Smart cast rejected
├── val property (no custom getter) → ✓ Smart cast allowed
├── var property → ✗ Always rejected (another thread could modify)
└── Property with custom getter → ✗ Rejected (getter could return different value)
```

### `is` vs `as` — Bytecode Level

```kotlin
val x: Any = "hello"

// is — type check, no throw
if (x is String) { /* safe */ }
```
```bytecode
ALOAD x
INSTANCEOF java/lang/String  ; pushes 0 or 1 — no exception
```

```kotlin
// as — unsafe cast, throws ClassCastException if wrong
val s: String = x as String
```
```bytecode
ALOAD x
CHECKCAST java/lang/String   ; throws ClassCastException if not String
```

```kotlin
// as? — safe cast, returns null if wrong
val s: String? = x as? String
```
```bytecode
ALOAD x
DUP
INSTANCEOF java/lang/String
IFEQ cast_failed
CHECKCAST java/lang/String   ; only cast if INSTANCEOF was true
; ...
cast_failed:
ACONST_NULL
```

### Why Smart Cast Fails Through a Property Getter

```kotlin
class Box {
    private val _value: String? = "hello"
    val value: String? get() = _value  // custom getter!
}

fun use(box: Box) {
    if (box.value != null) {
        // COMPILE ERROR: smart cast failed!
        println(box.value.length)  // getter could return null on second call!
    }

    // Safe pattern: capture result
    val v = box.value
    if (v != null) {
        println(v.length)  // works: v is a stable local val
    }
}
```

The compiler cannot smart-cast through a getter because the getter is a **method call** — it could return a different value each time. Even if the backing field is `val`, the getter could be overridden in a subclass (see [Q2.1 — Class Modifiers](02_classes_and_objects.md#q21--class-modifiers)) to return null.

> **Key Takeaway:** Smart casts are a compile-time guarantee. The compiler only performs them when it can prove the value is stable. Always capture mutable/getter-accessed values into local `val` before type-checking.

---

## Master Chain A — Constants (Interview Chain)

```
val BASE_URL = "..."
   │
   ├── Compiles to getter (getBASE_URL)          [Q1.1]
   │   └── Caller invokes INVOKEVIRTUAL          [Q0.4]
   │
   const val TAG = "..."
   │
   ├── LDC instruction at call site              [Q1.1]
   ├── No class loading triggered                [Q0.3]
   └── Binary compat risk: value baked in        [Q1.1]
   │
   @JvmField val → direct field, still runtime  [Q1.1]
   │
   Why can't TAG = SomeClass::class.simpleName?
   └── simpleName is runtime reflection          [Q1.1, Q3.3]
```

---

*← [Phase 0 — JVM Mental Model](00_jvm_mental_model.md) | [Phase 2 — Classes and Objects →](02_classes_and_objects.md)*
