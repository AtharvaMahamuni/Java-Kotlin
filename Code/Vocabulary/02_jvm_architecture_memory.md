# Section 2 — JVM Architecture & Memory (Q20–Q41)

---

## JVM Architecture (Q20–Q29)

### Q20. What is the JVM?
**Definition:** Java Virtual Machine — an abstract machine that runs Java bytecode on any OS.
**Core Idea:** "Write once, run anywhere." The JVM is the layer between your code and the OS.
**How it Works:** Loads `.class` files → verifies bytecode → interprets or JIT-compiles to native code → manages memory (GC).
**Example:** Same `.class` file runs on Windows, Linux, macOS — each has its own JVM implementation.
**Interview Insight:** The JVM is NOT the same as Java. Kotlin, Scala, and Groovy also run on the JVM.

---

### Q21. What is the JDK?
**Definition:** Java Development Kit — everything you need to WRITE and compile Java code.
**Core Idea:** JDK = JRE + compiler (`javac`) + tools (debugger, jar, javadoc).
**How it Works:** You install JDK to develop. It includes the JRE so you can also run.
**Example:** Running `javac Hello.java` requires the JDK.
**Interview Insight:** On a production server, you only need JRE (to run). On a developer machine, you need JDK (to compile and run).

---

### Q22. What is the JRE?
**Definition:** Java Runtime Environment — everything needed to RUN (not compile) Java programs.
**Core Idea:** JRE = JVM + standard class libraries.
**How it Works:** User downloads JRE to run a Java app. No compiler included.
**Example:** Running `java Hello` requires only the JRE.
**Interview Insight:** JDK ⊃ JRE ⊃ JVM. Most modern distributions ship JDK even in runtime environments.

---

### Q23. What happens when Java code is compiled?
**Definition:** `javac` converts `.java` source files into `.class` files containing bytecode.
**Core Idea:** Source → (javac) → Bytecode → (JVM) → Native code.
**How it Works:** `javac Hello.java` produces `Hello.class`. The `.class` file is platform-independent bytecode, not machine code.
**Example:** `javac Dog.java` → `Dog.class` → `java Dog` runs it.
**Interview Insight:** Compilation only checks syntax/types. Bytecode is NOT native code — the JVM interprets or JIT-compiles it at runtime.

---

### Q24. What is bytecode?
**Definition:** An intermediate, platform-independent instruction set that the JVM executes.
**Core Idea:** Not machine code (CPU-specific), not source code. The JVM translates bytecode to native instructions.
**How it Works:** `javac` produces bytecode. At runtime, the JVM's interpreter or JIT compiler converts it to CPU instructions.
**Example:** `javap -c Hello.class` shows the bytecode instructions.
**Interview Insight:** Android doesn't run JVM bytecode — it converts `.class` files to DEX (Dalvik Executable) format via D8/R8.

---

### Q25. What is class loading?
**Definition:** The process of finding a `.class` file and loading it into the JVM memory.
**Core Idea:** Classes are loaded on demand (lazily), not all at startup.
**How it Works:** 3 phases: Loading (find & read .class) → Linking (verify + prepare + resolve) → Initialization (run static initializers).
**Example:** First time you use `new Dog()`, the JVM loads `Dog.class` if not already loaded.
**Interview Insight:** Classes are loaded only once per ClassLoader. Static blocks run during initialization, once.

---

### Q26. What is the classloader?
**Definition:** A component of the JVM responsible for loading class files into memory.
**Core Idea:** Delegation model — a classloader asks its parent first before trying to load itself.
**How it Works:** Three built-in classloaders: Bootstrap → Extension → Application. Custom classloaders possible.
**Example:** `Class.forName("com.example.Dog")` triggers classloading by the application classloader.
**Interview Insight:** The delegation model prevents duplicate loading and ensures core classes (like `java.lang.String`) are always loaded by the bootstrap loader.

---

### Q27. What is the bootstrap classloader?
**Definition:** The root classloader, written in native code. Loads core Java classes from `rt.jar` / `java.base` module.
**Core Idea:** Loads `java.lang`, `java.util`, etc. — the JDK foundation classes.
**How it Works:** Implemented in C++, not Java. Has no parent. `String.class.getClassLoader()` returns null (indicating bootstrap).
**Example:** `System.out.println(String.class.getClassLoader());` → prints `null`.
**Interview Insight:** Bootstrap loader is why you can't override core Java classes — it loads them first with highest priority.

---

### Q28. What is the extension classloader?
**Definition:** Loads classes from the JDK's extension directory (`jre/lib/ext`).
**Core Idea:** Sits between bootstrap and application classloaders. Loads optional Java extension libraries.
**How it Works:** If bootstrap doesn't find the class, extension loader tries `ext` directory.
**Example:** Cryptography extensions historically loaded via extension classloader.
**Interview Insight:** Largely deprecated in Java 9+ modular system. In practice, you rarely interact with it directly.

---

### Q29. What is the application classloader?
**Definition:** Loads classes from the application classpath — your code and third-party JARs.
**Core Idea:** The classloader you interact with most. Loads everything in `CLASSPATH`.
**How it Works:** Parent is extension classloader. First asks parent; if not found, loads from classpath.
**Example:** Your `MainActivity.class` is loaded by the application classloader.
**Interview Insight:** On Android, the equivalent is `PathClassLoader` (for installed APKs) and `DexClassLoader` (for dynamic loading).

---

## Memory Model (Q30–Q36)

### Q30. What is heap memory?
**Definition:** The JVM memory region where all objects and arrays are allocated at runtime.
**Core Idea:** Objects live here. Garbage collection manages this region.
**How it Works:** Split into Young Generation (Eden + Survivor) and Old Generation. New objects → Eden. Surviving objects → Old Gen.
**Example:** `new Dog()` allocates a Dog object on the heap.
**Interview Insight:** Heap size controlled by `-Xmx` (max) and `-Xms` (initial). Android's heap per app is limited (~256MB typical).

---

### Q31. What is stack memory?
**Definition:** Thread-local memory that stores method call frames (local variables + return address + operand stack).
**Core Idea:** One stack per thread. LIFO. Automatically managed — no GC needed.
**How it Works:** Each method call pushes a frame. Method return pops the frame. Local primitives and references live here.
**Example:** `int x = 5;` inside a method lives on the stack. `Dog d = new Dog();` — `d` (the reference) is on stack; the object is on heap.
**Interview Insight:** `StackOverflowError` = recursion too deep; the stack is full. Stack is fast — simple pointer move to allocate/free.

---

### Q32. What is the method area / metaspace?
**Definition:** JVM memory region that stores class metadata: class structure, static variables, method bytecode, constants.
**Core Idea:** One per JVM (not per thread/object). Class definitions live here.
**How it Works:** Called "PermGen" in Java 7 and earlier. Replaced by "Metaspace" in Java 8 (native memory, not heap).
**Example:** `static int count = 0;` — the `count` variable lives in metaspace, not the heap.
**Interview Insight:** Metaspace can grow dynamically (limited by OS memory). PermGen had a fixed size → PermGen OOM was a common issue in older Java apps.

---

### Q33. What is garbage collection?
**Definition:** Automatic memory management — the JVM identifies and frees objects that are no longer reachable.
**Core Idea:** No manual `free()` needed. GC runs periodically to reclaim unused heap memory.
**How it Works:** Mark reachable objects from GC roots → sweep unreachable objects → optionally compact. Stop-the-world pauses occur during GC.
**Example:** After `dog = null;`, if no other reference points to the Dog object, GC can collect it.
**Interview Insight:** You can suggest GC with `System.gc()` but can't force it. On Android, GC pauses cause dropped frames — avoid allocating in tight loops.

---

### Q34. What are GC roots?
**Definition:** The starting points from which the GC traces reachability. Any object reachable from a GC root is kept alive.
**Core Idea:** If an object is reachable (directly or transitively) from a GC root, it will NOT be collected.
**How it Works:** GC roots include: local variables on thread stacks, static variables, JNI references, active threads.
**Example:** A static map holding Activity references = GC root → Activity can never be collected = memory leak.
**Interview Insight:** Understanding GC roots is the key to debugging Android memory leaks. LeakCanary traces from GC roots to the leaked object.

---

### Q35. What is a memory leak?
**Definition:** When objects that are no longer needed remain reachable from GC roots and cannot be collected.
**Core Idea:** The GC can't collect what it thinks is still in use. Memory grows until OOM.
**How it Works:** A long-lived object (singleton, static field) holds a reference to a short-lived object (Activity, Context).
**Example:** `static Context appContext = activity;` — Activity is never GC'd because the static field is a GC root.
**Interview Insight:** In Android: common leaks are static Context, inner classes (hold outer class reference), uncancelled listeners/callbacks. Use WeakReference for optional back-references.

---

### Q36. What is object allocation?
**Definition:** The process of reserving memory on the heap for a new object.
**Core Idea:** `new` triggers allocation. Fast in Java (bump pointer allocation in Eden).
**How it Works:** JVM uses TLAB (Thread-Local Allocation Buffer) per thread for fast allocation without locking.
**Example:** In a RecyclerView `onBindViewHolder` called 60fps × items — avoid `new` here; prefer object reuse.
**Interview Insight:** Frequent allocation triggers GC → pauses → dropped frames on Android. Profile with Android Studio Memory Profiler.

---

## Generics (Q37–Q41)

### Q37. What are generics?
**Definition:** A mechanism to parameterize types, enabling type-safe collections and methods without casting.
**Core Idea:** Write one class/method that works with any type. The compiler enforces type safety.
**How it Works:** `List<String>` tells the compiler only Strings allowed. No cast needed on retrieval.
**Example:** `List<String> names = new ArrayList<>();` vs old `List names = new ArrayList();` (requires casting + possible ClassCastException).
**Interview Insight:** Generics are compile-time only. At runtime, the type parameter is erased (type erasure).

---

### Q38. What is type erasure?
**Definition:** The JVM removes all generic type information at runtime. `List<String>` becomes `List` at runtime.
**Core Idea:** Generics are a compile-time illusion. The bytecode has no type parameters.
**How it Works:** Compiler adds casts automatically. `list.get(0)` becomes `(String) list.get(0)` in bytecode.
**Example:** `List<String>` and `List<Integer>` are the SAME type at runtime: both are just `List`.
**Interview Insight:** This is why you can't do `new T()` or `instanceof List<String>`. Also why Kotlin uses `reified` (inline functions) to work around this.

---

### Q39. Why do generics exist?
**Definition:** To provide compile-time type safety without performance overhead.
**Core Idea:** Before generics (Java 1.4), everything was `Object`. You'd get `ClassCastException` at runtime. Generics catch this at compile time.
**How it Works:** The compiler rejects type mismatches: `List<String> list; list.add(42);` → compile error.
**Example:** Old way: `String s = (String) list.get(0);` — crashes at runtime if wrong type. New way: compile-time error.
**Interview Insight:** Generics add zero runtime cost (type erasure). It's purely a compile-time tool for correctness.

---

### Q40. What are bounded generics?
**Definition:** Restricting the type parameter to a certain type or its subtypes/supertypes.
**Core Idea:** `<T extends Number>` means T can be Number or any subclass (Integer, Double, etc.).
**How it Works:**
- Upper bound: `<T extends Number>` — T must be Number or subtype
- Lower bound (wildcard only): `<? super Integer>` — ? must be Integer or supertype
**Example:** `double sum(List<? extends Number> list)` — works with `List<Integer>`, `List<Double>`, etc.
**Interview Insight:** Producer Extends, Consumer Super (PECS): use `? extends` when reading, `? super` when writing.

---

### Q41. What is wildcard usage in generics?
**Definition:** `?` is a wildcard representing an unknown type. Used for flexibility in method parameters.
**Core Idea:** `List<?>` = a list of some unknown type. More flexible than `List<Object>`.
**How it Works:**
- `List<?>` — unknown type (can read as Object, can't add)
- `List<? extends T>` — read-only, any subtype of T
- `List<? super T>` — write-friendly, any supertype of T
**Example:** `void printAll(List<?> list)` — accepts `List<String>`, `List<Integer>`, etc.
**Interview Insight:** You can't add to `List<?>` (except null) because the compiler doesn't know the actual type. Use `? extends` for read-only, `? super` for write.

---

← [01 Java Core Language](01_java_core_language.md) | [03 Serialization & Concurrency →](03_java_serialization_concurrency.md)
