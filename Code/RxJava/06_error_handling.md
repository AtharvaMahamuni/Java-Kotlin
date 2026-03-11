# Phase 06 — Error Handling: The Error Contract

The most important rule in RxJava: `onError` terminates the stream. Period.
After an error, the Observable is dead. This is a feature, not a bug — it
forces you to decide explicitly what to do with errors rather than letting
them silently corrupt state. The question is: do you handle the error and
produce a fallback value, resume with a different stream, or retry the
operation? Each answer has a specific operator. Getting this wrong means
either swallowing errors (bugs become invisible) or crashing the app.

---

## RX.06.1 — The Core Rule: onError Is Terminal

> **Builds on:** [01_observer_pattern.md] · [03_operators.md]
> **Connects to:** [08_disposables_lifecycle.md] · [09_android_patterns.md]

### Memory Trick
onError kills the stream. You must intercept it BEFORE it reaches the
subscriber, or handle it AT the subscriber. There is no "continue after error."

### What Happens Without Error Handling

```kotlin
// RxJava 2: unhandled onError = uncaught exception = crash
Observable.just(1, 2, 3)
    .map { if (it == 2) throw RuntimeException("boom") else it }
    .subscribe { println(it) }
    // Output: 1, then CRASH — OnErrorNotImplementedException

// RxJava 3: routes to RxJavaPlugins.setErrorHandler (no crash by default)
// But still: stream terminates at the error, 3 is never processed
```

### The Error Flow Through the Chain

```
Source: ──1──────2──────3──|──►
         map { if 2 throw }
         ──1──X (error at item 2)
              │
              ▼ error propagates DOWNSTREAM
         ──────X──►
                │
                ▼ reaches subscriber's onError
         onError { handle it }
```

Once the error propagates, the stream is DEAD. Item 3 is never emitted.

---

## RX.06.2 — onErrorReturn: Fallback Value

> **Connects to:** [10_decision_maps.md]

### Memory Trick
onErrorReturn = "if something breaks, return this default value and complete."
Stream ends normally after the fallback.

```kotlin
// Replace error with a default value, then complete normally
apiService.getUser(id)
    .toObservable()
    .onErrorReturn { error ->
        // Return a default User object instead of propagating error
        User.empty()
    }
    .subscribe { user ->
        // Always called — either real user or User.empty()
        displayUser(user)
    }
```

```
Without error handling:
  ──User──X──►  (error, stream dead)

With onErrorReturn(User.empty()):
  ──User──X                         (source threw)
           └──► User.empty()──|──►  (fallback emitted, then complete)
```

**When to use:** Non-critical data where a default is acceptable.
Never for errors that indicate data corruption or auth failure.

---

## RX.06.3 — onErrorResumeNext: Fallback Stream

### Memory Trick
onErrorResumeNext = "if something breaks, switch to this other Observable."
The new stream continues where the error left off.

```kotlin
// Switch to a fallback Observable on error
apiService.getUser(id)
    .toObservable()
    .onErrorResumeNext { error: Throwable ->
        when (error) {
            is HttpException -> when (error.code()) {
                404 -> Observable.just(User.notFound())
                401 -> Observable.error(AuthException("unauthorized"))
                else -> localDatabase.getUser(id)  // fallback to cache
            }
            is NetworkException -> localDatabase.getUser(id)
            else -> Observable.error(error)  // re-propagate unknown errors
        }
    }
    .subscribe(
        { user -> displayUser(user) },
        { error -> showError(error) }  // only auth errors reach here
    )
```

**onErrorReturn vs onErrorResumeNext:**

| Operator                 | Returns        | Stream behavior after error      |
|--------------------------|----------------|----------------------------------|
| `onErrorReturn`          | Single item T  | Emits fallback T, then completes |
| `onErrorResumeNext`      | Observable<T>  | Switches to fallback Observable  |

---

## RX.06.4 — retry and retryWhen

### retry — Simple Retry

```kotlin
// Retry immediately on error, up to N times
apiService.getUser(id)
    .toObservable()
    .retry(3)   // retry up to 3 times on any error
    .subscribe(
        { user -> displayUser(user) },
        { error -> showError(error) }  // called if all 3 retries fail
    )
```

```
With retry(3):
  Attempt 1: ──X  (error)
  Attempt 2: ──X  (error)
  Attempt 3: ──X  (error)
  Attempt 4: ──User──|──►  (success on 4th try)
  OR
  Attempt 4: ──X  →  onError reaches subscriber
```

**Warning:** `retry()` with no argument retries INFINITELY. Never use this
without a count or condition — it can loop forever.

### retryWhen — Exponential Backoff

```kotlin
// Retry with exponential backoff — the production pattern
apiService.getUser(id)
    .toObservable()
    .retryWhen { errors ->
        errors
            .zipWith(Observable.range(1, 3)) { error, retryCount ->
                Pair(error, retryCount)
            }
            .flatMap { (error, retryCount) ->
                if (error is NetworkException) {
                    val delaySeconds = 2L.pow(retryCount)  // 2, 4, 8 seconds
                    Observable.timer(delaySeconds, TimeUnit.SECONDS)
                } else {
                    // Non-retryable error — propagate immediately
                    Observable.error(error)
                }
            }
    }
    .subscribe(
        { user -> displayUser(user) },
        { error -> showError("Failed after retries: $error") }
    )
```

```
retryWhen with exponential backoff:

Attempt 1: ──X
             └── wait 2s ──►
Attempt 2:               ──X
                           └── wait 4s ──►
Attempt 3:                             ──X
                                         └── wait 8s ──►
Attempt 4:                                           ──User──|
OR (after 3 retries exhausted):
                                          onError reaches subscriber
```

### retry with Predicate — Smart Retry

```kotlin
// Only retry for specific error types
apiService.getUser(id)
    .toObservable()
    .retry { retryCount, error ->
        retryCount < 3 && error is NetworkException
        // Returns true = retry; false = propagate error
    }
    .subscribe(
        { user -> displayUser(user) },
        { error -> showError(error) }
    )
```

---

## RX.06.5 — Error Handling Decision Tree

```
Error occurred in stream. What do you do?

Can you provide a default value?
├── YES → onErrorReturn { defaultValue }
└── NO
    │
    Can you switch to a fallback stream (e.g., cache)?
    ├── YES → onErrorResumeNext { fallbackObservable }
    └── NO
        │
        Is the error transient (network timeout, 503)?
        ├── YES → retry(n) or retryWhen with backoff
        └── NO (auth error, 404, data corruption)
            │
            Propagate to subscriber's onError { }
            (Log it, show error UI, don't swallow)
```

---

## RX.06.6 — Interview Traps

### Trap 1: Swallowing Errors with onErrorReturn

```kotlin
// WRONG: swallows ALL errors, including critical ones
observable
    .onErrorReturn { User.empty() }  // 401 Unauthorized becomes empty user!

// CORRECT: only handle specific, expected errors
observable
    .onErrorResumeNext { error ->
        when (error) {
            is NetworkException -> Observable.just(User.empty())  // OK to default
            else -> Observable.error(error)  // propagate unexpected errors
        }
    }
```

### Trap 2: onError Not Implemented

```kotlin
// WRONG — RxJava 2 crashes on unhandled onError
observable
    .subscribe { user -> displayUser(user) }
    // If network fails: OnErrorNotImplementedException → crash!

// CORRECT — always provide onError handler
observable
    .subscribe(
        { user -> displayUser(user) },
        { error -> showError(error) }
    )
```

### Trap 3: Retrying Non-Idempotent Operations

```kotlin
// WRONG: retrying a POST request that creates a resource
apiService.createOrder(order)
    .retry(3)  // Could create 3 duplicate orders!

// CORRECT: only retry idempotent operations (GET, PUT with same data)
// For POST: retry only if you KNOW it failed before server processed it
apiService.createOrder(order)
    .retry { count, error ->
        count < 3 && error is ConnectException  // connection failed — server never saw it
    }
```

### Trap 4: Error After onErrorReturn Doesn't Retry

```kotlin
// onErrorReturn terminates the stream with a value
// You CANNOT retry after onErrorReturn
// If you want retry + fallback, retry MUST come first

observable
    .retry(3)                    // retry first
    .onErrorReturn { default }   // fallback only if all retries fail
    // NOT the other way around!
```

---

## Self-Test — RX.06

1. A stream emits items 1, 2, then throws an error, then would emit 3.
   With `onErrorReturn(99)`, what does the subscriber see?
   Does item 3 ever get emitted? Trace the signal sequence.

2. You want to retry a network call up to 3 times with a 2-second delay
   between each retry, but ONLY for `SocketTimeoutException`. For all other
   errors, propagate immediately. Write the `retryWhen` chain.

3. `onErrorReturn` vs `onErrorResumeNext`: when would you use a fallback
   Observable instead of a fallback value? Name two concrete Android scenarios.

4. A colleague says "I'll just wrap everything in `retry(100)` to handle
   flaky networks." What are two problems with this approach?

5. Where in the operator chain should you place error-handling operators
   relative to `subscribeOn` and `observeOn`? Does placement matter?
   Design a chain with network call → retry → fallback → UI update, with
   correct threading.

---

← [05_subjects.md](05_subjects.md) | [07_backpressure_flowable.md →](07_backpressure_flowable.md)
