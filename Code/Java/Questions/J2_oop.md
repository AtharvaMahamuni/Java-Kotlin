# Phase J2 — Object-Oriented Programming Internals

---

## J2.1 — Classes, final, abstract

> **Connects to:** [J2.2 — Interfaces: default & static methods](J2_oop.md#j22--interfaces-default--static-methods)

### WHY: Signals to the Compiler and JIT

The keywords `final` and `abstract` are not just design-level hints for human readers. They carry deep meaning to both the Java compiler and, more importantly, to the JIT (Just-In-Time) compiler at runtime. When the JIT sees that a class is `final`, it knows with certainty that no subclass will ever override any of its methods. This enables a powerful optimization called **devirtualization**: instead of performing an expensive virtual dispatch through the vtable (which requires a pointer dereference, a method table lookup, and an indirect call), the JIT can emit a direct call — or even inline the method body entirely. This is why `String`, `Integer`, `Long`, `Double`, and all other wrapper types in `java.lang` are declared `final`. Every method call on a `String` is a candidate for devirtualization.

`abstract`, on the other hand, signals incompleteness. An `abstract class` cannot be instantiated directly — it exists only to be subclassed. This forces a contract onto implementors while allowing the abstract class to carry shared state, concrete helper methods, and initialization logic that subclasses can reuse.

---

### `final class`: No Subclassing Allowed

```java
public final class ImmutablePoint {
    private final int x;
    private final int y;

    public ImmutablePoint(int x, int y) {
        this.x = x;
        this.y = y;
    }

    public int getX() { return x; }
    public int getY() { return y; }
}

// Compiler error: cannot inherit from final 'ImmutablePoint'
// class BadPoint extends ImmutablePoint {}
```

When the JIT encounters a call to `getX()` on an `ImmutablePoint` reference, it does not need to consult the vtable. It already knows there is exactly one `getX()` in existence — the one defined in `ImmutablePoint`. The JIT can inline the body (`return x;`) directly into the calling code, eliminating the call overhead entirely.

The JVM standard library relies on this heavily:

```java
// All of these are final — JIT devirtualizes all their methods
String s = "hello";
Integer i = 42;
Long l = 100L;
Double d = 3.14;
```

---

### `final method`: Devirtualization in a Non-Final Class

You can mark individual methods as `final` even in a non-final class. This tells the JIT: "even though this class can be subclassed, this particular method will never be overridden."

```java
public class Base {
    public final String identify() {
        return "Base";
    }

    public String describe() {       // NOT final — virtual dispatch
        return "A Base instance";
    }
}

class Child extends Base {
    // Compiler error: Cannot override the final method from Base
    // @Override public String identify() { return "Child"; }

    @Override
    public String describe() {       // This is fine — not final
        return "A Child instance";
    }
}
```

The bytecode difference is important:

```
// Call to a non-final method: uses INVOKEVIRTUAL (vtable lookup)
INVOKEVIRTUAL Base.describe:()Ljava/lang/String;

// Call to a final method: still compiles to INVOKEVIRTUAL in bytecode,
// BUT the JIT promotes this to a direct call / inline at runtime
// because it can prove no override exists
INVOKEVIRTUAL Base.identify:()Ljava/lang/String;
// → JIT: devirtualized to direct call or inlined
```

The bytecode itself still uses `INVOKEVIRTUAL` for `final` methods — devirtualization is a JIT-level optimization, not a bytecode-level change. However, because the JIT can verify that no subclass overrides the method (or that the declared type is final), it bypasses the vtable.

---

### `abstract class`: Forcing a Contract

An abstract class sits between a fully concrete class and an interface. It can contain:
- Abstract methods (no body — subclass must implement)
- Concrete methods (with body — subclass inherits and optionally overrides)
- Instance fields with state
- Constructors (always called by subclasses via `super()`)

```java
public abstract class Animal {
    private final String name;      // shared state in abstract class

    // Abstract classes DO have constructors — called by subclass
    public Animal(String name) {
        this.name = name;
    }

    // Abstract method — no body, subclass MUST implement
    public abstract String speak();

    // Concrete method — shared behavior, no need to override
    public String getName() {
        return name;
    }

    // Concrete method with default behavior — can override
    public String describe() {
        return getName() + " says: " + speak();
    }
}

class Dog extends Animal {
    public Dog(String name) {
        super(name);               // super() MUST be first statement
    }

    @Override
    public String speak() {
        return "Woof!";
    }
}

class Cat extends Animal {
    public Cat(String name) {
        super(name);
    }

    @Override
    public String speak() {
        return "Meow!";
    }
}
```

An abstract class with ZERO abstract methods is also legal. It is simply a class that cannot be instantiated directly but carries shared logic:

```java
public abstract class AbstractLogger {
    // Zero abstract methods — still cannot do: new AbstractLogger()
    public void log(String msg) {
        System.out.println("[LOG] " + msg);
    }
}
```

---

### Constructor Execution Order

Java enforces a strict execution order for initialization. This order is:

```
1. Static initializers (run once, when class is loaded)
2. Instance initializers (run each time an object is constructed, before constructor body)
3. Constructor body
```

```java
public class InitOrder {
    static int staticCounter;

    static {
        staticCounter = 10;
        System.out.println("1. Static initializer: staticCounter = " + staticCounter);
    }

    int instanceField = initInstance();  // runs before constructor body

    {
        System.out.println("2. Instance initializer block");
    }

    public InitOrder() {
        System.out.println("3. Constructor body");
    }

    private int initInstance() {
        System.out.println("  (instance field initialization)");
        return 42;
    }
}

// Output when doing: new InitOrder();
// 1. Static initializer: staticCounter = 10
//   (instance field initialization)
// 2. Instance initializer block
// 3. Constructor body
```

When inheritance is involved, the order extends: each level calls `super()` first, so parent initialization fully completes before child initialization begins.

```java
class Parent {
    Parent() { System.out.println("Parent constructor"); }
}

class Child extends Parent {
    Child() {
        super();   // compiler inserts this automatically if you don't write it
        System.out.println("Child constructor");
    }
}
// Output: Parent constructor → Child constructor
```

The compiler enforces that `super()` (or `this()` for constructor chaining) is the **first statement** in a constructor. You cannot call any instance methods or access instance fields before the superclass is initialized.

---

### `instanceof` With Abstract Classes

Abstract classes work fine with `instanceof`. The check applies to the concrete runtime type:

```java
Animal a = new Dog("Rex");
System.out.println(a instanceof Animal);  // true — Dog IS-A Animal
System.out.println(a instanceof Dog);     // true — it is a Dog
System.out.println(a instanceof Cat);     // false — it is not a Cat
```

---

### Memory Layout Diagram

```
Stack                 Heap
┌─────────────┐       ┌──────────────────────────────────────┐
│ a (ref)  ───┼──────►│ Dog object                           │
└─────────────┘       │  ┌─────────────────────────────────┐ │
                      │  │ Object header (mark word + klass)│ │
                      │  ├─────────────────────────────────┤ │
                      │  │ name (inherited from Animal)     │ │
                      │  │   → "Rex" (String ref on heap)  │ │
                      │  └─────────────────────────────────┘ │
                      └──────────────────────────────────────┘

Method Area (Metaspace)
┌────────────────────────────────────────────┐
│ Dog vtable                                 │
│   [0] speak()        → Dog.speak          │
│   [1] describe()     → Animal.describe    │
│   [2] getName()      → Animal.getName     │
└────────────────────────────────────────────┘
```

---

### Interview Trap

**"Can an abstract class have a constructor?"** Yes — always. Abstract classes always have constructors. The constructors are called by subclass constructors via `super()`. You cannot call `new AbstractClass()` directly, but the constructor still runs when you instantiate a concrete subclass.

**"Can an abstract class have all concrete methods?"** Yes. An abstract class with zero abstract methods is legal Java. It simply prevents direct instantiation while allowing subclassing. This is useful when you want to allow subclassing but not direct instantiation for design reasons.

**"Is a `final` method call faster?"** At bytecode level: no — it still emits `INVOKEVIRTUAL`. At JIT level: yes — the JIT can devirtualize and inline it. The performance difference only matters in hot loops.

---

## J2.2 — Interfaces: default & static methods

> **Builds on:** [J2.1 — Classes, final, abstract](J2_oop.md#j21--classes-final-abstract)
> **Connects to:** [J2.3 — Enums Internals](J2_oop.md#j23--enums-internals)

### WHY: Interface Evolution Without Breaking the World

Before Java 8, interfaces were a rigid contract. Every method declared in an interface had to be implemented by every implementing class. This meant that adding a single new method to a widely-used interface — say, `java.util.Collection` — would immediately break every class in the world that implemented it. This was known as the "interface evolution problem," and it was a genuine crisis when the Java team wanted to add stream-based methods to the collections framework for Java 8.

The solution was `default` methods: methods with a body in an interface. Any implementing class that does not override a `default` method simply inherits the default body. Existing code keeps compiling. New code gets the new functionality. This enabled the Java team to add `stream()`, `forEach()`, `spliterator()`, and `removeIf()` to `Collection` without breaking a single existing implementation.

---

### `default` Methods: Inherited Body

```java
public interface Greeter {
    String greet(String name);   // abstract — must implement

    default String greetLoudly(String name) {   // default — optional override
        return greet(name).toUpperCase();
    }
}

class FormalGreeter implements Greeter {
    @Override
    public String greet(String name) {
        return "Good day, " + name;
    }
    // greetLoudly is inherited from interface — no need to override
}

class CasualGreeter implements Greeter {
    @Override
    public String greet(String name) {
        return "Hey " + name + "!";
    }

    @Override
    public String greetLoudly(String name) {   // can override if desired
        return "HEY " + name.toUpperCase() + "!!!";
    }
}
```

---

### `static` Methods in Interfaces (Java 8+)

Static methods in interfaces belong to the interface itself, not to implementing classes. They are utility methods that live alongside the interface definition — similar to how `java.util.Collections` is a utility class for the `Collection` interface, but now embedded directly.

```java
public interface Validator<T> {
    boolean validate(T value);

    static <T> Validator<T> noOp() {        // called as Validator.noOp()
        return value -> true;
    }

    static Validator<String> nonEmpty() {   // factory on the interface
        return value -> value != null && !value.isEmpty();
    }
}

// Correct usage:
Validator<String> v = Validator.nonEmpty();

// Won't compile — static interface methods are NOT inherited:
// class MyValidator implements Validator<String> { ... }
// MyValidator.nonEmpty();  // ERROR
```

This is a key difference from `default` methods. `default` methods ARE inherited by implementing classes. `static` methods are NOT.

---

### `private` Methods in Interfaces (Java 9+)

When you have two `default` methods that share common logic, you don't want to expose that shared logic publicly. Java 9 added `private` methods to interfaces specifically for this use case:

```java
public interface Logger {
    default void logInfo(String msg) {
        log("INFO", msg);    // delegates to private helper
    }

    default void logError(String msg) {
        log("ERROR", msg);   // same private helper
    }

    private void log(String level, String msg) {   // not visible outside
        System.out.printf("[%s] %s%n", level, msg);
    }
}
```

`private static` methods in interfaces are also allowed for helpers used by static interface methods.

---

### The Diamond Problem With Default Methods

Multiple inheritance of state is forbidden in Java (no extending multiple classes), but multiple inheritance of behavior (via interfaces) creates the classic diamond problem:

```java
interface A {
    default void hello() { System.out.println("A"); }
}

interface B extends A {
    @Override
    default void hello() { System.out.println("B"); }
}

interface C extends A {
    @Override
    default void hello() { System.out.println("C"); }
}

// D inherits from both B and C — which hello() wins?
class D implements B, C {
    @Override
    public void hello() {
        B.super.hello();   // must explicitly choose one
        // C.super.hello();  // could also call C's version
    }
}
```

The resolution rules are:

1. **A class or superclass method always wins over any interface default.** If `D` itself defines `hello()`, or if any superclass of `D` defines `hello()`, that wins unconditionally.
2. **A more specific interface wins.** If one interface is a subtype of another, the more specific interface's default wins. Here, neither `B` nor `C` is more specific than the other.
3. **If still ambiguous, the class must explicitly override and call the desired version via `InterfaceName.super.method()`.**

---

### `INVOKEINTERFACE` vs `INVOKEVIRTUAL`

When a class implements an interface and you call a method through an interface reference, the JVM uses `INVOKEINTERFACE`. When calling through a class reference, it uses `INVOKEVIRTUAL`. The difference lies in how method lookup works:

```
Class-based dispatch (INVOKEVIRTUAL):
  └── vtable (virtual method table) — indexed by method slot
      Simple array lookup: vtable[slot_index] → method pointer
      O(1) — known slot at compile time

Interface-based dispatch (INVOKEINTERFACE):
  └── itable (interface method table) — secondary lookup structure
      Must find the right interface in the class's itable, then find method
      Slightly more complex — different classes implementing the same interface
      may have the method at different vtable slots
```

```java
ArrayList<String> list = new ArrayList<>();
list.add("hello");                   // INVOKEVIRTUAL — ArrayList reference

List<String> iface = list;
iface.add("world");                  // INVOKEINTERFACE — List interface reference
```

The JIT typically handles this with inline caches — after the first call, it caches the resolved method and subsequent calls are fast.

---

### Interview Trap

**"Can you call a static interface method via an implementing class reference?"** No. `MyInterface.staticMethod()` is valid. `myImplementation.staticMethod()` does not compile. This is unlike static methods in classes, which CAN be called on an instance (though it's bad style).

**"What happens if a class implements two interfaces with the same default method, but one interface's default comes from a super-interface?"** The more specific (child) interface wins. No override required.

**"Can an interface default method call abstract methods on `this`?"** Yes — and this is a powerful pattern. The default method calls `this.abstractMethod()`, and the concrete implementation at runtime provides the result.

---

## J2.3 — Enums Internals

> **Builds on:** [J2.2 — Interfaces: default & static methods](J2_oop.md#j22--interfaces-default--static-methods)
> **Connects to:** [J2.4 — Records (Java 16+)](J2_oop.md#j24--records-java-16)

### WHY: The Problem With the Int Enum Pattern

Before Java 5 enums, developers used the "int enum pattern":

```java
// Old style — int enum pattern
public static final int SEASON_SPRING = 0;
public static final int SEASON_SUMMER = 1;
public static final int SEASON_FALL   = 2;
public static final int SEASON_WINTER = 3;
```

This has severe problems: no type safety (you can pass any `int` where a season is expected), no namespace (all constants pollute the same class), no meaningful `toString()`, and no way to iterate over all values. Java enums solve all of these by making each constant a full object.

---

### What an Enum Compiles To

The decompiled output of a simple enum reveals the full machinery:

```java
// Source code:
public enum Color { RED, GREEN, BLUE }

// What the compiler generates (decompiled):
public final class Color extends Enum<Color> {

    // Each constant is a public static final instance of the class itself
    public static final Color RED   = new Color("RED",   0);
    public static final Color GREEN = new Color("GREEN", 1);
    public static final Color BLUE  = new Color("BLUE",  2);

    // Internal array holding all values — used by values()
    private static final Color[] $VALUES = { RED, GREEN, BLUE };

    // Private constructor — enum constructors are always private
    private Color(String name, int ordinal) {
        super(name, ordinal);   // calls Enum(String, int)
    }

    // Returns a CLONE of $VALUES — prevents external mutation
    public static Color[] values() {
        return $VALUES.clone();
    }

    // Looks up by name — throws IllegalArgumentException if not found
    public static Color valueOf(String name) {
        return (Color) Enum.valueOf(Color.class, name);
    }
}
```

The class is `final` (cannot be subclassed), extends `Enum<Color>` (so it cannot extend anything else), and each constant is initialized in a static initializer block when the class is first loaded.

---

### Why Must Enum Constructors Be Private?

The constraint "enum constructors are always private" exists to enforce the **singleton guarantee** for each constant.

The invariant: for any enum constant, there is **exactly one instance** of that constant in the JVM, forever. Every reference to `Color.RED` points to the same object. This is a stronger guarantee than any regular singleton — the compiler and JVM both enforce it.

If the constructor were not private, you could write:

```java
// Hypothetical — does NOT compile because enum constructors are private
Color red2 = new Color("RED", 0);

// Now: Color.RED == red2   → false
// Same name, same ordinal, different object identity
```

This breaks:
1. **Identity equality** — `Color.RED == someColor` would no longer reliably test "is this the RED constant?"
2. **switch statements** — Java switch on enums uses identity comparison under the hood. A second `RED` instance would fall through every case.
3. **`EnumSet` / `EnumMap`** — These use the ordinal as a bit-index. Two `RED` instances with `ordinal = 0` would both map to bit 0, corrupting the set.
4. **Serialization** — Java's enum serialization is special: deserializing an enum reads the `name` field and calls `Enum.valueOf()` to return the existing singleton. If you could construct enums freely, deserialization would return a NEW object, breaking identity (`readObject()` is even disabled for enums).

The private constructor, combined with `final class` and JVM-level special handling of enum serialization, makes each constant a true singleton — not just by convention, but by language enforcement.

---

### `values()` Clones the Array Every Call

This is a subtle performance trap. Every call to `Color.values()` creates a new array:

```java
// BAD: creates a new Color[] on every loop iteration check
for (Color c : Color.values()) {
    System.out.println(c);
}

// In a tight inner loop, this allocates garbage on every call.
// Prefer caching the array:
private static final Color[] ALL_COLORS = Color.values();  // cache once

for (Color c : ALL_COLORS) {
    System.out.println(c);
}
```

The clone is there for safety — if `values()` returned the internal `$VALUES` array directly, external code could corrupt it with `Color.values()[0] = null`. The clone prevents this.

---

### `ordinal()` vs Named Fields

`ordinal()` returns the 0-based position of the constant in the declaration order. This is fragile:

```java
enum Priority { LOW, MEDIUM, HIGH }
// LOW.ordinal() == 0, MEDIUM.ordinal() == 1, HIGH.ordinal() == 2

// If someone inserts CRITICAL before HIGH:
enum Priority { LOW, MEDIUM, CRITICAL, HIGH }
// Now HIGH.ordinal() == 3 — all code using ordinals is broken
```

The safe pattern is to store the meaningful value as an explicit field:

```java
public enum Priority {
    LOW(1), MEDIUM(5), HIGH(10), CRITICAL(100);

    private final int level;

    Priority(int level) {     // constructor — always private
        this.level = level;
    }

    public int getLevel() { return level; }
}
// Priority.HIGH.getLevel() == 10 — stable regardless of declaration order
```

---

### Enum With Abstract Methods: Constant-Specific Bodies

Each enum constant can have its own class body, even overriding abstract methods:

```java
public enum Operation {
    ADD {
        @Override
        public int apply(int x, int y) { return x + y; }
    },
    SUBTRACT {
        @Override
        public int apply(int x, int y) { return x - y; }
    },
    MULTIPLY {
        @Override
        public int apply(int x, int y) { return x * y; }
    };

    public abstract int apply(int x, int y);
}

// Usage:
int result = Operation.ADD.apply(3, 4);      // 7
int result2 = Operation.MULTIPLY.apply(3, 4); // 12
```

Under the hood, each constant with a body becomes an anonymous subclass of `Operation`. This is why `ADD.getClass()` returns `Operation$1` (an anonymous inner class), not `Operation` itself.

---

### `EnumSet` and `EnumMap`: Performance-Optimized Collections

`EnumSet` is backed by a single `long` (for enums with ≤ 64 constants) used as a bit vector. Each constant's `ordinal()` corresponds to a bit position:

```java
EnumSet<Color> warm = EnumSet.of(Color.RED, Color.GREEN);
// Internally: long bits = 0b011 (bit 0 for RED, bit 1 for GREEN)

warm.contains(Color.RED);   // (bits & (1L << RED.ordinal())) != 0 — O(1)
warm.add(Color.BLUE);       // bits |= (1L << BLUE.ordinal()) — O(1)
warm.remove(Color.RED);     // bits &= ~(1L << RED.ordinal()) — O(1)
```

```
Bit layout for EnumSet<Color>:
Position:  ... 2       1       0
Constant:  ... BLUE    GREEN   RED
Bit value:     1       1       0   → contains GREEN and BLUE, not RED
```

`EnumMap` is backed by an `Object[]` array indexed directly by `ordinal()`:

```java
EnumMap<Color, String> descriptions = new EnumMap<>(Color.class);
descriptions.put(Color.RED, "The color red");
// Internally: Object[] table[RED.ordinal()] = "The color red"
// Get: table[key.ordinal()] — no hashing, pure array access
```

Both are dramatically faster than `HashSet`/`HashMap` for enum keys due to zero hashing overhead.

---

### `switch` on Enum: Compiled to ordinals

```java
Color c = Color.GREEN;
switch (c) {
    case RED:   System.out.println("red");   break;
    case GREEN: System.out.println("green"); break;
    case BLUE:  System.out.println("blue");  break;
}

// Compiled approximately as:
// int[] $switchMap = {RED.ordinal()→0, GREEN.ordinal()→1, BLUE.ordinal()→2};
// tableswitch on $switchMap[c.ordinal()]
```

---

### Interview Trap

**"Can you make an enum constructor public?"** You can write `public` in the source, but the compiler silently converts it to `private`. Enum constructors are always private — there is no way to construct an enum constant from outside the enum class body.

**"Can enums extend other classes?"** No. Enums implicitly extend `java.lang.Enum<E>`, and Java does not support multiple class inheritance. An enum CANNOT extend any other class.

**"Can enums implement interfaces?"** Yes. This is the recommended way to add polymorphic behavior to enums. Each constant (or the enum class as a whole) can implement interface methods.

---

## J2.4 — Records (Java 16+)

> **Builds on:** [J2.3 — Enums Internals](J2_oop.md#j23--enums-internals)
> **Connects to:** [J2.5 — Sealed Classes (Java 17+)](J2_oop.md#j25--sealed-classes-java-17)

### WHY: The Data Class Boilerplate Problem

Before records, writing a simple data-holding class in Java required enormous boilerplate. Consider a 2D point:

```java
// Pre-record Java — 30+ lines for a trivial concept
public final class Point {
    private final int x;
    private final int y;

    public Point(int x, int y) {
        this.x = x;
        this.y = y;
    }

    public int getX() { return x; }
    public int getY() { return y; }

    @Override
    public boolean equals(Object o) {
        if (this == o) return true;
        if (!(o instanceof Point)) return false;
        Point point = (Point) o;
        return x == point.x && y == point.y;
    }

    @Override
    public int hashCode() {
        return Objects.hash(x, y);
    }

    @Override
    public String toString() {
        return "Point[x=" + x + ", y=" + y + "]";
    }
}
```

Records collapse this to one line:

```java
record Point(int x, int y) {}
```

---

### What the Compiler Generates

```java
record Point(int x, int y) {}

// Equivalent generated code (conceptual):
public final class Point extends Record {

    private final int x;      // private final — always
    private final int y;

    // Canonical constructor
    public Point(int x, int y) {
        this.x = x;
        this.y = y;
    }

    // Accessors — NOTE: x() not getX()
    public int x() { return this.x; }
    public int y() { return this.y; }

    // equals: component-wise comparison using all fields
    @Override
    public final boolean equals(Object o) {
        if (!(o instanceof Point)) return false;
        Point other = (Point) o;
        return this.x == other.x && this.y == other.y;
    }

    // hashCode: based on all components
    @Override
    public final int hashCode() {
        return Objects.hash(x, y);
    }

    // toString: Point[x=1, y=2] format
    @Override
    public final String toString() {
        return "Point[x=" + x + ", y=" + y + "]";
    }
}
```

---

### The Compact Constructor: Validation Without Redundancy

The compact constructor lets you add validation without re-listing the parameters in the assignment. The compiler automatically appends the assignments after your block:

```java
record Range(int min, int max) {
    // Compact constructor — no parameter list, no this.min = min
    Range {
        if (min > max) {
            throw new IllegalArgumentException(
                "min (" + min + ") must be <= max (" + max + ")"
            );
        }
        // Compiler implicitly appends:
        // this.min = min;
        // this.max = max;
    }
}

// Valid usage:
Range r1 = new Range(1, 10);     // OK
Range r2 = new Range(10, 1);     // throws IllegalArgumentException
```

You can also normalize inputs in a compact constructor:

```java
record NormalizedString(String value) {
    NormalizedString {
        value = value.trim().toLowerCase();  // reassign parameter before implicit assignment
    }
}

NormalizedString ns = new NormalizedString("  HELLO  ");
System.out.println(ns.value());  // "hello"
```

---

### Custom Accessor Overriding

You can override the generated accessor with custom logic:

```java
record Circle(double radius) {
    // Custom accessor with additional logic
    public double radius() {
        return Math.abs(radius);   // normalize negative radius
    }

    // Additional methods are fine
    public double area() {
        return Math.PI * radius() * radius();
    }
}
```

---

### Records and Interfaces

Records can implement interfaces, making them very useful for modeling typed values:

```java
public interface Shape {
    double area();
}

record Circle(double radius) implements Shape {
    @Override
    public double area() {
        return Math.PI * radius * radius;
    }
}

record Rectangle(double width, double height) implements Shape {
    @Override
    public double area() {
        return width * height;
    }
}
```

---

### Limitations of Records

```
┌─────────────────────────────────────────────────────────┐
│ Records CANNOT:                                         │
│   - Extend any class (implicitly extend Record)         │
│   - Be subclassed (implicitly final)                    │
│   - Declare additional instance fields beyond components│
│   - Have mutable state (all fields are final)           │
│                                                         │
│ Records CAN:                                            │
│   - Implement interfaces                                │
│   - Have static fields and methods                      │
│   - Have instance methods                               │
│   - Override generated equals/hashCode/toString         │
│   - Have custom (non-compact) canonical constructor     │
│   - Have additional constructors (must delegate to      │
│     canonical via this(...))                            │
└─────────────────────────────────────────────────────────┘
```

```java
record Person(String name, int age) {
    // Static field: allowed
    public static final int ADULT_AGE = 18;

    // Additional constructor — must call this(canonical)
    public Person(String name) {
        this(name, 0);   // delegates to canonical constructor
    }

    // Static method: allowed
    public static Person unknown() {
        return new Person("Unknown", -1);
    }

    // Instance method: allowed
    public boolean isAdult() {
        return age >= ADULT_AGE;
    }
}
```

---

### Interview Trap

**"How do you access a record field — `point.getX()` or `point.x()`?"** Records use `point.x()` — the accessor name matches the component name directly, without the `get` prefix. This breaks the JavaBean convention deliberately, since records are not JavaBeans.

**"Does this break Spring/Hibernate/Jackson?"** Potentially yes. Many frameworks expect JavaBean convention (`getX()`). Jackson (since 2.12) supports records natively. Hibernate has record support. For frameworks that strictly require JavaBeans, you may need `@JsonProperty` annotations or custom configuration.

**"Can a record field be null?"** Yes, unless you validate in the compact constructor. Records themselves have no built-in null-safety.

---

## J2.5 — Sealed Classes (Java 17+)

> **Builds on:** [J2.4 — Records (Java 16+)](J2_oop.md#j24--records-java-16)
> **Connects to:** [J3.1 — Type Erasure](J3_generics.md#j31--type-erasure)

### WHY: Controlled Inheritance for Closed Hierarchies

Java has always offered two extremes of class inheritance control:
- `final`: no subclasses at all
- No modifier: any class in any package can extend it

Sealed classes fill the middle ground: "you can subclass me, but only if you're on my approved list." This is enormously useful for modeling domain hierarchies where you know all the variants upfront — like AST nodes, network protocol messages, UI events, or geometric shapes.

The key insight is that a **closed set of subtypes enables exhaustive analysis**. When the compiler knows every possible subtype, it can verify that a `switch` expression covers all cases — without a `default` branch.

---

### The `permits` Clause

```java
// A sealed interface — only these three types may implement it
public sealed interface Shape
    permits Circle, Rectangle, Triangle {}

// Each permitted type must be one of: final, sealed, or non-sealed
public final record Circle(double radius) implements Shape {}

public final record Rectangle(double width, double height) implements Shape {}

public final record Triangle(double base, double height) implements Shape {}
```

The permitted subclasses must be in the **same package** (or same compilation unit) as the sealed class. This ensures the "closed set" invariant at compile time.

---

### Exhaustive Pattern Matching Switch (Java 21+)

The payoff for sealed classes is exhaustive switch expressions:

```java
double area(Shape shape) {
    return switch (shape) {
        case Circle c    -> Math.PI * c.radius() * c.radius();
        case Rectangle r -> r.width() * r.height();
        case Triangle t  -> 0.5 * t.base() * t.height();
        // No default needed — compiler knows ALL possible shapes!
        // If you add a new Shape subclass, this switch becomes a compile error.
    };
}
```

Without sealed classes, the compiler cannot know if there are other `Shape` implementations lurking in other packages, so a `default` branch would be required. With sealed classes, the compiler has certainty.

---

### `final` vs `sealed` vs `non-sealed`

The three allowed modifiers for permitted subclasses represent different extension policies:

```java
public sealed interface Expr
    permits Literal, BinaryOp, UnaryOp {}

// final — completely closed, no further subclassing
public final class Literal implements Expr {
    private final int value;
    public Literal(int value) { this.value = value; }
    public int value() { return value; }
}

// sealed — extends the hierarchy in a controlled way
public sealed class BinaryOp implements Expr
    permits AddOp, MulOp {}

public final class AddOp extends BinaryOp { ... }
public final class MulOp extends BinaryOp { ... }

// non-sealed — reopens the hierarchy completely
// (anyone can extend UnaryOp from any package)
public non-sealed class UnaryOp implements Expr {
    // This branch of the hierarchy is open again
}
```

---

### Abstract Sealed Classes

A sealed class can be abstract, enforcing a contract on all permitted subclasses:

```java
public abstract sealed class Vehicle
    permits Car, Truck, Motorcycle {

    private final String licensePlate;

    protected Vehicle(String licensePlate) {
        this.licensePlate = licensePlate;
    }

    public String getLicensePlate() { return licensePlate; }

    // All permitted subclasses must implement this
    public abstract int getWheelCount();
}

public final class Car extends Vehicle {
    public Car(String plate) { super(plate); }

    @Override
    public int getWheelCount() { return 4; }
}

public final class Motorcycle extends Vehicle {
    public Motorcycle(String plate) { super(plate); }

    @Override
    public int getWheelCount() { return 2; }
}
```

---

### Sealed Class + Records = Algebraic Data Types

The combination of sealed interfaces with record implementations is Java's answer to algebraic data types (ADTs) — a pattern well-known from functional languages and Kotlin:

```java
// Java ADT: a Result type that is either Success or Failure
public sealed interface Result<T>
    permits Result.Success, Result.Failure {

    record Success<T>(T value) implements Result<T> {}
    record Failure<T>(String error) implements Result<T> {}
}

// Exhaustive switch — compiler verifies all cases
Result<Integer> result = computeSomething();
String message = switch (result) {
    case Result.Success<Integer> s -> "Got: " + s.value();
    case Result.Failure<Integer> f -> "Error: " + f.error();
};
```

This pattern replaces checked exceptions in many modern Java APIs, and mirrors Kotlin's `sealed class` + `data class` combination exactly.

---

### Bytecode: The `PermittedSubclasses` Attribute

Sealed classes add a new attribute to the class file format (`PermittedSubclasses`), introduced in Java 17. You can inspect it with `javap -v`:

```
// javap -v Shape.class output (abbreviated):
public abstract interface Shape
  PermittedSubclasses:
    Circle
    Rectangle
    Triangle
```

At runtime, the JVM uses this attribute to enforce the sealed contract — a class not in the `PermittedSubclasses` list cannot extend the sealed type, even through reflection or bytecode manipulation.

---

### Diagram: Sealed Hierarchy vs Open Hierarchy

```
Open Hierarchy (before sealed):           Sealed Hierarchy:

   Shape (interface)                         Shape (sealed interface)
   ├── Circle                                permits: Circle, Rectangle, Triangle
   ├── Rectangle                             │
   ├── Triangle                              ├── Circle (final)
   ├── Hexagon (external!)                   ├── Rectangle (final)
   ├── AnyOtherShape (external!)             └── Triangle (final)
   └── ...unlimited subclasses
                                             Compiler knows: ONLY these 3 exist.
   Compiler: cannot know all cases.          Exhaustive switch is safe.
   Must use default branch.
```

---

### Interview Trap

**"Can a sealed class and its permitted subclasses be in different packages?"** Only if they are in the same module (named module). For unnamed modules (most apps), they must be in the same package or the same compilation unit.

**"Can a sealed class be abstract?"** Yes. Abstract sealed classes are common — they enforce both the abstract contract (subclasses must implement abstract methods) and the sealed contract (only permitted subclasses can extend).

**"What happens at runtime if you try to extend a sealed class via bytecode manipulation?"** The JVM enforces the `PermittedSubclasses` attribute at class loading time. An attempt to load a class extending a sealed type not listed in `PermittedSubclasses` throws `IncompatibleClassChangeError`.

**"Must all permitted subclasses directly extend the sealed type?"** Yes. You cannot have a permitted subclass that extends another permitted subclass (unless the intermediate class is itself sealed with its own permits list).

---

## Master Summary: OOP Internals in 5 Points

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  PHASE J2 — OOP INTERNALS MASTER SUMMARY                                     │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  1. FINAL & ABSTRACT (J2.1)                                                  │
│     • final class = no subclasses → JIT devirtualizes ALL method calls       │
│     • final method = no override → JIT can inline even in non-final class    │
│     • abstract class = cannot instantiate, CAN have constructors & state     │
│     • Constructor order: static init → instance init → constructor body      │
│     • super() must be the FIRST statement in any constructor                 │
│                                                                              │
│  2. INTERFACES (J2.2)                                                        │
│     • default methods = interface evolution without breaking impls (Java 8)  │
│     • static methods = utility on interface, NOT inherited by impls          │
│     • private methods = internal helpers for default/static (Java 9)         │
│     • Diamond: class wins > specific interface wins > must explicitly resolve │
│     • INVOKEVIRTUAL (class ref) vs INVOKEINTERFACE (interface ref) dispatch  │
│                                                                              │
│  3. ENUMS (J2.3)                                                             │
│     • Each constant = public static final instance of a final class          │
│     • Constructor always private; enum extends Enum<E>, cannot extend other  │
│     • values() clones the array every call — cache in tight loops            │
│     • ordinal() is fragile on reorder; prefer explicit named fields          │
│     • EnumSet = bit vector (O(1)); EnumMap = ordinal-indexed array (O(1))   │
│                                                                              │
│  4. RECORDS (J2.4)                                                           │
│     • One-line data classes: fields, canonical constructor, equals,          │
│       hashCode, toString all generated                                       │
│     • Accessor naming: x() not getX() — breaks JavaBean convention           │
│     • Compact constructor: validate/normalize, compiler appends assignments  │
│     • Implicitly final; cannot extend classes; CAN implement interfaces      │
│     • All fields are private final — records are immutable by design         │
│                                                                              │
│  5. SEALED CLASSES (J2.5)                                                    │
│     • permits clause = closed set of subclasses known at compile time        │
│     • Enables exhaustive switch without default branch (Java 21)             │
│     • Permitted subtype must be: final | sealed | non-sealed                 │
│     • sealed + record = Java's algebraic data types (like Kotlin sealed)     │
│     • JVM enforces via PermittedSubclasses class file attribute              │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

*← [Phase J1 — Type System](J1_type_system.md) | [Phase J3 — Generics →](J3_generics.md)*

---

**Cross-references:**
- Records (J2.4) vs Kotlin data classes — same concept, different syntax: [Kotlin 02 — Classes & Objects](../../Kotlin/Questions/02_classes_and_objects.md)
- Sealed classes (J2.5) — Kotlin's sealed classes are more powerful (subclasses not restricted to same file in Kotlin 1.5+): [Kotlin 02 — sealed class](../../Kotlin/Questions/02_classes_and_objects.md)
- Sealed classes + exhaustive switch expressions (Java 21): [J9.2 — Pattern Matching](J9_modern_java.md)
