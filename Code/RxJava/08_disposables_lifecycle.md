# Phase 08 — Disposables and Lifecycle: Memory Leaks

The most common RxJava bug in Android is forgetting to dispose. When you
subscribe to an Observable, a thread is potentially running, holding a
reference to your subscriber. If your subscriber is a Fragment or Activity
(or a closure that captures one), it cannot be garbage collected — even after
`onDestroy`. The stream keeps it alive. Fix: `Disposable` is the cancel handle.
`CompositeDisposable` is how you batch-cancel everything in `onCleared()`.

---

## RX.08.1 — The Disposable Contract

> **Builds on:** [01_observer_pattern.md] · [04_schedulers.md]
> **Connects to:** [09_android_patterns.md]

### Memory Trick
subscribe() returns a Disposable. Call dispose() to cancel.
Never subscribe without saving the Disposable (except truly fire-and-forget).

### How subscribe() Returns a Disposable

```kotlin
// The Observer is given a Disposable in onSubscribe
// You can also save the return value of subscribe()

val disposable: Disposable = observable
    .subscribeOn(Schedulers.io())
    .observeOn(AndroidSchedulers.mainThread())
    .subscribe(
        { item -> process(item) },
        { error -> handleError(error) }
    )

// Later, when you want to cancel:
disposable.dispose()
// The stream is cancelled:
// - Upstream computation stops (if subscribeOn was used)
// - No more onNext/onError/onComplete reaches your subscriber
```

### What dispose() Actually Does

```
Before dispose():
  [IO thread] ──network call──► result ──► [Main thread] onNext { }

After dispose():
  [IO thread] ──network call──► result ──► DROPPED (isDisposed = true)
                                           ^ your onNext is never called
```

**Important:** `dispose()` does NOT cancel the upstream IO work immediately
if it's already in-flight (e.g., HTTP request already sent). It cancels the
DELIVERY of results to your subscriber. The underlying OkHttp call may still
complete, but its result is discarded. For proper cancellation of HTTP, use
`Completable.fromCallable` with `Call.cancel()` in the `setCancellable` block.

---

## RX.08.2 — CompositeDisposable: The ViewModel Pattern

> **Connects to:** [09_android_patterns.md]

### Memory Trick
CompositeDisposable is a bag of Disposables. add() registers; clear() or
dispose() cancels all of them at once. Use in ViewModel.onCleared().

### The Standard Pattern

```kotlin
class UserViewModel(
    private val repository: UserRepository
) : ViewModel() {

    private val compositeDisposable = CompositeDisposable()

    val users = MutableLiveData<List<User>>()
    val error = MutableLiveData<String>()

    fun loadUsers() {
        val disposable = repository.getUsers()
            .subscribeOn(Schedulers.io())
            .observeOn(AndroidSchedulers.mainThread())
            .subscribe(
                { userList -> users.value = userList },
                { e -> error.value = e.message }
            )

        compositeDisposable.add(disposable)  // track it
    }

    fun searchUsers(query: String) {
        val disposable = repository.searchUsers(query)
            .debounce(300, TimeUnit.MILLISECONDS)
            .subscribeOn(Schedulers.io())
            .observeOn(AndroidSchedulers.mainThread())
            .subscribe(
                { results -> users.value = results },
                { e -> error.value = e.message }
            )

        compositeDisposable.add(disposable)  // track it too
    }

    override fun onCleared() {
        super.onCleared()
        compositeDisposable.clear()  // cancel ALL at once
        // Use clear() not dispose():
        // clear() lets you add more later; dispose() shuts the bag permanently
    }
}
```

### clear() vs dispose()

```kotlin
// clear() removes all Disposables and cancels them
// The CompositeDisposable can still accept new ones afterwards
compositeDisposable.clear()   // use in onCleared()

// dispose() cancels all AND marks the bag as disposed
// Any future add() calls will immediately dispose the new Disposable
compositeDisposable.dispose()  // use when ViewModel is truly done forever
// After dispose(): compositeDisposable.add(newDisposable) → immediately disposed
```

---

## RX.08.3 — Memory Leak Anatomy

### The Leak: Stream Outlives ViewModel

```
ViewModel created → loadUsers() called
  │
  ├── network call in progress on IO thread
  │   holding reference to: ViewModel → LiveData → Activity (via observer)
  │
  ▼
ViewModel.onCleared() NOT called (process death, recreation?)
  │
  ▼
Network call completes → onNext fires → updates LiveData
  → Activity reference held → Activity not GC'd
  → MEMORY LEAK
```

### Without CompositeDisposable

```kotlin
// WRONG: subscribing without tracking
class UserViewModel : ViewModel() {
    fun loadUsers() {
        // Disposable is created but NOT saved
        repository.getUsers()
            .subscribeOn(Schedulers.io())
            .subscribe { users ->
                // This lambda captures `this` (ViewModel)
                // If ViewModel is cleared but stream is still running:
                // The stream holds a reference to ViewModel
                // ViewModel can't be GC'd
                _users.value = users
            }
        // ^ leaks: no way to cancel this subscription
    }
}
```

### The Leak in Activity (NEVER DO THIS)

```kotlin
// EXTREMELY WRONG: subscribing in Activity to a long-running stream
class UserActivity : AppCompatActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        repository.getLiveUsers()  // infinite Flowable — never completes
            .subscribeOn(Schedulers.io())
            .observeOn(AndroidSchedulers.mainThread())
            .subscribe { users -> adapter.submitList(users) }
        // NO dispose() anywhere!
        // Stream holds reference to `this` Activity
        // Activity rotates → new Activity created
        // Old Activity held by stream → LEAK
        // New subscription created → now 2 streams update the same adapter
    }
}
```

### The Fix

```kotlin
// CORRECT: ViewModel owns the subscription
class UserViewModel : ViewModel() {
    private val disposables = CompositeDisposable()

    fun observeUsers() {
        disposables += repository.getLiveUsers()  // += calls add()
            .subscribeOn(Schedulers.io())
            .observeOn(AndroidSchedulers.mainThread())
            .subscribe(
                { users -> _users.value = users },
                { e -> _error.value = e.message }
            )
    }

    override fun onCleared() {
        disposables.clear()  // stream cancelled when ViewModel dies
    }
}

// Activity just observes LiveData — not the RxJava stream directly
class UserActivity : AppCompatActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        viewModel.users.observe(this) { users ->
            adapter.submitList(users)  // no RxJava here
        }
        viewModel.observeUsers()
    }
}
```

---

## RX.08.4 — RxLifecycle vs Manual Dispose

### Manual dispose (Recommended for new code)

```kotlin
// Clear the best approach: ViewModel owns streams, clears in onCleared()
// Explicit, easy to reason about, no library dependency
```

### RxLifecycle (Legacy)

```kotlin
// RxLifecycle from Trello: auto-dispose when lifecycle event occurs
// Requires Activity/Fragment to implement LifecycleProvider

observable
    .compose(RxLifecycle.bindUntilEvent(lifecycle, ActivityEvent.DESTROY))
    .subscribe { /* auto-disposed on onDestroy */ }

// Also: AutoDispose library (Uber) — more modern
observable
    .autoDispose(this)  // 'this' is LifecycleOwner
    .subscribe { /* auto-disposed based on lifecycle */ }
```

**Recommendation:** Use manual `CompositeDisposable` in ViewModel with
`onCleared()`. Avoid subscribing in Activity/Fragment directly for long-lived
streams; always delegate to ViewModel.

---

## RX.08.5 — isDisposed Check in Callbacks

```kotlin
// When bridging callback APIs, always check isDisposed
// before emitting to prevent work after cancellation
Observable.create<Location> { emitter ->
    val callback = LocationCallback { location ->
        if (!emitter.isDisposed) {   // IMPORTANT: check before emitting
            emitter.onNext(location)
        }
    }

    locationManager.requestUpdates(callback)

    // CRITICAL: set a cancellable to clean up when disposed
    emitter.setCancellable {
        locationManager.removeUpdates(callback)
    }
}
```

---

## RX.08.6 — Interview Traps

### Trap 1: Not Disposing Long-Running Streams

```kotlin
// WRONG: subscribing to infinite stream without dispose
fun onCreate() {
    userStatusStream   // WebSocket stream — never completes
        .subscribe { status -> updateStatus(status) }
    // When onDestroy fires, stream keeps running, holds Activity reference
}

// CORRECT:
private val disposables = CompositeDisposable()

fun onCreate() {
    disposables += userStatusStream
        .subscribe { status -> updateStatus(status) }
}

fun onDestroy() {
    disposables.clear()
}
// Better: move to ViewModel; Activity only observes LiveData
```

### Trap 2: Using dispose() Instead of clear() in onCleared()

```kotlin
// WRONG: Using dispose() if you might loadData() again
override fun onCleared() {
    compositeDisposable.dispose()  // permanently disabled!
    // If loadData() is called after this (edge case),
    // the new disposable is immediately disposed — silent bug
}

// CORRECT: Use clear() for normal cleanup
override fun onCleared() {
    compositeDisposable.clear()  // cancels current, allows future adds
}
```

### Trap 3: Subscribing Multiple Times Without Clearing

```kotlin
// WRONG: calling loadData() without clearing previous subscription
fun loadData() {
    compositeDisposable.add(
        repository.getData().subscribe { /* ... */ }
    )
    // Called 3 times? Now 3 subscriptions are running!
    // All 3 will update LiveData when they complete

// CORRECT: clear previous before adding new
fun loadData() {
    compositeDisposable.clear()  // cancel previous
    compositeDisposable.add(
        repository.getData().subscribe { /* ... */ }
    )
}
```

---

## Self-Test — RX.08

1. A `Flowable<List<Message>>` from Room runs on `Schedulers.io()` and
   delivers to Main. The ViewModel is cleared but `compositeDisposable.clear()`
   is NOT called. Trace the memory leak: what objects are kept alive? What
   specific crash (if any) would you see?

2. `dispose()` vs `clear()` on `CompositeDisposable`: you call `clear()` in
   `onCleared()`. After `clear()`, you call `compositeDisposable.add(newDisp)`.
   What happens to `newDisp`? Now answer for `dispose()`.

3. You have `Observable.create { emitter -> ... }` that wraps a Bluetooth
   scan callback. The Observable is disposed. The Bluetooth SDK still calls
   your callback. What happens if you call `emitter.onNext()` after disposal?
   What should you do instead?

4. A stream is subscribed in `Activity.onResume()` and disposed in
   `onPause()`. The Activity rotates. Walk through the Activity lifecycle
   events that fire: when does `onPause` fire? When does the new Activity
   `onResume` fire? Is there a gap where no subscription exists?

5. `add()` on a disposed `CompositeDisposable` immediately disposes the
   added `Disposable`. Design a scenario where this causes a silent bug
   that's hard to detect.

---

← [07_backpressure_flowable.md](07_backpressure_flowable.md) | [09_android_patterns.md →](09_android_patterns.md)
