# Phase 18 — Testing Patterns for Android & Kotlin

Testing is the skill that separates engineers who ship confidently from engineers who ship and pray. In Android interviews, testing questions probe three things: do you know the test pyramid (what to test at each level), do you understand the tooling (Mockk, Turbine, Robolectric), and can you design code that is testable in the first place. The last point is the most important — testability is a design quality, not something you bolt on afterward.

> **Connects to:** [Kotlin 09 — Coroutines](09_coroutines_execution_mechanics.md) · [Kotlin 11 — Flow](11_flow.md) · [Kotlin 13 — Android Architecture](13_android_architecture.md) · [A5 — Jetpack Compose](../../Android/Questions/A5_jetpack_compose.md)

---

## Q18.1 — The Test Pyramid and What to Test Where

### The Concrete Picture

Starting state: A feature with UserViewModel → UserRepository → UserDao + UserApi. Where do you put tests?

```
COMPONENT MAP:
  UserApi       (Retrofit interface)
  UserDao       (Room DAO)
  UserRepository(UserApi, UserDao)     ← depends on network + database
  UserViewModel (UserRepository)       ← depends on repository only
  UserScreen    (Composable)           ← depends on ViewModel state

TEST PLACEMENT:
  UserViewModel ──────────────────────► Unit test (JUnit + Mockk/Fake repo)
    mock/fake UserRepository               runs on JVM, <1ms each
    runTest + advanceUntilIdle()

  UserRepository ─────────────────────► Integration test (MockWebServer + Room in-memory)
    real Room DAO against in-memory DB     runs on JVM or Robolectric, ~100ms
    real Retrofit against MockWebServer

  UserDao ─────────────────────────────► Integration test (Room in-memory + Robolectric)
    actual SQL queries verified            runs on JVM via Robolectric

  UserScreen (Compose UI) ─────────────► UI test (createComposeRule)
    pass UiState directly, verify nodes    runs on emulator/device or Robolectric

RULE: Most code at the BOTTOM (unit tests): fast, cheap, many
      Least code at the TOP (E2E/Espresso): slow, brittle, few
```

### WHY: Not All Tests Are Equal

```
                    ┌──────────────┐
                    │  E2E / UI    │  ← slow, brittle, expensive
                    │  Espresso    │     run rarely (CI only)
                    ├──────────────┤
                    │ Integration  │  ← medium speed, moderate fragility
                    │  Room, Hilt  │     test component boundaries
                    ├──────────────┤
                    │ Unit Tests   │  ← fast, reliable, cheap
                    │ JUnit, Mockk │     run on every commit
                    └──────────────┘
```

**Rule of thumb:** Most tests should be unit tests. Integration tests cover contract boundaries (DAO queries, Retrofit responses). UI tests catch user-visible regressions.

| Layer | Tests | Tools | When to run |
|-------|-------|-------|-------------|
| Unit | ViewModel, UseCase, Repository (faked), pure logic | JUnit5, Mockk, Turbine | Every commit, <1 min |
| Integration | Room DAO, Retrofit with mock server, Hilt modules | Room in-memory, MockWebServer | PR build |
| UI | User flows, navigation, Compose UI | Compose testing, Espresso | Nightly / before release |

### Memory Trick

```
PYRAMID (bottom to top = fast to slow, many to few):
  Unit        ──► JVM, <1ms, no Android framework, run on every commit
  Integration ──► JVM/Robolectric, ~100ms, real DB/network, run on PR
  UI/E2E      ──► device/emulator, ~minutes, run nightly or before release

TOOL MAP:
  ViewModel logic  → JUnit + Mockk/Fake + runTest
  Room DAO queries → Room.inMemoryDatabaseBuilder + Robolectric
  Retrofit calls   → MockWebServer (OkHttp)
  Compose UI       → createComposeRule + semantic node finders
  Full flows       → Espresso (avoid unless necessary)

ANTI-PATTERN: testing everything through UI tests
  = slow feedback, brittle (UI changes break tests), hard to debug
```

---

## Q18.2 — Mocks vs Fakes — The Critical Distinction

### The Concrete Picture

Starting state: You have `UserRepository` interface. You need it in a ViewModel test. Two choices.

```
interface UserRepository {
    suspend fun getUser(id: String): User
    suspend fun saveUser(user: User)
}

MOCK approach:
  val repo = mockk<UserRepository>()
  every { repo.getUser("123") } returns User("123", "Alice")
  │
  ├── repo.getUser("123") ──► returns Alice  (hard-coded per call)
  ├── repo.getUser("456") ──► NOT STUBBED → MissingStubException!
  └── repo.saveUser(user) ──► NOT STUBBED → crash unless relaxed = true

FAKE approach:
  class FakeUserRepository : UserRepository {
    private val users = mutableMapOf<String, User>()
    override suspend fun getUser(id: String) = users[id] ?: throw NotFoundException(id)
    override suspend fun saveUser(user: User) { users[user.id] = user }
  }
  │
  ├── fakeRepo.saveUser(alice)    ──► stored in memory map
  ├── fakeRepo.getUser("1")       ──► returns alice (real lookup)
  └── test sequence: save then get ──► works because state persists

WHEN MOCK beats FAKE:
  Verify analytics call:
    verify { analytics.track("purchase_complete", mapOf("sku" to "abc")) }
  You WANT to assert a specific method was called with specific args
  Fakes can't express "was this called?" without adding extra test-helper state
```

### WHY: This Is a Senior Interview Question

> **"What's the difference between a mock and a fake, and which do you prefer?"**

```
MOCK: a test double created by a framework (Mockk, Mockito) that records calls
      and lets you verify interactions.

FAKE: a hand-written, simplified but working implementation of an interface.

Repository interface:
interface UserRepository {
    suspend fun getUser(id: String): User
    suspend fun saveUser(user: User)
}

MOCK approach:
  val repo = mockk<UserRepository>()
  every { repo.getUser("123") } returns User("123", "Alice")

FAKE approach:
  class FakeUserRepository : UserRepository {
      private val users = mutableMapOf<String, User>()

      override suspend fun getUser(id: String): User =
          users[id] ?: throw NotFoundException(id)

      override suspend fun saveUser(user: User) {
          users[user.id] = user
      }
  }
```

**When to use a Fake:**
- The component has meaningful behavior (not just data retrieval)
- Multiple tests use different states of the same component
- You want to test interaction sequences (save then get)
- The test should verify behavior, not that specific methods were called

**When a Mock is appropriate:**
- Verifying that a method was called with specific arguments (analytics events, logging)
- Simple one-off stubs where a fake would add zero value
- Collaborators you control and are confident about (not third-party code)

**The `verify` smell:**
```kotlin
// BAD: test verifies HOW code works, not WHAT it does
verify { analyticsService.track("button_click") }

// GOOD for analytics: verify IS appropriate here — analytics is a side effect
// BAD for repositories: testing that repo.getUser() was called tells you nothing
//   about whether the ViewModel correctly handled the result
verify { userRepository.getUser(any()) }  // ← this test is useless
```

### Memory Trick

```
FAKE vs MOCK decision tree:
  Does the component have internal state? ──► YES → Fake
  Do multiple tests share different states? ──► YES → Fake
  Are you testing a sequence (save then get)? ──► YES → Fake
  Are you verifying a method WAS called (analytics)? ──► YES → Mock

"verify() smell":
  verify { repo.getUser(any()) }  ← proves nothing about ViewModel behavior
  verify { analytics.track(...) }  ← legitimate (side effect verification)

FAKE advantage:
  FakeUserRepository stores real data → test can do: save("Alice") then get()
  Mock can only return what you stub per-call → no shared state between calls

RULE: prefer Fakes for collaborators with behavior
      use Mocks only for side-effect verification
```

---

## Q18.3 — Mockk: The Kotlin-First Mocking Library

### The Concrete Picture

Starting state: `UserRepository` is an interface. `UserViewModel` depends on it. You use Mockk.

```
MOCKK VOCABULARY:
  mockk<T>()        ── creates a strict mock (all calls must be stubbed)
  mockk<T>(relaxed=true) ── creates a relaxed mock (returns defaults, no stubs needed)
  spyk(realObj)     ── wraps a real object (real methods run unless overridden)

STUBBING (set up return values BEFORE the test action):
  every { repo.getUserCount() } returns 42          ← non-suspend
  coEvery { repo.getUser("123") } returns alice     ← suspend function
  coEvery { repo.getUser("999") } throws NotFoundException("999")

VERIFICATION (assert calls happened AFTER the test action):
  coVerify { repo.saveUser(alice) }                 ← was this called?
  coVerify(exactly = 1) { repo.saveUser(any()) }    ← called exactly once?
  coVerify(exactly = 0) { repo.deleteUser(any()) }  ← never called

FLOW:
  coEvery { ... }  →  viewModel.doAction()  →  advanceUntilIdle()  →  coVerify / assertEquals

SPY use case:
  spyk(realRepo)  ──► calls real methods for all except:
  coEvery { spyRepo.getUser("special") } returns mockUser  ← overrides one path
```

### Basic Setup

```kotlin
// build.gradle
testImplementation("io.mockk:mockk:1.13.x")
```

```kotlin
class UserViewModelTest {
    private val repository = mockk<UserRepository>()
    private lateinit var viewModel: UserViewModel

    @BeforeEach
    fun setup() {
        viewModel = UserViewModel(repository)
    }
}
```

---

### Stubbing with `every` / `coEvery`

```kotlin
// Suspend functions: coEvery
coEvery { repository.getUser("123") } returns User("123", "Alice")
coEvery { repository.getUser("999") } throws NotFoundException("999")

// Non-suspend:
every { repository.getUserCount() } returns 42

// Argument matchers:
coEvery { repository.getUser(any()) } returns User("0", "Default")
coEvery { repository.getUser(match { it.startsWith("admin") }) } returns adminUser
```

---

### Verifying with `verify` / `coVerify`

```kotlin
// Verify a call happened
coVerify { repository.saveUser(expectedUser) }

// Verify call count
coVerify(exactly = 1) { repository.saveUser(any()) }
coVerify(exactly = 0) { repository.deleteUser(any()) }  // never called

// Verify order
coVerifyOrder {
    repository.getUser("123")
    repository.saveUser(any())
}
```

---

### Spies — Wrapping Real Objects

```kotlin
// spyk wraps a real object — real methods run unless stubbed
val realRepo = UserRepositoryImpl(db, api)
val spyRepo = spyk(realRepo)

coEvery { spyRepo.getUser("special") } returns mockUser  // override one method
// all other methods call through to the real implementation
```

---

### Relaxed Mocks — No Stubs Required

```kotlin
// Relaxed mock: returns defaults (0, false, empty string, null) without stubs
val repo = mockk<UserRepository>(relaxed = true)

// Useful for tests where you only care about one specific interaction
// and don't want to stub everything else
```

### Memory Trick

```
MOCKK FUNCTION NAME RULES:
  Non-suspend:  every { }   /  verify { }
  Suspend:      coEvery { } /  coVerify { }
  ("co" prefix = coroutine = suspend)

ARGUMENT MATCHERS:
  any()            ← matches anything
  match { it > 0 }← matches by predicate
  "literal"        ← exact string match
  capture(slot)    ← capture the argument into a CapturingSlot

STRICT vs RELAXED:
  mockk<T>()           → crash if unstubbed method called
  mockk<T>(relaxed=true) → return 0/false/""/null for unstubbed calls

VERIFY ORDER:
  coVerifyOrder { first(); second() }     ← first MUST be called before second
  coVerifySequence { first(); second() }  ← EXACTLY these calls in this order
```

---

## Q18.4 — ViewModel Testing with Coroutines

### The Concrete Picture

Starting state: `UserViewModel` calls `viewModelScope.launch { repository.getUser(...) }`. Test runs on JVM.

```
PROBLEM ON JVM:
  viewModelScope uses Dispatchers.Main → no Android Looper on JVM → crash/deadlock

FIX — two-part setup:

  PART 1: MainDispatcherRule (TestWatcher)
    @get:Rule val mainDispatcherRule = MainDispatcherRule()
    │
    ├── starting(): Dispatchers.setMain(StandardTestDispatcher())
    └── finished(): Dispatchers.resetMain()
    Now all Dispatchers.Main calls → StandardTestDispatcher (JVM-safe, virtual clock)

  PART 2: runTest + advanceUntilIdle
    runTest {
      // ARRANGE
      coEvery { repository.getUser("123") } returns User("123", "Alice")

      // ACT
      viewModel.loadUser("123")          ← coroutine is QUEUED (not yet run)

      advanceUntilIdle()                 ← drain queue: coroutine runs to completion

      // ASSERT
      assertEquals(
        UserUiState.Success(User("123", "Alice")),
        viewModel.uiState.value
      )
    }

WITHOUT advanceUntilIdle():
  viewModel.loadUser("123")
  // coroutine is queued but hasn't executed
  assertEquals(Success, ...)  ← FAILS: state is still Loading

StandardTestDispatcher vs UnconfinedTestDispatcher:
  Standard:    manual advancement → full control over timing
  Unconfined:  eager execution → simpler, no advanceUntilIdle() needed
```

### The Problem: Coroutines Need a Test Dispatcher

ViewModels launch coroutines on `viewModelScope`, which uses `Dispatchers.Main`. Tests run on a JVM with no Android main thread. Without a test dispatcher, coroutine tests either deadlock or behave non-deterministically.

```kotlin
// build.gradle
testImplementation("org.jetbrains.kotlinx:kotlinx-coroutines-test:x.x.x")
```

---

### `StandardTestDispatcher` — Explicit Time Control

```kotlin
@OptIn(ExperimentalCoroutinesApi::class)
class UserViewModelTest {

    @get:Rule
    val mainDispatcherRule = MainDispatcherRule()  // see below

    private val repository = mockk<UserRepository>()
    private lateinit var viewModel: UserViewModel

    @Test
    fun `loadUser success updates state to Success`() = runTest {
        // ARRANGE
        coEvery { repository.getUser("123") } returns User("123", "Alice")

        // ACT
        viewModel.loadUser("123")
        advanceUntilIdle()  // run all pending coroutines to completion

        // ASSERT
        assertEquals(
            UserUiState.Success(User("123", "Alice")),
            viewModel.uiState.value
        )
    }

    @Test
    fun `loadUser error updates state to Error`() = runTest {
        coEvery { repository.getUser(any()) } throws IOException("Network error")

        viewModel.loadUser("123")
        advanceUntilIdle()

        val state = viewModel.uiState.value
        assertTrue(state is UserUiState.Error)
        assertEquals("Network error", (state as UserUiState.Error).message)
    }
}

// Reusable rule to replace Dispatchers.Main with a test dispatcher
class MainDispatcherRule(
    val dispatcher: TestDispatcher = StandardTestDispatcher()
) : TestWatcher() {
    override fun starting(description: Description) {
        Dispatchers.setMain(dispatcher)
    }
    override fun finished(description: Description) {
        Dispatchers.resetMain()
    }
}
```

---

### `UnconfinedTestDispatcher` — Eager Execution

```kotlin
// StandardTestDispatcher: coroutines are queued, run only when you call
//   advanceUntilIdle() or advanceTimeBy()
// Use when: you need to control timing precisely

// UnconfinedTestDispatcher: coroutines run eagerly, without explicit advancement
// Use when: timing doesn't matter and you just want coroutines to complete

@Test
fun `with unconfined — no advanceUntilIdle needed`() = runTest(UnconfinedTestDispatcher()) {
    coEvery { repository.getUser("123") } returns User("123", "Alice")

    viewModel.loadUser("123")
    // No advanceUntilIdle() needed — coroutine ran eagerly

    assertEquals(UserUiState.Success(User("123", "Alice")), viewModel.uiState.value)
}
```

---

### Testing StateFlow Emissions

```kotlin
@Test
fun `stateFlow emits Loading then Success`() = runTest {
    coEvery { repository.getUser("123") } coAnswers {
        delay(100)  // simulate network delay
        User("123", "Alice")
    }

    val states = mutableListOf<UserUiState>()
    // Collect emissions in background
    val job = launch(UnconfinedTestDispatcher()) {
        viewModel.uiState.collect { states.add(it) }
    }

    viewModel.loadUser("123")
    advanceUntilIdle()
    job.cancel()

    assertEquals(
        listOf(UserUiState.Loading, UserUiState.Success(User("123", "Alice"))),
        states
    )
}
```

### Memory Trick

```
REQUIRED SETUP for ViewModel coroutine tests:
  1. testImplementation("org.jetbrains.kotlinx:kotlinx-coroutines-test:x.x.x")
  2. @get:Rule val mainDispatcherRule = MainDispatcherRule()
  3. wrap test body in runTest { }
  4. call advanceUntilIdle() after triggering the action

MainDispatcherRule replaces Dispatchers.Main → allows coroutines to run on JVM
runTest provides virtual clock (delay(5000) = instant, no real wait)
advanceUntilIdle() = "run everything that's pending now"

TIMING VARIANTS:
  advanceUntilIdle()      ← drain all pending, regardless of delay
  advanceTimeBy(1001)     ← advance virtual clock by 1001ms only
  runCurrent()            ← run only coroutines ready NOW (no time advance)

COLLECTING STATEFLOW EMISSIONS:
  launch(UnconfinedTestDispatcher()) { viewModel.uiState.collect { states.add(it) } }
  (Must use UnconfinedTestDispatcher on collector to get emissions eagerly)
```

---

## Q18.5 — Flow Testing with Turbine

### The Concrete Picture

Starting state: `UserViewModel.uiState: StateFlow<UserUiState>`. You need to assert it emits Loading then Success.

```
WITHOUT Turbine (manual approach — fragile):
  val states = mutableListOf<UserUiState>()
  val job = launch(UnconfinedTestDispatcher()) { viewModel.uiState.collect { states.add(it) } }
  viewModel.loadUser("123")
  advanceUntilIdle()
  job.cancel()
  assertEquals(listOf(Loading, Success(alice)), states)
  // Problems: easy to forget job.cancel(), easy to start collecting too late

WITH Turbine:
  viewModel.uiState.test {
    val initial = awaitItem()               ← suspends until StateFlow emits (initial state)
    assertEquals(UserUiState.Loading, initial)

    viewModel.loadUser("123")
    advanceUntilIdle()

    val result = awaitItem()                ← suspends until next emission
    assertEquals(UserUiState.Success(alice), result)

    cancelAndIgnoreRemainingEvents()        ← stop listening, ignore any buffered events
  }

TURBINE test { } block:
  → sets up a subscriber on the Flow
  → each awaitItem() suspends until the Flow emits, then returns the value
  → awaitComplete() asserts the Flow emitted a terminal event (onComplete)
  → expectNoEvents() asserts nothing emitted (useful for "no state change" tests)
  → Turbine enforces that you consume all emissions (fail-fast on unexpected emissions)
```

Turbine is a library that makes testing Flow emissions clean and readable.

```kotlin
// build.gradle
testImplementation("app.cash.turbine:turbine:x.x.x")
```

---

### Basic Turbine Usage

```kotlin
@Test
fun `userFlow emits user on load`() = runTest {
    coEvery { repository.getUser("123") } returns User("123", "Alice")

    viewModel.uiState.test {
        // awaitItem() waits for the next emission
        val loading = awaitItem()
        assertEquals(UserUiState.Loading, loading)

        viewModel.loadUser("123")

        val success = awaitItem()
        assertEquals(UserUiState.Success(User("123", "Alice")), success)

        // Verify no more emissions
        cancelAndIgnoreRemainingEvents()
    }
}
```

---

### Testing Room DAO with Turbine

```kotlin
@Test
fun `inserting user makes it observable in Flow`() = runTest {
    val user = User("1", "Alice")

    dao.observeUsers().test {
        // Initial emission — empty list
        assertEquals(emptyList<User>(), awaitItem())

        dao.insert(user)

        // Room emits updated list
        assertEquals(listOf(user), awaitItem())

        cancelAndIgnoreRemainingEvents()
    }
}
```

### Memory Trick

```
TURBINE API — 5 key functions:
  awaitItem()                      ← wait for next emission, return it
  awaitComplete()                  ← assert Flow called onComplete
  awaitError()                     ← assert Flow threw an exception
  expectNoEvents()                 ← assert nothing emitted right now
  cancelAndIgnoreRemainingEvents() ← stop test, discard buffered events

TURBINE vs manual mutableList approach:
  Manual: easy to forget job.cancel(), race between collect start and emit
  Turbine: structured, no races, enforces consuming events (unexpected = test fail)

STATEFLOW quirk with Turbine:
  StateFlow always has an initial value → awaitItem() returns initial state first
  So tests often: awaitItem() for initial, trigger action, awaitItem() for updated

Room DAO + Turbine:
  dao.observeUsers().test {
    assertEquals(emptyList(), awaitItem())  ← initial Room emission
    dao.insert(user)
    assertEquals(listOf(user), awaitItem())  ← Room emits updated list
  }
```

---

## Q18.6 — Room DAO Testing

### The Concrete Picture

Starting state: `UserDao` with `insert(user)` and `getUser(id): User?`. You need to verify the SQL query is correct.

```
REAL DATABASE (production):
  AppDatabase → SQLite file on disk → persists across runs
  Cannot use in tests: slow, side effects between tests, requires Android context

IN-MEMORY DATABASE (test):
  Room.inMemoryDatabaseBuilder(context, AppDatabase::class.java).build()
  → No file on disk
  → Auto-cleared when db.close() is called (or process ends)
  → Fast (no I/O wait)
  → Requires real Room SQL engine → catches actual query bugs

TEST SETUP PATTERN:
  @Before fun setup() {
    db = Room.inMemoryDatabaseBuilder(context, AppDatabase::class.java)
             .allowMainThreadQueries()  ← disable main-thread check for tests only
             .build()
    dao = db.userDao()
  }
  @After fun teardown() { db.close() }  ← releases in-memory DB, clears data

  @Test fun insertAndGet() = runTest {
    val alice = User("1", "Alice")
    dao.insert(alice)           ──► written to in-memory SQLite
    val result = dao.getUser("1")  ──► real SQL SELECT executed
    assertEquals(alice, result) ──► verifies query correctness
  }

WHY NOT mock the DAO?:
  Mocking dao.getUser("1") returns alice → tests nothing about SQL correctness
  In-memory DB tests the actual @Query annotation SQL → catches typos, wrong columns
```

### Use an In-Memory Database

```kotlin
@RunWith(AndroidJUnit4::class)  // needed even for local tests with Robolectric
class UserDaoTest {

    private lateinit var db: AppDatabase
    private lateinit var dao: UserDao

    @Before
    fun setup() {
        // In-memory: fast, no disk I/O, auto-cleared after test
        db = Room.inMemoryDatabaseBuilder(
            ApplicationProvider.getApplicationContext(),
            AppDatabase::class.java
        )
        .allowMainThreadQueries()  // for tests only — never in production
        .build()
        dao = db.userDao()
    }

    @After
    fun teardown() {
        db.close()
    }

    @Test
    fun insertAndRetrieve() = runTest {
        val user = User("1", "Alice")
        dao.insert(user)

        val result = dao.getUser("1")
        assertEquals(user, result)
    }

    @Test
    fun getUserNotFound_returnsNull() = runTest {
        val result = dao.getUser("nonexistent")
        assertNull(result)
    }
}
```

### Memory Trick

```
IN-MEMORY DB pattern (4 required pieces):
  1. Room.inMemoryDatabaseBuilder(context, AppDatabase::class.java).build()
  2. .allowMainThreadQueries() ← TESTS ONLY, never production
  3. @After db.close()         ← clears DB between tests
  4. @RunWith(AndroidJUnit4::class) or Robolectric for Context

REAL SQL TESTED = in-memory Room runs SQLite engine
  → catches @Query typos, missing columns, wrong JOIN conditions
  → mocking DAO skips all of this (tests nothing about SQL)

FLOW DAO + Turbine:
  dao.observeUsers() returns Flow<List<User>>
  Room emits on every DB change → test with Turbine:
    awaitItem() for empty → insert → awaitItem() for updated list

allowMainThreadQueries() explanation:
  Room normally throws exception on main-thread queries (prevents ANR)
  In tests: no real main thread, synchronous is fine → allow it
```

---

## Q18.7 — Hilt in Tests

### The Concrete Picture

Starting state: `NetworkModule` provides `UserApi` (real Retrofit). In tests, you want `FakeUserApi` instead.

```
PRODUCTION DI graph:
  NetworkModule ──provides──► UserApi (real Retrofit → hits network)
                                  │
                              UserRepository ──► UserViewModel

TEST DI graph (swap NetworkModule out):
  FakeNetworkModule ──provides──► FakeUserApi (in-memory, deterministic)
                                       │
                                   UserRepository ──► UserViewModel

MECHANISM — @TestInstallIn:
  @TestInstallIn(
    components = [SingletonComponent::class],
    replaces = [NetworkModule::class]    ← tells Hilt: during tests, use THIS instead
  )
  @Module
  object FakeNetworkModule {
    @Provides fun provideUserApi(): UserApi = FakeUserApi()
  }

TEST SETUP — @HiltAndroidTest:
  @HiltAndroidTest                        ← enables Hilt injection in this test
  class UserViewModelTest {
    @get:Rule(order = 0) val hiltRule = HiltAndroidRule(this)
    @get:Rule(order = 1) val mainDispatcherRule = MainDispatcherRule()

    @Inject lateinit var repository: UserRepository  ← Hilt injects FakeUserApi version

    @Before fun setup() { hiltRule.inject() }  ← triggers actual injection
  }

ORDERING: HiltAndroidRule (order=0) must run BEFORE MainDispatcherRule (order=1)
  because Hilt sets up the component graph that MainDispatcherRule might depend on
```

### Replace Real Dependencies with Test Doubles

```kotlin
// Production module
@Module
@InstallIn(SingletonComponent::class)
object NetworkModule {
    @Provides fun provideUserApi(): UserApi = Retrofit.Builder()...
}

// Test module — replaces NetworkModule
@TestInstallIn(components = [SingletonComponent::class], replaces = [NetworkModule::class])
@Module
object FakeNetworkModule {
    @Provides fun provideUserApi(): UserApi = FakeUserApi()
}
```

---

### Injecting ViewModels in Tests

```kotlin
@HiltAndroidTest
class UserViewModelTest {

    @get:Rule(order = 0) val hiltRule = HiltAndroidRule(this)
    @get:Rule(order = 1) val mainDispatcherRule = MainDispatcherRule()

    @Inject lateinit var repository: UserRepository  // injected by Hilt (using test module)

    private lateinit var viewModel: UserViewModel

    @Before
    fun setup() {
        hiltRule.inject()
        viewModel = UserViewModel(repository)
    }
}
```

### Memory Trick

```
HILT TEST ANNOTATION MAP:
  @HiltAndroidTest       ← marks test class as Hilt-enabled
  HiltAndroidRule        ← JUnit rule that builds the component graph
  @TestInstallIn(components=[...], replaces=[RealModule::class]) ← swap module
  @Inject                ← inject test double from Hilt component graph
  hiltRule.inject()      ← must call in @Before to trigger injection

KEY DISTINCTION:
  @TestInstallIn replaces entire module → all provides in that module are replaced
  Want to replace only ONE binding? → use @BindValue in test class

RULE ORDER matters:
  HiltAndroidRule(order=0) must be FIRST → builds the graph
  Other rules (order=1, order=2) can use the built graph

ALTERNATIVE without Hilt:
  Just construct ViewModel manually with fakes:
    val viewModel = UserViewModel(FakeUserRepository())
  Hilt in tests is only needed if ViewModel is also injected via Hilt
```

---

## Q18.8 — Robolectric vs Android Instrumentation

| | **Robolectric** | **Android Instrumentation** |
|--|--|--|
| Runs on | JVM (no emulator/device needed) | Real device or emulator |
| Speed | Fast (seconds) | Slow (minutes — needs to install APK) |
| Android APIs | Simulated (shadows) — some gaps | Real Android APIs |
| Use for | Unit tests needing Context, Resources, Room | E2E UI tests, camera, Bluetooth, precise rendering |
| Reliability | Very good for most framework code | Ground truth — what users actually see |

```kotlin
// Robolectric test — JVM, no device needed
@RunWith(RobolectricTestRunner::class)
class UserActivityTest {
    @Test
    fun activityCreates_withoutCrash() {
        val activity = Robolectric.buildActivity(UserActivity::class.java)
            .create()
            .resume()
            .get()
        assertNotNull(activity)
    }
}
```

---

## Q18.9 — Compose UI Testing

```kotlin
class UserScreenTest {

    @get:Rule
    val composeTestRule = createComposeRule()

    @Test
    fun userScreen_showsName_whenLoaded() {
        composeTestRule.setContent {
            UserScreen(uiState = UserUiState.Success(User("1", "Alice")))
        }

        // Finders
        composeTestRule.onNodeWithText("Alice").assertIsDisplayed()
        composeTestRule.onNodeWithContentDescription("Profile image").assertExists()

        // Actions
        composeTestRule.onNodeWithText("Edit").performClick()

        // Assertions
        composeTestRule.onNodeWithText("Edit Profile").assertIsDisplayed()
    }

    @Test
    fun userScreen_showsLoading_initially() {
        composeTestRule.setContent {
            UserScreen(uiState = UserUiState.Loading)
        }
        composeTestRule.onNodeWithTag("loading_indicator").assertIsDisplayed()
    }
}
```

**Semantic matchers:**
- `onNodeWithText("text")` — find by displayed text
- `onNodeWithContentDescription("desc")` — for accessibility/icons
- `onNodeWithTag("test_tag")` — add `Modifier.testTag("x")` to mark nodes
- `onAllNodesWithText("Item")` — multiple matching nodes

---

## Master Summary: Testing

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  PHASE 18 — TESTING MASTER SUMMARY                                          │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  1. PYRAMID: Unit (fast, many) > Integration (medium) > UI (slow, few)     │
│                                                                              │
│  2. FAKES > MOCKS for repositories and collaborators with real behavior.   │
│     Mocks are appropriate for verifying side effects (analytics, logging).  │
│     verify() on a repository is usually a test-implementation-detail smell. │
│                                                                              │
│  3. VIEWMODEL TESTING:                                                       │
│     MainDispatcherRule: replaces Dispatchers.Main with TestDispatcher.     │
│     StandardTestDispatcher + advanceUntilIdle(): precise time control.     │
│     UnconfinedTestDispatcher: eager execution, no time control needed.     │
│                                                                              │
│  4. FLOW TESTING: Turbine.test { awaitItem() } is the cleanest API.        │
│     Room DAOs: in-memory database, never use real disk in unit tests.      │
│                                                                              │
│  5. HILT: @TestInstallIn replaces production modules with test doubles.    │
│     @HiltAndroidTest for component-level injection in tests.               │
│                                                                              │
│  6. ROBOLECTRIC: fast JVM-based tests with simulated Android APIs.         │
│     Use for: Activity/Fragment creation, Context-dependent logic, Room.    │
│     Use real instrumentation only for UI rendering and hardware APIs.      │
│                                                                              │
│  7. COMPOSE: createComposeRule() + semantic node finders.                  │
│     Prefer state-hoisted, stateless composables — pass state directly.    │
│     Add Modifier.testTag() to make nodes findable without text coupling.  │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

**Interview Traps:**

> **"How do you test a ViewModel that uses coroutines?"**
> Replace `Dispatchers.Main` with a `TestDispatcher` via a `TestWatcher` rule. Use `runTest` as the test scope. Call `advanceUntilIdle()` to drain all pending coroutines before asserting. Collect StateFlow emissions into a list by launching a background collection job before triggering the action.

> **"Mock vs Fake — which is better for a Repository?"**
> Fake. A Fake is a real implementation that stores data in memory. It lets you test actual sequences (insert then query), verify the ViewModel handled the result correctly (not just that a method was called), and reuse across many tests in different states. Mocks are appropriate when testing that a specific method was called with specific arguments — e.g., verifying an analytics event fired.

> **"How do you test a Flow that emits multiple values?"**
> Use Turbine: `flow.test { val item = awaitItem() }`. Turbine suspends until each emission arrives and gives you a clean assertion API. The alternative (collecting into a mutable list with a background launch) works but is more fragile.

> **"What's wrong with `allowMainThreadQueries()` in production?"**
> Room normally forbids database queries on the main thread to prevent ANR. `allowMainThreadQueries()` disables this protection. In production, queries on the main thread block the UI. Only use it in tests where you need synchronous query results without managing coroutines.

---

*← [Phase 17 — Performance & Memory](17_performance_and_memory.md)*

**Cross-references:**
- Coroutine testing (runTest, TestDispatcher): [Kotlin 09 — Coroutines](09_coroutines_execution_mechanics.md)
- Flow testing (Turbine): [Kotlin 11 — Flow](11_flow.md)
- ViewModel state (what you're testing): [Kotlin 13 — Android Architecture](13_android_architecture.md)
- Hilt setup (what you're replacing): [Kotlin 14 — Jetpack Components](14_jetpack_components.md)
- Compose UI tests: [A5 — Jetpack Compose](../../Android/Questions/A5_jetpack_compose.md)
