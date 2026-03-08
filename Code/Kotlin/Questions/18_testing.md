# Phase 18 — Testing

> The test pyramid is not about coverage — it's about feedback speed. Unit tests catch bugs in milliseconds. Integration tests catch contract violations in seconds. UI tests catch regressions in minutes. The right test is the one at the lowest layer that can detect the bug you're looking for.

## Navigation

[← Phase 17 — Performance and Memory](17_performance_and_memory.md)

## Questions in This File

- [Q18.1 — The Test Pyramid](#q181--the-test-pyramid)
- [Q18.2 — Fakes vs Mocks](#q182--fakes-vs-mocks)
- [Q18.3 — Mockk](#q183--mockk)
- [Q18.4 — ViewModel Testing with Coroutines](#q184--viewmodel-testing-with-coroutines)
- [Q18.5 — Flow Testing with Turbine](#q185--flow-testing-with-turbine)
- [Q18.6 — Room DAO Testing](#q186--room-dao-testing)
- [Q18.7 — Hilt in Tests](#q187--hilt-in-tests)
- [Q18.8 — Robolectric vs Instrumentation](#q188--robolectric-vs-instrumentation)
- [Q18.9 — Compose UI Testing](#q189--compose-ui-testing)

---

# Q18.1 — The Test Pyramid

> **Builds on:** [Q13.1 (ViewModel testability)](13_android_architecture.md#q131--mvvm-and-unidirectional-data-flow)
> **Connects to:** [Q18.4 (ViewModel testing)](18_testing.md#q184--viewmodel-testing-with-coroutines) · [Q18.6 (Room DAO)](18_testing.md#q186--room-dao-testing)

---

## The Core Rule

```
Unit tests:       JVM, <1ms each. Many. Run on every commit.
Integration tests: JVM/Robolectric, ~100ms. Medium. Run on PR.
UI tests:          Device/emulator, ~minutes. Few. Run nightly.

Most bugs are caught cheapest at the lowest layer.
Push every test as low in the pyramid as it can go.
```

---

## Layer Map for a Typical Feature

```
LAYER → TEST TYPE
┌──────────────────────────────┐
│ UserScreen    → UI test      │
│               createComposeRule
├──────────────────────────────┤
│ UserViewModel → Unit test    │
│               JUnit + Mockk  │
├──────────────────────────────┤
│ UserRepository→ Integration  │
│               MockWebServer  │
├──────────────────────────────┤
│ UserDao       → Integration  │
│               Room in-memory │
└──────────────────────────────┘
```

---

## Cost Comparison

```
                   ┌──────────────┐
                   │   E2E / UI   │  slow, brittle, expensive
                   │   Espresso   │  run before release only
                   ├──────────────┤
                   │ Integration  │  medium speed
                   │ Room, Hilt   │  test contract boundaries
                   ├──────────────┤
                   │ Unit Tests   │  fast, cheap, reliable
                   │ JUnit, Mockk │  run on every commit
                   └──────────────┘
```

| Layer | Tools | Speed | Run when |
|---|---|---|---|
| Unit | JUnit5, Mockk, Turbine | <1ms | Every commit |
| Integration | Room in-memory, MockWebServer | ~100ms | PR build |
| UI/E2E | createComposeRule, Espresso | ~minutes | Nightly / pre-release |

---

## ## Traps

**Trap — Testing everything through UI tests:**

```
Symptom: 3-minute test suite on every commit.
Problem: UI tests find bugs, but slowly and brittlely.
Fix: push each test to the lowest layer that can detect the bug.
  "Is this a ViewModel logic bug?" → unit test, not UI test.
```

**Trap — Mocking the DAO instead of using in-memory Room:**

```kotlin
// WRONG — tests nothing about SQL correctness:
every { dao.getUser("1") } returns user
// If there's a typo in @Query annotation, this test still passes.

// CORRECT — real in-memory Room executes the real SQL:
Room.inMemoryDatabaseBuilder(context, AppDatabase::class.java).build()
// @Query typo → test fails → bug caught at unit test layer
```

---

## Memory Trick

```
PYRAMID rule: push tests DOWN to the lowest layer that can catch the bug.
  Logic bug in ViewModel → unit test (JVM, no Android).
  SQL bug in @Query → integration test (Room in-memory).
  User flow bug → UI test (last resort).

TOOL MAP:
  ViewModel logic   → JUnit + Mockk/Fake + runTest
  Room DAO queries  → Room.inMemoryDatabaseBuilder + Robolectric
  Retrofit calls    → MockWebServer
  Compose UI        → createComposeRule + semantic finders
  Full user flows   → Espresso (avoid unless necessary)
```

---

## Self-Test

1. You have a bug in a UseCase that combines two repositories. Which test layer do you use? What tools?
2. You have a typo in a Room `@Query` annotation. Will a Mockk-based DAO test catch it?
3. What is the rule for where a test should live in the pyramid?

---

# Q18.2 — Fakes vs Mocks

> **Builds on:** [Q13.2 (Repository interfaces)](13_android_architecture.md#q132--clean-architecture-layer-boundaries)
> **Connects to:** [Q18.3 (Mockk)](18_testing.md#q183--mockk) · [Q18.4 (ViewModel tests)](18_testing.md#q184--viewmodel-testing-with-coroutines)

---

## The Core Rule

```
Fake = hand-written working implementation (stores data, has real behavior).
Mock = framework-generated stub that records calls and returns what you configure.

Prefer Fakes for collaborators with behavior (repositories, DAOs).
Use Mocks for verifying side effects (analytics events, logging).
```

---

## Side by Side

```kotlin
interface UserRepository {
    suspend fun getUser(id: String): User
    suspend fun saveUser(user: User)
}

// MOCK approach:
val repo = mockk<UserRepository>()
every { repo.getUser("1") } returns User("1", "Alice")
// Limitation: can only return what you stub per call. No shared state.
// repo.saveUser(user) then repo.getUser(id) doesn't work — Mockk doesn't connect them.

// FAKE approach:
class FakeUserRepository : UserRepository {
    private val users = mutableMapOf<String, User>()

    override suspend fun getUser(id: String) = users[id] ?: throw NotFoundException(id)
    override suspend fun saveUser(user: User) { users[user.id] = user }

    // Test helper:
    fun seed(user: User) { users[user.id] = user }
}

// Fake enables sequence testing:
val repo = FakeUserRepository()
repo.saveUser(alice)              // state persists in the map
val result = repo.getUser("1")   // real lookup → works!
assertEquals(alice, result)
```

---

## When to Use Each

```
Use FAKE when:
  ✓ The component has internal state (stores data)
  ✓ Multiple tests use different states of the same component
  ✓ Testing interaction sequences (save then get, insert then observe)
  ✓ Reusing the same fake across many test cases

Use MOCK when:
  ✓ Verifying a side effect was triggered (analytics.track(), logger.log())
  ✓ Simple one-off stubs where behavior doesn't matter
  ✓ The collaborator has no state (stateless transformers)
```

---

## The `verify()` Smell

```kotlin
// BAD — tests HOW the code works, not WHAT it does:
coVerify { userRepository.getUser(any()) }
// This passes even if the ViewModel did the wrong thing with the result!

// GOOD — verify side effects that can't be observed otherwise:
coVerify { analytics.track("purchase_complete", mapOf("sku" to "abc")) }
// Analytics is a fire-and-forget side effect — verifying it is legitimate.
```

`verify` on a repository is a test-implementation-detail smell. It proves a method was called, not that the ViewModel handled the result correctly.

---

## Memory Trick

```
FAKE: working implementation, in-memory storage, real behavior.
MOCK: configured stubs + call recording.

FAKE > MOCK for repositories:
  Mock can't do: save("Alice") then get() → verify Alice returned
  Fake can: stores in map, real lookup

MOCK is appropriate for: side-effect verification (analytics, logging, metrics).

verify() smell: coVerify { repo.getUser(any()) }
  → passes even if ViewModel crashed after the call
  → proves nothing useful about business logic
```

---

## Self-Test

1. What is the difference between a Fake and a Mock?
2. Can you test a sequence (save then get) using a Mock? Using a Fake?
3. When is `coVerify { analytics.track(...) }` legitimate?
4. Your ViewModel calls `repo.getUser(id)`, maps the result, and updates `_state`. Write the test using a Fake. Would a Mock work equally well here?

---

# Q18.3 — Mockk

> **Builds on:** [Q18.2 (Fakes vs Mocks)](18_testing.md#q182--fakes-vs-mocks)
> **Connects to:** [Q18.4 (ViewModel testing)](18_testing.md#q184--viewmodel-testing-with-coroutines)

---

## The Core Rule

```
Non-suspend: every { } / verify { }
Suspend:     coEvery { } / coVerify { }
("co" prefix = coroutine)
```

---

## Setup

```kotlin
// build.gradle:
testImplementation("io.mockk:mockk:1.13.x")

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

## Stubbing

```kotlin
// Non-suspend:
every { repository.getUserCount() } returns 42

// Suspend:
coEvery { repository.getUser("123") } returns User("123", "Alice")
coEvery { repository.getUser("999") } throws NotFoundException("999")

// Argument matchers:
coEvery { repository.getUser(any()) } returns User("0", "Default")
coEvery { repository.getUser(match { it.startsWith("admin") }) } returns adminUser

// Capturing an argument:
val slot = slot<String>()
coEvery { repository.getUser(capture(slot)) } returns user
// After call: slot.captured == the actual argument passed
```

---

## Verifying

```kotlin
// Was it called?
coVerify { repository.saveUser(expectedUser) }

// Exactly once?
coVerify(exactly = 1) { repository.saveUser(any()) }

// Never called?
coVerify(exactly = 0) { repository.deleteUser(any()) }

// Order matters?
coVerifyOrder {
    repository.getUser("123")
    repository.saveUser(any())
}
```

---

## Strict vs Relaxed

```kotlin
// Strict (default) — crash if unstubbed method called:
val repo = mockk<UserRepository>()
repo.getUserCount()  // MissingStubException if not stubbed!

// Relaxed — return defaults (0, false, null, "") for unstubbed calls:
val repo = mockk<UserRepository>(relaxed = true)
repo.getUserCount()  // returns 0 without a stub
```

---

## Spies — Wrap a Real Object

```kotlin
val realRepo = UserRepositoryImpl(db, api)
val spyRepo = spyk(realRepo)

// Override one method, all others call through to real implementation:
coEvery { spyRepo.getUser("special") } returns mockUser
// spyRepo.saveUser() → calls the REAL saveUser()
```

---

## ## Traps

**Trap — Using `every` for a suspend function:**

```kotlin
// WRONG — suspend function needs coEvery:
every { repository.getUser("1") } returns user   // compiles but silently fails

// CORRECT:
coEvery { repository.getUser("1") } returns user
```

**Trap — Forgetting to call `clearMocks` between tests:**

```kotlin
// Shared mock state leaks between tests:
@AfterEach
fun teardown() {
    clearAllMocks()  // resets all stubs and recorded calls
}
```

---

## Memory Trick

```
MOCKK RULE: co prefix = coroutine = suspend function.
  every / verify         → non-suspend
  coEvery / coVerify     → suspend

ARGUMENT MATCHERS:
  any()            → match anything
  match { pred }   → match by predicate
  capture(slot)    → capture into CapturingSlot for later inspection

STRICT vs RELAXED:
  strict (default)      → MissingStubException on unstubbed call
  relaxed = true        → returns 0/false/""/null for unstubbed calls

SPY: real object + selective overrides. spyk(realObj).
```

---

## Self-Test

1. What is the difference between `every` and `coEvery`?
2. `coEvery { repo.getUser(any()) } returns user`. You later assert `slot.captured`. What does that do?
3. When would you use `spyk()` instead of `mockk()`?
4. What happens if you call an unstubbed method on a strict mock?

---

# Q18.4 — ViewModel Testing with Coroutines

> **Builds on:** [Q9.2 (Dispatchers)](09_coroutines_execution_mechanics.md#q92--coroutine-context-and-dispatchers) · [Q10.4 (viewModelScope)](10_structured_concurrency.md#q104--lifecycle-scopes-and-process-death)
> **Connects to:** [Q18.5 (Flow testing with Turbine)](18_testing.md#q185--flow-testing-with-turbine)

---

## The Core Rule

```
viewModelScope uses Dispatchers.Main.
Dispatchers.Main requires an Android Looper — doesn't exist on JVM.
Fix: replace Dispatchers.Main with a TestDispatcher via MainDispatcherRule.

StandardTestDispatcher: coroutines are queued, run only when advanced.
UnconfinedTestDispatcher: coroutines run eagerly, no manual advancement needed.
```

---

## The Problem on JVM

```kotlin
// ViewModel under test:
class UserViewModel(private val repo: UserRepository) : ViewModel() {
    fun loadUser(id: String) {
        viewModelScope.launch {          // uses Dispatchers.Main
            _state.value = repo.getUser(id)
        }
    }
}

// Test on JVM:
viewModel.loadUser("1")
assertEquals(Success, viewModel.state.value)  // FAILS — coroutine hasn't run yet!
// AND: Dispatchers.Main isn't set up → RuntimeException
```

---

## Two-Part Fix

**Part 1: `MainDispatcherRule`** — replace `Dispatchers.Main` with a test dispatcher:

```kotlin
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

**Part 2: `runTest` + `advanceUntilIdle`:**

```kotlin
@get:Rule val mainDispatcherRule = MainDispatcherRule()

@Test
fun `loadUser success emits Content state`() = runTest {
    // ARRANGE
    coEvery { repository.getUser("1") } returns User("1", "Alice")

    // ACT
    viewModel.loadUser("1")       // coroutine queued, NOT run yet

    advanceUntilIdle()            // drain all pending coroutines

    // ASSERT
    assertEquals(
        UserUiState.Content(User("1", "Alice")),
        viewModel.state.value
    )
}
```

---

## `StandardTestDispatcher` vs `UnconfinedTestDispatcher`

```
StandardTestDispatcher:
  action()            ← coroutine QUEUED ⏸
  advanceUntilIdle()  ← drain all pending
  assert(...)         ← now safe to check ✓

UnconfinedTestDispatcher:
  action()   ← coroutine runs EAGERLY ▶
  assert(...) ← safe immediately ✓
  (no advanceUntilIdle needed)
```

```kotlin
// StandardTestDispatcher (default):
//   Coroutines queued. Run only when you call advanceUntilIdle() / advanceTimeBy().
//   Use for: time-sensitive tests, testing intermediate states.

// UnconfinedTestDispatcher:
//   Coroutines run eagerly. No advancement needed.
//   Use for: simple tests where timing doesn't matter.

@Test
fun `with unconfined — no advanceUntilIdle needed`() = runTest(UnconfinedTestDispatcher()) {
    coEvery { repository.getUser("1") } returns User("1", "Alice")

    viewModel.loadUser("1")
    // No advanceUntilIdle() — coroutine ran eagerly

    assertEquals(UserUiState.Content(User("1", "Alice")), viewModel.state.value)
}
```

---

## Testing Loading → Success Transition

```kotlin
@Test
fun `loadUser emits Loading then Content`() = runTest {
    coEvery { repository.getUser("1") } coAnswers {
        delay(100)
        User("1", "Alice")
    }

    val states = mutableListOf<UserUiState>()
    val collectJob = launch(UnconfinedTestDispatcher()) {
        viewModel.state.collect { states.add(it) }
    }

    viewModel.loadUser("1")
    advanceUntilIdle()
    collectJob.cancel()

    assertEquals(
        listOf(UserUiState.Loading, UserUiState.Content(User("1", "Alice"))),
        states
    )
}
```

---

## ## Traps

**Trap — Asserting before `advanceUntilIdle()`:**

```kotlin
// WRONG — coroutine hasn't run yet:
viewModel.loadUser("1")
assertEquals(UserUiState.Content(...), viewModel.state.value)  // FAILS

// CORRECT:
viewModel.loadUser("1")
advanceUntilIdle()
assertEquals(UserUiState.Content(...), viewModel.state.value)  // passes
```

**Trap — Missing `MainDispatcherRule`:**

Without the rule, `viewModelScope.launch` tries to use `Dispatchers.Main` on JVM → `IllegalStateException: Module with the Main dispatcher had failed to initialize`.

---

## Memory Trick

```
REQUIRED SETUP (3 pieces):
  1. @get:Rule val mainDispatcherRule = MainDispatcherRule()
  2. wrap test in runTest { }
  3. call advanceUntilIdle() after triggering the action

MainDispatcherRule: swaps Dispatchers.Main for TestDispatcher (JVM-safe, virtual clock).
runTest: virtual clock (delay(5000) = instant, no real wait).
advanceUntilIdle(): "drain and run everything pending right now".

TIMING VARIANTS:
  advanceUntilIdle()    ← run all pending (regardless of delay)
  advanceTimeBy(1001)   ← advance virtual clock by 1001ms
  runCurrent()          ← run only coroutines ready NOW

Standard: manual control. Unconfined: eager execution (simpler tests).
```

---

## Self-Test

1. Why does `viewModelScope.launch` fail on JVM without a test dispatcher?
2. What does `MainDispatcherRule` do? Write the implementation from memory.
3. You call `viewModel.loadUser("1")` in `runTest`. Is the coroutine guaranteed to have run by the next line? How do you ensure it has?
4. When would you choose `UnconfinedTestDispatcher` over `StandardTestDispatcher`?
5. `runTest` contains `delay(5000)`. Does the test actually wait 5 real seconds?

---

# Q18.5 — Flow Testing with Turbine

> **Builds on:** [Q11.3 (StateFlow)](11_flow.md#q113--stateflow-vs-sharedflow) · [Q18.4 (ViewModel testing)](18_testing.md#q184--viewmodel-testing-with-coroutines)
> **Connects to:** [Q18.6 (Room DAO Flow testing)](18_testing.md#q186--room-dao-testing)

---

## The Core Rule

```
flow.test { awaitItem() } — Turbine's way to assert Flow emissions cleanly.
awaitItem() suspends until the next emission arrives. Fails if flow completes first.
StateFlow always has an initial value → awaitItem() returns that first.
```

---

```
Turbine flow.test { } block:
  ┌─────────────────────────────┐
  │ awaitItem()  → Loading      │ ← initial
  │ triggerAction()             │
  │ advanceUntilIdle()          │
  │ awaitItem()  → Content(x)  │ ← result
  │ cancelAndIgnoreRemaining()  │
  └─────────────────────────────┘
StateFlow ALWAYS emits initial value
first → consume it before asserting!
```

## The Problem Without Turbine

```kotlin
// Manual approach — fragile:
val states = mutableListOf<UserUiState>()
val job = launch(UnconfinedTestDispatcher()) {
    viewModel.state.collect { states.add(it) }
}
viewModel.loadUser("1")
advanceUntilIdle()
job.cancel()
assertEquals(listOf(Loading, Content(alice)), states)
// Problems: easy to start collecting after the emission, easy to forget job.cancel()
```

---

## Turbine API

```kotlin
// build.gradle:
testImplementation("app.cash.turbine:turbine:x.x.x")

@Test
fun `loadUser emits Loading then Content`() = runTest {
    coEvery { repository.getUser("1") } returns User("1", "Alice")

    viewModel.state.test {
        // StateFlow initial value:
        assertEquals(UserUiState.Loading, awaitItem())

        viewModel.loadUser("1")
        advanceUntilIdle()

        // After load completes:
        assertEquals(UserUiState.Content(User("1", "Alice")), awaitItem())

        cancelAndIgnoreRemainingEvents()   // stop, discard buffered events
    }
}
```

---

## Turbine API Reference

```
awaitItem()                      ← wait for next emission, return it
awaitComplete()                  ← assert flow completed (onComplete)
awaitError()                     ← assert flow threw an exception
expectNoEvents()                 ← assert nothing emitted right now
cancelAndIgnoreRemainingEvents() ← stop collecting, ignore buffered events
```

---

## Testing Room DAO Flow with Turbine

```kotlin
@Test
fun `inserting user emits updated list`() = runTest {
    dao.observeUsers().test {
        assertEquals(emptyList(), awaitItem())   // initial Room emission (empty)

        dao.insert(User("1", "Alice"))

        assertEquals(listOf(User("1", "Alice")), awaitItem())   // Room emits after write

        cancelAndIgnoreRemainingEvents()
    }
}
```

---

## ## Traps

**Trap — Forgetting StateFlow's initial value:**

```kotlin
// WRONG — expects Content first, but StateFlow emits Loading initially:
viewModel.state.test {
    assertEquals(UserUiState.Content(alice), awaitItem())  // FAILS — Loading was first!
}

// CORRECT — consume initial state first:
viewModel.state.test {
    awaitItem()  // consume Loading (or whatever initial state is)
    viewModel.loadUser("1")
    advanceUntilIdle()
    assertEquals(UserUiState.Content(alice), awaitItem())
}
```

**Trap — Using `expectNoEvents()` when events are buffered:**

```kotlin
// WRONG — Turbine fails if an event arrives when you expected none:
viewModel.doSomething()
viewModel.state.test {
    expectNoEvents()  // FAILS if doSomething() triggered an emission
}

// CORRECT — use cancelAndIgnoreRemainingEvents() if you don't care about remaining:
viewModel.state.test {
    val item = awaitItem()
    // ... assert on item
    cancelAndIgnoreRemainingEvents()
}
```

---

## Memory Trick

```
TURBINE 5 functions:
  awaitItem()                      ← wait for and return next emission
  awaitComplete()                  ← assert onComplete
  awaitError()                     ← assert exception
  expectNoEvents()                 ← assert nothing emitted
  cancelAndIgnoreRemainingEvents() ← stop, discard rest

StateFlow quirk: always has initial value → awaitItem() returns it first.
  Pattern: awaitItem() to consume initial → trigger action → awaitItem() for result.

Turbine vs manual list:
  Manual: race between collection start and emission, easy to forget job.cancel().
  Turbine: structured, no races, unexpected emission = test failure (fail-fast).
```

---

## Self-Test

1. Write a test for a ViewModel that emits `Loading` then `Content(alice)` using Turbine.
2. Why does `awaitItem()` return the initial state first for a `StateFlow`?
3. What happens in Turbine if the Flow emits an unexpected event that you didn't `awaitItem()` for?
4. What does `cancelAndIgnoreRemainingEvents()` do? When do you use it instead of `awaitComplete()`?

---

# Q18.6 — Room DAO Testing

> **Builds on:** [Q14.1 (Room internals)](14_jetpack_components.md#q141--room-internals) · [Q18.5 (Turbine)](18_testing.md#q185--flow-testing-with-turbine)
> **Connects to:** [Q18.8 (Robolectric)](18_testing.md#q188--robolectric-vs-instrumentation)

---

## The Core Rule

```
Use Room.inMemoryDatabaseBuilder() for DAO tests.
Real Room SQL engine runs against in-memory SQLite.
@Query typos → test fails at SQL execution, not at parse time.
Mocking the DAO tests nothing about the SQL.
```

---

## Test Pattern

```kotlin
@RunWith(AndroidJUnit4::class)   // needed for ApplicationProvider.getApplicationContext()
class UserDaoTest {

    private lateinit var db: AppDatabase
    private lateinit var dao: UserDao

    @Before
    fun setup() {
        db = Room.inMemoryDatabaseBuilder(
            ApplicationProvider.getApplicationContext(),
            AppDatabase::class.java
        )
        .allowMainThreadQueries()   // tests only — never production
        .build()
        dao = db.userDao()
    }

    @After
    fun teardown() {
        db.close()   // releases in-memory DB, clears all data between tests
    }

    @Test
    fun insertAndRetrieve() = runTest {
        val user = User("1", "Alice")
        dao.insert(user)
        assertEquals(user, dao.getUser("1"))
    }

    @Test
    fun getUser_notFound_returnsNull() = runTest {
        assertNull(dao.getUser("nonexistent"))
    }
}
```

---

## Why In-Memory Over Mocking

```kotlin
// MOCK — tests nothing about SQL:
coEvery { dao.getUser("1") } returns user
// If @Query("SELECT * FROM usrs WHERE id = :id") has a typo → mock still returns user → bug not caught

// IN-MEMORY ROOM — tests the actual SQL:
dao.insert(user)
assertEquals(user, dao.getUser("1"))
// @Query typo → SQLiteException at test time → bug caught before production
```

---

## Testing Flow DAO with Turbine

```kotlin
@Test
fun `insert triggers Flow emission`() = runTest {
    dao.observeUsers().test {
        assertEquals(emptyList(), awaitItem())   // initial empty emission

        dao.insert(User("1", "Alice"))

        assertEquals(listOf(User("1", "Alice")), awaitItem())  // Room emits after write

        cancelAndIgnoreRemainingEvents()
    }
}
```

---

## `allowMainThreadQueries()` — Why Tests Need It

Room prevents database access on the main thread in production (throws `IllegalStateException`). Tests use `allowMainThreadQueries()` to bypass this — in test environments there's no real UI thread risk and synchronous queries simplify test code.

**Never use in production code.** Queries on the main thread → ANR risk.

---

## ## Traps

**Trap — Not closing the database between tests:**

```kotlin
// WRONG — in-memory DB carries state between tests:
// Test 1 inserts "Alice", Test 2 expects empty → FAILS because "Alice" is still there

// CORRECT — close in @After:
@After fun teardown() { db.close() }  // new DB built fresh in next @Before
```

**Trap — Using the real `AppDatabase` instead of in-memory:**

```kotlin
// WRONG — writes to a real file:
Room.databaseBuilder(context, AppDatabase::class.java, "test.db").build()
// Persists between test runs, slow, hard to clean up

// CORRECT:
Room.inMemoryDatabaseBuilder(context, AppDatabase::class.java).build()
```

---

## Memory Trick

```
IN-MEMORY ROOM pattern (4 pieces):
  1. Room.inMemoryDatabaseBuilder(context, AppDatabase::class.java).build()
  2. .allowMainThreadQueries()  ← tests only
  3. @After db.close()          ← fresh DB for each test
  4. @RunWith(AndroidJUnit4::class) for ApplicationProvider context

Why not mock DAO?
  Mocking skips SQL execution → @Query bugs invisible.
  In-memory Room runs real SQLite → catches every query mistake.

allowMainThreadQueries(): removes the main-thread guard.
  Production: guards against ANR.
  Tests: no real UI thread, synchronous queries needed.
```

---

## Self-Test

1. Why is mocking the DAO insufficient for verifying `@Query` annotations?
2. What does `allowMainThreadQueries()` disable? Why is it acceptable in tests?
3. What happens to the in-memory database data when you call `db.close()`?
4. Write a test that verifies deleting a user removes it from a subsequent `getAll()` call.

---

# Q18.7 — Hilt in Tests

> **Builds on:** [Q13.5 (Hilt internals)](13_android_architecture.md#q135--dependency-injection--hilt)
> **Connects to:** [Q18.4 (ViewModel testing)](18_testing.md#q184--viewmodel-testing-with-coroutines)

---

## The Core Rule

```
@TestInstallIn(components=[...], replaces=[RealModule::class])
  Swaps an entire production module for a test module.

@HiltAndroidTest: marks the test class as Hilt-enabled.
HiltAndroidRule: JUnit rule that builds the component graph.
hiltRule.inject(): triggers @Inject field injection in the test class.
```

---

## Swapping a Module

```kotlin
// Production module:
@Module @InstallIn(SingletonComponent::class)
object NetworkModule {
    @Provides fun provideUserApi(): UserApi = Retrofit.Builder()...build().create(UserApi::class.java)
}

// Test module — replaces NetworkModule entirely:
@TestInstallIn(components = [SingletonComponent::class], replaces = [NetworkModule::class])
@Module
object FakeNetworkModule {
    @Provides fun provideUserApi(): UserApi = FakeUserApi()
}
// Every component in SingletonComponent that needs UserApi gets FakeUserApi instead.
```

---

## Test Setup

```kotlin
@HiltAndroidTest
class UserViewModelTest {

    @get:Rule(order = 0) val hiltRule = HiltAndroidRule(this)
    @get:Rule(order = 1) val mainDispatcherRule = MainDispatcherRule()

    @Inject lateinit var repository: UserRepository   // Hilt injects the test version

    private lateinit var viewModel: UserViewModel

    @Before
    fun setup() {
        hiltRule.inject()                             // must call before using @Inject fields
        viewModel = UserViewModel(repository)
    }
}
```

**Rule order matters:** `HiltAndroidRule` (order=0) must run before any rule that depends on the built graph.

---

## `@TestInstallIn` vs `@BindValue`

```kotlin
// @TestInstallIn: replaces an entire module (all its @Provides):
@TestInstallIn(components=[...], replaces=[NetworkModule::class])
object FakeNetworkModule { ... }

// @BindValue: replaces a single binding directly in the test class:
@HiltAndroidTest
class MyTest {
    @BindValue @JvmField
    val userApi: UserApi = FakeUserApi()   // replaces only UserApi binding
}
```

`@BindValue` is simpler when you only need to replace one binding rather than a full module.

---

## ## Traps

**Trap — Calling `@Inject` fields before `hiltRule.inject()`:**

```kotlin
// WRONG — field is null before inject() is called:
@Before
fun setup() {
    viewModel = UserViewModel(repository)  // repository is null! hiltRule.inject() not called yet
    hiltRule.inject()
}

// CORRECT:
@Before
fun setup() {
    hiltRule.inject()                      // inject first
    viewModel = UserViewModel(repository)  // now repository is injected
}
```

**Trap — Wrong rule order:**

```kotlin
// WRONG — Hilt graph not built when MainDispatcherRule tries to run:
@get:Rule(order = 0) val mainDispatcherRule = MainDispatcherRule()
@get:Rule(order = 1) val hiltRule = HiltAndroidRule(this)

// CORRECT — Hilt first:
@get:Rule(order = 0) val hiltRule = HiltAndroidRule(this)
@get:Rule(order = 1) val mainDispatcherRule = MainDispatcherRule()
```

---

## Memory Trick

```
HILT TEST CHECKLIST:
  1. @HiltAndroidTest on test class
  2. @get:Rule(order=0) val hiltRule = HiltAndroidRule(this)
  3. @Inject lateinit var dep: Dependency
  4. hiltRule.inject() in @Before (before using @Inject fields)
  5. @TestInstallIn to replace production module

@TestInstallIn: replaces entire module → all @Provides in it.
@BindValue:     replaces single binding → simpler for one-off swaps.

Rule order: HiltAndroidRule first (order=0). Others after.
```

---

## Self-Test

1. What does `@TestInstallIn(replaces=[NetworkModule::class])` do?
2. What happens if you access an `@Inject` field before calling `hiltRule.inject()`?
3. What is the difference between `@TestInstallIn` and `@BindValue`? When would you choose each?

---

# Q18.8 — Robolectric vs Instrumentation

> **Connects to:** [Q18.6 (Room DAO)](18_testing.md#q186--room-dao-testing) · [Q18.9 (Compose UI testing)](18_testing.md#q189--compose-ui-testing)

---

## The Core Rule

```
Robolectric: simulates Android APIs on the JVM. Fast. No emulator.
Instrumentation: real Android APIs on device/emulator. Slow. Ground truth.
```

---

## Comparison Table

| | Robolectric | Android Instrumentation |
|---|---|---|
| Runs on | JVM (no device needed) | Real device or emulator |
| Speed | Fast (seconds) | Slow (minutes) |
| Android APIs | Simulated (shadows — some gaps) | Real Android APIs |
| Use for | Context, Resources, Room, View logic | Camera, Bluetooth, precise rendering, E2E |
| Reliability | Very good for most framework code | Ground truth — what users see |

---

## When to Use Each

```
Use ROBOLECTRIC for:
  ✓ Room DAO tests (needs Context for database builder)
  ✓ Activity/Fragment creation without full UI
  ✓ Resource loading (strings, drawables)
  ✓ Anything that needs Android Context but not hardware

Use INSTRUMENTATION for:
  ✓ User-visible rendering (pixel-accurate assertions)
  ✓ Hardware APIs (Camera, Bluetooth, GPS)
  ✓ Espresso user flows (tap, scroll, navigate)
  ✓ Testing predictive back gesture, system UI interaction
```

---

## Basic Robolectric Test

```kotlin
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

## Memory Trick

```
Robolectric = JVM + shadow objects simulating Android.
  Fast, no device, some API gaps.
  Use for: Room (needs Context), Activity creation, resource access.

Instrumentation = real Android on device.
  Slow, accurate, needed for: Espresso, camera, pixel-perfect UI.

Rule: default to Robolectric. Only go to instrumentation when Robolectric can't.
```

---

# Q18.9 — Compose UI Testing

> **Connects to:** [Q18.4 (ViewModel testing)](18_testing.md#q184--viewmodel-testing-with-coroutines)

---

## The Core Rule

```
createComposeRule() → sets up a composable under test.
Finders: onNodeWithText, onNodeWithContentDescription, onNodeWithTag.
Actions: performClick, performTextInput, performScrollTo.
Assertions: assertIsDisplayed, assertExists, assertIsEnabled.

Prefer stateless composables that receive UiState directly —
avoids needing a real ViewModel in UI tests.
```

---

## Basic Setup

```kotlin
class UserScreenTest {

    @get:Rule val composeTestRule = createComposeRule()

    @Test
    fun `content state shows user name`() {
        composeTestRule.setContent {
            UserScreen(uiState = UserUiState.Content(User("1", "Alice")))
        }

        composeTestRule.onNodeWithText("Alice").assertIsDisplayed()
    }

    @Test
    fun `loading state shows progress indicator`() {
        composeTestRule.setContent {
            UserScreen(uiState = UserUiState.Loading)
        }

        composeTestRule.onNodeWithTag("loading_indicator").assertIsDisplayed()
    }

    @Test
    fun `edit button click triggers callback`() {
        var editClicked = false
        composeTestRule.setContent {
            UserScreen(
                uiState = UserUiState.Content(User("1", "Alice")),
                onEditClick = { editClicked = true }
            )
        }

        composeTestRule.onNodeWithText("Edit").performClick()
        assertTrue(editClicked)
    }
}
```

---

## Semantic Finders Reference

```kotlin
// By text:
onNodeWithText("Alice")
onAllNodesWithText("Item")   // multiple nodes

// By content description (for icons, images):
onNodeWithContentDescription("Profile image")

// By test tag (most stable — add Modifier.testTag("x") to composable):
onNodeWithTag("loading_indicator")

// By role:
onNode(hasRole(Role.Button))
```

---

## `Modifier.testTag()` — The Stable Finder

Text changes when copy changes. Content descriptions change when designs change. `testTag` is a stable identifier that survives both.

```kotlin
// In Composable:
CircularProgressIndicator(
    modifier = Modifier.testTag("loading_indicator")
)

// In test:
composeTestRule.onNodeWithTag("loading_indicator").assertIsDisplayed()
```

---

## ## Traps

**Trap — Testing with a real ViewModel (creates coroutine dependency):**

```kotlin
// WRONG — test now depends on coroutines, Hilt, TestDispatcher setup:
composeTestRule.setContent {
    val vm: UserViewModel = viewModel()   // needs Hilt, TestDispatcher
    UserScreen(vm = vm)
}

// CORRECT — pass UiState directly (stateless composable):
composeTestRule.setContent {
    UserScreen(uiState = UserUiState.Content(alice))   // no VM needed
}
```

**Trap — Asserting before Compose has rendered:**

```kotlin
// Compose rendering is asynchronous after setContent.
// Use: composeTestRule.waitForIdle() if needed before asserting.
composeTestRule.setContent { SlowComposable() }
composeTestRule.waitForIdle()
composeTestRule.onNodeWithText("Done").assertIsDisplayed()
```

---

## Memory Trick

```
COMPOSE TEST RULE: createComposeRule() (no Activity needed).

FINDERS (most stable → least stable):
  testTag   → most stable (explicit, never changes with copy/design)
  contentDescription → medium (changes with design)
  text      → least stable (changes with copy/i18n)

PREFER stateless composables: UserScreen(uiState = ...) → no ViewModel in UI test.

ACTIONS: performClick(), performTextInput("abc"), performScrollTo().
ASSERTIONS: assertIsDisplayed(), assertExists(), assertIsEnabled(), assertIsNotEnabled().
```

---

## Self-Test

1. Why is `onNodeWithTag("x")` a more stable finder than `onNodeWithText("Submit")`?
2. What is the advantage of testing a stateless composable with `UiState` directly vs using a real ViewModel?
3. After `composeTestRule.setContent { }`, when can you immediately assert on nodes?

---

## Phase 18 — Summary

```
┌────────────────────────────────────────────────────────────────────────┐
│  1. Pyramid: Unit (JVM, <1ms) > Integration (~100ms) > UI (minutes). │
│     Push tests to the lowest layer that can catch the bug.           │
│                                                                        │
│  2. Fakes > Mocks for stateful collaborators (repositories, DAOs).   │
│     Mocks are appropriate for side-effect verification (analytics).  │
│     verify(repo.getUser()) is a test-implementation smell.           │
│                                                                        │
│  3. ViewModel tests need MainDispatcherRule + runTest.               │
│     Standard: coroutines queue, need advanceUntilIdle().             │
│     Unconfined: eager execution, simpler tests.                      │
│                                                                        │
│  4. Turbine: flow.test { awaitItem() } — structured, no races.      │
│     StateFlow emits initial value first → consume it with awaitItem. │
│                                                                        │
│  5. Room DAO: in-memory builder + allowMainThreadQueries() + close() │
│     in @After. In-memory runs real SQL → catches @Query bugs.        │
│                                                                        │
│  6. Hilt tests: @HiltAndroidTest + HiltAndroidRule(order=0) +       │
│     @TestInstallIn to swap modules. hiltRule.inject() before @Inject │
│     fields are used.                                                  │
│                                                                        │
│  7. Robolectric: JVM + simulated Android, fast. Use for Context,    │
│     Room, Activity creation. Instrumentation for hardware/E2E only.  │
│                                                                        │
│  8. Compose: createComposeRule() + testTag for stable finders.      │
│     Prefer stateless composables in UI tests (no ViewModel needed).  │
└────────────────────────────────────────────────────────────────────────┘
```

---

*← [Phase 17 — Performance and Memory](17_performance_and_memory.md)*