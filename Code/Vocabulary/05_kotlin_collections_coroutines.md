# Section 5 — Kotlin Collections & Coroutines (Q83–Q91)

---

## Collections (Q83–Q86)

### Q83. Difference between `List` and `MutableList`?
**Definition:** `List<T>` is read-only (no add/remove). `MutableList<T>` allows modification.
**Core Idea:** Kotlin separates read-only and mutable views at the type level. `List` does NOT guarantee immutability — the underlying data can still be changed via a `MutableList` reference.
**How it Works:** `listOf()` returns `List`. `mutableListOf()` returns `MutableList`. Both backed by `ArrayList`.
**Example:** `val list: List<Int> = mutableListOf(1, 2, 3)` — `list` can't call `add()`, but the underlying list can be changed via the original `MutableList` reference.
**Interview Insight:** `List` = read-only interface, NOT immutable. If you need truly immutable, use `Collections.unmodifiableList()` or a persistent collection. In Kotlin, expose `List`, hold `MutableList` privately — this is the standard ViewModel pattern.

---

### Q84. Difference between `Set` and `HashSet`?
**Definition:** `Set<T>` is the read-only interface. `HashSet<T>` is a concrete mutable implementation using a hash table.
**Core Idea:** `Set` = contract (no duplicates). `HashSet` = implementation (O(1) add/remove/contains via hashing).
**How it Works:** `setOf()` returns read-only `Set` (backed by `LinkedHashSet`). `hashSetOf()` returns `HashSet`. No guaranteed order in `HashSet`.
**Example:** `val set: Set<Int> = setOf(1, 2, 3)` — read-only. `val hs: HashSet<Int> = hashSetOf(1, 2, 3)` — mutable.
**Interview Insight:** `HashSet` = O(1) operations, no order. `LinkedHashSet` = insertion order maintained. `TreeSet` = sorted order, O(log n). Choose based on whether order matters.

---

### Q85. Difference between `Map` and `HashMap`?
**Definition:** `Map<K,V>` is the read-only interface. `HashMap<K,V>` is the mutable, hash-table-based implementation.
**Core Idea:** Same separation as List/MutableList. `Map` = no puts. `HashMap` = mutable, O(1) get/put.
**How it Works:** `mapOf()` → read-only `Map`. `hashMapOf()` / `mutableMapOf()` → `HashMap`.
**Example:** `val map: Map<String, Int> = mapOf("a" to 1)`. `val hm: HashMap<String, Int> = hashMapOf("a" to 1)`.
**Interview Insight:** `HashMap` allows one null key and multiple null values. `LinkedHashMap` maintains insertion order. `TreeMap` maintains sorted key order.

---

### Q86. Difference between `IntArray` and `Array<Int>`?
**Definition:** `IntArray` is a primitive `int[]` on the JVM. `Array<Int>` is an array of boxed `Integer` objects.
**Core Idea:** `IntArray` = primitive, more memory-efficient, no boxing overhead. `Array<Int>` = boxed integers, interoperable with generics.
**How it Works:** `intArrayOf(1, 2, 3)` → `int[]` in bytecode. `arrayOf(1, 2, 3)` → `Integer[]` in bytecode.
**Example:** For numeric processing (math, signals), prefer `IntArray` — no boxing. For use with generics (`List<Array<Int>>`), need `Array<Int>`.
**Interview Insight:** Same distinction exists for `LongArray`, `FloatArray`, `DoubleArray`. On Android, prefer primitive arrays for large datasets to reduce GC pressure from boxing.

---

## Coroutines (Q87–Q91)

### Q87. What is a coroutine?
**Definition:** A suspendable computation — a unit of work that can be paused and resumed without blocking a thread.
**Core Idea:** Lightweight threads. Thousands of coroutines can run on a few threads. They don't block; they suspend.
**How it Works:** At a `suspend` point, the coroutine saves its state and frees the thread. When ready, it resumes on the same or different thread.
**Example:** `viewModelScope.launch { val data = fetchData() /* suspend here */ updateUI(data) }` — no thread blocking.
**Interview Insight:** Coroutines are NOT threads. They're more like tasks that cooperate to share threads. 10,000 coroutines on 4 threads is fine; 10,000 threads would crash the app.

---

### Q88. What is a suspend function?
**Definition:** A function marked with `suspend` that can be paused and resumed. Can only be called from another suspend function or a coroutine.
**Core Idea:** `suspend` = "this function might pause execution here. Don't block a thread while waiting."
**How it Works:** The compiler transforms suspend functions into state machines. A continuation object stores the paused state and resumes when the awaited work completes.
**Example:** `suspend fun fetchUser(id: String): User = withContext(Dispatchers.IO) { api.getUser(id) }`
**Interview Insight:** `suspend` does NOT mean it runs on a background thread. It means it can pause. Use `withContext(Dispatchers.IO)` to switch threads inside a suspend function.

---

### Q89. What is a coroutine scope?
**Definition:** Defines the lifetime of coroutines launched within it. When the scope is cancelled, all its child coroutines are cancelled.
**Core Idea:** Scopes enforce structured concurrency — no orphaned coroutines leak beyond their parent.
**How it Works:** `viewModelScope` is tied to ViewModel lifecycle. `lifecycleScope` is tied to Activity/Fragment. Custom: `CoroutineScope(Dispatchers.Main + job)`.
**Example:** `viewModelScope.launch { ... }` — cancelled automatically when ViewModel is cleared.
**Interview Insight:** Never use `GlobalScope` in production — it creates orphaned coroutines that can outlive the component that launched them. Always use a scoped option.

---

### Q90. What is a dispatcher?
**Definition:** Determines which thread or thread pool a coroutine runs on.
**Core Idea:** `Dispatchers.Main` = UI thread. `Dispatchers.IO` = I/O thread pool. `Dispatchers.Default` = CPU thread pool.
**How it Works:** `withContext(Dispatchers.IO) { ... }` switches the coroutine to the IO thread pool for that block.

| Dispatcher | Use for |
|---|---|
| `Dispatchers.Main` | UI updates, view manipulation |
| `Dispatchers.IO` | Network, DB, file I/O |
| `Dispatchers.Default` | CPU-intensive work (sorting, parsing) |
| `Dispatchers.Unconfined` | Testing, rarely in production |

**Interview Insight:** Similar to RxJava's `subscribeOn`/`observeOn`. Start in `viewModelScope` (Main), switch to IO for data, switch back to Main for UI.

---

### Q91. What is structured concurrency?
**Definition:** A paradigm where coroutines are organized in a parent-child hierarchy. A parent won't complete until all its children complete. Cancellation and errors propagate through the hierarchy.
**Core Idea:** No orphaned coroutines. Every coroutine has a scope/parent. Cancelling the parent cancels all children.
**How it Works:** `launch` creates a child coroutine in the current scope. The scope's `Job` tracks all children. `cancel()` on the scope propagates to all children.
**Example:** A ViewModel is cleared → `viewModelScope` is cancelled → all in-flight network calls are cancelled → no callbacks fire on dead ViewModel.
**Interview Insight:** Structured concurrency solves the "I forgot to cancel this background task" problem. It's why `viewModelScope` and `lifecycleScope` exist — they're structured scopes tied to lifecycle.

---

← [04 Kotlin Basics](04_kotlin_basics_classes.md) | [06 Android Framework →](06_android_framework_components.md)
