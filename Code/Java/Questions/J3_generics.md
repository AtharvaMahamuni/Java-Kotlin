# Phase J3 — Generics

---

## J3.1 — Type Erasure

> **Connects to:** [J3.2 — Wildcards & PECS](J3_generics.md#j32--wildcards--pecs)

### WHY: Binary Compatibility Was Non-Negotiable

When Java 5 introduced generics in 2004, the JVM bytecode format could not change in a way that would break the millions of existing `.class` files compiled with Java 1.4. The Java team needed generics to provide compile-time type safety while generating bytecode that was binary-compatible with pre-generic code. The solution they chose was **type erasure**: all generic type information exists only in the source code and `.class` file metadata (for reflection), but is completely stripped from the actual bytecode instructions.

This means that `List<String>` and `List<Integer>` produce nearly identical bytecode. The generic type parameter is used by the compiler to insert type checks (casts) at the right places, but the JVM itself never sees `<String>` or `<Integer>` at runtime.

---

### What Erasure Actually Means

At runtime, every parameterized type collapses to its raw form:

```java
List<String>  strings  = new ArrayList<>();
List<Integer> integers = new ArrayList<>();
List<Double>  doubles  = new ArrayList<>();

// All three are identical at runtime:
System.out.println(strings.getClass());   // class java.util.ArrayList
System.out.println(integers.getClass());  // class java.util.ArrayList
System.out.println(doubles.getClass());   // class java.util.ArrayList

// Proof — they are literally the same class:
System.out.println(strings.getClass() == integers.getClass());  // true
```

The compiler uses the type parameter to generate casts at call sites. When you do:

```java
List<String> list = new ArrayList<>();
list.add("hello");
String s = list.get(0);   // no cast in source code
```

The compiler generates bytecode equivalent to:

```java
List list = new ArrayList();    // raw type in bytecode
list.add("hello");
String s = (String) list.get(0);   // compiler inserts checkcast
```

---

### Erasure Rules in Detail

```
Type Parameter              →   Erases To
─────────────────────────────────────────
T                           →   Object
T extends Comparable        →   Comparable
T extends Serializable      →   Serializable  (first bound)
T extends A & B & C         →   A             (first bound)
List<T>                     →   List
List<String>                →   List
Map<K, V>                   →   Map
T[]                         →   Object[]
```

```java
// Generic method before erasure:
public <T extends Comparable<T>> T max(T a, T b) {
    return a.compareTo(b) > 0 ? a : b;
}

// After erasure (what the JVM sees):
public Comparable max(Comparable a, Comparable b) {
    return a.compareTo(b) > 0 ? a : b;
}
// The return type is Comparable, and call sites get a (ReturnType) cast inserted.
```

---

### Why `instanceof List<String>` Fails

Because `List<String>` and `List<Integer>` are the same thing at runtime, the JVM cannot distinguish them. The compiler forbids the test:

```java
Object obj = new ArrayList<String>();

// Compile error: Cannot perform instanceof check against
// parameterized type List<String>. Use List<?> instead.
if (obj instanceof List<String>) { }   // ERROR

// Correct — unbounded wildcard is reifiable:
if (obj instanceof List<?>) { }        // OK
```

**Reifiable types** are types whose full type information is available at runtime:
- Primitive types: `int`, `double`, etc.
- Non-generic classes: `String`, `Object`, `Thread`
- Raw types: `List`, `Map`
- Unbounded wildcard parameterizations: `List<?>`, `Map<?, ?>`
- Arrays of reifiable types: `String[]`, `int[]`, `List<?>[]`

---

### Bridge Methods: Erasure Creates a Compatibility Problem

Consider a generic class being subclassed with a concrete type:

```java
public class Processor<T> {
    public T process(T input) {
        return input;
    }
}

class StringProcessor extends Processor<String> {
    @Override
    public String process(String input) {
        return input.toUpperCase();
    }
}
```

After erasure, `Processor<String>` becomes `Processor` with `process(Object)`. But `StringProcessor.process(String)` has a different signature than `process(Object)`. The JVM would not consider it an override.

To fix this, the compiler synthesizes a **bridge method**:

```java
// What the compiler actually generates in StringProcessor:
class StringProcessor extends Processor {
    // Your override:
    public String process(String input) {
        return input.toUpperCase();
    }

    // Compiler-generated bridge method — marked synthetic in bytecode:
    @Override
    public Object process(Object input) {  // matches erased parent signature
        return process((String) input);    // delegates, with cast
    }
}
```

You can see bridge methods with `javap -v`:

```
// javap -v StringProcessor.class (relevant excerpt):
public java.lang.String process(java.lang.String);
  Code:
    0: aload_1
    1: invokevirtual #2  // String.toUpperCase
    4: areturn

public java.lang.Object process(java.lang.Object);  // bridge method
  flags: ACC_PUBLIC, ACC_BRIDGE, ACC_SYNTHETIC
  Code:
    0: aload_0
    1: aload_1
    2: checkcast     #3  // class String
    5: invokevirtual #4  // StringProcessor.process(String)
    8: areturn
```

---

### Heap Pollution: When Erasure Goes Wrong

Heap pollution occurs when a variable of a parameterized type refers to an object that is not of that parameterized type. Erasure makes this possible:

```java
List rawList = new ArrayList<String>();   // raw type — no warning on creation
rawList.add(42);                          // unchecked — adds Integer to "String list"

List<String> stringList = rawList;        // unchecked assignment warning — but compiles!

// The ClassCastException happens HERE, not at the assignment above:
String s = stringList.get(0);
// Bytecode: (String) rawList.get(0) → ClassCastException: Integer cannot be cast to String
```

The deceptive part is that the exception does not happen at the line that looks wrong (`rawList.add(42)` or the assignment). It happens at an innocent-looking getter call, because that is where the compiler inserted the `checkcast` bytecode instruction.

---

### Diagram: Type Information Through Compilation Stages

```
Source Code              .class Metadata              JVM Bytecode
──────────────           ────────────────             ─────────────
List<String>        →    Signature: List<String>  →   List (raw)
                         (stored in Signature       (no generic info
                          attribute — used by        in instructions)
                          reflection, IDEs)

add(String)         →    (checked at compile time) →  add(Object)
get(0) → String     →    (return type recorded)    →  get(0) + CHECKCAST String
```

---

### Interview Trap

**"Can you use `instanceof` with a generic type?"** You cannot use it with a parameterized type like `List<String>`. But you CAN use it with an unbounded wildcard: `obj instanceof List<?>`. The wildcard `?` is reifiable because it means "any List" — the type parameter is acknowledged as unknown.

**"What is a reifiable type?"** A type whose complete type information is available at runtime. Parameterized types are not reifiable (their parameter is erased). Unbounded wildcards like `List<?>` are reifiable because `?` explicitly says "unknown" — there is no specific type to remember.

**"Why doesn't Java use reified generics like C#?"** Retrofitting reified generics into a JVM with binary compatibility constraints is extremely difficult. Every existing `.class` file using `List` would need to be incompatible with new `List<T>` code. Projects like Valhalla are exploring this for value types, but full generic reification remains a long-term goal.

---

## J3.2 — Wildcards & PECS

> **Builds on:** [J3.1 — Type Erasure](J3_generics.md#j31--type-erasure)
> **Connects to:** [J3.3 — Bounded Type Parameters](J3_generics.md#j33--bounded-type-parameters)

### WHY: Generics Are Invariant By Default

The most counterintuitive fact about Java generics is their **invariance**: even though `Integer extends Number`, `List<Integer>` does NOT extend `List<Number>`. They are completely unrelated types:

```java
List<Integer> integers = new ArrayList<>();
List<Number>  numbers  = integers;   // COMPILE ERROR — not a List<Number>
```

This is intentional. If it were allowed, you could do:

```java
// Hypothetical (this does NOT compile — thankfully):
List<Number> numbers = integers;  // if this were allowed...
numbers.add(3.14);                // adds a Double to a List<Integer>!
Integer i = integers.get(0);      // ClassCastException at runtime
```

Invariance prevents this. But invariance creates a usability problem: a method taking `List<Number>` cannot accept `List<Integer>`, even though that seems perfectly reasonable. Wildcards solve this tension.

---

### `? extends T` — Upper Bounded Wildcard (Producer)

`List<? extends Number>` means "a List of some specific type that is Number or a subtype of Number." You do not know the exact subtype, but you know anything you read out of it will be a `Number`.

```java
// Works with List<Integer>, List<Double>, List<Long>, List<Number> — all of them
public static double sumAll(List<? extends Number> list) {
    double total = 0.0;
    for (Number n : list) {       // can read as Number — safe, because ? extends Number
        total += n.doubleValue();
    }
    return total;
}

// All valid call sites:
List<Integer> ints    = List.of(1, 2, 3);
List<Double>  doubles = List.of(1.1, 2.2);
List<Number>  mixed   = List.of(1, 2.2);

System.out.println(sumAll(ints));    // 6.0
System.out.println(sumAll(doubles)); // 3.3
System.out.println(sumAll(mixed));   // 3.2
```

**Why can't you write to a `? extends Number` list?**

```java
public static void addOne(List<? extends Number> list) {
    list.add(1);      // COMPILE ERROR
    list.add(1.5);    // COMPILE ERROR
    list.add(null);   // OK — null is the only thing you can add
}
```

Because the compiler does not know if the list is `List<Integer>` or `List<Double>`. Adding an `Integer` to a `List<Double>` would be a type error. So the compiler forbids all additions (except `null`, which is assignment-compatible with any reference type).

---

### `? super T` — Lower Bounded Wildcard (Consumer)

`List<? super Integer>` means "a List of some specific type that is Integer or a supertype of Integer." You do not know the exact supertype, but you know anything you put IN must be an `Integer` (since `Integer` is-a supertype of itself, Number, and Object — all valid).

```java
// Works with List<Integer>, List<Number>, List<Object>
public static void fillWithIntegers(List<? super Integer> list) {
    list.add(1);    // safe — Integer IS-A (? super Integer) ✓
    list.add(2);
    list.add(3);
}

List<Integer> ints    = new ArrayList<>();
List<Number>  numbers = new ArrayList<>();
List<Object>  objects = new ArrayList<>();

fillWithIntegers(ints);     // works
fillWithIntegers(numbers);  // works — Number is a supertype of Integer
fillWithIntegers(objects);  // works — Object is a supertype of Integer
// fillWithIntegers(List<Double>) — COMPILE ERROR, Double is not Integer or supertype
```

**Why can't you read as T from a `? super T` list?**

```java
public static void readProblem(List<? super Integer> list) {
    Integer i = list.get(0);  // COMPILE ERROR
    Object o  = list.get(0);  // OK — Object is the only safe return type
}
```

Because the list might be `List<Object>`, containing any `Object`. Reading and expecting an `Integer` would fail if the actual element is a `String`. The only safe read type is `Object`.

---

### PECS: The Mnemonic

**P**roducer **E**xtends, **C**onsumer **S**uper.

- If a collection **produces** (you read FROM it): use `? extends T`
- If a collection **consumes** (you write TO it): use `? super T`
- If you both read and write: use the exact type `T` with no wildcard

The canonical example from `java.util.Collections.copy`:

```java
// src produces T values (we read from it) → extends
// dst consumes T values (we write to it)  → super
public static <T> void copy(List<? super T> dst, List<? extends T> src) {
    int size = src.size();
    for (int i = 0; i < size; i++) {
        T element = src.get(i);   // read from producer (? extends T) — returns T
        dst.set(i, element);      // write to consumer (? super T) — accepts T
    }
}

// Flexible at call sites:
List<Integer>  ints    = List.of(1, 2, 3);
List<Number>   numbers = new ArrayList<>(Collections.nCopies(3, 0));
Collections.copy(numbers, ints);   // copy List<Integer> into List<Number> — valid!
```

---

### `List<?>` — Unbounded Wildcard

`List<?>` means "a List of some specific but completely unknown type." It is the most permissive wildcard:

```java
public static void printAll(List<?> list) {
    for (Object element : list) {  // can only read as Object
        System.out.println(element);
    }
    // list.add("anything")  // COMPILE ERROR — cannot add (except null)
    // list.add(null);        // OK
}

// Accepts ANY List:
printAll(List.of("a", "b"));
printAll(List.of(1, 2, 3));
printAll(List.of(1.1, 2.2));
printAll(Collections.emptyList());
```

---

### `List<?>` vs `List<Object>`: A Critical Distinction

```java
List<Object>  lObj  = new ArrayList<>();
List<?>       lAny  = new ArrayList<>();

// List<Object> means specifically: a list of Object
lObj.add("hello");    // OK — String is an Object
lObj.add(42);         // OK — Integer is an Object

// List<?> means: a list of SOME unknown specific type
lAny.add("hello");    // COMPILE ERROR — don't know the element type
lAny.add(42);         // COMPILE ERROR

// Subtyping difference:
List<String> strings = new ArrayList<>();
lObj = strings;   // COMPILE ERROR — List<String> is not List<Object>
lAny = strings;   // OK — List<?> accepts List<String>
```

`List<Object>` is a specific parameterization. `List<?>` is an existential type — "there exists some type T such that this is a List<T>."

---

### Wildcard Capture

Sometimes the compiler needs to "capture" the wildcard and give it a name internally:

```java
public static void swapFirst(List<?> list) {
    // list.set(0, list.get(0));  // COMPILE ERROR — ? on left doesn't match ? on right
    swapHelper(list);  // delegate to a method that names the type
}

private static <T> void swapHelper(List<T> list) {
    T first = list.get(0);
    list.set(0, first);   // now T is captured and consistent
}
```

---

### Diagram: What You Can and Cannot Do

```
Collection Type          | Read As    | Write (besides null)
─────────────────────────┼────────────┼──────────────────────
List<T>                  | T          | T (and subtypes)
List<? extends Number>   | Number     | nothing (except null)
List<? super Integer>    | Object     | Integer (and subtypes)
List<?>                  | Object     | nothing (except null)
List<Object>             | Object     | Object (and subtypes)
```

---

### Interview Trap

**"Why can't I add to `List<? extends Number>`?"** Because the compiler doesn't know the exact subtype. The list could be `List<Integer>`, `List<Double>`, or `List<BigDecimal>`. Adding a `Double` to a `List<Integer>` would be a type violation. The compiler conservatively forbids all additions to be safe.

**"What is the difference between `<T extends Number>` and `<? extends Number>`?"** A type parameter `<T extends Number>` gives the type a name (`T`) that you can use throughout the method — for return types, other parameters, local variables. A wildcard `<? extends Number>` is anonymous — you cannot refer to the type by name. Use a type parameter when you need to use the type multiple times; use a wildcard when you only care about the bound.

---

## J3.3 — Bounded Type Parameters

> **Builds on:** [J3.2 — Wildcards & PECS](J3_generics.md#j32--wildcards--pecs)
> **Connects to:** [J3.4 — Generic Methods & Type Inference](J3_generics.md#j34--generic-methods--type-inference)

### WHY: Requiring Capabilities From Type Parameters

Sometimes a generic method needs to do more than just hold a value — it needs to call methods on it. Without a bound, the only methods available on `T` are those inherited from `Object` (`equals`, `hashCode`, `toString`). Bounds give `T` a concrete interface or class to work with.

```java
// Without bound — can only call Object methods on T
public static <T> T max(T a, T b) {
    // a.compareTo(b)  — COMPILE ERROR: T has no compareTo method
    return a;  // useless
}

// With upper bound — T must implement Comparable<T>
public static <T extends Comparable<T>> T max(T a, T b) {
    return a.compareTo(b) >= 0 ? a : b;   // now valid!
}

// Usage — T is inferred:
System.out.println(max(3, 7));           // 7 — T inferred as Integer
System.out.println(max("apple", "fig")); // "fig" — T inferred as String
```

---

### Erasure to the Upper Bound

The bound also determines what the erased bytecode looks like:

```java
// Source:
public static <T extends Comparable<T>> T max(T a, T b) {
    return a.compareTo(b) >= 0 ? a : b;
}

// After erasure — T erases to first bound (Comparable):
public static Comparable max(Comparable a, Comparable b) {
    return a.compareTo(b) >= 0 ? a : b;
}
// Call sites get a CHECKCAST to the expected return type:
// String s = (String) max("a", "b");
```

```
// javap -c output for max:
public static java.lang.Comparable max(java.lang.Comparable, java.lang.Comparable);
  Code:
     0: aload_0                         // load a
     1: aload_1                         // load b
     2: invokeinterface #2, 2           // Comparable.compareTo(Object)
     7: iflt          12
    10: aload_0                         // return a
    11: areturn
    12: aload_1                         // return b
    13: areturn
```

---

### Multiple Bounds

A type parameter can have multiple bounds with `&`. All bounds after the first must be interfaces (the first can be a class or interface):

```java
// T must be Serializable AND Comparable<T>
public static <T extends Serializable & Comparable<T>> T clampedMax(
        T a, T b, T ceiling) {
    T max = a.compareTo(b) >= 0 ? a : b;
    return max.compareTo(ceiling) > 0 ? ceiling : max;
}

// Multiple interface bounds:
public static <T extends Runnable & AutoCloseable> void runAndClose(T resource)
        throws Exception {
    try (resource) {
        resource.run();
    }
}

// Class bound MUST come first:
// <T extends AbstractBase & InterfaceA & InterfaceB>   ← valid
// <T extends InterfaceA & AbstractBase & InterfaceB>   ← COMPILE ERROR (class not first)
```

When multiple bounds are present, `T` erases to the **first bound** in bytecode:

```
<T extends Serializable & Comparable<T>>  →  T erases to Serializable
<T extends AbstractBase & InterfaceA>     →  T erases to AbstractBase
```

---

### Recursive / Self-Referential Bounds

The pattern `<T extends Comparable<T>>` is a recursive bound: T is compared to itself. This is the mechanism that makes `Comparable` work for all its implementations:

```java
// Comparable is declared as:
public interface Comparable<T> {
    int compareTo(T other);
}

// When String implements Comparable<String>:
// T = String, so compareTo(String other) — compares strings to strings

// The generic max method:
// <T extends Comparable<T>> means: T can be compared to its OWN type
// This prevents: max(String a, Integer b) — T can't be both String and Integer
```

Another classic recursive bound — the `Enum` declaration itself:

```java
// How java.lang.Enum is declared:
public abstract class Enum<E extends Enum<E>> implements Comparable<E> {
    public final int ordinal() { ... }
    public final int compareTo(E other) { return this.ordinal - other.ordinal; }
}

// When you write:  enum Color { RED, GREEN, BLUE }
// The compiler expands it to:  final class Color extends Enum<Color>
// So E = Color, meaning: Color.compareTo(Color other) — type-safe ordinal comparison
```

---

### Builder Pattern With Recursive Bounds

Recursive bounds enable fluent builder APIs where subclasses return their own type (not the parent type):

```java
// Without recursive bound — parent methods return Builder, not SubBuilder
abstract class Builder<T extends Builder<T>> {
    private String name;

    @SuppressWarnings("unchecked")
    public T withName(String name) {
        this.name = name;
        return (T) this;   // cast — T is guaranteed to be the actual subclass
    }

    public abstract Object build();
}

class CarBuilder extends Builder<CarBuilder> {
    private int wheels;

    public CarBuilder withWheels(int wheels) {
        this.wheels = wheels;
        return this;
    }

    @Override
    public Car build() {
        return new Car(/* name */, wheels);
    }
}

// Fluent chain works because each method returns CarBuilder, not Builder:
Car car = new CarBuilder()
    .withName("Ferrari")   // returns CarBuilder — defined in Builder<CarBuilder>
    .withWheels(4)         // returns CarBuilder — defined in CarBuilder
    .build();
```

---

### Bounded Type Parameter vs Wildcard: The Key Distinction

```java
// TYPE PARAMETER — T has a name, can be referenced multiple times
public static <T extends Number> void processPair(T a, T b) {
    // a and b are guaranteed the SAME type T
    // Can use T as return type, in other arguments, etc.
    T result = a;   // legal — T is a known named type
}
processPair(1, 2);       // T = Integer — both must be Integer
// processPair(1, 2.0); // COMPILE ERROR — T cannot be both Integer and Double

// WILDCARD — no name, used when you just need the bound
public static void readAll(List<? extends Number> list) {
    // Cannot say "give me another List<same type as list's element>"
    // Cannot use ? as a type anywhere
}
// list can be List<Integer>, List<Double>, etc.
```

---

### Diagram: Bound Hierarchy

```
                   Object
                     │
               Serializable  Comparable<T>
                  │    └──────────┘
              Number (implements both)
               ├── Integer
               ├── Double
               └── Long

<T extends Number & Comparable<T>>:
  Valid T values: Integer, Double, Long, BigDecimal ...
  (any Number subclass that also implements Comparable<T>)

Erasure: T → Number (first bound)
```

---

### Interview Trap

**"Do I use `extends` or `implements` in a generic bound for an interface?"** Always `extends`, even for interfaces: `<T extends Runnable>`, never `<T implements Runnable>`. The Java syntax uses `extends` for both class and interface bounds in generic type parameters.

**"What is the upper bound for unbounded type parameters?"** `Object`. A plain `<T>` is equivalent to `<T extends Object>`.

**"Can a type parameter have a lower bound like `<T super Integer>`?"** No. Type parameters can only have upper bounds (`extends`). Lower bounds (`super`) are only available for wildcards. You can use `<? super Integer>` but not `<T super Integer>`.

---

## J3.4 — Generic Methods & Type Inference

> **Builds on:** [J3.3 — Bounded Type Parameters](J3_generics.md#j33--bounded-type-parameters)

### WHY: Generic Methods Are Independent of Class Genericity

A class does not need to be generic for its methods to be generic. Any method can declare its own type parameters, enabling per-method genericity without making the entire class carry type information. This is common in utility methods, factory methods, and algorithms.

```java
// Non-generic class with generic methods:
public class Utils {

    // Type parameter declared before return type
    public static <T> T identity(T value) {
        return value;
    }

    public static <T extends Comparable<T>> T min(T a, T b) {
        return a.compareTo(b) <= 0 ? a : b;
    }

    // Multiple type parameters
    public static <K, V> Map.Entry<K, V> entry(K key, V value) {
        return Map.entry(key, value);
    }
}
```

---

### Type Inference: The Compiler Figures Out T

When you call a generic method, you do not always need to specify the type parameter. The compiler infers it from the provided arguments:

```java
// Inference from argument type:
String s  = Utils.identity("hello");   // T inferred as String
Integer i = Utils.identity(42);        // T inferred as Integer

// Inference from both arguments:
Integer smallest = Utils.min(3, 7);    // T inferred as Integer — both args are Integer
// Utils.min(3, 7.0) — compile error: T cannot be inferred (int vs double)

// Inference from two separate params:
Map.Entry<String, Integer> e = Utils.entry("age", 25);
// K=String, V=Integer — inferred from "age" and 25
```

---

### The Diamond Operator (Java 7+)

Before Java 7, you had to repeat type parameters on both sides of an assignment:

```java
// Java 6 — verbose:
Map<String, List<Integer>> map = new HashMap<String, List<Integer>>();

// Java 7+ diamond operator — right side infers from left:
Map<String, List<Integer>> map = new HashMap<>();  // <> infers <String, List<Integer>>
```

The diamond operator is just syntactic sugar for type inference from the assignment target.

---

### Target Typing (Java 8+)

Java 8 extended type inference to consider the **target type** — what the result will be assigned to or passed to. This is especially important for methods that return empty/singleton containers:

```java
// Before Java 8 — explicit type argument needed:
List<String> empty = Collections.<String>emptyList();

// Java 8+ — target type (List<String>) drives inference:
List<String> empty = Collections.emptyList();   // T inferred as String from target

// In method arguments — target type from parameter type:
void processStrings(List<String> list) { ... }
processStrings(Collections.emptyList());   // T=String inferred from parameter type
```

Another example with lambdas (target typing at work):

```java
// Comparator<String> is the target type — lambda parameters inferred as String
Comparator<String> comp = (a, b) -> a.length() - b.length();
//                                   ^ String     ^ String  (inferred from target)
```

---

### Explicit Type Arguments: When Inference Fails

Sometimes the compiler cannot infer the type parameter, or infers a type that is broader than what you need. In those cases, you can specify the type argument explicitly:

```java
// Inference produces Object — too broad:
List empty1 = Collections.emptyList();           // List of Object (pre-Java 8 style)

// Explicit type argument — precise:
List<String> empty2 = Collections.<String>emptyList();

// When inference produces the wrong type:
List<Number> nums = Collections.emptyList();   // works — target typing infers Number
// But if you pass emptyList() as an argument to an overloaded method that
// might match multiple overloads, explicit type arg resolves ambiguity:
someOverloadedMethod(Collections.<String>emptyList());
```

The explicit type argument syntax: `ClassName.<TypeArg>methodName(args)` for static methods, or `instance.<TypeArg>methodName(args)` for instance methods.

---

### Multiple Type Parameters and Cross-Inference

When a generic method has multiple type parameters, the compiler infers all of them simultaneously:

```java
public static <K, V> HashMap<K, V> newMap(K key, V value) {
    HashMap<K, V> map = new HashMap<>();
    map.put(key, value);
    return map;
}

// K=String, V=Integer — both inferred from arguments:
HashMap<String, Integer> m = newMap("count", 42);

// Chained inference:
public static <T> Pair<T, T> pair(T a, T b) { ... }
Pair<String, String> p = pair("hello", "world");  // T=String from both args
// pair("hello", 42)  — T inferred as Object (common supertype) — might surprise you
```

---

### The `Collections.emptyList()` Idiom: Historical Context

This method illustrates how type inference evolved:

```java
// Collections.emptyList() signature:
public static <T> List<T> emptyList() { return EMPTY_LIST; }

// Java 5-7: without target typing, inference from return context didn't work
List<String> l1 = Collections.emptyList();           // needed explicit <String>
someMethod(Collections.emptyList());                  // T inferred as Object

// Java 8+: target typing makes it work:
List<String>  l2 = Collections.emptyList();          // T=String from assignment target
List<Integer> l3 = Collections.emptyList();          // T=Integer from assignment target
processStrings(Collections.emptyList());             // T=String from method param type
```

---

### Java vs Kotlin: Limits of Java Type Inference

Java's type inference is **local**: each expression is inferred one at a time, left to right. Kotlin's type inference is **bidirectional**: it can flow information forward AND backward in an expression.

```java
// Java: inference is one-directional — context flows into expressions
List<String> list = new ArrayList<>();           // OK — target drives <>

// Java cannot infer across chained calls as well as Kotlin:
var list2 = List.of("a", "b");   // OK with var — inference from right side
// But: var list3 = Collections.emptyList();  // inferred as List<Object> — not useful

// Kotlin bidirectional inference:
// val list = emptyList<String>()    // explicit, but
// val list: List<String> = emptyList()  // type flows from declaration to function
// val result = listOf("a").map { it.length }  // String inferred, then Int result
```

When Java inference fails, the options are:
1. Add explicit type argument: `Collections.<String>emptyList()`
2. Use a local variable with `var` on the right side
3. Break the expression into two statements with an intermediate typed variable

---

### Generic Method Return Type Inference: Complete Example

```java
public class TypeInferenceDemo {

    // Generic factory
    public static <T> Optional<T> maybe(T value) {
        return Optional.ofNullable(value);
    }

    // Multiple bounds on return type
    public static <T extends Number & Comparable<T>> T clamp(T value, T min, T max) {
        if (value.compareTo(min) < 0) return min;
        if (value.compareTo(max) > 0) return max;
        return value;
    }

    public static void main(String[] args) {
        Optional<String>  s = maybe("hello");    // T=String
        Optional<Integer> i = maybe(42);          // T=Integer
        Optional<Object>  o = maybe(null);        // T=Object (null gives no info)

        Integer clamped  = clamp(15, 1, 10);      // T=Integer, result: 10
        Double  dClamped = clamp(0.5, 1.0, 5.0); // T=Double, result: 1.0
    }
}
```

---

### Diagram: Type Inference Flow

```
Source code:
  List<String> list = Collections.emptyList();

Inference steps:
  1. Target type: List<String>             (from left side of assignment)
  2. Method signature: <T> List<T> emptyList()
  3. Unify: List<T> = List<String>
  4. Solve: T = String
  5. No type argument needed in source

Call site bytecode (after inference):
  INVOKESTATIC Collections.emptyList:()Ljava/util/List;
  CHECKCAST   List                     (raw — erased)
  ASTORE      1                        (store into 'list')
```

---

### Interview Trap

**"Is Java's type inference as powerful as Kotlin's?"** No. Java's inference is local (expression-level) and primarily left-to-right. Kotlin's inference is bidirectional and flows through the entire expression including lambdas. In Java, `var x = Collections.emptyList()` gives you `List<Object>` — not useful. You need an explicit type argument or assignment to a typed variable.

**"What does the diamond operator do?"** It tells the compiler to infer the type arguments from the context (target type or constructor arguments). It is not the same as a raw type. `new ArrayList<>()` creates a properly typed `ArrayList<T>` where T is inferred. `new ArrayList()` creates a raw `ArrayList` that defeats type checking.

**"Can type inference span multiple statements?"** No. Each statement is inferred independently. `var x = Collections.emptyList(); x.add("hello");` — the `var` gives `x` type `List<Object>`, and then `add("hello")` adds a String to a `List<Object>` (which works, but is not `List<String>`). You cannot call `x.get(0)` and get a `String` — you get `Object`.

---

## Master Summary: Generics in 4 Points

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  PHASE J3 — GENERICS MASTER SUMMARY                                          │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  1. TYPE ERASURE (J3.1)                                                      │
│     • List<String> and List<Integer> are the SAME class at runtime           │
│     • T erases to its upper bound (Object if unbounded)                      │
│     • Compiler inserts CHECKCAST at every generic get-site                   │
│     • Bridge methods maintain override contracts after erasure               │
│     • Heap pollution: ClassCastException from mixed raw+generic usage        │
│     • instanceof with parameterized type is forbidden; List<?> is OK        │
│                                                                              │
│  2. WILDCARDS & PECS (J3.2)                                                  │
│     • Generics are INVARIANT: List<Integer> is NOT List<Number>              │
│     • ? extends T → read as T (producer), cannot write (except null)        │
│     • ? super T   → write T (consumer), read as Object only                 │
│     • PECS: Producer Extends, Consumer Super                                 │
│     • List<?> = unknown element type: read as Object, write nothing          │
│     • List<Object> ≠ List<?>: former is specific, latter is existential      │
│                                                                              │
│  3. BOUNDED TYPE PARAMETERS (J3.3)                                           │
│     • <T extends X> gives T capabilities of X (can call X's methods)        │
│     • T erases to first bound in bytecode                                    │
│     • Multiple bounds: <T extends A & B & C> — first must be class          │
│     • Recursive bound <T extends Comparable<T>>: T comparable to itself      │
│     • Always use extends keyword even for interface bounds                   │
│     • No lower bounds (<T super X> is illegal — only wildcards have super)  │
│                                                                              │
│  4. GENERIC METHODS & INFERENCE (J3.4)                                       │
│     • Generic methods are independent of class genericity                    │
│     • Type parameter declared BEFORE return type: <T> List<T> method(T a)  │
│     • Java 7 diamond <>: infers from target type on left side                │
│     • Java 8 target typing: emptyList() infers from assignment/parameter     │
│     • Explicit type arg when inference fails: List.<String>emptyList()       │
│     • Java inference is local; Kotlin's is bidirectional — key difference   │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

*← [Phase J2 — OOP](J2_oop.md) | [Phase J4 — Functional Java →](J4_functional.md)*
