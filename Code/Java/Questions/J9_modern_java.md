# Phase J9 — Modern Java (Java 9–21)

Java 8 was a revolution. Java 9 through 21 have been a steady evolution — but an evolution that every senior developer must understand, because these features now appear in production codebases and every modern Java interview. This phase covers the key language and platform features introduced since Java 8: local variable type inference, the module system, switch expressions and pattern matching, Virtual Threads (Project Loom), and Structured Concurrency. The culminating feature — Virtual Threads — is arguably the most significant Java change since generics: it lets you write blocking, sequential code that performs like async code, without coroutine syntax, callbacks, or reactive frameworks.

---

## J9.1 — Local Variable Type Inference (`var`) & Java 9 Module System

> **Connects to:** [J9.2 — Switch Expressions & Pattern Matching](J9_modern_java.md#j92--switch-expressions--pattern-matching-java-14-21)

### WHY `var` Exists

Java has always been statically typed — every variable has a type known at compile time. Before Java 10, you had to write that type explicitly even when it was obvious from context:

```java
// Pre-Java 10: redundant type repetition
ArrayList<Map<String, List<Integer>>> data = new ArrayList<Map<String, List<Integer>>>();
Map.Entry<String, Integer> entry = map.entrySet().iterator().next();
```

This is mechanical repetition: the compiler already knows the type from the right-hand side. `var` eliminates that redundancy while preserving static typing.

### `var` Is Compile-Time Static Inference, Not Dynamic Typing

This is the most important point: `var` is **not** like JavaScript's `var` or Python's dynamic typing. The type is inferred at compile time and is fixed. The compiled bytecode is identical to writing the explicit type.

```java
var list = new ArrayList<String>();   // compiler infers: ArrayList<String>
var entry = map.entrySet().iterator().next();  // compiler infers: Map.Entry<K,V>

// This is a compile error — type is ArrayList<String>, not List<String>
// (even though it would be with an explicit declaration)
var x = new ArrayList<String>();
x = new LinkedList<String>();         // COMPILE ERROR: LinkedList ≠ ArrayList<String>

// Bytecode is identical to explicit type:
ArrayList<String> list = new ArrayList<String>();
```

Verify by running `javap -v` on compiled code — `var` leaves no trace.

### What `var` Can and Cannot Be Used On

```java
// ALLOWED: local variable with initializer
var count = 0;
var name = "Alice";
var map = new HashMap<String, Integer>();

// ALLOWED: for-each loop variable
for (var entry : map.entrySet()) { ... }

// ALLOWED: try-with-resources variable
try (var conn = DriverManager.getConnection(url)) { ... }

// NOT ALLOWED: class fields
class MyClass {
    var field = 5;        // COMPILE ERROR — fields must have explicit type
}

// NOT ALLOWED: method parameters
void process(var data) { ... }   // COMPILE ERROR

// NOT ALLOWED: method return types
var getList() { ... }            // COMPILE ERROR

// NOT ALLOWED: without initializer
var x;                           // COMPILE ERROR — cannot infer without right-hand side

// NOT ALLOWED: null initializer (type cannot be inferred)
var x = null;                    // COMPILE ERROR
```

### The Diamond Problem with `var`

```java
// GOTCHA: var + diamond operator infers the raw/most-general type
var list1 = new ArrayList<>();         // infers ArrayList<Object>, NOT ArrayList<String>!
var list2 = new ArrayList<String>();   // correct — type argument provided

// Practical impact:
list1.add("hello");   // fine (Object)
list1.add(42);        // also fine (Object) — you've lost type safety
String s = list1.get(0);   // COMPILE ERROR — returns Object

// Best practice: always provide explicit type argument with var
var map = new HashMap<String, Integer>();   // good
```

### Java 9 Module System (JPMS)

The Java Platform Module System introduced a new unit of encapsulation above the package: the **module**. A module is a collection of packages with explicit declarations of what it exports (makes accessible to other modules) and what it requires (depends on).

```java
// module-info.java (must be at the root of the module's source tree)
module com.example.myapp {
    requires java.base;            // implicit — all modules require java.base
    requires java.sql;             // depend on the JDBC module
    requires com.example.utils;   // depend on another module

    exports com.example.myapp.api;         // expose this package to all modules
    exports com.example.myapp.internal     // expose only to specific module
        to com.example.trusted;

    opens com.example.myapp.model;        // allow deep reflection (for frameworks)
    opens com.example.myapp.config        // allow reflection only from specific module
        to spring.core;

    uses com.example.spi.Plugin;          // declares it's a consumer of this service
    provides com.example.spi.Plugin       // declares it provides an implementation
        with com.example.myapp.PluginImpl;
}
```

**The three access levels with modules:**

```
Without modules (classpath):
  Any class can access any public class in any package — unlimited visibility.

With modules:
  Public class in a module:   accessible only if the package is exported
  Exported package:           public types accessible at compile and runtime
  Opened package:             public types accessible via reflection at runtime
                              (needed for Spring/Hibernate/Jackson to work)
  Non-exported package:       completely inaccessible even if public — this is
                              why internal JDK APIs (sun.misc.Unsafe) now
                              generate warnings or fail entirely
```

**Module types:**

| Type | Definition | Example |
|------|-----------|---------|
| Named module | Has `module-info.class`, on the module path | Your app's modules |
| Automatic module | On module path but NO `module-info.class` | Third-party JARs not yet modularized |
| Unnamed module | Everything on the classpath (old-style) | Legacy classpath apps |

**WHY modules matter (even if you don't use them directly):**
- JDK itself is now modular: `java.base`, `java.sql`, `java.desktop`, etc. — you can create a minimal JRE with `jlink`
- Strong encapsulation: internal JDK APIs (like `sun.misc.Unsafe`) are inaccessible by default — this is why you see `--add-opens` flags in some frameworks
- Reliable configuration: missing dependencies are detected at startup, not at runtime (`ClassNotFoundException` at 2 AM)

### Interview Trap: `var` vs Dynamic Typing

**"Does `var` make Java dynamically typed?"** Absolutely not. The type is inferred at compile time and is immutable. The compiled bytecode contains the exact concrete type. You cannot assign an incompatible type to a `var` variable after declaration — the compiler will reject it. `var` is purely a developer ergonomics feature.

**"Can you use `var` in a lambda?"** No. Lambda parameters cannot use `var` as their declared type in the lambda header (you either provide explicit types or omit them entirely). Exception: Java 11 allows `var` in lambda parameters specifically to attach annotations: `(@NonNull var x) -> x.length()`.

---

## J9.2 — Switch Expressions & Pattern Matching (Java 14–21)

> **Builds on:** [J2.4 — Records](J2_oop.md#j24--records-java-16) · [J2.5 — Sealed Classes](J2_oop.md#j25--sealed-classes-java-17)
> **Connects to:** [J9.3 — Virtual Threads](J9_modern_java.md#j93--virtual-threads-project-loom--java-21)

### WHY Switch Evolved

Java's original `switch` statement was inherited from C: fall-through semantics, statement-only body, no value produced. Modern Java programs need switch to:
1. Produce a value (for functional-style code)
2. Cover all cases exhaustively (for sealed types)
3. Match on types and patterns (for complex dispatch)

### Switch Expressions (Java 14+)

Switch expressions produce a value. They use the `->` arrow syntax (no fall-through) or `yield` in a block body:

```java
// Old switch statement (fall-through, no value):
String result;
switch (day) {
    case MONDAY:
    case TUESDAY:
        result = "early week";
        break;
    case WEDNESDAY:
        result = "midweek";
        break;
    default:
        result = "late week";
}

// New switch expression (arrow syntax, produces value):
String result = switch (day) {
    case MONDAY, TUESDAY -> "early week";    // comma-separated cases, no fall-through
    case WEDNESDAY -> "midweek";
    default -> "late week";
};   // <- semicolon required (it's an expression used in assignment)

// Block body with yield:
int score = switch (grade) {
    case 'A' -> 100;
    case 'B' -> 85;
    case 'C' -> {
        // multi-line logic allowed in block
        System.out.println("Average grade");
        yield 70;    // yield produces the value from a block
    }
    default -> 0;
};
```

**Exhaustiveness:** switch expressions MUST cover all possible values (or have a `default`). This is enforced at compile time — a switch expression that can produce no value in some path is a compile error.

```java
// Compile error if Day is an enum with 7 values and we only cover 3:
String result = switch (day) {
    case MONDAY -> "mon";
    case TUESDAY -> "tue";
    case WEDNESDAY -> "wed";
    // COMPILE ERROR: switch expression does not cover all possible values
};
```

### Pattern Matching for `instanceof` (Java 16+)

Before Java 16, `instanceof` required an explicit cast:

```java
// Old style: redundant cast
if (obj instanceof String) {
    String s = (String) obj;   // safe cast — we know it's a String
    System.out.println(s.length());
}

// Java 16+ pattern matching: binding variable declared in the test
if (obj instanceof String s) {
    System.out.println(s.length());   // s is available here, already cast
}
// s is NOT in scope outside the if block
```

The binding variable `s` is automatically cast and scoped to the branch where the test is true. The JVM performs the cast once; subsequent uses of `s` do not re-check.

### Pattern Matching for `switch` (Java 21+)

The most powerful form: switch can now match on type patterns with guard clauses:

```java
Object obj = ...; // could be Integer, String, or something else

String result = switch (obj) {
    case Integer i when i > 0  -> "positive int: " + i;
    case Integer i             -> "non-positive int: " + i;
    case String s when s.isEmpty() -> "empty string";
    case String s              -> "string: " + s;
    case null                  -> "null";
    default                    -> "something else: " + obj.getClass().getName();
};
```

**`when` guard clauses:** the `when` keyword adds a boolean condition to a type pattern. If the type matches but the guard is false, the switch continues to the next case. Cases are checked top-to-bottom; the first matching case wins.

### Sealed Classes + Exhaustive Switch = No Default Required

The most important interaction: when switching over a sealed type and covering all permitted subtypes, the compiler proves exhaustiveness and no `default` is needed:

```java
// J2.5 example — sealed Shape hierarchy
sealed interface Shape permits Circle, Rectangle, Triangle {}
record Circle(double radius) implements Shape {}
record Rectangle(double width, double height) implements Shape {}
record Triangle(double base, double height) implements Shape {}

// Exhaustive switch — no default needed!
double area(Shape shape) {
    return switch (shape) {
        case Circle c    -> Math.PI * c.radius() * c.radius();
        case Rectangle r -> r.width() * r.height();
        case Triangle t  -> 0.5 * t.base() * t.height();
        // Compiler KNOWS there are exactly 3 subtypes — all covered
        // If you add a new Shape subtype, THIS SWITCH IS A COMPILE ERROR
    };
}
```

This is the killer combination for domain modeling: add a new variant to the sealed hierarchy and the compiler immediately flags every exhaustive switch that needs updating. You cannot forget to handle the new case.

### Deconstruction Patterns with Records (Java 21+)

Pattern matching integrates with records to destructure them inline:

```java
record Point(int x, int y) {}
record Line(Point start, Point end) {}

Object obj = new Line(new Point(0, 0), new Point(3, 4));

// Deconstruct nested records:
if (obj instanceof Line(Point(int x1, int y1), Point(int x2, int y2))) {
    double length = Math.sqrt(Math.pow(x2 - x1, 2) + Math.pow(y2 - y1, 2));
    System.out.println("Line length: " + length);
}
```

The nested deconstruction pattern extracts the record components without explicit field access. This is Java's approach to the destructuring that functional languages have had for decades.

### Interview Trap: Arrow Case vs Fall-Through

The old `switch` statement's colon syntax (`case X:`) still exists and still falls through. The new arrow syntax (`case X ->`) does NOT fall through. Mixing them in the same switch is a compile error:

```java
// Old: FALLS THROUGH
switch (x) {
    case 1:
    case 2:
        System.out.println("1 or 2");   // handles both 1 and 2
        break;
    case 3:
        // falls through to case 4 without break!
    case 4:
        System.out.println("3 or 4");
}

// New: no fall-through, comma-separated cases
switch (x) {
    case 1, 2 -> System.out.println("1 or 2");
    case 3, 4 -> System.out.println("3 or 4");
}
// Cannot use break in arrow-style switch cases (no fall-through to prevent)
```

---

## J9.3 — Virtual Threads (Project Loom — Java 21)

> **Builds on:** [J7.1 — Executor Framework](J7_concurrent_utilities.md#j71--executor-framework--threadpoolexecutor) · [J6.1 — Thread Lifecycle](J6_concurrency_fundamentals.md#j61--thread-lifecycle)

### WHY Virtual Threads: The Problem with Platform Threads

Before Java 21, the only kind of Java `Thread` was a **platform thread** — a Java thread backed 1:1 by an OS thread. This creates a fundamental scaling problem:

```
Platform Thread Cost:
  - OS stack allocation:     ~1 MB per thread (default, tunable with -Xss)
  - OS scheduler registration: syscall overhead
  - Context switch cost:     microseconds per switch (save/restore CPU registers)
  - Practical limit:         ~10,000 threads before OS scheduler thrashes

A server handling 50,000 concurrent HTTP requests with blocking I/O
needs 50,000 threads → 50 GB of stack space → OOM, or ~50,000
threads thrashing the OS scheduler
```

The traditional solutions — async/reactive programming (Project Reactor, RxJava) — require restructuring code around callbacks and non-blocking APIs. This fixes the threading problem but at enormous cost to code readability, debuggability, and library compatibility.

### Virtual Threads: The JVM Takes Control

Virtual threads are **JVM-managed, user-space threads**. They are not OS threads:

```
Virtual Thread Cost:
  - JVM stack:       starts at ~1 KB, grows on demand (stack chunks on heap)
  - JVM scheduler:   work-stealing ForkJoinPool (not OS scheduler)
  - Millions possible: limited by heap, not OS thread limits
  - Blocking I/O:   virtual thread is UNMOUNTED (carrier freed), not blocked
```

**The carrier thread model:**

```
Virtual Thread Lifecycle on Blocking I/O:

  [Virtual Thread A]          [Virtual Thread B]
       │                            │
       │ mount on Carrier-1         │
       ▼                            │
  ┌──────────────┐                  │
  │ Carrier-1    │  running A       │
  └──────────────┘                  │
       │                            │
       │ A calls socket.read()      │
       │ (blocking I/O)             │
       │                            │
       │ JVM UNMOUNTS A             │
       │ A's stack saved to heap    │
       ▼                            │
  ┌──────────────┐                  │
  │ Carrier-1    │  now mounts B ◄──┘
  └──────────────┘
       │
       │ B runs while A waits for I/O
       │
       │ I/O completes for A
       │ A remounted on any available carrier
       ▼
  ┌──────────────┐
  │ Carrier-2    │  running A again (same virtual thread, different carrier)
  └──────────────┘
```

The key insight: the OS thread (carrier) is **never blocked** during I/O. It is freed to run other virtual threads. A pool of N carrier threads (N = number of CPU cores by default) can handle millions of concurrent I/O-bound virtual threads.

### Creating Virtual Threads

```java
// Method 1: Thread.ofVirtual()
Thread vt = Thread.ofVirtual()
    .name("my-virtual-thread")
    .start(() -> System.out.println("Hello from " + Thread.currentThread()));

// Method 2: Virtual thread per task executor (one-liner, most common)
ExecutorService executor = Executors.newVirtualThreadPerTaskExecutor();
executor.submit(() -> handleRequest(request));
// Each submitted task gets its own virtual thread — no pooling needed!

// Method 3: Check if current thread is virtual
boolean isVirtual = Thread.currentThread().isVirtual();

// Method 4: Create but don't start immediately
Thread vt2 = Thread.ofVirtual().unstarted(() -> doWork());
vt2.start();
```

**Key mental shift:** with virtual threads, you use `newVirtualThreadPerTaskExecutor()` — one virtual thread PER TASK. Do not pool virtual threads. They are cheap. Creating and discarding them is the intended pattern. Pooling them (like a fixed thread pool) defeats the purpose.

### Performance Model: I/O-Bound vs CPU-Bound

```
Virtual Threads HELP (I/O-bound workloads):
──────────────────────────────────────────
  HTTP clients, JDBC (blocking), file I/O, network sockets, gRPC,
  REST API calls — anything where threads spend most of their time
  waiting for external responses.

  Before virtual threads:
    1000 concurrent HTTP calls → 1000 platform threads (~1 GB stack)

  With virtual threads:
    1000 concurrent HTTP calls → 8 carrier threads (8-core machine)
    All I/O wait happens as unmounted virtual threads on heap


Virtual Threads DON'T HELP (CPU-bound workloads):
──────────────────────────────────────────────────
  Image processing, cryptography, sorting, mathematical computation —
  anything where threads are actively computing, not waiting.

  A CPU-bound virtual thread stays MOUNTED on its carrier (it never
  blocks, so it never unmounts). You still have N carrier threads for
  N cores. Virtual threads add scheduling overhead for no gain.
  Use ForkJoinPool or parallel streams for CPU-bound work instead.
```

### The Pinning Problem: `synchronized` Blocks

Virtual threads have one significant limitation: if a virtual thread enters a `synchronized` block or a `synchronized` method, it **pins** the carrier thread. A pinned carrier cannot be used by other virtual threads during the I/O wait.

```java
// PROBLEM: synchronized pins the carrier thread
class DatabasePool {
    synchronized Connection getConnection() throws Exception {
        // If this calls blocking I/O while synchronized,
        // the carrier thread is pinned — defeats virtual thread benefit!
        return underlyingPool.get();   // may block waiting for connection
    }
}

// SOLUTION: use ReentrantLock instead of synchronized for blocking operations
class DatabasePool {
    private final ReentrantLock lock = new ReentrantLock();

    Connection getConnection() throws Exception {
        lock.lock();
        try {
            return underlyingPool.get();   // JVM can unmount virtual thread here!
        } finally {
            lock.unlock();
        }
    }
}
```

`ReentrantLock` integrates with the JVM's virtual thread scheduler — the virtual thread is unmounted (not pinned) when it blocks waiting for the lock. `synchronized` does not, because it uses the OS-level monitor in the object header, which the JVM cannot intercept at the same level.

**Detection:** run with `-Djdk.tracePinnedThreads=full` to log pinning events. Watch for heavily-used `synchronized` blocks in hot paths.

### Virtual Threads vs Kotlin Coroutines

Both solve the same I/O-bound concurrency problem from different angles:

```
Feature                  Virtual Threads          Kotlin Coroutines
─────────────────────────────────────────────────────────────────────────
Mechanism                JVM platform feature     Language feature (compiler)
Code style               Blocking (sequential)    Sequential (looks blocking)
Syntax change needed     None — just use          suspend fun, async/await,
                         blocking APIs normally   coroutine builders
Library compatibility    Any blocking Java lib     Must use coroutine-aware
                         works as-is              suspending functions
Debuggability            Standard Java stack       Coroutine stack traces
                         traces                   (improved, but different)
CPU-bound scaling        Same as before           Same as before (dispatchers)
Framework integration    Automatic in Spring 6+   Native in Kotlin ecosystem
```

Key insight: virtual threads let you use **existing blocking Java APIs** (JDBC, `HttpClient`, file I/O) without modification and get non-blocking performance. Coroutines require libraries to expose `suspend` variants. For new Kotlin code, coroutines are the idiomatic choice; for existing Java codebases, virtual threads are the pragmatic path.

### Interview Trap: "Are Virtual Threads Pooled?"

Do not pool virtual threads. The `newVirtualThreadPerTaskExecutor()` executor creates one virtual thread per task and discards it when done. This is correct usage. Creating a fixed pool of virtual threads (like `newFixedThreadPool` but with virtual threads) is an anti-pattern: you lose the benefit of having many lightweight threads if you artificially limit concurrency.

```java
// WRONG — pools virtual threads, limits concurrency
ExecutorService badPool = Executors.newFixedThreadPool(100,
    Thread.ofVirtual().factory());   // 100 virtual threads max — defeats the point

// CORRECT — one virtual thread per task, unlimited
ExecutorService goodPool = Executors.newVirtualThreadPerTaskExecutor();
```

---

## J9.4 — Structured Concurrency & Sequenced Collections (Java 21)

> **Builds on:** [J9.3 — Virtual Threads](J9_modern_java.md#j93--virtual-threads-project-loom--java-21)

### WHY Structured Concurrency

Virtual threads make it cheap to create many concurrent subtasks. But managing their lifecycle — cancelling them on failure, collecting their results, ensuring none leak after the parent scope exits — is still error-prone with raw futures. Structured Concurrency borrows the concept from Kotlin's coroutines: a scope that owns all the concurrent work spawned inside it, with guaranteed cleanup.

The core guarantee: **all subtasks must finish (either complete or be cancelled) before the scope exits**. You cannot have a leaked subtask running after its parent scope closes.

```java
// Without Structured Concurrency: manually manage futures
Future<UserProfile> profileFuture = executor.submit(() -> fetchProfile(userId));
Future<List<Order>> ordersFuture = executor.submit(() -> fetchOrders(userId));

UserProfile profile = profileFuture.get();   // blocks
List<Order> orders = ordersFuture.get();     // blocks
// What if fetchProfile throws? ordersFuture is still running (leaked!)
```

### StructuredTaskScope (Java 21, Preview)

```java
import java.util.concurrent.StructuredTaskScope;

// Pattern 1: ShutdownOnFailure — cancel all if any subtask fails
try (var scope = new StructuredTaskScope.ShutdownOnFailure()) {

    // fork() submits a subtask and returns a Subtask (not a Future)
    StructuredTaskScope.Subtask<UserProfile> profileTask =
        scope.fork(() -> fetchProfile(userId));

    StructuredTaskScope.Subtask<List<Order>> ordersTask =
        scope.fork(() -> fetchOrders(userId));

    scope.join();           // wait for all subtasks to complete or any to fail
    scope.throwIfFailed();  // rethrow the first exception if any subtask failed
                            // and cancels remaining subtasks

    // All succeeded — get results safely
    UserProfile profile = profileTask.get();
    List<Order> orders = ordersTask.get();

} // scope.close() ensures ALL subtasks are done/cancelled — no leaks
```

```java
// Pattern 2: ShutdownOnSuccess — return first successful result (race)
try (var scope = new StructuredTaskScope.ShutdownOnSuccess<String>()) {

    scope.fork(() -> fetchFromPrimaryServer());
    scope.fork(() -> fetchFromBackupServer());

    scope.join();
    String result = scope.result();   // returns whichever completed first
                                      // cancels the slower task automatically

}
```

**Structured Concurrency's guarantees:**
1. A subtask cannot outlive its enclosing scope (no leaks)
2. If a subtask fails, the failure policy (ShutdownOnFailure/ShutdownOnSuccess) determines what happens to siblings
3. The scope closes only when all subtasks are complete or cancelled
4. Thread-dump tools can show the parent-child structure of tasks — better observability

```
Task Hierarchy with Structured Concurrency:

  handleRequest (parent scope)
  ├── fetchProfile (subtask, virtual thread)
  └── fetchOrders  (subtask, virtual thread)

  If fetchProfile fails → scope shuts down → fetchOrders cancelled → exception thrown
  If both succeed → scope collects results → continues
  Either way → scope.close() completes → no leaks
```

### Sequenced Collections (Java 21)

Java 21 added three new interfaces to the collections framework to fill a long-standing gap: there was no uniform way to access the first or last element of a collection, or to iterate in reverse.

```java
// Java 21: SequencedCollection interface (extends Collection)
interface SequencedCollection<E> extends Collection<E> {
    E getFirst();
    E getLast();
    void addFirst(E e);
    void addLast(E e);
    E removeFirst();
    E removeLast();
    SequencedCollection<E> reversed();  // returns a reverse-order VIEW
}

// Java 21: SequencedMap interface (extends Map)
interface SequencedMap<K, V> extends Map<K, V> {
    Map.Entry<K, V> firstEntry();
    Map.Entry<K, V> lastEntry();
    Map.Entry<K, V> pollFirstEntry();
    Map.Entry<K, V> pollLastEntry();
    SequencedMap<K, V> reversed();
}
```

Before Java 21, to get the last element of a List:

```java
// Before Java 21 — verbose and inconsistent
String last = list.get(list.size() - 1);           // List
Object last2 = ((LinkedList<?>) list).getLast();   // LinkedList only
String last3 = deque.peekLast();                   // Deque

// Java 21 — uniform for any SequencedCollection
String last = list.getLast();
String first = list.getFirst();
List<String> reversed = list.reversed();   // live view, not a copy
```

**Which collections implement the new interfaces:**

| Collection | Implements |
|-----------|-----------|
| `ArrayList` | `SequencedCollection` |
| `LinkedList` | `SequencedCollection`, `SequencedMap` (as Deque) |
| `TreeSet` | `SequencedCollection` (NavigableSet extends it) |
| `LinkedHashSet` | `SequencedCollection` |
| `TreeMap` | `SequencedMap` |
| `LinkedHashMap` | `SequencedMap` |

`HashSet` and `HashMap` do NOT implement the sequenced interfaces — they have no defined order.

### The Complete Modern Java Picture

Putting it all together — sealed classes (J2.5), records (J2.4), pattern matching switch (J9.2), and structured concurrency (J9.4) form a cohesive system for writing safe, expressive, concurrent Java:

```java
// Domain modeling with sealed types + records (J2.4, J2.5)
sealed interface Result<T> permits Result.Success, Result.Failure {
    record Success<T>(T value) implements Result<T> {}
    record Failure<T>(String error, Throwable cause) implements Result<T> {}
}

// Concurrent fetch with virtual threads + structured concurrency (J9.3, J9.4)
Result<DashboardData> buildDashboard(long userId) {
    try (var scope = new StructuredTaskScope.ShutdownOnFailure()) {

        var profileTask = scope.fork(() -> fetchProfile(userId));
        var ordersTask  = scope.fork(() -> fetchOrders(userId));
        var metricsTask = scope.fork(() -> fetchMetrics(userId));

        scope.join().throwIfFailed();

        var data = new DashboardData(
            profileTask.get(), ordersTask.get(), metricsTask.get()
        );
        return new Result.Success<>(data);

    } catch (Exception e) {
        return new Result.Failure<>("Failed to build dashboard", e);
    }
}

// Pattern matching on sealed result type (J9.2)
String render(Result<DashboardData> result) {
    return switch (result) {
        case Result.Success<DashboardData> s -> renderDashboard(s.value());
        case Result.Failure<DashboardData> f -> renderError(f.error());
        // No default needed — sealed type, all cases covered
    };
}
```

### Interview Trap: Structured Concurrency vs CompletableFuture

**"How does Structured Concurrency differ from CompletableFuture?"**

`CompletableFuture` chains computations with callbacks and does not guarantee task containment — a future created inside a method can outlive the method. Cancellation must be manually propagated. Stack traces are fragmented across callback chains, making debugging difficult.

Structured Concurrency provides:
- Lexical scoping: all subtasks are contained within the scope's block
- Automatic cancellation: scope policies handle cancellation on failure/success
- No leaks: the scope cannot exit until all subtasks are done or cancelled
- Better observability: task hierarchy is visible in thread dumps

`CompletableFuture` is better for: composing independent async operations with complex dependency graphs, integration with non-blocking I/O frameworks (Netty, WebFlux), and code that must interoperate with existing reactive libraries.

---

### Virtual Threads vs Kotlin Coroutines — Side-by-Side

Both solve the same core problem: **I/O-bound code that blocks a thread wastes OS resources**. They take fundamentally different approaches.

```
┌─────────────────────┬──────────────────────────────┬──────────────────────────────┐
│                     │  Java Virtual Threads (JDK 21)│  Kotlin Coroutines           │
├─────────────────────┼──────────────────────────────┼──────────────────────────────┤
│ Abstraction level   │ Thread (looks like blocking) │ Suspend functions (explicit)  │
│ Scheduling          │ JVM (ForkJoinPool carrier)   │ JVM + CoroutineDispatcher     │
│ State storage       │ Stack on heap (~1KB)         │ Continuation object (heap)    │
│ Blocking I/O        │ Unmounts carrier, no stall   │ suspend + resume, no stall    │
│ Code style          │ Regular blocking code        │ Must mark suspend, use await  │
│ Structured concur. │ StructuredTaskScope (JDK 21) │ Built-in (launch/async/scope) │
│ Cancellation        │ Thread.interrupt()           │ First-class CancellationExc.  │
│ CPU-bound work      │ No benefit (still blocks)    │ No benefit (use Default disp.)│
│ Ecosystem fit       │ Drop-in for any blocking API │ Kotlin-first, new mental model│
│ Pinning risk        │ synchronized blocks carrier  │ No pinning; use Lock instead  │
└─────────────────────┴──────────────────────────────┴──────────────────────────────┘
```

**The key mental model difference:**

Virtual Threads pretend to be threads — you write blocking code and the JVM handles unmounting/remounting transparently. No new keywords, no function coloring problem (no `suspend` virus spreading through your call stack). Drop existing JDBC/Hibernate/Apache HttpClient code into a virtual thread and it scales.

Kotlin Coroutines require explicit color — a `suspend` function can only be called from another `suspend` function or a coroutine builder. This is the "function coloring" trade-off: more explicit = more control, but a steeper learning curve and more refactoring cost for existing codebases.

**Interview Q: "Can I use Kotlin coroutines AND virtual threads?"**
Yes — they complement each other. Dispatchers.IO already runs on a ForkJoinPool; on JDK 21+ you can configure it to use virtual threads as the backing threads. Coroutines handle structured concurrency and cancellation; virtual threads handle JVM-level I/O efficiency. They are not mutually exclusive.

**Interview Trap: "Virtual threads replace coroutines."**
No. Virtual threads are a JVM feature (lower level). Coroutines are a programming model (higher level) with built-in structured concurrency, cancellation, Flow, and ViewModel integration. On Android, virtual threads are not relevant (Android runs ART, not OpenJDK 21). Coroutines remain the answer for Android development.

> **See also:** [Kotlin 09 — Coroutines](../../Kotlin/Questions/09_coroutines_execution_mechanics.md) · [J7.6 — CompletableFuture](J7_concurrent_utilities.md)

---

## Master Summary: Modern Java (9–21)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  PHASE J9 — MODERN JAVA MASTER SUMMARY                                        │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  1. VAR & MODULES (J9.1)                                                     │
│     var = compile-time static inference — NOT dynamic typing. Bytecode is    │
│     identical to explicit type. Only for local variables with initializer.   │
│     var + diamond (<>) infers Object if no type arg: var x = new ArrayList<>()│
│     infers ArrayList<Object>. Always provide type arg with var.              │
│     Modules (JPMS): module-info.java with exports/requires/opens/provides.   │
│     Named > automatic > unnamed module. --add-opens for framework reflection.│
│                                                                              │
│  2. SWITCH EXPRESSIONS & PATTERN MATCHING (J9.2)                             │
│     Switch expression: produces a value, arrow syntax (->), no fall-through, │
│     exhaustiveness required (or default). yield in block body.               │
│     instanceof pattern: if (obj instanceof String s) — s is auto-cast.      │
│     Switch + type patterns: case String s when s.isEmpty() -> ...           │
│     Sealed types + exhaustive switch = no default needed, compile-time       │
│     verification — add a subtype → every switch is a compile error.         │
│     Record deconstruction: case Point(int x, int y) -> ...                  │
│                                                                              │
│  3. VIRTUAL THREADS (J9.3)                                                   │
│     Platform threads: 1:1 with OS threads, ~1MB stack, ~10k limit.          │
│     Virtual threads: JVM-managed, ~1KB stack, millions possible.            │
│     I/O blocks → virtual thread UNMOUNTS (carrier thread freed).            │
│     Create: Thread.ofVirtual().start() or newVirtualThreadPerTaskExecutor(). │
│     DO NOT pool virtual threads — one per task is correct.                   │
│     Help: I/O-bound work. Don't help: CPU-bound work.                       │
│     Pinning: synchronized pins carrier — use ReentrantLock for I/O blocks.  │
│                                                                              │
│  4. STRUCTURED CONCURRENCY & SEQUENCED COLLECTIONS (J9.4)                   │
│     StructuredTaskScope: fork subtasks, join, all done/cancelled on close.  │
│     ShutdownOnFailure: cancel all if any fails; throwIfFailed() + get().    │
│     ShutdownOnSuccess: return first result, cancel rest (race pattern).     │
│     No task leaks: scope cannot exit until all subtasks are settled.        │
│     SequencedCollection: getFirst(), getLast(), reversed() — uniform API    │
│     for List, LinkedHashSet, TreeSet, LinkedHashMap, TreeMap.                │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

*← [Phase J8 — Garbage Collection & JVM Tuning](J8_gc_and_jvm_tuning.md)*

---

**Cross-references:**
- Virtual Threads vs CompletableFuture (pre-Loom async model): [J7.6 — CompletableFuture](J7_concurrent_utilities.md)
- Virtual Threads vs Kotlin Coroutines (same problem, different ecosystems): [Kotlin 09 — Coroutines](../../Kotlin/Questions/09_coroutines_execution_mechanics.md)
- Structured Concurrency parallel concept in Kotlin: [Kotlin 10 — Structured Concurrency](../../Kotlin/Questions/10_structured_concurrency.md)
- Sealed classes + exhaustive switch (Java 21): [J2.5 — Sealed Classes](J2_oop.md)
- Records as Java's data class equivalent: [J2.4 — Records](J2_oop.md) · [Kotlin 02 — data class](../../Kotlin/Questions/02_classes_and_objects.md)
