# Phase 14: Jetpack Components

## Navigation
[← Master Index](master_chains.md)

## Questions in This File
- [Q14.1 — Room — Internals](#q141--room--internals)
- [Q14.2 — WorkManager](#q142--workmanager)
- [Q14.3 — Paging 3](#q143--paging-3)
- [Q14.4 — Thread-Safe Caching](#q144--thread-safe-caching)

---

## Q14.1 — Room — Internals

> **Builds on:** [Q11.3 — Flow (Room returns Flow)](11_flow.md#q113--stateflow-vs-sharedflow) · [Q9.2 — Dispatchers.IO for DB](09_coroutines_execution_mechanics.md#q92--coroutine-context-and-dispatchers)
> **Connects to:** [Q13.6 — Repository pattern](13_android_architecture.md#q136--repository-and-offline-first-patterns) · [Q14.2 — WorkManager](14_jetpack_components.md#q142--workmanager)
> **Reference:** [Android Docs — Room persistence library](https://developer.android.com/training/data-storage/room)

### The Concrete Picture

Starting state — raw SQLite (what Room replaces):
```kotlin
// Without Room — raw SQLite, runtime crash risk:
val cursor = db.rawQuery("SELECT * FROM usrs", null)  // typo "usrs" → crashes at runtime!
while (cursor.moveToNext()) {
    val name = cursor.getString(cursor.getColumnIndex("nam"))  // wrong column → silent null
}
```

After Room — compile-time SQL verification:
```kotlin
@Entity(tableName = "users")
data class UserEntity(@PrimaryKey val id: String, val name: String, val age: Int)

@Dao
interface UserDao {
    @Query("SELECT * FROM usrs")        // ← COMPILE ERROR: Table 'usrs' not found
    fun getAll(): List<UserEntity>

    @Query("SELECT * FROM users")       // ← generates this at compile time:
    fun observeAll(): Flow<List<UserEntity>>
}
```

Room annotation processor pipeline:
```
Source code (@Entity, @Dao, @Database)
    │  KAPT/KSP processes annotations at build time
    ▼
Generated: AppDatabase_Impl.java
    ├── CREATE TABLE SQL embedded in code
    ├── UserDao_Impl with null checks and type mappings
    └── InvalidationTracker setup for Flow emissions
```
Any SQL error = build error, not runtime crash.

### First Principles: What Is Room?

Room is a compile-time-verified ORM (Object-Relational Mapper) that sits on top of SQLite. Instead of writing raw SQL everywhere, you write Kotlin interfaces and data classes, and Room generates the implementation.

The key advantage over raw SQLite: **compile-time SQL verification**. If your SQL query references a column that doesn't exist, it's a **build error**, not a runtime crash.

### What `@Entity` Compiles To

```kotlin
@Entity(tableName = "users")
data class UserEntity(
    @PrimaryKey val id: String,
    val name: String,
    val age: Int,
    @ColumnInfo(name = "email_address") val email: String
)
```

Room's annotation processor generates:
```sql
-- CREATE TABLE SQL generated at compile time:
CREATE TABLE IF NOT EXISTS `users` (
    `id` TEXT NOT NULL,
    `name` TEXT NOT NULL,
    `age` INTEGER NOT NULL,
    `email_address` TEXT NOT NULL,
    PRIMARY KEY(`id`)
)
```

This SQL is embedded in the generated `RoomDatabase` implementation and run when the database is first created.

### `@Transaction` — Atomic Guarantee

```kotlin
@Dao
interface OrderDao {
    @Insert
    suspend fun insertOrder(order: OrderEntity)

    @Insert
    suspend fun insertItems(items: List<OrderItemEntity>)

    @Transaction  // ← guarantees both inserts are atomic
    suspend fun insertOrderWithItems(order: OrderEntity, items: List<OrderItemEntity>) {
        insertOrder(order)
        insertItems(items)  // if this fails, insertOrder is rolled back!
    }
}
```

Without `@Transaction`, if `insertItems` fails after `insertOrder` succeeds, you'd have an order with no items — corrupted data. `@Transaction` wraps everything in a SQLite `BEGIN TRANSACTION ... COMMIT` block. Either both succeed or neither does.

Also used for `@Query` that returns relations:
```kotlin
@Transaction  // required when returning @Relation
@Query("SELECT * FROM users WHERE id = :userId")
suspend fun getUserWithOrders(userId: String): UserWithOrders
// Without @Transaction, multiple queries might see inconsistent intermediate state
```

### How Room's `Flow<List<T>>` Auto-Emits

Room uses an **invalidation tracker** to detect when a table has changed. [`Flow`](11_flow.md#q111--cold-vs-hot-streams) from Room auto-emits whenever the observed table is invalidated:

```
Room Invalidation Mechanism:
┌──────────────────────────────────────────────────────────────────┐
│  Any write to table "users" (insert, update, delete)            │
│         │                                                        │
│         ▼                                                        │
│  InvalidationTracker marks "users" table as dirty               │
│         │                                                        │
│         ▼                                                        │
│  All active Flow collectors for queries on "users"              │
│  receive "invalidated" signal                                   │
│         │                                                        │
│         ▼                                                        │
│  Each Flow re-executes its query                                │
│         │                                                        │
│         ▼                                                        │
│  New results emitted to collectors                              │
└──────────────────────────────────────────────────────────────────┘
```

```kotlin
@Dao
interface UserDao {
    @Query("SELECT * FROM users")
    fun observeAllUsers(): Flow<List<UserEntity>>
    // This Flow auto-emits whenever the "users" table changes
}

// Usage:
userDao.observeAllUsers()
    .map { it.toDomain() }
    .collect { users -> updateUI(users) }
// Every INSERT/UPDATE/DELETE to "users" triggers a new emission!
```

### `@Embedded` vs `@Relation`

**`@Embedded`:** Flattens a nested object's fields into the same table row:

```kotlin
data class Address(val street: String, val city: String)

@Entity
data class UserEntity(
    @PrimaryKey val id: String,
    val name: String,
    @Embedded val address: Address  // address fields added to users table
)
// Table: users(id, name, street, city)
```

**`@Relation`:** Fetches related entities from a SEPARATE table:

```kotlin
data class UserWithPosts(
    @Embedded val user: UserEntity,
    @Relation(
        parentColumn = "id",
        entityColumn = "user_id"
    )
    val posts: List<PostEntity>
)
// Executes: SELECT * FROM posts WHERE user_id = users.id
// Requires @Transaction to be consistent
```

### Room Migrations

```kotlin
// Room checks version on open. If db version != schema version → needs migration
@Database(entities = [UserEntity::class], version = 2)  // bumped from 1 to 2!
abstract class AppDatabase : RoomDatabase() {
    abstract fun userDao(): UserDao

    companion object {
        val MIGRATION_1_2 = object : Migration(1, 2) {
            override fun migrate(database: SupportSQLiteDatabase) {
                database.execSQL("ALTER TABLE users ADD COLUMN age INTEGER NOT NULL DEFAULT 0")
            }
        }
    }
}

// Provide migration when building:
Room.databaseBuilder(context, AppDatabase::class.java, "app.db")
    .addMigrations(AppDatabase.MIGRATION_1_2)
    .build()
```

If you bump the version WITHOUT providing a migration: **`IllegalStateException: A migration from 1 to 2 was required but not found.`** Room refuses to open the database to prevent data corruption.

**Fallback:** `.fallbackToDestructiveMigration()` — drops and recreates the database. Data lost. Only use during development.

### Memory Trick

```
Room query flow:
  @Query write  →  InvalidationTracker marks table dirty
                →  Flow re-executes query  →  new emission to UI

@Transaction mnemonic: "ALL or NOTHING"
  insertOrder() succeeds, insertItems() fails → WITHOUT @Transaction: corrupted state
  WITH @Transaction: SQLite rolls back insertOrder too — both fail together

@Embedded vs @Relation:
  @Embedded  = same table row (flat, no JOIN needed)
  @Relation  = separate table, triggers extra SELECT (requires @Transaction)

Migration version bump without script = IllegalStateException (Room refuses to open)
  "Room would rather crash than silently corrupt your data"
```

---

## Q14.2 — WorkManager

> **Builds on:** [Q16.2 — Background Work Evolution](16_android_system_internals.md#q162--background-work-evolution)
> **Connects to:** [Q10.4 — Lifecycle Scopes](10_structured_concurrency.md#q104--lifecycle-scopes-and-process-death)
> **Reference:** [Android Docs — Schedule tasks with WorkManager](https://developer.android.com/topic/libraries/architecture/workmanager)

### The Concrete Picture

Starting state — background work in a plain Service (Android 8+):
```
User opens app → starts Service → starts upload
User presses home (app goes to background)
    │
    └── Android 8+ Oreo: kills background service within ~60 seconds
            ← upload cancelled, no retry, user never knows
```

After WorkManager:
```
WorkManager.enqueue(uploadWork)
    │
    ├── Persists request to WorkManager's internal Room DB
    │       (survives process death, survives reboot)
    │
    ├── Registers with JobScheduler (API 23+)
    │       (OS-managed, battery-friendly, Doze-safe)
    │
    └── When constraints met (CONNECTED network):
            Worker.doWork() runs on background thread
            Result.success() → work removed from DB
            Result.retry()   → re-scheduled with backoff

Chain: CompressWorker ──► UploadWorker ──► NotifyWorker
  Output data from step N ──► becomes inputData for step N+1
```

### Why a `Service` Doesn't Guarantee Background Work

Android's `Service` runs on the main thread by default (you must create a thread yourself) and is subject to OS battery-saving policies:

- **Android 8+ (Oreo):** Background services killed within ~1 minute of the app going to background, unless the app is in the foreground
- **Doze mode:** Services may be deferred significantly
- Process death: Services can be killed by the OS at any time

### WorkManager's Guarantee

WorkManager guarantees execution even across:
- Process death
- Device reboot
- OS kill due to memory pressure
- Doze mode (work is deferred but not cancelled)

It achieves this by persisting work requests to a Room database and using the OS's battery-friendly scheduling APIs (JobScheduler on API 23+, AlarmManager + broadcast receiver as fallback).

```
WorkManager persistence:
Your work request → Room DB → JobScheduler (OS level)
                                    │
                                    ▼ (even after reboot)
                               Work runs in Worker (background thread)
```

### `OneTimeWorkRequest` vs `PeriodicWorkRequest`

```kotlin
// OneTimeWorkRequest — runs once:
val uploadWork = OneTimeWorkRequestBuilder<UploadWorker>()
    .setConstraints(Constraints.Builder()
        .setRequiredNetworkType(NetworkType.CONNECTED)
        .build())
    .setInputData(workDataOf("file_path" to "/storage/photo.jpg"))
    .build()
WorkManager.getInstance(context).enqueue(uploadWork)

// PeriodicWorkRequest — runs repeatedly:
val syncWork = PeriodicWorkRequestBuilder<SyncWorker>(
    repeatInterval = 15,  // minimum is 15 minutes!
    repeatIntervalTimeUnit = TimeUnit.MINUTES
).build()
WorkManager.getInstance(context).enqueueUniquePeriodicWork(
    "sync",
    ExistingPeriodicWorkPolicy.KEEP,  // keep existing if already enqueued
    syncWork
)
```

**Minimum period for `PeriodicWorkRequest`: 15 minutes** — Android enforces this to prevent battery drain.

### Chaining Workers

```kotlin
// Chain: compress → upload → notify
WorkManager.getInstance(context)
    .beginUniqueWork("upload_chain", ExistingWorkPolicy.REPLACE,
        OneTimeWorkRequestBuilder<CompressWorker>().build()
    )
    .then(OneTimeWorkRequestBuilder<UploadWorker>().build())
    .then(OneTimeWorkRequestBuilder<NotifyWorker>().build())
    .enqueue()

// then() guarantees: CompressWorker completes BEFORE UploadWorker starts
// Output data from CompressWorker becomes input data for UploadWorker:

class CompressWorker(ctx: Context, params: WorkerParameters) : CoroutineWorker(ctx, params) {
    override suspend fun doWork(): Result {
        val compressed = compressFile(inputData.getString("file_path")!!)
        return Result.success(workDataOf("compressed_path" to compressed))
    }
}

class UploadWorker(ctx: Context, params: WorkerParameters) : CoroutineWorker(ctx, params) {
    override suspend fun doWork(): Result {
        val path = inputData.getString("compressed_path")!!  // from CompressWorker
        upload(path)
        return Result.success()
    }
}
```

### `ExistingWorkPolicy` Variants

```kotlin
// REPLACE: cancel existing work, start new:
WorkManager.enqueueUniqueWork("sync", ExistingWorkPolicy.REPLACE, request)
// Use: user triggers manual refresh — cancel old sync, start fresh

// KEEP: if work already exists, keep it (ignore the new request):
WorkManager.enqueueUniqueWork("sync", ExistingWorkPolicy.KEEP, request)
// Use: ensure only one instance runs — don't restart if already running

// APPEND: add new work to run AFTER existing work:
WorkManager.enqueueUniqueWork("sync", ExistingWorkPolicy.APPEND, request)
// Use: sequential queue — don't run new work until old work finishes
```

### Memory Trick

```
WorkManager guarantee source:
  "Persisted to Room → JobScheduler → runs even after reboot"
  Service = RAM only; WorkManager = disk + OS scheduler

ExistingWorkPolicy:
  REPLACE  = cancel old, start fresh    (user-triggered manual refresh)
  KEEP     = ignore new, keep old       (deduplicate periodic sync)
  APPEND   = queue new after old        (ordered sequential tasks)

Minimum periodic interval = 15 minutes (Android enforces, cannot go lower)

CoroutineWorker vs Worker:
  CoroutineWorker.doWork() is suspend → can call suspend functions directly
  Worker.doWork() is blocking         → must use runBlocking (avoid in new code)
```

---

## Q14.3 — Paging 3

> **Builds on:** [Q11.2 — Flow Operators](11_flow.md#q112--flow-operators) · [Q14.1 — Room](14_jetpack_components.md#q141--room--internals)
> **Connects to:** [Q11.4 — Flow collection](11_flow.md#q114--flow-collection-and-lifecycle)
> **Reference:** [Android Docs — Paging 3 library](https://developer.android.com/topic/libraries/architecture/paging/v3-overview)

### The Concrete Picture

Starting state — manual pagination (what Paging 3 replaces):
```kotlin
var page = 1
fun loadMore() {
    viewModelScope.launch {
        val users = api.getUsers(page, pageSize = 20)
        _list.value = _list.value + users   // manual accumulation
        page++
        // Problems: no offline support, no Room integration,
        //           scroll position lost on rotation, no retry UI
    }
}
```

After Paging 3 with RemoteMediator (network + Room SSoT):
```
User scrolls to bottom
    │
    ▼
Pager detects "load more needed"
    │
    ▼
RemoteMediator.load(APPEND)
    │  api.getUsers(nextPage)          ← network fetch
    │  db.withTransaction {
    │      userDao.insertAll(users)    ← write to Room
    │      remoteKeyDao.insert(key)   ← store next page number
    │  }
    │
    ▼
Room InvalidationTracker fires
    │
    ▼
PagingSource (backed by Room) re-queries
    │
    ▼
PagingData emitted → LazyColumn / RecyclerView shows new items

Offline: RemoteMediator fails → Room still has existing pages → no blank screen
```

Cursor vs offset — the bug that cursor pagination eliminates:
```
Offset:  page 2 = "items 20-39"  →  but if item 5 was deleted, item 20 (old) = item 19 (new)
         → item 19 appears in BOTH page 1 and page 2 (duplicate)
Cursor:  page 2 = "items after id=XYZ"  →  stable ID, deletions don't shift positions
```

### `PagingSource` vs `RemoteMediator`

**`PagingSource`:** Defines HOW to load pages of data (from network OR local DB):

```kotlin
class UserPagingSource(private val api: UserApi) : PagingSource<Int, User>() {
    override suspend fun load(params: LoadParams<Int>): LoadResult<Int, User> {
        return try {
            val page = params.key ?: 1
            val response = api.getUsers(page = page, size = params.loadSize)
            LoadResult.Page(
                data = response.users,
                prevKey = if (page == 1) null else page - 1,
                nextKey = if (response.hasMore) page + 1 else null
            )
        } catch (e: Exception) {
            LoadResult.Error(e)
        }
    }

    override fun getRefreshKey(state: PagingState<Int, User>): Int? {
        return state.anchorPosition?.let { state.closestPageToPosition(it)?.prevKey?.plus(1) }
    }
}
```

**`RemoteMediator`:** Coordinates between network and local database. Network is the data source, Room is the local cache:

```kotlin
@OptIn(ExperimentalPagingApi::class)
class UserRemoteMediator(
    private val api: UserApi,
    private val db: AppDatabase
) : RemoteMediator<Int, UserEntity>() {
    override suspend fun load(
        loadType: LoadType,    // REFRESH, PREPEND, or APPEND
        state: PagingState<Int, UserEntity>
    ): MediatorResult {
        return try {
            val page = when (loadType) {
                LoadType.REFRESH -> 1   // start from beginning
                LoadType.PREPEND -> return MediatorResult.Success(endOfPaginationReached = true)
                LoadType.APPEND -> {
                    val remoteKey = db.remoteKeyDao().getLastKey()
                    remoteKey?.nextKey ?: return MediatorResult.Success(endOfPaginationReached = true)
                }
            }
            val response = api.getUsers(page, state.config.pageSize)
            db.withTransaction {
                if (loadType == LoadType.REFRESH) {
                    db.userDao().clearAll()          // clear stale data on refresh
                    db.remoteKeyDao().clearAll()
                }
                db.remoteKeyDao().insertKey(RemoteKey(nextKey = if (response.hasMore) page + 1 else null))
                db.userDao().insertAll(response.users.toEntity())
            }
            MediatorResult.Success(endOfPaginationReached = !response.hasMore)
        } catch (e: Exception) {
            MediatorResult.Error(e)
        }
    }
}
```

### Why Cursor-Based Pagination Beats Offset

**Offset-based problem:** "Give me items 10-20" → but if item 5 is deleted before this request, item 11 (now at position 10) appears twice (once in page 1, once in page 2).

```
Offset pagination data shifting bug:
Initial:    [A, B, C, D, E, F, G, H, I, J, ...]
Page 1:     [A, B, C, D, E]  (offset 0-4)
Delete B:   [A, C, D, E, F, G, H, I, J, ...]
Page 2:     [E, F, G, H, I]  (offset 5-9)
Bug: E appeared in BOTH page 1 and page 2!
```

**Cursor-based:** "Give me items after cursor X" → cursor is a stable identifier, not a position. Insertions/deletions don't shift positions.

```
Cursor pagination:
Page 1: cursor=null → [A, B, C, D, E], nextCursor = E.id
Delete B:   [A, C, D, E, F, G, H, ...]
Page 2: cursor=E.id → [F, G, H, I, J]  (starts after E — no duplicates!)
```

### `RemoteKey` Entities — Why They're Needed

`RemoteMediator` stores "what page to fetch next" for each item in a `RemoteKey` table. This is needed because:
- Room is the source of truth (UI reads from Room)
- Room doesn't know what "next page URL/number" is — that's network metadata
- `RemoteKey` bridges: "for the last item in Room, what is the next network page?"

```kotlin
@Entity(tableName = "remote_keys")
data class RemoteKey(
    @PrimaryKey val nextKey: Int?  // next page to load, null = end of list
)
```

### How Room Acts as Single Source of Truth in Paging 3

```
Flow:
Pager(pagingSourceFactory = { db.userDao().pagingSource() }, remoteMediator = userRemoteMediator)
  │
  │  UI reads from Room (PagingSource from DB)
  │  RemoteMediator handles loading from network → writes to Room
  │  Room's InvalidationTracker emits to UI when data changes
  ▼
UI always shows Room data; network seamlessly fills Room in background
```

---

## Q14.4 — Thread-Safe Caching

> **Builds on:** [Q7.3 — Collection pitfalls](07_collections_and_sequences.md#q73--common-collection-pitfalls) · [Q5.2 — lazy double-checked locking](05_properties_and_delegation.md#q52--lazy-internals)
> **Connects to:** [Q17.1 — Memory Leaks](17_performance_and_memory.md#q171--memory-leaks--top-5-causes)
> **Reference:** [Kotlin Docs — Shared mutable state and concurrency](https://kotlinlang.org/docs/shared-mutable-state-and-concurrency.html)

### `Mutex.withLock` vs `synchronized` — Key Difference

Both protect shared mutable state, but with different mechanics:

**`synchronized` (thread-blocking):**
```kotlin
val lock = Object()
synchronized(lock) {
    // Thread BLOCKS — OS parks the thread
    // The thread cannot do anything else while waiting
    doWork()
}
```

**`Mutex.withLock` (coroutine-aware suspension):**
```kotlin
val mutex = Mutex()
mutex.withLock {
    // Coroutine SUSPENDS — the thread is FREED for other coroutines!
    // Another coroutine can run on this thread while waiting for the lock
    doWork()
}
```

```
Thread behavior:
synchronized:   Thread ─[waiting]─[waiting]─[waiting]─[got lock]─[working]─►
                         ↑ thread is BLOCKED, wasting CPU scheduling slot

Mutex:          Thread ─[suspends, frees thread]───────────────[resumed]─[working]─►
                         ↑ thread does other coroutines' work while waiting
```

Use `Mutex` in coroutine code — `synchronized` in coroutines can deadlock on a single-threaded dispatcher.

### The `getOrLoad` Atomic Pattern

```kotlin
class ImageCache {
    private val mutex = Mutex()
    private val cache = mutableMapOf<String, Bitmap>()

    suspend fun getOrLoad(url: String): Bitmap {
        // WRONG: check then load — race condition!
        // if (cache.containsKey(url)) return cache[url]!!
        // cache[url] = loadImage(url)  // two coroutines might both reach here!

        // CORRECT: atomic check-and-load with mutex
        cache[url]?.let { return it }  // fast path: no lock if already cached

        return mutex.withLock {
            // Inside lock: check again (another coroutine may have loaded it)
            cache[url] ?: run {
                val bitmap = loadImage(url)
                cache[url] = bitmap
                bitmap
            }
        }
    }
}
```

**The race condition without mutex:**
```
Coroutine 1: check cache → miss
Coroutine 2: check cache → miss
Coroutine 1: loadImage(url) → result
Coroutine 2: loadImage(url) → result  ← DUPLICATE LOAD!
Both store result. Wasted work.
```

### `ConcurrentHashMap.computeIfAbsent` vs Coroutine Mutex

```kotlin
// ConcurrentHashMap.computeIfAbsent: thread-safe, but NOT coroutine-safe
val cache = ConcurrentHashMap<String, Bitmap>()
cache.computeIfAbsent(url) { loadImageBlocking(url) }  // blocking operation inside!
// This BLOCKS the thread — don't use blocking ops inside computeIfAbsent!

// Mutex: coroutine-safe, works with suspend functions:
val mutex = Mutex()
val cache = HashMap<String, Bitmap>()
mutex.withLock {
    cache.getOrPut(url) { loadImage(url) }  // can suspend here!
}
```

**When to use `ConcurrentHashMap.computeIfAbsent`:** Pure Kotlin/Java (no coroutines), thread-based concurrency, fast non-blocking computation.

**When to use `Mutex`:** Coroutine context, operation may suspend (network, DB), single-threaded dispatcher.

---

## Master Summary: Jetpack Components in 5 Points

```
┌────────────────────────────────────────────────────────────────────────┐
│  1. Room generates CREATE TABLE SQL from @Entity at compile time.     │
│     @Transaction wraps multiple operations atomically (BEGIN/COMMIT). │
│     Flow<List<T>> auto-emits via InvalidationTracker on any write.   │
│                                                                        │
│  2. WorkManager persists work to Room DB, survives process death +    │
│     reboot. PeriodicWork minimum: 15 minutes. Chain with .then().    │
│                                                                        │
│  3. PagingSource: how to load pages. RemoteMediator: coordinates      │
│     network + local DB (network writes to Room; UI reads Room).      │
│     RemoteKeys store "next page" metadata for the last loaded item.  │
│                                                                        │
│  4. Cursor pagination beats offset — no data shifting bugs.          │
│     Offset: item deletions shift positions → duplicates.             │
│     Cursor: stable ID reference → no position shifting.              │
│                                                                        │
│  5. Mutex.withLock suspends coroutine (frees thread) while waiting.  │
│     synchronized blocks the thread — wrong in coroutine context.     │
│     The double-check pattern (fast path + locked slow path) prevents │
│     duplicate loads.                                                  │
└────────────────────────────────────────────────────────────────────────┘
```

---

*← [Phase 13 — Android Architecture](13_android_architecture.md) | [Phase 15 — Networking →](15_networking.md)*
