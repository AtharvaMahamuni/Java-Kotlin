```
00_jvm_mental_model.md
```

It preserves your structure and **adds the missing definitions + tricky interview insights**.

---

```markdown
# Phase 0: JVM Mental Model

> The JVM has exactly **two worlds: primitives and objects**.  
> Every Kotlin feature — nullable types, generics, lateinit, inline — exists because of the tension between these two worlds.

Understanding this tension = understanding the JVM.

---

# Navigation

[← Master Index](master_chains.md)

## Questions in This File

- Q0.1 — Primitives vs References: The Two Worlds
- Q0.2 — JVM Type Mapping: When Does Kotlin Box?
- Q0.3 — Class Loading and `init {}` in `object`
- Q0.4 — The JVM Call Stack
- Q0.5 — Code Execution Pipeline (.kt → Running Code)
- Q0.6 — JVM Interview Traps (Advanced)

---

# Q0.1 — Primitives vs References: The Two Worlds

The JVM only understands **two kinds of values**.

```

1. Primitives
2. References (Objects)

````

Everything in Kotlin and Java maps to one of these.

---

## The Concrete Picture

### Primitive

```kotlin
val x: Int = 42
````

```
STACK
+-------+
| 42    |
+-------+
```

The **value itself lives inside the variable**.

No pointer.
No wrapper.

---

### Reference

```kotlin
val y: String = "hi"
```

```
STACK                  HEAP
+----------+           +-------------+
| y = 0x7f | --------> | "hi" object |
+----------+           +-------------+
```

The variable stores **a pointer to an object**.

---

# Why Two Worlds Exist

The JVM designers had two conflicting goals.

### Performance

Math operations must be extremely fast.

```
i + 1
```

Cannot allocate objects.

---

### Object-Oriented Programming

Collections must store **any type**.

```
List
Map
Set
```

This requires everything to inherit from:

```
java.lang.Object
```

But primitives **do not inherit from Object**.

---

### Solution

Two parallel systems.

| Primitive      | Reference         |
| -------------- | ----------------- |
| raw value      | pointer to object |
| no identity    | object identity   |
| no header      | metadata          |
| cannot be null | can be null       |

---

# The 8 JVM Primitives

```
byte
short
int
long

float
double

boolean
char
```

Everything else is a **reference type**.

---

# Why Primitives Cannot Be Null

A primitive variable stores **raw bits**.

Example: `int`

```
32 bits
```

Every bit pattern represents a real number.

Example:

```
00000000 = 0
11111111 = -1
```

There is **no unused bit pattern** to represent `null`.

Therefore:

```
Primitives cannot represent null.
```

---

# References Can Be Null

References store **memory addresses**.

Example:

```
0x7f0011
```

Address `0x0` is reserved.

```
0x0 = null
```

This is why references can be null.

---

# Object Memory Layout

Typical JVM object:

```
Mark Word        8 bytes
Class Pointer    4 bytes
Padding          4 bytes
-------------------------
Header total     ~16 bytes
```

Example:

```
Integer object

16 byte header
4 byte value
padding
```

≈ **24 bytes**

Primitive `int`:

```
4 bytes
```

---

# Stack vs Heap

```
STACK
(per thread)

method frames
local variables
return addresses
```

```
HEAP
(shared)

objects
arrays
class metadata
```

Example call stack:

```
main()
  loadUser()
    parse()
```

Stack:

```
| parse |
| loadUser |
| main |
```

---

# Escape Analysis (JIT Optimization)

Sometimes objects do **not escape the method**.

Example:

```kotlin
fun compute(): Int {
    val p = Point(1,2)
    return p.x + p.y
}
```

The JVM may allocate `Point` **on the stack instead of heap**.

Benefits:

```
no heap allocation
no GC
faster execution
```

---

# Garbage Collection

Heap is managed by the **Garbage Collector**.

Typical layout:

```
Young Generation
   Eden
   Survivor

Old Generation
```

### Minor GC

Triggered when Eden fills.

Fast.

Most objects die here.

---

### Major GC

Triggered when Old Gen fills.

Slow.

May cause pauses.

---

# Why Boxing Causes GC Pressure

Example:

```
List<Integer>
```

Each number becomes an object.

Loop creating millions of objects → frequent GC → UI jank.

---

# Q0.2 — JVM Type Mapping: When Does Kotlin Box?

Two rules determine boxing.

---

## Rule 1 — Nullable Types

```
Int  → int
Int? → Integer
```

Nullable values must support `null`.

---

## Rule 2 — Generic Types

JVM generics only work with Objects.

Example:

```
List<Int>
```

Actually becomes:

```
List<Integer>
```

Because primitives cannot be stored in generic containers.

---

# Decision Flow

```
Nullable?
  YES → boxed

Else generic?
  YES → boxed

Else
  primitive
```

---

# Primitive Arrays vs Object Arrays

```
IntArray   → int[]
Array<Int> → Integer[]
```

Memory comparison:

```
1M IntArray   ≈ 4MB
1M Array<Int> ≈ 20MB
```

---

# Integer Cache

Java caches:

```
-128 to 127
```

Example:

```kotlin
val a: Int? = 127
val b: Int? = 127

a === b   // true
```

But:

```kotlin
val a: Int? = 128
val b: Int? = 128

a === b   // false
```

---

# Equality

```
==  structural equality
=== reference equality
```

---

# Q0.3 — Class Loading and `init {}`

Classes are loaded lazily.

Three phases:

```
1 LOAD
2 LINK
3 INITIALIZE
```

---

## ClassLoader

Loads `.class` files.

Types:

```
Bootstrap ClassLoader
Platform ClassLoader
Application ClassLoader
```

Android equivalents:

```
DexClassLoader
PathClassLoader
```

---

# Initialization

Runs the **class initializer**.

```
<clinit>
```

Kotlin:

```
init {}
```

in `object` compiles here.

---

# When Initialization Happens

| Access            | Trigger |
| ----------------- | ------- |
| new MyClass()     | YES     |
| static method     | YES     |
| static field read | YES     |
| const val         | NO      |

Example:

```kotlin
object Config {
    const val TAG = "APP"
    val URL = "example"
}
```

```
Config.TAG → no init
Config.URL → init
```

---

# Thread Safety

JVM guarantees:

```
<clinit> runs once
only one thread executes it
others block
```

Therefore:

```
Kotlin object = thread-safe singleton
```

---

# Q0.4 — JVM Call Stack

Every method call creates a **stack frame**.

Frame contains:

```
local variables
operand stack
return address
```

---

# Operand Stack

JVM instructions use a stack.

Example:

```
ICONST_2
ICONST_3
IMUL
```

Execution:

```
[]
[2]
[2,3]
[6]
```

JVM is a **stack-based machine**.

---

# Dispatch Types

| Type      | Instruction     |
| --------- | --------------- |
| Static    | INVOKESTATIC    |
| Private   | INVOKESPECIAL   |
| Virtual   | INVOKEVIRTUAL   |
| Interface | INVOKEINTERFACE |

---

# vtable (Virtual Method Table)

Used for polymorphism.

Example:

```
Animal
 speak → Animal.speak

Dog
 speak → Dog.speak
```

Call flow:

```
1 determine runtime type
2 lookup method in vtable
3 jump to method
```

---

# itable (Interface Table)

Used for interface dispatch.

Steps:

```
1 determine object type
2 search interface implementation
3 call method
```

More expensive than vtable lookup.

---

# Why Kotlin Classes Are Final

Final classes allow:

```
devirtualization
method inlining
better JIT optimization
```

---

# Q0.5 — Code Execution Pipeline

```
.kt
↓
kotlinc
↓
.class
↓
d8
↓
.dex
↓
ART runtime
```

---

# Compilation Stages

1. Parse → AST
2. Type checking
3. Desugaring
4. Bytecode generation

---

# Constant Pool

Each `.class` file contains a **constant pool**.

Stores:

```
string literals
method references
class names
field references
```

Example:

```
String s = "hello"
```

The string lives in the constant pool.

---

# Desktop JVM vs Android

Desktop:

```
Interpret
JIT compile hot code
```

Android:

```
AOT compilation
Profile guided optimizations
```

---

# Dalvik vs ART

Old Android:

```
Dalvik VM
JIT only
```

Modern Android:

```
ART runtime
AOT + JIT
```

---

# Why DEX Exists

DEX format:

```
smaller memory footprint
shared constant pools
optimized for mobile
```

---

# Q0.6 — JVM Interview Traps

These are questions interviewers love asking.

---

## Trap 1 — Why JVM Is Stack-Based

Instead of registers.

Reasons:

```
simpler bytecode
portable across CPUs
smaller instruction size
easier verification
```

---

## Trap 2 — Why Interface Calls Are Slower

Interface dispatch uses **itable lookup**, which requires:

```
type resolution
interface mapping
method lookup
```

More work than vtable dispatch.

---

## Trap 3 — Why Boxing Sometimes Does Not Allocate

Integer caching:

```
-128 to 127
```

Returns cached objects.

Therefore boxing **may not allocate**.

---

## Trap 4 — Why Final Helps Performance

Final classes allow:

```
devirtualization
method inlining
JIT optimization
```

Open classes prevent these optimizations.

---

## Trap 5 — Why String Constants Behave Differently

String literals are stored in the **String constant pool**.

Example:

```java
String a = "hello";
String b = "hello";
```

Both reference the same object.

```
a == b → true
```

But:

```java
new String("hello")
```

creates a new object.

---

# Master Summary

Everything in the JVM flows from one rule:

```
Primitives = raw values
Objects = heap references
```

Kotlin features exist to **bridge these worlds**.

---

# Final Self-Test

1. Why can't primitives represent null?
2. What two conditions cause Kotlin boxing?
3. What triggers class initialization?
4. Why are interface calls slower than virtual calls?
5. Why is JVM stack-based instead of register-based?

```

