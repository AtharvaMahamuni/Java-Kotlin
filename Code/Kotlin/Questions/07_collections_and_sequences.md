# Phase 7: Collections and Sequences

## Navigation
[← Phase 6 — Extension Functions](06_extension_functions.md) | [→ Phase 8 — Other Kotlin Features](08_other_kotlin_features.md)

## Questions in This File
- [Q7.1 — Kotlin's Collection Hierarchy](#q71--kotlins-collection-hierarchy)
- [Q7.2 — Sequences vs Eager Collections](#q72--sequences-vs-eager-collections)
- [Q7.3 — Common Collection Pitfalls](#q73--common-collection-pitfalls)
- [Q7.4 — HashMap Internals, Pre-sizing, and Map Null Safety](#q74--hashmap-internals-pre-sizing-and-map-null-safety)

---

## Q7.1 — Kotlin's Collection Hierarchy

> **Builds on:** [Q3.2 — Variance](03_generics_and_variance.md#q32--variance) · [Q3.1 — Type Erasure](03_generics_and_variance.md#q31--type-erasure) · [Q0.2 — JVM Type Mapping](phase0_jvm_mental_model_v3.md#q02--jvm-type-mapping)
> **Connects to:** [Q7.2 — Sequences](#q72--sequences-vs-eager-collections) · [Q7.3 — Pitfalls](#q73--common-collection-pitfalls)

---

### The Core Design — Derived From Variance

Kotlin separates read-only and mutable collection interfaces. This is not an arbitrary design choice — it falls out directly from variance rules.

**Why `List<out E>` can be covariant:**
`List` has no methods that accept `E` as input — you can only read `E` out (via `get()`). A `List<Dog>` can safely substitute for a `List<Animal>` — every element you read IS-AN `Animal`. No write path = no corruption opportunity = safe to mark `out E`.

**Why `MutableList<E>` must be invariant:**
`MutableList` has `add(element: E)`. `E` appears in an "in" position. If `MutableList<Dog>` were a subtype of `MutableList<Animal>`:

```kotlin
val dogs: MutableList<Dog> = mutableListOf(Dog("Rex"))
val animals: MutableList<Animal> = dogs  // if this compiled...
animals.add(Cat("Whiskers"))             // Cat added to a Dog list — type corruption
val rex: Dog = dogs[1]                   // ClassCastException at runtime
```

The write path forces invariance. This is the same logic as Java arrays being covariant but broken (`Dog[]` is a subtype of `Animal[]` → `ArrayStoreException` at runtime).

```
Iterable<out T>
      │
Collection<out E>                ← read-only, covariant
      │
 ┌────┴──────┐
List<out E>  Set<out E>          ← covariant: E only comes OUT via get()/iterator
 │               │
MutableList<E>  MutableSet<E>   ← invariant: add(E) puts E IN

Map<K, out V>                   ← read-only; K invariant (used in both get(K) and keys)
                                  V covariant (only comes OUT via get/values)
MutableMap<K, V>                ← both invariant

(All are Kotlin compile-time interfaces only — no JVM equivalents.
 Backed by java.util.* at runtime via type erasure.)
```

---

### Bytecode Reality — Kotlin Interfaces Are Compile-Time Only

The Kotlin collection interfaces (`kotlin.collections.List`, `kotlin.collections.MutableList`, etc.) **do not exist as separate JVM classes**. At the bytecode level, they are erased to their Java counterparts:

```
kotlin.collections.List<T>        → java.util.List<T>     (at JVM bytecode level)
kotlin.collections.MutableList<T> → java.util.List<T>     (SAME JVM type!)
kotlin.collections.Set<T>         → java.util.Set<T>
kotlin.collections.Map<K,V>       → java.util.Map<K,V>
```

The separation between `List` and `MutableList` is **purely a Kotlin compiler enforcement**. At runtime, both are `java.util.List`. This is why:
1. Java code can freely call `add()` on a Kotlin `List<T>` reference (Java sees `java.util.List`)
2. `list is MutableList` is always `true` for an `ArrayList`-backed list at runtime
3. Casting `list as MutableList<Int>` never throws — no class difference to detect

---

### Read-Only ≠ Immutable — The Critical Distinction

`List<T>` means **you cannot mutate through this reference**. It does NOT guarantee the underlying data never changes.

```kotlin
val mutableList = mutableListOf(1, 2, 3)
val readOnly: List<Int> = mutableList   // SAME underlying ArrayList object — no copy!

mutableList.add(4)
println(readOnly)  // [1, 2, 3, 4] — readOnly reflects the change!
```

At the bytecode level, there is no wrapper, no defensive copy, no `@Immutable` annotation. The `List` interface simply does not declare `add()`/`remove()` — the **Kotlin compiler** enforces this restriction at call sites. Java code bypasses it entirely:

```java
// In Java — compiles and runs fine, no exception:
((java.util.List<Integer>) kotlinReadOnlyList).add(99);
// Java sees java.util.List which does have add() — no guard exists
```

**How to get true immutability:**

```kotlin
// Option 1: defensive copy (new list, no shared reference)
val truly: List<Int> = mutableList.toList()
// now truly and mutableList are different ArrayList objects — mutations don't cross

// Option 2: kotlinx.collections.immutable (structural sharing, O(log n) operations)
val persistent: PersistentList<Int> = persistentListOf(1, 2, 3)
val updated = persistent.add(4)  // returns NEW list, persistent is unchanged
```

---

### Underlying Java Types — and WHY Each Choice Was Made

```kotlin
listOf(1, 2, 3)          → java.util.Arrays.asList(1, 2, 3)
mutableListOf(1, 2, 3)   → java.util.ArrayList
setOf(1, 2, 3)           → java.util.LinkedHashSet
mutableSetOf(1, 2, 3)    → java.util.LinkedHashSet
mapOf("a" to 1)          → java.util.LinkedHashMap
mutableMapOf("a" to 1)   → java.util.LinkedHashMap
```

**Why `listOf()` uses `Arrays.asList()` — not `ArrayList`:**

`Arrays.asList()` wraps a fixed-length Java array directly. The array is allocated once; no `ArrayList` resizing bookkeeping. Key behaviours:

```kotlin
val list = listOf(1, 2, 3)

(list as MutableList)[0] = 99    // set() — replaces element, array size unchanged → WORKS
(list as MutableList).add(4)     // add() — would grow the array → UnsupportedOperationException
(list as MutableList).remove(1)  // remove() — would shrink the array → UnsupportedOperationException
```

`Arrays.asList` is lighter than `ArrayList` — no capacity field, no modCount semantics for resizing (it still has modCount for structural change detection), no `ensureCapacity` logic.

**Why `setOf()` uses `LinkedHashSet` — not `HashSet`:**

`HashSet` gives non-deterministic iteration order — the order depends on hash bucket distribution, which can vary between JVM runs, JVM versions, and even between invocations as the hash seed changes. `LinkedHashSet` wraps a `HashMap` AND maintains a doubly-linked list connecting all entries in insertion order. This makes `setOf(1, 2, 3).toString()` always print `[1, 2, 3]` — deterministic, reproducible, debuggable. Kotlin chose predictability as the default.

**Why both `setOf()` and `mutableSetOf()` use `LinkedHashSet`:**

`mutableSetOf` could use plain `HashSet` (slightly faster, less memory). Kotlin chose consistent behaviour: both use `LinkedHashSet` so mutation doesn't surprise you with reordering.

---

### `emptyList()` — The Singleton

```kotlin
emptyList<String>() === emptyList<Int>()  // TRUE — same object
```

Why? Generic type parameters are erased at runtime — `emptyList<String>()` and `emptyList<Int>()` both call the same `CollectionsKt.emptyList()` function, which returns a single `EmptyList` object (a Kotlin `object` declaration):

```kotlin
// Kotlin stdlib (simplified):
internal object EmptyList : List<Nothing>, Serializable {
    override fun get(index: Int): Nothing = throw IndexOutOfBoundsException(index.toString())
    override val size: Int get() = 0
    // ... other overrides
}

fun <T> emptyList(): List<T> = EmptyList  // same object, cast at call site
```

**Decompiled Java:**
```java
// emptyList<String>() compiles to:
(List<String>) CollectionsKt.emptyList()  // cast at call site only, same singleton
```

Zero allocation. Always use `emptyList()` when the result is known to be empty — `listOf()` with no arguments also delegates to `emptyList()`.

---

### `IntArray` vs `Array<Int>` — Boxing Explained

**Why it matters:** wrong choice in a loop = 2.7× more memory + GC pressure.

```
           IntArray          Array<Int>
           ────────          ──────────
JVM type   int[]             Integer[]
Boxing?    NO                YES (always)
Layout     [1][2][3]         [ref][ref][ref]
                              ↓    ↓    ↓
                             (heap Integer objects)
```

**Quick rule:**
```
IntArray  → primitive int[]  → use for numeric data
Array<Int> → boxed Integer[] → avoid in tight loops
List<Int>  → ALWAYS boxes    → generics erase to Object,
                               no List<int> possible on JVM
```

```
IntArray   → JVM int[]     → raw primitives, contiguous memory, NO boxing
Array<Int> → JVM Integer[] → heap-allocated Integer wrapper objects, ALWAYS boxed
```

```kotlin
val prim: IntArray = intArrayOf(1, 2, 3)
// JVM bytecode: NEWARRAY T_INT 3
// Memory layout: [ arrayHeader | 1 | 2 | 3 ]   ← 12 bytes of data + ~16 bytes header

val boxed: Array<Int> = arrayOf(1, 2, 3)
// JVM bytecode: ANEWARRAY java/lang/Integer 3
// Memory layout: [ arrayHeader | ref1 | ref2 | ref3 ]   ← 3 references
//   + heap objects: Integer(1) at ref1, Integer(2) at ref2, Integer(3) at ref3
//   Each Integer object: ~16 bytes header + 4 bytes int field = ~20 bytes
// Total: ~76 bytes vs ~28 bytes — roughly 2.7× more memory
```

**Why `List<Int>` always boxes:**
Generics erase to `Object` at the JVM level. A `List<Int>` is `java.util.List<Object>` at runtime. A primitive `int` is not an `Object` — it must be auto-boxed to `Integer` to be stored in the list. There is no `java.util.List<int>` possible on the JVM.

**Decompiled Java for boxing:**
```java
List<Integer> list = new ArrayList<>();
list.add(Integer.valueOf(42));   // explicit boxing — Integer.valueOf(42) call
int x = list.get(0).intValue();  // explicit unboxing — .intValue() call
// Each add/get is two method calls — overhead per element
```

For numeric processing in tight loops: always use `IntArray`, `LongArray`, `DoubleArray`, `FloatArray`. These map to `int[]`, `long[]`, `double[]`, `float[]` — no boxing, cache-friendly contiguous memory.

---

### ## Trap: `listOf()` with One Element Uses a Different Implementation

```kotlin
listOf("single")   // → SingletonList (java.util.Collections.singletonList)
listOf()           // → EmptyList singleton
listOf(1, 2, 3)    // → Arrays.asList(1, 2, 3)
```

`Collections.singletonList` is an even lighter wrapper than `Arrays.asList` — it holds a single reference field with no array allocation. An interviewer probing `listOf()` internals may expect this distinction.

---

### Memory Trick

```
READ-ONLY ≠ IMMUTABLE.
  List<T> = "no add/set through THIS reference" — Kotlin compiler enforcement only.
  At JVM level: kotlin.collections.List == java.util.List (same bytecode type).
  Java casts and mutates freely — no runtime guard.
  Same ArrayList object behind List and MutableList references.
  True immutability: .toList() copy or kotlinx PersistentList.

List<out E>     = covariant  (E only OUT → safe to widen to List<Animal>)
MutableList<E>  = invariant  (add(E) is an IN position → widening corrupts)
Map<K, out V>   = K invariant (used as key — both in/out), V covariant (only out)

listOf()   → Arrays.asList (fixed array — add/remove throw UOE, set works)
           → listOf(one) → Collections.singletonList (even lighter)
           → listOf()    → EmptyList singleton
setOf()    → LinkedHashSet (insertion ORDER preserved — not HashSet!)
mapOf()    → LinkedHashMap (insertion order)
emptyList() → EmptyList singleton (type erasure → same object for all type params)

IntArray   → int[]    → 0 boxing → fast for numeric loops
Array<Int> → Integer[] → boxing → ~2.7× more memory per element
List<Int>  → always boxes (generics erase to Object — no List<int> on JVM)
```

### Self-Test

1. Derive why `MutableList<Dog>` is NOT a subtype of `MutableList<Animal>`. Show the code that would cause a `ClassCastException` if it were.
2. `val view: List<Int> = mutableList` — does `view` see new elements added via `mutableList`? Why, at the bytecode level?
3. *"At runtime, is `kotlin.collections.List<T>` a different JVM class from `kotlin.collections.MutableList<T>`?"* — Answer and explain the implication for Java interop.
4. `listOf()` uses `Arrays.asList()`. What does that mean for `add()`? For `set()`? Why that choice over `ArrayList`?
5. `emptyList<String>() === emptyList<Int>()` — true or false? Derive the answer from type erasure and show the decompiled Java.
6. `IntArray` vs `Array<Int>` — JVM types? Memory layout? Why does `List<Int>` always box?

---

## Q7.2 — Sequences vs Eager Collections

> **Builds on:** [Q4.1 — lambda allocation](04_functions_lambdas_inlining.md#q41--lambda-compilation) · [Q4.2 — inline](04_functions_lambdas_inlining.md#q42--inline-noinline-crossinline)
> **Connects to:** [Q7.3 — Pitfalls](#q73--common-collection-pitfalls) · [Q11.1 — Flow (async counterpart to Sequence)](11_flow.md#q111--cold-vs-hot-streams)

---

### Eager vs Lazy — The Core Difference

**Eager (collection chain):** Every operator produces a **complete intermediate collection** before the next operator starts. All elements are processed up-front.

**Lazy (sequence chain):** One element travels the full pipeline from source to terminal before the next element is touched. The terminal operator drives evaluation.

```kotlin
val list = listOf(1, 2, 3, 4, 5, 6, 7, 8, 9, 10)

// EAGER — 3 intermediate lists created:
val result = list
    .filter { it % 2 == 0 }    // → new ArrayList [2,4,6,8,10]       ← alloc #1
    .map { it * it }            // → new ArrayList [4,16,36,64,100]   ← alloc #2
    .take(3)                    // → new ArrayList [4,16,36]          ← alloc #3
// Ops: 10 filter + 5 map + 5 take-checks = 20 ops, 2 wasted map calls

// LAZY — 0 intermediate lists:
val result2 = list.asSequence()
    .filter { it % 2 == 0 }    // no list — wraps source in FilteringSequence
    .map { it * it }            // no list — wraps filter in TransformingSequence
    .take(3)                    // TERMINAL — drives evaluation
    .toList()
//
// Pull 1 → filter(1%2==0? NO) → skip
// Pull 2 → filter(YES) → map(4) → take(count=1)
// Pull 3 → filter(NO) → skip
// Pull 4 → filter(YES) → map(16) → take(count=2)
// Pull 5 → filter(NO) → skip
// Pull 6 → filter(YES) → map(36) → take(count=3) → DONE. Elements 7–10 never touched.
// Ops: 6 filter + 3 map = 9 ops. No intermediate lists.
```

---

### The Iterator Decorator Chain — Internal Mechanism

A `Sequence` is a chain of **decorated iterators**. Each operator returns a new `Sequence` object wrapping the previous one. Nothing executes until a terminal operator calls `.iterator().next()`.

```
list.asSequence()
  → SequenceImpl                       (wraps ArrayList.iterator())
      .filter { it % 2 == 0 }
  → FilteringSequence                  (wraps SequenceImpl, holds predicate)
      .map { it * it }
  → TransformingSequence               (wraps FilteringSequence, holds transform fn)
      .take(3)
  → TakeSequence                       (wraps TransformingSequence, holds n=3)
      .toList()                        ← TERMINAL: calls TakeSequence.iterator()

One call to TakeSequence.iterator().hasNext()/next():
  → calls TransformingSequence.iterator().next()
      → calls FilteringSequence.iterator().next()
          → calls source.iterator().next() → gets 1
          → predicate(1) = false → source.next() → gets 2
          → predicate(2) = true → returns 2 upstream
      → transform(2) = 4 → returns 4 upstream
  → TakeSequence records element 1 of 3, emits 4 to toList()
```

Each element traversal = multiple virtual method calls through the decorator stack. This is the per-element overhead that makes sequences slower for small collections.

---

### ## Trap: Stateful Operators Break Laziness — Must Buffer ALL

Some operators must see **all** elements before they can emit any output. They force full materialisation of the stream.

```kotlin
// WRONG expectation: "sequence makes this lazy"
(1..1_000_000).asSequence()
    .filter { it % 2 == 0 }
    .sorted()              // ← STATEFUL: must see ALL 500,000 filtered elements
                           //   to determine the sorted order. Buffers everything.
    .take(5)               // ← too late — sorted() already consumed the stream
    .toList()
// Performance: identical to eager sorted(). Sequence gained nothing.
```

**Stateful operators — break laziness (must buffer ALL elements):**
`sorted()`, `sortedBy()`, `sortedWith()`, `distinct()`, `distinctBy()`, `groupBy()`, `chunked()`, `windowed()`

**Stateless operators — remain lazy (only need current element):**
`filter()`, `map()`, `flatMap()`, `take()`, `drop()`, `takeWhile()`, `dropWhile()`, `onEach()`

```
Why sorted() is stateful:
  To output the minimum element, sorted() must have seen ALL elements.
  (What if the last element is the smallest?)
  → must buffer entire stream first.

Why filter() is stateless:
  Decision for element N depends only on element N itself.
  → no buffering needed, truly lazy.
```

---

### When Sequences Are SLOWER Than Eager

Each sequence operator = one additional wrapper object + virtual dispatch per element per operator:

```
Eager (10 elements, filter + map):
  filter:  10 comparisons → new ArrayList (≤10 elements, ~40 bytes)
  map:     ≤10 transforms → new ArrayList (≤10 elements, ~40 bytes)
  Total: ~20 operations + 2 small ArrayList allocations

Sequence (10 elements, filter + map):
  Per element: FilteringSequence.next() [virtual call]
               → source.next()         [virtual call]
               → predicate check
               → TransformingSequence wraps result [virtual call]
               → transform fn call
  = 4–5 virtual calls per element → ~50 virtual calls total
  + 2 wrapper objects (FilteringSequence, TransformingSequence)

Winner for 10 elements: EAGER (2 allocations, ~20 ops vs ~50 virtual calls)
Winner for 1,000,000 elements + take(5): SEQUENCE (processes ~10 elements, not 1M)
```

```
Use Sequence when:
  ✓ Large data (> ~100 elements) with 3+ operators
  ✓ Early termination (take, first, find, any) — stops after what it needs
  ✓ Potentially infinite data (generateSequence, sequence { yield() })
  ✓ Memory-constrained (no intermediate lists allocated)

Use Eager when:
  ✓ Small data (< ~20 elements) — virtual dispatch overhead outweighs list cost
  ✓ Single operator — no intermediate list to save anyway
  ✓ Stateful operations dominate (sorted, distinct) — laziness broken regardless
```

---

### `generateSequence` — Potentially Infinite

```kotlin
// Infinite — early termination required:
val naturals = generateSequence(1) { it + 1 }
naturals.take(10).toList()     // [1, 2, 3, ..., 10] — evaluates exactly 10 elements

// Fibonacci via Pair state:
val fibs = generateSequence(Pair(0, 1)) { (a, b) -> Pair(b, a + b) }
    .map { it.first }
fibs.take(8).toList()          // [0, 1, 1, 2, 3, 5, 8, 13]

// Finite — null terminates:
val lines = generateSequence { readLine() }  // null return → sequence ends
lines.toList()                               // reads until EOF
```

Pattern: `generateSequence(seed) { prev -> nextValue or null }`.
Seed = first element. Lambda = next element given previous, or `null` to terminate.

---

### Sequence vs Flow — Why They Are NOT the Same

| | `Sequence<T>` | `Flow<T>` |
|---|---|---|
| Execution | Synchronous, blocking | Asynchronous, suspending |
| Call `delay()` / network inside? | ❌ blocks calling thread | ✅ suspends, thread freed |
| Thread model | Caller's thread, single-threaded | Any dispatcher |
| Backpressure | Built-in (pull model — consumer drives) | Via `buffer()`, `conflate()` |
| Cold/Hot | Always cold | Cold (Flow) or Hot (SharedFlow/StateFlow) |

`Flow` is NOT "async Sequence." The critical difference: a Flow producer can **suspend** between emissions — a network call inside `emit()` does not block any thread. The same operation inside a `Sequence` block freezes the calling thread for the full duration. See [Q11.1](11_flow.md#q111--cold-vs-hot-streams).

---

### Memory Trick

```
EAGER: each operator = function(ALL elements) → NEW intermediate collection
  3 operators on 1000 elements = 3 allocations, all 1000 elements processed at each step

LAZY (Sequence): each operator = lightweight wrapper object around an iterator
  Terminal (toList, first, sum) drives the pull — element by element
  Element travels FULL PIPELINE before next element starts

## Trap: STATEFUL OPERATORS BREAK LAZINESS
  sorted(), distinct(), groupBy(), chunked(), windowed()
  Must buffer ALL elements before emitting ANY → full materialisation
  .asSequence().sorted() = identical cost to .sorted() (eager)

SEQUENCE IS SLOWER for small collections:
  Virtual dispatch per element per operator > cost of small list allocation
  Rule of thumb: >100 elements + 3+ operators + early termination → Sequence

generateSequence(seed) { prev -> next or null }
  Infinite until terminal stops pulling or lambda returns null.

Sequence = pull, synchronous, blocks thread
Flow     = pull, asynchronous, suspends → producer can do I/O without blocking thread
```

### Self-Test

1. `list.filter { }.map { }.first()` — eager: how many intermediate list allocations? With `.asSequence()`? How many elements does `.first()` evaluate with a sequence?
2. Draw the decorator chain for `.asSequence().filter { }.map { }.take(3)`. What drives execution?
3. Why is `(1..1_000_000).asSequence().sorted().first()` NOT faster than eager? What does `sorted()` do to the stream?
4. When is a `Sequence` SLOWER than eager collection operators? Give the concrete mechanism.
5. What is a terminal operator? Name four. What happens if you forget the terminal — what is the return type?
6. One-sentence mechanical difference between `Sequence<T>` and `Flow<T>`.

---

## Q7.3 — Common Collection Pitfalls

> **Builds on:** [Q7.1 — Collection Hierarchy](#q71--kotlins-collection-hierarchy) · [Q7.2 — Sequences](#q72--sequences-vs-eager-collections)
> **Connects to:** [Q10.6 — Mutex for thread-safe caching](10_structured_concurrency.md#q106--mutex-and-synchronization-primitives) · [Q14.4 — Thread-Safe Caching](14_jetpack_components.md#q144--thread-safe-caching)

---

### `ConcurrentModificationException` — Fail-Fast Iterators

Java's `ArrayList` (and most `java.util` collections) uses a **fail-fast** strategy: the iterator throws immediately when it detects a structural modification that wasn't made through itself.

**The mechanism — `modCount` in `AbstractList`:**

```java
// AbstractList (Java source — parent of ArrayList):
protected transient int modCount = 0;

// STRUCTURAL operations (change size): add, remove, clear, addAll, removeAll
//   → modCount++  (each call increments by 1)

// NON-STRUCTURAL operations (replace element, don't change size): set()
//   → modCount NOT incremented — safe during iteration

// When iterator.iterator() is called:
int expectedModCount = modCount;  // snapshot taken here

// Inside iterator.next() — checked BEFORE every element:
if (modCount != expectedModCount)
    throw new ConcurrentModificationException();
// "Fail-fast" = crash immediately with a clear error, not silently skip/duplicate elements
```

```kotlin
// WRONG: structural modification during iteration
val list = mutableListOf(1, 2, 3, 4, 5)
for (item in list) {
    if (item == 3) list.remove(item)
    // remove() → modCount++ → next call to iterator.next() detects change → CME
}
```

**Three safe patterns:**

```kotlin
// 1. removeIf — internal iteration, no external iterator exposed:
list.removeIf { it == 3 }

// 2. MutableIterator.remove() — the iterator removes through itself, updates expectedModCount:
val iter = list.iterator()
while (iter.hasNext()) {
    if (iter.next() == 3) iter.remove()  // safe: iterator's own modCount tracking
}

// 3. Filter to a new list — never mutates original:
val filtered = list.filter { it != 3 }
```

---

### ## Trap: `set()` Does NOT Throw CME — But Looks Like It Should

A common interview follow-up: *"Does calling `list[0] = 99` during iteration throw `ConcurrentModificationException`?"*

```kotlin
val list = mutableListOf(1, 2, 3, 4, 5)
for (item in list) {
    if (item == 3) list[2] = 99  // set() — replaces element, does NOT change size
    // set() does NOT increment modCount → CME is NOT thrown
    // list iteration continues normally
}
// list is now [1, 2, 99, 4, 5] — mutation happened, no exception
```

`set()` changes an element's value but not the list's structure (size). `modCount` is not incremented. The iterator continues without error. This can produce confusing results (visiting the old or new value depending on iteration position) — but no exception.

---

### `groupBy` vs `groupingBy`

```kotlin
// groupBy — EAGER: creates entire Map<K, List<V>> immediately
val grouped: Map<Int, List<String>> = words.groupBy { it.length }
// For 1M words: builds one List<String> per distinct length
// ALL 1M strings are held in those lists simultaneously in memory
// To count: .mapValues { it.value.size } iterates all lists again — 2nd pass

// groupingBy — LAZY RECIPE: returns Grouping<T, K> (no data yet)
val counts: Map<Int, Int> = words
    .groupingBy { it.length }
    .eachCount()
// Single pass through source elements
// Maintains ONLY Map<Int, Int> (counts) — never builds List<String> groups
// Peak memory: source stream + tiny count map
```

```
groupBy  on 1M strings by length:
  Memory peak: ~1M String references across all grouped lists
  → Map<Int, List<String>> with total 1M elements across all lists

groupingBy.eachCount() on 1M strings:
  Memory peak: source stream (1 String reference at a time) + Map<Int, Int> (tiny)
  → Map<Int, Int> with ~40 entries (distinct word lengths)
```

Available `groupingBy` terminal operations: `eachCount()`, `fold(initial) { acc, e -> }`, `reduce { key, acc, e -> }`, `aggregate { key, acc?, e, first -> }`.

Use `groupBy` when you need the actual grouped elements. Use `groupingBy` when you only need an aggregate — one pass, no intermediate lists.

---

### `getOrPut` — Convenient But NOT Atomic

```kotlin
val cache = mutableMapOf<String, List<User>>()
val users = cache.getOrPut("alice") { fetchUsers("alice") }  // looks atomic — is NOT
```

**The race condition — `getOrPut` is two operations:**

`getOrPut` compiles to: check if key exists → if not, compute value → insert. These three steps are NOT protected by any lock. Between the check and the insert, another thread can do the same check.

```
Thread 1: cache.containsKey("alice") → false
                                                Thread 2: cache.containsKey("alice") → false
Thread 1: fetchUsers("alice") → List(...)       ← DUPLICATE WORK
                                                Thread 2: fetchUsers("alice") → List(...)
Thread 1: cache["alice"] = result1
                                                Thread 2: cache["alice"] = result2  ← overwrites
```

Both threads do redundant work, and the final cached value is indeterminate.

```kotlin
// Thread-safe atomic compute:
val cache = ConcurrentHashMap<String, List<User>>()
val users = cache.computeIfAbsent("alice") { fetchUsers("alice") }
// JVM spec: computeIfAbsent holds a per-bucket lock
// Lambda runs at most once per key even under concurrent access
```

| | Thread-safe reads? | Lambda runs once? |
|---|---|---|
| `MutableMap.getOrPut` | ✗ (no thread safety) | ✗ |
| `ConcurrentHashMap.getOrPut` (Kotlin ext) | ✓ | ✗ (not atomic check+insert) |
| `ConcurrentHashMap.computeIfAbsent` | ✓ | ✓ (JVM spec guarantee) |

---

### ## Trap: `getOrPut` in Coroutines Is Equally Unsafe

```kotlin
// WRONG: coroutines on IO pool can interleave just like threads
val cache = mutableMapOf<String, Data>()
suspend fun getData(key: String) = withContext(Dispatchers.IO) {
    cache.getOrPut(key) { fetchData(key) }
    // Two coroutines can both reach the containsKey check before either inserts
}

// Fix option 1: ConcurrentHashMap.computeIfAbsent
val cache = ConcurrentHashMap<String, Data>()
cache.computeIfAbsent(key) { fetchData(key) }  // atomic per JVM

// Fix option 2: Mutex for suspend-aware serialisation
val mutex = Mutex()
val cache = mutableMapOf<String, Data>()
suspend fun getData(key: String): Data = mutex.withLock {
    cache.getOrPut(key) { fetchData(key) }
    // Only one coroutine in this block at a time — no race
}
```

---

### `LinkedHashMap(accessOrder = true)` — LRU Cache Foundation

`LinkedHashMap` maintains a **doubly-linked list** connecting all entries in insertion order (by default). The constructor's `accessOrder` parameter changes the ordering semantics:

- `accessOrder = false` (default): iteration follows insertion order
- `accessOrder = true`: every `get()` or `put()` **moves the accessed entry to the tail** — tail = most recently used, head = least recently used

```
Internal state with accessOrder=true (3 entries):
  HEAD (LRU = evict first)               TAIL (MRU = accessed last)
  [entry "b" | prev=null | next→"c"] ←→ [entry "c" | prev←"b" | next→"a"] ←→ [entry "a" | prev←"c" | next=null]
```

```kotlin
class LruCache<K, V>(private val maxSize: Int) : LinkedHashMap<K, V>(16, 0.75f, true) {
    // removeEldestEntry called after EVERY put()
    // eldest = HEAD entry = least-recently-used = eviction candidate
    override fun removeEldestEntry(eldest: Map.Entry<K, V>): Boolean {
        return size > maxSize  // true → framework auto-removes HEAD entry
    }
}

val cache = LruCache<String, Bitmap>(3)
cache["a"] = bitmapA           // list: [a]
cache["b"] = bitmapB           // list: [a → b]
cache["c"] = bitmapC           // list: [a → b → c]
cache.get("a")                 // get("a") → moves a to TAIL: [b → c → a]
cache["d"] = bitmapD           // put triggers removeEldestEntry: size(4) > 3
                               // eldest = HEAD = "b" → removed: [c → a → d]
println(cache.keys)            // [c, a, d]
```

`android.util.LruCache` uses exactly this `LinkedHashMap(accessOrder=true) + removeEldestEntry` pattern internally.

---

### Memory Trick

```
ConcurrentModificationException = fail-fast modCount sentinel in AbstractList.
  modCount++ on: add, remove, clear, addAll, removeAll  (structural — size changes)
  modCount NOT touched on: set()                         (non-structural — value replaces)
  Iterator.next() checks: modCount != expectedModCount → throws immediately.
  Safe removal: removeIf { }, iter.remove(), or filter to new list.

## Trap: set() during iteration = NO CME (modCount not incremented).
  Looks dangerous but works — element replaced in place, size unchanged.

groupBy    → EAGER → Map<K, List<V>> — all 1M strings in memory simultaneously
groupingBy → RECIPE (Grouping<T,K>) → terminal (eachCount/fold) = one pass, tiny map
  Use groupingBy for count/sum/reduce. Use groupBy only if you need the element lists.

getOrPut = NOT ATOMIC. Two operations: check + insert = race window.
  Fix: ConcurrentHashMap.computeIfAbsent (JVM atomic per-bucket lock).
  Also unsafe in coroutines (IO pool interleaving). Fix: Mutex.withLock.

LinkedHashMap(accessOrder=true):
  Doubly-linked list. Every get/put moves entry to TAIL (MRU position).
  HEAD = LRU = eldest = eviction candidate.
  removeEldestEntry(eldest) returns size > maxSize → framework removes HEAD.
  = LRU cache in ~5 lines. android.util.LruCache uses this exact pattern.
```

### Key Takeaways — Q7.3

| Pitfall | Root cause | Fix |
|---|---|---|
| `ConcurrentModificationException` | `modCount` check in `iterator.next()` | `removeIf`, `iter.remove()`, or filter-copy |
| `set()` during iteration | `set()` doesn't touch `modCount` | Allowed — but produces confusing results |
| `groupBy` memory | Builds all element lists eagerly | `groupingBy + eachCount()` for aggregates |
| `getOrPut` race | Check + insert are two separate operations | `ConcurrentHashMap.computeIfAbsent` |
| LRU eviction | Need access-order doubly-linked list | `LinkedHashMap(accessOrder=true)` + `removeEldestEntry` |

### Self-Test

1. What is `modCount`? Which operations increment it? Which don't? Why is `set()` treated differently?
2. Three safe ways to remove elements during iteration — write each pattern.
3. `groupBy` vs `groupingBy` on 1M strings grouped by length — what is the peak memory difference?
4. Show with a thread-interleaving diagram why `getOrPut` is not atomic. What JVM method is atomic?
5. `LinkedHashMap(accessOrder=true)` — what happens to the internal linked list when you call `get("a")`? Draw the before/after state.
6. *"Is `set()` during a for-each loop over an `ArrayList` safe or does it throw CME?"* — Answer and explain why.

---

## Q7.4 — HashMap Internals, Pre-sizing, and Map Null Safety

> **Builds on:** [Q7.1 — Collection Hierarchy](#q71--kotlins-collection-hierarchy) · [Q0.1 — JVM Primitives](00_jvm_mental_model.md)
> **Connects to:** [Q7.3 — getOrPut / LRU](#q73--common-collection-pitfalls)

---

### WHY This Matters

HashMap is used everywhere — caches, frequency counts, graph adjacency lists. Understanding bucket internals explains O(1) average vs worst-case, why pre-sizing matters, and why `map[key]` returns nullable.

---

### Interface vs Implementation — Design Pattern

Kotlin/Java collections separate **what** from **how**:

```
Interface       Implementation
─────────       ──────────────
Map<K,V>    →   HashMap         (unordered, O(1))
            →   LinkedHashMap   (insertion order, O(1))
            →   TreeMap         (sorted by key, O(log n))

Set<E>      →   HashSet         (unordered, O(1))
            →   LinkedHashSet   (insertion order, O(1))
            →   TreeSet         (sorted, O(log n))
```

**Always type your variable to the interface:**
```kotlin
val map: Map<Int, String> = HashMap()   // ✓ program to interface
val map: HashMap<Int, String> = HashMap() // ✗ locks in implementation
```

---

### HashMap Internals — Bucket Chain

```
hash(key) → bucket index → linked chain (or tree if long)

Buckets:
  [0] → null
  [1] → Node(k1,v1) → Node(k5,v5) → null   ← collision chain
  [2] → Node(k2,v2) → null
  [3] → null
  [4] → Node(k4,v4) → null
```

```
lookup(key):
  1. hash(key) → bucket index         O(1)
  2. walk chain, equals() check        O(1) avg, O(n) worst
  insert/delete: same structure        O(1) avg
```

**Collision note:** Java 8+ converts chains > 8 nodes into a **red-black tree** (O(log n) worst case), balancing memory vs speed automatically.

---

### Pre-sizing — Avoid Rehash

Hash tables have a **load factor** (default 0.75). When `size > capacity × 0.75`:
```
resize → new array (2× size) → rehash ALL entries → O(n)
```

If you know the input size, pre-size to avoid multiple resizes:
```kotlin
// BAD: starts at capacity 16, rehashes at 12, 24, 48...
val map = HashMap<Int, Int>()

// GOOD: single allocation, no rehash
val map = HashMap<Int, Int>(nums.size)
val set = HashSet<Int>(nums.size)
```

**Formula:** `initialCapacity = expectedSize / 0.75 + 1`
(Kotlin/Java helper: `HashMap(expectedSize * 4 / 3 + 1)` is precise)

---

### LinkedHashMap vs TreeMap — When to Use Each

```
HashMap        → fastest, no order needed
LinkedHashMap  → need insertion order (default setOf/mapOf in Kotlin)
TreeMap        → need sorted keys (range queries, floor/ceiling)
```

```kotlin
val freq = TreeMap<Char, Int>()
freq.floorKey('m')    // largest key ≤ 'm' — O(log n)
freq.ceilingKey('m')  // smallest key ≥ 'm' — O(log n)
freq.subMap('a','f')  // range slice — NavigableMap API
```

---

### Map Null Safety — `map[key]` Returns `V?`

`map[key]` returns `V?` because the key might not exist.

```kotlin
val map = mapOf(1 to "a", 2 to "b")

val v = map[3]          // → null (V? = String?)
val v = map[1]!!        // → "a" but crashes if key absent — avoid

// Safe patterns:
val v = map[key] ?: "default"           // elvis — default on miss
val v = map.getOrDefault(key, "n/a")    // explicit default
val v = map.getOrElse(key) { compute(key) }  // lazy default

// Check before use:
if (key in map) {
    val v = map[key]!!   // safe here — key confirmed present
}
```

**## Trap: two-argument `get` doesn't exist** — `map.get(key, default)` is NOT valid Kotlin. Use `getOrDefault`.

---

### Choosing the Right Collection — Decision Tree

```
Need ordered?
├── No  → HashMap / HashSet        (O(1), less memory)
├── Insertion order → LinkedHashMap / LinkedHashSet
└── Sorted order   → TreeMap / TreeSet   (O(log n))

Large numeric data?
├── Yes → IntArray / LongArray / DoubleArray  (no boxing)
└── No  → List<Int> is fine

Know size upfront?
└── Yes → HashMap(size) / HashSet(size)  (avoid rehash)
```

---

### Memory Trick

```
HashMap internals:
  hash(key) → bucket → chain → O(1) avg, O(n) worst
  chain → tree (> 8 nodes) → O(log n) worst — Java 8+ auto
  resize at 75% capacity → O(n) rehash all entries
  pre-size: HashMap(n) avoids multiple rehashes for known n

Interface types:
  Map/Set/List = interfaces (no storage)
  HashMap/TreeMap = implementations (storage)
  Always declare as interface type for flexibility

map[key] = V?  (not V — key may be absent)
  ?: "default"         — safe
  getOrDefault(k, v)   — safe
  !!                   — throws if absent, avoid

Sorted? → TreeMap/TreeSet O(log n)
Order?  → LinkedHashMap/LinkedHashSet (Kotlin default for setOf/mapOf)
Fast?   → HashMap/HashSet O(1)
Nums?   → IntArray (no boxing) > List<Int> (always boxes)
```

### Self-Test

1. Draw the internal structure of a `HashMap` with 5 entries. Where do collisions go? What happens when a chain exceeds 8 nodes (Java 8+)?
2. `HashMap<Int,Int>` for 10,000 entries — how many resizes with default capacity? How do you avoid them?
3. `map[key]` — what type does it return and why? Write three safe access patterns.
4. You need to iterate map entries in sorted-key order. Which implementation? What's the lookup cost?
5. `setOf(1,2,3)` — which Java class backs it? Why NOT `HashSet`?
6. You have `nums: IntArray` — should you convert it to `List<Int>` for frequency counting? What's the cost?

---

## Master Summary: Collections and Sequences

```
1. HIERARCHY
   List<out E>     = covariant = read-only (E only OUT — no add/set)
   MutableList<E>  = invariant = read-write (add(E) is IN position — widening corrupts)
   kotlin.collections.List == java.util.List at JVM bytecode level (type erased)
   READ-ONLY ≠ IMMUTABLE: same object, Java casts and mutates freely, no runtime guard
   listOf()    → Arrays.asList (fixed array: add throws UOE, set works)
               → listOf(x)    → Collections.singletonList
               → listOf()     → EmptyList singleton
   setOf()    → LinkedHashSet (insertion order — NOT HashSet, for determinism)
   emptyList() → EmptyList singleton (type erasure → same object for all type params)
   IntArray   → int[] (no boxing)   Array<Int> → Integer[] (~2.7× more memory)
   List<Int>  → always boxes (generics erase to Object)

2. SEQUENCES
   Lazy decorator chain of wrapped iterators. Terminal drives pull (element by element).
   STATEFUL operators (sorted, distinct, chunked) break laziness — buffer ALL elements.
   SLOWER for small collections: virtual dispatch per element per operator.
   generateSequence(seed) { prev → next or null } — infinite until null or terminal stops.
   Sequence = pull, synchronous, blocks thread.
   Flow = pull, asynchronous, suspends → producer can do network/I/O without blocking.

3. PITFALLS
   CME      = modCount fail-fast: set() safe, add/remove throw; fix with removeIf/iter.remove
   groupBy  = eager lists (all elements in memory); groupingBy = one-pass aggregate
   getOrPut = NOT atomic (check + insert = two ops); fix: ConcurrentHashMap.computeIfAbsent
   LinkedHashMap(accessOrder=true) + removeEldestEntry = LRU cache (android.util.LruCache pattern)

4. HASHMAP INTERNALS + PRE-SIZING + NULL SAFETY
   hash(key) → bucket → chain (→ tree if >8 nodes, Java 8+) = O(1) avg
   resize at 75% capacity → O(n) rehash; pre-size: HashMap(n) avoids repeated resizes
   Interface types: Map/Set/List (declare as) vs HashMap/TreeMap (implement with)
   Sorted keys → TreeMap O(log n); insertion order → LinkedHashMap; fast → HashMap O(1)
   map[key] = V? (nullable — key may be absent); use ?: or getOrDefault, avoid !!
   Numeric arrays: IntArray → int[] (no boxing); List<Int> → always boxes (generics erase to Object)
```

---

*← [Phase 6 — Extension Functions](06_extension_functions.md) | [Phase 8 — Other Kotlin Features →](08_other_kotlin_features.md)*