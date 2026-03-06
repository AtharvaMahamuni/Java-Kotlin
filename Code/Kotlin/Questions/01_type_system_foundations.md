```
01_type_system_foundations.md
```

---

# Phase 1 — Type System Foundations

Kotlin's type system exists at three layers.

```

1 Kotlin language rules
2 Compiler analysis
3 JVM representation

```

Understanding these explains:

```

properties
null safety
smart casts
Nothing
Unit

```

---

# Navigation

← Phase 0 — JVM Mental Model

---

# Q1.0 — var vs val

Kotlin controls mutability using two keywords.

```

var  → mutable reference
val  → read-only reference

```

---

## First Principle

Important rule:

```

val ≠ immutable object
val = immutable reference

````

Example:

```kotlin
val list = mutableListOf(1)
list.add(2)    // allowed
````

Why?

```
reference cannot change
object may mutate
```

---

## Visual Model

```
val list
   │
   ▼
MutableList object
   │
   ├─ add()
   ├─ remove()
   └─ mutate data
```

---

# var

```kotlin
var name = "Atharva"
name = "Alex"
```

Compiler generates:

```
field
getter
setter
```

---

# val

```kotlin
val name = "Atharva"
```

Compiler generates:

```
field
getter
```

No setter.

---

# Bytecode Model

Example:

```kotlin
var age = 25
```

Conceptually:

```
private int age

getAge()
setAge()
```

---

# Constructor Properties

Example:

```kotlin
class User(val name: String)
```

Compiler generates:

```
private final String name
getName()
```

For `var`:

```
private String name
getName()
setName()
```

---

# JVM Difference

```
val → final field
var → mutable field
```

(when backing field exists)

---

# Smart Cast Connection

Works:

```kotlin
val x: Any = "hi"

if (x is String) {
    println(x.length)
}
```

Fails:

```kotlin
var x: Any = "hi"

if (x is String) {
    println(x.length)
}
```

Why?

```
var may change
between check and use
```

---

# Q1.1 — val vs const val

Two declarations:

```kotlin
object Config {
    val BASE = "api"
    const val TAG = "APP"
}
```

---

# val

Compiled as property:

```
field
getter()
```

Access bytecode:

```
GETSTATIC instance
INVOKEVIRTUAL getter
```

---

# JIT Note

JVM often **inlines trivial getters**.

Getter cost mostly disappears in hot code.

---

# const val

Example:

```kotlin
const val TAG = "APP"
```

Usage:

```kotlin
println(TAG)
```

Bytecode:

```
LDC "APP"
```

Literal inserted directly.

---

# Important Detail

```
const val does NOT
prevent class loading
```

It only avoids **class initialization**.

---

# @JvmField

Example:

```kotlin
@JvmField val URL = "example"
```

Removes getter.

But still:

```
runtime field
class initialization
```

---

# Binary Compatibility Trap

Library:

```
const val VERSION = "1.0"
```

Client compiled with `"1.0"`.

If library updates:

```
VERSION = "2.0"
```

Client still uses `"1.0"`.

Until recompiled.

---

# Q1.2 — Nullability

Kotlin null safety exists only in the compiler.

At JVM level:

```
String
String?
```

Both become:

```
java.lang.String
```

---

# Runtime Protection

Example:

```kotlin
fun greet(name: String)
```

Compiler inserts:

```
Intrinsics.checkNotNullParameter
```

Protects against Java callers.

---

# Platform Types

Java method:

```java
String getName()
```

Kotlin sees:

```
String!
```

Meaning:

```
could be String
could be String?
```

Both allowed:

```kotlin
val a: String = javaCall()
val b: String? = javaCall()
```

---

# Elvis Operator

Example:

```kotlin
val name = maybe ?: "unknown"
```

Bytecode:

```
ALOAD maybe
IFNONNULL skip
LDC "unknown"
```

Branch generated.

---

# Compiler Optimization

If value proven non-null:

```
Elvis removed
```

---

# Q1.3 — Type Hierarchy

Mobile-friendly hierarchy:

```
        Any
         │
        Any?
         │
        null
         │
      Nothing
```

---

# Two Top Types

Kotlin has two roots:

```
Any   → non-null
Any?  → nullable
```

---

# Nothing

Represents computation that **never returns**.

Example:

```kotlin
fun fail(): Nothing =
    throw Exception()
```

Why this works:

```kotlin
val name: String =
    throw Exception()
```

Because:

```
Nothing is subtype
of all types
```

---

# Empty Collections

```
emptyList()
emptySet()
emptyMap()
```

Return:

```
List<Nothing>
```

Which works for:

```
List<String>
List<Int>
List<User>
```

---

# Unit

Kotlin equivalent of `void`.

Difference:

```
void → no value
Unit → object
```

---

# JVM Behavior

Function returning Unit:

```
RETURN
```

No object.

But in generics:

```
() -> Unit
```

JVM uses:

```
Unit.INSTANCE
```

---

# Q1.4 — Property vs Field

Key rule:

```
PROPERTY ≠ FIELD
```

---

# Field

Field is **memory storage**.

Example JVM field:

```
private String name
```

Fields:

```
store data
occupy memory
exist in objects
```

---

# Property

Property is Kotlin abstraction.

It may contain:

```
getter
setter
field (optional)
```

---

# Visual Model

```
PROPERTY
  │
  ├ getter()
  ├ setter()
  └ field
```

---

# Property Without Field

Example:

```kotlin
val area
 get() = width * height
```

Meaning:

```
getter exists
field does not
```

---

# Why Interfaces Have Properties

Example:

```kotlin
interface Animal {
    val name: String
}
```

Compiles to:

```
getName()
```

No field.

---

# Q1.5 — Backing Fields

Backing field is **storage used by property**.

Generated when:

```
initializer present
default getter used
field keyword used
lateinit property
```

Example:

```kotlin
val x = 5
```

Field generated.

---

# No Field Example

```kotlin
val x get() = 5
```

Getter only.

---

# Backing Field Keyword

```
field
```

Example:

```kotlin
var count = 0
 set(value) {
   field = value
 }
```

---

# lateinit Rule

```
lateinit works only
for reference types
```

Because Kotlin uses:

```
null sentinel
```

Primitive cannot hold null.

---

# Q1.6 — Smart Casts

Smart casts narrow types automatically.

Example:

```kotlin
if (x is String) {
    println(x.length)
}
```

---

# Flow Analysis

Works across control flow.

Example:

```kotlin
if (x !is String) return
println(x.length)
```

---

# Smart Cast Requirements

Works only if variable is stable.

```
local val        ✓
var property     ✗
custom getter    ✗
lambda capture   ✗
```

---

# Lambda Trap

Example:

```kotlin
var x: Any = "hello"

if (x is String) {
  run {
    x.length
  }
}
```

Rejected because lambda might run later.

---

# Safe Pattern

```
val v = x
```

Then check.

---

# Q1.7 — Value Classes

Example:

```kotlin
@JvmInline
value class UserId(val id: String)
```

Runtime representation:

```
String
```

---

# Boxing Cases

Value classes box when used in:

```
generics
nullable types
interfaces
```

---

# Type Alias

```
typealias UserId = String
```

Compile-time alias only.

---

# Comparison

| Feature     | New Type | Runtime |
| ----------- | -------- | ------- |
| typealias   | no       | none    |
| value class | yes      | minimal |
| data class  | yes      | object  |

---

# Q1.8 — Contracts

Contracts help compiler reason about code.

Example:

```kotlin
requireNotNull(x)
```

After call:

```
x smart-cast to non-null
```

---

# Q1.9 — Interview Traps

Trap 1

```
val x: String =
    throw Exception()
```

Why?

```
throw returns Nothing
```

---

Trap 2

Why does this work?

```
emptyList()
```

Answer:

```
List<Nothing>
```

---

Trap 3

Why can Java break null safety?

```
platform types
```

---

Trap 4

Why smart cast fails on properties?

```
another thread
may modify property
```

---

Trap 5

Why getters disappear in profiler?

```
JIT inlining
```

---

Trap 6

Why cannot check:

```
list is List<String>
```

Because:

```
type erasure
```

---

Trap 7

Why does this compile?

```
val list = mutableListOf(1)
list.add(2)
```

Because:

```
val protects reference
not object mutation
```

---

# Master Summary

Four pillars of Kotlin type system:

```
mutability
nullability
type hierarchy
flow typing
```

These explain:

```
smart casts
Nothing
Unit
const val
platform types
```

---

# Final Self Test

1 Why does val not guarantee immutability?
2 Why can Java break Kotlin null safety?
3 Why does throw work inside expressions?
4 When does Kotlin generate a backing field?
5 Why do smart casts fail for properties?
