# Phase 01 — The Observer Pattern: RxJava's Foundation

RxJava is not magic. It is the Observer Pattern — one of the oldest design
patterns — taken seriously, standardized, and extended with functional
operators. If you understand the classic Observer Pattern, you understand what
RxJava is doing under the hood. If you understand the three-signal contract
(onNext / onError / onComplete), you understand what every RxJava chain
guarantees. Everything else in RxJava is built on this contract.

---

## RX.01.1 — Classic Observer Pattern

> **Builds on:** [00_why_rxjava.md]
> **Connects to:** [02_observable_types.md] · [05_subjects.md]

### Memory Trick
Subject holds a list of Observers. When state changes, it notifies all of them.
RxJava formalizes this with a strict signal contract.

### Classic Structure

```
┌──────────────────────┐      notifyAll()
│  Subject / EventBus  │──────────────────►  Observer 1
│  (holds subscriber   │                  ►  Observer 2
│   list internally)   │                  ►  Observer 3
└──────────────────────┘
         ▲
   setState(newValue)
   (called by producer)
```

```kotlin
// Classic pattern — manual implementation
interface Observer {
    fun update(data: Any)
}

class EventBus {
    private val observers = mutableListOf<Observer>()
    fun subscribe(o: Observer) = observers.add(o)
    fun notify(data: Any) = observers.forEach { it.update(data) }
}
```

**Problem with classic Observer:**
- No standard for "I'm done emitting" (completion)
- No standard for "something went wrong" (error)
- No standard for cancellation
- Thread safety is the caller's problem

RxJava solves all four.

---

## RX.01.2 — RxJava's Observable → Observer Contract

> **Connects to:** [03_operators.md] · [06_error_handling.md]

### Memory Trick
Observable emits items. Observer receives them via exactly three methods.
The contract is: onNext* (onError | onComplete)?

### The Contract in Code

```kotlin
// What an Observer looks like
interface Observer<T> {
    fun onSubscribe(d: Disposable)    // called first, always
    fun onNext(item: T)               // called 0..N times
    fun onError(e: Throwable)         // called at most once
    fun onComplete()                  // called at most once
}

// How you subscribe
val observable: Observable<String> = Observable.just("a", "b", "c")

observable.subscribe(object : Observer<String> {
    override fun onSubscribe(d: Disposable) {
        // Save d to cancel later
    }
    override fun onNext(item: String) {
        println("Got: $item")
    }
    override fun onError(e: Throwable) {
        println("Error: ${e.message}")
    }
    override fun onComplete() {
        println("Done")
    }
})
```

### The Signal Timeline Diagram

```
Time axis: ──────────────────────────────►

Happy path:
  ──onNext(a)──onNext(b)──onNext(c)──onComplete──►
                                              │
                              stream ends here, no more signals

Error path:
  ──onNext(a)──onNext(b)──onError(e)──────────►
                               │
                stream ends here, onComplete never fires

Empty path:
  ──onComplete────────────────────────────────►
  (zero items, immediate completion)

Infinite stream (UI events, sensors):
  ──onNext──onNext──onNext──onNext──────────► (no complete)
```

### The Formal Contract Rules

| Rule | Implication |
|------|-------------|
| `onNext` can fire 0 to N times | Observable may emit nothing |
| `onError` OR `onComplete`, never both | Terminal signals are mutually exclusive |
| After a terminal signal, nothing more fires | `onNext` after `onComplete` = illegal |
| `onSubscribe` always fires first | Use it to store the `Disposable` |
| Signals are sequential (not concurrent) | No two calls overlap in time |

---

## RX.01.3 — The Three Signals in Depth

> **Connects to:** [06_error_handling.md] · [08_disposables_lifecycle.md]

### onNext — The Data Signal

```kotlin
// Fires for each item. Can be called many times.
// Never fires after onError or onComplete.
observable
    .subscribe { item ->   // shorthand for onNext only
        processItem(item)
    }
```

**What you must know:**
- Operators between source and subscriber transform the onNext stream
- `map { }` transforms each onNext value
- `filter { }` can drop onNext calls entirely

### onError — The Error Signal

```kotlin
// Fires at most once. Terminates the stream.
// No more onNext or onComplete after this.
observable.subscribe(
    { item -> processItem(item) },   // onNext
    { error -> handleError(error) }  // onError — required in prod!
)
```

**What you must know:**
- If you don't provide an `onError` handler, RxJava throws the error
  as an uncaught exception (crashes in RxJava 2; routed to global handler in RxJava 3)
- Errors propagate downstream through the operator chain
- Operators like `onErrorReturn` can intercept and convert errors

### onComplete — The Completion Signal

```kotlin
// Fires at most once. Terminates the stream normally.
Observable.just("a", "b")
    .subscribe(
        { item -> println(item) },
        { error -> println("error") },
        { println("Done!") }  // onComplete lambda
    )
// Output: a, b, Done!
```

**What you must know:**
- Not all Observables ever complete (UI events, live DB queries)
- `Single` and `Completable` encode "exactly one" and "zero items" at the type level

---

## RX.01.4 — Interview Traps

### Trap 1: What happens after onError?

```kotlin
// WRONG mental model:
// "After onError, the stream continues with onNext"

// CORRECT:
// onError is TERMINAL. The stream is dead.
// Any subsequent emissions from the source are IGNORED.

val subject = PublishSubject.create<Int>()
subject.subscribe(
    { println("onNext: $it") },
    { println("onError: ${it.message}") },
    { println("onComplete") }
)

subject.onNext(1)        // prints: onNext: 1
subject.onError(RuntimeException("boom"))  // prints: onError: boom
subject.onNext(2)        // NOTHING — stream is terminated
subject.onComplete()     // NOTHING — stream is terminated
```

### Trap 2: Can onNext fire after onComplete?

```kotlin
// The contract says NO. But what actually happens?
// RxJava wraps your Observer in a SafeObserver which enforces the contract.
// It silently discards onNext calls that arrive after onComplete.
// This is a GUARANTEE you can rely on.

val subject = PublishSubject.create<Int>()
subject.subscribe { println("onNext: $it") }

subject.onComplete()
subject.onNext(1)   // SafeObserver discards this — nothing printed
```

### Trap 3: Who calls onSubscribe?

```kotlin
// onSubscribe is called SYNCHRONOUSLY during subscribe()
// BEFORE any onNext calls
// Use it to store the Disposable for cancellation

var myDisposable: Disposable? = null

observable.subscribe(object : Observer<String> {
    override fun onSubscribe(d: Disposable) {
        myDisposable = d   // safe — called before any onNext
    }
    override fun onNext(item: String) { /* ... */ }
    override fun onError(e: Throwable) { /* ... */ }
    override fun onComplete() { /* ... */ }
})
```

### Trap 4: Missing onError handler = crash

```kotlin
// WRONG — in RxJava 2, this crashes the app on error:
observable.subscribe { item -> processItem(item) }

// CORRECT — always handle errors:
observable.subscribe(
    { item -> processItem(item) },
    { error -> Log.e("TAG", "Error", error) }
)

// OR use the safe subscribe operator:
observable
    .doOnError { error -> Log.e("TAG", "Error", error) }
    .onErrorComplete()   // convert error to completion for non-critical streams
    .subscribe { item -> processItem(item) }
```

---

## Self-Test — RX.01

1. The contract says `onError` and `onComplete` are mutually exclusive.
   What breaks in a system where both could fire? Design the rule yourself
   before looking it up.

2. An Observable emits 1000 items, then calls `onError`. Your `onNext`
   handler processed all 1000. Your `onError` handler runs. Is the stream
   still alive? Can you re-subscribe? What would re-subscribing do for a
   cold Observable?

3. `SafeObserver` wraps your Observer and enforces the contract. What is the
   performance implication of this wrapping? When would you want to bypass it
   (hint: `unsafeSubscribe` exists in RxJava 2)?

4. A colleague wraps an `EventBus` (classic Observer) in an Observable. They
   say "when the bus fires, I call `onNext`; when the app closes, I call
   `onComplete`." What contract violation is likely to happen, and why?

5. Explain why `onSubscribe` must be called synchronously (before `onNext`).
   What would go wrong if it were called asynchronously on the IO thread?

---

← [00_why_rxjava.md](00_why_rxjava.md) | [02_observable_types.md →](02_observable_types.md)
