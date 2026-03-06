```
02_classes_and_objects.md
```
---
# Phase 2 — Classes, Objects, and Initialization

> **Core Idea**
>
> Kotlin classes ultimately compile into **JVM classes**.  
> Understanding the JVM structure explains how inheritance,
> initialization, and method dispatch really work.

---

# Navigation

← Phase 1 — Type System  
→ Phase 3 — Generics and Variance

---

# Topics

```

Q2.1 Class Structure
Q2.2 Constructors and init blocks
Q2.3 Initialization Order
Q2.4 Virtual Dispatch
Q2.5 Class Modifiers
Q2.6 Inheritance Mechanics
Q2.7 Data Classes
Q2.8 Sealed Classes
Q2.9 Enum Classes
Q2.10 Object Keyword
Q2.11 Nested vs Inner Classes
Q2.12 Delegation
Q2.13 Value Classes

````

---

# Q2.1 — Class Structure (Kotlin → JVM)

## The Concrete Picture

A Kotlin class:

```kotlin
class User(val name: String)
````

compiles into a JVM class:

```
User.class
 ├ field name
 ├ constructor <init>
 └ getter getName()
```

Decompiled Java:

```java
public final class User {

    private final String name;

    public User(String name) {
        this.name = name;
    }

    public final String getName() {
        return name;
    }
}
```

---

## Mental Model

A Kotlin class contains:

```
properties
functions
constructors
nested types
```

The compiler converts them into JVM components:

```
fields
methods
constructors
static members
```

---

## Memory Trick

```
Kotlin class
   ↓
JVM class
   │
   ├ fields
   ├ methods
   ├ <init>
   └ <clinit>
```

---

# Q2.2 — Constructors and `init`

## The Concrete Picture

Example:

```kotlin
class User(val name: String) {

    val greeting = "Hello $name"

    init {
        println("User created")
    }
}
```

Execution order:

```
User("Alice")

1 constructor parameter assigned
2 property initializer runs
3 init block runs
```

---

## JVM Reality

All constructor logic becomes **one `<init>` method**.

```java
public User(String name) {
    this.name = name;
    this.greeting = "Hello " + name;
    System.out.println("User created");
}
```

---

## Memory Trick

```
constructor parameters
↓
property initializers
↓
init blocks
```

Declaration order = execution order.

---

# Q2.3 — Initialization Order

## Golden Rule

```
SUPERCLASS INITIALIZES BEFORE SUBCLASS
```

---

## Example

```kotlin
open class Base {

    init {
        println("Base init")
    }
}

class Child : Base() {

    init {
        println("Child init")
    }
}
```

Execution:

```
new Child()

1 Base init
2 Child init
```

---

## Full JVM Sequence

```
new Child()

Child.<init>
 ├ super.<init>
 │   ├ Base properties
 │   └ Base init blocks
 │
 ├ Child properties
 └ Child init blocks
```

---

# Q2.4 — Virtual Dispatch

Virtual dispatch is **one of the most important JVM concepts**.

---

## The Concrete Picture

Example:

```kotlin
open class Animal {
    open fun speak() {
        println("Animal sound")
    }
}

class Dog : Animal() {
    override fun speak() {
        println("Bark")
    }
}

fun main() {
    val animal: Animal = Dog()
    animal.speak()
}
```

Output:

```
Bark
```

Even though the variable type is `Animal`.

---

## Mental Model

Method resolution happens based on the **actual object type**, not the variable type.

```
Animal variable
      │
      ▼
Dog object
      │
      ▼
Dog.speak()
```

---

## JVM Reality

The JVM performs **vtable lookup**.

```
object → method table → actual implementation
```

Instruction used:

```
INVOKEVIRTUAL
```

---

## Why This Matters

Virtual dispatch enables **polymorphism**.

```
Parent reference
   ↓
calls child implementation
```

---

## Interview Trap — Constructor + Virtual Dispatch

Example:

```kotlin
open class Base {

    init {
        printMessage()
    }

    open fun printMessage() {}
}

class Child : Base() {

    val msg = "Hello"

    override fun printMessage() {
        println(msg.length)
    }
}
```

Execution:

```
Base init
 ↓
virtual dispatch
 ↓
Child method executed
 ↓
msg not initialized yet
```

Result:

```
null / crash
```

---

## Safe Rule

Never call **open methods in constructors**.

---

## Memory Trick

```
Virtual dispatch
= method chosen by object type at runtime
```

---

# Q2.5 — Class Modifiers

Kotlin classes are **final by default**.

```
final
open
abstract
```

Example:

```kotlin
class A
open class B
abstract class C
```

---

## Why Kotlin Uses `final` by Default

Java classes are open by default which caused the:

```
Fragile Base Class Problem
```

Subclasses can override behavior unexpectedly.

Kotlin forces developers to **explicitly allow inheritance**.

---

# Q2.6 — Inheritance Mechanics

Kotlin allows:

```
single class inheritance
multiple interface inheritance
```

Example:

```kotlin
interface A {
    fun foo() { println("A") }
}

interface B {
    fun foo() { println("B") }
}

class C : A, B {

    override fun foo() {
        super<A>.foo()
    }
}
```

---

## Property Overrides

Example:

```kotlin
open class Base {
    open val x = 1
}
```

Compiles to:

```
open fun getX()
```

Overriding property means **overriding method**.

---

# Q2.7 — Data Classes

Data classes automatically generate:

```
equals
hashCode
copy
toString
componentN
```

Example:

```kotlin
data class User(val id: Int, val name: String)
```

---

## Destructuring

Example:

```kotlin
val (id, name) = user
```

Uses:

```
component1()
component2()
```

---

## Important Rule

Only **primary constructor properties** participate.

Example:

```kotlin
data class User(val id: Int) {
    var loginTime: Long = 0
}
```

`loginTime` is ignored in equality.

---

# Q2.8 — Sealed Classes

Sealed classes define **closed type hierarchies**.

Example:

```kotlin
sealed class Result
```

Compiler knows **all subclasses**.

---

## Exhaustive `when`

```
when(result) {
    is Success -> ...
    is Error -> ...
}
```

Compiler ensures all branches handled.

---

# Q2.9 — Enum Classes

Example:

```kotlin
enum class Direction {
    NORTH,
    SOUTH
}
```

Generated members:

```
values()
valueOf()
```

Each enum entry is a **singleton instance**.

---

# Q2.10 — The `object` Keyword

Three uses:

```
object declaration
companion object
object expression
```

---

## Singleton Object

Example:

```kotlin
object Database
```

Compiled to:

```
Database class
 └ static INSTANCE
```

---

## Companion Object

Used for **static-like members**.

```
User.Companion
```

---

## Object Expression

Example:

```kotlin
val listener =
    object : ClickListener {}
```

Creates an **anonymous class instance**.

---

# Q2.11 — Nested vs Inner Classes

Example:

```kotlin
class Outer {

    class Nested

    inner class Inner
}
```

---

## Nested Class

```
static class
```

No reference to outer class.

---

## Inner Class

```
holds reference to outer instance
```

Memory model:

```
Outer
 └ Inner
     └ this$0 → Outer
```

This can cause **Android memory leaks**.

---

# Q2.12 — Delegation

Delegation allows composition without boilerplate.

Example:

```kotlin
class LoggingList<T>(
    private val list: MutableList<T>
) : MutableList<T> by list
```

---

## Concept

```
LoggingList
   │
   └ delegate → MutableList
```

Calls automatically forwarded.

---

# Q2.13 — Value Classes

Value classes provide **type safety without runtime allocation**.

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

## Boxing Scenarios

Value classes box when used in:

```
nullable types
generics
interfaces
```

---

# Master Mental Model

```
Kotlin class
   ↓
JVM class
   │
   ├ fields
   ├ methods
   ├ constructors
   └ static initializer
```

Object creation:

```
super constructor
↓
property initializers
↓
init blocks
↓
subclass initialization
```

---

# Self-Test

1. Why is virtual dispatch dangerous inside constructors?
2. Why are Kotlin classes `final` by default?
3. What is the difference between nested and inner classes?
4. When do value classes box?
5. Why should data class keys be immutable?
