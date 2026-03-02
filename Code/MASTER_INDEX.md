# Master Index — Java · Kotlin · Android Interview Curriculum

This index connects all three curricula (Java J0–J9, Kotlin 00–18, Android A0–A5) into a navigable study guide. Use it to jump between related topics across languages, or to find all coverage of a concept regardless of which file it lives in.

---

## Java Curriculum (J0–J9)

Located at: `Java/Questions/`

| File | Topics |
|------|--------|
| [J0 — JVM Mental Model](Java/Questions/J0_jvm_mental_model.md) | Primitives vs References, Autoboxing & Integer Cache, String Pool, Bytecode & invokedynamic |
| [J1 — Type System](Java/Questions/J1_type_system.md) | Widening/narrowing, casting, type inference |
| [J2 — OOP Internals](Java/Questions/J2_oop.md) | final/abstract, Interfaces (default/static/private), Enums, Records, Sealed Classes |
| [J3 — Generics](Java/Questions/J3_generics.md) | Type erasure, wildcards, bounded type parameters, PECS |
| [J4 — Functional Java](Java/Questions/J4_functional.md) | Lambdas, Functional Interfaces, Streams (lazy pipeline), Parallel Streams |
| [J5 — Collections](Java/Questions/J5_collections.md) | ArrayList vs LinkedList, HashMap internals, TreeMap/LinkedHashMap, Concurrent collections |
| [J6 — Concurrency Fundamentals](Java/Questions/J6_concurrency_fundamentals.md) | Thread lifecycle, synchronized & monitor, JMM & volatile, wait/notify |
| [J7 — Concurrent Utilities](Java/Questions/J7_concurrent_utilities.md) | Executor framework, ThreadPoolExecutor, Locks, Atomics, Synchronizers, CompletableFuture |
| [J8 — GC & JVM Tuning](Java/Questions/J8_gc_and_jvm_tuning.md) | Generational GC, G1GC/ZGC, JVM flags, memory leaks, heap dumps |
| [J9 — Modern Java](Java/Questions/J9_modern_java.md) | var, JPMS modules, switch expressions, pattern matching, Virtual Threads, Structured Concurrency |
| [Java Master Chains](Java/Questions/java_master_chains.md) | Interview chains A–I: JVM, Generics, OOP/JIT, Streams, Collections, volatile/JMM, ThreadPoolExecutor, GC, Virtual Threads |

---

## Kotlin Curriculum (00–18)

Located at: `Kotlin/Questions/`

| File | Topics |
|------|--------|
| [00 — JVM Mental Model](Kotlin/Questions/00_jvm_mental_model.md) | Kotlin on JVM, bytecode, interop |
| [01 — Type System](Kotlin/Questions/01_type_system_foundations.md) | Null safety, smart casts, type hierarchy |
| [02 — Classes & Objects](Kotlin/Questions/02_classes_and_objects.md) | data class, object, companion object, sealed, enum |
| [02.5 — Initialization](Kotlin/Questions/02_5_initialization_mechanics.md) | init blocks, lazy, lateinit, by delegates |
| [03 — Generics & Variance](Kotlin/Questions/03_generics_and_variance.md) | in/out variance, reified, star projection |
| [04 — Functions & Lambdas](Kotlin/Questions/04_functions_lambdas_inlining.md) | Higher-order functions, inline, crossinline, noinline |
| [05 — Properties & Delegation](Kotlin/Questions/05_properties_and_delegation.md) | Custom getters/setters, delegated properties, by lazy |
| [06 — Extension Functions](Kotlin/Questions/06_extension_functions.md) | Extensions, scope functions (let/run/apply/also/with) |
| [07 — Collections & Sequences](Kotlin/Questions/07_collections_and_sequences.md) | Immutable/mutable collections, Sequence vs List, operators |
| [08 — Other Kotlin Features](Kotlin/Questions/08_other_kotlin_features.md) | Destructuring, operator overloading, DSLs |
| [09 — Coroutines](Kotlin/Questions/09_coroutines_execution_mechanics.md) | suspend, CoroutineScope, Dispatchers, launch/async/await |
| [10 — Structured Concurrency](Kotlin/Questions/10_structured_concurrency.md) | Job hierarchy, cancellation, SupervisorScope, exception handling |
| [11 — Flow](Kotlin/Questions/11_flow.md) | Cold vs hot Flow, StateFlow, SharedFlow, operators, backpressure |
| [12 — Reflection & Operators](Kotlin/Questions/12_reference_operators_and_reflection.md) | KClass, KProperty, reflection, operator functions |
| [13 — Android Architecture](Kotlin/Questions/13_android_architecture.md) | MVVM with Kotlin, ViewModel, LiveData, StateFlow |
| [14 — Jetpack Components](Kotlin/Questions/14_jetpack_components.md) | Room, Hilt, Navigation, DataStore, WorkManager |
| [15 — Networking](Kotlin/Questions/15_networking.md) | Retrofit, OkHttp, interceptors, Moshi/Gson |
| [16 — Android System Internals](Kotlin/Questions/16_android_system_internals.md) | Binder, ART, processes from Kotlin perspective |
| [17 — Performance & Memory](Kotlin/Questions/17_performance_and_memory.md) | Memory leaks, profiling, optimizations |
| [18 — Testing](Kotlin/Questions/18_testing.md) | Test pyramid, Mockk, fakes vs mocks, ViewModel testing, Turbine, Room, Hilt test modules, Compose UI tests |
| [Kotlin Master Chains](Kotlin/Questions/master_chains.md) | Interview chains A–K: Constants, Init, Nullability, Generics, ViewModel, Cancellation, Flow, Concurrency, HashMap, Architecture, Inline |

---

## Android Curriculum (A0–A5)

Located at: `Android/Questions/`

| File | Topics |
|------|--------|
| [A0 — Android Platform](Android/Questions/A0_android_platform.md) | System stack (5 layers), Zygote/app startup, ART/DEX/R8, Binder IPC |
| [A1 — Activity & Fragment](Android/Questions/A1_activity_fragment.md) | Activity lifecycle, config changes/ViewModel/Bundle, Fragment two-lifecycles, Tasks/launch modes |
| [A2 — Main Thread & Views](Android/Questions/A2_main_thread_and_views.md) | Looper/MessageQueue/Handler, ANR detection, View measure/layout/draw, Choreographer/Vsync |
| [A3 — Architecture Patterns](Android/Questions/A3_architecture_patterns.md) | MVC/MVP/MVVM/MVI/Clean Architecture, directory structures, interview scenarios |
| [A4 — Offline & Data Layer](Android/Questions/A4_offline_and_data.md) | Offline-first, Repository pattern, sync strategies, conflict resolution |
| [A5 — Jetpack Compose](Android/Questions/A5_jetpack_compose.md) | Recomposition model, remember/rememberSaveable, side effects, derivedStateOf, state hoisting, ViewModel integration, performance |

---

## Concept-First Navigation

Find all coverage of a topic across the three curricula:

### Concurrency & Threading
| Concept | Java | Kotlin | Android |
|---------|------|--------|---------|
| Thread model basics | [J6](Java/Questions/J6_concurrency_fundamentals.md) | [K09](Kotlin/Questions/09_coroutines_execution_mechanics.md) | [A2.1](Android/Questions/A2_main_thread_and_views.md) |
| Thread pools & Executors | [J7.1](Java/Questions/J7_concurrent_utilities.md) | [K09 Dispatchers](Kotlin/Questions/09_coroutines_execution_mechanics.md) | — |
| Synchronization & locks | [J6.2](Java/Questions/J6_concurrency_fundamentals.md), [J7.3](Java/Questions/J7_concurrent_utilities.md) | [K09](Kotlin/Questions/09_coroutines_execution_mechanics.md) | — |
| Coroutines / Virtual Threads | [J9.3 Virtual Threads](Java/Questions/J9_modern_java.md) | [K09](Kotlin/Questions/09_coroutines_execution_mechanics.md), [K10](Kotlin/Questions/10_structured_concurrency.md) | [A2.1 Handler](Android/Questions/A2_main_thread_and_views.md) |
| Background work | [J7.1](Java/Questions/J7_concurrent_utilities.md) | [K09](Kotlin/Questions/09_coroutines_execution_mechanics.md) | [A4.4 WorkManager](Android/Questions/A4_offline_and_data.md) |
| CompletableFuture vs Coroutines | [J7.6](Java/Questions/J7_concurrent_utilities.md) | [K09](Kotlin/Questions/09_coroutines_execution_mechanics.md) | — |

### Memory & Garbage Collection
| Concept | Java | Kotlin | Android |
|---------|------|--------|---------|
| Heap structure | [J0.1](Java/Questions/J0_jvm_mental_model.md), [J8.1](Java/Questions/J8_gc_and_jvm_tuning.md) | [K00](Kotlin/Questions/00_jvm_mental_model.md) | [A0.3 ART](Android/Questions/A0_android_platform.md) |
| GC algorithms | [J8.2](Java/Questions/J8_gc_and_jvm_tuning.md) | — | [A0.3](Android/Questions/A0_android_platform.md) |
| Memory leaks | [J8.4](Java/Questions/J8_gc_and_jvm_tuning.md) | [K17](Kotlin/Questions/17_performance_and_memory.md) | [A1.3 ViewBinding](Android/Questions/A1_activity_fragment.md), [A3.3 MVP detach](Android/Questions/A3_architecture_patterns.md) |
| Object header / references | [J0.1](Java/Questions/J0_jvm_mental_model.md) | [K00](Kotlin/Questions/00_jvm_mental_model.md) | — |

### Data & Persistence
| Concept | Java | Kotlin | Android |
|---------|------|--------|---------|
| Collections internals | [J5](Java/Questions/J5_collections.md) | [K07](Kotlin/Questions/07_collections_and_sequences.md) | — |
| Offline-first / Repository | — | [K13](Kotlin/Questions/13_android_architecture.md), [K14](Kotlin/Questions/14_jetpack_components.md) | [A4](Android/Questions/A4_offline_and_data.md) |
| Room / SQLite | — | [K14](Kotlin/Questions/14_jetpack_components.md) | [A4.1](Android/Questions/A4_offline_and_data.md) |
| Networking / Retrofit | — | [K15](Kotlin/Questions/15_networking.md) | [A4.2](Android/Questions/A4_offline_and_data.md) |
| Background sync | [J7.1](Java/Questions/J7_concurrent_utilities.md) | [K14](Kotlin/Questions/14_jetpack_components.md) | [A4.4](Android/Questions/A4_offline_and_data.md) |

### Architecture & Design Patterns
| Concept | Java | Kotlin | Android |
|---------|------|--------|---------|
| MVVM | — | [K13](Kotlin/Questions/13_android_architecture.md) | [A3.4](Android/Questions/A3_architecture_patterns.md) |
| MVI | — | [K13](Kotlin/Questions/13_android_architecture.md) | [A3.5](Android/Questions/A3_architecture_patterns.md) |
| Clean Architecture | — | [K13](Kotlin/Questions/13_android_architecture.md) | [A3.6](Android/Questions/A3_architecture_patterns.md) |
| Dependency Injection (Hilt) | — | [K14](Kotlin/Questions/14_jetpack_components.md) | [A3.6 — Clean Architecture](Android/Questions/A3_architecture_patterns.md) |
| Reactive programming (Flow) | [J4.3 Streams](Java/Questions/J4_functional.md) | [K11](Kotlin/Questions/11_flow.md) | [A4.1](Android/Questions/A4_offline_and_data.md) |

### Type System & Language Features
| Concept | Java | Kotlin | Android |
|---------|------|--------|---------|
| Null safety | J1 (Optional) | [K01](Kotlin/Questions/01_type_system_foundations.md) | — |
| Sealed classes | [J2.5](Java/Questions/J2_oop.md) | [K02](Kotlin/Questions/02_classes_and_objects.md) | [A3.5 UiState](Android/Questions/A3_architecture_patterns.md) |
| Data classes / Records | [J2.4](Java/Questions/J2_oop.md) | [K02](Kotlin/Questions/02_classes_and_objects.md) | [A4.3 Domain models](Android/Questions/A4_offline_and_data.md) |
| Generics | [J3](Java/Questions/J3_generics.md) | [K03](Kotlin/Questions/03_generics_and_variance.md) | — |
| Lambdas & functional | [J4.1](Java/Questions/J4_functional.md) | [K04](Kotlin/Questions/04_functions_lambdas_inlining.md) | — |

### Android-Specific Internals
| Concept | Java | Kotlin | Android |
|---------|------|--------|---------|
| Binder IPC | — | [K16](Kotlin/Questions/16_android_system_internals.md) | [A0.4](Android/Questions/A0_android_platform.md) |
| Activity lifecycle | — | — | [A1.1](Android/Questions/A1_activity_fragment.md) |
| ViewModel survival | — | [K13](Kotlin/Questions/13_android_architecture.md) | [A1.2](Android/Questions/A1_activity_fragment.md), [A3.4](Android/Questions/A3_architecture_patterns.md) |
| Main thread / ANR | [J6](Java/Questions/J6_concurrency_fundamentals.md) | [K09](Kotlin/Questions/09_coroutines_execution_mechanics.md) | [A2.2](Android/Questions/A2_main_thread_and_views.md) |
| View rendering | — | — | [A2.3](Android/Questions/A2_main_thread_and_views.md), [A2.4](Android/Questions/A2_main_thread_and_views.md) |

---

## Recommended Study Order

### Track A: Core Java (JVM internals first)
J0 → J1 → J2 → J3 → J4 → J5 → J6 → J7 → J8 → J9

### Track B: Kotlin Modern Android
K00 → K01 → K02 → K03 → K04 → K09 → K10 → K11 → K13 → K14 → K15

### Track C: Android Systems
A0 → A1 → A2 → A3 → A4

### Track D: Interview Prep (concept clusters)
1. **Concurrency**: J6 → J7 → K09 → K10 → A2.1–A2.2 → J9.3 (Virtual Threads)
2. **Memory**: J0 → J8 → K17 → A0.3 (ART)
3. **Architecture**: A3 → A4 → K13 → K14
4. **Type System**: J2 → J3 → K01 → K02 → K03

---

*All files follow the same format: WHY this matters → Core concept with ASCII diagrams → Code examples → Interview Traps → Master Summary → Cross-references*
