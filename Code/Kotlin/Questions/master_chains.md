# Master Follow-Up Chains

> These are the interview chains — each link is a question that naturally leads to the next. Interviewers follow these paths to find where your knowledge ends.

## Navigation
| Phase | File |
|-------|------|
| 0 — JVM Mental Model | [00_jvm_mental_model.md](00_jvm_mental_model.md) |
| 1 — Type System | [01_type_system_foundations.md](01_type_system_foundations.md) |
| 17 — Performance & Memory | [17_performance_and_memory.md](17_performance_and_memory.md) |
| **Master Chains** | ← You are here |

---

## Chain A — Constants

*"Tell me about `val` vs `const val`."*

```
val BASE_URL = "..."   [Q1.1]
    │
    ├──► Compiles to a GETTER: getBASE_URL()   [Q0.4]
    │    └──► Every access is INVOKEVIRTUAL (virtual dispatch + stack frame)
    │
val vs const val — what's different?
    │
    ├──► const val TAG = "..."
    │    └──► Inlined as LDC at every call site — no class loading, no method call   [Q1.1]
    │
Why can't TAG = SomeClass::class.simpleName?
    │
    └──► simpleName is a RUNTIME reflection call — not known at compile time   [Q3.3]
         const val requires compile-time constant (primitive or String)
         └──► The 3 constraints: must be primitive/String, compile-time value,
              top-level or companion object
    │
@JvmField vs const val — same thing?
    │
    └──► @JvmField: exposes field directly (no getter), but still runtime-assigned   [Q1.1]
         const val: inlined at compile time — no class loading at all
         Binary compatibility hazard: changing const val value requires recompile of callers!
```

---

## Chain B — Initialization

*"What is the difference between a primary constructor and `init`?"*

```
Primary constructor vs init block   [Q2.5.1]
    │
    ├──► Both compile to the SAME <init> method
    │    └──► Interleaved in declaration order (not all properties, then all init blocks)
    │
What order do they run in?
    │
    ├──► Property initializer 1 → init block 1 → property 2 → init block 2...
    │    └──► BUG: reference a property declared BELOW before it's set → NPE   [Q2.5.5]
    │
What about secondary constructors?
    │
    ├──► Must delegate to primary via this() — JVM requires constructor chain   [Q2.5.2]
    │    └──► Delegation runs FIRST, then secondary body
    │
What happens in a subclass?
    │
    ├──► Superclass <init> runs BEFORE subclass <init>   [Q2.5.3]
    │    └──► TRAP: open function in super init → sees uninitialized subclass fields
    │         "null" printed even though field is assigned in subclass!
    │
When does companion object initialize?
    │
    ├──► Lazily — on first access to a non-const member   [Q2.5.4]
    │    └──► const val access does NOT trigger companion init (inlined at compile time)
    │
What about circular object initialization?
    │
    └──► Object A's init accesses Object B, and B's init accesses A → DEADLOCK   [Q2.5.4]
```

---

## Chain C — Nullability to `lateinit`

*"What's the difference between `String` and `String?`?"*

```
String vs String? at JVM level   [Q1.2]
    │
    ├──► SAME JVM type (java.lang.String)
    │    └──► Kotlin's null safety is compile-time only (@NotNull/@Nullable annotations)
    │
What is a platform type (String!)?
    │
    ├──► Java code with no @Nullable annotation → Kotlin doesn't know nullability   [Q1.2]
    │    └──► Risk: assign String! to String → silent NPE at runtime
    │
Why can't Int be null?
    │
    ├──► Int maps to JVM primitive int — no object, no null sentinel   [Q0.2]
    │    └──► Int? maps to java.lang.Integer (boxed — can be null)
    │
So why does `lateinit var count: Int` fail?
    │
    ├──► lateinit uses null as the "uninitialized" sentinel   [Q5.1]
    │    └──► int can't be null → can't use null as sentinel → compile error
    │
How does Delegates.notNull<Int>() work?
    │
    ├──► Stores value as Any? (boxes the Int), uses null as sentinel   [Q5.3]
    │    └──► Throws IllegalStateException (not UninitializedPropertyAccessException)
    │
How does ::property.isInitialized work?
    │
    └──► Compiles to a simple != null check on the backing field   [Q5.1]
         NOT a reflection call — cheap
         Class-private: can't check from outside (TOCTOU risk, encapsulation)
```

---

## Chain D — Generics to Reified

*"Why does `list is List<String>` fail at runtime?"*

```
Type erasure — what is it?   [Q3.1]
    │
    ├──► JVM backward compatibility with Java 1.0 — no generics in bytecode
    │    └──► List<String> and List<Int> are BOTH just List at runtime
    │
So is checks on generic types fail?
    │
    ├──► Compiler refuses: "Cannot check for erased type"
    │    └──► list is List<*> works — checks for any List, not specific element type
    │
What about variance? (out T, in T)   [Q3.2]
    │
    ├──► out T (covariant): Container<Dog> IS-A Container<Animal>
    │    └──► T only in OUT positions (returned, never stored) — safe to read as Animal
    │
    ├──► in T (contravariant): Container<Animal> IS-A Container<Dog>
    │    └──► T only in IN positions (accepted, never returned) — safe to accept Dog
    │
    └──► Compile-time only — both erased to Object in bytecode
    │
How does reified defeat erasure?   [Q3.3]
    │
    ├──► requires inline function — body pasted at call site
    │    └──► At call site: concrete type is known → compiler substitutes T with actual type
    │
    ├──► startActivity<DetailActivity>() — how does this work?
    │    └──► inline fun <reified T: Activity> startActivity()
    │         T::class.java is substituted with DetailActivity::class.java at call site
    │
Why can't a class have reified type parameter?
    │
    └──► Classes are instantiated — not inlined. Type parameter is always erased.
         Only function type parameters can be reified.
```

---

## Chain E — ViewModel to Process Death

*"How does ViewModel survive rotation?"*

```
ViewModel survives configuration change   [Q13.3]
    │
    ├──► Via ViewModelStore retained in NonConfigurationInstances
    │    └──► Activity.onRetainNonConfigurationInstance() saves ViewModelStore
    │         New Activity retrieves it from lastNonConfigurationInstance
    │
Does ViewModel survive process death?
    │
    ├──► NO. Process death kills everything in memory.   [Q13.3]
    │    └──► onDestroy() is NOT called on process death!
    │
What does survive process death?
    │
    ├──► SavedStateHandle — hooked into onSaveInstanceState   [Q13.3]
    │    └──► Bundle → Binder IPC → system server persists it
    │
What are the limits?
    │
    ├──► Binder transaction size ~1MB   [Q16.3]
    │    └──► TransactionTooLargeException if exceeded
    │         Store only small data: IDs, selected indices, tab positions
    │
What about large data?
    │
    └──► Room database (persists to SQLite) for large structured data
         DataStore (persists to disk) for preferences
         Re-fetch from network using the saved identifier
```

---

## Chain F — Coroutine Cancellation

*"What does `suspend` actually do?"*

```
suspend = CPS transformation   [Q9.1]
    │
    ├──► Compiler adds Continuation<T> parameter and a state machine
    │    └──► label field tracks which suspension point to resume at
    │
Where are local variables stored during suspension?
    │
    ├──► Promoted to fields on the Continuation object (heap, not stack)   [Q9.1]
    │    └──► Stack frame is freed; Continuation keeps the variables alive
    │
Does suspend mean it runs on a background thread?
    │
    ├──► NO. suspend is about calling convention, not threading.   [Q9.1]
    │    └──► Thread is determined by Dispatcher (Dispatchers.IO, Main, Default)
    │
What is CancellationException?   [Q10.3]
    │
    ├──► Thrown at next suspension point when job.cancel() is called
    │    └──► MUST be re-thrown — never swallowed in catch(Exception)!
    │
What if I swallow it?
    │
    ├──► Coroutine continues running even after cancel() — LEAK   [Q4.3, Q10.3]
    │    └──► Scope never completes cleanup
    │
How do viewModelScope and lifecycleScope auto-cancel?
    │
    └──► viewModelScope uses SupervisorJob — cancelled in ViewModel.onCleared()   [Q13.3]
         lifecycleScope — cancelled when lifecycle reaches DESTROYED
         repeatOnLifecycle(STARTED) — cancels/restarts on lifecycle transitions   [Q11.4]
```

---

## Chain G — Flow to StateFlow

*"What is a cold Flow?"*

```
Cold Flow — producer runs per collector   [Q11.1]
    │
    ├──► Each collect{} starts a NEW execution of the flow { } block
    │    └──► Like Sequence — lazy, independent per subscriber
    │
What makes StateFlow and SharedFlow hot?
    │
    ├──► Producer is independent of collectors — always running   [Q11.3]
    │    └──► Collectors tap into existing stream, may miss past values
    │
How do you convert a cold flow to hot?
    │
    ├──► stateIn(scope, started, initialValue) → StateFlow   [Q11.3]
    │    shareIn(scope, started, replay) → SharedFlow
    │
StateFlow skips duplicate consecutive emissions?
    │
    ├──► Yes — uses equals() to compare new vs current value   [Q11.3]
    │    └──► This is a BUG for navigation events: 2nd nav to same screen is dropped!
    │
How to fix navigation events?
    │
    ├──► SharedFlow(replay=0) — no duplicate filter, no replay on subscribe   [Q11.3]
    │    └──► Or Channel — acts as a queue, exactly-once delivery
    │
Why does collectAsStateWithLifecycle matter?
    │
    └──► collectAsState (wrong): always collects, even in background — wastes resources
         collectAsStateWithLifecycle (correct): stops collecting below STARTED   [Q11.4]
```

---

## Chain H — Structured Concurrency

*"What's the difference between `launch` and `async`?"*

```
launch returns Job — async returns Deferred<T>   [Q9.3]
    │
    ├──► Deferred extends Job — adds await() for retrieving result
    │
Does async propagate exceptions immediately?
    │
    ├──► YES — propagates to parent NOW, not only at await()   [Q9.3, Q10.3]
    │    └──► ONLY contained in supervisorScope — then only at await()
    │
Why doesn't try-catch around launch{} work?
    │
    ├──► launch returns immediately — exception is on a DIFFERENT call stack   [Q9.3]
    │    └──► Exception travels through coroutine hierarchy, not JVM exception mechanism
    │
How does cancellation propagate?
    │
    ├──► job.cancel() → CancellationException thrown at next suspend point   [Q10.1]
    │    └──► Propagates DOWN the Job tree (parent cancels all children)
    │
How does an exception propagate?
    │
    ├──► Exception propagates UP the Job tree → parent cancels all siblings   [Q10.1]
    │    └──► Unless SupervisorJob is used → sibling isolation
    │
What's the difference between coroutineScope and supervisorScope?   [Q10.2]
    │
    ├──► coroutineScope: one child fails → all fail (all-or-nothing)
    │    supervisorScope: one child fails → others continue (independent)
    │
When does CoroutineExceptionHandler fire?   [Q10.3]
    │
    └──► ONLY on root coroutines launched with launch (not async, not nested)
         In viewModelScope: uncaught exceptions go there
         Inside nested launch: exception propagates up first, CEH is last resort
```

---

## Quick Reference: Interview Trap Summary

```
┌──────────────────────────────────────────────────────────────────────────┐
│ TRAP 1: "lateinit var count: Int" — compile error! Int is primitive,   │
│         can't use null as sentinel. Use Delegates.notNull<Int>().       │
│                                                                          │
│ TRAP 2: open function in init block → sees uninitialized subclass       │
│         fields. Returns null/0. Kotlin's most famous silent bug.        │
│                                                                          │
│ TRAP 3: try-catch around launch{} never fires. Exception travels        │
│         through Job hierarchy, not JVM exception stack.                  │
│                                                                          │
│ TRAP 4: async propagates exception IMMEDIATELY to parent. Not only at   │
│         await(). Only contained in supervisorScope.                      │
│                                                                          │
│ TRAP 5: StateFlow skips duplicates. Use SharedFlow(replay=0) for        │
│         navigation events — second nav to same screen WON'T be lost.    │
│                                                                          │
│ TRAP 6: lifecycleScope.launch { flow.collect{} } continues in bg.      │
│         Use repeatOnLifecycle(STARTED) to stop in background.           │
│                                                                          │
│ TRAP 7: Service runs on the MAIN THREAD. You must create threads/       │
│         coroutines yourself inside a Service.                            │
│                                                                          │
│ TRAP 8: ViewModel survives rotation but NOT process death.              │
│         onDestroy is NOT called on process death.                        │
│                                                                          │
│ TRAP 9: list is List<String> fails — erasure. Use list is List<*>.      │
│                                                                          │
│ TRAP 10: MutableList<Dog> is NOT a subtype of MutableList<Animal>.     │
│          List<Dog> IS (covariant). The difference is write ability.     │
└──────────────────────────────────────────────────────────────────────────┘
```

---

*All 8 chains cover the complete interview question space from JVM fundamentals to Android production patterns.*
