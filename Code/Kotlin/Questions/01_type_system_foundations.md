# Phase 1 — Type System Foundations

> Kotlin's type system operates at three layers: **language rules** (what you write), **compiler analysis** (what it proves), **JVM representation** (what actually runs). Every question in this phase connects these three.

## Navigation

[← Phase 0 — JVM Mental Model](phase0_jvm_mental_model_v3.md)

## Questions in This File

- [Q1.0 — var vs val](#q10--var-vs-val)
- [Q1.1 — val vs const val](#q11--val-vs-const-val)
- [Q1.2 — Nullability](#q12--nullability)
- [Q1.3 — Type Hierarchy: Any, Nothing, Unit](#q13--type-hierarchy-any-nothing-unit)
- [Q1.4 — Property vs Field](#q14--property-vs-field)
- [Q1.5 — Backing Fields](#q15--backing-fields)
- [Q1.6 — Smart Casts](#q16--smart-casts)
- [Q1.7 — Value Classes](#q17--value-classes)
- [Q1.8 — Contracts](#q18--contracts)
- [Q1.9 — Interview Traps](#q19--interview-traps)

---

# Q1.0 — var vs val

> **Connects to:** [Q0.1 (stack vs heap)](phase0_jvm_mental_model_v3.md#q01--primitives-vs-references-the-two-worlds) · [Q1.6 (smart casts require val)](#q16--smart-casts)

---

## The Core Rule

```
var = mutable reference    (can reassign)
val = read-only reference  (cannot reassign)
```

---

## Critical Distinction

```
val ≠ immutable OBJECT
val = immutable REFERENCE
```

The reference is locked. The object it points to is not.

---

## The Trap

```kotlin
val list = mutableListOf(1, 2)
list.add(3)     // ✅ allowed — mutating the object
list = listOf() // ❌ error — reassigning the reference
```

```
val list
  |
  v
MutableList [1, 2, 3]  ← object mutated, reference stayed
```

---

## What the Compiler Generates

### var

```kotlin
var name = "Atharva"
```

Becomes:

```
private String name
getName()    // getter
setName()    // setter
```

### val

```kotlin
val name = "Atharva"
```

Becomes:

```
private final String name
getName()    // getter only
```

No setter. `final` prevents reassignment at JVM level.

---

## Constructor Properties

```kotlin
class User(val name: String, var age: Int)
```

Generates:

```
val name → private final String name + getName()
var age  → private int age + getAge() + setAge()
```

---

## Why Smart Casts Need val

```kotlin
val x: Any = "hello"
if (x is String) {
    println(x.length)  // ✅ smart cast works
}
```

```kotlin
var x: Any = "hello"
if (x is String) {
    println(x.length)  // ❌ compiler rejects
}
```

Why?

```
var can be reassigned between the check and the use.
Another thread could write x = 42 after the is-check.
val guarantees the reference stays the same.
```

See [Q1.6 — Smart Casts](#q16--smart-casts).

---

## Memory Trick

```
val = "the drawer is locked shut"
       (but the thing inside can still change)

var = "the drawer can be opened and swapped"
```

---

## Self-Test

1. Does `val list = mutableListOf(1)` prevent `list.add(2)`? Why or why not?
2. What JVM keyword does `val` compile to on the backing field?
3. Why does the compiler reject smart casts on `var`?

---

# Q1.1 — val vs const val

> **Connects to:** [Q0.4 (getter call overhead)](phase0_jvm_mental_model_v3.md#q04--the-jvm-call-stack) · [Q0.3 (const val doesn't trigger class loading)](phase0_jvm_mental_model_v3.md#q03--class-loading-and-init--in-object)

---

## The Problem

```kotlin
object Config {
    val BASE_URL = "https://api.example.com"
    const val TAG = "APP"
}
```

Both look like constants. But the JVM sees completely different code.

---

## val — Runtime Property

```kotlin
val BASE_URL = "https://api.example.com"
```

Compiles to:

```
private static final String BASE_URL
public static String getBASE_URL()
```

Every access calls the getter:

```
GETSTATIC Config.INSTANCE
INVOKEVIRTUAL Config.getBASE_URL()
```

Two instructions. Method call overhead.

---

## const val — Compile-Time Literal

```kotlin
const val TAG = "APP"
```

Usage:

```kotlin
Log.d(Config.TAG, "hello")
```

Bytecode at the call site:

```
LDC "APP"
```

The string `"APP"` is pasted directly. No getter. No field access. No class loading. `Config` is never touched.

---

## JIT Note

The JIT often inlines trivial getters for `val`, shrinking the gap. But `const val` is **guaranteed** zero-overhead at compile time — no reliance on JIT warmup.

---

## const val Constraints

```
1. Only String and primitives (Int, Long, Boolean, etc.)
2. Only at top-level, object, or companion object
3. Value must be known at compile time
```

```kotlin
const val TAG = Config::class.simpleName  // ❌ computed at runtime
const val MAX = 100                        // ✅ literal
const val URL = "https://api.com"          // ✅ literal
```

---

## @JvmField — The Middle Ground

```kotlin
@JvmField val URL = "https://api.com"
```

Removes the getter. Access becomes:

```
GETSTATIC Config.URL
```

One instruction instead of two. But:

```
Still a runtime field.
Still triggers class initialization.
Still not inlined as literal.
```

| | val | @JvmField val | const val |
|---|---|---|---|
| Getter? | Yes | No | No |
| Field access? | Via getter | Direct | None — inlined |
| Triggers class init? | Yes | Yes | **No** |
| Works for objects? | Yes | Yes | Only String + primitives |

---

## Binary Compatibility Trap

Library publishes:

```kotlin
const val VERSION = "1.0"
```

Client compiles → `"1.0"` is baked into client's bytecode.

Library updates to `"2.0"`.

Client still uses `"1.0"` until recompiled.

```
const val = value frozen at compile time
Updating the library ≠ updating the client
```

This is why library authors sometimes prefer `val` for values that might change between releases.

---

## Memory Trick

```
val       = getter call    (runtime, class loaded)
@JvmField = field access   (runtime, class loaded)
const val = literal pasted (compile time, class NOT loaded)
```

---

## Self-Test

1. What bytecode instruction does `const val TAG = "APP"` produce at the call site?
2. Why does `const val` not trigger class initialization but `val` does?
3. You publish a library with `const val VERSION = "1.0"`. A user updates the library to `"2.0"` without recompiling. What value do they see?
4. What's the difference between `@JvmField val` and `const val`?

---

# Q1.2 — Nullability

> **Connects to:** [Q0.1 (why primitives can't be null)](phase0_jvm_mental_model_v3.md#q01--primitives-vs-references-the-two-worlds) · [Q5.1 (lateinit null sentinel)](05_properties_and_delegation.md#q51--lateinit-internals)

---

## The Key Insight

Null safety exists **only in the compiler**.

At JVM level:

```
String   → java.lang.String
String?  → java.lang.String
```

Same type. The `?` is erased. The JVM has no concept of nullable vs non-nullable.

---

## How Kotlin Protects at Runtime

```kotlin
fun greet(name: String) { ... }
```

Compiler inserts a check at the top:

```
Intrinsics.checkNotNullParameter(name, "name")
```

This catches Java callers passing null — it crashes at the entry point, not deep inside.

---

## Platform Types — The Danger Zone

Java method:

```java
public String getName() { ... }
```

Kotlin sees:

```
String!
```

This is a **platform type** — Kotlin doesn't know if it's nullable.

Both compile:

```kotlin
val a: String  = javaObj.getName()  // trusts Java — crashes if null
val b: String? = javaObj.getName()  // safe — handles null
```

```
String! = "I don't know, you decide"
Always treat Java returns as String? unless annotated.
```

---

## @NotNull and @Nullable

Java annotations give Kotlin hints:

```java
@NotNull  String getName()   → Kotlin sees String
@Nullable String getEmail()  → Kotlin sees String?
```

These are **compile-time only**. No runtime cost. They eliminate the `String!` ambiguity.

---

## Elvis Operator

```kotlin
val name = maybe ?: "unknown"
```

Bytecode:

```
ALOAD maybe
DUP
IFNONNULL skip
POP
LDC "unknown"
skip:
```

A conditional branch. If `maybe` is non-null, use it. Otherwise, use the fallback.

If the compiler can prove `maybe` is non-null, the branch is eliminated entirely.

---

## Safe Call Chaining

```kotlin
val len = user?.address?.city?.length
```

Each `?.` compiles to a null check:

```
if user != null
  if user.address != null
    if user.address.city != null
      return city.length
return null
```

Each `?.` = one `IFNULL` branch.

---

## !! — Not-Null Assertion

```kotlin
val name: String = nullableValue!!
```

Compiles to:

```
Intrinsics.checkNotNull(nullableValue)
```

Throws `NullPointerException` if null. Use only when certain.

---

## Memory Trick

```
String vs String?  = same JVM type
Null safety        = compiler trick, erased at runtime
String!            = Java says "figure it out yourself"
Elvis (?:)         = conditional branch in bytecode
!!                 = checkNotNull() — NPE if wrong
```

---

## Self-Test

1. At JVM level, is `String` different from `String?`?
2. What does Kotlin insert at the top of `fun greet(name: String)` to protect against Java nulls?
3. What is `String!` and when do you see it?
4. What bytecode does `maybe ?: "default"` produce?

---

# Q1.3 — Type Hierarchy: Any, Nothing, Unit

> **Connects to:** [Q0.2 (Any = Object, forces boxing)](phase0_jvm_mental_model_v3.md#q02--jvm-type-mapping-when-does-kotlin-box) · [Q2.3 (sealed class with Nothing)](02_classes_and_objects.md#q23--sealed-classes-and-interfaces) · [Q3.2 (variance positions)](03_generics_and_variance.md#q32--declaration-site-variance)

---

## The Hierarchy

```
    Any       (top — non-null root)
     |
    Any?      (nullable root)
   / | \
String Int  User ...
   \ | /
  Nothing    (bottom — subtype of all)
```

---

## Any

Kotlin's root type. Every non-nullable type extends it.

```
Any = java.lang.Object at JVM level
```

```kotlin
val x: Any = "hello"  // ✓
val y: Any = 42        // ✓ (boxes to Integer)
val z: Any = User()    // ✓
```

Three methods inherited from `Any`:

```
equals()
hashCode()
toString()
```

---

## Any vs Any?

```
Any  = cannot be null
Any? = can be null (true top type)
```

```kotlin
val a: Any  = null  // ❌ compile error
val b: Any? = null  // ✓
```

---

## Nothing

Represents: **a computation that never completes**.

```kotlin
fun fail(msg: String): Nothing {
    throw IllegalStateException(msg)
}
```

No value can ever be `Nothing`. It's the **bottom type** — subtype of every type.

---

## Why Nothing Matters

Because `Nothing` is a subtype of everything, it fits anywhere:

```kotlin
val name: String = throw Exception()
// throw returns Nothing
// Nothing IS-A String  ✓
// Compiles.
```

```kotlin
val result: Int = TODO()
// TODO() returns Nothing
// Nothing IS-A Int  ✓
```

---

## Nothing in Collections

```kotlin
val strings: List<String> = emptyList()
val ints: List<Int> = emptyList()
```

`emptyList()` returns `List<Nothing>`. `List<Nothing>` IS-A `List<T>` for any T because of `out` variance. Same object. Works because `Nothing` is the bottom type.

---

## Nothing in Sealed Classes

```kotlin
sealed class Result<out T> {
    data class Success<T>(val data: T) : Result<T>()
    data class Error(val e: Throwable) : Result<Nothing>()
}
```

`Result<Nothing>` IS-A `Result<T>` for any T. `Error` carries no data, so `Nothing` fits the unused type parameter.

---

## Unit

Kotlin's equivalent of `void`. But it's an actual object.

```
void → no return value
Unit → singleton object (Unit.INSTANCE)
```

Simple function:

```kotlin
fun log(msg: String): Unit { ... }
```

Bytecode: `RETURN` — void return, no object.

In a generic position:

```kotlin
val action: () -> Unit = { println("hi") }
```

JVM must return something:

```
GETSTATIC Unit.INSTANCE
ARETURN
```

Same pattern as boxing — generics force `Unit` to become a real object.

---

## Unit vs Nothing vs Void

| | Returns? | Has value? | JVM |
|---|---|---|---|
| `Unit` | Yes | Singleton object | `void` or `Unit.INSTANCE` |
| `Nothing` | **Never** | No value exists | Function never returns |
| Java `void` | Yes | No value | `void` |

---

## Memory Trick

```
Any     = root of all non-null types = Object
Nothing = bottom of all types = "never returns"
Unit    = "returns, but nothing useful" = void

throw   → Nothing  (never completes)
TODO()  → Nothing  (never completes)
println → Unit     (completes, no useful value)
```

---

## Self-Test

1. Why does `val x: String = throw Exception()` compile?
2. What type does `emptyList()` return? Why can it be assigned to `List<String>`?
3. When does `Unit` become a real object at JVM level?
4. What's the difference between `Nothing` and `Unit`?

---

# Q1.4 — Property vs Field

> **Connects to:** [Q0.4 (getter overhead)](phase0_jvm_mental_model_v3.md#q04--the-jvm-call-stack) · [Q1.5 (backing fields)](#q15--backing-fields)

---

## The Rule

```
PROPERTY ≠ FIELD

Field    = memory storage (JVM concept)
Property = Kotlin abstraction (getter + setter + optional field)
```

---

## Field

Raw storage in the JVM:

```java
private String name;   // JVM field — occupies memory, that's all
```

---

## Property

A Kotlin property may contain:

```
getter     (always)
setter     (if var)
field      (sometimes — not always!)
```

---

## Property WITH Field

```kotlin
var name = "Atharva"
```

Generates:

```
private String name          ← field
public String getName()      ← getter
public void setName(String)  ← setter
```

---

## Property WITHOUT Field

```kotlin
val area: Int
    get() = width * height
```

Generates:

```
public int getArea()    ← getter (computes on every call)
                        ← NO field (nothing stored)
```

No memory allocated for `area`. Computed fresh each time.

---

## Why This Matters for Interfaces

```kotlin
interface Animal {
    val name: String
}
```

Compiles to:

```java
public interface Animal {
    String getName();   // abstract method
}
```

No field. Interfaces can't have fields (JVM rule). But they CAN declare properties — a property is just a getter contract.

---

## The Implementation

```kotlin
class Dog(override val name: String) : Animal
```

Generates:

```
private final String name   ← field (in Dog)
public String getName()     ← getter (fulfills interface)
```

The field lives in the class. The interface only defines the getter.

---

## Memory Trick

```
Field    = "the storage box"
Property = "the box + the access rules"

Interface property = "access rules only, no box"
Class property     = "usually has a box, always has rules"
```

---

## Self-Test

1. Does `val area get() = width * height` have a backing field?
2. Why can interfaces have properties but not fields?
3. What JVM construct does `interface Animal { val name: String }` compile to?

---

# Q1.5 — Backing Fields

> **Connects to:** [Q1.4 (property vs field)](#q14--property-vs-field) · [Q5.1 (lateinit backing field)](05_properties_and_delegation.md#q51--lateinit-internals)

---

## What Is a Backing Field

The actual storage behind a property. Compiler generates one when it needs to store data.

---

## When Is It Generated?

```
✓ Property has an initializer     → val x = 5
✓ Default getter/setter used      → var y: String
✓ field keyword used in accessor  → set(v) { field = v }
✓ lateinit property               → lateinit var z: String
```

---

## When Is It NOT Generated?

```
✗ Custom getter with no field reference
```

```kotlin
val area: Int
    get() = width * height    // no field keyword → no backing field
```

---

## The field Keyword

Inside a custom accessor, `field` refers to the backing field:

```kotlin
var count = 0
    set(value) {
        if (value >= 0) field = value
    }
```

Without `field`, there's no way to read/write the stored value from inside the accessor.

---

## Backing Field in Bytecode

```kotlin
var count = 0
    set(value) {
        if (value >= 0) field = value
    }
```

Becomes:

```java
private int count = 0;

public int getCount() { return count; }

public void setCount(int value) {
    if (value >= 0) this.count = value;
}
```

`field` in Kotlin = `this.count` in bytecode.

---

## Backing Property Pattern

When you need private mutable but public read-only:

```kotlin
private val _items = mutableListOf<String>()
val items: List<String> get() = _items
```

`items` has no backing field. It delegates to `_items`.

Standard Android pattern for `StateFlow` / `LiveData`:

```kotlin
private val _state = MutableStateFlow(Loading)
val state: StateFlow<UiState> = _state.asStateFlow()
```

---

## Self-Test

1. Does `val x = 5` have a backing field? Does `val x get() = 5`?
2. What does the `field` keyword compile to in bytecode?
3. Why use the `_items` / `items` backing property pattern?

---

# Q1.6 — Smart Casts

> **Connects to:** [Q1.0 (var breaks smart casts)](#q10--var-vs-val) · [Q2.3 (sealed class when exhaustiveness)](02_classes_and_objects.md#q23--sealed-classes-and-interfaces) · [Q3.1 (type erasure breaks is checks)](03_generics_and_variance.md#q31--type-erasure)

---

## What They Are

The compiler narrows a type automatically after a check:

```kotlin
fun process(x: Any) {
    if (x is String) {
        println(x.length)  // x is now String — no cast needed
    }
}
```

---

## Flow Analysis

Works across control flow:

```kotlin
fun process(x: Any) {
    if (x !is String) return

    println(x.length)  // compiler knows x is String here
}
```

---

## Smart Cast Requirements

The variable must be **stable** — the compiler must guarantee it hasn't changed between the check and the use.

```
local val           ✓   (can't change)
local var           ✓   (if not reassigned between check and use)
val property        ✗   (custom getter might return different value)
var property        ✗   (another thread could reassign)
open val property   ✗   (subclass might override getter)
```

---

## Why Properties Fail

```kotlin
class Box(val item: Any)

fun test(box: Box) {
    if (box.item is String) {
        box.item.length  // ❌ smart cast impossible
    }
}
```

`item` has a getter. Even though it's `val`, a subclass could override the getter to return different values each time.

Fix:

```kotlin
val item = box.item   // capture in local val
if (item is String) {
    item.length       // ✓ local val is stable
}
```

---

## The Lambda Trap

```kotlin
var x: Any = "hello"
if (x is String) {
    run { x.length }   // ❌ rejected
}
```

The lambda might execute later, after `x` has been reassigned.

---

## is vs as

```
is  = type CHECK (returns Boolean)
as  = type CAST (returns casted type or throws)
as? = SAFE cast (returns null instead of throwing)
```

Bytecode:

```
is  → INSTANCEOF instruction
as  → CHECKCAST instruction (throws ClassCastException)
as? → INSTANCEOF + CHECKCAST (null if check fails)
```

---

## Memory Trick

```
Smart cast needs STABILITY:
  local val → ✓ (locked)
  property  → ✗ (getter might lie)
  var       → ✗ (might change)

Fix: capture in local val, then check.
```

---

## Self-Test

1. Why does smart cast fail on `val` properties but work on local `val`?
2. Why does `run { x.length }` fail after `if (x is String)` when `x` is `var`?
3. What JVM instruction does `is` compile to? What about `as`?
4. How do you fix a failing smart cast on a property?

---

# Q1.7 — Value Classes

> **Connects to:** [Q0.2 (boxing)](phase0_jvm_mental_model_v3.md#q02--jvm-type-mapping-when-does-kotlin-box) · [Q3.1 (type erasure)](03_generics_and_variance.md#q31--type-erasure)

---

## The Problem They Solve

```kotlin
fun process(userId: String, orderId: String) { ... }

process(orderId, userId)  // compiles fine — arguments are swapped!
```

Both are `String`. Compiler can't catch the mistake.

---

## Value Class

```kotlin
@JvmInline
value class UserId(val id: String)

@JvmInline
value class OrderId(val id: String)

fun process(userId: UserId, orderId: OrderId) { ... }
process(OrderId("o1"), UserId("u1"))  // ❌ compile error — types don't match
```

Type safety. But at runtime:

```
UserId("u1") → just "u1" (the String)
```

The wrapper is **erased**. Zero overhead.

---

## When Boxing Happens

Value classes box when used in:

```
nullable type       UserId?
generic position    List<UserId>
interface type      Comparable<UserId>
type check          x is UserId
```

Same rules as primitives in [Q0.2](phase0_jvm_mental_model_v3.md#q02--jvm-type-mapping-when-does-kotlin-box).

---

## Name Mangling

```kotlin
fun process(id: UserId) { ... }
fun process(id: String) { ... }
```

At JVM level, both would be `process(String)` after erasure. Collision.

Kotlin prevents this by **mangling** the function name:

```
process-<hashcode>(String)
```

This makes it invisible to Java callers. Use `@JvmName` to provide a clean name.

---

## typealias vs value class vs data class

| | New type? | Runtime cost | Type safety |
|---|---|---|---|
| `typealias` | No — just an alias | None | None |
| `value class` | Yes | None (usually erased) | Yes |
| `data class` | Yes | Object allocation | Yes |

```kotlin
typealias UserId = String         // userId + orderId are both String — no safety

@JvmInline
value class UserId(val id: String) // type-safe at compile time, erased at runtime
```

---

## Self-Test

1. What does `UserId("abc")` become at runtime?
2. When does a value class get boxed?
3. Why does Kotlin mangle function names that take value class parameters?
4. What's the difference between `typealias UserId = String` and `value class UserId(val id: String)`?

---

# Q1.8 — Contracts

> **Connects to:** [Q1.6 (smart casts)](#q16--smart-casts)

---

## What They Are

Contracts let functions tell the compiler things it can't prove on its own.

---

## The Most Common Contract

```kotlin
fun greet(name: String?) {
    requireNotNull(name)
    println(name.length)    // ✓ smart cast — compiler trusts the contract
}
```

Without the contract, the compiler wouldn't know that `requireNotNull` guarantees non-null after the call.

---

## How requireNotNull Works

```kotlin
public inline fun <T : Any> requireNotNull(value: T?): T {
    contract {
        returns() implies (value != null)
    }
    if (value == null) throw IllegalArgumentException()
    return value
}
```

The contract says: "if this function returns normally, then `value` is non-null."

---

## Other Built-in Contracts

```kotlin
require(condition)     // implies condition == true after call
check(condition)       // implies condition == true after call
checkNotNull(value)    // implies value != null after call
```

---

## run / let / apply Contracts

```kotlin
val x: String? = "hello"
x?.let {
    println(it.length)  // ✓ it is String inside let
}
```

`let` has a contract that tells the compiler the lambda executes exactly once, enabling smart casts inside it.

---

## Limitation

Custom contracts for arbitrary functions are still experimental. The standard library contracts are what you'll use in practice.

---

## Self-Test

1. What happens after `requireNotNull(x)` — can you use `x` as non-null?
2. What does the contract `returns() implies (value != null)` mean?
3. Why can you smart-cast inside `let { }` but not inside `run { }` on a `var`?

---

# Q1.9 — Interview Traps

> Collected traps from all of Phase 1. These are the exact follow-up questions interviewers use.

---

## Trap 1 — throw in expressions

```kotlin
val x: String = throw Exception()
```

Why does this compile?

```
throw returns Nothing.
Nothing is subtype of String.
Type system accepts it.
```

---

## Trap 2 — emptyList assignment

```kotlin
val names: List<String> = emptyList()
```

Why does this work without specifying `<String>`?

```
emptyList() returns List<Nothing>.
Nothing is subtype of String.
List<Nothing> IS-A List<String> via out variance.
Type inference fills in String.
```

---

## Trap 3 — Java null safety breach

```kotlin
fun greet(name: String) {
    println(name.length)
}
```

Can Java break this?

```
Yes. Java sees greet(String) — no null enforcement.
Java can call greet(null).
Kotlin inserts checkNotNullParameter, so it crashes
at the entry point — not deep inside.
```

---

## Trap 4 — Smart cast on property

```kotlin
class Box(val item: Any)

if (box.item is String) {
    box.item.length  // ❌ fails
}
```

Why?

```
val property has a getter.
Subclass could override it.
Compiler can't guarantee stability.
Capture in local val first.
```

---

## Trap 5 — Getter invisible in profiler

```kotlin
object Config {
    val URL = "https://..."
}
```

You profile and see no `getURL()` call. Why?

```
JIT inlined the trivial getter.
The call exists in bytecode but disappears
in native code after optimization.
```

---

## Trap 6 — is check with generics

```kotlin
if (list is List<String>)  // ❌ compile error
```

Why?

```
Type erasure.
At runtime, List<String> is just List.
JVM cannot check the generic parameter.
Use: list is List<*>  ✓
```

See [Q3.1 — Type Erasure](03_generics_and_variance.md#q31--type-erasure).

---

## Trap 7 — val allows mutation

```kotlin
val list = mutableListOf(1)
list.add(2)  // ✓
```

Why?

```
val locks the reference, not the object.
The list object itself is mutable.
Only reassignment is blocked.
```

---

## Trap 8 — const val binary compatibility

```kotlin
// Library v1
const val VERSION = "1.0"

// Library v2
const val VERSION = "2.0"
```

Client still sees `"1.0"`. Why?

```
const val is inlined at compile time.
Client has "1.0" baked in.
Must recompile to pick up "2.0".
```

---

# Master Summary: Phase 1

> Kotlin's type system is a compile-time layer over the JVM. Null safety, smart casts, and value classes don't exist at runtime — the compiler enforces them, then erases them.

**1. var/val** (Q1.0)
`val` = immutable reference, not immutable object.
`val` enables smart casts. `var` breaks them.

**2. val/const val** (Q1.1)
`val` = getter call at runtime. `const val` = literal inlined at compile time.
`const val` doesn't trigger class loading. Binary compatibility trap.
→ [Phase 0: Q0.3 (class loading)](phase0_jvm_mental_model_v3.md#q03--class-loading-and-init--in-object)

**3. Nullability** (Q1.2)
`String` and `String?` are the same JVM type. Null safety = compiler trick.
`String!` = platform type from Java. `checkNotNullParameter` protects at runtime.

**4. Type Hierarchy** (Q1.3)
`Any` = top (Object). `Nothing` = bottom (subtype of everything).
`throw` returns `Nothing`. `Unit` = void as an object.

**5. Property vs Field** (Q1.4)
Property = getter + setter + optional field. Interfaces have properties, not fields.

**6. Backing Fields** (Q1.5)
Generated when initializer or `field` keyword is present.
Backing property pattern: `_state` / `state` for mutable/read-only exposure.

**7. Smart Casts** (Q1.6)
Require stable variables: local val ✓, property ✗, var ✗.
`is` = INSTANCEOF. `as` = CHECKCAST. Capture in local val to fix.

**8. Value Classes** (Q1.7)
Type-safe wrapper, erased at runtime. Boxes in same cases as primitives.
`typealias` = no safety. `value class` = safety + zero cost.

**9. Contracts** (Q1.8)
Tell the compiler what a function guarantees. Unlocks smart casts after `requireNotNull`, `require`, `check`.

---

## Final Self-Test: All of Phase 1

1. **(Q1.0)** Does `val` guarantee the object can't be modified?
2. **(Q1.1)** What's the bytecode difference between accessing `val` and `const val`?
3. **(Q1.2)** At JVM level, is `String` different from `String?`?
4. **(Q1.3)** Why does `val x: String = throw Exception()` compile?
5. **(Q1.4)** Can an interface have a backing field?
6. **(Q1.5)** When does the compiler NOT generate a backing field?
7. **(Q1.6)** Why do smart casts fail on `val` properties?
8. **(Q1.7)** What happens to `value class UserId(val id: String)` at runtime?
9. **(Q1.8)** After `requireNotNull(x)`, why can the compiler treat `x` as non-null?
10. **(Q1.9)** `val list = mutableListOf(1); list.add(2)` — is this allowed? Why?

---

*Next: [Phase 2 — Classes and Objects →](02_classes_and_objects.md)*