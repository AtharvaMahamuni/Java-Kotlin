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
