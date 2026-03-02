# Java Master Follow-Up Chains

> The Java equivalent of `master_chains.md`. Each chain maps the path an interviewer walks when drilling into a Java topic. Every node shows the question, the answer, and the mechanism behind the answer.

## Navigation

| Chain | Topic | Starting Question |
|-------|-------|-------------------|
| [A](#chain-a--jvm-stack--heap--object-identity) | JVM Stack vs Heap → Object Identity | "What's the difference between `==` and `.equals()`?" |
| [B](#chain-b--type-erasure--generics--wildcards) | Type Erasure → Generics → Wildcards | "Why can't you do `instanceof List<String>`?" |
| [C](#chain-c--oop--polymorphism--virtual-dispatch--jit) | OOP → Polymorphism → JIT | "What does `final` do to a class?" |
| [D](#chain-d--lambdas--streams--parallel-pitfalls) | Lambdas → Streams → Parallel Pitfalls | "What is a lambda in Java?" |
| [E](#chain-e--collections--hashmap--concurrenthashmap) | Collections → HashMap → Thread Safety | "How does HashMap work?" |
| [F](#chain-f--volatile--jmm--synchronized--locks) | volatile → JMM → synchronized → Locks | "What does `volatile` do?" |
| [G](#chain-g--threadpoolexecutor--futures--completablefuture) | ThreadPoolExecutor → Futures → CompletableFuture | "What's wrong with `newFixedThreadPool`?" |
| [H](#chain-h--gc--heap-regions--memory-leaks--oom) | GC → Heap Regions → Memory Leaks → OOM | "When does a Minor GC trigger?" |
| [I](#chain-i--modern-java--virtual-threads--structured-concurrency) | Modern Java → Virtual Threads → Structured Concurrency | "What are virtual threads?" |

---

## Chain A — JVM Stack vs Heap → Object Identity

*"What's the difference between `==` and `.equals()`?"*
> **What the interviewer is testing:** Whether you know `==` is pointer equality at the JVM level — and whether you know the exceptions (Integer cache, String pool) that make this confusing.

```
== compares REFERENCES, not content   [J0.1]
    │
    ├──► For primitives: == compares VALUES directly (int a == int b compares bits).
    │    For objects: == compares the POINTER — are both variables pointing to the
    │    SAME object on the heap? Two separate `new String("hello")` calls produce
    │    two different objects at different heap addresses → == is false even though
    │    the content is identical.
    │
    ├──► equals() is a method call. Object.equals() defaults to == (reference equality).
    │    String, Integer, List etc. OVERRIDE it to compare content.
    │    If you write a class and don't override equals(), == and .equals() behave the same.
    │
So why does Integer a = 127; Integer b = 127; a == b return true?
    │
    ├──► Integer.valueOf() (used by autoboxing) maintains a cache for -128 to +127.   [J0.2]
    │    valueOf(127) returns the SAME cached Integer object every time.
    │    a and b both point to the SAME object → == is true.
    │    valueOf(128) creates a NEW Integer object each time → == is false for 128.
    │    WHY this range: most common int values fall here; 256 cached objects ≈ 4KB.
    │
Why does "hello" == "hello" return true for string literals?
    │
    ├──► String literals are interned into the JVM String Pool at class load time.   [J0.3]
    │    The compiler deduplicates all identical string literals across the class.
    │    Both "hello" references point to the same interned String object in the pool.
    │    new String("hello") BYPASSES the pool → creates a heap object → == is false.
    │    String.intern() forces a string back into the pool.
    │
How does the JVM know the "type" of an object at runtime?
    │
    ├──► Every object on the heap has a 12-16 byte object header.   [J0.1]
    │    The header contains a CLASS POINTER (klass pointer) — a reference to the
    │    Class metadata object (in Metaspace) that describes this object's type.
    │    instanceof, casts, and virtual dispatch all read this class pointer.
    │    On 64-bit JVMs, compressed OOPs encode this pointer in 32 bits (saves memory).
    │
When is an object eligible for GC?
    │
    └──► When it is no longer reachable from any GC root.
         GC roots: local variables in any thread's stack frame, static fields,
         JNI references, active thread objects.
         Even if two objects reference each other (circular reference), if neither
         is reachable from a GC root, both are eligible — the JVM uses reachability,
         NOT reference counting.   [J8.1]
```

---

## Chain B — Type Erasure → Generics → Wildcards

*"Why can't you do `instanceof List<String>`?"*
> **What the interviewer is testing:** Type erasure understanding — the most-asked generics question — then whether you understand PECS for wildcard bounds.

```
Type erasure — what is it?   [J3.1]
    │
    ├──► At compile time, the Java compiler knows List<String> vs List<Integer>.
    │    At runtime, both are simply List in the bytecode.
    │    The compiler removes (erases) generic type arguments from the compiled bytecode
    │    to maintain binary compatibility with pre-generic Java 1.4 class files.
    │    Result: the JVM has no concept of "a List that holds only Strings."
    │
So why does instanceof List<String> fail?
    │
    ├──► The `instanceof` operator checks the runtime type via the object's class pointer.
    │    There is no "List<String>" class to check against at runtime — only "List".
    │    The compiler refuses to compile it: "Cannot check for erased type List<String>."
    │    list instanceof List<?> compiles: checks the object is a List (ignoring element type).
    │
What does erasure produce in the bytecode?
    │
    ├──► Type parameters are replaced by their upper bound (Object if unbounded).   [J3.1]
    │    public T get(int i) → public Object get(int i)  in bytecode.
    │    At the call site, the compiler inserts a CHECKCAST:
    │    String s = list.get(0) → String s = (String) list.get(0) in bytecode.
    │    Bridge methods are generated when overriding generic methods to preserve
    │    the polymorphism contract (one method with erased signature + one bridge).
    │
What is PECS?   [J3.2]
    │
    ├──► Producer Extends, Consumer Super — the rule for choosing wildcards.
    │    ? extends T (upper bounded): you can READ T from it, never WRITE.
    │    WHY: if List<? extends Animal> could be a List<Dog> or List<Cat>,
    │    you can safely read any element as Animal. But if you try to add a Cat
    │    to what might be a List<Dog>, that's a type violation — compiler forbids it.
    │
    ├──► ? super T (lower bounded): you can WRITE T into it, never READ as T.
    │    WHY: if List<? super Dog> could be a List<Dog> or List<Animal>,
    │    adding a Dog is always safe (Dog IS-A Dog, Dog IS-A Animal).
    │    But reading: you don't know if you get a Dog or an Animal or an Object —
    │    you can only read as Object (the top of the hierarchy).
    │
    ├──► PECS mnemonic applied:
    │    copy(List<? extends T> src, List<? super T> dest)
    │    src PRODUCES elements (you read from it) → ? extends T
    │    dest CONSUMES elements (you write to it) → ? super T
    │
What is heap pollution?   [J3.1]
    │
    └──► When a variable of a parameterized type refers to an object that is NOT
         of that parameterized type. Caused by unchecked casts or raw types.
         List rawList = new ArrayList<String>();
         List<Integer> intList = rawList;   // unchecked cast — compiles with warning
         intList.get(0) → ClassCastException at runtime when the CHECKCAST fires.
         The error occurs at the read site, far from where the type was corrupted —
         making heap pollution bugs very hard to trace.
```

---

## Chain C — OOP → Polymorphism → Virtual Dispatch → JIT

*"What does `final` do to a class?"*
> **What the interviewer is testing:** Whether you connect final → JIT optimization → devirtualization, and whether you know the deoptimization consequence.

```
final class — what changes?   [J2.1]
    │
    ├──► final prevents subclassing. No class can extend a final class.
    │    Consequence for the JVM: a final class has no subclasses to dispatch to.
    │    Any call to a method on a final class reference is MONOMORPHIC by definition —
    │    there is only one possible implementation. No vtable lookup needed.
    │
How does the JIT exploit this?
    │
    ├──► For a final class, the JIT can DEVIRTUALIZE every method call:   [J0.4]
    │    Instead of INVOKEVIRTUAL → vtable index lookup → indirect jump,
    │    the JIT compiles it to a direct call (or inlines the method body entirely).
    │    For non-final classes, the JIT still does this speculatively (monomorphic
    │    inline cache) if it has only seen one concrete type at that call site.
    │    Guard: "if receiver is still ClassA, use inlined code; else deoptimize."
    │
What happens when the JIT's speculation is wrong?
    │
    ├──► DEOPTIMIZATION: the JVM discards the compiled code for that method and   [J0.4]
    │    falls back to interpreted execution. After enough interpreted cycles,
    │    the JIT recompiles with bimorphic inline cache (two type checks, two paths).
    │    If a third type appears → MEGAMORPHIC: no inlining, plain vtable lookup.
    │    Production impact: introducing a logging proxy that wraps your service
    │    makes every call site bimorphic → all inlined paths are abandoned.
    │
What does INVOKEVIRTUAL vs INVOKEINTERFACE mean?   [J0.4]
    │
    ├──► INVOKEVIRTUAL: dispatches via the vtable (virtual method table).
    │    Each class has a vtable — an array of method pointers.
    │    The method's index in the vtable is fixed at class-load time (same across hierarchy).
    │    Lookup: O(1) — just array[index].
    │
    ├──► INVOKEINTERFACE: dispatches via the itable (interface method table).
    │    An interface can be implemented by any class in any hierarchy —
    │    the method's position is not at a fixed vtable index.
    │    The JVM must search the itable to find the correct implementation.
    │    Slightly more expensive, but JIT devirtualization eliminates the difference
    │    at monomorphic call sites.
    │
What does abstract enforce?   [J2.1]
    │
    └──► abstract class: cannot be instantiated directly, but CAN be subclassed.
         abstract method: must be overridden in every concrete subclass.
         The compiler enforces this — any non-abstract subclass that doesn't
         override all abstract methods is a compile error.
         WHY useful: forces subclasses to provide an implementation without specifying
         what that implementation must be. Template Method pattern relies on this.
```

---

## Chain D — Lambdas → Streams → Parallel Pitfalls

*"What is a lambda in Java?"*
> **What the interviewer is testing:** Whether you know `invokedynamic` (not just "it's an anonymous class"), and whether you know what makes parallel streams dangerous.

```
What is a lambda at the JVM level?   [J4.1]
    │
    ├──► A lambda is NOT an anonymous inner class (despite looking like one).
    │    The compiler emits an INVOKEDYNAMIC instruction at the lambda call site.
    │    On first invocation, INVOKEDYNAMIC calls LambdaMetafactory.metafactory()
    │    (the bootstrap method), which dynamically generates a class that implements
    │    the target functional interface by delegating to a static synthetic method
    │    the compiler created from the lambda body.
    │    WHY not anonymous class: anonymous classes are generated at compile time
    │    (one .class file per lambda). invokedynamic defers class generation to runtime,
    │    letting the JVM choose the optimal strategy per platform.
    │
What is a functional interface?   [J4.1]
    │
    ├──► Any interface with exactly ONE abstract method. @FunctionalInterface enforces this.
    │    Examples: Runnable (run()), Callable<V> (call()), Comparator<T> (compare()),
    │    Function<T,R> (apply()), Predicate<T> (test()), Consumer<T> (accept()).
    │    A lambda can be assigned to any compatible functional interface.
    │    WHY: the compiler needs exactly one method to "fill in" with the lambda body.
    │    Default and static methods in the interface don't count (not abstract).
    │
What is a Stream and why is it lazy?   [J4.3]
    │
    ├──► A Stream is a pipeline: Source → [intermediate ops] → terminal op.
    │    Intermediate ops (filter, map, flatMap) are LAZY — they build a description
    │    of what to do but do NOT process any elements.
    │    The terminal op (collect, forEach, findFirst) TRIGGERS execution.
    │    WHY lazy: allows the pipeline to short-circuit. findFirst() + filter() only
    │    processes elements until one passes the filter — not the whole collection.
    │    Also enables pipeline fusion: filter + map run in ONE pass over the data,
    │    not two separate passes.
    │
When does parallel stream actually help vs hurt?   [J4.3]
    │
    ├──► HELPS: large data (thousands of elements), CPU-bound computation per element,
    │    no shared mutable state, the source can be efficiently split (ArrayList yes,
    │    LinkedList no — linked lists require sequential traversal to split).
    │
    ├──► HURTS — stateful intermediate ops:
    │    sorted() and distinct() require seeing ALL elements before producing output.
    │    sorted() in a parallel stream: all threads collect their elements, then merge-sort.
    │    The sort is parallel, but the merge requires coordination → significant overhead
    │    for small datasets, may not beat sequential.
    │
    ├──► HURTS — boxing overhead:
    │    Stream<Integer> boxes every element. Use IntStream, LongStream, DoubleStream
    │    for primitives to eliminate boxing allocations entirely.
    │
What is the common thread pool parallel streams use?   [J4.3]
    │
    └──► ForkJoinPool.commonPool() — shared across the entire application.
         Default parallelism: number of CPU cores - 1.
         If your parallel stream blocks on I/O (wrong use case), it blocks the common pool
         threads, starving OTHER parallel streams and CompletableFuture operations
         that also use commonPool.
         Fix: wrap in a custom ForkJoinPool:
         new ForkJoinPool(4).submit(() -> list.parallelStream().map(...).collect(...)).get()
```

---

## Chain E — Collections → HashMap → ConcurrentHashMap

*"How does HashMap work?"*
> **What the interviewer is testing:** Bucketing, treeification, resize mechanics, and why these make HashMap unsafe under concurrency.

```
HashMap structure and get()   [J5.2]
    │
    ├──► Array of buckets (Node[] table). Default capacity: 16 buckets.
    │    get(key): compute hash → spread bits → bucket index = hash % capacity
    │    → walk the chain in that bucket comparing keys with equals().
    │    Average: O(1). Worst case (all keys in one bucket): O(n) pre-Java 8, O(log n) Java 8+.
    │
What is treeification and why was it added?   [J5.2]
    │
    ├──► Java 8: when a bucket chain exceeds 8 nodes, it converts to a Red-Black tree.
    │    get/put on a tree bucket: O(log n) instead of O(n).
    │    WHY: pre-Java 8, you could craft a denial-of-service attack by sending keys
    │    that all hash to the same bucket, making every HashMap operation O(n).
    │    Treeification caps worst-case at O(log n) regardless of key distribution.
    │    Converts back to linked list when size drops below 6 (hysteresis).
    │
When does HashMap resize?   [J5.2]
    │
    ├──► When size > capacity * loadFactor (default 0.75).
    │    At capacity 16: resizes at 12 entries. New capacity: 32.
    │    Resize: allocate new array, REHASH all entries (recompute bucket index under new capacity).
    │    WHY rehash: bucket index = hash % capacity. Doubling capacity changes the modulus.
    │    Java 8 optimization: because capacity is always a power of 2, the new bucket index
    │    is either the old index OR old index + oldCapacity (just check one new bit).
    │    This halves the rehashing cost and avoids recomputing the hash.
    │
Why is HashMap not thread-safe?   [J6.2]
    │
    ├──► Two threads calling put() simultaneously can both see size < resizeThreshold,
    │    both enter resize(), both write to the table reference concurrently.
    │    Java 7: resize creates a new linked list with reversed node order.
    │    Two concurrent resizes can create a cycle: node1.next = node2, node2.next = node1.
    │    Any subsequent get() on that bucket spins forever — infinite loop, 100% CPU.
    │    Java 8: resize algorithm is different (no reversal), but concurrent puts can still
    │    cause lost updates (both threads write to the same bucket, one update is lost).
    │
What does ConcurrentHashMap do differently?   [J5.4]
    │
    ├──► Java 7: divided into 16 segments (Segment extends ReentrantLock).
    │    Concurrent writes to different segments proceed in parallel.
    │    Java 8+: bin-level synchronization using CAS (Compare-And-Swap) for empty buckets
    │    and synchronized (per-bin monitor) for non-empty buckets.
    │    Reads are entirely LOCK-FREE — use volatile reads via VarHandle.
    │    get() never acquires a lock. put() only locks the specific bin being modified.
    │
ConcurrentHashMap vs Collections.synchronizedMap — which to use?   [J5.4]
    │
    └──► synchronizedMap wraps EVERY method with synchronized(this).
         All operations (including reads) acquire a single lock.
         Under contention: every thread blocks every other thread — no parallelism.
         ConcurrentHashMap: reads are lock-free, writes lock only the affected bin.
         Multiple writers can proceed concurrently if they're in different bins.
         Use ConcurrentHashMap always. synchronizedMap is only appropriate when
         you need to iterate while holding the lock (ConcurrentHashMap's iterators
         are weakly consistent — they don't throw ConcurrentModificationException).
```

---

## Chain F — volatile → JMM → synchronized → Locks

*"What does `volatile` do?"*
> **What the interviewer is testing:** Whether you know visibility is distinct from atomicity, and whether you can explain the JMM happens-before rule.

```
volatile guarantees VISIBILITY, not atomicity   [J6.3]
    │
    ├──► Without volatile: a write by Thread A to a field might sit in Thread A's
    │    CPU cache (L1/L2). Thread B reading the same field reads its OWN cache —
    │    which may have a stale value. No cache coherence guarantee.
    │    With volatile: reads/writes go directly to main memory (or flush cache to memory).
    │    Every thread that reads a volatile field sees the most recently written value.
    │
    ├──► BUT: volatile does NOT make compound operations atomic.
    │    volatile int count; count++ is READ → INCREMENT → WRITE — three operations.
    │    Two threads can both read count=0, both increment to 1, both write 1.
    │    Result: count=1 instead of count=2. Use AtomicInteger for atomic increment.
    │
What is the happens-before guarantee from volatile?   [J6.3]
    │
    ├──► JMM rule: a write to a volatile field happens-before every subsequent read
    │    of that same field by any thread.
    │    Consequence: ALL writes performed by Thread A BEFORE writing the volatile field
    │    are visible to Thread B AFTER it reads the volatile field.
    │    This is the "publication idiom": write all fields, then write volatile flag=true.
    │    Thread B reads volatile flag=true → all earlier writes are visible.
    │    Thread B does NOT need to read each field as volatile — transitivity covers them.
    │
When is volatile insufficient and synchronized required?   [J6.2]
    │
    ├──► Whenever you have a "check-then-act" compound operation:
    │    if (map.containsKey(k)) { map.put(k, compute()) }  — NOT safe with volatile map.
    │    Between the check and the put, another thread can insert the same key.
    │    synchronized: guarantees MUTUAL EXCLUSION + visibility.
    │    Only ONE thread can hold the monitor at a time — the check-then-act is atomic.
    │
How does synchronized work at the JVM level?   [J6.2]
    │
    ├──► Every object has a monitor (built into the object header's mark word).
    │    MONITORENTER: thread attempts to acquire the monitor.
    │    If acquired: mark word stores the thread ID, lock count = 1.
    │    If contended: thread goes to BLOCKED state (OS-level block).
    │    MONITOREXIT: decrement count. At 0, release monitor, wake up BLOCKED threads.
    │    Performance: uncontended synchronized is very cheap (JIT often eliminates it
    │    entirely via lock elision if the lock object doesn't escape the method).
    │
When should you use ReentrantLock over synchronized?   [J7.3]
    │
    └──► ReentrantLock adds capabilities synchronized doesn't have:
         1. tryLock(timeout) — attempt acquisition, fail fast if unavailable.
         2. lockInterruptibly() — can be interrupted while waiting (synchronized can't).
         3. Multiple Conditions (newCondition()) vs one implicit wait set.
         4. Fairness mode (FIFO acquisition order) — prevents starvation.
         Use synchronized by default (simpler, JIT-optimized). Use ReentrantLock
         when you specifically need one of these four capabilities.
         CRITICAL: ReentrantLock MUST be unlocked in a finally block.
         Forgetting finally → deadlock if an exception is thrown while holding the lock.
```

---

## Chain G — ThreadPoolExecutor → Futures → CompletableFuture

*"What's wrong with `newFixedThreadPool`?"*
> **What the interviewer is testing:** Whether you know the OOM hazard, and whether you understand the CompletableFuture composition model.

```
Executors.newFixedThreadPool(n) — the hidden danger   [J7.1]
    │
    ├──► newFixedThreadPool(4) creates a ThreadPoolExecutor with:
    │    corePoolSize = maximumPoolSize = 4, and an UNBOUNDED LinkedBlockingQueue.
    │    When all 4 threads are busy and a new task arrives: task queued.
    │    When the queue has 1 million tasks: still queued — no back-pressure.
    │    Under sustained overload: queue grows without bound → OutOfMemoryError.
    │
The correct way: construct ThreadPoolExecutor directly   [J7.1]
    │
    ├──► new ThreadPoolExecutor(4, 8, 60, SECONDS,
    │        new ArrayBlockingQueue<>(1000),
    │        new ThreadPoolExecutor.CallerRunsPolicy())
    │    Bounded queue: when full, new threads spawn up to maximumPoolSize (8).
    │    CallerRunsPolicy: when at max threads AND queue full, the CALLER runs the task.
    │    This slows the producer (natural backpressure) instead of crashing the JVM.
    │
What is the task routing order in ThreadPoolExecutor?   [J7.1]
    │
    ├──► 1. If running threads < corePoolSize: start a new thread (even if idle ones exist).
    │    2. If at corePoolSize: offer to queue.
    │    3. If queue is full: start a new thread up to maximumPoolSize.
    │    4. If at maximumPoolSize: RejectedExecutionHandler.
    │    KEY INSIGHT: the pool does NOT grow past corePoolSize until the queue is FULL.
    │    With an unbounded queue (LinkedBlockingQueue), step 3 NEVER triggers.
    │    maximumPoolSize > corePoolSize only matters with a BOUNDED queue.
    │
What is Future and why is it limited?   [J7.6]
    │
    ├──► Future<T> represents an async computation result. future.get() BLOCKS the
    │    calling thread until the result is ready.
    │    Problems: no chaining (can't say "when this completes, run that"),
    │    no combining (can't easily say "wait for all of these"),
    │    no non-blocking callbacks.
    │
How does CompletableFuture fix this?   [J7.6]
    │
    ├──► CompletableFuture<T> is a non-blocking Future with a rich composition API.
    │    thenApply(fn): transform the result (like Stream.map) — runs in the completing thread.
    │    thenApplyAsync(fn): transform the result on a new thread (commonPool by default).
    │    thenCompose(fn): chain async operations (fn returns another CompletableFuture).
    │    thenCombine(other, fn): run two futures in parallel, combine their results.
    │    allOf(f1, f2, f3): wait for all futures (returns CompletableFuture<Void>).
    │    exceptionally(fn): handle failure without stopping the chain.
    │
thenApply vs thenApplyAsync — which thread runs the callback?   [J7.6]
    │
    └──► thenApply: runs on whatever thread completed the upstream stage.
         If the upstream was already done when thenApply was registered:
         runs on the registering thread (synchronous execution).
         If the upstream completes while thenApply is waiting:
         runs on the completing thread (async execution in the completing thread).
         This makes thenApply NON-DETERMINISTIC about which thread it runs on.
         thenApplyAsync: ALWAYS submits the callback to the executor (commonPool by default).
         Predictable threading — use thenApplyAsync when thread context matters
         (e.g., never do UI work in a thenApply — use Android's Main executor instead).
```

---

## Chain H — GC → Heap Regions → Memory Leaks → OOM

*"When does a Minor GC trigger?"*
> **What the interviewer is testing:** Whether you know the generational hypothesis and can reason about what causes OOM and memory leaks.

```
Minor GC — trigger and mechanics   [J8.1]
    │
    ├──► Eden space fills up → Minor GC triggered (stop-the-world, usually <10ms).
    │    Generational hypothesis: most objects die young (created in one request, die
    │    when the request ends). So collect Eden (young gen) frequently and cheaply.
    │    Minor GC traces from GC roots INTO Eden + active Survivor space.
    │    Live objects copied to the empty Survivor space (S0/S1 alternate roles).
    │    Objects that survive enough GCs (default 15 cycles) → promoted to Old Gen.
    │
What triggers a Full GC and why is it expensive?   [J8.1]
    │
    ├──► Full GC: collects the ENTIRE heap (Young + Old Gen + Metaspace).
    │    Triggers: Old Gen fills up, System.gc() called, or JVM decides it's necessary.
    │    WHY expensive: Old Gen is large (gigabytes); collecting it stop-the-world
    │    can pause the application for seconds. "GC pause = user-visible latency."
    │
How does G1GC differ from Serial/Parallel GC?   [J8.2]
    │
    ├──► Serial/Parallel: fixed young/old regions. Full GC = entire heap pause.
    │    G1GC: heap divided into ~2048 equal regions (1–32MB each).
    │    Each region is independently labeled Eden/Survivor/Old/Humongous at any time.
    │    G1 does "mixed collections": collects young regions + the OLD regions with the
    │    most garbage first ("Garbage First" = garbage-dense regions prioritized).
    │    Concurrent marking runs alongside the application (no long stop-the-world).
    │    Tuning: -XX:MaxGCPauseMillis=200 (target pause, not a hard limit).
    │
What are common memory leak patterns in Java?   [J8.4]
    │
    ├──► 1. STATIC COLLECTIONS: static Map<Key, Value> that grows indefinitely.
    │       Objects added but never removed. GC cannot collect them — static fields
    │       are always reachable from the class (a GC root). Old Gen fills → OOM.
    │
    ├──► 2. LISTENERS NOT REMOVED: UI component registers a listener on a service.
    │       UI component is destroyed but the service still holds the listener reference.
    │       The destroyed component can't be GC'd — classic Android Context leak.
    │
    ├──► 3. THREADLOCAL NOT CLEARED: ThreadLocal stores values per-thread.
    │       In a thread pool, threads are reused. A ThreadLocal set in request A
    │       persists when the thread is reused for request B. If the value is large,
    │       it leaks across requests. Always call remove() in a finally block.
    │
    ├──► 4. INNER CLASS HOLDING OUTER REFERENCE: a non-static inner class (or anonymous
    │       class) holds an implicit reference to its enclosing instance.
    │       A Runnable created inside an Activity, submitted to a long-running executor,
    │       keeps the Activity alive until the Runnable completes.
    │
What causes OutOfMemoryError and how do you diagnose it?   [J8.4]
    │
    └──► Types of OOM:
         "Java heap space": heap exhausted. Objects can't be allocated.
         "GC overhead limit exceeded": JVM spent >98% of time in GC recovering <2% heap.
         "Metaspace": class metadata space exhausted (too many classes loaded).
         "unable to create new native thread": OS process limit reached.
         Diagnosis: add -XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=/tmp/
         Open the heap dump in Eclipse MAT → "Leak Suspects" report shows the largest
         retained object trees and their GC root path.
```

---

## Chain I — Modern Java → Virtual Threads → Structured Concurrency

*"What are virtual threads?"*
> **What the interviewer is testing:** Whether you understand the carrier model (not just "lightweight threads"), and whether you can contrast them with Kotlin coroutines.

```
Virtual threads — what problem do they solve?   [J9.3]
    │
    ├──► Platform (OS) threads: one JVM thread = one OS thread = ~1MB stack.
    │    An OS thread blocked on I/O WASTES: the OS still allocates a kernel stack,
    │    a thread control block, and scheduler context for a thread that does nothing.
    │    Practical limit: ~10,000 threads before memory and scheduler overhead hurts.
    │    For high-throughput servers handling 1M concurrent requests: not viable.
    │
How do virtual threads solve this?   [J9.3]
    │
    ├──► Virtual threads are JVM-managed, not OS-managed.
    │    A small pool of "carrier threads" (OS threads, one per CPU) execute virtual threads.
    │    When a virtual thread blocks on I/O (e.g., reading from a socket),
    │    the JVM UNMOUNTS it from the carrier thread (saves its stack to the heap).
    │    The carrier thread is now free to run ANOTHER virtual thread.
    │    When the I/O completes, the virtual thread is REMOUNTED on any available carrier.
    │    Stack: ~1KB per virtual thread (on heap). You can have MILLIONS concurrently.
    │
What is the "pinning" problem?   [J9.3]
    │
    ├──► If a virtual thread calls synchronized and blocks INSIDE a synchronized block,
    │    it CANNOT be unmounted — it is "pinned" to the carrier thread.
    │    The carrier thread is blocked for the duration of the I/O inside the synchronized.
    │    You've now turned a virtual thread into a platform thread (full blocking).
    │    FIX: replace synchronized with ReentrantLock for any code path that
    │    does I/O inside the lock. ReentrantLock allows unmounting while waiting.
    │
Virtual threads vs Kotlin coroutines — key differences?   [J9.3]
    │
    ├──► Virtual threads: write normal blocking code — the JVM handles unmounting.
    │    No new keywords, no function coloring. Drop JDBC/Retrofit into a virtual thread.
    │    Coroutines: explicit suspend keyword. Can only call suspend from suspend.
    │    Requires refactoring existing code. But: first-class cancellation, structured
    │    concurrency built in, Flow for reactive streams, Android ViewModel integration.
    │    On Android: virtual threads are NOT available (Android runs ART, not OpenJDK 21).
    │    Coroutines remain the only answer for Android async programming.
    │
What is Structured Concurrency?   [J9.4]
    │
    └──► StructuredTaskScope: a try-with-resources block that owns its child tasks.
         fork(callable): submit a subtask.
         scope.join(): wait for all subtasks to complete.
         The scope CANNOT exit until all forked tasks are done or cancelled.
         This eliminates task leaks — no subtask outlives its scope.
         ShutdownOnFailure: if any subtask fails, cancel all others.
           scope.throwIfFailed() — rethrows the first exception.
         ShutdownOnSuccess: return the first successful result, cancel the rest.
         WHY: CompletableFuture.allOf() and Thread management can easily leak tasks
         on failure. StructuredTaskScope makes the "fan-out → join → handle" pattern
         safe by construction, with task lifecycle tied to lexical scope.
```

---

## Quick Reference: Java Interview Traps

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ TRAP 1: Integer a = 128; Integer b = 128; a == b → FALSE                   │
│   WHY: Integer cache covers only -128..127. valueOf(128) creates a new      │
│   object each time. Always use .equals() for Integer comparison.            │
│                                                                              │
│ TRAP 2: list instanceof List<String> → compile error                        │
│   WHY: Type erasure. List<String> is just List at runtime.                  │
│   Use list instanceof List<?> instead.                                       │
│                                                                              │
│ TRAP 3: volatile int count; count++ is NOT atomic                           │
│   WHY: count++ is read-increment-write — three separate operations.         │
│   A thread can be preempted between read and write. Use AtomicInteger.      │
│                                                                              │
│ TRAP 4: newFixedThreadPool → OOM under sustained load                       │
│   WHY: Uses an unbounded LinkedBlockingQueue. Queue grows without limit.    │
│   Use ThreadPoolExecutor + ArrayBlockingQueue + CallerRunsPolicy.           │
│                                                                              │
│ TRAP 5: thenApply vs thenApplyAsync — thread is non-deterministic          │
│   WHY: thenApply runs on whatever thread completed the upstream stage.      │
│   Could be the caller's thread or a pool thread. Use thenApplyAsync        │
│   when you need predictable threading.                                       │
│                                                                              │
│ TRAP 6: synchronized blocks virtual threads (pinning)                       │
│   WHY: synchronized holds the carrier thread even when blocking on I/O.    │
│   The carrier can't be freed for other virtual threads. Use ReentrantLock.  │
│                                                                              │
│ TRAP 7: try-catch does NOT work around Future.get() for async exceptions   │
│   WHY: get() wraps exceptions in ExecutionException. You must unwrap:       │
│   catch (ExecutionException e) { Throwable cause = e.getCause(); }         │
│                                                                              │
│ TRAP 8: HashMap in a concurrent context → infinite loop (Java 7)           │
│   WHY: Concurrent resize creates a cycle in the bucket's linked list.      │
│   get() on that bucket spins forever. Use ConcurrentHashMap always.        │
│                                                                              │
│ TRAP 9: parallel stream uses ForkJoinPool.commonPool()                      │
│   WHY: Blocking inside a parallel stream starves the shared pool used by   │
│   all parallel streams and CompletableFuture in the same JVM.              │
│   Wrap in a custom ForkJoinPool or don't block in stream operations.       │
│                                                                              │
│ TRAP 10: ThreadLocal in thread pools leaks across requests                  │
│   WHY: Thread pool threads are reused. ThreadLocal set in request A        │
│   is still present when the thread handles request B. Call remove().       │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

*Chains A–I cover the complete Java interview question space from JVM fundamentals to modern concurrency. Each chain ends at the depth that distinguishes a senior engineer's answer.*

*← [Java Curriculum (J0–J9)](../../MASTER_INDEX.md) | [Kotlin Master Chains →](../../../Kotlin/Questions/master_chains.md)*
