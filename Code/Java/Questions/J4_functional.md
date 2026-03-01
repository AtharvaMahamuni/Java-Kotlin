# Phase J4 — Functional Java

Java 8 was the most transformative release in the language's history. It did not merely add syntax — it added an entirely different programming model. Before Java 8, Java was purely imperative and object-oriented: you wrote step-by-step instructions that mutated state. After Java 8, you can describe computations as pipelines of transformations over data, letting the runtime decide how to execute them. This phase builds the mental model that makes functional Java feel natural rather than alien. Lambdas, functional interfaces, and streams are not independent features — they are a single cohesive system built on top of the JVM's `invokedynamic` instruction.

---

## J4.1 — Lambda Expressions

> **Connects to:** [J4.2 — Functional Interfaces](J4_functional.md#j42--functional-interfaces) · [J4.3 — Streams: Lazy Pipeline](J4_functional.md#j43--streams-lazy-pipeline)

### WHY Lambdas Exist

Before Java 8, the only way to pass behavior as a value was through anonymous classes. If you wanted to sort a list of strings by length, you had to write this:

```java
Collections.sort(names, new Comparator<String>() {
    @Override
    public int compare(String a, String b) {
        return Integer.compare(a.length(), b.length());
    }
});
```

This is six lines of boilerplate to express one concept: compare by length. The compiler generates a new `.class` file on disk for every anonymous class instantiation. Every time you pass behavior, you pay the cost of a full class definition with all its ceremony.

Lambda expressions solve both problems. They compress the syntax to the point where you are expressing only the meaningful parts, and they do not generate a new `.class` file at compile time. Instead, they use the JVM's `invokedynamic` instruction to defer class generation to runtime.

### Lambda Syntax

A lambda has three parts: parameter list, arrow, and body.

```java
// Expression body (single expression, no braces, no return keyword)
(int a, int b) -> a + b

// Block body (multiple statements, must use return)
(int a, int b) -> {
    int sum = a + b;
    return sum;
}

// Type inference (compiler infers types from context)
(a, b) -> a + b

// Single parameter — parentheses optional
name -> name.toUpperCase()

// No parameters
() -> System.out.println("hello")
```

The compiler infers parameter types from the functional interface the lambda is assigned to. If the functional interface says the method takes two `int` parameters, you don't need to repeat that.

### What a Lambda IS

A lambda is not a special object type. It is an instance of a **functional interface** — any interface that has exactly one abstract method (a Single Abstract Method, or SAM interface). The lambda provides the implementation of that one method.

```java
@FunctionalInterface
interface Transformer {
    String transform(String input);
}

Transformer toUpper = s -> s.toUpperCase();
// toUpper is an instance of Transformer
// toUpper.transform("hello") returns "HELLO"
```

The type of a lambda is always determined by context — by what functional interface you are assigning it to. The lambda `s -> s.toUpperCase()` has no type on its own; it only has a type when assigned to a `Transformer`, or a `Function<String, String>`, or a `UnaryOperator<String>`, or any other interface with a compatible SAM.

### The "Effectively Final" Rule

Lambdas can capture local variables from their enclosing scope, but those variables must be **final or effectively final**. Effectively final means: the variable is never reassigned after initialization, even if you did not write the `final` keyword.

```java
int x = 5;       // effectively final — never reassigned below
int y = 10;
y = 20;           // y is reassigned — no longer effectively final

Runnable r = () -> System.out.println(x + y);  // COMPILE ERROR: y is not effectively final
```

The error on `y` is not arbitrary. It exists because of a deep problem with the JVM memory model:

A lambda can outlive the stack frame that created it. Consider a method that creates a lambda and returns it. The method's stack frame is destroyed when the method returns. If the lambda held a reference to the local variable `y`, and `y` could be changed by the caller after the lambda was captured, then the lambda would be reading from a destroyed stack slot — a dangling reference.

The effectively-final rule eliminates this problem by guaranteeing that the captured value is frozen at capture time. The JVM copies the variable's value into the lambda's synthetic fields. Since the value can never change after capture, the copy is always accurate.

**Instance fields and static fields are exempt** from this rule. They live on the heap, not the stack. They have well-defined lifetimes managed by the garbage collector. A lambda can freely read from and write to instance fields:

```java
class Counter {
    private int count = 0;                    // instance field — on the heap

    public Runnable getIncrementer() {
        return () -> count++;                 // FINE — count is a heap-allocated field
    }
}
```

Here the lambda captures `this` (the Counter instance), which IS a reference on the heap. Mutating `count` through `this` is perfectly legal.

### Lambda Bytecode vs Anonymous Class Bytecode

This is where lambdas are architecturally different from anonymous classes, not just syntactically different.

**Anonymous class:** The compiler generates a separate `.class` file at compile time (e.g., `MyClass$1.class`). Every time execution reaches that code, the JVM allocates a new object of that synthetic class:

```
// Bytecode for: new Runnable() { public void run() { ... } }
NEW pkg/MyClass$1             ; allocate instance of anonymous class
DUP                           ; duplicate reference for constructor call
INVOKESPECIAL pkg/MyClass$1.<init> ()V   ; call constructor
```

**Lambda:** The compiler generates a single synthetic method in the containing class (e.g., `lambda$myMethod$0`). At the call site, it emits an `invokedynamic` instruction:

```
// Bytecode for: () -> System.out.println("hi")
INVOKEDYNAMIC run() Ljava/lang/Runnable;
    BootstrapMethods: LambdaMetafactory.metafactory(...)
```

`invokedynamic` is a special JVM instruction introduced in Java 7 for dynamic dispatch. When the JVM first encounters this instruction, it calls the **bootstrap method** — `LambdaMetafactory.metafactory()`. This method uses `java.lang.invoke` machinery to synthesize a class at runtime that implements the target functional interface by delegating to the synthetic lambda method. This synthesized class is cached; subsequent calls reuse the same class.

The implications are significant:
- **Faster startup for unused lambdas**: a lambda defined in a code path that never executes never causes class synthesis. With anonymous classes, the `.class` file was always loaded.
- **Fewer class files on disk**: your JAR is smaller and more readable.
- **Better JIT optimization**: the JVM can inline the synthetic class aggressively since it controls its generation.

### Method References: 4 Kinds

Method references are syntactic sugar for lambdas that simply call a single existing method. They are cleaner to read but semantically identical.

```java
// 1. Static method reference: ClassName::staticMethod
// Equivalent lambda: (s) -> Integer.parseInt(s)
Function<String, Integer> parser = Integer::parseInt;

// 2. Bound instance method reference: instance::instanceMethod
// Equivalent lambda: (s) -> System.out.println(s)
Consumer<String> printer = System.out::println;
// "Bound" because System.out is a specific, fixed instance

// 3. Unbound instance method reference: ClassName::instanceMethod
// Equivalent lambda: (s) -> s.toLowerCase()
Function<String, String> lower = String::toLowerCase;
// "Unbound" because the instance is the first argument at call time:
// lower.apply("HELLO") calls "HELLO".toLowerCase()

// 4. Constructor reference: ClassName::new
// Equivalent lambda: () -> new ArrayList<>()
Supplier<ArrayList<String>> factory = ArrayList::new;
// Or with an argument: (n) -> new ArrayList<>(n)
Function<Integer, ArrayList<String>> sizedFactory = ArrayList::new;
```

The unbound instance method reference (`String::toLowerCase`) is the subtlest. The lambda it represents takes the receiver as its first argument. This is why `Function<String, String>` works — the single argument becomes the string that `toLowerCase()` is called on.

### Interview Trap: Lambdas Are Not True Closures

In languages like JavaScript or Python, closures can capture and mutate variables from outer scopes. Java lambdas cannot mutate captured local variables. You sometimes see code that tries to work around this with a one-element array:

```java
// "Trick" to mutate a captured value — fragile and misleading
int[] counter = {0};
Runnable r = () -> counter[0]++;   // compiles — the array reference is effectively final
r.run();
System.out.println(counter[0]);    // 1
```

This works only because the array reference itself is effectively final (never reassigned), even though the contents change. But if this lambda runs in parallel, you have a data race on `counter[0]`. The effectively-final rule exists precisely to discourage this pattern. The idiomatic solution for accumulation is `Stream.reduce()` or an atomic variable, not array tricks.

---

## J4.2 — Functional Interfaces

> **Builds on:** [J4.1 — Lambda Expressions](J4_functional.md#j41--lambda-expressions)
> **Connects to:** [J4.3 — Streams: Lazy Pipeline](J4_functional.md#j43--streams-lazy-pipeline)

### WHY a Standard Vocabulary

Before Java 8, every library invented its own one-method interfaces: `Runnable`, `Callable`, `Comparator`, `ActionListener`, `Predicate` (Guava), and so on. These interfaces were incompatible even when they had identical shapes. A method expecting a `Runnable` could not accept a `Callable<Void>` even though both take no arguments and return nothing (ignoring the checked exception).

The `java.util.function` package establishes a standard vocabulary of 43 functional interfaces covering the most common function shapes. Once you internalize this vocabulary, you can read any functional Java code because all standard libraries speak the same language.

### The Core Seven Interfaces

These seven interfaces cover the essential shapes. Learn their signatures, their abstract method names, and what they represent:

```
Interface               Shape              Abstract Method
──────────────────────────────────────────────────────────────
Function<T, R>          T → R              R apply(T t)
Predicate<T>            T → boolean        boolean test(T t)
Consumer<T>             T → void           void accept(T t)
Supplier<T>             () → T             T get()
BiFunction<T, U, R>     T, U → R           R apply(T t, U u)
UnaryOperator<T>        T → T              T apply(T t)       [extends Function<T,T>]
BinaryOperator<T>       T, T → T           T apply(T t, T u)  [extends BiFunction<T,T,T>]
```

In practice:
- Use `Function` when you transform one value into another type.
- Use `Predicate` for filters and conditions — anywhere you test a value.
- Use `Consumer` for side effects — printing, saving, logging.
- Use `Supplier` for lazy production of a value — defer construction until needed.
- Use `BiFunction` / `BiConsumer` / `BiPredicate` when you need two inputs.
- Use `UnaryOperator` / `BinaryOperator` when input and output types are the same — cleaner than `Function<T,T>`.

```java
// Function<T, R>: convert String to its length
Function<String, Integer> length = String::length;
int n = length.apply("hello");   // 5

// Predicate<T>: test if a string is blank
Predicate<String> isBlank = String::isBlank;
boolean result = isBlank.test("  ");  // true

// Consumer<T>: print each element
Consumer<String> print = System.out::println;
print.accept("hello");   // prints "hello"

// Supplier<T>: lazily create an expensive object
Supplier<List<String>> listMaker = ArrayList::new;
List<String> list = listMaker.get();   // creates new ArrayList

// BiFunction<T,U,R>: combine first name and last name
BiFunction<String, String, String> fullName = (first, last) -> first + " " + last;
String name = fullName.apply("John", "Doe");   // "John Doe"

// UnaryOperator<T>: double a number
UnaryOperator<Integer> doubler = n2 -> n2 * 2;
int doubled = doubler.apply(5);   // 10

// BinaryOperator<T>: sum two integers
BinaryOperator<Integer> sum = Integer::sum;
int total = sum.apply(3, 4);   // 7
```

### Primitive Specializations: Avoid Boxing

The generic interfaces like `Function<Integer, Integer>` require boxing — converting the primitive `int` to an `Integer` object on every call. For performance-sensitive code processing millions of values, this is unacceptable. Java provides specialized interfaces for `int`, `long`, and `double`:

```
Primitive Specializations (partial list — int family shown):
──────────────────────────────────────────────────────────────
IntFunction<R>          int → R            R apply(int value)
ToIntFunction<T>        T → int            int applyAsInt(T value)
IntUnaryOperator        int → int          int applyAsInt(int op)
IntBinaryOperator       int, int → int     int applyAsInt(int l, int r)
IntSupplier             () → int           int getAsInt()
IntPredicate            int → boolean      boolean test(int value)
IntConsumer             int → void         void accept(int value)
```

Long and double families mirror the int family (`LongFunction`, `ToLongFunction`, `LongUnaryOperator`, etc.). There are also cross-type functions like `IntToLongFunction` (int → long) and `LongToIntFunction` (long → int).

```java
// Without primitive specialization: boxes every int to Integer
Function<Integer, Integer> boxed = n -> n * n;

// With primitive specialization: no boxing, faster
IntUnaryOperator noBoxing = n -> n * n;

// In a stream context, this is why IntStream is faster than Stream<Integer>
int sum = IntStream.rangeClosed(1, 1_000_000)
    .map(n -> n * n)           // IntUnaryOperator — no boxing
    .sum();                    // returns primitive int
```

### Composition Methods

Functional interfaces are not just containers for lambdas — they provide `default` methods for composing functions. This is how you build pipelines without streams.

```java
// Function composition
Function<String, Integer> length = String::length;
Function<Integer, String> toStr = n -> "len=" + n;

// andThen: apply this, then apply after
Function<String, String> lengthThenStr = length.andThen(toStr);
String r1 = lengthThenStr.apply("hello");   // "len=5"

// compose: apply before first, then apply this
Function<String, String> strThenLength = toStr.compose(length);
String r2 = strThenLength.apply("hello");   // same result — "len=5"
// Note: compose and andThen just differ in which you think of as "primary"
```

```java
// Predicate composition
Predicate<Integer> isEven = n -> n % 2 == 0;
Predicate<Integer> isPositive = n -> n > 0;

Predicate<Integer> isEvenAndPositive = isEven.and(isPositive);
Predicate<Integer> isEvenOrPositive  = isEven.or(isPositive);
Predicate<Integer> isOdd             = isEven.negate();

System.out.println(isEvenAndPositive.test(4));    // true
System.out.println(isEvenAndPositive.test(-4));   // false
System.out.println(isEvenOrPositive.test(-4));    // true (even)
System.out.println(isOdd.test(3));                // true
```

```java
// Consumer composition with andThen
Consumer<String> log = s -> System.out.println("LOG: " + s);
Consumer<String> save = s -> database.save(s);

Consumer<String> logThenSave = log.andThen(save);
logThenSave.accept("event");   // first logs, then saves
```

The composition methods follow the same design: `andThen` executes the receiver first, then the argument; `compose` (on Function only) reverses that order. For Predicate, `and`/`or`/`negate` mirror boolean algebra.

### @FunctionalInterface Annotation

The `@FunctionalInterface` annotation serves two purposes: documentation and compile-time enforcement.

```java
@FunctionalInterface
interface Transformer {
    String transform(String input);    // the one SAM

    // These are fine — they do NOT count as abstract:
    default Transformer andThen(Transformer after) {
        return s -> after.transform(this.transform(s));
    }

    static Transformer identity() {
        return s -> s;
    }
}

// This would be a COMPILE ERROR — two abstract methods:
@FunctionalInterface
interface Broken {
    void doA();
    void doB();   // ERROR: multiple non-overriding abstract methods found
}
```

Without `@FunctionalInterface`, a lambda can still target any single-abstract-method interface — the annotation is not required for a lambda to work. But the annotation triggers a compile error if someone accidentally adds a second abstract method to the interface later, which would break all existing lambdas.

### Interview Trap: Comparator Is a Functional Interface

`Comparator<T>` is annotated with `@FunctionalInterface` and it works with lambdas. But if you look at the interface, it appears to have two abstract methods: `compare()` and `equals()`. How?

The rule is: methods that override a `public` method from `Object` do not count toward the abstract method count. Every Java class inherits from `Object`, and `Object` declares `equals(Object)` as a public method. Since any concrete implementation of `Comparator` will necessarily inherit `equals()` from `Object` (or override it), `equals()` is not truly "unimplemented" — it does not count as an abstract SAM method.

Therefore, `compare(T o1, T o2)` is the only real abstract method, and `Comparator<T>` is a valid functional interface. A lambda `(a, b) -> a.length() - b.length()` implements `compare()`.

---

## J4.3 — Streams: Lazy Pipeline

> **Builds on:** [J4.1 — Lambda Expressions](J4_functional.md#j41--lambda-expressions) · [J4.2 — Functional Interfaces](J4_functional.md#j42--functional-interfaces)
> **Connects to:** [J4.4 — Stream Internals & Parallel Streams](J4_functional.md#j44--stream-internals--parallel-streams)

### WHY Streams Exist

Consider filtering a list of users to find active admins, extracting their email addresses, sorting them, and collecting them. In imperative style:

```java
List<String> result = new ArrayList<>();
for (User u : users) {
    if (u.isActive() && u.isAdmin()) {
        result.add(u.getEmail());
    }
}
Collections.sort(result);
```

This is three separate passes of concern mixed together: filtering, extraction, sorting. You cannot reuse the "filter active admins" logic without re-writing it. You cannot swap in a parallel execution strategy. You always process the entire collection, even if you only need the first result.

Streams solve all of these problems by representing computation as a **lazy pipeline**. You describe the transformation, not the iteration. The runtime decides when and how to execute it.

### The Three Parts of a Stream Pipeline

Every stream pipeline has exactly three parts:

**1. Source** — creates the stream:
```java
Stream.of("a", "b", "c")            // from varargs
Arrays.stream(array)                 // from array
list.stream()                        // from Collection
Stream.iterate(0, n -> n + 1)       // infinite sequence
Stream.generate(Math::random)        // infinite random values
IntStream.range(0, 10)              // primitive int range [0, 10)
IntStream.rangeClosed(1, 10)        // primitive int range [1, 10]
Files.lines(path)                    // lines of a file (lazy I/O)
```

**2. Intermediate operations** — lazy transformations, each returns a new `Stream`:
```java
.filter(predicate)       // keep elements matching predicate
.map(function)           // transform each element
.flatMap(function)       // transform each element to a stream, then flatten
.distinct()              // remove duplicates (uses equals/hashCode)
.sorted()                // natural order
.sorted(comparator)      // custom order
.limit(n)                // take at most n elements
.skip(n)                 // skip first n elements
.peek(consumer)          // observe elements without changing them (debugging)
.mapToInt(function)      // convert to IntStream (primitive, no boxing)
```

**3. Terminal operations** — eager, trigger execution, consume the stream:
```java
.collect(collector)      // gather into a collection or string
.forEach(consumer)       // side effect on each element
.reduce(identity, op)    // fold all elements into one value
.count()                 // count elements
.findFirst()             // first element (Optional)
.findAny()               // any element, faster in parallel
.anyMatch(predicate)     // true if any element matches
.allMatch(predicate)     // true if all elements match
.noneMatch(predicate)    // true if no elements match
.min(comparator)         // minimum element (Optional)
.max(comparator)         // maximum element (Optional)
.toList()                // Java 16+: direct unmodifiable list
```

### Laziness: Nothing Executes Until Terminal

This is the most important property to internalize. Every intermediate operation is lazy — calling `.filter()` or `.map()` does not process a single element. It only builds a description of what to do. The actual computation begins only when a terminal operation is called.

```java
Stream<String> stream = List.of("alice", "bob", "charlie", "david")
    .stream()
    .filter(s -> {
        System.out.println("filter: " + s);
        return s.startsWith("a") || s.startsWith("d");
    })
    .map(s -> {
        System.out.println("map: " + s);
        return s.toUpperCase();
    });

// NOTHING has printed yet — no elements processed
System.out.println("About to call terminal...");
List<String> result = stream.collect(Collectors.toList());
// Now both filter and map run for each element
```

Output:
```
About to call terminal...
filter: alice
map: alice
filter: bob
filter: charlie
filter: david
map: david
```

Notice the execution is **vertical** (per-element), not **horizontal** (all-of-filter then all-of-map). "alice" goes through the entire pipeline before "bob" is even seen by the filter. This is called **pipeline fusion** and is a key performance optimization.

### Short-Circuiting: Stop Early

Short-circuit operations allow the pipeline to stop before consuming the entire source. This makes streams correct and efficient for infinite sources:

```java
// Without short-circuit — would process 1 million elements
// With findFirst() — stops at element 2 (the first even number)
Optional<Integer> first = IntStream.rangeClosed(1, 1_000_000)
    .filter(n -> n % 2 == 0)    // lazy
    .map(n -> n * n)             // lazy
    .findFirst();                // terminal + short-circuit

// findFirst() triggers execution:
// - n=1: filter(1%2==0) → false, skip
// - n=2: filter(2%2==0) → true, map(2*2) → 4, findFirst() → return Optional.of(4)
// Total elements processed: 2 out of 1,000,000
```

Short-circuit terminal operations: `findFirst()`, `findAny()`, `anyMatch()`, `allMatch()`, `noneMatch()`
Short-circuit intermediate operations: `limit(n)`, `takeWhile(predicate)` (Java 9+)

### Infinite Streams

Because streams are lazy and support short-circuit terminals, you can define infinite sequences:

```java
// Infinite sequence of Fibonacci numbers
Stream<long[]> fibs = Stream.iterate(
    new long[]{0, 1},
    f -> new long[]{f[1], f[0] + f[1]}
);

// Take the first 10 Fibonacci numbers
fibs.limit(10)
    .map(f -> f[0])
    .forEach(System.out::println);
// 0, 1, 1, 2, 3, 5, 8, 13, 21, 34

// Infinite stream of random doubles — take first 5 above 0.9
OptionalDouble result = Stream.generate(Math::random)
    .mapToDouble(Double::doubleValue)
    .filter(d -> d > 0.9)
    .findFirst();
```

Without `limit()` or a short-circuit terminal, an infinite stream will run forever. The `Stream.generate()` and `Stream.iterate()` sources never exhaust themselves — the pipeline must control termination.

### collect() and Collectors

The `collect()` terminal operation is the most powerful. It takes a `Collector` that describes how to accumulate elements. The `Collectors` utility class provides all the common patterns:

```java
List<String> names = employees.stream()
    .map(Employee::getName)
    .collect(Collectors.toList());           // mutable List (implementation unspecified)

List<String> names2 = employees.stream()
    .map(Employee::getName)
    .toList();                               // Java 16+: unmodifiable List, more efficient

Set<String> nameSet = employees.stream()
    .map(Employee::getName)
    .collect(Collectors.toSet());            // HashSet (order not guaranteed)

// Join strings with separator, prefix, suffix
String csv = employees.stream()
    .map(Employee::getName)
    .collect(Collectors.joining(", ", "[", "]"));
// "[Alice, Bob, Charlie]"

// Group by a classifier function — produces Map<K, List<V>>
Map<Department, List<Employee>> byDept = employees.stream()
    .collect(Collectors.groupingBy(Employee::getDepartment));

// Group and then count — Map<Department, Long>
Map<Department, Long> countByDept = employees.stream()
    .collect(Collectors.groupingBy(
        Employee::getDepartment,
        Collectors.counting()
    ));

// Partition by predicate — Map<Boolean, List<T>>
Map<Boolean, List<Employee>> seniorVsJunior = employees.stream()
    .collect(Collectors.partitioningBy(e -> e.getYears() >= 5));

// Summarizing statistics
IntSummaryStatistics stats = employees.stream()
    .collect(Collectors.summarizingInt(Employee::getSalary));
// stats.getMin(), getMax(), getAverage(), getSum(), getCount()

// toMap — be careful: duplicate keys throw IllegalStateException by default
Map<String, Employee> byName = employees.stream()
    .collect(Collectors.toMap(
        Employee::getName,        // key function
        e -> e,                   // value function
        (e1, e2) -> e1            // merge function — keep first on duplicate key
    ));
```

### Stream Cannot Be Reused

Once a terminal operation has been called on a stream, the stream is exhausted. Calling any method on it afterward throws `IllegalStateException`:

```java
Stream<String> stream = List.of("a", "b").stream();
long count = stream.count();          // terminal: consumes stream
stream.forEach(System.out::println);  // THROWS: IllegalStateException: stream has already been operated upon
```

If you need to process the same data multiple times, create a new stream from the source each time, or store the data in a collection first.

### Interview Trap: Forgetting the Terminal Operation

This is perhaps the most common stream bug. You chain filter and map and the code compiles and runs without errors — but it does nothing:

```java
// BUG: no terminal operation
employees.stream()
    .filter(e -> e.getSalary() < 50_000)
    .map(Employee::getName);
// This line executes in 0 nanoseconds and produces no visible effect.
// The stream is created, filter and map are registered as lazy stages,
// then the stream is discarded. No elements ever flow through.

// CORRECT:
List<String> lowPaidNames = employees.stream()
    .filter(e -> e.getSalary() < 50_000)
    .map(Employee::getName)
    .collect(Collectors.toList());
```

IDE inspections like IntelliJ's "Stream result is not used" warning catch this, but it slips through in code review surprisingly often.

---

## J4.4 — Stream Internals & Parallel Streams

> **Builds on:** [J4.3 — Streams: Lazy Pipeline](J4_functional.md#j43--streams-lazy-pipeline)
> **Connects to:** [J5.4 — Concurrent Collections](J5_collections.md#j54--concurrent-collections)

### WHY Understanding Internals Matters

Parallel streams look like a free lunch: add `.parallel()` and your code runs on multiple cores. In practice, parallel streams regularly perform worse than sequential streams when applied naively. Understanding the Spliterator, pipeline fusion, and Fork/Join mechanics lets you predict performance rather than guessing.

### Spliterator: The Engine Behind Streams

Every collection provides a `Spliterator<T>` (splittable iterator) that serves as the source for streams. A Spliterator has two key methods:

```java
// Process one element: return false when exhausted
boolean tryAdvance(Consumer<? super T> action);

// Try to split into two roughly equal halves (for parallelism)
// Returns null if cannot/should not split further
Spliterator<T> trySplit();
```

Spliterators also report **characteristics** that tell the stream machinery what optimizations are safe:

```
SIZED      — knows exact number of elements in advance
ORDERED    — elements have a defined encounter order
DISTINCT   — no duplicate elements
SORTED     — elements are in sorted order
NONNULL    — no null elements
IMMUTABLE  — source cannot be modified during traversal
SUBSIZED   — trySplit() produces SIZED spliterators
```

For example, `ArrayList`'s spliterator is SIZED + ORDERED, so `count()` can return the size without traversal. `HashSet`'s spliterator is SIZED + DISTINCT but not ORDERED, so `findFirst()` can be implemented as `findAny()`.

### Pipeline Fusion: One Pass Over the Data

The most important performance property of sequential streams is that all intermediate operations execute in a single pass over the source. `filter` + `map` + `filter` is NOT three separate traversals:

```java
long result = list.stream()
    .filter(s -> s.length() > 3)    // stage 1
    .map(String::toUpperCase)        // stage 2
    .filter(s -> s.startsWith("A")) // stage 3
    .count();                        // terminal
```

Internally, `ReferencePipeline` builds a linked chain of stage objects: `Head → StatelessOp(filter) → StatelessOp(map) → StatelessOp(filter) → TerminalOp(count)`. When the terminal fires, it pulls one element from the source, pushes it through all three stages, then pulls the next element. The data never sits in an intermediate collection between stages.

This is why streams are often faster than the equivalent code using multiple `stream()` chains or intermediate collections.

### Parallel Streams: Fork/Join Under the Hood

When you call `.parallel()`, the stream framework switches from single-threaded pull-based traversal to a Fork/Join divide-and-conquer strategy:

1. The Spliterator's `trySplit()` is called recursively to divide the source into sub-ranges.
2. Each sub-range is submitted as a task to the **ForkJoinPool.commonPool()** (shared across the JVM).
3. Each worker thread runs the pipeline on its sub-range independently.
4. Results are combined (using the terminal operation's combiner) as tasks complete.

```java
// Count primes up to 100 million — CPU-bound, large data, no ordering needed
long primeCount = LongStream.rangeClosed(2, 100_000_000L)
    .parallel()
    .filter(n -> isPrime(n))
    .count();
// Uses all available CPU cores via ForkJoinPool.commonPool()
```

### When Parallel Streams Are Faster

Parallel streams are faster when ALL of the following are true:
- **Large data**: at minimum ~10,000 elements. Thread overhead dominates for small collections.
- **CPU-bound work**: heavy computation per element (prime checking, encryption, parsing).
- **Splittable source**: arrays, `ArrayList`, `IntStream.range()` split perfectly. `LinkedList` splits poorly (no random access). `Stream.iterate()` cannot split at all.
- **No ordering dependency**: `findAny()` is faster in parallel than `findFirst()` (which requires imposing order after parallel execution).
- **Stateless operations**: `filter` and `map` are stateless (each element processed independently). `sorted()`, `distinct()`, and `limit()` are stateful — they require coordination across all threads and often negate parallel gains.

### When Parallel Streams Are Slower

```java
// Example 1: Small collection — thread overhead > computation
List<Integer> tiny = List.of(1, 2, 3, 4, 5);
int sum = tiny.parallelStream().mapToInt(Integer::intValue).sum();
// Sequential would be faster — fork/join overhead for 5 elements is wasteful

// Example 2: Non-splittable source
Stream.iterate(0, n -> n + 1)   // cannot split — each element depends on previous
    .parallel()
    .limit(1000)
    .sum();                      // parallel provides no speedup here

// Example 3: Stateful operation requiring synchronization
long distinct = LongStream.rangeClosed(1, 1_000_000L)
    .parallel()
    .distinct()   // requires global state — threads must coordinate
    .count();     // parallel may be slower than sequential
```

### The Shared Mutable State Bug

This is the most dangerous parallel stream mistake. `forEach` with a non-thread-safe collection is a data race:

```java
// DATA RACE — ArrayList is not thread-safe
List<Integer> results = new ArrayList<>();
IntStream.range(0, 10_000)
    .parallel()
    .forEach(results::add);   // multiple threads call add() concurrently
// results.size() may be < 10,000 — lost updates
// May throw ConcurrentModificationException
// May even corrupt ArrayList's internal array

// CORRECT: use collect(), which uses thread-local accumulators
List<Integer> safe = IntStream.range(0, 10_000)
    .parallel()
    .boxed()
    .collect(Collectors.toList());   // thread-safe: each thread has private partial result
```

The `collect()` operation works correctly in parallel because `Collectors` implementations use a **supplier** (create private partial result) + **accumulator** (add to partial result) + **combiner** (merge two partial results) pattern. Each thread works on its own partial result, eliminating shared state.

### reduce() and Associativity

The `reduce()` operation must produce the same result whether executed sequentially or in any parallel order. This requires the operation to be **associative**: `(a op b) op c == a op (b op c)`.

```java
// Correct: addition is associative
int sum = IntStream.range(1, 100)
    .parallel()
    .reduce(0, Integer::sum);   // 0+1+2+...+99 = 4950, regardless of order

// INCORRECT: subtraction is NOT associative
// Sequential: ((10 - 1) - 2) - 3 = 4
// Parallel might compute: (10 - 1) - (2 - 3) = 10 — WRONG
int bad = IntStream.of(10, 1, 2, 3)
    .parallel()
    .reduce(0, (a, b) -> a - b);   // result is unpredictable
```

### Custom Thread Pool for Parallel Streams

By default, parallel streams use `ForkJoinPool.commonPool()`. This pool is shared across the entire JVM — if a web server uses parallel streams for a database query, it may block other parallel operations. The workaround is to submit the stream task to a custom pool:

```java
ForkJoinPool customPool = new ForkJoinPool(4);  // 4 threads

try {
    int result = customPool.submit(() ->
        IntStream.rangeClosed(1, 1_000_000)
            .parallel()
            .filter(n -> isPrime(n))
            .sum()
    ).get();   // blocks until complete
} finally {
    customPool.shutdown();
}
```

This is a workaround, not an official API — it relies on the implementation detail that the parallel stream uses the pool of the thread that calls `.forEach()` or the equivalent. It works in practice in all current JVM implementations.

### Interview Trap: Parallel Is Not Always Parallel

```java
// This "parallel" stream will run sequentially:
Stream.iterate(0, n -> n + 1)
    .parallel()
    .limit(10)
    .forEach(System.out::println);
```

`Stream.iterate()` generates elements sequentially — each element depends on the previous one via the function `n -> n + 1`. The resulting Spliterator cannot split. Even though `.parallel()` is set, there is nothing to parallelize. The JVM will fall back to sequential execution. You will see the elements printed in order (0 through 9).

---

## Master Summary

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         PHASE J4 — FUNCTIONAL JAVA                              │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  1. LAMBDAS are instances of functional interfaces, not anonymous classes.      │
│     They use invokedynamic + LambdaMetafactory to synthesize classes at         │
│     runtime, not compile time. Captured local vars must be effectively final    │
│     because lambdas outlive the stack frame — fields are fine (they're on       │
│     the heap). A lambda IS NOT a true closure — it cannot mutate locals.        │
│                                                                                 │
│  2. FUNCTIONAL INTERFACES provide a standard vocabulary (Function, Predicate,   │
│     Consumer, Supplier, BiFunction, UnaryOperator, BinaryOperator). Use         │
│     primitive specializations (IntFunction, IntPredicate, etc.) in              │
│     performance-sensitive code to avoid boxing overhead. Compose with           │
│     andThen/compose/and/or/negate. Comparator is a valid SAM despite           │
│     having equals() — Object methods don't count toward the abstract SAM.       │
│                                                                                 │
│  3. STREAMS are lazy pipelines. Intermediate ops (filter, map, flatMap)         │
│     register computation but do nothing. Only a terminal op (collect,           │
│     forEach, reduce, count) triggers execution. The pipeline executes           │
│     element-by-element (vertical fusion), not stage-by-stage. Forgetting        │
│     the terminal is a silent bug — the code compiles and runs but does nothing. │
│                                                                                 │
│  4. PARALLEL STREAMS use Fork/Join + Spliterator.trySplit(). They are           │
│     faster only for: large data (>10k elements), CPU-bound work, splittable     │
│     sources (arrays, ranges), and stateless operations. Never use shared        │
│     mutable state (ArrayList) in parallel forEach — use collect() instead.      │
│     reduce() must be associative for correct parallel results.                  │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

*← [Phase J3 — Generics](J3_generics.md) | [Phase J5 — Collections →](J5_collections.md)*
