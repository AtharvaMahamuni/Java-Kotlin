# Kotlin & Android Mastery — Complete Study Plan

**Format:** Each question = one focused study session.
**Connections:** `← Q[X.Y]` = builds on that question | `→ Q[X.Y]` = connects forward to it
**Goal:** Build intuition from JVM primitives up to Android system design.

---

## Phase 0: JVM Mental Model
*Must be understood first — every phase builds on this.*

### 0.1 Primitives vs References
- What is the difference between a JVM primitive (`int`, `boolean`, `long`) and a reference type (`Integer`, `Object`)?
- Why do primitives have default values (`0`, `false`) but reference types default to `null`?
- What does "stack vs heap" mean for where a primitive vs a reference is stored?
- What is "boxing" and "unboxing", and what runtime cost does it introduce?
  → connects to Q1.1 (val stores primitives), Q5.1 (lateinit can't use null sentinel with primitives), Q3.3 (reified erases to Object)

### 0.2 JVM Type Mapping
- How does Kotlin's `Int` map to JVM `int` vs how does `Int?` map to `java.lang.Integer`?
- What is the rule: when does Kotlin use the primitive and when does it box?
- Why does `List<Int>` always store boxed `Integer` objects, never raw `int`?
- What is the cost difference between iterating `IntArray` vs `Array<Int>`?
  → connects to Q5.1 (why lateinit forbids Int), Q3.1 (erasure works on Object), Q7.1 (IntArray vs Array)

### 0.3 Class Loading and the `static {}` Block
- What is the JVM class loading lifecycle: load → link → initialize?
- When exactly does the `static {}` (class initializer) block run?
- What guarantee does the JVM give about thread safety during class initialization?
  → connects to Q2.4 (object singleton thread safety), Q2.5.4 (companion object init time)

### 0.4 The JVM Call Stack
- What is a stack frame, and what gets allocated when a method is called?
- Why does calling a method (getter) cost more than reading a field directly?
- What is the difference between a virtual method dispatch and a direct call?
  → connects to Q1.1 (val getter overhead), Q4.2 (inline eliminates method call)

---

## Phase 1: Type System Foundations

### 1.1 `val` vs `const val`
- What bytecode does `val BASE_URL = "..."` inside an `object` compile to — what is the caller actually invoking? `← Q0.4`
- Why does every `val` access call a getter method, and what is the allocation implication in a hot path?
- What does `const val` emit at the call site — what does "inlined as literal" mean precisely?
- What are the exact three constraints that prevent `const val TAG = SomeClass::class.simpleName`?
- Why doesn't `@JvmField` give you the same zero-overhead guarantee as `const val`?
  → connects to Q2.3 (companion object and const), Q5.3 (delegates also generate methods)

### 1.2 Nullability at the Type Level
- How does the Kotlin type system represent `String` vs `String?` — are they different JVM types?
- What does `@NotNull` and `@Nullable` actually do at runtime vs compile time?
- What is a "platform type" (`String!`) and why is it dangerous when calling Java code from Kotlin?
- When does the Elvis operator `?:` generate a conditional branch in bytecode vs when is it eliminated?
  → connects to Q5.1 (lateinit null sentinel), Q2.5.3 (null in open function init trap)

### 1.3 `Nothing`, `Unit`, and the Type Hierarchy
- What is `Nothing` and why does the compiler accept `Result<Nothing>` where `Result<User>` is expected?
- Why does `throw` have type `Nothing`, and what does that enable in `if/when` expressions?
- What is the difference between `Unit` and `void` at the JVM level?
- Why can `Nothing` appear in `out` (covariant) positions but causes a compile error in `in` (contravariant) positions? `→ Q3.2`
  → connects to Q2.3 (sealed class Error carries Nothing), Q3.2 (variance positions)

### 1.4 Smart Casts
- What conditions must be true for the compiler to perform a smart cast after an `is` check?
- Why does a smart cast become invalid after a `var` property check but remain valid after a `val` check?
- What is the difference between `is` and `as` — what does each compile to at the bytecode level?
- Why does smart cast fail through a property getter even if the backing field is `val`?
  → connects to Q2.3 (sealed class when exhaustiveness), Q3.1 (type erasure breaks is checks)

---

## Phase 2: Classes and Objects

### 2.1 Class Modifiers
- Why are Kotlin classes `final` by default — what Java problem does this prevent?  `← Q0.4`
- What bytecode does `open` generate vs `final` — what is the virtual dispatch table difference?
- When does choosing `abstract` over `open` make architectural sense?
- What is the "fragile base class" problem, and how does `final by default` protect against it?
  → connects to Q2.5.3 (open function in init is dangerous)

### 2.2 Data Classes
- Which properties are included in `equals`, `hashCode`, `copy`, `componentN` — and which are excluded?
- Why does a mutable `var` in a data class break `HashSet` in production — what is the exact sequence that corrupts the bucket?  `← Q0.1`
- Why is `copy()` shallow — what does that mean when a property is a `MutableList`?
- What is `@UnsafeVariance` used for in `List.contains()`, and why is it safe there?
  → connects to Q3.2 (UnsafeVariance in covariant types), Q7.1 (List covariance)

### 2.3 Sealed Classes and Interfaces
- What bytecode does `sealed class` compile to — why is its constructor `private`?
- How does `when` on a sealed hierarchy achieve exhaustiveness at compile time — what compiler mechanism enforces it?
- When do you choose `sealed class` vs `sealed interface` vs `enum class` — what capability does each unlock?
- What does `Result<Nothing>` as a sealed subtype mean, and why does it work?  `← Q1.3`
- What changed in Kotlin 1.5 about where sealed subclasses can be declared?

### 2.4 The `object` Keyword
- How does JVM class loading guarantee thread-safe singleton initialization for `object`?  `← Q0.3`
- What is the exact bytecode for an `object` — what is `INSTANCE` and where is it initialized?
- What is the difference between `object`, `companion object`, and an anonymous `object` at bytecode level?
- When does an anonymous `object` inside a method capture the outer `this` reference — and why does that leak?  `← Q0.1`
- How does `companion object` differ from Java `static` — can it implement interfaces?

### 2.5 Value Classes
- What does "erased at runtime" mean for `value class` — what does the JVM actually see?
- When does boxing occur for a `value class` — list the exact four scenarios?
- Why does the compiler mangle method names for value classes, and what problem does it prevent?
- When would you choose `value class` over `typealias` — what safety does it add?

---

## Phase 2.5: Initialization and Construction Mechanics
*All traps here come from one rule: JVM initializes top-to-bottom, superclass-before-subclass, delegation-before-body.*

### 2.5.1 Primary Constructor vs `init` Block
- What is the difference between a primary constructor and an `init` block — are they the same thing at the bytecode level?
- When you have both property initializers and multiple `init` blocks, what is the exact execution order?
- Why does the compiler interleave property initializers and `init` blocks in declaration order — what bug would arise if it ran all properties first, then all `init` blocks?
- What bytecode does a primary constructor compile into — is there a separate `<init>` method?

### 2.5.2 Primary vs Secondary Constructors
- Why must every secondary constructor delegate to the primary constructor via `this()` — what JVM rule enforces this?
- What executes first: the `this()` delegation call body, or the secondary constructor body?
- When would you use a secondary constructor over a default parameter value — what is the practical Java interop difference?
- What is the execution order when you have an `init` block AND a secondary constructor — which wins?

### 2.5.3 Inheritance Initialization Order
- What is the exact execution order when a subclass is instantiated: superclass `init` or subclass `init` first?
- Why is calling an `open` function inside an `init` block dangerous — write the exact code that silently produces `0` or `null` as a bug?  `← Q2.1`
- What is the "leaked `this`" problem in constructors — what happens if you pass `this` to another object during construction?
- How does making a class `final` remove the open-function-in-init danger?

### 2.5.4 Companion Object and Object Initialization
- When exactly does a `companion object` get initialized — at class load time or first access?  `← Q0.3`
- Why does accessing a `const val` in a companion object NOT trigger the companion object initialization?  `← Q1.1`
- What happens if two `object` declarations reference each other during initialization — what is the deadlock risk?
- Why does accessing a `companion object` member not guarantee the enclosing class itself is initialized?

### 2.5.5 Property Initializer Order Traps
- What happens if a property initializer references another property declared below it — does it compile?
- Why does this compile but produce `0` or `null` at runtime — what does the bytecode reveal?
- What is the execution order difference between a `val` with a default value vs a `val` with a `lazy` delegate?  `→ Q5.2`
- When does a `const val` get assigned vs when does a regular `val` get assigned — are they in the same bytecode block?

### 2.5.6 Constructor Visibility and Factory Patterns
- Why would you make a primary constructor `private`, and what design pattern does this enable?
- What is the difference between a `private constructor` + `companion object` factory vs a top-level factory function — when would you prefer each?
- What does `@JvmOverloads` generate for constructors with default parameters — how many constructors appear in bytecode?
- How does `@Inject constructor` for Hilt interact with your own constructor body — where in the execution order does DI inject?

---

## Phase 3: Generics and Variance

### 3.1 Type Erasure
- Why does the JVM erase generic type parameters — what historical constraint (Java 1.4 backward compatibility) caused this design?  `← Q0.2`
- What exactly happens at bytecode level with `List<String>` vs `List<Int>` — are they the same class?
- Why does `list is List<String>` fail at runtime — what does the compiler error "cannot check erased type" mean?
- What is the difference between `List<*>`, `List<Any?>`, `List<out Any>`, and a raw Java `List` — in terms of what you can read and write?
- Why does Kotlin forbid raw types entirely — what bug does that prevent?

### 3.2 Variance
- What is the Liskov Substitution Principle, and what question does it raise for generic containers?  `← Q2.1`
- Why is `MutableList<Dog>` NOT a subtype of `MutableList<Animal>` — write the exact code that would corrupt memory if it were?
- Why is `List<Dog>` a subtype of `List<Animal>` — what design property of `List` makes this safe?
- What does `out T` restrict — what positions is `T` forbidden from, and why?
- What does `in T` restrict — what positions is `T` forbidden from, and why?
- How do `out`/`in` compile to bytecode — do they survive in the JVM class file?
- What is declaration-site variance vs use-site variance (type projections) — when do you need each?
- What is `@UnsafeVariance` and why is it used in `List.contains(element: @UnsafeVariance E)`?  `← Q2.2`
- Why are Java arrays covariant (`String[]` IS-A `Object[]`) — and what runtime crash does this enable?

### 3.3 Reified Type Parameters
- What is the exact mechanism by which `inline` + `reified` defeats type erasure — what does the compiler substitute at the call site?  `← Q3.1, Q4.2`
- Why can reified type parameters ONLY exist inside `inline` functions — why not on class type parameters?
- What is the Java `Class<T>` pattern, and how does reified eliminate it — show the bytecode difference?
- What does `T::class` resolve to inside a reified function vs outside it?
- Write the `startActivity<DetailActivity>()` extension using reified — what makes this work?

---

## Phase 4: Functions, Lambdas, and Inlining

### 4.1 Lambda Compilation
- What anonymous class does every lambda compile to — what interface does it implement?  `← Q0.1`
- What is a non-capturing lambda vs a capturing lambda — which is a singleton and which allocates per call?
- Why does Kotlin generate anonymous classes instead of using Java's `invokedynamic` + `LambdaMetafactory`?
- What is the concrete heap allocation cost of passing a lambda to a non-inline function in a loop?

### 4.2 `inline`, `noinline`, `crossinline`
- What exactly does `inline` paste at the call site — function body AND lambda body?  `← Q4.1`
- Why does an inlined lambda allow a non-local `return` — what does "non-local" mean exactly?
- What problem does `crossinline` solve — write the exact scenario where a non-local return becomes illegal?
- Why does `noinline` leave a lambda as a `Function` object — what use requires it to remain an object?
- When is `inline` harmful: binary compatibility for library APIs, and code size explosion?
- Why do all standard library operators (`map`, `filter`, `let`, `also`) use `inline` — what does this cost at call sites?

### 4.3 Higher-Order Functions with `suspend`
- How does a `suspend` lambda differ from a regular lambda at the JVM level — what extra parameter does it carry?  `→ Q9.1`
- Why does `Thread.sleep(1000)` inside a suspend function block the thread but `delay(1000)` does not?
- Write a `retryWithBackoff` function — why must `CancellationException` always be re-thrown, not swallowed?
- What happens if you catch `Exception` in a retry loop without re-throwing `CancellationException` — what leaks?

### 4.4 Scope Functions
- What is the bytecode difference between `let`, `run`, `apply`, `also`, `with` — do any of them cost anything?
- What is the `this` vs `it` distinction — which functions use which, and why?
- When does choosing the wrong scope function cause a logic bug (not just a style issue)?
- Why are all scope functions `inline` — what would they cost if they weren't?  `← Q4.2`

### 4.5 Named and Default Parameters
- What bytecode does a function with default parameters compile to — how many methods are generated?
- What does `@JvmOverloads` add for Java callers — and why is it necessary?
- What is the `$default` synthetic method the compiler generates — what bitmask does it use?
- When do default parameters eliminate the need for builder patterns or secondary constructors?  `← Q2.5.2`

---

## Phase 5: Properties and Delegation

### 5.1 `lateinit` Internals
- What sentinel value does `lateinit` use internally — what does the backing field look like in decompiled Java?  `← Q0.1, Q1.2`
- Why does `lateinit var count: Int` fail at compile time — what JVM constraint makes it impossible?  `← Q0.2`
- Why does `lateinit` throw `UninitializedPropertyAccessException` and NOT `NullPointerException` — what contract does that express?
- Why does `::property.isInitialized` compile to a null check rather than a reflection call?
- Why can `isInitialized` only be called from the same class — what API design reason prevents external access?

### 5.2 `lazy` Internals
- What synchronization mechanism does `LazyThreadSafetyMode.SYNCHRONIZED` use — what is double-checked locking?
- What happens if the `lazy` block throws — is the result cached, and what happens on the next access?
- Why does `lazy` require `val` not `var` — what contract would break if reassignment were allowed?
- When would you use `LazyThreadSafetyMode.NONE`, and what concurrency bug can it cause?
- Why does a `lazy` property in a Fragment hold the old destroyed view — what does this tell you about lazy's caching model?  `← Q2.5.1`

### 5.3 Delegates
- How does the `by` keyword compile — what interface must a delegate implement (`getValue`/`setValue`)?
- How does `Delegates.notNull<Int>()` work around the lateinit primitive restriction — what does it use as sentinel?  `← Q5.1`
- What is the difference in exception type between `lateinit` and `Delegates.notNull()` — and why does that matter for debugging?
- How does `by map` delegation work for property storage — what makes it useful for JSON deserialization?
- What is `ReadOnlyProperty` vs `ReadWriteProperty` — what is the arity difference?

---

## Phase 6: Extension Functions

### 6.1 Compilation and Dispatch
- How does an extension function compile — what does `fun String.greet()` look like in Java bytecode?
- What is the receiver type in bytecode — is it `this` or a parameter?
- Why can't extension functions override member functions — what dispatch rule prevents this?
- What is the difference between `open` class extension and member function in terms of polymorphism?

### 6.2 Extension Functions as API Design
- When do extension functions make sense vs adding a method to the class itself?
- How do the RecyclerView extension functions (`setup`, `onScrolledToEnd`) use `apply` to enable method chaining?  `← Q4.4`
- What is the null-safety advantage of calling an extension function on a nullable receiver: `fun String?.orEmpty()`?
- Why do extension functions on `RecyclerView` avoid the need for subclassing?  `← Q2.1`

### 6.3 Extension Properties
- What constraint prevents extension properties from having backing fields — what does this mean for their implementation?
- How does an extension property compile compared to a member property?
- When would you use an extension property vs an extension function — what is the semantic difference?

---

## Phase 7: Collections and Sequences

### 7.1 Kotlin's Collection Hierarchy
- What is the difference between `List` (read-only) and `MutableList` — why is `List` covariant (`out E`) but `MutableList` is not?  `← Q3.2`
- What is the difference between `Array<Int>` and `IntArray` — when does each box?  `← Q0.2`
- Why is `listOf()` backed by `java.util.Arrays.asList()` — what are its constraints?
- What is the difference between `emptyList()` and `listOf()` with no arguments — is one a singleton?

### 7.2 Sequences vs Eager Collections
- What is a `Sequence` and when does it evaluate — what does "lazy" mean for a chain of operators?
- Write `list.filter { }.map { }` as a Collection chain vs a Sequence chain — how many intermediate lists does each create?
- When is a Sequence SLOWER than an eager collection — what is the overhead for small collections?
- How does `generateSequence` work — what makes it potentially infinite?
- How does `Flow` relate to `Sequence` — what does `Flow` add?  `→ Q11.1`

### 7.3 Common Collection Pitfalls
- Why does modifying a collection while iterating it throw `ConcurrentModificationException` — what flag tracks this?
- What is the difference between `groupBy` (eager, returns Map) vs `groupingBy` (lazy, returns `Grouping`)?
- What does `getOrPut` guarantee atomically vs getting and then putting separately?
- How does `LinkedHashMap` with `accessOrder=true` enable LRU cache behavior?  `→ Q14.4`

---

## Phase 8: Other Kotlin Features

### 8.1 Destructuring
- What is a destructuring declaration — what `componentN()` functions does it call?
- How does `data class` automatically provide `component1()`, `component2()` etc.?
- When can destructuring be used in lambda parameters — what syntax does this enable?
- What is the `_` placeholder in destructuring — what does the compiler do with it?

### 8.2 String Templates and Operators
- What does `"Hello $name"` compile to — is it `String.format()` or `StringBuilder`?
- What is operator overloading — what function name does `+` on a custom class map to?
- What does the `invoke` operator enable — how does it make an object callable like a function?
- What is the `rangeTo` operator and how does it power `in 1..10` checks?

### 8.3 SAM Conversions
- What is a SAM interface and when does Kotlin automatically convert a lambda to one?
- What is the difference between a Kotlin `fun interface` and a regular single-method interface for SAM conversion?
- When does SAM conversion NOT work — what breaks the automatic conversion?

---

## Phase 9: Coroutines — Execution Mechanics

### 9.1 What `suspend` Actually Does
- What is Continuation Passing Style (CPS) — what two things does the compiler add to every `suspend` function?  `← Q4.3`
- What does the state machine's `label` field represent — draw the state transitions for a function with two suspension points.
- Where are local variables stored across suspension points — stack or heap?
- What does `COROUTINE_SUSPENDED` mean — what is the callback model it implements?
- Why does `suspend` say NOTHING about which thread a function runs on?

### 9.2 Coroutine Context and Dispatchers
- What is a `CoroutineContext` — what is the `+` operator on two contexts doing?
- What thread pool backs `Dispatchers.Default` vs `Dispatchers.IO` — are they separate pools or the same?
- What does `Dispatchers.Main.immediate` do differently from `Dispatchers.Main` — when does it skip the `Handler.post()`?
- When does `withContext(Dispatchers.IO)` cause an actual thread switch vs reuse the current thread?  `← Q9.2`
- What is `limitedParallelism(N)` on `Dispatchers.IO` — how does it differ from the default 64-thread cap?

### 9.3 `launch` vs `async`
- What is the type difference between `Job` (from `launch`) and `Deferred<T>` (from `async`)?
- Does `async` propagate its exception to the parent immediately or only at `.await()` — what is the exact answer?  `→ Q10.3`
- Why does `try-catch` around `launch { }` NOT catch the exception from inside the launch?
- What is the lazy `async` trap — why does `async(start = LAZY)` produce sequential execution?  `→ Q9.4`

### 9.4 Coroutine Start Modes
- What is the execution difference between `DEFAULT`, `LAZY`, `ATOMIC`, and `UNDISPATCHED`?
- When would you use `ATOMIC` — what guarantee does it give that `DEFAULT` does not?
- What does `UNDISPATCHED` mean for the first vs subsequent suspension points?
- Why is `UNDISPATCHED` useful for guaranteed initialization before an emitter fires?

---

## Phase 10: Structured Concurrency

### 10.1 The Job Hierarchy
- What tree structure do coroutine `Job`s form — what are the three invariants of structured concurrency?  `← Q9.1`
- What is the exact method `childCancelled(cause: Throwable): Boolean` doing in `JobSupport` — what does returning `true` vs `false` mean?
- How does cancellation propagate downward vs how does an exception propagate upward — are they the same mechanism?
- What happens when a `CancellationException` is the cause vs a non-cancellation exception?

### 10.2 `coroutineScope` vs `supervisorScope`
- What is the one source-code-level difference between `ScopeCoroutine` and `SupervisorCoroutine`?  `← Q10.1`
- When does `supervisorScope` itself throw vs isolate the child failure — what is the exact rule?
- When do you use `coroutineScope` (all-or-nothing) vs `supervisorScope` (independent operations)?
- Why do `viewModelScope` and `lifecycleScope` both use `SupervisorJob` internally?

### 10.3 Exception Handling Rules
- Why does `CoroutineExceptionHandler` only work on root coroutines with `launch` — not on nested children?  `← Q9.3`
- Why does `async` encapsulate exceptions in `Deferred` — and does it still propagate to the parent without `.await()`?
- What is `CancellationException` — why must it ALWAYS be re-thrown and never swallowed?  `← Q4.3`
- What happens when a tight CPU loop runs after `job.cancel()` — why does it never actually cancel?
- Why does `try-catch` INSIDE a `launch` work but `try-catch` AROUND a `launch` does not?

### 10.4 Lifecycle Scopes and Process Death
- What `Job` type and `Dispatcher` does `viewModelScope` use internally, and why those specific choices?  `← Q10.2`
- Does `ViewModel` survive process death — what is the exact boundary of its survival?
- What is the difference between `lifecycleScope.launch { }` and `repeatOnLifecycle(STARTED) { }` — what lifecycle bug does the latter fix?
- What is `SavedStateHandle` — how does it survive process death when ViewModel does not?

### 10.5 `select` Expression
- What does `select { }` do — how does it "race" multiple async operations?
- What does "biased toward the first clause" mean — what happens when two are simultaneously ready?
- Why does `select` NOT auto-cancel the losing coroutine — what must you do manually?
- What is the Java `CompletableFuture.anyOf()` equivalent and how does it compare to `select`?

---

## Phase 11: Flow

### 11.1 Cold vs Hot Streams
- What makes `Flow` cold — what happens each time a new collector subscribes?  `← Q7.2`
- What makes `StateFlow` and `SharedFlow` hot — what is the "source of truth" model?
- What is the relationship between `Sequence` (pull, synchronous) and `Flow` (push, async, suspend-aware)?
- What is backpressure and how does `Flow` handle it via `buffer`, `conflate`, and `collectLatest`?

### 11.2 Flow Operators
- What is the difference between `map` and `flatMapLatest` — when does the inner coroutine get cancelled?
- What does `debounce` do — write the debounce search pattern and explain why `flatMapLatest` is essential for cancelling in-flight requests?
- What does `conflate` do vs `buffer(capacity = 1)` vs `buffer(UNLIMITED)` — what trade-off does each make?
- What does `distinctUntilChanged` do — what is the equality check it uses?
- What is the difference between `zip` and `combine` — when does each emit?

### 11.3 `StateFlow` vs `SharedFlow`
- Why does `StateFlow` skip duplicate consecutive emissions — and when is that a production bug?  `← Q9.3`
- What `replay`, `extraBufferCapacity`, and `onBufferOverflow` settings should you use for one-shot navigation events?
- Why is `StateFlow` wrong for navigation events after screen rotation — what does "replay = 1" do to a navigation command?
- What is the difference between `stateIn` and `shareIn` applied to a cold Flow?

### 11.4 Flow Collection and Lifecycle
- What is the difference between `collect`, `launchIn`, `collectAsStateWithLifecycle`, and `collectAsState`?
- Why does `lifecycleScope.launch { flow.collect { } }` have a subtle lifecycle bug — what does it do when the app goes to background?
- What does `repeatOnLifecycle(STARTED)` add — what exactly does it cancel and restart?
- When a `Flow` collector is cancelled, what happens to emissions already buffered but not yet processed?

---

## Phase 12: Reference Operators and Reflection

### 12.1 `::` Operators
- What anonymous class does a function reference (`::myFun`) compile to — what interface does it implement?  `← Q4.1`
- What is the arity difference between a bound reference (`"hello"::length`) and an unbound reference (`String::length`)?
- How does a property reference (`Box::value`) differ from a function reference — what hierarchy does it use (`KProperty1`)?
- How does Kotlin's `::` differ from Java's `::` at bytecode level — anonymous class vs `invokedynamic`?
- When does passing `::function` to an `inline` function eliminate the object entirely?  `← Q4.2`

### 12.2 KClass vs Class
- What is the difference between `MyClass::class` (`KClass`) and `MyClass::class.java` (`Class`)?
- What Kotlin-specific metadata does `KClass` expose that `Class` does not (`isData`, `isSealed`, `primaryConstructor`)?
- How does `widget::class` (instance) differ from `Widget::class` (type) — what covariance applies?
- When do you need `KClass` vs `Class` — which does Gson/Moshi/Retrofit require?

---

## Phase 13: Android Architecture

### 13.1 MVVM and Unidirectional Data Flow
- Is MVVM unidirectional? — what is the precise answer that separates senior from mid-level responses?
- What is the difference between MVVM, MVP, and MVI — what does each pattern enforce?
- When does adding MVI's single immutable state object make sense over plain MVVM?
- What is the "presentation layer" contract — what should and should not live in a ViewModel?

### 13.2 Clean Architecture Layer Boundaries
- Where do repository interfaces live — Domain or Data layer — and why does the answer reveal understanding of dependency inversion?
- What is the Dependency Rule — which direction can dependencies point, and which is forbidden?
- When is a UseCase/Interactor justified vs over-engineering — what Google's guidance says?
- How do you test a UseCase in isolation — what does "pure Kotlin, zero Android imports" enable?

### 13.3 ViewModel Internals
- How does ViewModel survive configuration changes — what is `ViewModelStore` and `NonConfigurationInstances`?  `← Q10.4`
- Does ViewModel survive process death — what is the exact moment it is destroyed and recreated?
- What is `SavedStateHandle` and how does it hook into `onSaveInstanceState` under the hood?
- What is the Bundle size limit (~1MB for the Binder transaction) — what happens when you exceed it?
- When would you scope a ViewModel to a navigation graph instead of a single screen?

### 13.4 LiveData vs StateFlow vs SharedFlow
- What are the four key differences between LiveData and StateFlow — when is StateFlow the better choice?  `← Q11.3`
- Why doesn't LiveData belong in the domain layer — what Android dependency does it carry?
- When does StateFlow NOT replace LiveData — what does consecutive duplicate filtering break?
- What is the correct pattern for one-shot events (navigation, snackbar) — `SharedFlow` or `Channel`?

### 13.5 Dependency Injection
- What is the difference between Dependency Injection and Service Locator — is Koin a DI framework?
- How does Hilt work under the hood — what does `@HiltAndroidApp` generate at compile time?
- What is the difference between `@Singleton`, `@ActivityScoped`, `@ViewModelScoped` — what lifetime does each have?
- What is `@Binds` vs `@Provides` — when do you use each?
- How does `@HiltViewModel` generate a `ViewModelFactory` without you writing one?

### 13.6 Repository and Offline-First Patterns
- What is the "single source of truth" pattern — why does the UI observe Room (DB) and not the API response?
- What is the `NetworkBoundResource` pattern — what is the flow: cache first → network → update DB → emit?
- How do you handle optimistic updates — what rollback strategy works with Room + Flow?
- What are the conflict resolution strategies ranked by complexity: Last-Write-Wins → Server-Wins → Field-level merge → CRDTs?

### 13.7 Error Handling Across Layers
- Where should HTTP exceptions be converted to domain errors — Data layer or ViewModel?
- What is the typed `sealed class AppError` pattern and what does it enable in the ViewModel?
- How do you differentiate a 401 (re-login) from a 500 (show error) in the ViewModel layer?
- What happens when `CancellationException` reaches the ViewModel's `catch (e: Exception)` block?  `← Q10.3`

---

## Phase 14: Jetpack Components

### 14.1 Room — Internals
- What does `@Entity` compile to — how does Room generate the `CREATE TABLE` SQL?
- What is the `@Transaction` annotation on a DAO method — what does it guarantee atomically?
- How does Room's `Flow<List<T>>` auto-emit on data change — what invalidation mechanism drives it?
- What is `@Embedded` vs `@Relation` in Room — when does each apply?
- What is a Room Migration — what happens if you bump `version` without providing one?

### 14.2 WorkManager
- Why does a `Service` NOT guarantee background work completion — what OS policy kills it?
- What is WorkManager's guarantee — what survives process death, device reboot, and OS kill?
- What is the difference between `OneTimeWorkRequest` and `PeriodicWorkRequest` — what is the minimum period?
- How do you chain workers — what does `then()` guarantee about execution order?
- What is `ExistingWorkPolicy.REPLACE` vs `KEEP` vs `APPEND` — when do you use each?

### 14.3 Paging 3
- What is `PagingSource` vs `RemoteMediator` — what does each own?
- Why is cursor-based pagination better than offset-based — what data-shifting bug does offset suffer from?
- What does `RemoteMediator.load()` do on `LoadType.REFRESH` vs `APPEND` — what is cleared on each?
- How does Room act as the single source of truth in Paging 3 — what triggers the PagingSource to invalidate?
- What are `RemoteKey` entities and why are they needed?

### 14.4 Thread-Safe Caching
- What is the difference between `Mutex.withLock` (coroutine-native) vs `synchronized` (thread-blocking)?  `← Q7.3`
- What is the `getOrLoad` atomic check-and-load pattern — what race condition does it prevent?
- When would you use `ConcurrentHashMap.computeIfAbsent` vs a coroutine Mutex?
- What is the `LinkedHashMap(accessOrder = true)` mechanism that enables LRU eviction?  `← Q7.3`

---

## Phase 15: Networking

### 15.1 OkHttp Interceptor Chain
- What is the difference between an Application interceptor (`addInterceptor`) and a Network interceptor (`addNetworkInterceptor`)?
- Which interceptor sees cached responses and which only sees wire-level requests?
- Where should logging go — Application or Network interceptor — and why?
- What is the `Authenticator` interface — how does it differ from an `Interceptor` for handling 401s?

### 15.2 Token Refresh Pattern
- Why must token refresh use `synchronized` or `Mutex` — what concurrent 401 race does it prevent?  `← Q14.4`
- Why does `runBlocking` inside `Authenticator.authenticate()` work here despite being a blocking call?
- How do you prevent an infinite retry loop when the refresh token itself is expired?
- What is the correct way to forward the new token to all in-flight requests that received a 401 simultaneously?

### 15.3 JSON Serialization Pitfalls
- Why is Gson dangerous with Kotlin data classes — what null safety violation can it silently introduce?
- What does Kotlin Serialization do differently from Gson for `@Transient` and default values?
- What is Moshi's KSP codegen and how does it differ from reflection-based Moshi?
- When would you use `@SerializedName` (Gson) vs `@SerialName` (Kotlin Serialization)?

---

## Phase 16: Android System Internals

### 16.1 Activity and Fragment Lifecycle
- What is the exact callback order during rotation — what changed in Android P about `onSaveInstanceState` timing?
- When is `onDestroy` NOT called — what does the OS do when it kills a process for memory?
- What are the two lifecycles a Fragment has — and what memory leak does this create with ViewBinding?
- What is `repeatOnLifecycle(STARTED)` solving at the lifecycle level?  `← Q11.4`

### 16.2 Background Work Evolution
- Does a `Service` run on a background thread — what is the exact answer that eliminates candidates?
- What did Android 8 (Oreo) change about background execution limits?
- What did Android 14 change about foreground services — what is `MissingForegroundServiceTypeException`?
- What is the evolution chain: `AsyncTask` → `IntentService` → `WorkManager` — what gap does each fill?

### 16.3 Binder IPC
- What is Binder IPC — how many times is data copied in a Binder transaction (answer: once)?
- What is the Binder transaction size limit (~1MB) — what exception does exceeding it throw?
- What is the architecture: Client → Proxy (BinderProxy) → Kernel Driver → Stub (Binder) → Server?
- How does this limit affect `SavedStateHandle` and `onSaveInstanceState` data size?  `← Q13.3`

### 16.4 Zygote and App Startup
- What happens when you tap an app icon — trace the path from Launcher to first Activity frame?
- What is Zygote forking — why does it make app startup fast (copy-on-write of preloaded classes)?
- What is `ActivityThread.main()` — what does it set up before `Application.onCreate()`?
- What is `Looper.prepareMainLooper()` — what infinite loop does it start?

### 16.5 Handler, Looper, and MessageQueue
- What is the relationship: one Thread → one Looper → one MessageQueue → many Handlers?
- What is an ANR — what two conditions trigger it (5 seconds for input, 10 seconds for broadcast)?
- What happens if you create a `Handler` on a background thread without `Looper.prepare()`?
- How does `Handler.postDelayed()` relate to coroutine `delay()` on `Dispatchers.Main`?  `← Q9.2`

---

## Phase 17: Performance and Memory

### 17.1 Memory Leaks — Top 5 Causes
- What is the Activity context in singleton leak — why does `applicationContext` fix it?  `← Q2.4`
- What is the non-static inner class leak — what implicit reference does it hold to the outer class?
- What is the Handler delayed message leak — why does storing the Runnable and removing it in `onDestroy` fix it?  `← Q16.5`
- What is the `GlobalScope` coroutine leak — why is `viewLifecycleOwner.lifecycleScope` the fix?  `← Q10.4`
- What is the unregistered listener leak — name three listener types that commonly cause this?

### 17.2 RecyclerView Internals
- What is the 4-level cache: Scrap → Cache → ViewCacheExtension → RecycledViewPool?
- What does `setHasFixedSize(true)` actually do — what layout pass does it skip?
- What is the real cost of `notifyDataSetChanged()` vs `submitList()` with `DiffUtil`?
- What is Myers' diff algorithm — what is its time complexity `O(N + D²)`?
- What is the RecyclerView-inside-NestedScrollView anti-pattern — why does it destroy recycling?

### 17.3 The 16ms Budget
- What is the 16ms frame budget — what happens when you exceed it (jank, dropped frame)?
- What are the three phases of rendering: Measure → Layout → Draw — which is most expensive to trigger?
- Why should `Paint` objects never be created inside `onDraw` — what GC pressure does it introduce?  `← Q0.1`
- What is a Baseline Profile — how does it provide ART with AOT-compiled hot paths at install time?
- What is the reported startup improvement from Baseline Profiles at major apps (~30%)?

### 17.4 Testing
- What is `runTest` and how does it differ from the deprecated `runBlockingTest`?
- What is `StandardTestDispatcher` vs `UnconfinedTestDispatcher` — when does each advance time?
- What is Turbine — what does `awaitItem()` do for Flow testing?
- What is the test double hierarchy: Fake vs Mock vs Stub — when do you prefer a Fake repository?
- Why does `adb shell am kill <package>` simulate process death better than just pressing Home?  `← Q13.3`

---

## Master Follow-Up Chains
*These are the exact chains interviewers use to find where your knowledge ends.*

**Chain A — Constants:**
`val vs const val` → getter overhead → `@JvmField` limitation → `const val` inlining → why TAG can't be const → binary compatibility

**Chain B — Initialization:**
`init vs constructor` → property initializer order → open function in init trap → superclass init order → companion object timing → `const val` initialization exemption

**Chain C — Nullability to lateinit:**
`String vs String?` → JVM primitive vs reference → why Int can't be null → why lateinit forbids Int → `Delegates.notNull` alternative → `isInitialized` null check

**Chain D — Generics to Reified:**
Type erasure → `is List<String>` fails → `out/in` as compile-time only → `reified` requires inline → call-site substitution → `startActivity<T>` pattern

**Chain E — ViewModel to Process Death:**
`ViewModel survives rotation` → `ViewModelStore` retained → process death kills everything → `SavedStateHandle` hooks `onSaveInstanceState` → Bundle 1MB limit → Room/DataStore for complex state

**Chain F — Coroutine Cancellation:**
`suspend` = state machine, not thread → `CancellationException` must be re-thrown → `try-catch(Exception)` swallows it → coroutine leaks → `viewModelScope` auto-cancels on `onCleared` → `repeatOnLifecycle` for UI safety

**Chain G — Flow to StateFlow:**
Cold Flow → each collector independent → `shareIn`/`stateIn` makes it hot → `StateFlow` skips duplicates → navigation event bug → `SharedFlow(replay=0)` for events → `Channel` as alternative

**Chain H — Structured Concurrency:**
`GlobalScope` leaks → `viewModelScope` uses `SupervisorJob` → `childCancelled()` returns false → sibling isolation → `CoroutineExceptionHandler` root only → `async` exception at `await()`

---

*Total: ~180 focused questions across 17 phases + 8 master chains.*
*Every question traces from JVM mechanism → Kotlin abstraction → Android application → interview trap.*
