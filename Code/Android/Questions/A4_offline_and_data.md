# Phase A4 — Offline-First & Data Layer Architecture

The data layer is where production Android apps live or die. You can have a beautiful MVVM or Clean Architecture presentation layer, but if your data layer doesn't handle flaky networks, process death, conflicting edits, and synchronization failures correctly, your app will frustrate users the moment they step into a subway tunnel. This phase is about the patterns that make data reliable: the Repository as a decision-maker, Room as the source of truth, the sync strategies that keep offline and online data consistent, and the Repository Bridge that ties it all together.

---

## A4.1 — Offline-First Architecture

> **Builds on:** [A3.6 — Clean Architecture](A3_architecture_patterns.md#a36--clean-architecture-the-full-stack)
> **Connects to:** [A4.3 — Repository Pattern](A4_offline_and_data.md#a43--repository-pattern-the-decision-maker)

### WHY Offline-First

Mobile networks are fundamentally unreliable. A user on a subway, in an elevator, or in a remote area has no guarantee of connectivity. An app that fails silently or crashes without internet is a bad app. The best mobile apps work the same whether the user has 5G or no signal.

More importantly: **latency**. Even with a good connection, fetching data from a server on every screen open adds 200–800ms of perceived loading time. An offline-first app shows cached data INSTANTLY and then updates silently in the background.

```
Online-first app (what bad apps do):
  User opens screen
  → API call (200-800ms wait)
  → Show loading spinner
  → API succeeds → render data
  → API fails → show empty state / error

  On the subway: error screen. User is frustrated.

Offline-first app:
  User opens screen
  → Room query (1-5ms) → render cached data IMMEDIATELY
  → Simultaneously: try API call in background
  → API succeeds → update Room → Room Flow emits → UI refreshes silently
  → API fails → user still sees cached data, small "last synced X ago" banner

  On the subway: works perfectly. User doesn't even notice.
```

### The Core Principle: Local Database = Single Source of Truth

```
WRONG (API-first, no source of truth):

  ViewModel.loadUsers()
       │
       ▼
  API call → success
       │
       ▼
  Update UI directly from API response
       │
       Problem: rotation → re-fetch needed, stale data after background,
       offline = error state, no data persistence across sessions

CORRECT (DB as single source of truth):

  ViewModel.loadUsers()
       │
       ▼
  Repository observes Room Flow ──────────────────────────► ViewModel
                 │                                         (always up to date)
                 │
  Room (persistent)           ◄──── Repository syncs from API
       │                             (writes to DB, not directly to ViewModel)
       │
  ViewModel gets update via Flow emission from Room

  UI always reads from Room. API writes to Room. Room → UI.
```

### Room + Flow: The Reactive Pipeline

```kotlin
// UserDao.kt — Room generates the Flow automatically
@Dao
interface UserDao {
    // Flow emits a new List every time the users table changes
    @Query("SELECT * FROM users WHERE is_deleted = 0 ORDER BY name ASC")
    fun observeUsers(): Flow<List<UserEntity>>

    @Query("SELECT * FROM users WHERE id = :id")
    suspend fun getUserById(id: String): UserEntity?

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertAll(users: List<UserEntity>)

    @Update
    suspend fun update(user: UserEntity)

    @Query("UPDATE users SET is_deleted = 1 WHERE id = :id")
    suspend fun softDelete(id: String)

    @Query("SELECT * FROM users WHERE is_deleted = 0 AND synced = 0")
    suspend fun getUnsynced(): List<UserEntity>
}

// UserRepositoryImpl.kt — offline-first pattern
class UserRepositoryImpl(
    private val userDao: UserDao,
    private val userApiService: UserApiService
) : UserRepository {

    // UI reads this — always from DB, never directly from API
    override fun observeUsers(): Flow<List<User>> =
        userDao.observeUsers()
            .map { entities -> entities.map { it.toDomain() } }

    // Called by the ViewModel to trigger a background sync
    override suspend fun refreshUsers(): Result<Unit> {
        return try {
            val dto = userApiService.getUsers()
            userDao.insertAll(dto.map { it.toEntity() })
            Result.success(Unit)
        } catch (e: Exception) {
            Result.failure(e)
        }
    }
}

// UserViewModel.kt — offline-first ViewModel
class UserViewModel(
    private val getUsersUseCase: GetUsersUseCase,
    private val refreshUsersUseCase: RefreshUsersUseCase
) : ViewModel() {

    private val _uiState = MutableStateFlow(UserUiState())
    val uiState: StateFlow<UserUiState> = _uiState.asStateFlow()

    init {
        // Start observing DB immediately — shows cached data at once
        observeLocalData()
        // Trigger background sync (doesn't block UI)
        refreshInBackground()
    }

    private fun observeLocalData() {
        viewModelScope.launch {
            getUsersUseCase()   // returns Flow<List<User>>
                .collect { users ->
                    _uiState.update { it.copy(users = users, isLoading = false) }
                }
        }
    }

    private fun refreshInBackground() {
        viewModelScope.launch {
            _uiState.update { it.copy(isSyncing = true) }
            val result = refreshUsersUseCase()
            _uiState.update {
                it.copy(
                    isSyncing = false,
                    syncError = if (result.isFailure) result.exceptionOrNull()?.message else null
                )
            }
        }
    }

    fun onPullToRefresh() {
        refreshInBackground()
    }
}
```

### Offline-First State Model

```kotlin
data class UserUiState(
    val users: List<User> = emptyList(),    // from Room — always available
    val isLoading: Boolean = true,           // true before first DB emission
    val isSyncing: Boolean = false,          // background API sync in progress
    val syncError: String? = null,           // API sync failed (but DB still works)
    val lastSyncedAt: Long? = null           // timestamp of last successful sync
) {
    val showSyncBanner: Boolean get() = syncError != null || isSyncing
    val syncBannerText: String get() = when {
        isSyncing -> "Syncing..."
        syncError != null -> "Offline — showing cached data"
        else -> ""
    }
}
```

### Complete Offline-First Flow Diagram

```
App Launch (with connectivity):

  ViewModel.init()
      │
      ├──── observeLocalData() ──────────────────────────────────────────┐
      │         │                                                          │
      │         │ Room.observeUsers() emits IMMEDIATELY (even if empty)   │
      │         ▼                                                          │
      │     UI renders (possibly empty with isLoading=true)               │
      │                                                                    │
      └──── refreshInBackground()                                         │
                │                                                          │
                │ API call (200ms-2s)                                      │
                ▼                                                          │
           API returns users                                               │
                │                                                          │
                ▼                                                          │
           Room.insertAll(users)    ◄── DB write triggers Flow            │
                │                                                          │
                └──────────────────────────────────────────────────────────┘
                     Room Flow emits new list → UI updates automatically

App Launch (without connectivity):

  ViewModel.init()
      │
      ├──── observeLocalData() ──────────────────────────────────────────┐
      │         │                                                          │
      │         │ Room.observeUsers() emits cached data IMMEDIATELY       │
      │         ▼                                                          │
      │     UI renders with cached data (instant)                         │
      │                                                                    │
      └──── refreshInBackground()                                         │
                │                                                          │
                │ API call → fails (IOException / UnknownHostException)   │
                ▼                                                          │
           isSyncing=false, syncError="Offline – showing cached data"     │
                │                                                          │
           UI shows sync error banner (cached data still visible)         │
```

### Interview Q&A

**"User opens the app with no internet. What happens with an offline-first architecture?"**
Room emits the cached data immediately (within milliseconds). The ViewModel also triggers a background refresh which fails. The UI shows the cached data (which the user can fully interact with) plus a small banner saying "Offline — showing cached data". When connectivity returns, the ViewModel can re-trigger sync (via `ConnectivityManager` broadcast or WorkManager).

**"How does Room's Flow automatically update the UI when data changes?"**
Room uses `InvalidationTracker` internally. When you write to a table, Room marks it as invalid. All active `Flow` queries on that table immediately emit a new result. This is how `userDao.observeUsers()` can return a `Flow<List<UserEntity>>` that automatically pushes new values when the sync writes new data — no polling, no manual refresh needed.

**"What's the downside of offline-first?"**
(1) Complexity: three layers of code (API, DB, UI) vs one API call. (2) Data freshness: the user may see stale data if sync hasn't run. (3) Conflict resolution (see A4.4): if the user edits data offline and someone else edits the same data online, you need a conflict resolution strategy. (4) Storage: you're caching everything locally, which uses device storage.

---

## A4.2 — API-Based (Online-First) Applications

> **Connects to:** [A4.3 — Repository Pattern](A4_offline_and_data.md#a43--repository-pattern-the-decision-maker)

### When Online-First Is Acceptable

Some data MUST be real-time and cannot be cached meaningfully:
- **Stock prices, crypto prices**: a 5-second-old price is wrong
- **Live sports scores**: cached = wrong
- **Map tiles with real-time traffic**: cached = outdated routing
- **One-time use codes**: SMS verification, payment tokens
- **Streaming content**: YouTube, audio streams — too large to pre-cache

For these, offline-first adds complexity without benefit. Online-first with graceful degradation is correct.

### Three Caching Approaches

#### Approach 1: HTTP Caching (OkHttp + Server Cache-Control)

The simplest form — transparent to your code. The server sends `Cache-Control` headers; OkHttp caches the response on disk.

```kotlin
// NetworkModule.kt
val okHttpClient = OkHttpClient.Builder()
    .cache(Cache(
        directory = File(context.cacheDir, "http_cache"),
        maxSize = 10L * 1024 * 1024  // 10 MB
    ))
    .addInterceptor { chain ->
        val request = chain.request()
        // If offline, serve from cache (even expired cache)
        val isOnline = isNetworkAvailable(context)
        val requestWithCacheControl = if (!isOnline) {
            request.newBuilder()
                .header("Cache-Control", "public, only-if-cached, max-stale=${60 * 60 * 24}")
                .build()
        } else {
            request
        }
        chain.proceed(requestWithCacheControl)
    }
    .build()
```

What happens:
- First call: hits API, saves response to disk cache
- Subsequent calls (within `max-age`): returns from disk, no network request
- Stale cache (offline): served with `only-if-cached` — shows old data rather than error
- Server returns `ETag`/`Last-Modified`: OkHttp sends conditional GET → 304 Not Modified if unchanged → zero data transferred

**Limitation**: Cache is keyed by URL. Personalized responses (with user tokens in headers) are not cached by default unless you configure cache keys carefully.

#### Approach 2: In-Memory Cache (ViewModel / Repository level)

Fast (no disk I/O), but lost on process death.

```kotlin
class UserRepositoryImpl(
    private val apiService: UserApiService
) : UserRepository {

    // In-memory cache with TTL
    private var cachedUsers: List<User>? = null
    private var cacheTimestamp: Long = 0
    private val CACHE_TTL_MS = 5 * 60 * 1000L  // 5 minutes

    override suspend fun getUsers(forceRefresh: Boolean = false): List<User> {
        val isCacheValid = cachedUsers != null &&
            (System.currentTimeMillis() - cacheTimestamp) < CACHE_TTL_MS

        return if (!forceRefresh && isCacheValid) {
            cachedUsers!!  // serve from memory
        } else {
            val users = apiService.getUsers().map { it.toDomain() }
            cachedUsers = users
            cacheTimestamp = System.currentTimeMillis()
            users
        }
    }
}
```

**Use case**: session data (auth token, user preferences fetched on login, reference data like countries/currencies). Lost on process death → refetch on cold start.

#### Approach 3: Disk Cache (DataStore / Room)

Survives process death. More code, but persists across sessions.

```kotlin
// Using DataStore for simple key-value caching
class UserPreferencesRepository(
    private val dataStore: DataStore<Preferences>
) {
    private val USER_PROFILE_KEY = stringPreferencesKey("user_profile_json")
    private val PROFILE_CACHE_TIME = longPreferencesKey("profile_cache_time")

    suspend fun getCachedProfile(): UserProfile? {
        val prefs = dataStore.data.first()
        val json = prefs[USER_PROFILE_KEY] ?: return null
        val cacheTime = prefs[PROFILE_CACHE_TIME] ?: 0L
        return if (System.currentTimeMillis() - cacheTime < TTL) {
            gson.fromJson(json, UserProfile::class.java)
        } else null
    }

    suspend fun cacheProfile(profile: UserProfile) {
        dataStore.edit { prefs ->
            prefs[USER_PROFILE_KEY] = gson.toJson(profile)
            prefs[PROFILE_CACHE_TIME] = System.currentTimeMillis()
        }
    }
}
```

### Sealed Class for Network Results

```kotlin
// NetworkResult.kt — used across all repositories
sealed class NetworkResult<out T> {
    data class Success<T>(val data: T) : NetworkResult<T>()
    data class Error(
        val code: Int?,
        val message: String,
        val exception: Exception? = null
    ) : NetworkResult<Nothing>()
    object Loading : NetworkResult<Nothing>()

    val isSuccess get() = this is Success
    val isError get() = this is Error

    // Extension to transform data while preserving error/loading
    fun <R> map(transform: (T) -> R): NetworkResult<R> = when (this) {
        is Success -> Success(transform(data))
        is Error -> this
        Loading -> Loading
    }
}
```

```kotlin
// Retrofit error handling helper
suspend fun <T> safeApiCall(call: suspend () -> Response<T>): NetworkResult<T> {
    return try {
        val response = call()
        if (response.isSuccessful) {
            val body = response.body()
            if (body != null) NetworkResult.Success(body)
            else NetworkResult.Error(response.code(), "Empty response body")
        } else {
            val errorBody = response.errorBody()?.string()
            val errorMessage = parseError(errorBody) ?: response.message()
            NetworkResult.Error(response.code(), errorMessage)
        }
    } catch (e: IOException) {
        NetworkResult.Error(null, "Network error: ${e.message}", e)
    } catch (e: HttpException) {
        NetworkResult.Error(e.code(), e.message(), e)
    }
}
```

### Retry with Exponential Backoff

```kotlin
suspend fun <T> withRetry(
    times: Int = 3,
    initialDelay: Long = 1000L,
    maxDelay: Long = 30_000L,
    factor: Double = 2.0,
    block: suspend () -> T
): T {
    var currentDelay = initialDelay
    repeat(times - 1) { attempt ->
        try {
            return block()
        } catch (e: Exception) {
            if (e is CancellationException) throw e  // never swallow cancellation
        }
        delay(currentDelay)
        currentDelay = (currentDelay * factor).toLong().coerceAtMost(maxDelay)
    }
    return block()  // last attempt throws if it fails
}

// Usage:
val users = withRetry(times = 3) { apiService.getUsers() }
```

### Optimistic Updates

Show the result before confirmation, roll back on failure:

```kotlin
fun onLikePost(postId: String) {
    viewModelScope.launch {
        // 1. Update state immediately (optimistic)
        val originalPosts = _state.value.posts
        _state.update { state ->
            state.copy(posts = state.posts.map { post ->
                if (post.id == postId) post.copy(liked = true, likeCount = post.likeCount + 1)
                else post
            })
        }
        // 2. Call API in background
        val result = safeApiCall { apiService.likePost(postId) }
        // 3a. Success: do nothing (local state already matches server)
        // 3b. Failure: revert
        if (result is NetworkResult.Error) {
            _state.update { it.copy(posts = originalPosts) }
            _sideEffects.emit(SideEffect.ShowError("Failed to like post"))
        }
    }
}
```

### Interview Q&A

**"Your app shows a user profile. The API takes 800ms. How do you handle this?"**
Three-layer answer: (1) Show shimmer/skeleton loading state immediately using `UiState.Loading`. (2) Trigger the API call in the ViewModel on `init` or first composition. (3) On success, transition to `UiState.Success(profile)`. On failure, show `UiState.Error` with retry button. If you have offline-first setup, show the cached profile from Room first, then refresh.

**"The API changes a field name from `user_name` to `username`. How do you handle this?"**
This is why the DTO layer exists. Change only `UserDto`: `@SerializedName("username") val name: String`. The domain model `User` is unchanged. Room entity is unchanged. The mapper `UserDto.toDomain()` still maps `dto.name` to `user.name`. Zero ripple effect outside the DTO class.

---

## A4.3 — Repository Pattern: The Decision-Maker

> **Builds on:** [A4.1 — Offline-First](A4_offline_and_data.md#a41--offline-first-architecture) · [A4.2 — API-Based](A4_offline_and_data.md#a42--api-based-online-first-applications)

### WHY Repository Is Critical

Without a Repository, every ViewModel must decide: "Should I use cached data? Should I fetch fresh data? Did this data change?" That logic is duplicated across every screen that shows users. With a Repository, that decision lives in ONE place.

```
Without Repository (anti-pattern):

  UserListViewModel:
    if (cache.isValid()) show(cache.users)
    else fetchFromApi()

  UserDetailViewModel:
    if (cache.isValid()) show(cache.user)
    else fetchFromApi()

  SearchViewModel:
    if (cache.isValid()) filter(cache.users, query)
    else fetchFromApi()

  ← Same logic in 3 ViewModels. Change the caching policy → touch 3 files.

With Repository:

  UserRepository.getUsers()  ← decides: cache or API
  UserRepository.getUser(id) ← same decision policy

  UserListViewModel → UserRepository.getUsers()
  UserDetailViewModel → UserRepository.getUser(id)
  SearchViewModel → UserRepository.getUsers()

  ← Change caching policy → touch 1 file (Repository).
```

### The networkBoundResource Pattern

The complete decision tree for every data request:

```kotlin
// Reusable utility (inline function for efficiency)
inline fun <LocalType, RemoteType, DomainType> networkBoundResource(
    crossinline queryDb: () -> Flow<LocalType?>,
    crossinline fetchRemote: suspend () -> RemoteType,
    crossinline saveRemote: suspend (RemoteType) -> Unit,
    crossinline mapToDomain: (LocalType) -> DomainType,
    crossinline shouldFetch: (LocalType?) -> Boolean = { true }
): Flow<Resource<DomainType>> = flow {

    emit(Resource.Loading())

    val localData = queryDb().first()

    if (shouldFetch(localData)) {
        // Emit local data while fetching (don't make user wait for network)
        if (localData != null) {
            emit(Resource.Success(mapToDomain(localData), isStale = true))
        }

        try {
            val remoteData = fetchRemote()
            saveRemote(remoteData)    // saves to DB → triggers Flow emission below
        } catch (e: Exception) {
            // Network failed — emit local data as best-available result
            if (localData != null) {
                emit(Resource.Success(mapToDomain(localData), isStale = true))
            } else {
                emit(Resource.Error(e.message ?: "Unknown error"))
            }
        }
    }

    // Collect ongoing DB changes (this is the live stream)
    queryDb()
        .filter { it != null }
        .collect { freshLocal ->
            emit(Resource.Success(mapToDomain(freshLocal!!)))
        }
}
```

```kotlin
// UserRepositoryImpl.kt using networkBoundResource
class UserRepositoryImpl(
    private val dao: UserDao,
    private val api: UserApiService,
    private val prefs: SharedPreferences
) : UserRepository {

    override fun getUsers(): Flow<Resource<List<User>>> = networkBoundResource(
        queryDb = { dao.observeUsers().map { it.ifEmpty { null } } },
        fetchRemote = { api.getUsers() },
        saveRemote = { dtos ->
            val entities = dtos.map { it.toEntity() }
            dao.insertAll(entities)
            prefs.edit().putLong(LAST_SYNC_KEY, System.currentTimeMillis()).apply()
        },
        mapToDomain = { entities -> entities.map { it.toDomain() } },
        shouldFetch = { localData ->
            localData == null || isCacheStale()
        }
    )

    private fun isCacheStale(): Boolean {
        val lastSync = prefs.getLong(LAST_SYNC_KEY, 0L)
        return System.currentTimeMillis() - lastSync > CACHE_TTL_MS
    }
}
```

### The Mapper Triple: Why Three Model Types

```
                  API Response        Room DB             Business Logic
Model Type:       DTO                 Entity              Domain Model
─────────────────────────────────────────────────────────────────────────
Android deps:     No (Gson/Moshi)     Yes (@Entity, @PK)  No (pure Kotlin)
Mutable?          No (val fields)     No (val fields)     No (data class)
Example field:    userName: String    user_name: String   name: String
(API uses snake    (Gson maps it)     (Room column)       (stable)
case)
Contains:         API-shaped data     DB-optimized data   Business concepts
Owner:            Data layer          Data layer          Domain layer
Annotations:      @SerializedName     @Entity, @Column    None
```

```kotlin
// Three concrete representations of the same concept

// DTO (API layer) — shaped by what the API returns
data class UserDto(
    @SerializedName("user_id")   val id: String,
    @SerializedName("user_name") val name: String,
    @SerializedName("email_address") val email: String,
    @SerializedName("access_level") val accessLevel: Int,
    @SerializedName("created_at") val createdAt: String  // ISO string from API
)

// Entity (DB layer) — shaped for efficient DB storage
@Entity(tableName = "users")
data class UserEntity(
    @PrimaryKey val id: String,
    @ColumnInfo(name = "name") val name: String,
    @ColumnInfo(name = "email") val email: String,
    @ColumnInfo(name = "role") val role: String,  // stored as string
    @ColumnInfo(name = "created_at_epoch") val createdAtEpoch: Long,  // stored as epoch
    @ColumnInfo(name = "last_synced") val lastSynced: Long,
    @ColumnInfo(name = "is_dirty") val isDirty: Boolean = false  // local-only flag
)

// Domain Model — shaped for business logic
data class User(
    val id: String,
    val name: String,
    val email: String,
    val role: UserRole,      // proper enum, not string or int
    val createdAt: Instant,  // proper type, not String or Long
    val isPremium: Boolean = role == UserRole.PREMIUM  // business rule
)

// Mappers
fun UserDto.toEntity() = UserEntity(
    id = id, name = name, email = email,
    role = UserRole.fromAccessLevel(accessLevel).name,
    createdAtEpoch = Instant.parse(createdAt).toEpochMilli(),
    lastSynced = System.currentTimeMillis()
)

fun UserEntity.toDomain() = User(
    id = id, name = name, email = email,
    role = UserRole.valueOf(role),
    createdAt = Instant.ofEpochMilli(createdAtEpoch)
)
```

### Cache Invalidation Strategies

```
Strategy 1: TIME-BASED (TTL — Time To Live)
  Simplest. Cache is valid for N minutes/hours/days.
  Good for: reference data (countries, categories), user profiles
  Bad for: data that changes instantly (stock prices, messages)

  Implementation: store `lastSyncedAt` timestamp alongside data.
  shouldFetch = { System.currentTimeMillis() - lastSyncedAt > TTL }

Strategy 2: EVENT-BASED
  Invalidate immediately after a mutation.
  Good for: any data your app modifies (user profile after update)
  After PUT /user → call repository.invalidate() → next getUser() fetches fresh

  Implementation: after successful write, clear cache entry or set lastSyncedAt=0.

Strategy 3: VERSION/ETAG
  Server sends a version tag. Client sends it back. Server says "same" (304)
  or "changed" (200 + new data).
  Good for: large responses where bandwidth matters
  Requires server support.

Strategy 4: EVENT-DRIVEN (FCM Push)
  Server pushes a "data changed" notification. Client syncs on receipt.
  Good for: collaborative apps (shared documents, team tasks)
  Bad for: apps where push isn't available or real-time isn't needed.
```

### Sharing Repository Data Across Multiple Screens

```kotlin
// Problem: 3 ViewModels all call repository.getUsers() → 3 separate DB queries
// Solution: share the upstream Flow with WhileSubscribed

class UserRepositoryImpl(
    private val dao: UserDao,
    private val api: UserApiService,
    private val scope: CoroutineScope  // application scope
) : UserRepository {

    // Shared Flow — one DB subscription, multiple collectors
    private val _usersFlow: Flow<List<User>> = dao.observeUsers()
        .map { entities -> entities.map { it.toDomain() } }
        .shareIn(
            scope = scope,
            started = SharingStarted.WhileSubscribed(stopTimeoutMillis = 5000),
            replay = 1  // new collectors get the latest value immediately
        )

    override fun observeUsers(): Flow<List<User>> = _usersFlow
}

// Now all ViewModels share the same underlying DB subscription
// When the last subscriber leaves for >5s, the upstream Flow is cancelled
// When a new subscriber arrives within the 5s window, it reuses the existing subscription
```

### Interview Q&A

**"Who should call the repository — Activity or ViewModel?"**
ViewModel. The Activity/Fragment is the View layer — it observes state and sends user events. It should never directly call data layer code. Repositories in Activity would bypass the ViewModel, making state management unpredictable and testing impossible (you can't mock a repository call that happens in an Activity).

**"Repository.getUser() is called from three different screens. How do you avoid triple network calls?"**
Use `shareIn(WhileSubscribed(5000), replay=1)` on the underlying Flow in the repository. All three ViewModels collect from the same shared Flow. Only one DB subscription and one network sync exist. The `5000ms` stop timeout keeps the subscription alive for 5 seconds after the last subscriber leaves (handles rotation without re-syncing).

**"How do you test a Repository that mixes Room and Retrofit?"**
Test with in-memory Room database (no file I/O, no emulator needed) and a Retrofit mock (MockWebServer or a fake API implementation). Write a `FakeUserApi` that returns hardcoded data, use an in-memory Room DB, and test the repository logic directly in a JUnit test. This is faster and more reliable than Espresso tests.

---

## A4.4 — Data Synchronization Strategies

> **Builds on:** [A4.1 — Offline-First](A4_offline_and_data.md#a41--offline-first-architecture)
> **Connects to:** [A3.6 — Clean Architecture](A3_architecture_patterns.md#a36--clean-architecture-the-full-stack)

### Three Sync Trigger Types

```
Trigger 1: USER-INITIATED (Pull-to-Refresh)
  Most explicit. User swipes down → trigger sync.
  Always provide this. Users need control.

Trigger 2: PERIODIC BACKGROUND SYNC (WorkManager)
  Automatic. Happens while app is in background.
  Good for: feed apps, email, news, social media.
  Guaranteed to run even after process death and device restart.

Trigger 3: PUSH-TRIGGERED (FCM → Immediate Sync)
  Server says "hey, data changed" → client syncs now.
  Most responsive. Good for: messaging, collaborative documents.
  Requires FCM setup and server-side push infrastructure.
```

### WorkManager: Background Sync That Survives Everything

```kotlin
// SyncUsersWorker.kt
@HiltWorker
class SyncUsersWorker @AssistedInject constructor(
    @Assisted appContext: Context,
    @Assisted workerParams: WorkerParameters,
    private val userRepository: UserRepository
) : CoroutineWorker(appContext, workerParams) {

    override suspend fun doWork(): Result {
        return try {
            userRepository.refreshUsers()
            Result.success()
        } catch (e: Exception) {
            // Retry up to 3 times with exponential backoff
            if (runAttemptCount < 3) Result.retry()
            else Result.failure()
        }
    }

    companion object {
        const val WORK_NAME = "sync_users"

        fun buildPeriodicRequest(): PeriodicWorkRequest =
            PeriodicWorkRequestBuilder<SyncUsersWorker>(
                repeatInterval = 1, TimeUnit.HOURS
            )
            .setConstraints(
                Constraints.Builder()
                    .setRequiredNetworkType(NetworkType.CONNECTED)
                    .setRequiresBatteryNotLow(true)
                    .build()
            )
            .setBackoffCriteria(
                BackoffPolicy.EXPONENTIAL,
                WorkRequest.MIN_BACKOFF_MILLIS,
                TimeUnit.MILLISECONDS
            )
            .build()

        fun buildImmediateRequest(): OneTimeWorkRequest =
            OneTimeWorkRequestBuilder<SyncUsersWorker>()
                .setConstraints(
                    Constraints.Builder()
                        .setRequiredNetworkType(NetworkType.CONNECTED)
                        .build()
                )
                .build()
    }
}

// In Application.onCreate() or wherever you schedule:
WorkManager.getInstance(context).enqueueUniquePeriodicWork(
    SyncUsersWorker.WORK_NAME,
    ExistingPeriodicWorkPolicy.KEEP,  // don't reschedule if already running
    SyncUsersWorker.buildPeriodicRequest()
)
```

### WorkManager Chaining

```kotlin
// Complex sync pipeline: fetch → process → upload pending local changes
val fetchWork = OneTimeWorkRequestBuilder<FetchRemoteChangesWorker>().build()
val processWork = OneTimeWorkRequestBuilder<ProcessChangesWorker>().build()
val uploadWork = OneTimeWorkRequestBuilder<UploadLocalChangesWorker>().build()

WorkManager.getInstance(context)
    .beginUniqueWork("full_sync", ExistingWorkPolicy.REPLACE, fetchWork)
    .then(processWork)
    .then(uploadWork)
    .enqueue()
```

### Conflict Resolution: Four Strategies

**Context:** User A edits a note offline. User B edits the same note online. User A reconnects. What happens?

```
Strategy 1: Last Write Wins (LWW)
  ──────────────────────────────
  Whoever wrote last, wins. Determined by timestamp.
  Simple. No user involvement.
  Risk: User A's offline changes are silently overwritten by User B.
  Good for: personal data (notes, settings) where conflicts are rare.

  Implementation:
  - Each entity has an `updated_at` field
  - On sync: if server.updated_at > local.updated_at → use server's version
  - If local.updated_at > server.updated_at → upload local version

Strategy 2: Server Wins
  ─────────────────────
  Server is always authoritative. Local changes are discarded on conflict.
  Good for: shared data where consistency > user preference
  (financial records, inventory, admin-managed content).

  Implementation:
  - On sync: always replace local with server version
  - Upload local changes first, then fetch server state
  - If server rejects your change: revert local, show error

Strategy 3: Client Wins
  ──────────────────────
  Local changes always take precedence. User owns their data.
  Good for: local-first apps (personal journals, offline drafts).

  Implementation:
  - Track local changes with `is_dirty = true` flag
  - On sync: send local changes to server, ignore server response
  - Risk: user might not see changes made by other sessions

Strategy 4: Manual Merge (Conflict Detection)
  ────────────────────────────────────────────
  Detect the conflict, show it to the user, let them decide.
  Good for: collaborative documents, shared notes, team apps.
  Complex but user-friendly.

  Detection:
  - Each entity has `version` (integer, incremented on write)
  - On upload: send `{ ..., "base_version": 3 }`
  - Server: if current version ≠ 3 → reject with 409 Conflict
  - Client: fetch server version, show diff to user

  Field-level merge (automatic):
  - If User A changed `title` and User B changed `body`:
    → merge = User A's title + User B's body (no conflict!)
  - Only true conflicts (same field changed) require user resolution
```

### Implementing Conflict Detection

```kotlin
// UserEntity with versioning
@Entity(tableName = "users")
data class UserEntity(
    @PrimaryKey val id: String,
    val name: String,
    val email: String,
    val version: Int = 0,       // server-assigned version number
    val isDirty: Boolean = false,  // true = has local unpublished changes
    val baseVersion: Int = 0    // version when we last synced
)

// Repository sync logic with conflict detection
suspend fun syncUser(userId: String) {
    val local = dao.getUser(userId) ?: return

    if (!local.isDirty) {
        // No local changes — just fetch latest
        val remote = api.getUser(userId)
        dao.insert(remote.toEntity())
        return
    }

    // Has local changes — try to upload
    try {
        val response = api.updateUser(
            userId,
            UpdateUserRequest(
                name = local.name,
                email = local.email,
                baseVersion = local.baseVersion    // "I started from version X"
            )
        )
        // Server accepted — update version, clear dirty flag
        dao.insert(local.copy(version = response.newVersion, isDirty = false))

    } catch (e: ConflictException) {  // HTTP 409
        // Server rejected — fetch current server version
        val serverVersion = api.getUser(userId)

        // Attempt field-level merge
        val merged = mergeUsers(local, serverVersion.toDomain())
        if (merged != null) {
            // Merge succeeded — try again with merged version
            dao.insert(merged.toEntity())
            syncUser(userId)  // retry
        } else {
            // True conflict — notify user to resolve manually
            dao.insert(local.copy(hasConflict = true))
            notifyConflict(userId)
        }
    }
}
```

### Optimistic Update Pattern: Full Lifecycle

```kotlin
// The complete optimistic update flow in a ViewModel
fun onToggleUserActive(user: User) {
    viewModelScope.launch {
        // Snapshot for rollback
        val originalUsers = _state.value.users

        // 1. Optimistic: update state immediately (zero perceived latency)
        _state.update { state ->
            state.copy(users = state.users.map { u ->
                if (u.id == user.id) u.copy(isActive = !u.isActive) else u
            })
        }

        // 2. Also update Room (so the DB state matches UI — important for offline)
        dao.updateUser(user.copy(isActive = !user.isActive, isDirty = true))

        // 3. Call API
        val result = safeApiCall { api.updateUser(user.id, UpdateRequest(isActive = !user.isActive)) }

        when (result) {
            is NetworkResult.Success -> {
                // 4a. API confirmed → clear dirty flag, update version
                dao.updateUser(user.copy(
                    isActive = !user.isActive,
                    isDirty = false,
                    version = result.data.version
                ))
                // UI state already correct from step 1 — nothing more needed
            }
            is NetworkResult.Error -> {
                // 4b. API failed → revert both DB and state
                dao.updateUser(user)  // revert DB
                _state.update { it.copy(users = originalUsers) }  // revert UI
                _sideEffects.emit(SideEffect.ShowError("Update failed: ${result.message}"))
            }
            NetworkResult.Loading -> { /* unreachable */ }
        }
    }
}
```

### Sync Status Indicators: UX That Doesn't Panic Users

```kotlin
// SyncStatus.kt
sealed class SyncStatus {
    object Idle : SyncStatus()
    object Syncing : SyncStatus()
    data class Error(val message: String) : SyncStatus()
    data class Success(val lastSyncedAt: Long) : SyncStatus()
}

// In UiState
data class UserListUiState(
    val users: List<User> = emptyList(),
    val isLoading: Boolean = true,
    val syncStatus: SyncStatus = SyncStatus.Idle
) {
    val syncBannerText: String? get() = when (syncStatus) {
        is SyncStatus.Syncing -> "Syncing..."
        is SyncStatus.Error -> "Offline — last sync ${syncStatus.message}"
        is SyncStatus.Success -> {
            val minutesAgo = (System.currentTimeMillis() - syncStatus.lastSyncedAt) / 60_000
            if (minutesAgo < 2) null  // "synced just now" → show nothing
            else "Last synced ${minutesAgo}m ago"
        }
        SyncStatus.Idle -> null
    }
}
```

### Preventing Duplicate Data on Sync

```kotlin
// Room: use REPLACE strategy to upsert (prevents duplicates)
@Insert(onConflict = OnConflictStrategy.REPLACE)
suspend fun insertAll(users: List<UserEntity>)

// Problem: REPLACE deletes + re-inserts, which triggers observers even if nothing changed
// Better for large datasets: use IGNORE + UPDATE
@Insert(onConflict = OnConflictStrategy.IGNORE)
suspend fun insertIfNotExists(users: List<UserEntity>): List<Long>

@Update
suspend fun update(user: UserEntity)

// Client-side idempotency keys (UUID generated on device)
data class PendingAction(
    val id: String = UUID.randomUUID().toString(),  // idempotency key
    val type: ActionType,
    val payload: String,   // JSON
    val createdAt: Long = System.currentTimeMillis(),
    val synced: Boolean = false
)

// Server can deduplicate by idempotency key — safe to retry without double-processing
```

### Interview Q&A

**"The user edits a note offline. Their friend edits the same note online. They reconnect. What happens?"**

Walk through the four strategies:
1. **What's your conflict detection mechanism?** Version numbers or timestamps on each entity.
2. **When the offline user reconnects**, the repository tries to upload the local change, including the `baseVersion` (the version when the user started editing).
3. **Server checks**: if the current server version ≠ baseVersion → conflict detected → HTTP 409.
4. **What to do**: depends on app design. For shared notes: perform field-level merge (different fields → auto-merge, same field → show conflict dialog). For personal notes: Last Write Wins based on timestamp.

**"How do you test a Repository that uses both Room and Retrofit?"**

(1) In-memory Room database: `Room.inMemoryDatabaseBuilder(context, AppDatabase::class.java).build()` — no file I/O, no emulator needed, runs in JVM tests with Robolectric. (2) Retrofit mock: implement a `FakeUserApi` that returns hardcoded responses for success paths, throws exceptions for error paths. (3) Test the repository's decision logic directly: "when local is stale, fetchRemote is called; when local is fresh, fetchRemote is not called."

**"WorkManager vs AlarmManager vs Foreground Service for background sync — when to use each?"**

| | WorkManager | AlarmManager | Foreground Service |
|--|--|--|--|
| Guarantees completion | Yes | No | Yes (while running) |
| Survives reboot | Yes | Only if you re-register | Only if you restart |
| Battery constraints | Built-in | Manual | Manual |
| Doze mode | Handles it | Breaks in Doze | OK if foreground |
| Best for | Periodic sync, deferred work | Exact-time alarms (reminders, calendar) | Active downloads, music playback |

For data sync: always WorkManager. AlarmManager for user-facing exact-time reminders (8 PM notification). Foreground Service for real-time data that must stay running (GPS tracking, live audio).

---

## Master Summary: Offline & Data Layer

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  PHASE A4 — OFFLINE-FIRST & DATA LAYER MASTER SUMMARY                        │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  OFFLINE-FIRST (A4.1)                                                        │
│  Local DB = single source of truth. UI reads only from Room.                 │
│  API → Room → Room Flow → ViewModel → UI (never API → ViewModel directly).  │
│  On open: Room emits immediately (cached). Background sync runs in parallel. │
│  On network error: cached data + sync error banner. App still works.         │
│                                                                              │
│  ONLINE-FIRST (A4.2)                                                         │
│  When acceptable: real-time data, streaming, one-time use tokens.           │
│  Caching: HTTP (OkHttp Cache-Control), in-memory (session), disk (Room).    │
│  Error handling: sealed class NetworkResult<T> (Success/Error/Loading).     │
│  Optimistic updates: update state → call API → rollback on failure.         │
│                                                                              │
│  REPOSITORY PATTERN (A4.3)                                                   │
│  Single decision point: is cache fresh? fetch from DB or API?                │
│  networkBoundResource(): emit local stale → fetch API → write DB → emit     │
│  Three model types: DTO (API-shaped) / Entity (DB-shaped) / Domain (stable) │
│  Mapper: DTO→Entity, Entity→Domain. Change one layer → touch one mapper.    │
│  Share across screens: shareIn(WhileSubscribed(5000), replay=1).            │
│                                                                              │
│  DATA SYNC (A4.4)                                                            │
│  Triggers: user pull-to-refresh / WorkManager periodic / FCM push.          │
│  WorkManager: guaranteed execution, constraint-aware (network, battery).    │
│  Conflict resolution: Last Write Wins, Server Wins, Client Wins, Merge.     │
│  Detection: version numbers + baseVersion → HTTP 409 on conflict.           │
│  Optimistic updates: update DB + state immediately, rollback on API fail.   │
│  Idempotency keys: UUID per action, safe to retry without duplicates.       │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

*← [Phase A3 — Architecture Patterns](A3_architecture_patterns.md) | [Phase A5 — Jetpack Compose →](A5_jetpack_compose.md)*

---

**Cross-references:**
- Kotlin coroutines (suspend functions, viewModelScope): [Kotlin 09 — Coroutines](../../Kotlin/Questions/09_coroutines_execution_mechanics.md)
- Kotlin Flow (Room → ViewModel pipeline): [Kotlin 11 — Flow](../../Kotlin/Questions/11_flow.md)
- Jetpack components (Room, DataStore, WorkManager): [Kotlin 14 — Jetpack Components](../../Kotlin/Questions/14_jetpack_components.md)
- Networking (Retrofit, OkHttp): [Kotlin 15 — Networking](../../Kotlin/Questions/15_networking.md)
- Android performance (memory, leaks): [Kotlin 17 — Performance & Memory](../../Kotlin/Questions/17_performance_and_memory.md)
- Java concurrency (thread pools, executors): [J7 — Concurrent Utilities](../../Java/Questions/J7_concurrent_utilities.md)
