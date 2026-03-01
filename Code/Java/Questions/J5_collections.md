# Phase J5 — Collections

Java's collections framework is where data structures theory meets JVM implementation reality. Almost every program you write uses ArrayList, HashMap, or one of their siblings. Knowing the data structures is not enough — you need to understand how the JVM implements them, why their performance characteristics differ from textbook Big-O claims, and which concurrent variants to reach for when threads enter the picture. This phase covers the four most interview-critical areas: ArrayList vs LinkedList, HashMap internals (the single most common deep-dive interview topic), ordered maps, and concurrent collections.

---

## J5.1 — ArrayList vs LinkedList

> **Connects to:** [J5.2 — HashMap Internals](J5_collections.md#j52--hashmap-internals) · [J5.4 — Concurrent Collections](J5_collections.md#j54--concurrent-collections)

### WHY This Comparison Matters

The ArrayList vs LinkedList debate is one of the most frequently asked interview questions, and the textbook answer ("LinkedList for frequent middle insertions, ArrayList for random access") is wrong in practice. Understanding why requires going below the API surface to the memory layout of each structure and how modern CPU caches interact with them.

### ArrayList Internals

ArrayList is backed by a plain `Object[]` array. All elements are stored in a single contiguous block of memory. This single fact determines almost all of its performance characteristics.

```
ArrayList memory layout (capacity 10, size 4):
┌───────────────────────────────────────────────────┐
│ Object[]  │ ref0 │ ref1 │ ref2 │ ref3 │ null × 6 │
└───────────────────────────────────────────────────┘
              [0]    [1]    [2]    [3]

Each slot is a 4-byte (compressed oops) or 8-byte reference.
```

**Initial capacity and growth:** When you call `new ArrayList<>()`, the internal array starts at capacity 10. When the array is full and you call `add()`, ArrayList allocates a new array with `newCapacity = oldCapacity + (oldCapacity >> 1)` — that is, 50% growth. It then copies all existing elements with `Arrays.copyOf()`, which calls `System.arraycopy()` — a native method that uses CPU memory-move instructions (`memcpy`).

```java
// Visible in ArrayList source (OpenJDK):
private Object[] grow(int minCapacity) {
    int oldCapacity = elementData.length;
    if (oldCapacity > 0 || elementData != DEFAULTCAPACITY_EMPTY_ELEMENTDATA) {
        int newCapacity = ArraysSupport.newLength(oldCapacity,
            minCapacity - oldCapacity, /* minimum growth */
            oldCapacity >> 1           /* preferred growth: 50% */);
        return elementData = Arrays.copyOf(elementData, newCapacity);
    } else {
        return elementData = new Object[Math.max(DEFAULT_CAPACITY, minCapacity)];
    }
}
```

**Operation complexities:**

| Operation | Complexity | Explanation |
|-----------|-----------|-------------|
| `get(int index)` | O(1) | Direct array index: `elementData[index]` |
| `add(E e)` at end | O(1) amortized | Occasional resize is O(n), but amortized over n insertions gives O(1) |
| `add(int index, E e)` in middle | O(n) | `System.arraycopy()` shifts elements right |
| `remove(int index)` | O(n) | `System.arraycopy()` shifts elements left |
| `contains(E e)` | O(n) | Linear scan |
| `size()` | O(1) | Stored field |

The key insight for `add()` at end: resize happens when the array is full. After a resize from size n to 1.5n, you can do approximately 0.5n more `add()` calls before the next resize. The total cost of n insertions is n * O(1) for the non-resize ones + O(n) for the resize itself. Amortized per-insertion: O(1).

**Pre-sizing:** If you know the approximate final size upfront, pre-size to eliminate all resizes:
```java
List<String> list = new ArrayList<>(1_000_000);   // no resizes needed
```

### LinkedList Internals

LinkedList is a doubly-linked list. Each element lives in its own `Node` object on the heap, scattered across memory:

```java
// Simplified Node structure (from OpenJDK):
private static class Node<E> {
    E item;
    Node<E> next;
    Node<E> prev;
}
```

```
LinkedList memory layout (4 elements):

Stack:
  list → [head=NodeA, tail=NodeD, size=4]

Heap (nodes scattered in memory):
  NodeA [prev=null, item="a", next=NodeB]  ← somewhere in heap
       ↓
  NodeB [prev=NodeA, item="b", next=NodeC]  ← different memory page
       ↓
  NodeC [prev=NodeB, item="c", next=NodeD]  ← yet another page
       ↓
  NodeD [prev=NodeC, item="d", next=null]
```

Each `Node` object has an object header (typically 12–16 bytes on HotSpot), plus three reference fields (4 bytes each with compressed oops) = approximately 28–32 bytes per element. ArrayList uses 4 bytes per element (just the reference). For a list of 1 million integers, LinkedList uses ~28 MB; ArrayList uses ~4 MB plus the integer objects.

**Operation complexities:**

| Operation | Complexity | Explanation |
|-----------|-----------|-------------|
| `get(int index)` | O(n) | Traverse from head or tail (whichever is closer) |
| `add(E e)` at end | O(1) | Update `tail` and `tail.prev` |
| `addFirst(E e)` | O(1) | Update `head` and `head.next` |
| `add(int index, E e)` | O(n) to find + O(1) to insert | Must walk to position |
| `remove(int index)` | O(n) to find + O(1) to remove | Must walk to position |
| `removeFirst()` | O(1) | Update head pointer |
| `removeLast()` | O(1) | Update tail pointer |

### The CPU Cache Problem: Why Textbook Theory Fails

Modern CPUs have L1/L2/L3 caches. When the CPU accesses a memory address, it loads an entire **cache line** (~64 bytes) into L1 cache. If the next access is to a nearby address (already in that cache line), it completes in ~1-4 clock cycles. If the address is far away (cache miss), it may require going to main RAM — 200+ clock cycles.

ArrayList's contiguous array means that after loading element[0], elements[1] through element[15] are already in the cache line. Sequential iteration hits the cache almost every time.

LinkedList's nodes are allocated on the heap at different times and end up scattered across memory. Traversing node → node.next requires loading a new, distant memory location at each step — essentially every step is a cache miss.

**Practical consequence:** For middle insertions, the benchmark always looks like this:

```
Inserting 100,000 elements at middle:
ArrayList (System.arraycopy):  ~50 ms
LinkedList (walk to middle):   ~500 ms
```

ArrayList's `System.arraycopy()` is a highly optimized native call that can exploit SIMD instructions to move many bytes at once through cache. LinkedList's O(n) traversal to find the midpoint incurs n/2 cache misses. The constant factor of LinkedList's O(1) insert crushes its theoretical advantage.

### When LinkedList Actually Wins

LinkedList's `Deque` operations are genuinely O(1) with low constant factors because they access only the head or tail — no traversal:

```java
// LinkedList as Deque — this IS faster than ArrayList
Deque<String> deque = new LinkedList<>();
deque.addFirst("a");     // O(1) — update head
deque.addLast("b");      // O(1) — update tail
deque.removeFirst();     // O(1) — update head
deque.removeLast();      // O(1) — update tail
```

However, even here the better choice is `ArrayDeque`, which is also O(1) for all deque operations, is cache-friendly (circular array), and has no object allocation per element.

### Interview Trap: "Use LinkedList for Middle Insertions"

This advice appears in outdated textbooks and is wrong in practice. The correct advice is:

- **Default choice:** `ArrayList` — cache-friendly, lower memory overhead, fast iteration.
- **Queue/Deque operations:** `ArrayDeque` — O(1) head/tail access, cache-friendly, no per-element object overhead.
- **LinkedList's actual use case:** when you hold an `Iterator` positioned at the insertion point and want true O(1) insertion without re-traversal. This is rare and only relevant with the `ListIterator.add()` method.

---

## J5.2 — HashMap Internals

> **Connects to:** [J5.3 — TreeMap & LinkedHashMap](J5_collections.md#j53--treemap--linkedhashmap) · [J5.4 — Concurrent Collections](J5_collections.md#j54--concurrent-collections)

### WHY HashMap Internals Matter

HashMap is the single most common topic in Java interviews after basic syntax. Every developer uses it daily, but most developers have only a surface understanding. The questions interviewers ask — "what happens when two keys hash to the same bucket?", "what is the time complexity of get()?", "why must hashCode and equals be consistent?" — all require understanding the internal structure.

### The Bucket Array

HashMap maintains an array of **buckets**: `Node<K,V>[] table`. Each bucket is either null (empty) or the head of a chain of nodes that all hashed to that bucket.

```
HashMap internal structure (capacity 16, 3 entries):

table (length 16):
[0]  → null
[1]  → null
[2]  → Node("bob", 25, hash=2, next=null)
[3]  → null
[4]  → Node("alice", 30, hash=4, next=Node("charlie", 22, hash=20, next=null))
       ← two keys collide at bucket 4!
[5]  → null
...
[15] → null
```

Each `Node` stores:
```java
static class Node<K,V> implements Map.Entry<K,V> {
    final int hash;       // cached hash code
    final K key;
    V value;
    Node<K,V> next;       // next node in chain (for collision)
}
```

### The Hash Function

Computing the bucket index for a key happens in two steps:

**Step 1: Spread the hash code**
```java
// HashMap.hash() — "perturbation function"
static final int hash(Object key) {
    int h;
    return (key == null) ? 0 : (h = key.hashCode()) ^ (h >>> 16);
}
```

This XORs the high 16 bits of the hash code with the low 16 bits. Why? Many `hashCode()` implementations (especially integers and strings in common ranges) have variation mostly in the low bits. XORing with the high bits ensures that high-bit variation also affects the bucket selection, improving distribution and reducing collisions.

**Step 2: Map to a bucket index**
```java
// Inside put() and get():
int index = (n - 1) & hash;   // n = table.length (always a power of 2)
```

Because the table length is always a power of 2, `(n-1)` is a bitmask of all 1s. The `&` is equivalent to `hash % n`, but bitwise AND is far faster than division.

### Collision Resolution: Chaining

When two keys map to the same bucket index, HashMap chains them in a linked list:

```java
// put() simplified (Java 8, non-treeified path):
Node<K,V> p = table[index];
if (p == null) {
    table[index] = newNode(hash, key, value, null);    // empty bucket: direct insert
} else {
    // Collision: walk the chain
    Node<K,V> e;
    if (p.hash == hash && (p.key == key || (key != null && key.equals(p.key)))) {
        e = p;   // key exists at head — update value
    } else {
        for (int binCount = 0; ; ++binCount) {
            if ((e = p.next) == null) {
                p.next = newNode(hash, key, value, null);   // append to chain
                if (binCount >= TREEIFY_THRESHOLD - 1)      // 8
                    treeifyBin(tab, hash);                   // convert to tree!
                break;
            }
            if (e.hash == hash && (e.key == key || (key != null && key.equals(p.key)))) {
                break;   // found existing key
            }
            p = e;
        }
    }
    if (e != null) { e.value = value; }   // update value for existing key
}
```

**Before Java 8:** collision chains were always linked lists. Worst case O(n) for `get()` when all keys hash to the same bucket. A deliberate attack sending millions of requests with collision-crafted keys could degrade a hash map to O(n) per lookup — a Denial-of-Service vulnerability.

**Java 8 treeification:** When a bucket's chain length reaches `TREEIFY_THRESHOLD` (8), the chain is converted to a **Red-Black tree**. The worst case for that bucket drops from O(n) to O(log n). The tree is converted back to a linked list when the count drops below `UNTREEIFY_THRESHOLD` (6) during removal. This hysteresis (8 to grow, 6 to shrink) prevents thrashing.

```
Chain → Tree conversion (bucket 4 with 8+ collisions):

Before (chain):
Node("key0") → Node("key1") → Node("key2") → ... → Node("key7")
[O(n) worst case for lookup]

After treeification (Red-Black tree rooted at bucket 4):
           Node("key3")
          /            \
     Node("key1")   Node("key6")
     /      \        /       \
Node("key0") Node("key2") ...
[O(log n) worst case for lookup]
```

### Resize and Rehash

When the number of entries exceeds `capacity * loadFactor` (default: `16 * 0.75 = 12`), HashMap doubles the table size and rehashes all entries:

```java
final Node<K,V>[] resize() {
    // Double the capacity
    int newCap = oldCap << 1;   // multiply by 2
    Node<K,V>[] newTab = new Node[newCap];

    // Rehash all entries
    for (int j = 0; j < oldCap; j++) {
        Node<K,V> e = oldTab[j];
        while (e != null) {
            int newIndex = e.hash & (newCap - 1);   // recompute index
            // insert into newTab[newIndex]
            e = e.next;
        }
    }
    return newTab;
}
```

This is an O(n) operation. Since load factor is 0.75, capacity doubles when 75% full. The amortized cost of resize across n insertions is O(1) per insertion. But if you know the expected size, pre-sizing eliminates all resizes:

```java
// If you expect ~100 entries, pre-size so that 100 < capacity * 0.75
// capacity needed: 100 / 0.75 = 134 → rounds up to next power of 2: 256
Map<String, String> map = new HashMap<>(256);    // no resizing up to 192 entries
// Or let Guava compute the right size:
// Maps.newHashMapWithExpectedSize(100)          // handles the math for you
```

### Why hashCode() and equals() Must Be Consistent

The HashMap contract states: if `a.equals(b)` is `true`, then `a.hashCode()` must equal `b.hashCode()`. Violating this creates silent data corruption:

```java
class BadKey {
    int id;
    BadKey(int id) { this.id = id; }

    @Override
    public boolean equals(Object o) {
        return o instanceof BadKey && ((BadKey) o).id == this.id;
    }
    // hashCode() NOT overridden — uses Object's identity-based hash!
}

Map<BadKey, String> map = new HashMap<>();
BadKey k1 = new BadKey(42);
map.put(k1, "value");

BadKey k2 = new BadKey(42);   // logically equal to k1
System.out.println(k2.equals(k1));       // true — equals() says they're equal
System.out.println(map.get(k2));         // null — k1 and k2 hash to DIFFERENT buckets!
// HashMap looked in wrong bucket, never found k1's entry
```

The reverse violation (same `hashCode()`, different `equals()`) does not break correctness — it just causes unnecessary collisions and degrades performance.

### The Mutable Key Bug

If you put an object into a HashMap as a key and then mutate the object in a way that changes its `hashCode()`, the entry becomes permanently lost:

```java
List<String> key = new ArrayList<>(List.of("a", "b"));
Map<List<String>, Integer> map = new HashMap<>();
map.put(key, 42);

System.out.println(map.get(key));   // 42 — correct

key.add("c");   // MUTATE THE KEY

// key.hashCode() has changed — HashMap looks in wrong bucket
System.out.println(map.get(key));   // null — entry is lost!
// The entry is still in the map (you can see it via map.entrySet()),
// but it's in the wrong bucket and unreachable via get()
```

This is why immutable objects (String, Integer, enums, records) make the safest HashMap keys. If you must use mutable objects as keys, ensure their `hashCode()` is based only on immutable fields.

### null Key Handling

HashMap allows exactly one `null` key. The `hash(null)` function returns 0, so null keys always go to bucket 0. This is a special-cased path in put/get — it works correctly but you must remember that only HashMap (and LinkedHashMap) support null keys. TreeMap and ConcurrentHashMap throw `NullPointerException` for null keys.

### Interview Trap: Time Complexity of get()

The correct answer is:
- **O(1) average case** — assuming a good hash function and low collision rate
- **O(log n) worst case** — with Java 8 treeification, when all keys hash to one bucket
- **O(n) worst case** — before Java 8, or when treeification hasn't triggered yet (< 8 collisions in a bucket)

Saying "O(1)" without qualification is technically wrong. Interviewers who know HashMap internals will push back.

---

## J5.3 — TreeMap & LinkedHashMap

> **Builds on:** [J5.2 — HashMap Internals](J5_collections.md#j52--hashmap-internals)
> **Connects to:** [J5.4 — Concurrent Collections](J5_collections.md#j54--concurrent-collections)

### WHY Ordered Maps Exist

HashMap gives you O(1) average operations but makes no promises about iteration order — and the order changes with each resize. Two use cases require order:

1. **Iteration in sorted key order:** reporting, range queries, finding the minimum/maximum key.
2. **Iteration in insertion or access order:** caching where you need to know which entry was accessed least recently.

TreeMap and LinkedHashMap serve these use cases respectively, at different performance costs.

### TreeMap: Red-Black Tree Ordering

TreeMap stores all entries in a **Red-Black tree** — a self-balancing binary search tree that guarantees O(log n) for all basic operations:

```
TreeMap with keys {1, 3, 5, 7, 9} (Red-Black tree):

          5 (BLACK)
         / \
       3     7
      / \   / \
     1   4 6   9
```

Every `put()`, `get()`, and `remove()` traverses the tree from root to the appropriate position — O(log n). The tree self-balances on insertions and deletions via rotation and recoloring, keeping height bounded at O(log n).

**Ordering:** TreeMap maintains entries sorted by key. The ordering comes from either:
1. The key's natural order via `Comparable` — keys must implement `Comparable<K>`, or
2. A custom `Comparator` passed to the constructor: `new TreeMap<>(myComparator)`

If neither is provided and you insert a key that doesn't implement `Comparable`, `put()` throws `ClassCastException`.

**Range operations — TreeMap's real advantage:**

```java
TreeMap<Integer, String> map = new TreeMap<>();
// insert entries...

// First and last:
Integer first = map.firstKey();          // smallest key
Integer last  = map.lastKey();           // largest key

// Navigation methods (Java 6+):
Integer floor   = map.floorKey(5);       // greatest key <= 5
Integer ceiling = map.ceilingKey(5);     // smallest key >= 5
Integer lower   = map.lowerKey(5);       // greatest key strictly < 5
Integer higher  = map.higherKey(5);      // smallest key strictly > 5

// Sub-map views (live views, backed by the original TreeMap):
SortedMap<Integer, String> head = map.headMap(5);          // keys < 5
SortedMap<Integer, String> tail = map.tailMap(5);          // keys >= 5
SortedMap<Integer, String> sub  = map.subMap(3, 7);        // keys in [3, 7)
NavigableMap<Integer, String> desc = map.descendingMap();  // reverse order view

// These views reflect real-time changes to the underlying map
// Modifications to the view modify the original map too
```

These range operations make TreeMap the natural choice for implementing scheduling systems, interval trees, or any data structure that needs to answer "what is the nearest entry to this value?"

**Null keys:** TreeMap does NOT allow null keys (a `null.compareTo(x)` would throw `NullPointerException`). Null values are allowed.

### LinkedHashMap: Insertion and Access Order

LinkedHashMap extends HashMap — it has the same bucket array with the same O(1) average get/put. The addition is a **doubly-linked list** that threads through all entries, maintaining a secondary ordering:

```
LinkedHashMap internal structure:

Bucket array (for O(1) hash lookup):
[0] → null
[1] → Entry("bob")
[2] → Entry("alice")
...

Linked list (for ordered iteration):
header ↔ Entry("alice") ↔ Entry("bob") ↔ Entry("charlie") ↔ header
(insertion order: alice was inserted first)
```

Each entry in LinkedHashMap has two extra fields: `before` and `after` pointers for the doubly-linked list.

**Two ordering modes:**

```java
// Default: insertion order
LinkedHashMap<String, Integer> insertionOrder = new LinkedHashMap<>();
insertionOrder.put("banana", 2);
insertionOrder.put("apple", 1);
insertionOrder.put("cherry", 3);
// Iteration: banana, apple, cherry (insertion order preserved)

// Access order: most recently accessed entry moves to end
LinkedHashMap<String, Integer> accessOrder =
    new LinkedHashMap<>(16, 0.75f, true);   // third arg: accessOrder = true
accessOrder.put("banana", 2);
accessOrder.put("apple", 1);
accessOrder.put("cherry", 3);
// Internal order: banana ↔ apple ↔ cherry

accessOrder.get("banana");   // moves banana to end
// Internal order: apple ↔ cherry ↔ banana
```

### LRU Cache: The Classic LinkedHashMap Use Case

Access-order LinkedHashMap, combined with the `removeEldestEntry()` hook, implements an LRU (Least Recently Used) cache in about 10 lines:

```java
class LRUCache<K, V> extends LinkedHashMap<K, V> {
    private final int maxSize;

    LRUCache(int maxSize) {
        super(maxSize, 0.75f, true);   // initialCapacity, loadFactor, accessOrder=true
        this.maxSize = maxSize;
    }

    @Override
    protected boolean removeEldestEntry(Map.Entry<K, V> eldest) {
        // Called after every put(). If we return true, the eldest entry is removed.
        // "Eldest" in access-order mode means least recently accessed.
        return size() > maxSize;
    }
}

// Usage:
LRUCache<Integer, String> cache = new LRUCache<>(3);
cache.put(1, "one");
cache.put(2, "two");
cache.put(3, "three");
cache.get(1);           // access key 1 → moves to most-recently-used end
cache.put(4, "four");   // triggers removeEldestEntry — evicts key 2 (least recently used)
// cache now contains: {3=three, 1=one, 4=four}
```

`removeEldestEntry()` is called after `put()` and `putIfAbsent()`. If it returns `true`, the entry pointed to by `eldest` (the head of the linked list — the least recently used) is removed automatically. This is O(1): remove head of linked list, remove from bucket array.

### IdentityHashMap

`IdentityHashMap` uses `==` (reference equality) instead of `equals()`, and `System.identityHashCode()` instead of `hashCode()`. Two keys are "the same" only if they are literally the same object, regardless of what their `equals()` method says.

```java
Map<String, Integer> identity = new IdentityHashMap<>();
String s1 = new String("hello");
String s2 = new String("hello");

identity.put(s1, 1);
identity.put(s2, 2);   // different key! s1 != s2

System.out.println(identity.size());   // 2 — both entries present
System.out.println(identity.get(s1));  // 1
System.out.println(identity.get(s2));  // 2

// In a regular HashMap:
Map<String, Integer> regular = new HashMap<>();
regular.put(s1, 1);
regular.put(s2, 2);   // same key! s1.equals(s2) is true
System.out.println(regular.size());   // 1 — s2 replaced s1's value
```

Use cases: object graph traversal (detecting visited nodes), serialization frameworks (tracking serialized objects), proxy/instrumentation systems that need identity-based tracking.

### WeakHashMap

`WeakHashMap` holds keys via **weak references**. The garbage collector is free to collect an entry's key at any time if no other strong reference to the key exists. When a key is collected, the entry disappears from the map.

```java
Map<Object, String> cache = new WeakHashMap<>();
Object key = new Object();
cache.put(key, "associated value");

System.out.println(cache.size());   // 1

key = null;             // drop the strong reference
System.gc();            // hint to GC (not guaranteed, but often works in demos)
System.out.println(cache.size());   // 0 — entry was collected along with the key
```

`WeakHashMap` is useful for caches that should not prevent their keys from being garbage collected. The classic use case is a per-class cache (key = Class object) or a per-thread cache (key = Thread object) — when the class or thread is unloaded/terminated, the cache entry disappears automatically without explicit cleanup.

**Caution:** `WeakHashMap` is NOT thread-safe. For a concurrent weak-key cache, use `ConcurrentHashMap` with `WeakReference` values (or Guava's `CacheBuilder`).

### Interview Trap: Comparator That Returns 0 for "Equal" Keys

TreeMap considers two keys equal if and only if the comparator returns 0. This is independent of `equals()`. If your comparator returns 0 for two keys that `equals()` considers distinct, TreeMap will treat them as the same key and keep only one value:

```java
// Sort strings case-insensitively
TreeMap<String, Integer> map = new TreeMap<>(String.CASE_INSENSITIVE_ORDER);
map.put("Apple", 1);
map.put("apple", 2);   // comparator returns 0 for "Apple" vs "apple"!
// Only one entry survives: {"Apple": 2} (second put overwrites first)
System.out.println(map.size());         // 1 — NOT 2!
System.out.println(map.get("APPLE"));   // 2
```

The fix: ensure your comparator's notion of equality matches your objects' `equals()` method. If the comparator must differ from `equals()` (e.g., case-insensitive ordering for case-sensitive keys), document this explicitly and be aware that TreeMap's "duplicates" behavior may surprise you.

---

## J5.4 — Concurrent Collections

> **Builds on:** [J5.2 — HashMap Internals](J5_collections.md#j52--hashmap-internals) · [J5.3 — TreeMap & LinkedHashMap](J5_collections.md#j53--treemap--linkedhashmap)

### WHY Concurrent Collections

`HashMap` is not thread-safe. If two threads call `put()` simultaneously, you get undefined behavior. In Java 6 and earlier, concurrent resizes could create cycles in the linked list, causing `get()` to spin in an infinite loop — a production outage scenario. In Java 8+, you get `ConcurrentModificationException` or lost updates.

The naive fix is `Collections.synchronizedMap(map)`, which wraps every method in a `synchronized` block on the map object:

```java
Map<String, Integer> syncMap = Collections.synchronizedMap(new HashMap<>());
// Thread 1: syncMap.put("key", 1)   ← blocks until Thread 2 releases lock
// Thread 2: syncMap.get("key")      ← holds lock, blocks Thread 1
```

This serializes all access — only one thread operates on the map at a time. For a highly concurrent application with many threads reading and writing the same map, this is a throughput bottleneck.

### ConcurrentHashMap — Java 7: Segment-Based Locking

Java 7's `ConcurrentHashMap` partitioned the hash table into 16 **Segments** by default. Each Segment was an independent mini-HashMap with its own `ReentrantLock`. Up to 16 threads could write simultaneously, each to a different Segment, without blocking each other.

```
Java 7 ConcurrentHashMap structure:

segments[0]  → Segment (lock + bucket array) → entries...
segments[1]  → Segment (lock + bucket array) → entries...
...
segments[15] → Segment (lock + bucket array) → entries...

A key maps to: segment index = (hash >>> segmentShift) & segmentMask
               then to:    bucket index within that segment
```

`size()` had to acquire all 16 segment locks to get a consistent count — expensive if called frequently.

### ConcurrentHashMap — Java 8: CAS + Per-Bucket Locking

Java 8 completely redesigned ConcurrentHashMap. Segments were removed. The structure is now a single flat `Node[] table`, just like HashMap. Concurrency is achieved via **CAS (compare-and-swap) operations** and **synchronized blocks on individual bucket heads**:

```java
// Simplified put() logic (Java 8):
for (;;) {  // spin until successful
    Node<K,V> f = tabAt(tab, i);           // volatile read of bucket head

    if (f == null) {
        // Empty bucket: use CAS — no lock needed!
        if (casTabAt(tab, i, null, new Node<>(hash, key, value, null)))
            break;   // CAS succeeded: done
        // CAS failed: another thread inserted — retry loop
    } else {
        // Non-empty bucket: lock just this bucket head
        synchronized (f) {
            // ... walk chain, insert or update
        }
    }
}
```

For most insertions (into empty buckets), no lock is acquired at all — the CAS instruction is atomic at the hardware level. Only when there is a collision does the code take a lock, and that lock covers only the single bucket head node, not the entire table. The result is dramatically higher throughput: hundreds of threads can write concurrently as long as their keys hash to different buckets.

**Java 8 ConcurrentHashMap key properties:**
- No null keys or null values. A `null` return from `get()` unambiguously means "key not present" (unlike HashMap where null value is valid).
- `size()` is an estimate under concurrent modification — maintained via a distributed counter (similar to `LongAdder`).
- `mappingCount()` returns a `long` — use this instead of `size()` for large maps.
- Full Java 8 treeification (bucket chains → Red-Black trees at threshold 8).

### Atomic Composite Operations

The most important thing about ConcurrentHashMap is that individual operations are thread-safe, but composing them is not:

```java
ConcurrentHashMap<String, Integer> map = new ConcurrentHashMap<>();

// WRONG — not atomic (check-then-act race condition):
if (!map.containsKey("key")) {
    map.put("key", computeExpensiveValue());
}
// Thread A checks: containsKey("key") → false
// Thread B checks: containsKey("key") → false
// Both compute value and both call put() — duplicate computation!

// CORRECT — atomic:
map.computeIfAbsent("key", k -> computeExpensiveValue());
// The lambda runs at most once, even under contention
```

The atomic composite operations available on `ConcurrentHashMap`:

```java
// computeIfAbsent: if key absent, compute and insert
map.computeIfAbsent("key", k -> new ArrayList<>());

// computeIfPresent: if key present, compute new value (or remove if null returned)
map.computeIfPresent("key", (k, v) -> v + 1);

// compute: always compute new value (insert/update/remove)
map.compute("key", (k, v) -> v == null ? 1 : v + 1);   // increment, or start at 1

// merge: if key absent, insert value; if present, combine with existing
map.merge("key", 1, Integer::sum);   // accumulate counts — cleaner than compute

// putIfAbsent: atomic put-if-absent, returns existing value or null
Integer existing = map.putIfAbsent("key", 42);

// replace: atomic replace only if key exists
boolean replaced = map.replace("key", oldValue, newValue);   // CAS semantics
```

### CopyOnWriteArrayList

`CopyOnWriteArrayList` takes the opposite trade-off from ConcurrentHashMap: reads are completely lock-free, but writes are very expensive.

On every write (`add()`, `set()`, `remove()`), the entire backing array is copied, the modification is applied to the copy, and the reference is atomically updated to point to the new array. Readers always see a consistent, immutable snapshot — the array reference they read when their operation started never changes under them.

```java
CopyOnWriteArrayList<String> list = new CopyOnWriteArrayList<>();
list.add("a");   // creates copy of [], produces ["a"], swaps reference

// Many readers — lock-free, see the stable snapshot at their start time
for (String s : list) {
    // If another thread calls list.add("b") here,
    // this iterator still sees the OLD snapshot — no ConcurrentModificationException!
    System.out.println(s);
}
```

**When to use:** listener/observer lists, where registrations rarely change but notifications are frequent. A typical event bus has ~5 listeners registered at startup and thousands of events dispatched per second — reads dominate massively.

**When NOT to use:** any list with frequent writes. Adding 10,000 elements to a `CopyOnWriteArrayList` creates 10,000 full array copies — O(n²) total work.

### BlockingQueue Implementations

`BlockingQueue` extends `Queue` with two critical operations:
- `put(e)`: insert, blocking if the queue is full (for bounded queues).
- `take()`: remove and return head, blocking if the queue is empty.

These are the building blocks of the producer-consumer pattern:

```java
BlockingQueue<Task> queue = new ArrayBlockingQueue<>(100);

// Producer thread:
queue.put(new Task(...));   // blocks if queue has 100 items

// Consumer thread:
Task task = queue.take();   // blocks until an item is available
process(task);
```

**Implementations:**

| Implementation | Bounded? | Backing Structure | Locking |
|----------------|----------|-------------------|---------|
| `ArrayBlockingQueue` | Yes | Circular array | Single lock |
| `LinkedBlockingQueue` | Optional | Linked nodes | Separate head/tail locks |
| `PriorityBlockingQueue` | No | Binary heap | Single lock |
| `SynchronousQueue` | N/A (no storage) | None | CAS |
| `DelayQueue` | No | Priority heap | Single lock |

`LinkedBlockingQueue` uses two separate locks (one for the head, one for the tail) so producers and consumers do not block each other unless the queue is empty or full — higher throughput than `ArrayBlockingQueue` for high-contention producer-consumer scenarios.

`SynchronousQueue` has no internal storage. A `put()` blocks until another thread calls `take()`, and vice versa. It is a rendezvous point — a zero-capacity handoff. This is how `Executors.newCachedThreadPool()` works internally: submitting a task is a `put()`, and a cached thread picks it up with `take()`.

### Interview Trap: ConcurrentHashMap Is Not Fully Atomic

A common misconception is that ConcurrentHashMap makes all your concurrent map code correct. It does not. Individual operations are atomic; compound operations are not:

```java
ConcurrentHashMap<String, Integer> map = new ConcurrentHashMap<>();
map.put("count", 0);

// WRONG — not atomic (check-then-act on two separate operations):
if (map.size() == 0) {
    map.put("initialized", true);
}
// Thread A and Thread B can both see size == 0 and both insert

// WRONG — read-then-write (not atomic):
int current = map.get("count");    // read
map.put("count", current + 1);    // write (another thread may have changed it!)

// CORRECT — single atomic operation:
map.merge("count", 1, Integer::sum);
// Or for more complex logic:
map.compute("count", (k, v) -> v == null ? 1 : v + 1);
```

The rule: use `computeIfAbsent`, `compute`, `merge`, `putIfAbsent`, and `replace(key, old, new)` for all check-then-act patterns. Never split what should be one atomic operation into separate `get()` + `put()` calls.

---

## Master Summary

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                          PHASE J5 — COLLECTIONS                                  │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  1. ARRAYLIST vs LINKEDLIST: ArrayList wins in almost every real benchmark      │
│     because its contiguous memory array is CPU cache-friendly. LinkedList's     │
│     per-element Node objects scatter across the heap, causing cache misses on   │
│     every traversal. Use ArrayList as the default. Use ArrayDeque for           │
│     queue/deque operations. LinkedList's only real advantage is O(1) insert     │
│     at a held iterator position — rare in practice.                             │
│                                                                                 │
│  2. HASHMAP: backed by Node[] array of buckets. Hash function XORs high/low     │
│     bits for better distribution. Collisions resolved by chaining; Java 8       │
│     treeifies chains at length 8 (O(n) → O(log n) worst case). Resize          │
│     doubles capacity when size > capacity*0.75. get() is O(1) average,         │
│     O(log n) worst case. hashCode/equals must be consistent; mutable keys      │
│     are dangerous. null key goes to bucket 0.                                   │
│                                                                                 │
│  3. ORDERED MAPS: TreeMap uses a Red-Black tree — O(log n) all operations,     │
│     sorted by key, excellent for range queries (floorKey, subMap, headMap).     │
│     LinkedHashMap = HashMap + doubly-linked list — O(1) operations with        │
│     insertion or access ordering. Access-order + removeEldestEntry() = LRU      │
│     cache in 10 lines. Comparator returning 0 means "same key" in TreeMap,     │
│     regardless of equals().                                                     │
│                                                                                 │
│  4. CONCURRENT COLLECTIONS: ConcurrentHashMap (Java 8) uses CAS for empty      │
│     buckets and per-bucket synchronized for collisions — no global lock.        │
│     Individual operations are atomic; compound operations (check-then-act)     │
│     are NOT — use compute/merge/putIfAbsent. CopyOnWriteArrayList: reads are   │
│     lock-free, writes copy the array — only for read-heavy, rarely-written      │
│     lists. BlockingQueue implements producer-consumer; SynchronousQueue         │
│     is a zero-capacity rendezvous.                                              │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

*← [Phase J4 — Functional Java](J4_functional.md) | [Phase J6 — Concurrency Fundamentals →](J6_concurrency_fundamentals.md)*
