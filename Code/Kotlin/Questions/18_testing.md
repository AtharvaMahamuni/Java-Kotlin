# Phase 18 — Testing Patterns for Android & Kotlin

Testing is the skill that separates engineers who ship confidently from engineers who ship and pray. In Android interviews, testing questions probe three things: do you know the test pyramid (what to test at each level), do you understand the tooling (Mockk, Turbine, Robolectric), and can you design code that is testable in the first place. The last point is the most important — testability is a design quality, not something you bolt on afterward.

> **Connects to:** [Kotlin 09 — Coroutines](09_coroutines_execution_mechanics.md) · [Kotlin 11 — Flow](11_flow.md) · [Kotlin 13 — Android Architecture](13_android_architecture.md) · [A5 — Jetpack Compose](../../Android/Questions/A5_jetpack_compose.md)

---

## Q18.1 — The Test Pyramid and What to Test Where

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

---

## Q18.2 — Mocks vs Fakes — The Critical Distinction

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

---

## Q18.3 — Mockk: The Kotlin-First Mocking Library

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

---

## Q18.4 — ViewModel Testing with Coroutines

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

---

## Q18.5 — Flow Testing with Turbine

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

---

## Q18.6 — Room DAO Testing

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

---

## Q18.7 — Hilt in Tests

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
