# Phase 09 — Android Patterns: Daily Work

Theory is only valuable when it maps to the code you write every day. This
file connects all previous concepts to the four most common Android RxJava
patterns: Retrofit for network calls, Room for local data, search-as-you-type
for user input, and ViewModel + CompositeDisposable for lifecycle. Each
pattern shows the complete, production-ready code. The final section gives
you an honest migration decision table for RxJava vs Flow.

---

## RX.09.1 — Retrofit + RxJava: Single<Response> Pattern

> **Builds on:** [02_observable_types.md] · [04_schedulers.md] · [06_error_handling.md]
> **Connects to:** [10_decision_maps.md]

### Memory Trick
Retrofit + RxJava = Single<T> per call. subscribeOn(IO), observeOn(Main).
One error handler for network errors, HTTP errors, and parsing errors.

### Setup

```kotlin
// build.gradle (already have RxJava — no boilerplate shown)
// Retrofit adapter:
val retrofit = Retrofit.Builder()
    .addCallAdapterFactory(RxJava3CallAdapterFactory.create())
    .addConverterFactory(GsonConverterFactory.create())
    .baseUrl(BASE_URL)
    .build()
```

### API Interface

```kotlin
interface UserApi {
    @GET("users/{id}")
    fun getUser(@Path("id") id: String): Single<User>

    @GET("users")
    fun getUsers(): Single<List<User>>

    @POST("users")
    fun createUser(@Body user: User): Completable

    @PUT("users/{id}")
    fun updateUser(@Path("id") id: String, @Body user: User): Single<User>
}
```

### ViewModel: Single Network Call

```kotlin
class UserViewModel(
    private val api: UserApi
) : ViewModel() {

    private val disposables = CompositeDisposable()
    val user = MutableLiveData<User>()
    val loading = MutableLiveData<Boolean>()
    val error = MutableLiveData<String>()

    fun loadUser(id: String) {
        disposables += api.getUser(id)
            .subscribeOn(Schedulers.io())
            .observeOn(AndroidSchedulers.mainThread())
            .doOnSubscribe { loading.value = true }
            .doFinally { loading.value = false }   // fires on complete OR error
            .onErrorResumeNext { e ->
                when (e) {
                    is HttpException -> when (e.code()) {
                        404 -> Single.just(User.notFound())
                        401 -> Single.error(AuthException())
                        else -> Single.error(e)
                    }
                    else -> Single.error(e)
                }
            }
            .subscribe(
                { u -> user.value = u },
                { e -> error.value = e.message }
            )
    }

    override fun onCleared() = disposables.clear()
}
```

### Combining Two Calls with zip

```kotlin
// Load user and their posts simultaneously, combine when both complete
fun loadUserWithPosts(userId: String) {
    disposables += Single.zip(
        api.getUser(userId).subscribeOn(Schedulers.io()),
        api.getUserPosts(userId).subscribeOn(Schedulers.io())
    ) { user, posts ->
        UserWithPosts(user, posts)
    }
    .observeOn(AndroidSchedulers.mainThread())
    .subscribe(
        { data -> userWithPosts.value = data },
        { e -> error.value = e.message }
    )
}
```

---

## RX.09.2 — Room + RxJava: Flowable<List<T>> Live Queries

> **Builds on:** [07_backpressure_flowable.md] · [08_disposables_lifecycle.md]

### Memory Trick
Room live query = Flowable. Auto-updates when DB changes. Subscribe in
ViewModel, expose via LiveData. Dispose in onCleared().

### Room DAO

```kotlin
@Dao
interface MessageDao {
    // Live query — use Flowable
    @Query("SELECT * FROM messages ORDER BY timestamp DESC")
    fun getMessages(): Flowable<List<Message>>

    // One-time read — use Single
    @Query("SELECT * FROM messages WHERE id = :id")
    fun getMessage(id: String): Single<Message>

    // Write — use Completable
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    fun insertMessage(message: Message): Completable

    // Nullable result — use Maybe
    @Query("SELECT * FROM messages WHERE id = :id LIMIT 1")
    fun findMessage(id: String): Maybe<Message>
}
```

### ViewModel with Room Live Query

```kotlin
class MessageViewModel(
    private val dao: MessageDao
) : ViewModel() {

    private val disposables = CompositeDisposable()
    val messages = MutableLiveData<List<Message>>()

    init {
        observeMessages()
    }

    private fun observeMessages() {
        disposables += dao.getMessages()
            .subscribeOn(Schedulers.io())
            .observeOn(AndroidSchedulers.mainThread())
            .subscribe(
                { msgs -> messages.value = msgs },
                { e -> Log.e("VM", "DB error", e) }
            )
        // This stream stays alive — any DB insert/update/delete
        // triggers a new emission automatically
    }

    fun sendMessage(text: String) {
        val message = Message(text = text, timestamp = System.currentTimeMillis())
        disposables += dao.insertMessage(message)
            .subscribeOn(Schedulers.io())
            .observeOn(AndroidSchedulers.mainThread())
            .subscribe(
                { /* success — live query will auto-update messages */ },
                { e -> Log.e("VM", "Insert failed", e) }
            )
    }

    override fun onCleared() = disposables.clear()
}
```

---

## RX.09.3 — Search with debounce + switchMap

> **Builds on:** [03_operators.md] · [04_schedulers.md]

### Memory Trick
User types → debounce waits for pause → switchMap cancels previous search →
new search runs → results delivered. 4 operators, one chain.

### Full Search Implementation

```kotlin
class SearchViewModel(
    private val api: SearchApi
) : ViewModel() {

    private val disposables = CompositeDisposable()
    val results = MutableLiveData<List<SearchResult>>()
    val loading = MutableLiveData<Boolean>()

    // Call this with the EditText's text change Observable
    fun bindSearch(queryStream: Observable<String>) {
        disposables += queryStream
            .debounce(300, TimeUnit.MILLISECONDS)  // wait for typing pause
            .filter { query -> query.length >= 2 } // ignore very short queries
            .distinctUntilChanged()                // ignore same query twice
            .switchMap { query ->                  // cancel previous search
                api.search(query)                  // returns Single<List<Result>>
                    .toObservable()
                    .subscribeOn(Schedulers.io())
                    .doOnSubscribe { loading.postValue(true) }
                    .doFinally { loading.postValue(false) }
                    .onErrorReturn { emptyList() }  // don't crash on network error
            }
            .observeOn(AndroidSchedulers.mainThread())
            .subscribe { searchResults ->
                results.value = searchResults
            }
    }

    override fun onCleared() = disposables.clear()
}

// In Fragment:
class SearchFragment : Fragment() {
    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        viewModel.bindSearch(
            searchEditText.textChanges()  // RxBinding
                .map { it.toString() }
        )
        viewModel.results.observe(viewLifecycleOwner) { results ->
            adapter.submitList(results)
        }
    }
}
```

### What Each Operator Contributes

```
User types: "r" "rx" "rxja" "rxjava"
            50ms gaps

debounce(300ms):
  Only fires after 300ms of silence
  → "rxjava" (user stopped typing)

filter(length >= 2):
  Prevents empty or single-char searches

distinctUntilChanged():
  If user types "rxjava", backspaces, retypes "rxjava"
  → only fires once (same value)

switchMap:
  If somehow two queries DO get through,
  previous API call is cancelled
  → Only latest result matters
```

---

## RX.09.4 — ViewModel + CompositeDisposable: Complete Template

```kotlin
abstract class RxViewModel : ViewModel() {
    protected val disposables = CompositeDisposable()

    override fun onCleared() {
        super.onCleared()
        disposables.clear()
    }
}

// Usage
class ProductViewModel(
    private val repo: ProductRepository
) : RxViewModel() {

    private val _products = MutableLiveData<List<Product>>()
    val products: LiveData<List<Product>> = _products

    private val _uiState = MutableLiveData<UiState>(UiState.Idle)
    val uiState: LiveData<UiState> = _uiState

    fun loadProducts(category: String) {
        disposables += repo.getProducts(category)
            .subscribeOn(Schedulers.io())
            .observeOn(AndroidSchedulers.mainThread())
            .doOnSubscribe { _uiState.value = UiState.Loading }
            .subscribe(
                { products ->
                    _products.value = products
                    _uiState.value = UiState.Success
                },
                { error ->
                    _uiState.value = UiState.Error(error.message ?: "Unknown")
                }
            )
    }
}
```

---

## RX.09.5 — RxJava vs Flow Migration Decision Table

> **Connects to:** [10_decision_maps.md]

### When to Migrate to Flow

| Signal                                      | Action                       |
|---------------------------------------------|------------------------------|
| New feature in existing RxJava codebase     | Write in Flow, interop at boundaries |
| Retrofit — new API interface                | Switch to suspend fun        |
| Room — new DAO                              | Use Flow<List<T>> instead of Flowable |
| ViewModel state management                  | Switch to StateFlow/SharedFlow |
| All new project                             | Use Coroutines + Flow exclusively |

### How to Interop During Migration

```kotlin
// Converting Observable to Flow (in new code that receives old RxJava)
val flow: Flow<T> = rxObservable.asFlow()

// Converting Flow to Observable (in old code that expects RxJava)
val observable: Observable<T> = flow.asObservable()

// Retrofit: both can coexist
interface ApiService {
    // Old RxJava endpoint
    @GET("users")
    fun getUsersRx(): Single<List<User>>

    // New Coroutines endpoint
    @GET("posts")
    suspend fun getPosts(): List<Post>
}
```

### Migration Priority

```
HIGH PRIORITY (migrate first):
├── Activity/Fragment subscriptions (leak risk)
├── New ViewModel state (use StateFlow)
└── New Retrofit calls (suspend fun)

LOW PRIORITY (leave for now):
├── Complex operator chains (map/flatMap/zip combos)
├── Existing working code that's stable
└── Places where RxJava's operators are uniquely suited
```

---

## Self-Test — RX.09

1. Your search chain uses `switchMap`. The user types "rx" and "rxjava"
   100ms apart. The "rx" search takes 500ms; the "rxjava" search takes 200ms.
   What does the user see? What would they see with `flatMap` instead?

2. Room's `Flowable<List<Message>>` emits whenever ANY message is inserted,
   updated, or deleted. If 100 messages are batch-inserted in a transaction,
   how many emissions does the Flowable make? (Hint: transaction boundary)

3. `doOnSubscribe` fires on the subscribing thread. Your chain has
   `subscribeOn(IO)`. If you put `doOnSubscribe { loading.value = true }`
   BEFORE `subscribeOn`, which thread does it run on? After `subscribeOn`?
   Which do you want for updating LiveData?

4. You zip two Single<T> calls. One takes 100ms; the other 2000ms.
   How long does the zip take? What happens if one of them errors?

5. You're migrating a ViewModel from RxJava to StateFlow. The existing code
   uses `BehaviorSubject` for state. What is the Flow equivalent? What
   property of BehaviorSubject maps to which property of StateFlow?

---

← [08_disposables_lifecycle.md](08_disposables_lifecycle.md) | [10_decision_maps.md →](10_decision_maps.md)
