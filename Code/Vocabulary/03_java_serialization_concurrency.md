# Section 3 — Serialization & Concurrency (Q42–Q52)

---

## Serialization (Q42–Q45)

### Q42. What is serialization?
**Definition:** Converting an object's state into a byte stream so it can be stored or transmitted.
**Core Idea:** Object → bytes. Useful for saving state to disk or sending over a network.
**How it Works:** Implement `Serializable`, then use `ObjectOutputStream.writeObject(obj)`.
**Example:** Saving a `User` object to a file or passing it between Android processes via Intent (though Parcelable is preferred on Android).
**Interview Insight:** On Android, prefer `Parcelable` over `Serializable` — it's 10x faster because it avoids reflection.

---

### Q43. What is deserialization?
**Definition:** Converting a byte stream back into an object.
**Core Idea:** Bytes → Object. The reverse of serialization.
**How it Works:** Use `ObjectInputStream.readObject()`. The class must still exist and the `serialVersionUID` must match.
**Example:** Reading a saved `User` object back from a file.
**Interview Insight:** Deserialization can execute arbitrary code — it's a known security vulnerability (Java deserialization attacks). Never deserialize untrusted data.

---

### Q44. What is the `Serializable` interface?
**Definition:** A marker interface (no methods) that tells the JVM this class can be serialized.
**Core Idea:** Just implementing this interface enables Java's built-in serialization mechanism.
**How it Works:** Add `implements Serializable`. Optionally define `private static final long serialVersionUID = 1L;` to control version compatibility.
**Example:** `class User implements Serializable { String name; int age; }`
**Interview Insight:** `transient` fields are skipped during serialization. If `serialVersionUID` doesn't match on deserialization, `InvalidClassException` is thrown.

---

### Q45. Difference between Serializable and Externalizable?

| | Serializable | Externalizable |
|---|---|---|
| Control | JVM controls serialization | You control it completely |
| Methods | None (marker interface) | `writeExternal()` + `readExternal()` |
| Performance | Slower (reflection) | Faster (custom logic) |
| Fields | All non-transient serialized | Only what you explicitly write |

**Interview Insight:** `Externalizable` is used when you need fine-grained control (e.g., skip certain fields without `transient`, or serialize in a custom format).

---

## Concurrency (Q46–Q52)

### Q46. What is a thread?
**Definition:** The smallest unit of CPU execution. A lightweight sub-process that runs independently within a process.
**Core Idea:** Multiple threads in one process share the same heap memory but have their own stack.
**How it Works:** Create via `new Thread(runnable).start()` or an `ExecutorService`. The OS scheduler decides when each thread runs.
**Example:** Android's main thread renders UI; a background thread fetches network data.
**Interview Insight:** Thread creation is expensive. On Android, use `Kotlin Coroutines` or `RxJava` instead of raw threads. Never do I/O on the main thread.

---

### Q47. What is a process?
**Definition:** An independent program instance with its own memory space (heap, stack, code segment).
**Core Idea:** Processes are isolated from each other. Threads within a process share memory.
**How it Works:** The OS creates a process when you launch an app. Each Android app runs in its own process by default.
**Example:** Opening Maps and Chrome are two separate processes — one crashing doesn't kill the other.
**Interview Insight:** On Android, components in the same app can be declared to run in separate processes (`android:process=":background"` in manifest). IPC (Binder) is needed to communicate between processes.

---

### Q48. What is multithreading?
**Definition:** Running multiple threads concurrently within a single process.
**Core Idea:** Improves throughput by doing work in parallel (e.g., UI on main thread, network on IO thread).
**How it Works:** Threads share heap memory. The OS or JVM schedules them. True parallelism requires multiple CPU cores.
**Example:** Fetching user data + loading images simultaneously — two threads doing work in parallel.
**Interview Insight:** Multithreading introduces race conditions and deadlocks. On Android: UI thread + background threads for I/O is the standard pattern.

---

### Q49. What is synchronization?
**Definition:** A mechanism to ensure only one thread accesses a critical section at a time.
**Core Idea:** Prevents race conditions by serializing access to shared resources.
**How it Works:** `synchronized` keyword acquires a monitor lock on an object. Other threads block until the lock is released.
**Example:** `synchronized void increment() { count++; }` — only one thread runs this at a time.
**Interview Insight:** `synchronized` has overhead. Prefer higher-level concurrency tools: `AtomicInteger`, `ConcurrentHashMap`, `ReentrantLock`, or Coroutines on Android.

---

### Q50. What is a race condition?
**Definition:** A bug where the program's behavior depends on the timing/ordering of thread execution.
**Core Idea:** Two threads read-modify-write a shared variable without synchronization → unpredictable result.
**How it Works:** Thread A reads count=5, Thread B reads count=5, both increment → both write 6. Expected: 7. Actual: 6.
**Example:** `count++` is NOT atomic — it's read + increment + write. Two threads doing this simultaneously lose updates.
**Interview Insight:** Use `AtomicInteger.incrementAndGet()` or `synchronized` to prevent race conditions. Kotlin `StateFlow` and `Channel` are designed to be thread-safe.

---

### Q51. What is a deadlock?
**Definition:** Two or more threads are blocked forever, each waiting for a resource held by the other.
**Core Idea:** Thread A holds Lock 1, wants Lock 2. Thread B holds Lock 2, wants Lock 1. Both wait forever.
**How it Works:** Requires 4 conditions: mutual exclusion, hold and wait, no preemption, circular wait.
**Example:**
```
Thread A: lock(lockA); lock(lockB);
Thread B: lock(lockB); lock(lockA);  // deadlock!
```
**Interview Insight:** Prevent by always acquiring locks in the same order. Or use `tryLock()` with timeout. Android: avoid holding locks during IPC calls.

---

### Q52. What is thread safety?
**Definition:** Code that works correctly when accessed by multiple threads simultaneously, without external synchronization.
**Core Idea:** A thread-safe class protects its own state from concurrent modification.
**How it Works:** Achieved via immutability, `synchronized`, atomic operations, thread-local storage, or higher-level constructs (Coroutines, RxJava).
**Example:** `String` is thread-safe (immutable). `ArrayList` is NOT thread-safe. `CopyOnWriteArrayList` is thread-safe.
**Interview Insight:** Immutability is the easiest way to achieve thread safety — no shared mutable state means no synchronization needed.

---

← [02 JVM Architecture](02_jvm_architecture_memory.md) | [04 Kotlin Basics →](04_kotlin_basics_classes.md)
