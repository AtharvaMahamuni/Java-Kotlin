# Master Follow-Up Chains

> These are the interview chains — each link is a question that naturally leads to the next. Interviewers follow these paths to find where your knowledge ends.
> **How to use:** Each node shows the question, then the answer with the mechanism behind it. The indentation shows how interviewers drill deeper. Read each chain end-to-end before an interview.

## Navigation — Master Index

| Phase | File | Questions |
|-------|------|-----------|
| 0 — JVM Mental Model | [00_jvm_mental_model.md](00_jvm_mental_model.md) | Q0.1 · Q0.2 · Q0.3 · Q0.4 · Q0.5 |
| 1 — Type System | [01_type_system_foundations.md](01_type_system_foundations.md) | Q1.1 · Q1.2 · Q1.3 · Q1.4 |
| 2 — Classes & Objects | [02_classes_and_objects.md](02_classes_and_objects.md) | Q2.1 · Q2.2 · Q2.3 · Q2.4 · Q2.5 |
| 2.5 — Initialization | [02_5_initialization_mechanics.md](02_5_initialization_mechanics.md) | Q2.5.1 · Q2.5.2 · Q2.5.3 · Q2.5.4 · Q2.5.5 · Q2.5.6 |
| 3 — Generics & Variance | [03_generics_and_variance.md](03_generics_and_variance.md) | Q3.1 · Q3.2 · Q3.3 · Q3.4 |
| 4 — Functions & Lambdas | [04_functions_lambdas_inlining.md](04_functions_lambdas_inlining.md) | Q4.1 · Q4.2 · Q4.3 · Q4.4 · Q4.5 |
| 5 — Properties & Delegation | [05_properties_and_delegation.md](05_properties_and_delegation.md) | Q5.1 · Q5.2 · Q5.3 |
| 6 — Extension Functions | [06_extension_functions.md](06_extension_functions.md) | Q6.1 · Q6.2 · Q6.3 |
| 7 — Collections & Sequences | [07_collections_and_sequences.md](07_collections_and_sequences.md) | Q7.1 · Q7.2 · Q7.3 |
| 8 — Other Kotlin Features | [08_other_kotlin_features.md](08_other_kotlin_features.md) | Q8.1 · Q8.2 · Q8.3 |
| 9 — Coroutines Mechanics | [09_coroutines_execution_mechanics.md](09_coroutines_execution_mechanics.md) | Q9.1 · Q9.2 · Q9.3 · Q9.4 |
| 10 — Structured Concurrency | [10_structured_concurrency.md](10_structured_concurrency.md) | Q10.1 · Q10.2 · Q10.3 · Q10.4 · Q10.5 · Q10.6 |
| 11 — Flow | [11_flow.md](11_flow.md) | Q11.1 · Q11.2 · Q11.3 · Q11.4 · Q11.5 |
| 12 — Reflection & References | [12_reference_operators_and_reflection.md](12_reference_operators_and_reflection.md) | Q12.1 · Q12.2 |
| 13 — Android Architecture | [13_android_architecture.md](13_android_architecture.md) | Q13.1 · Q13.2 · Q13.3 · Q13.4 · Q13.5 · Q13.6 · Q13.7 |
| 14 — Jetpack Components | [14_jetpack_components.md](14_jetpack_components.md) | Q14.1 · Q14.2 · Q14.3 · Q14.4 |
| 15 — Networking | [15_networking.md](15_networking.md) | Q15.1 · Q15.2 · Q15.3 |
| 16 — Android System Internals | [16_android_system_internals.md](16_android_system_internals.md) | Q16.1 · Q16.2 · Q16.3 · Q16.4 · Q16.5 |
| 17 — Performance & Memory | [17_performance_and_memory.md](17_performance_and_memory.md) | Q17.1 · Q17.2 · Q17.3 · Q17.4 |
| **Master Chains** | ← You are here | Chains A–K |

---

## Chain A — Constants

*"Tell me about `val` vs `const val`."*
> **What the interviewer is testing:** Do you know what Kotlin properties compile to, or do you think `val` is just a "read-only variable"?

```
val BASE_URL = "https://api.example.com"   [Q1.1]
    │
    ├──► Compiles to a private backing field + a public getter: getBASE_URL()   [Q0.4]
    │    WHY: In Kotlin, every property is an abstraction over a field+accessor pair.
    │    Even a simple val is a method call at the JVM level: INVOKEVIRTUAL.
    │    This means class loading is required before any access, and every read
    │    goes through a method dispatch.
    │
val vs const val — what's the difference?
    │
    ├──► const val TAG = "MyActivity"
    │    └──► Inlined as an LDC (load constant) instruction at every call site.   [Q1.1]
    │         There is NO method call, NO class loading, NO backing field.
    │         The compiler bakes the string literal directly into the caller's bytecode.
    │         Effect: zero runtime cost — identical to a Java public static final constant.
    │
Why can't `const val TAG = SomeClass::class.simpleName`?
    │
    ├──► simpleName is evaluated at runtime via KClass reflection.   [Q3.3]
    │    const val requires a compile-time constant — a value the compiler can
    │    evaluate during compilation before any class is loaded.
    │    The three constraints on const val:
    │      1. Type must be primitive or String (not even Long? counts)
    │      2. Value must be computable at compile time (literal or expression of literals)
    │      3. Declared at top-level or in a companion object (not inside a function)
    │
@JvmField vs const val — aren't they the same?
    │
    └──► Different in a critical way:   [Q1.1]
         @JvmField: eliminates the getter — exposes the field directly in bytecode.
           Callers read the field with GETFIELD (one instruction, no method overhead).
           BUT the field is still initialized at runtime when the class is loaded.
         const val: not just field elimination — the VALUE is inlined into caller bytecode.
           There is no field at all. The class doesn't even need to be loaded.

         BINARY COMPATIBILITY HAZARD:
         If you change `const val VERSION = 1` to `const val VERSION = 2` in a library
         and ship only the library JAR (without recompiling callers), every caller still
         has the old value `1` baked into their bytecode. This is a silent, hard-to-find bug.
         @JvmField does not have this problem: callers read the field at runtime.
```

---

## Chain B — Initialization Order

*"What is the difference between a primary constructor and an `init` block?"*
> **What the interviewer is testing:** Whether you understand how Kotlin maps its syntax to a single JVM `<init>` method, and whether you know the dangerous ordering trap.

```
Primary constructor parameters vs init block   [Q2.5.1]
    │
    ├──► Both compile to the SAME `<init>()` method in the class bytecode.
    │    There is no separate "primary constructor method" and "init method."
    │    The compiler merges them into one method in declaration order.
    │
What is the exact execution order?
    │
    ├──► Interleaved, strictly in order of appearance in the source file:   [Q2.5.1]
    │    property initializer 1 → init block 1 → property initializer 2 → init block 2 ...
    │
    │    WHY this matters — the forward-reference bug:
    │    class Foo {
    │        val double = num * 2    // ← BUG: num not initialized yet!
    │        val num = 5
    │    }
    │    double = 0 (not 10), because `num * 2` runs before `val num = 5`.
    │    Kotlin does NOT re-order for correctness. Declaration order is execution order.   [Q2.5.5]
    │
What about secondary constructors?
    │
    ├──► Secondary constructors MUST delegate to the primary via `this(...)`.   [Q2.5.2]
    │    WHY: The JVM requires that every constructor call either super() or this() as its
    │    first action. Kotlin enforces this at language level.
    │    Order: primary constructor body (including all init blocks) runs FIRST,
    │    then the secondary constructor body runs. You cannot bypass primary init.
    │
What happens in a subclass?
    │
    ├──► Superclass <init> always runs BEFORE subclass <init>.   [Q2.5.3]
    │    This is a JVM rule, not just Kotlin.
    │
    │    THE INFAMOUS TRAP:
    │    open class Base {
    │        init { printValue() }         // ← called during Base <init>
    │        open fun printValue() { ... }
    │    }
    │    class Child : Base() {
    │        val value = "hello"
    │        override fun printValue() { println(value) }  // prints NULL
    │    }
    │    WHY: When Base.init{} calls printValue(), the Child object exists in memory
    │    but Child's <init> has NOT run yet. `value` is still null (its default
    │    before assignment). The override dispatches to Child.printValue() but sees
    │    an uninitialized field.   [Q2.5.3]
    │
When does the companion object initialize?
    │
    └──► Lazily — on first access to a non-const member.   [Q2.5.4]
         const val access does NOT trigger companion init (inlined at compile time,
         no class loading needed). This is why companion objects can hold expensive
         resources (e.g., a Regex or a database) without paying the cost at startup.

         DEADLOCK TRAP:
         If Object A's companion init accesses Object B, and Object B's companion init
         accesses Object A → class initialization deadlock. The JVM holds a per-class
         lock during `<clinit>`. Circular init dependencies cause both threads to wait forever.
```

---

## Chain C — Nullability to `lateinit`

*"What's the difference between `String` and `String?`?"*
> **What the interviewer is testing:** Whether you know Kotlin's null safety is purely compile-time, and whether you understand the JVM null representation.

```
String vs String? at the JVM level   [Q1.2]
    │
    ├──► They are the SAME JVM type: java.lang.String.
    │    The difference exists only in the Kotlin compiler's type checker.
    │    String is annotated @NotNull; String? is annotated @Nullable.
    │    At bytecode level, both are just object references. The JVM doesn't know
    │    about Kotlin's null safety — the compiler enforces it before bytecode is generated.
    │
What is a platform type (String!)?
    │
    ├──► When Kotlin calls Java code with no @Nullable/@NotNull annotation,   [Q1.2]
    │    the Kotlin compiler doesn't know if the value can be null.
    │    It treats it as a platform type — displayed as `String!` in IDE tooltips.
    │    You can assign it to either `String` or `String?`.
    │    Risk: assigning `String!` to `String` (non-nullable) is allowed by the compiler,
    │    but if the Java code actually returns null, you get an NPE at the assignment site —
    │    not where you use the string. Silent and confusing to debug.
    │
Why can't `Int` be null?
    │
    ├──► `Int` in Kotlin maps to the JVM primitive `int` — 4 bytes of memory.   [Q0.2]
    │    Primitives are not objects. There is no object header, no null pointer.
    │    null is a sentinel value meaning "this reference points to nothing."
    │    A primitive int CAN'T point to anything — it holds the value directly.
    │    `Int?` maps to `java.lang.Integer` (boxed) — an object on the heap that CAN be null.
    │
So why does `lateinit var count: Int` fail to compile?
    │
    ├──► lateinit works by using `null` as the "not yet initialized" sentinel.   [Q5.1]
    │    When you access a lateinit var before init, the compiler inserts a null check
    │    and throws UninitializedPropertyAccessException if it finds null.
    │    `Int` maps to primitive `int` — there is no null state. You cannot use null
    │    as a sentinel for a primitive. The compiler rejects this at compile time.
    │    Solution: use `Delegates.notNull<Int>()` instead.
    │
How does `Delegates.notNull<Int>()` work then?
    │
    ├──► It stores the value as `Any?` (a boxed reference, nullable Object).   [Q5.3]
    │    The initial value of the Any? field is null.
    │    On read, it checks if the stored value is null and throws IllegalStateException.
    │    On write, it stores the provided value (boxing the Int to Integer).
    │    Trade-off: every read/write now involves boxing — slightly more overhead
    │    than a regular Int field.
    │
How does `::property.isInitialized` work?
    │
    └──► For lateinit var, the compiler generates a check that reads the backing field
         and compares it to null. It's a simple IFNULL bytecode instruction — NOT
         a reflection call. No KClass lookup, no Method invocation.   [Q5.1]
         Performance: identical to if (field != null).
         Restriction: you can only call ::property.isInitialized from within the class
         (or its companion). External callers can't check — it's class-private.
         This prevents TOCTOU races: check→use is only safe within the same class.
```

---

## Chain D — Generics to Reified

*"Why does `list is List<String>` fail at runtime?"*
> **What the interviewer is testing:** Type erasure understanding — one of the most-asked generics questions — and whether you know the reified workaround.

```
Type erasure — what is it and WHY does it exist?   [Q3.1]
    │
    ├──► At compile time, the Kotlin/Java compiler knows that `list` is `List<String>`.
    │    At runtime, after compilation, all generic type arguments are ERASED.
    │    `List<String>` and `List<Int>` become the same type `List` in bytecode.
    │    WHY: Java 5 introduced generics in 2004. Millions of `.class` files compiled
    │    with Java 1.4 used raw `List`. To remain binary-compatible — so old code and
    │    new generic code could coexist — the JVM format was not changed.
    │    Type arguments exist only in source code and `.class` metadata (for reflection),
    │    but not in the actual bytecode instructions that check types.
    │
So why does `list is List<String>` fail?
    │
    ├──► The `is` check compiles to a CHECKCAST instruction at runtime.
    │    At runtime, there is no `List<String>` to check against — only `List`.
    │    The compiler refuses to compile `is List<String>` because it knows the check
    │    would always succeed for any List (since all Lists are erased to List).
    │    `list is List<*>` works — it checks that the object is a List, ignoring element type.
    │
What about variance — out T and in T?   [Q3.2]
    │
    ├──► out T (covariant): you can only READ T from the container, never write.
    │    WHY this is safe: if you can only read, you always get an Animal or a subtype.
    │    Reading a Dog as an Animal is always safe (Dog IS-A Animal).
    │    `List<out Animal>` accepts a `List<Dog>` because you can only read from it.
    │
    ├──► in T (contravariant): you can only WRITE T to the container, never read.
    │    WHY this is safe: if Container<Animal> accepts any Animal, passing it a Dog
    │    (a subtype of Animal) is safe — Dog IS-A Animal, so it fits.
    │    `Comparator<in Dog>` accepts a `Comparator<Animal>` because comparing Dogs
    │    with an Animal comparator always works.
    │
    └──► Both variance annotations are compile-time only. At runtime, both
         `List<out Animal>` and `List<in Animal>` are erased to just `List`.
    │
How does `reified` defeat erasure?   [Q3.3]
    │
    ├──► reified only works on inline functions. When the compiler inlines a function,
    │    it copies the function body to every call site. At each call site, the
    │    concrete type is known — so the compiler substitutes T with the actual type.
    │    The CHECKCAST/instanceof check in the inlined body uses the real type,
    │    not a type parameter that would be erased.
    │
    ├──► Real example: `startActivity<DetailActivity>(context)`
    │    inline fun <reified T: Activity> Context.startActivity() {
    │        startActivity(Intent(this, T::class.java))
    │    }
    │    At the call site, T is DetailActivity. After inlining, the bytecode reads:
    │    Intent(this, DetailActivity::class.java) — a concrete class reference.
    │    No erasure problem, because the type was substituted before compilation.   [Q3.3]
    │
Why can't a class have a reified type parameter?
    │
    └──► Classes are instantiated with `new ClassName()` — the JVM allocates an object.
         There is no inlining of class bodies. The class is compiled once and used many
         times for different type arguments. Since reified requires inlining to work,
         and class bodies can't be inlined, class type parameters can never be reified.
         Only function type parameters can be reified (because functions can be inlined).
```

---

## Chain E — ViewModel to Process Death

*"How does ViewModel survive rotation?"*
> **What the interviewer is testing:** Whether you know the retention mechanism — not just "it uses ViewModelStore" but HOW ViewModelStore survives the destroy-create cycle.

```
ViewModel survives configuration change — HOW exactly?   [Q13.3]
    │
    ├──► The Activity has a method: onRetainNonConfigurationInstance().
    │    Before the Activity is destroyed for rotation, the system calls this method.
    │    ViewModelStore overrides this to return itself (the container holding ViewModels).
    │    When the new Activity is created, it calls getLastNonConfigurationInstance()
    │    to retrieve the ViewModelStore from the previous Activity.
    │    The ViewModel is NEVER destroyed — the Activity wrapping it is recreated,
    │    but the ViewModel object in the ViewModelStore is the same object.
    │    WHY the ViewModel must not hold Activity/View references: the old Activity
    │    is destroyed. If the ViewModel holds a reference to it, the old Activity
    │    cannot be garbage-collected → memory leak.   [Q13.3]
    │
Does ViewModel survive process death?
    │
    ├──► NO. ViewModelStore is an in-memory object in the app process.   [Q13.3]
    │    When the OS kills the process (SIGKILL), ALL memory is reclaimed instantly.
    │    The JVM is not given a chance to run onDestroy(), finalizers, or any cleanup.
    │    When the user returns to the app, a fresh process is started.
    │    ViewModelStore starts empty — all ViewModels are new instances.
    │
What DOES survive process death?
    │
    ├──► SavedStateHandle — it is hooked into the Activity's onSaveInstanceState.   [Q13.3]
    │    Before the process is killed, the system serializes the Bundle to disk.
    │    WHY this works: onSaveInstanceState is called by the system before it
    │    kills the process (or before stop, on API 28+). The system writes the Bundle
    │    as a Parcel to disk via Binder to system_server. On next launch, the system
    │    reads this Bundle back and passes it to onCreate.
    │    SavedStateHandle gives ViewModels access to this Bundle transparently.
    │
What are the Bundle size limits?
    │
    ├──► Binder has a 1MB limit for all active transactions in a process.   [Q16.3]
    │    A Bundle is serialized and transmitted via Binder to system_server.
    │    If the Bundle exceeds ~500KB (to leave headroom for other transactions),
    │    you risk TransactionTooLargeException — a crash that is hard to reproduce
    │    and confusing because it comes from deep in the system stack.
    │    Rule: store only primitive/small data in Bundle — IDs, selected index,
    │    tab position, search query. Never put bitmaps, large lists, or full objects.
    │
What about large in-memory data across process death?
    │
    └──► You cannot preserve it. Instead, save the KEY (e.g., the entity ID) in the Bundle.
         On restart, the ViewModel reads the ID from SavedStateHandle and re-fetches
         the data from Room (local database) or the network.
         This is the correct pattern:
           SavedStateHandle → stores the ID (primitive, Bundle-safe)
           Room → stores the actual data (disk-persisted, survives process death)
           ViewModel → re-queries Room on startup using the saved ID
```

---

## Chain F — Coroutine Cancellation

*"What does `suspend` actually do?"*
> **What the interviewer is testing:** Whether you understand the compiler transformation, not just "it pauses the function."

```
suspend = Continuation Passing Style (CPS) transformation   [Q9.1]
    │
    ├──► The Kotlin compiler rewrites every suspend function. It adds a hidden
    │    `Continuation<T>` parameter and converts the function body into a state machine.
    │    The state machine uses a `label` field to remember which suspension point
    │    to resume at. suspend fun foo(): String becomes foo(continuation: Continuation<String>): Any.
    │    Return type is Any because the function either returns a value (fast path)
    │    or returns the sentinel COROUTINE_SUSPENDED (suspending path).
    │
Where are local variables stored during suspension?
    │
    ├──► On the HEAP — promoted to fields on the Continuation object.   [Q9.1]
    │    Normal JVM methods store locals in the stack frame. When the method returns,
    │    the stack frame is popped and locals are gone.
    │    A suspend function must be resumable on a DIFFERENT thread — potentially
    │    long after the original stack frame is gone. The Continuation object (on the heap)
    │    holds these locals as fields until the function resumes.
    │    Cost: one heap allocation per coroutine launch (the state machine object).
    │    Kotlin optimizes: variables NOT live across a suspension point stay on the stack.
    │
Does `suspend` mean the function runs on a background thread?
    │
    ├──► NO. suspend is about calling convention, not threading.   [Q9.1]
    │    It means: this function may pause and resume via a Continuation callback.
    │    WHERE the function runs is determined entirely by the Dispatcher in its CoroutineContext.
    │    A suspend function on Dispatchers.Main runs on the main thread.
    │    The same function on Dispatchers.IO runs on an IO thread pool thread.
    │    Common interview mistake: "I made it suspend so it runs in background." Wrong.
    │    You must also switch to the right Dispatcher (withContext or coroutineScope).
    │
What is CancellationException and why must it be re-thrown?   [Q10.3]
    │
    ├──► When job.cancel() is called, the cancellation is cooperative: the coroutine is NOT
    │    killed immediately. Instead, at the next suspension point, the runtime resumes
    │    the coroutine with Result.failure(CancellationException).
    │    The state machine calls ResultKt.throwOnFailure(), which throws CancellationException
    │    at the current suspension point — appearing as if the suspended function threw it.
    │    If you catch(e: Exception) and swallow it, you catch CancellationException too.
    │    The coroutine then continues executing — it is no longer aware it was cancelled.
    │    The parent scope never knows the child finished — resources are held indefinitely.
    │    FIX: always use catch(e: CancellationException) { throw e } or catch specific types.
    │
What if I have cleanup to do on cancellation?
    │
    ├──► Use try { ... } finally { ... }. The finally block ALWAYS runs.   [Q10.3]
    │    Even when CancellationException is thrown, finally runs.
    │    But: inside finally, if the coroutine is cancelled, calling ANY suspend function
    │    will throw CancellationException again immediately.
    │    Use NonCancellable to run suspend code in finally:
    │    finally { withContext(NonCancellable) { db.save() } }
    │
How do viewModelScope and lifecycleScope auto-cancel?
    │
    └──► viewModelScope is a CoroutineScope with a SupervisorJob.   [Q13.3]
         ViewModel.onCleared() calls viewModelScope.cancel() — called when the ViewModel
         is permanently destroyed (user leaves the screen with finish(), not rotation).
         WHY SupervisorJob: sibling coroutines in viewModelScope don't cancel each other.
         A failing network call doesn't cancel an unrelated animation coroutine.

         lifecycleScope is cancelled when the lifecycle reaches DESTROYED state.
         repeatOnLifecycle(STARTED): starts a new coroutine each time lifecycle reaches
         STARTED (foreground), cancels it when lifecycle drops below STARTED (background).
         This is how you stop collecting Flow when the screen is in the background.   [Q11.4]
```

---

## Chain G — Flow to StateFlow

*"What is a cold Flow?"*
> **What the interviewer is testing:** Cold vs hot understanding, and whether you know the StateFlow duplicate-filtering bug that kills navigation events.

```
Cold Flow — producer runs per collector   [Q11.1]
    │
    ├──► A cold Flow is a lazy definition of a data pipeline. The flow { } block
    │    is NOT executed when you create the Flow — it executes when you call collect{}.
    │    Each collector gets its own independent execution of the producer.
    │    Two collectors on the same cold Flow trigger two separate network calls (or two
    │    separate DB queries). Like a factory function, not a running machine.
    │    Analogy: a cold Flow is like a video file — each viewer starts from the beginning.
    │
What makes StateFlow and SharedFlow hot?
    │
    ├──► They have a producer that runs independently of collectors.   [Q11.3]
    │    A hot Flow is like a live TV broadcast — it runs regardless of how many viewers
    │    are watching. Collectors tap into the ongoing stream.
    │    If you collect a StateFlow mid-stream, you receive the CURRENT value immediately
    │    (replay=1 always). You may have missed earlier values.
    │    WHY hot flows for UI state: the ViewModel computes state once, and multiple
    │    UI components (different Composables, or a Fragment + child Fragment) can all
    │    observe the same StateFlow without triggering redundant computation.
    │
How do you convert a cold Flow to hot?
    │
    ├──► stateIn(scope, started, initialValue) → StateFlow   [Q11.3]
    │    Starts the upstream cold Flow in `scope`. The upstream runs once regardless of
    │    collector count. Collectors see the current value. Unsubscribed states controlled by `started`.
    │    shareIn(scope, started, replay) → SharedFlow
    │    Like stateIn but allows configuring how many past values new collectors see.
    │
    │    started strategies for shareIn / stateIn:
    │    Eagerly: starts immediately, never stops (use for app-wide hot data)
    │    Lazily: starts on first collector, never stops after that
    │    WhileSubscribed(5000): starts when first collector appears, stops 5 seconds
    │      after last collector disappears. The 5-second grace period survives
    │      configuration changes (rotation takes ~1 second).
    │
StateFlow skips duplicate consecutive emissions — why is this a bug for navigation?
    │
    ├──► StateFlow uses equals() to compare the new value against the current value.   [Q11.3]
    │    If new == current, the emission is dropped — no collectors are notified.
    │    For UI state (showing a list of users), this is desirable: don't redraw if data didn't change.
    │    For EVENTS (navigate to screen X), this is catastrophic:
    │    User taps "Open Details" → StateFlow emits NavigateToDetail
    │    User is on Details screen, presses back → flow still holds NavigateToDetail
    │    User taps "Open Details" again → StateFlow receives NavigateToDetail again
    │    equals() matches → DROPPED. Navigation never fires. Silent bug.
    │
How to fix navigation events?
    │
    ├──► SharedFlow(replay=0) — no initial value, no duplicate filter.   [Q11.3]
    │    Each emission goes through regardless of previous value.
    │    Caveat: replay=0 means if the collector is not active when the event is emitted,
    │    the event is lost. Use this with repeatOnLifecycle(STARTED) to ensure the collector
    │    is always active when the screen is visible.
    │    Alternative: Channel(BUFFERED) — queue semantics, exactly-once delivery.
    │    The "Consuming Events" architecture pattern uses a Channel for navigation.
    │
Why does `collectAsStateWithLifecycle` matter vs `collectAsState`?
    │
    └──► collectAsState collects the Flow unconditionally — even when the Composable
         is in the background (paused or stopped). This wastes CPU, keeps threads active,
         and can process UI updates that will never reach the screen.
         collectAsStateWithLifecycle pauses collection when the lifecycle drops below STARTED
         (the defined minimum state). Collection automatically resumes when the app returns
         to foreground.   [Q11.4]
         WHY this matters for battery: a chat app using collectAsState continues processing
         incoming message events even while the user is on a different app.
```

---

## Chain H — Structured Concurrency

*"What's the difference between `launch` and `async`?"*
> **What the interviewer is testing:** Exception propagation semantics, which is one of the most misunderstood areas in coroutines.

```
launch returns Job — async returns Deferred<T>   [Q9.3]
    │
    ├──► Deferred<T> extends Job. It adds one thing: the ability to await() the result.
    │    launch: fire-and-forget. You don't get the return value.
    │    async: concurrent computation. You get a future-like Deferred<T>.
    │    await() suspends until the Deferred completes and returns the value (or throws).
    │
Does async propagate exceptions immediately?
    │
    ├──► YES — this surprises most developers.   [Q9.3, Q10.3]
    │    If async { } throws before await() is called, the exception propagates to the
    │    parent scope IMMEDIATELY — not when you call await().
    │    WHY: async still creates a child Job in the coroutine hierarchy. Any failure
    │    in a child Job propagates up to the parent by default.
    │    Exception: inside supervisorScope, a failing async only throws at await().
    │    The parent and siblings are not affected.
    │    COMMON BUG: wrapping async in try/catch and expecting to catch it at await()
    │    — if you're not in a supervisorScope, the exception already propagated.
    │
Why doesn't try-catch around launch{} work?
    │
    ├──► launch{} returns immediately. The lambda runs asynchronously on another thread   [Q9.3]
    │    (or later on the same thread). By the time the lambda throws, your try-catch
    │    block has already exited — it's no longer on the call stack.
    │    The exception travels through the JOB TREE (parent→sibling cancellation),
    │    not through the JVM exception mechanism.
    │    Correct patterns:
    │    1. CoroutineExceptionHandler in the scope (catches root-level exceptions)
    │    2. try-catch INSIDE the launch{} body
    │    3. async{} + try { deferred.await() } catch(e: Exception) in supervisorScope
    │
How does cancellation propagate?
    │
    ├──► Cancellation propagates DOWN the Job tree (parent to children).   [Q10.1]
    │    job.cancel() marks the Job as cancelled, then sends CancellationException
    │    to every child. Children propagate to their children, and so on.
    │    WHY: a cancelled parent no longer needs results from its children —
    │    letting them run would waste resources.
    │    CancellationException is a normal part of the lifecycle — it's not an error.
    │    It is NOT forwarded UP to the parent (a cancelled child doesn't cancel the parent).
    │
How does an exception propagate?
    │
    ├──► Exceptions propagate UP the Job tree (child to parent).   [Q10.1]
    │    When a child coroutine fails with a non-CancellationException:
    │    1. The child notifies the parent of failure
    │    2. The parent cancels all OTHER children (siblings)
    │    3. The parent fails too, propagating further up
    │    This "fail fast" behavior ensures no child runs pointlessly if the overall
    │    computation has already failed.
    │    SupervisorJob breaks this chain: child failures are isolated.
    │    The parent does NOT cancel siblings, and does NOT fail itself.
    │
What's the difference between coroutineScope and supervisorScope?   [Q10.2]
    │
    ├──► coroutineScope: failure of ANY child cancels ALL children + throws in the parent.
    │    All-or-nothing semantics. Use when all concurrent work must succeed for the
    │    result to be valid (e.g., parallel API calls where you need all results).
    │    supervisorScope: each child is isolated. Failure of one child does NOT affect
    │    siblings. Parent does not fail. Use for independent operations where partial
    │    success is acceptable (e.g., loading profile photo independently of user data).
    │
When does CoroutineExceptionHandler fire?   [Q10.3]
    │
    └──► ONLY on ROOT coroutines launched with launch{} (not async, not nested launch).
         A root coroutine is one whose parent is NOT another coroutine (e.g., launched
         directly on a scope, not inside another launch{}).
         WHY not async: async exceptions are designed to be caught at await(). If CEH
         also caught them, you'd have two places handling the same exception.
         WHY not nested launch: nested launch failures propagate UP to the parent first.
         By the time the exception reaches the root, the CEH catches it as a last resort.
         In Android: viewModelScope's CEH catches uncaught exceptions in that scope.
```

---

## Chain I — HashMap Internals → Thread Safety

*"How does HashMap work internally?"*
> **What the interviewer is testing:** Whether you know the bucketing + collision resolution mechanism, Java 8's treeification optimization, and thread safety implications.

```
HashMap — basic structure   [J5.2]
    │
    ├──► An array of buckets (Node[] table). Default initial capacity: 16.
    │    Key → hashCode() → (hash ^ (hash >>> 16)) % capacity → bucket index.
    │    WHY spread high bits into low bits: if all keys have different high bits but
    │    the same low bits, they'd all land in bucket 0. Bit mixing distributes more evenly.
    │
What happens when two keys hash to the same bucket?
    │
    ├──► COLLISION. The bucket becomes a linked list of nodes (chained hashing).   [J5.2]
    │    get(key): walk the list, compare each node with equals(). O(n) in worst case.
    │
    ├──► Java 8 optimization — TREEIFICATION:
    │    When a bucket's chain exceeds 8 nodes → converted to a Red-Black tree.   [J5.2]
    │    get/put on a tree bucket: O(log n) instead of O(n).
    │    Below 6 nodes → converts back to linked list (hysteresis prevents thrashing).
    │    WHY matters: before Java 8, a denial-of-service attack could be crafted by sending
    │    many keys that hash to the same bucket, making HashMap O(n) for every operation.
    │    Treeification caps worst-case at O(log n).
    │
When does HashMap resize?
    │
    ├──► When size > capacity * loadFactor (default loadFactor = 0.75).   [J5.2]
    │    At 16 buckets: resize triggers at 12 entries.
    │    Resize: create new array (double the size), rehash all entries.
    │    WHY 0.75: empirically balances space vs collision rate. Higher loadFactor means
    │    more collisions; lower means more memory waste.
    │    WHY rehash: bucket index = hash % capacity. Doubling capacity changes the modulus
    │    — the same key may land in a different bucket.
    │
Why is HashMap not thread-safe?
    │
    ├──► Two threads calling put() simultaneously can both see size < threshold,
    │    both trigger resize, and both try to write to the same internal array reference.
    │    Result: data corruption (lost entries), or in Java 7, an INFINITE LOOP in the
    │    linked list due to a cycle created during concurrent resize.   [J6.2]
    │
    ├──► WHY infinite loop (Java 7 specifically):
    │    Two threads A and B both enter resize(). Thread A starts rehashing, sets
    │    node.next pointers. Thread B reads partially-updated next pointers and creates
    │    a cycle: node1.next = node2, node2.next = node1. Any subsequent get() on that
    │    bucket spins forever. Java 8 fixed this with a different resize algorithm.
    │
What do you use instead for thread safety?
    │
    ├──► ConcurrentHashMap — not synchronizedMap(HashMap).   [J5.4]
    │    Collections.synchronizedMap wraps every method in synchronized(this).
    │    Every get/put blocks all other threads. O(1) per op but full lock contention.
    │    ConcurrentHashMap uses stripe locking (Java 7) / CAS + bin-level sync (Java 8+).
    │    Multiple threads can write to DIFFERENT buckets simultaneously — no contention.
    │    Reads are LOCK-FREE (non-volatile reads via VarHandle in Java 9+).
    │
When would you choose ConcurrentHashMap over a plain HashMap?
    │
    └──► Any time the map is accessed by more than one thread.
         Even "mostly read" workloads: plain HashMap with concurrent reads is unsafe
         because a concurrent write (even from background work) can corrupt the internal
         table. ConcurrentHashMap reads are safe and lock-free — no performance cost
         for concurrent reads.
         Exception: if you control all access with external synchronization already,
         synchronizedMap is simpler. But ConcurrentHashMap is almost always the right choice.
```

---

## Chain J — Android Architecture Decisions

*"How would you architect a new feature?"*
> **What the interviewer is testing:** Pattern knowledge plus JUDGMENT — they want to see you reason about tradeoffs, not just name patterns.

```
The three forces that make Android architecture hard   [A3.1]
    │
    ├──► 1. LIFECYCLE: Android owns your objects. Activity/Fragment can be destroyed
    │       and recreated at any time. Code that ignores this crashes on rotation.
    │    2. CONFIGURATION CHANGES: rotation, locale, night mode — recreate Activity,
    │       keep ViewModel. All UI state not in ViewModel must survive via Bundle.
    │    3. PROCESS DEATH: OS kills background apps silently. Only Bundle (disk) and
    │       persistent storage (Room, DataStore) survive. ViewModel does not.
    │
    │    Every architecture pattern is an answer to these three forces.
    │
MVC vs MVP vs MVVM — what problem does each solve?   [A3.2, A3.3, A3.4]
    │
    ├──► MVC (bad in Android): Activity is BOTH View AND Controller.
    │    You cannot test the Activity in isolation — it depends on the Android framework.
    │    Network callbacks fire after the Activity is destroyed → crash.
    │    No separation of concerns: business logic lives alongside UI code.
    │
    ├──► MVP (better): Extract the Presenter — pure Kotlin/Java, no Android dependencies.
    │    Activity implements a ViewInterface. Presenter calls view.showUser() — it doesn't
    │    know about Activities, only about the interface. Presenter is unit-testable.
    │    Remaining problem: Presenter holds a View reference. If you forget to call
    │    detachView() in onDestroy(), the Activity is leaked. 1:1 Presenter-View coupling
    │    creates boilerplate explosion in large apps.
    │
    └──► MVVM (current recommendation): ViewModel holds state as Flow/StateFlow.
         Activity/Fragment observes the Flow. ViewModel does NOT hold a View reference —
         the observer relationship is one-directional (View observes ViewModel, not vice versa).
         ViewModel survives rotation via ViewModelStore. No leak by design.
         WHY StateFlow: it always has a value (current state), replays on new collectors
         (new Fragment or screen rotation gets current state immediately).
    │
When would you choose MVI over MVVM?   [A3.5]
    │
    ├──► MVVM: multiple Flows for multiple state slices. The UI must combine them correctly.
    │    If two Flows update simultaneously, there can be inconsistent intermediate states
    │    (loading=false, data=null before data arrives).
    │    MVI: ONE data class for the entire screen's state. ONE event to process at a time.
    │    Impossible states become impossible by construction.
    │    WHEN to use MVI:
    │    - Complex screens with many interdependent state fields
    │    - Teams that need deterministic testing (every state is reproducible from intents)
    │    - Jetpack Compose (Compose redraws the whole screen anyway — one state object fits perfectly)
    │    WHEN MVI is over-engineering:
    │    - Simple CRUD screens with one or two state pieces
    │    - Small teams where the Contract boilerplate adds friction without payoff
    │
When does Clean Architecture make sense?   [A3.6]
    │
    ├──► Clean Architecture adds a Domain layer between Presentation and Data.
    │    Domain: pure Kotlin (no Android imports), Use Cases, Repository interfaces.
    │    Value it adds:
    │    1. Domain is independently testable — no mocking of Room or Retrofit.
    │    2. Multiple frontends can share the same Domain (Android app + Desktop app).
    │    3. API shape and DB schema can change without touching business logic.
    │    When it's worth it: 3+ developers, multiple features being built in parallel,
    │    long-lived app where requirements will evolve, desire to run Use Cases in tests
    │    without Android emulator.
    │
When is Clean Architecture over-engineering?
    │
    └──► Single-developer weekend app, prototype, or <3 screens.
         Each layer adds files (Repository interface + impl, UseCase, Mapper triple).
         If the domain layer has one Use Case that just calls one Repository method,
         it's pure pass-through with no value. The rule: if the domain layer has no
         logic (no business rules, no transformations), it doesn't need to exist.
         A ViewModel calling a Repository directly is not "bad architecture" for small apps.
```

---

## Chain K — Inline Functions → Performance → Reified

*"What does `inline` actually do and when should you use it?"*
> **What the interviewer is testing:** Whether you understand the real cost of lambda capture and the three use cases that justify `inline`.

```
Why do higher-order functions have overhead in Kotlin?   [Q4.1]
    │
    ├──► A lambda is an object. When you pass `{ x -> x * 2 }` to a function,
    │    the compiler creates a Function1<Int, Int> instance on the heap.
    │    If the lambda captures variables from the outer scope, a new object is created
    │    EACH TIME the lambda is used — storing the captured values as fields.
    │    For a hot path (e.g., in a RecyclerView, a processing loop), this means
    │    thousands of short-lived allocations → GC pressure.
    │
What does `inline` do to eliminate this?   [Q4.2]
    │
    ├──► The compiler COPIES the entire function body to every call site.
    │    There is no function call. There is no lambda object.
    │    The lambda body is also inlined — it becomes raw bytecode at the call site.
    │    Result: zero object allocation, zero virtual dispatch overhead.
    │
    ├──► But: code size increases. Every call site gets a copy of the function body.
    │    If the inline function is large and called in many places, bytecode bloat occurs.
    │    Rule of thumb: only inline functions that take lambda parameters.
    │    Inlining a function without lambda parameters achieves nothing new
    │    (the JIT already inlines hot methods at runtime).
    │
What is `noinline`?   [Q4.2]
    │
    ├──► If an inline function has multiple lambda parameters, you can opt ONE out:
    │    inline fun execute(action: () -> Unit, noinline callback: () -> Unit)
    │    `action` is inlined (no object). `callback` remains a real Function0 object.
    │    WHY you'd need this: `callback` might be stored (assigned to a variable,
    │    passed to another function) — you can't store inlined code, only real objects.
    │
What is `crossinline`?   [Q4.2]
    │
    ├──► Inlined lambdas can use `return` to return from the ENCLOSING function
    │    (non-local return). This is only possible because the lambda is inlined —
    │    there's no real lambda object to "return from."
    │    crossinline prevents non-local returns: the lambda is still inlined, but
    │    the compiler forbids `return` inside it (only `return@label` is allowed).
    │    WHY: if the inlined lambda is executed in a different execution context
    │    (e.g., inside a Runnable or coroutine), a non-local return to the enclosing
    │    function would be wrong — the enclosing function may have already returned.
    │
When does `inline` enable `reified`?   [Q3.3, Q4.2]
    │
    └──► Type parameters are erased at runtime. Normally, you cannot do T::class.java
         because T has no runtime representation — it's just a compile-time placeholder.
         With `inline fun <reified T>`, the compiler substitutes T at each call site
         with the actual concrete type BEFORE generating bytecode.
         The result: T::class.java in the inlined bytecode is literally DetailActivity::class.java
         — a concrete, erasure-proof class reference.
         Without inline, there's no call site substitution. T would still be erased.
         This is why reified is ONLY available on inline functions — the substitution
         requires inlining; without it, erasure applies as normal.

         Real example:
         inline fun <reified T : Any> Gson.fromJson(json: String): T =
             fromJson(json, T::class.java)      // T is concrete here because of inline
         val user: User = gson.fromJson(jsonString)
         // Compiles to: gson.fromJson(jsonString, User::class.java) — no erasure
```

---

## Quick Reference: Interview Trap Summary

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ TRAP 1: "lateinit var count: Int" — compile error!                          │
│   WHY: lateinit uses null as sentinel. int is a JVM primitive — no null     │
│   state exists. Use Delegates.notNull<Int>() instead (boxes to Any?).       │
│                                                                              │
│ TRAP 2: open function called in init block → sees null subclass fields.     │
│   WHY: Superclass <init> runs before subclass <init>. The subclass object   │
│   exists in memory but its fields are uninitialized (null/0 defaults).      │
│   Virtual dispatch calls the subclass override, which reads unset fields.   │
│                                                                              │
│ TRAP 3: try-catch around launch{} never fires.                              │
│   WHY: launch returns immediately. The lambda runs asynchronously.          │
│   The exception travels through the Job hierarchy, not the JVM stack.       │
│   Put try-catch INSIDE the launch body, or use CoroutineExceptionHandler.   │
│                                                                              │
│ TRAP 4: async propagates exception IMMEDIATELY to parent — not at await().  │
│   WHY: async creates a child Job. Any child failure propagates up.          │
│   Only inside supervisorScope is the exception held until await().          │
│                                                                              │
│ TRAP 5: StateFlow skips duplicate consecutive emissions.                    │
│   WHY: StateFlow uses equals() to filter. If current state == new state,   │
│   no collector is notified. Navigation events (emit same destination twice) │
│   are silently dropped. Use SharedFlow(replay=0) for one-time events.       │
│                                                                              │
│ TRAP 6: lifecycleScope.launch { flow.collect{} } — continues in background.│
│   WHY: the coroutine is still alive even when the screen is invisible.      │
│   Use repeatOnLifecycle(STARTED) to cancel collection when not in foreground│
│                                                                              │
│ TRAP 7: Service runs on the MAIN THREAD.                                    │
│   WHY: Service.onCreate/onStartCommand are called on the main thread.       │
│   Long work blocks the UI. Must start a coroutine or thread explicitly.     │
│                                                                              │
│ TRAP 8: ViewModel survives rotation but NOT process death.                  │
│   WHY: ViewModelStore is in-memory. SIGKILL wipes the process with no       │
│   callbacks. Use SavedStateHandle for small state, Room for large data.     │
│                                                                              │
│ TRAP 9: "list is List<String>" — compiler error (erasure).                  │
│   WHY: at runtime, List<String> and List<Int> are both just List.           │
│   Use "list is List<*>" to check for a List regardless of element type.     │
│                                                                              │
│ TRAP 10: MutableList<Dog> is NOT a subtype of MutableList<Animal>.          │
│   WHY: if it were, you could put a Cat into a MutableList<Dog> via the      │
│   Animal reference — type corruption. List<Dog> IS a subtype of List<Animal>│
│   because List is read-only (out T covariant) — you can only read Dogs,    │
│   and a Dog read as an Animal is always safe.                                │
│                                                                              │
│ TRAP 11: const val change in a library without recompiling callers.         │
│   WHY: const val is inlined into caller bytecode. If you ship a new library │
│   JAR with a changed const val, callers still have the OLD value baked in.  │
│   Not a runtime error — a silent behavioral bug. Always recompile callers.  │
│                                                                              │
│ TRAP 12: Forgetting to call detachView() in MVP → Activity memory leak.    │
│   WHY: Presenter holds a View (Activity) reference. Activity is destroyed   │
│   on rotation but Presenter lives on (e.g., in a retained Fragment).        │
│   The Activity can't be GC'd. On every rotation: one more leaked Activity.  │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

*Chains A–K cover the complete interview question space from JVM fundamentals to Android production patterns. Each chain ends at a depth that distinguishes a senior engineer's answer from a junior one.*
