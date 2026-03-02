# Phase 7: Collections and Sequences

## Navigation
[← Master Index](master_chains.md)

## Questions in This File
- [Q7.1 — Kotlin's Collection Hierarchy](#q71--kotlins-collection-hierarchy)
- [Q7.2 — Sequences vs Eager Collections](#q72--sequences-vs-eager-collections)
- [Q7.3 — Common Collection Pitfalls](#q73--common-collection-pitfalls)

---

## Q7.1 — Kotlin's Collection Hierarchy

> **Builds on:** [Q3.2 — Variance](03_generics_and_variance.md#q32--variance) · [Q0.2 — JVM Type Mapping](00_jvm_mental_model.md#q02--jvm-type-mapping)
> **Reference:** [Kotlin Docs — Collections Overview](https://kotlinlang.org/docs/collections-overview.html)

### The Concrete Picture

Four types that look related but behave very differently:

```kotlin
val list: List<Int>          // read-only interface — no add/remove via this reference
val mutableList: MutableList<Int>  // mutable — has add/remove/set

val ro: List<Int> = mutableList   // SAME underlying object!
mutableList.add(99)
ro.size  // includes 99! Read-only ≠ immutable.
```

The hierarchy:
```
List<out E>         ← covariant (out): List<Dog> IS-A List<Animal>
MutableList<E>      ← invariant: MutableList<Dog> is NOT MutableList<Animal>
```

Why the difference? List only reads (`get()`). MutableList reads AND writes (`add()`).
Adding a `Cat` to a `Dog` list = type corruption → must be invariant.

### First Principles: Read-Only vs Immutable

Before diving in, a crucial distinction:

**Read-only ≠ Immutable.** Kotlin's `List` is **read-only** — you can't call `add()` or `remove()`. But the underlying data CAN change if someone else holds a `MutableList` reference to the same list.

```kotlin
val mutableList = mutableListOf(1, 2, 3)
val readOnly: List<Int> = mutableList   // same underlying object!

mutableList.add(4)
println(readOnly)  // [1, 2, 3, 4] — it changed! Not truly immutable.
```

**Truly immutable** = the data never changes, period. Kotlin's read-only collections don't guarantee this.

### The Collection Hierarchy

```
kotlin.collections
                    Iterable<out T>
                          │
                     Collection<out E>   ← read-only, covariant (out E)
                     /           \
               List<out E>      Set<out E>
               MutableList<E>   MutableSet<E>  ← mutable, INVARIANT (no out!)

                     Map<K, out V>         ← read-only, values covariant
                     MutableMap<K, V>      ← mutable, invariant

               (All backed by java.util.* at runtime)
```

### Why `List` is Covariant (`out E`) but `MutableList` is Not

[`List<out E>`](03_generics_and_variance.md#q32--variance) — [covariant](03_generics_and_variance.md#q32--variance) because `List` only has read operations:
```kotlin
interface List<out E> {
    fun get(index: Int): E    // E in OUT position — returns E, never stores it
    val size: Int
    // NO add(), remove(), set() — can't corrupt the list
}
```

Because `List<Dog>` can only READ elements and every `Dog` IS-AN `Animal`, reading from `List<Dog>` and using it as `List<Animal>` is safe.

```kotlin
val dogs: List<Dog> = listOf(Dog("Rex"), Dog("Spot"))
val animals: List<Animal> = dogs  // ✓ SAFE: List is covariant
```

**`MutableList<E>`** — invariant because it has write operations:
```kotlin
interface MutableList<E> : List<E> {
    fun add(element: E)   // E in IN position — accepts E, can corrupt type
    fun set(index: Int, element: E)
}
```

If `MutableList<Dog>` were a subtype of `MutableList<Animal>`:
```kotlin
val dogs: MutableList<Dog> = mutableListOf(Dog("Rex"))
val animals: MutableList<Animal> = dogs  // if this were allowed...
animals.add(Cat("Whiskers"))  // adding Cat to a Dog list → type corruption!
```

### `Array<Int>` vs `IntArray` — When Each Boxes

```kotlin
// IntArray = JVM int[] — primitive array, NO boxing
val primitiveArr: IntArray = IntArray(5) { it }
// JVM: int[] { 0, 1, 2, 3, 4 } — each element is 4 bytes, direct value

// Array<Int> = JVM Integer[] — object array, ALWAYS boxes
val boxedArr: Array<Int> = Array(5) { it }
// JVM: Integer[] { Integer(0), Integer(1), ... } — each element is a 16-byte heap object + reference
```

```
Memory layout for [1, 2, 3]:

IntArray:   [1][2][3]           4 bytes each = 12 bytes + header
             ↑ value stored directly

Array<Int>: [ref1][ref2][ref3]  4 bytes each (references) = 12 bytes + header
             ↑ points to       + heap: Integer(1), Integer(2), Integer(3)
               heap objects      16 bytes each = 48 bytes

Total:       ~16 bytes           ~60 bytes — 3.75× more memory!
```

**Rule:** For numeric arrays in performance-critical code (game loops, image processing, audio), always use `IntArray`, `FloatArray`, `LongArray` — never `Array<Int>` (see [Q0.2 — boxing cost](00_jvm_mental_model.md#q02--jvm-type-mapping)).

### Memory Trick

```
READ-ONLY ≠ IMMUTABLE.
  List<Int> = "you can't modify through THIS reference"
  Someone else holding MutableList to same data CAN modify it.
  For true immutability: use ImmutableList (Guava) or toList() copy.

List<out E> = COVARIANT (readonly → only reads → safe to widen)
MutableList<E> = INVARIANT (can write → widening could corrupt types)

ARRAY boxing shortcut:
  TypeArray (IntArray, FloatArray) → primitive array → unboxed → fast
  Array<Type> (Array<Int>)         → object array   → boxed   → slow
  Choose TypeArray for performance-critical numeric data.
```

### `listOf()` — Backed by `Arrays.asList()`

```kotlin
val list = listOf(1, 2, 3)
```

**Decompiled:**
```java
List list = CollectionsKt.listOf(new Integer[]{1, 2, 3});
// internally: Arrays.asList(1, 2, 3)
```

`Arrays.asList()` creates a fixed-size list that:
- Allows `set()` (change elements in-place) — ✓
- Does NOT allow `add()` or `remove()` — throws `UnsupportedOperationException`
- Is backed by the original array — changes to the array affect the list

**Important:** Kotlin's `listOf()` returns a `List` (read-only interface). Even though the underlying `Arrays.asList` list allows `set()`, Kotlin's type system prevents you from calling `set()` because `List` doesn't expose it.

### `emptyList()` vs `listOf()` With No Arguments

```kotlin
val a = emptyList<Int>()   // returns a SINGLETON empty list
val b = listOf<Int>()      // also returns a SINGLETON empty list (same as emptyList())

// Both compile to the same thing:
// Collections.emptyList() — a shared singleton, zero allocation!
```

`emptyList<T>()` is preferred for clarity and is slightly more direct. Both return the same JVM singleton — `Collections.EMPTY_LIST`.

---

## Q7.2 — Sequences vs Eager Collections

> **Builds on:** [Q4.2 — inline (all sequence operators are inline)](04_functions_lambdas_inlining.md#q42--inline-noinline-crossinline) · [Q4.1 — lambda allocation cost](04_functions_lambdas_inlining.md#q41--lambda-compilation)
> **Connects to:** [Q11.1 — Flow (async counterpart to Sequence)](11_flow.md#q111--cold-vs-hot-streams)
> **Reference:** [Kotlin Docs — Sequences](https://kotlinlang.org/docs/sequences.html)

### The Concrete Picture

Same operations. Completely different execution strategy:

```
EAGER (list.filter.map.take):
  filter ALL 10 → get [2,4,6,8,10]  — 10 elements processed, intermediate list
  map    ALL 5  → get [4,16,36,64,100] — 5 elements processed, intermediate list
  take first 3  → get [4,16,36]
  TOTAL: 15 operations, 2 intermediate lists

LAZY (list.asSequence.filter.map.take):
  element 1: filter(no) → skip
  element 2: filter(yes) → map → count 1 of 3
  element 3: filter(no) → skip
  element 4: filter(yes) → map → count 2 of 3
  element 5: filter(no) → skip
  element 6: filter(yes) → map → count 3 of 3 → DONE (elements 7-10 never touched)
  TOTAL: 6 operations, 0 intermediate lists
```

When lazy is WORSE: small collections (~< 20 elements). Each sequence operator wraps
another object (`FilteringSequence`, `TransformingSequence`). More overhead than savings.

### First Principles: Eager vs Lazy Evaluation

**Eager (collections):** Process ALL elements at each step. Each operator creates a new intermediate collection.

**Lazy (sequences):** Process ONE element all the way through the pipeline, then the next. No intermediate collections.

### The Classic Example: Intermediate Lists

```kotlin
val list = listOf(1, 2, 3, 4, 5, 6, 7, 8, 9, 10)

// EAGER (Collection chain):
val result = list
    .filter { it % 2 == 0 }    // creates: [2, 4, 6, 8, 10]  ← intermediate list!
    .map { it * it }            // creates: [4, 16, 36, 64, 100] ← another list!
    .take(3)                    // creates: [4, 16, 36]  ← another list!

// 3 intermediate lists created, even though we only need 3 results.
```

```kotlin
// LAZY (Sequence chain):
val result = list.asSequence()
    .filter { it % 2 == 0 }    // no list created — transforms lazily
    .map { it * it }            // no list created — transforms lazily
    .take(3)                    // stops after 3 results!
    .toList()                   // terminal: triggers evaluation → [4, 16, 36]
```

```
EAGER evaluation:
list = [1,2,3,4,5,6,7,8,9,10]
       │ filter
       ▼
[2,4,6,8,10]  ← FULL intermediate list
       │ map
       ▼
[4,16,36,64,100]  ← FULL intermediate list
       │ take(3)
       ▼
[4,16,36]  ← final result
All 10 elements were processed through filter and map!

LAZY evaluation:
1 → filter(1%2==0? NO) → skip
2 → filter(2%2==0? YES) → map(2*2=4) → take(1 of 3) → [4]
3 → filter(3%2==0? NO) → skip
4 → filter(4%2==0? YES) → map(4*4=16) → take(2 of 3) → [4,16]
5 → filter(5%2==0? NO) → skip
6 → filter(6%2==0? YES) → map(6*6=36) → take(3 of 3) → [4,16,36] → DONE!
Elements 7-10 never even visited!
```

### When Is a Sequence SLOWER Than Eager Collections?

For **small collections** (roughly < 10-20 elements), sequences have overhead:
- Each sequence operation creates a wrapper object (`FilteringSequence`, `TransformingSequence`)
- Iterator protocol has more indirection than a direct ArrayList loop

```kotlin
// For 5 elements — eager is faster:
listOf(1, 2, 3, 4, 5).filter { it > 2 }.map { it * 2 }
// Creates small ArrayList objects, JIT-friendly, cache-friendly

listOf(1, 2, 3, 4, 5).asSequence().filter { it > 2 }.map { it * 2 }.toList()
// Creates FilteringSequence, TransformingSequence objects — more overhead than savings
```

**Rule of thumb:**
- Use Sequence when: large collections (> ~100 elements), early termination (`take`, `first`, `find`), or potentially infinite
- Use eager when: small collections, or when multiple terminal operations are needed on the intermediate results

### `generateSequence` — Potentially Infinite

```kotlin
// Infinite sequence of natural numbers:
val naturals = generateSequence(1) { it + 1 }

// Safe: take only what you need
val first10 = naturals.take(10).toList()  // [1, 2, 3, ..., 10]

// Fibonacci sequence:
val fibonacci = generateSequence(Pair(0, 1)) { (a, b) -> Pair(b, a + b) }
    .map { it.first }
// 0, 1, 1, 2, 3, 5, 8, 13, ...
val first8 = fibonacci.take(8).toList()

// Reading file lines lazily:
val lines = generateSequence(bufferedReader::readLine)  // null terminates
lines.filter { it.isNotBlank() }.take(100).toList()
```

### Memory Trick

```
SEQUENCE = lazy pipeline. One element travels the full pipeline before the next starts.

USE SEQUENCE WHEN:
  ✓ Large dataset (> ~100 elements)
  ✓ Early termination (take, first, find) — stops after getting what it needs
  ✓ Potentially infinite data (generateSequence)

USE EAGER WHEN:
  ✓ Small dataset (< ~20 elements) — overhead of wrappers outweighs savings
  ✓ Multiple terminals on same intermediate (can't reuse lazy sequence)

Sequence is SYNCHRONOUS (blocks thread).
Flow = async Sequence (can suspend, non-blocking).
```

### How `Flow` Relates to `Sequence`

| | `Sequence` | `Flow` |
|--|-----------|--------|
| Evaluation | Synchronous | Asynchronous |
| Blocking | Yes (blocks thread) | No (suspends) |
| Can suspend | No | Yes |
| Concurrent collection | No | Yes (with `buffer`, etc.) |
| Cold | Yes | Yes |

`Flow` is the async equivalent of `Sequence` — it uses the same lazy element-by-element processing model, but each step can `suspend`. (→ See [Q11.1 — Cold vs Hot Streams](11_flow.md#q111--cold-vs-hot-streams))

---

## Q7.3 — Common Collection Pitfalls

> **Builds on:** [Q7.1 — Collection Hierarchy](07_collections_and_sequences.md#q71--kotlins-collection-hierarchy) · [Q0.1 — heap allocation](00_jvm_mental_model.md#q01--primitives-vs-references)
> **Connects to:** [Q14.4 — Thread-Safe Caching](14_jetpack_components.md#q144--thread-safe-caching)
> **Reference:** [Kotlin Docs — Collection Operations](https://kotlinlang.org/docs/collection-operations.html)

### The Concrete Picture

Three classic pitfalls, each with a concrete example and fix:

**Pitfall 1:** Modifying while iterating:
```
for (item in list) { if (item == 3) list.remove(item) }
→ ConcurrentModificationException

Fix: list.removeAll { it == 3 }          (no external iterator)
     list.filter { it != 3 }              (new list)
     iterator.remove() inside while loop  (safe mutation via iterator)
```

**Pitfall 2:** groupBy (eager) when you need groupingBy (lazy):
```
groupBy { it.length }  → Map<K, List<V>> created immediately, ALL elements processed
groupingBy { it.length }.eachCount()  → aggregates in one pass, no intermediate lists
```

**Pitfall 3:** Race condition on getOrPut:
```
if (!cache.contains(key)) cache[key] = compute()  ← gap between check and put!
cache.getOrPut(key) { compute() }                  ← single call (still not thread-safe)
ConcurrentHashMap.computeIfAbsent(key) { compute() }  ← truly thread-safe
```

### `ConcurrentModificationException` — The Modification Flag

Java's (and Kotlin's) mutable collections track modifications with a `modCount` field:

```kotlin
val list = mutableListOf(1, 2, 3, 4, 5)

// CRASH: ConcurrentModificationException
for (item in list) {
    if (item == 3) list.remove(item)  // modifies list while iterating!
}
```

**How it works:**
```java
// Inside ArrayList:
int expectedModCount = modCount;  // captured at iterator creation

// In next():
if (modCount != expectedModCount) {
    throw new ConcurrentModificationException();  // detected mutation!
}
```

`list.remove()` increments `modCount`. The iterator checks on every `next()` call — mismatch → exception.

**Fixes:**
```kotlin
// Fix 1: Use removeAll with a predicate (no external iteration):
list.removeAll { it == 3 }

// Fix 2: Use iterator explicitly:
val iterator = list.iterator()
while (iterator.hasNext()) {
    if (iterator.next() == 3) iterator.remove()  // safe: iterator tracks modifications
}

// Fix 3: Filter to a new list:
val filtered = list.filter { it != 3 }
```

### `groupBy` vs `groupingBy`

```kotlin
// groupBy — EAGER: immediately creates a Map<K, List<V>>
val grouped: Map<Int, List<String>> = listOf("apple", "banana", "cherry", "apricot")
    .groupBy { it.length }
// Result: {5=[apple], 6=[banana, cherry], 7=[apricot]}
// All elements processed immediately into Map

// groupingBy — LAZY: returns a Grouping<T, K> for chained aggregation
val grouped2 = listOf("apple", "banana", "cherry", "apricot")
    .groupingBy { it.length }
    .eachCount()  // terminal: counts per group
// Result: {5=1, 6=2, 7=1}
// More efficient: never creates intermediate List<V>
```

```kotlin
// groupingBy aggregate variants:
val words = listOf("one", "two", "three", "four", "five")

words.groupingBy { it.length }
    .eachCount()              // count per group
    .also { println(it) }    // {3=2, 5=2, 4=1}

words.groupingBy { it.length }
    .fold("") { acc, word -> "$acc $word".trim() }  // concatenate per group
```

### `getOrPut` — Atomic Check-and-Set

```kotlin
val cache = mutableMapOf<String, List<User>>()

// WRONG: Two separate operations — race condition!
fun getUsersForCity(city: String): List<User> {
    if (!cache.containsKey(city)) {    // check
        cache[city] = fetchUsers(city) // put  ← gap between check and put!
    }
    return cache[city]!!
}

// CORRECT: getOrPut is atomic (single synchronized operation internally):
fun getUsersForCity(city: String): List<User> {
    return cache.getOrPut(city) { fetchUsers(city) }
    // Checks for key AND inserts if missing in one operation
}
```

**Important caveat:** `getOrPut` is NOT thread-safe. "Atomic" here means a single function call — not multi-thread safe. For thread safety, use `ConcurrentHashMap.computeIfAbsent`.

### `LinkedHashMap(accessOrder = true)` — LRU Cache Foundation

```kotlin
// accessOrder = true: moves accessed entries to the tail (most recently used at end)
val lruCache = object : LinkedHashMap<String, Bitmap>(16, 0.75f, true) {
    val maxSize = 50

    override fun removeEldestEntry(eldest: Map.Entry<String, Bitmap>): Boolean {
        return size > maxSize  // remove oldest (head) when over capacity
    }
}

// Usage:
lruCache["image1"] = bitmap1    // [image1]
lruCache["image2"] = bitmap2    // [image1, image2]
lruCache["image1"]              // ACCESS image1 → moves to tail: [image2, image1]
// When full: image2 (eldest/LRU) removed first
```

```
Access-order LinkedHashMap (LRU):
Head (LRU / evict first) ──────────────────── Tail (MRU / keep last)
[image3]  ← accessed longest ago    [image1]  ← accessed most recently
           [image2]
```

### Memory Trick

```
CME (ConcurrentModificationException):
  ArrayList tracks mutations with a modCount counter.
  Iterator captures modCount at creation.
  Any mutation → modCount changes → iterator detects on next() → CME.
  NEVER modify while iterating with a for loop.
  Safe options: removeAll, filter (new list), or iterator.remove().

getOrPut vs computeIfAbsent:
  getOrPut      → single Kotlin function (NOT thread-safe)
  computeIfAbsent → ConcurrentHashMap method (thread-safe, truly atomic)
  In multithreaded code: use ConcurrentHashMap.computeIfAbsent.

LinkedHashMap(accessOrder=true) = free LRU:
  On every get(), moves the entry to the tail.
  Override removeEldestEntry() to evict head when over capacity.
  That's LRU in ~10 lines.
```

---

## Master Summary: Collections and Sequences in 5 Points

```
┌───────────────────────────────────────────────────────────────────────┐
│  1. List is read-only (covariant out E). MutableList is invariant.   │
│     Read-only ≠ Immutable — the underlying data CAN change.          │
│                                                                        │
│  2. IntArray = int[] (primitives, no boxing).                        │
│     Array<Int> = Integer[] (objects, always boxed). Use IntArray!    │
│                                                                        │
│  3. Sequences are lazy — no intermediate collections.                 │
│     Faster for large data + early termination. Slower for small data.│
│                                                                        │
│  4. ConcurrentModificationException: never modify while iterating.   │
│     Use removeAll{}, iterator.remove(), or filter to new list.       │
│                                                                        │
│  5. groupBy is eager (returns Map). groupingBy is lazy (returns      │
│     Grouping for chained aggregation — more memory efficient).        │
└───────────────────────────────────────────────────────────────────────┘
```

---

*← [Phase 6 — Extension Functions](06_extension_functions.md) | [Phase 8 — Other Kotlin Features →](08_other_kotlin_features.md)*
