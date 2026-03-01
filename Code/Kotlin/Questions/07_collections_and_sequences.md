# Phase 7: Collections and Sequences

## Navigation
| Phase | File |
|-------|------|
| 6 — Extension Functions | [06_extension_functions.md](06_extension_functions.md) |
| **7 — Collections & Sequences** | ← You are here |
| 8 — Other Kotlin Features | [08_other_kotlin_features.md](08_other_kotlin_features.md) |

---

## Q7.1 — Kotlin's Collection Hierarchy

> **Builds on:** [Q3.2 — Variance](03_generics_and_variance.md#q32--variance) · [Q0.2 — JVM Type Mapping](00_jvm_mental_model.md#q02--jvm-type-mapping)
> **Reference:** [Kotlin Docs — Collections Overview](https://kotlinlang.org/docs/collections-overview.html)

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

**`List<out E>`** — covariant because `List` only has read operations:
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

**Rule:** For numeric arrays in performance-critical code (game loops, image processing, audio), always use `IntArray`, `FloatArray`, `LongArray` — never `Array<Int>`.

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

> **Reference:** [Kotlin Docs — Sequences](https://kotlinlang.org/docs/sequences.html)
> **Connects to:** [Q11.1 — Flow](11_flow.md)

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

### How `Flow` Relates to `Sequence`

| | `Sequence` | `Flow` |
|--|-----------|--------|
| Evaluation | Synchronous | Asynchronous |
| Blocking | Yes (blocks thread) | No (suspends) |
| Can suspend | No | Yes |
| Concurrent collection | No | Yes (with `buffer`, etc.) |
| Cold | Yes | Yes |

`Flow` is the async equivalent of `Sequence` — it uses the same lazy element-by-element processing model, but each step can `suspend`. (→ See [Q11.1 Flow](11_flow.md))

---

## Q7.3 — Common Collection Pitfalls

> **Reference:** [Kotlin Docs — Collection Operations](https://kotlinlang.org/docs/collection-operations.html)

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
