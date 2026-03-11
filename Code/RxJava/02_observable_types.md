# Phase 02 — Observable Types: What You Subscribe To

RxJava 2+ introduced five observable types instead of one. This was not API
bloat — it was type-safety. Before RxJava 2, every stream was `Observable`,
even one that emits exactly one item. This forced callers to guess: "Will this
emit zero items? One? Infinite?" RxJava 2 encodes the cardinality at the type
level. If a method returns `Single<User>`, you KNOW it emits exactly one item
or an error — no guessing, no null checks. The type is the documentation.

---

## RX.02.1 — The Five Types

> **Builds on:** [01_observer_pattern.md]
> **Connects to:** [07_backpressure_flowable.md] · [10_decision_maps.md]

### Memory Trick
Observable = many. Single = one-or-error. Maybe = zero-or-one. Completable =
done-or-error. Flowable = many-with-backpressure.

### Type Comparison Table

| Type           | Items emitted   | Signals available          | Use case                          |
|----------------|-----------------|----------------------------|-----------------------------------|
| `Observable<T>`| 0 to infinity   | onNext / onError / onComplete | UI events, lists, general streams |
| `Single<T>`    | exactly 1 or error | onSuccess / onError       | Network call, DB lookup by ID     |
| `Maybe<T>`     | 0 or 1 or error | onSuccess / onComplete / onError | Nullable DB lookup, cache hit/miss|
| `Completable`  | 0 (no items)    | onComplete / onError       | Fire-and-forget: write, delete    |
| `Flowable<T>`  | 0 to infinity   | onNext / onError / onComplete | DB live queries, sensor streams   |

### When to Use Each

```
Do you emit items?
├── NO  → Completable (write to DB, POST with no response body)
└── YES → How many?
    ├── Exactly 1 → Single<T>   (GET user by ID, network response)
    ├── 0 or 1   → Maybe<T>     (cache lookup, nullable query)
    └── Many     → Does the source produce faster than consumer can handle?
        ├── YES → Flowable<T>   (Room live queries, file reads)
        └── NO  → Observable<T> (UI click events, in-memory lists)
```

### Code Examples

```kotlin
// Single — network call
fun getUser(id: String): Single<User> =
    apiService.getUser(id)   // Retrofit + RxJava adapter returns Single

// Maybe — cache lookup
fun getCachedUser(id: String): Maybe<User> =
    cache[id]?.let { Maybe.just(it) } ?: Maybe.empty()

// Completable — fire-and-forget write
fun saveUser(user: User): Completable =
    Completable.fromAction { database.insert(user) }

// Observable — UI events (never completes)
fun buttonClicks(): Observable<Unit> =
    button.clicks()   // RxBinding

// Flowable — Room live query (can emit rapidly)
@Query("SELECT * FROM users")
fun getAllUsers(): Flowable<List<User>>
```

---

## RX.02.2 — Cold vs Hot Observable

> **Connects to:** [05_subjects.md] · [03_operators.md]

### Memory Trick
Cold = Netflix: each subscriber gets their own private stream from the start.
Hot = live TV: you join the broadcast already in progress.

### Cold Observable

```kotlin
// Cold: the source starts fresh for EACH subscriber
val cold = Observable.create<Int> { emitter ->
    println("Source started!")   // prints for EACH subscriber
    emitter.onNext(1)
    emitter.onNext(2)
    emitter.onNext(3)
    emitter.onComplete()
}

cold.subscribe { println("Sub1: $it") }
// Output: Source started! Sub1: 1, Sub1: 2, Sub1: 3

cold.subscribe { println("Sub2: $it") }
// Output: Source started! Sub2: 1, Sub2: 2, Sub2: 3
// ^ Source restarted from scratch for Sub2
```

**Cold Observable timeline:**

```
Subscribe 1 at t=0:
  Sub1: ──1──2──3──|──►   (own private stream)

Subscribe 2 at t=5s:
  Sub2:      ──1──2──3──|──►  (own private stream, starts fresh)
```

All these are cold by default:
- `Observable.just()`
- `Observable.fromIterable()`
- `Observable.create()`
- Retrofit Single (makes a NEW network call per subscribe)
- Room Flowable (opens a NEW DB cursor per subscribe)

### Hot Observable

```kotlin
// Hot: the source runs independently; subscribers see ONLY
// emissions that occur AFTER they subscribe

val subject = PublishSubject.create<Int>()

subject.onNext(1)  // emitted BEFORE anyone subscribes — lost!

subject.subscribe { println("Sub1: $it") }
subject.onNext(2)  // Sub1 sees this

subject.subscribe { println("Sub2: $it") }
subject.onNext(3)  // BOTH Sub1 and Sub2 see this
```

**Hot Observable timeline:**

```
Source:  ──1──2──────3──────4──────►
                │         │
            Sub1 joins  Sub2 joins

Sub1:       ────2──────3──────4──►  (missed 1)
Sub2:                ──────3──4──►  (missed 1 and 2)
```

Hot observables:
- `PublishSubject` / `BehaviorSubject` / `ReplaySubject`
- `ConnectableObservable` (after `connect()`)
- `RxBinding` UI event streams (button clicks are hot)

### Converting Cold → Hot: publish() + connect()

```kotlin
// Make a cold Observable hot so all subscribers share one execution
val cold = Observable.interval(1, TimeUnit.SECONDS)

val hot: ConnectableObservable<Long> = cold.publish()

hot.subscribe { println("Sub1: $it") }
hot.subscribe { println("Sub2: $it") }

hot.connect()  // NOW the source starts; both subscribers share it
// Both Sub1 and Sub2 receive the same emissions
```

---

## RX.02.3 — Lazy Creation: Nothing Happens Until subscribe()

> **Connects to:** [08_disposables_lifecycle.md]

### Memory Trick
`Observable.create { }` is just a recipe. subscribe() bakes the cake.

```kotlin
val expensiveObservable = Observable.create<User> { emitter ->
    // This block does NOT run here!
    val user = database.fetchUser()  // NOT called yet
    emitter.onNext(user)
    emitter.onComplete()
}

// STILL nothing has run. The lambda is stored, not executed.
println("Before subscribe")

expensiveObservable.subscribe { user ->
    println("Got: $user")
}
// NOW the lambda runs. "fetchUser()" is called NOW.
```

**Why this matters:**
- You can construct complex chains without any I/O happening
- Each `subscribe()` call triggers a fresh execution (cold)
- You can share the "recipe" (the Observable reference) safely across
  the codebase; subscribing is the trigger, not construction

---

## RX.02.4 — Interview Traps

### Trap 1: Cold vs Hot Confusion with Retrofit

```kotlin
// WRONG assumption:
val userCall = apiService.getUser(id)  // Single<User>
// "I cached this Single, so it won't make a second network call"

userCall.subscribe { /* call 1 */ }
userCall.subscribe { /* call 2 — makes ANOTHER network call! Cold! */ }

// CORRECT: if you want to share one network call result:
val sharedUser = apiService.getUser(id).cache()  // replays to all subscribers
```

### Trap 2: Subject Misuse (Wrong Type)

```kotlin
// WRONG: Using PublishSubject when you need BehaviorSubject for late subscribers
class ViewModel {
    val state = PublishSubject.create<UiState>()

    fun loadData() {
        state.onNext(UiState.Loading)  // emitted once
        // If Activity rotates and re-subscribes AFTER this emission,
        // it sees NOTHING — PublishSubject doesn't replay
    }
}

// CORRECT: BehaviorSubject replays the last value to new subscribers
class ViewModel {
    val state = BehaviorSubject.createDefault<UiState>(UiState.Idle)
    // New subscribers immediately get the current state
}
```

### Trap 3: Observable vs Flowable for Room

```kotlin
// WRONG: Room returns Flowable for live queries, but you used Observable
@Query("SELECT * FROM users")
fun getAllUsers(): Observable<List<User>>  // compiles but loses backpressure

// CORRECT: Use Flowable for Room to handle rapid DB updates
@Query("SELECT * FROM users")
fun getAllUsers(): Flowable<List<User>>  // Room handles backpressure correctly
```

### Trap 4: Single doesn't emit "empty"

```kotlin
// WRONG: Using Single when the result might not exist
fun findUser(id: String): Single<User> =
    Single.create { emitter ->
        val user = db.find(id)
        emitter.onSuccess(user)  // user could be null! NullPointerException!
    }

// CORRECT: Use Maybe for nullable results
fun findUser(id: String): Maybe<User> =
    Maybe.create { emitter ->
        val user = db.find(id)
        if (user != null) emitter.onSuccess(user)
        else emitter.onComplete()  // empty — no item, no error
    }
```

---

## Self-Test — RX.02

1. You're writing a method that deletes a user from the DB. It doesn't need to
   return the deleted user. Which type do you use and why? What if you DO need
   to confirm the number of rows deleted?

2. A cold `Observable.create { }` makes a network call. Two subscribers
   subscribe 500ms apart. How many network calls are made? How would you change
   the code to make only ONE network call?

3. Explain the difference between a `PublishSubject` and a `BehaviorSubject`
   using the "live TV" metaphor. Which one should a ViewModel expose to its
   View, and why?

4. `Maybe` has three terminal signals: `onSuccess`, `onComplete`, and `onError`.
   In what real-world scenario would `onComplete` fire instead of `onSuccess`?
   Give a concrete Android example.

5. Why does the lazy execution model (nothing runs until subscribe) make
   testing easier? How would eager execution (runs on construction) complicate
   unit tests?

---

← [01_observer_pattern.md](01_observer_pattern.md) | [03_operators.md →](03_operators.md)
