# RxJava Study Guide — Index

**Target:** SDE-2 Android developer | **Style:** First principles, interview-ready
**Scope:** RxJava 2/3 compatible | **Code:** Kotlin only

---

## Phase Table

| File | Topic | What You'll Know After |
|------|-------|------------------------|
| [00_why_rxjava.md](00_why_rxjava.md) | The Problem | Why callbacks break at scale; the reactive mental model |
| [01_observer_pattern.md](01_observer_pattern.md) | The Foundation | onNext/onError/onComplete contract and guarantees |
| [02_observable_types.md](02_observable_types.md) | What You Subscribe To | Single/Maybe/Completable/Observable/Flowable and cold vs hot |
| [03_operators.md](03_operators.md) | Transform the Stream | map/flatMap/concatMap/switchMap and when to use each |
| [04_schedulers.md](04_schedulers.md) | Which Thread | subscribeOn vs observeOn; IO/Computation/Main |
| [05_subjects.md](05_subjects.md) | Imperative Meets Reactive | Publish/Behavior/Replay/AsyncSubject and when to use them |
| [06_error_handling.md](06_error_handling.md) | The Error Contract | onErrorReturn/Resume/retry/retryWhen patterns |
| [07_backpressure_flowable.md](07_backpressure_flowable.md) | When Producer > Consumer | Flowable and BUFFER/DROP/LATEST/ERROR strategies |
| [08_disposables_lifecycle.md](08_disposables_lifecycle.md) | Memory Leaks | CompositeDisposable and ViewModel lifecycle |
| [09_android_patterns.md](09_android_patterns.md) | Daily Work | Retrofit, Room, search-as-you-type, ViewModel template |
| [10_decision_maps.md](10_decision_maps.md) | Birds-Eye View | Decision trees and one-page operator cheat sheet |

**Estimated read time:**
00: 10 min | 01: 12 min | 02: 12 min | 03: 18 min | 04: 12 min |
05: 12 min | 06: 12 min | 07: 12 min | 08: 12 min | 09: 15 min | 10: 10 min

---

## "I Need to Do X" — Quick Reference

| I need to... | Go to |
|---|---|
| Understand WHY RxJava exists | [00 §RX.00.1](00_why_rxjava.md) |
| Understand onNext/onError/onComplete rules | [01 §RX.01.2](01_observer_pattern.md) |
| Choose between Single/Maybe/Completable/Observable | [02 §RX.02.1](02_observable_types.md) |
| Understand cold vs hot Observable | [02 §RX.02.2](02_observable_types.md) |
| Choose between map/flatMap/concatMap/switchMap | [03 §RX.03.2](03_operators.md) |
| Implement search-as-you-type with debounce | [03 §RX.03.3](03_operators.md) + [09 §RX.09.3](09_android_patterns.md) |
| Combine two streams (zip, combineLatest) | [03 §RX.03.4](03_operators.md) |
| Set up threading for Android | [04 §RX.04.2](04_schedulers.md) |
| Understand subscribeOn vs observeOn | [04 §RX.04.2](04_schedulers.md) |
| Choose between Subject types | [05 §RX.05.2](05_subjects.md) |
| Implement retry with exponential backoff | [06 §RX.06.4](06_error_handling.md) |
| Decide between onErrorReturn and onErrorResumeNext | [06 §RX.06.6](06_error_handling.md) |
| Understand backpressure and Flowable | [07 §RX.07.1](07_backpressure_flowable.md) |
| Choose BackpressureStrategy | [07 §RX.07.2](07_backpressure_flowable.md) |
| Prevent memory leaks (CompositeDisposable) | [08 §RX.08.2](08_disposables_lifecycle.md) |
| Integrate Retrofit with RxJava | [09 §RX.09.1](09_android_patterns.md) |
| Integrate Room with RxJava | [09 §RX.09.2](09_android_patterns.md) |
| Decide RxJava vs Flow migration | [09 §RX.09.5](09_android_patterns.md) |
| Get a one-page operator cheat sheet | [10 §RX.10.7](10_decision_maps.md) |
| See all decision trees at once | [10_decision_maps.md](10_decision_maps.md) |

---

## Recommended Study Tracks

### Track 1: Complete Beginner (read in order)
00 → 01 → 02 → 04 → 03 → 06 → 08 → 09 → 05 → 07 → 10

### Track 2: Interview Prep (know the traps)
01 (contract) → 02 (cold/hot) → 03 (flatMap family) → 04 (threading) →
06 (error contract) → 08 (leaks) → 10 (decision trees)

### Track 3: Daily Reference (skip to the problem)
10 (decision maps) → specific file for depth

### Track 4: Backpressure Focus
02 (Observable vs Flowable intro) → 07 (full backpressure) → 09 (Room pattern)

---

## Key Invariants to Memorize

```
1. onError / onComplete are TERMINAL — stream dies after either
2. subscribeOn = source thread (only first call wins)
   observeOn   = downstream thread (each call takes effect)
3. Cold Observable = fresh stream per subscriber (Retrofit = new call each time)
   Hot Observable  = shared stream (Subject, UI events)
4. Always save Disposable; call compositeDisposable.clear() in onCleared()
5. flatMap  = parallel, unordered
   concatMap = sequential, ordered
   switchMap = cancel previous, only latest
6. Flowable for Room live queries. Observable for UI events.
7. BehaviorSubject for ViewModel state (replays last value to new subscribers)
```

---

## Direct Section Links

### 00 — Why RxJava?
[RX.00.1 The Callback Problem](00_why_rxjava.md#rx001--the-callback-problem) |
[RX.00.2 What Reactive Means](00_why_rxjava.md#rx002--what-reactive-means) |
[RX.00.3 RxJava vs Coroutines/Flow](00_why_rxjava.md#rx003--rxjava-vs-coroutinesflow-when-each-wins)

### 01 — Observer Pattern
[RX.01.1 Classic Observer](01_observer_pattern.md#rx011--classic-observer-pattern) |
[RX.01.2 Observable→Observer Contract](01_observer_pattern.md#rx012--rxjavas-observable--observer-contract) |
[RX.01.3 Three Signals In Depth](01_observer_pattern.md#rx013--the-three-signals-in-depth) |
[RX.01.4 Interview Traps](01_observer_pattern.md#rx014--interview-traps)

### 02 — Observable Types
[RX.02.1 The Five Types](02_observable_types.md#rx021--the-five-types) |
[RX.02.2 Cold vs Hot](02_observable_types.md#rx022--cold-vs-hot-observable) |
[RX.02.3 Lazy Creation](02_observable_types.md#rx023--lazy-creation-nothing-happens-until-subscribe) |
[RX.02.4 Interview Traps](02_observable_types.md#rx024--interview-traps)

### 03 — Operators
[RX.03.1 Category Table](03_operators.md#rx031--operator-categories) |
[RX.03.2 Flattening Operators](03_operators.md#rx032--the-flattening-operators-most-confused-group) |
[RX.03.3 Filter Operators](03_operators.md#rx033--filter-operators) |
[RX.03.4 Combine Operators](03_operators.md#rx034--combine-operators) |
[RX.03.5 Utility Operators](03_operators.md#rx035--utility-operators-side-effects) |
[RX.03.6 Interview Traps](03_operators.md#rx036--interview-traps)

### 04 — Schedulers
[RX.04.1 Scheduler Types](04_schedulers.md#rx041--scheduler-types) |
[RX.04.2 subscribeOn vs observeOn](04_schedulers.md#rx042--subscribeon-vs-observeon) |
[RX.04.3 Multiple Calls](04_schedulers.md#rx043--multiple-subscribeon--observeon-calls) |
[RX.04.4 Threading Reality](04_schedulers.md#rx044--threading-reality-what-actually-happens) |
[RX.04.5 Interview Traps](04_schedulers.md#rx045--interview-traps)

### 05 — Subjects
[RX.05.1 What Is a Subject](05_subjects.md#rx051--what-is-a-subject) |
[RX.05.2 The Four Subject Types](05_subjects.md#rx052--the-four-subject-types) |
[RX.05.3 Subject vs Observable.create](05_subjects.md#rx053--when-to-use-subject-vs-observablecreate) |
[RX.05.4 Interview Traps](05_subjects.md#rx054--interview-traps)

### 06 — Error Handling
[RX.06.1 Core Rule](06_error_handling.md#rx061--the-core-rule-onerror-is-terminal) |
[RX.06.2 onErrorReturn](06_error_handling.md#rx062--onerrorreturn-fallback-value) |
[RX.06.3 onErrorResumeNext](06_error_handling.md#rx063--onerrorresumenext-fallback-stream) |
[RX.06.4 retry / retryWhen](06_error_handling.md#rx064--retry-and-retrywhen) |
[RX.06.5 Decision Tree](06_error_handling.md#rx065--error-handling-decision-tree) |
[RX.06.6 Interview Traps](06_error_handling.md#rx066--interview-traps)

### 07 — Backpressure & Flowable
[RX.07.1 The Problem](07_backpressure_flowable.md#rx071--the-backpressure-problem) |
[RX.07.2 BackpressureStrategy](07_backpressure_flowable.md#rx072--backpressurestrategy-comparison) |
[RX.07.3 Observable vs Flowable](07_backpressure_flowable.md#rx073--observable-vs-flowable-decision) |
[RX.07.4 Creation Patterns](07_backpressure_flowable.md#rx074--flowable-creation-patterns) |
[RX.07.5 Interview Traps](07_backpressure_flowable.md#rx075--interview-traps)

### 08 — Disposables & Lifecycle
[RX.08.1 Disposable Contract](08_disposables_lifecycle.md#rx081--the-disposable-contract) |
[RX.08.2 CompositeDisposable Pattern](08_disposables_lifecycle.md#rx082--compositedisposable-the-viewmodel-pattern) |
[RX.08.3 Memory Leak Anatomy](08_disposables_lifecycle.md#rx083--memory-leak-anatomy) |
[RX.08.4 RxLifecycle vs Manual](08_disposables_lifecycle.md#rx084--rxlifecycle-vs-manual-dispose) |
[RX.08.5 isDisposed Check](08_disposables_lifecycle.md#rx085--isdisposed-check-in-callbacks) |
[RX.08.6 Interview Traps](08_disposables_lifecycle.md#rx086--interview-traps)

### 09 — Android Patterns
[RX.09.1 Retrofit Pattern](09_android_patterns.md#rx091--retrofit--rxjava-singleresponse-pattern) |
[RX.09.2 Room Pattern](09_android_patterns.md#rx092--room--rxjava-flowablelistt-live-queries) |
[RX.09.3 Search + debounce](09_android_patterns.md#rx093--search-with-debounce--switchmap) |
[RX.09.4 ViewModel Template](09_android_patterns.md#rx094--viewmodel--compositedisposable-complete-template) |
[RX.09.5 RxJava vs Flow Migration](09_android_patterns.md#rx095--rxjava-vs-flow-migration-decision-table)

### 10 — Decision Maps
[RX.10.1 Which Type?](10_decision_maps.md#rx101--which-observable-type) |
[RX.10.2 Which Flattening Op?](10_decision_maps.md#rx102--which-flattening-operator) |
[RX.10.3 Which Subject?](10_decision_maps.md#rx103--which-subject) |
[RX.10.4 Which Scheduler?](10_decision_maps.md#rx104--which-scheduler) |
[RX.10.5 Which Backpressure?](10_decision_maps.md#rx105--which-backpressure-strategy) |
[RX.10.6 Error Decision](10_decision_maps.md#rx106--error-handling-decision) |
[RX.10.7 Operator Cheat Sheet](10_decision_maps.md#rx107--one-page-operator-cheat-sheet) |
[RX.10.8 Pattern Quick Reference](10_decision_maps.md#rx108--full-pattern-quick-reference)

---

## Connection to Other Notes

| RxJava Concept | Related File |
|---|---|
| Android architecture (where RxJava fits) | [A3_architecture_patterns.md](../Questions/A3_architecture_patterns.md) |
| Coroutines/Flow alternative | `Code/Kotlin/Questions/09_structured_concurrency.md` |
| ViewModel + LiveData context | [A3_architecture_patterns.md](../Questions/A3_architecture_patterns.md) |
| Retrofit setup | [A4_offline_and_data.md](../Questions/A4_offline_and_data.md) |
| Room database | [A4_offline_and_data.md](../Questions/A4_offline_and_data.md) |

---

*All files: Kotlin only, RxJava 2/3 compatible, mobile-friendly ASCII diagrams (≤60 chars wide)*
