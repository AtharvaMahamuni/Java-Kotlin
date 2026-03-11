# Phase 03 — Operators: Transform the Stream

Operators are the verbs of RxJava. An Observable is a noun — a stream of data.
Operators describe what to DO with that stream. Every operator creates a NEW
Observable that wraps the previous one; nothing mutates in place. Understanding
operators means understanding which category a problem belongs to, then
picking the right tool. The most dangerous confusion is between the four
flattening operators: map, flatMap, concatMap, switchMap. Getting these wrong
produces subtle ordering bugs that only appear under load.

---

## RX.03.1 — Operator Categories

> **Builds on:** [02_observable_types.md] · [01_observer_pattern.md]
> **Connects to:** [04_schedulers.md] · [06_error_handling.md]

### Memory Trick
Transform = change items. Filter = drop items. Combine = merge streams.
Utility = side effects. Error = handle failures.

### Master Category Table

| Category    | Operators                                          | Purpose                        |
|-------------|---------------------------------------------------|--------------------------------|
| **Transform**| `map` `flatMap` `concatMap` `switchMap` `scan` `buffer` `window` | Change item values or cardinality |
| **Filter**  | `filter` `take` `skip` `distinct` `debounce` `throttle` `sample` | Reduce what flows downstream   |
| **Combine** | `zip` `combineLatest` `merge` `concat` `amb`      | Merge multiple streams         |
| **Utility** | `doOnNext` `doOnError` `doOnComplete` `delay` `timeout` | Side effects, timing           |
| **Error**   | `onErrorReturn` `onErrorResumeNext` `retry` `retryWhen` | Handle failures                |

---

## RX.03.2 — The Flattening Operators (Most Confused Group)

> **Connects to:** [10_decision_maps.md]

### Memory Trick
- `map`: one-to-one sync transform
- `flatMap`: one-to-many async, ORDER NOT GUARANTEED
- `concatMap`: one-to-many async, ORDERED, sequential
- `switchMap`: one-to-many async, CANCEL PREVIOUS, only latest

### map — Synchronous 1:1 Transform

```kotlin
// Transforms each item synchronously
// Returns T, not Observable<T>
Observable.just(1, 2, 3)
    .map { it * 2 }        // Int → Int (NOT Int → Observable<Int>)
    .subscribe { println(it) }
// Output: 2, 4, 6
```

```
Input:  ──1──────2──────3──|──►
         map(x2)
Output: ──2──────4──────6──|──►
```

### flatMap — Async 1:many, Order Not Guaranteed

```kotlin
// Each item spawns a new Observable; results MERGE (interleaved)
// Use for: parallel async operations where order doesn't matter
Observable.just("user1", "user2", "user3")
    .flatMap { id ->
        apiService.getUser(id)         // returns Single<User>
            .toObservable()
            .subscribeOn(Schedulers.io())
    }
    .subscribe { user -> println(user) }
// Output order is NOT guaranteed — whichever finishes first
```

```
Input:  ──a──────b──────c──|──►
         flatMap(makeRequest)

Inner streams (all start simultaneously):
  a→  ────────────────A──►   (slow)
  b→  ────────B──────►       (fast)
  c→  ──────────────────C──► (slowest)

Output: ──────B──────A──────C──|──►
        ^ ORDER NOT PRESERVED ^
```

### concatMap — Async 1:many, Sequential, Ordered

```kotlin
// Each inner Observable must COMPLETE before the next starts
// Use for: ordered operations (pagination, sequential writes)
Observable.just(1, 2, 3)
    .concatMap { page ->
        apiService.getPage(page)
            .toObservable()
    }
    .subscribe { items -> println(items) }
// Output order: page1 results, THEN page2, THEN page3 — GUARANTEED
```

```
Input:  ──1──────2──────3──|──►
         concatMap(getPage)

Inner streams (run ONE AT A TIME):
  1→  ──────────Page1──►|   (waits for complete)
  2→              ──────Page2──►|  (starts after 1 done)
  3→                      ──────Page3──►|

Output: ──────────Page1──────Page2──────Page3──|──►
        ^ ORDER PRESERVED, sequential ^
```

### switchMap — Async 1:many, Cancel Previous

```kotlin
// When a new item arrives, CANCEL the current inner Observable
// Use for: search-as-you-type, navigation events
searchInput
    .debounce(300, TimeUnit.MILLISECONDS)
    .switchMap { query ->
        apiService.search(query)    // previous search CANCELLED
            .toObservable()
    }
    .subscribe { results -> updateUI(results) }
// If user types "a" then quickly "ab", the "a" search is cancelled
```

```
Input:  ──a──────ab──────abc──|──►
         switchMap(search)

Inner streams:
  a→   ─────────search(a)────────► CANCELLED when "ab" arrives
  ab→        ──search(ab)──────────► CANCELLED when "abc" arrives
  abc→                 ──search(abc)──►|

Output:                          ──Result(abc)──|──►
        ^ ONLY LATEST WINS ^
```

### Decision Tree: Which Flattening Operator?

```
Does the transform return a single item synchronously?
├── YES → map { }
└── NO (returns Observable/Single/etc.)
    │
    Does ORDER matter?
    ├── NO → flatMap { }  (parallel, fastest overall)
    └── YES
        │
        Should previous work be CANCELLED when new item arrives?
        ├── YES → switchMap { } (search, navigation)
        └── NO  → concatMap { } (pagination, sequential writes)
```

### Comparison Table

| Operator    | Concurrency | Order       | Cancels previous? | Use case              |
|-------------|-------------|-------------|-------------------|-----------------------|
| `map`       | Sync        | Preserved   | N/A               | Simple transforms     |
| `flatMap`   | Parallel    | NOT guaranteed | No             | Parallel API calls    |
| `concatMap` | Sequential  | Preserved   | No                | Pagination, ordered   |
| `switchMap` | Latest only | Latest only | YES               | Search, type-ahead    |

---

## RX.03.3 — Filter Operators

> **Connects to:** [09_android_patterns.md]

### filter — Drop Items That Don't Match

```kotlin
Observable.just(1, 2, 3, 4, 5)
    .filter { it % 2 == 0 }
    .subscribe { println(it) }
// Output: 2, 4
```

### take / skip — Cardinality Control

```kotlin
// take: keep only first N items
Observable.range(1, 100)
    .take(3)
    .subscribe { println(it) }
// Output: 1, 2, 3 (stream completes after 3)

// skip: discard first N items
Observable.range(1, 5)
    .skip(2)
    .subscribe { println(it) }
// Output: 3, 4, 5
```

### debounce — Wait for Silence

```kotlin
// Emit only if no new item arrives within the time window
// PERFECT for search-as-you-type
searchEditText.textChanges()          // fires on every keystroke
    .debounce(300, TimeUnit.MILLISECONDS)
    .subscribe { query -> search(query) }
// Types "hello" rapidly: only fires search("hello") once
```

```
Input:  ─h─e─l─l─o──────────world─────────►
         debounce(300ms)
Output: ──────────────o─────────────world──►
                      ^ 300ms of silence ^
```

### throttleFirst — Rate Limiting

```kotlin
// Emit first item in window, ignore rest until window expires
// PERFECT for button clicks (prevent double-submit)
button.clicks()
    .throttleFirst(1000, TimeUnit.MILLISECONDS)
    .subscribe { handleClick() }
// Rapid clicks: only first one fires; rest ignored for 1 second
```

```
Input:  ─click─click─click──────click──►
         throttleFirst(1s)
Output: ─click──────────────────click──►
         ^ ignores middle clicks ^      ^ new window started
```

---

## RX.03.4 — Combine Operators

> **Connects to:** [05_subjects.md]

### zip — Pair Items 1:1

```kotlin
// Combines items at matching positions
// Waits for BOTH streams to emit before producing a pair
val names = Observable.just("Alice", "Bob")
val scores = Observable.just(95, 87)

Observable.zip(names, scores) { name, score ->
    "$name: $score"
}.subscribe { println(it) }
// Output: Alice: 95, Bob: 87
```

```
Names:  ──Alice────────Bob──|──►
Scores: ──────────95──87────|──►
         zip()
Output: ──────────Alice:95──Bob:87──|──►
        ^ waits for BOTH to emit ^
```

### combineLatest — Whenever Either Updates

```kotlin
// Emits when ANY source emits, using the latest values from all
// PERFECT for form validation (any field changes → re-validate)
Observable.combineLatest(
    emailField.textChanges(),
    passwordField.textChanges()
) { email, password ->
    email.isNotEmpty() && password.length >= 8
}.subscribe { isValid -> submitButton.isEnabled = isValid }
```

```
Email:    ──a────ab────abc──────────────────►
Password: ──────────────────pass──password──►
           combineLatest
Output:   ──────ab─────abc──────────────────►
                          ↑ any emission triggers
```

### merge vs concat — Combining Streams

```kotlin
// merge: subscribe to ALL sources simultaneously (interleaved)
val stream1 = Observable.interval(200, TimeUnit.MILLISECONDS).take(3)
val stream2 = Observable.interval(300, TimeUnit.MILLISECONDS).take(3)
Observable.merge(stream1, stream2)
    .subscribe { println(it) }
// Output is INTERLEAVED based on timing

// concat: subscribe to sources SEQUENTIALLY
Observable.concat(stream1, stream2)
    .subscribe { println(it) }
// Output: all of stream1, THEN all of stream2
```

```
merge:
  s1: ──a──a──a──|──►
  s2: ────b────b────b──|──►
out:  ──a─b─a──a──b──b──|──►  (interleaved)

concat:
  s1: ──a──a──a──|──►
  s2: (waits)      ──b──b──b──|──►
out:  ──a──a──a──────b──b──b──|──►
```

---

## RX.03.5 — Utility Operators (Side Effects)

### doOnNext / doOnError / doOnComplete

```kotlin
// Use for logging, analytics — NOT for business logic
// These do NOT transform the stream
apiService.getUser(id)
    .toObservable()
    .doOnNext { user -> Log.d("TAG", "Got user: ${user.id}") }
    .doOnError { e -> analytics.logError("user_fetch_failed", e) }
    .doOnComplete { Log.d("TAG", "Stream completed") }
    .subscribe(
        { user -> updateUI(user) },
        { error -> showError(error) }
    )
```

**Rule:** If you're modifying shared state in `doOnNext`, you're doing it wrong.
These are for READ-ONLY side effects (logging, metrics). Use `map` or `flatMap`
for transformations.

---

## RX.03.6 — Interview Traps

### Trap 1: flatMap Order Assumption

```kotlin
// WRONG assumption: flatMap preserves order
Observable.just(3, 1, 2)
    .flatMap { n ->
        Observable.just(n).delay(n.toLong(), TimeUnit.SECONDS)
    }
    .subscribe { println(it) }
// Output: 1, 2, 3  — NOT 3, 1, 2!
// The delay causes 1 to finish first, then 2, then 3

// CORRECT: Use concatMap if order matters
Observable.just(3, 1, 2)
    .concatMap { n ->
        Observable.just(n).delay(n.toLong(), TimeUnit.SECONDS)
    }
    .subscribe { println(it) }
// Output: 3, 1, 2 — order preserved
```

### Trap 2: switchMap Cancels Silently

```kotlin
// switchMap cancels the previous inner Observable
// If the inner Observable writes to DB, the write is CANCELLED
// This is a silent data loss bug

searchQuery
    .switchMap { query ->
        // WARNING: if user types quickly, this DB write may be cancelled!
        database.search(query)
            .flatMap { results ->
                database.cacheResults(results)  // may be cancelled!
            }
    }
```

### Trap 3: doOnNext for Business Logic

```kotlin
// WRONG: modifying state in doOnNext
var count = 0
observable
    .doOnNext { count++ }       // BAD — side effect in "peek" operator
    .subscribe { process(it) }

// CORRECT: use scan for stateful accumulation
observable
    .scan(0) { acc, _ -> acc + 1 }  // produces running count
    .subscribe { count -> display(count) }
```

---

## Self-Test — RX.03

1. User types "r", "rx", "rxj" in 50ms intervals, then pauses.
   With `debounce(300ms)`, how many search calls fire? With `switchMap`
   instead of `debounce`, how many calls are made and cancelled?
   What happens if you use BOTH?

2. You need to fetch 5 pages of results, in order, where each page's URL
   depends on the previous page's response. Which flattening operator do you
   use? Why would `flatMap` be wrong here?

3. `zip` waits for both sources to emit before producing output.
   `combineLatest` emits when EITHER source emits, using latest from both.
   Design a scenario where using `zip` instead of `combineLatest` causes
   a UI bug.

4. You have a stream of user actions. You want to take only the first 10.
   After the 10th action, should the stream complete? Check your mental model:
   does `take(10)` call `onComplete` or just stop calling `onNext`?

5. A colleague uses `doOnNext` to update a database. You tell them this is
   wrong. They ask: "But it works!" Explain the CONTRACT reason why `doOnNext`
   is wrong for this, even if it works in practice.

---

← [02_observable_types.md](02_observable_types.md) | [04_schedulers.md →](04_schedulers.md)
