# Phase 13 — Android Architecture

> Android has one rule that all architecture patterns enforce: the UI layer must not own business logic or state. Everything else — MVVM vs MVI, LiveData vs StateFlow, Hilt vs Koin — is a consequence of that one rule applied at different levels.

## Navigation

[← Phase 12 — Reference Operators and Reflection](12_reference_operators_and_reflection.md) | [→ Phase 14 — Jetpack Components](14_jetpack_components.md)

## Questions in This File

- [Q13.1 — MVVM and Unidirectional Data Flow](#q131--mvvm-and-unidirectional-data-flow)
- [Q13.2 — Clean Architecture Layer Boundaries](#q132--clean-architecture-layer-boundaries)
- [Q13.3 — ViewModel Internals](#q133--viewmodel-internals)
- [Q13.4 — LiveData vs StateFlow vs SharedFlow](#q134--livedata-vs-stateflow-vs-sharedflow)
- [Q13.5 — Dependency Injection — Hilt](#q135--dependency-injection--hilt)
- [Q13.6 — Repository and Offline-First](#q136--repository-and-offline-first)
- [Q13.7 — Error Handling Across Layers](#q137--error-handling-across-layers)

---

# Q13.1 — MVVM and Unidirectional Data Flow

> **Builds on:** [Q10.4 (viewModelScope)](10_structured_concurrency.md#q104--lifecycle-scopes-and-process-death) · [Q11.3 (StateFlow)](11_flow.md#q113--stateflow-vs-sharedflow)
> **Connects to:** [Q13.2 (Clean Architecture)](13_android_architecture.md#q132--clean-architecture-layer-boundaries) · [Q13.3 (ViewModel internals)](13_android_architecture.md#q133--viewmodel-internals)

---

## The Core Rule

```
MVVM separates concerns.
MVI enforces one-way data flow.
You can use MVI ON TOP OF MVVM. They are not alternatives.
```

---

## The Problem: MassiveViewActivity

```
UserProfileActivity (500+ lines):
  ├── onClick() → calls Retrofit directly
  ├── onResponse() → parses JSON, updates UI, writes DB
  ├── onConfigurationChanged() → manual state save
  └── everything tangled — rotation = data loss, tests = impossible
```

**MVVM with UDF layered on top:**

```
View                      ViewModel                    Repository
  │                            │                            │
  │── onEvent(LoadProfile) ──► │                            │
  │                            │── getUser(id) ────────────►│
  │                            │◄── User ───────────────────│
  │◄── collect(uiState) ───── │                            │
```

Direction rule: events flow **UP** (View → VM), state flows **DOWN** (VM → View). One direction only.

---

## Is MVVM Unidirectional?

**No. MVVM doesn't enforce it — MVI does.**

Classic MVVM:
- View observes ViewModel (one direction ✓)
- View can also call ViewModel methods directly (creates two-way coupling)

MVI (strict UDF):
```
View emits Intents ──► ViewModel reduces ──► State
View renders State ◄────────────────────────────
         ↑                                      │
         └────────────────────────────────────── (loop, one direction)
```

**Interview answer:** "MVVM is about separation of concerns, not data flow direction. You enforce UDF on top of MVVM with a single `StateFlow<UiState>` output and a single `onEvent(UiEvent)` entry point. Pure MVI makes this contract mandatory."

---

## What Lives in ViewModel — The Rule

```kotlin
// GOOD — pure Kotlin island, no Android framework:
class UserViewModel(
    private val getUser: GetUserUseCase   // pure Kotlin, no Android import
) : ViewModel() {
    private val _state = MutableStateFlow<UserUiState>(UserUiState.Loading)
    val state: StateFlow<UserUiState> = _state.asStateFlow()

    fun onEvent(event: UserEvent) {
        when (event) {
            is UserEvent.Load -> loadUser(event.id)
        }
    }

    private fun loadUser(id: String) {
        viewModelScope.launch {
            _state.value = try {
                UserUiState.Content(getUser(id))
            } catch (e: AppError) {
                UserUiState.Error(e)
            }
        }
    }
}
```

```
IN (ViewModel owns):           OUT (ViewModel must not own):
  _uiState: MutableStateFlow     Context reference
  fun onEvent()                  View reference
  viewModelScope coroutines      Navigation logic (debated)
  UseCase/Repository calls       Android Framework APIs
```

**Mnemonic: "VM is a pure Kotlin island — no Android waves can reach it."**

---

## MVVM vs MVP vs MVI

| Pattern | View-VM coupling | State management | Testability |
|---|---|---|---|
| MVP | Presenter holds View interface reference | Manual, call-by-call | Medium (mock View) |
| MVVM | VM exposes observable; View observes | LiveData / StateFlow | High (no View ref) |
| MVI | Single immutable state; events explicit | Single `StateFlow<State>` | Very High (pure functions) |

---

## ## Traps

**Trap — "Is MVVM the same as MVI?"**

No. MVVM is a structural pattern. MVI is a data-flow contract. MVVM with a single StateFlow and `onEvent()` is MVVM that *implements* MVI's UDF contract.

**Trap — Context in ViewModel leaks:**

```kotlin
// WRONG — Activity leaks:
class UserViewModel(private val context: Context) : ViewModel()

// OK if you must — use Application context:
class UserViewModel(private val app: Application) : AndroidViewModel(app)

// BEST — inject a wrapper, keep VM pure:
class UserViewModel(private val stringRes: StringProvider) : ViewModel()
```

---

## Memory Trick

```
MVVM = separation.   MVI = direction contract.
MVI can be implemented on top of MVVM.

VM owns: StateFlow<State>, fun onEvent(), viewModelScope coroutines.
VM bans: Context, View refs, Framework APIs.

UDF: Events UP (View→VM), State DOWN (VM→View).
```

---

## Self-Test

1. Is MVVM unidirectional? What pattern enforces UDF as a strict contract?
2. What makes `AndroidViewModel` different from `ViewModel`? When should you use it?
3. Why can't a ViewModel hold a reference to an Activity?
4. What is the single-event entry point pattern and why does it improve testability?

---

# Q13.2 — Clean Architecture Layer Boundaries

> **Builds on:** [Q13.1 (MVVM)](13_android_architecture.md#q131--mvvm-and-unidirectional-data-flow)
> **Connects to:** [Q13.5 (DI)](13_android_architecture.md#q135--dependency-injection--hilt) · [Q13.7 (Error handling)](13_android_architecture.md#q137--error-handling-across-layers)

---

## The Core Rule

```
Dependencies can only point INWARD.
Presentation → Domain ← Data
Domain knows nothing about Retrofit, Room, or Android.
```

---

## The Dependency Rule — Visual

```
┌───────────────────────────────────────┐
│  Presentation (ViewModel, Composable) │
│         │ depends on                  │
│         ▼                             │
│  Domain (UseCase, Repository interface, Domain Model) │
│         ▲ depends on                  │
│         │                             │
│  Data (RepositoryImpl, Retrofit, Room)│
└───────────────────────────────────────┘

Arrows: Presentation → Domain ✓
        Data         → Domain ✓ (implements its interfaces)
        Domain       → Data   ✗ (violation!)
        Presentation → Data   ✗ (violation!)
```

---

## Repository Interface — Where Does It Live?

**Answer: Domain layer.** This is the Dependency Inversion Principle.

```kotlin
// Domain layer — interface, no imports from Retrofit or Room:
interface UserRepository {
    suspend fun getUser(id: String): User
    suspend fun saveUser(user: User)
}

// Data layer — implementation, depends on Domain interface:
class UserRepositoryImpl(
    private val api: UserApi,
    private val dao: UserDao
) : UserRepository {
    override suspend fun getUser(id: String): User =
        try { api.getUser(id).toDomain() }
        catch (e: HttpException) { throw translateError(e) }
}
```

**Test:** "Can the Domain module compile without the Data module?" → Yes = correct. No = interface is in wrong layer.

---

## When Is a UseCase Justified?

```kotlin
// JUSTIFIED — combines multiple repos, real business logic:
class PlaceOrderUseCase(
    private val cartRepo: CartRepository,
    private val inventoryRepo: InventoryRepository,
    private val paymentRepo: PaymentRepository,
    private val orderRepo: OrderRepository
) {
    suspend operator fun invoke(userId: String): Order {
        val cart = cartRepo.getCart(userId)
        inventoryRepo.reserveItems(cart.items)
        val payment = paymentRepo.charge(cart.total)
        return orderRepo.createOrder(userId, cart, payment)
    }
}

// OVER-ENGINEERING — just a pass-through:
class GetUserUseCase(private val repo: UserRepository) {
    suspend operator fun invoke(id: String) = repo.getUser(id)
    // Zero value — ViewModel can call repo directly
}
```

**Decision rule:** "Does removing this UseCase require changing two or more ViewModels?" → Yes = justified. No = call the repo directly.

---

## Domain Models vs Entity/DTO

```
Network DTO  →  toDomain()  →  Domain Model  →  toUiModel()  →  UI Model
(ApiUser)                       (User)                          (UserUiState)

Why separate?
  ApiUser has network fields (rawJson, serverTimestamp) — UI doesn't need these.
  User is pure business object — no Retrofit or Room annotations.
  UiModel is display-ready — has formatted strings, display flags.
```

---

## ## Traps

**Trap — `HttpException` leaking into the ViewModel:**

```kotlin
// WRONG — Retrofit type in Presentation:
catch (e: HttpException) { if (e.code() == 401) navigateToLogin() }

// CORRECT — Data layer translates to domain error:
// In RepositoryImpl:
catch (e: HttpException) { throw when (e.code()) { 401 -> AppError.Unauthorized } }
// In ViewModel:
catch (e: AppError.Unauthorized) { navigate(LoginScreen) }
```

**Trap — Injecting `UserRepositoryImpl` directly into ViewModel:**

```kotlin
// WRONG — ViewModel depends on concrete Data type:
class UserViewModel(private val repo: UserRepositoryImpl)

// CORRECT — depends only on the interface (Domain type):
class UserViewModel(private val repo: UserRepository)
```

---

## Memory Trick

```
Dependency arrows point INWARD only: Presentation → Domain ← Data.

Repository interface location test:
  "Can Domain compile without Data?" YES → correct. NO → wrong layer.

UseCase justified test:
  "Does removing it require rewriting 2+ ViewModels?" YES → keep it.

Domain model is pure Kotlin — no @Entity, no @SerializedName.
```

---

## Self-Test

1. Where does the `UserRepository` interface live — Domain or Data? Why?
2. You have a `GetUserUseCase` that's a one-liner delegating to `UserRepository`. Is it justified? What's the cost?
3. The ViewModel catches `HttpException`. Which layer boundary was violated and how do you fix it?
4. Can the Domain layer import from `kotlinx.coroutines`? What about `retrofit2`?

---

# Q13.3 — ViewModel Internals

> **Builds on:** [Q10.4 (viewModelScope)](10_structured_concurrency.md#q104--lifecycle-scopes-and-process-death)
> **Connects to:** [Q11.3 (StateFlow)](11_flow.md#q113--stateflow-vs-sharedflow) · [Q13.4 (StateFlow choice)](13_android_architecture.md#q134--livedata-vs-stateflow-vs-sharedflow)

---

## The Core Rule

```
ViewModel survives configuration changes (rotation) via NonConfigurationInstances.
ViewModel does NOT survive process death.
SavedStateHandle survives both — it rides the Binder (system server).
```

---

## How ViewModel Survives Rotation

```
ROTATION (ViewModel survival):
Old Activity:
  onPause()
  onSaveInstanceState()
  onStop()
  onRetainNonConfigurationInstance()
    └─ saves ViewModelStore
  onDestroy()

New Activity:
  onCreate()
    └─ getLastNonConfigurationInstance()
         └─ restores ViewModelStore
              └─ same ViewModel ✓
```

The `ViewModelStore` is a `HashMap<String, ViewModel>`. During rotation, Android saves it in `NonConfigurationInstances` — a blob that lives in the `ActivityThread` (not destroyed with the Activity). The Activity is recreated but the store is restored.

```kotlin
// Simplified ComponentActivity source:
override fun onRetainNonConfigurationInstance(): Any {
    return NonConfigurationInstances(viewModelStore = mViewModelStore)
}

override fun onCreate(savedInstanceState: Bundle?) {
    val nc = lastNonConfigurationInstance as? NonConfigurationInstances
    nc?.viewModelStore?.let { mViewModelStore.putAll(it) }  // restore!
}
```

---

## Survival Matrix

```
Event                   ViewModel    SavedStateHandle    Room/DataStore
Rotation                ✓ YES        ✓ YES               ✓ YES
Background (in memory)  ✓ YES        ✓ YES               ✓ YES
Process death (OOM)     ✗ NO         ✓ YES               ✓ YES
Force quit              ✗ NO         ✗ NO                ✓ YES
```

```
WHAT STORES WHERE:
  RAM   → ViewModel (rotation ✓)
          (killed with process ✗)
  Binder→ SavedStateHandle (✓)
  Disk  → Room / DataStore (✓)
```

**Mnemonic:**
- ViewModel lives in RAM → RAM dies with process → VM dies
- SavedStateHandle rides the Binder → system server holds it → survives process death
- Room is SQLite on disk → nothing kills it short of uninstall

---

## `SavedStateHandle` — How It Works

`SavedStateHandle` hooks into Android's `onSaveInstanceState(Bundle)` mechanism.

```kotlin
@HiltViewModel
class UserViewModel @Inject constructor(
    private val savedState: SavedStateHandle   // injected by Hilt automatically
) : ViewModel() {

    // Survives rotation AND process death:
    var userId: String?
        get() = savedState["userId"]
        set(value) { savedState["userId"] = value }

    // As StateFlow:
    val userIdFlow = savedState.getStateFlow("userId", "")
}
```

```
SavedStateHandle path:
  savedState["key"] = value
      │
      ▼
  Serialized into Bundle
      │
      ▼
  onSaveInstanceState() → Binder IPC → system_server stores it
      │
      ▼                              (process killed here)
  New process starts, Activity restored
      │
      ▼
  intent.extras has the Bundle → SavedStateHandle reconstructed
```

---

## The ~1MB Bundle Size Limit

`onSaveInstanceState` uses Binder IPC. Binder has a per-transaction limit of ~1MB.

```kotlin
// WRONG — TransactionTooLargeException:
savedState["users"] = userList  // 10,000 User objects = hundreds of KB

// CORRECT — store only the key, re-fetch from DB:
savedState["selectedUserId"] = "user_42"   // 8 bytes
// On restore: read selectedUserId → fetch User from Room
```

Safe types for `SavedStateHandle`: `String`, `Int`, `Boolean`, small `Parcelable` data classes.

---

## ViewModel Scoped to Nav Graph

```kotlin
// Standard — each screen gets its own ViewModel:
val vm: UserViewModel by viewModels()

// Shared across screens in a nav graph:
val vm: CheckoutViewModel by navGraphViewModels(R.id.checkout_graph)
// Same instance in OrderListScreen AND OrderSummaryScreen
```

Use for wizard flows, checkout, onboarding — any multi-step flow where screens share state.

---

## ## Traps

**Trap — `onCleared()` is NOT called on process death:**

```kotlin
// onCleared() is called when user navigates away (back press, clear recents).
// It is NOT called when the OS kills the process.
// → Don't use onCleared() to save critical state; use SavedStateHandle instead.
```

**Trap — Assuming ViewModel clears on rotation:**

```kotlin
// viewModelScope is tied to the ViewModel's lifecycle, not the Activity's.
// Coroutines launched in viewModelScope survive rotation.
// They are cancelled only when onCleared() is called.
```

---

## Memory Trick

```
ViewModelStore = HashMap<String, ViewModel>.
Survives rotation via NonConfigurationInstances (held by ActivityThread).
Cleared when user navigates away (back press / clear recents).

SavedStateHandle = Bundle backed by Binder IPC.
  ~1MB limit. Store keys, not lists.
  Survives process death. ViewModel does not.

onCleared() = user navigated away. NOT process death.
```

---

## Self-Test

1. Trace the exact mechanism that lets a ViewModel survive screen rotation.
2. Does `viewModelScope.launch { }` survive screen rotation? Does it survive process death?
3. What is the `~1MB` limit? Where does it come from? What happens if you exceed it?
4. You have scroll position (Int) and a list of 5,000 items to persist. What goes in `SavedStateHandle` and what goes in Room? Why?
5. When is `onCleared()` called? Name two scenarios where it is NOT called.

---

# Q13.4 — LiveData vs StateFlow vs SharedFlow

> **Builds on:** [Q11.3 (StateFlow vs SharedFlow)](11_flow.md#q113--stateflow-vs-sharedflow) · [Q13.3 (ViewModel)](13_android_architecture.md#q133--viewmodel-internals)
> **Connects to:** [Q11.4 (Flow collection lifecycle)](11_flow.md#q114--flow-collection-and-lifecycle)

---

## The Core Rule

```
StateFlow  = current state. Has value. Filters duplicates.
SharedFlow = events. No stored value. No filter.
LiveData   = legacy. Android-only. Lifecycle-aware out of the box.
```

---

## The Four Key Differences

| | LiveData | StateFlow |
|---|---|---|
| Android dependency | Yes (`androidx.lifecycle`) | No (`kotlinx.coroutines`) |
| Null support | Yes | Only if `StateFlow<T?>` |
| Lifecycle aware | Built-in (`observe()`) | Requires `repeatOnLifecycle` |
| Duplicate filtering | No | Yes (uses `equals()`) |

**StateFlow wins when:** you're already using coroutines, Domain layer must stay Android-free, or you need Compose compatibility (`collectAsStateWithLifecycle`).

**LiveData is acceptable when:** you're maintaining a legacy View-based codebase with no coroutines.

---

## Lifecycle-Safe Collection

```kotlin
// WRONG — collects even when app is in background (wastes work):
lifecycleScope.launch {
    viewModel.state.collect { render(it) }
}

// CORRECT — pauses collection when backgrounded:
lifecycleScope.launch {
    repeatOnLifecycle(Lifecycle.State.STARTED) {
        viewModel.state.collect { render(it) }
    }
}
```

`repeatOnLifecycle(STARTED)` cancels the inner coroutine when the lifecycle goes below STARTED and relaunches when it comes back. This is the standard pattern for observing StateFlow in an Activity or Fragment.

---

## The Navigation Event Trap

StateFlow filters duplicate values. Navigation events break silently.

```kotlin
// WRONG — StateFlow for navigation events:
val navigateTo = MutableStateFlow<String?>(null)
navigateTo.value = "DetailScreen"
// User presses back, navigates to "DetailScreen" again:
navigateTo.value = "DetailScreen"   // DROPPED — same as previous!
```

```
StateFlow (filters duplicates):
  emit("Detail") → emit("Detail")
       ✓ received    ✗ DROPPED

Channel (delivers all):
  send("Detail") → send("Detail")
       ✓ received    ✓ received
```

---

## One-Shot Events — `SharedFlow` or `Channel`?

```kotlin
// SharedFlow(replay=0) — broadcast, multiple observers:
private val _events = MutableSharedFlow<UiEvent>()
val events = _events.asSharedFlow()

viewModelScope.launch { _events.emit(UiEvent.Navigate("Detail")) }

// Collect (MUST be lifecycle-aware):
lifecycleScope.launch {
    repeatOnLifecycle(Lifecycle.State.STARTED) {
        viewModel.events.collect { event -> handleEvent(event) }
    }
}

// Channel — single consumer, simpler, queue-based:
private val _events = Channel<UiEvent>(Channel.BUFFERED)
val events = _events.receiveAsFlow()

viewModelScope.launch { _events.send(UiEvent.Navigate("Detail")) }
```

**Rule:** Single consumer (one UI collecting) → `Channel`. Multiple observers → `SharedFlow(replay=0)`.

---

## Decision Table

```
┌──────────────────────────────────────┐
│ UI state (loading/content/error)     │
│   → StateFlow                        │
├──────────────────────────────────────┤
│ One-shot event, 1 consumer           │
│   → Channel                          │
├──────────────────────────────────────┤
│ One-shot event, N observers          │
│   → SharedFlow(replay=0)             │
├──────────────────────────────────────┤
│ Legacy View-based app                │
│   → LiveData (acceptable)            │
└──────────────────────────────────────┘
```

---

## ## Traps

**Trap — `collect` without `repeatOnLifecycle` in Fragments:**

```kotlin
// WRONG — Fragment.onViewCreated, collects even in background:
viewLifecycleOwner.lifecycleScope.launch {
    viewModel.state.collect { render(it) }
}

// CORRECT:
viewLifecycleOwner.lifecycleScope.launch {
    viewLifecycleOwner.repeatOnLifecycle(Lifecycle.State.STARTED) {
        viewModel.state.collect { render(it) }
    }
}
```

**Trap — Exposing `MutableStateFlow` from ViewModel:**

```kotlin
// WRONG — UI can write directly:
val state = MutableStateFlow<UserUiState>(Loading)

// CORRECT — expose read-only:
private val _state = MutableStateFlow<UserUiState>(Loading)
val state: StateFlow<UserUiState> = _state.asStateFlow()
```

---

## Memory Trick

```
"StateFlow COMPARES, Channel DELIVERS."
  navigate("Detail") twice via StateFlow → second is LOST
  navigate("Detail") twice via Channel   → both arrive

LiveData = Android type. Can't use in Domain layer.
StateFlow = coroutine type. Domain-safe. Needs repeatOnLifecycle in UI.

collect without repeatOnLifecycle = collects in background = wasted work.
```

---

## Self-Test

1. You emit "DetailScreen" twice to a `StateFlow`. How many times does the collector receive it? Why?
2. What does `repeatOnLifecycle(STARTED)` do that `lifecycleScope.launch` alone does not?
3. When should you use `Channel` over `SharedFlow` for UI events?
4. Can a `StateFlow` live in the Domain layer? Can a `LiveData`? Why?

---

# Q13.5 — Dependency Injection — Hilt

> **Builds on:** [Q13.2 (Clean Architecture)](13_android_architecture.md#q132--clean-architecture-layer-boundaries)
> **Connects to:** [Q2.4 (object singleton)](02_classes_and_objects.md#q24--the-object-keyword)

---

## The Core Rule

```
DI = dependencies pushed INTO objects (via constructor).
Service Locator = objects pull FROM a global registry.
Hilt = true DI. Koin = Service Locator with DI syntax.
```

---

## DI vs Service Locator — Side by Side

```kotlin
// DI (Hilt/Dagger) — constructor declares what it needs:
class UserRepository @Inject constructor(
    private val api: UserApi,    // injected by Hilt
    private val dao: UserDao     // injected by Hilt
)

// Service Locator (Koin pattern) — object pulls from global registry:
class UserRepository {
    private val api: UserApi by inject()   // global lookup at runtime
    private val dao: UserDao by inject()   // global lookup at runtime
}
```

**Why DI wins for testing:**

```kotlin
// Hilt/Dagger — just pass test doubles via constructor:
val repo = UserRepository(FakeUserApi(), FakeUserDao())

// Koin — must configure global registry before each test:
startKoin { modules(module { single { FakeUserApi() } }) }
// Forgetting this → real production objects in tests
```

---

## How Hilt Works — Code Generation

```kotlin
@HiltAndroidApp class MyApp : Application()
@AndroidEntryPoint class MainActivity : AppCompatActivity()

@HiltViewModel
class UserViewModel @Inject constructor(
    private val repo: UserRepository
) : ViewModel()
```

Hilt's annotation processor (KSP) generates at compile time:

```
MyApp_HiltComponents.java
  └── SingletonC (Dagger component — the DI container)
        ├── provides @Singleton AppDatabase
        ├── provides @Singleton UserApi
        └── provides @Singleton UserRepositoryImpl (bound to UserRepository interface)

UserViewModel_HiltModules.java
  └── UserViewModel_Factory — auto-generated ViewModelFactory
        ← ViewModelProvider uses this factory
        ← Hilt provides UserRepository to it
```

You write `by viewModels()` — Hilt handles factory creation and injection.

---

## Hilt Scopes

```
Scope ladder (outer → inner):
  @Singleton       → app lifetime (one instance for entire app)
  @ActivityScoped  → activity lifetime
  @ViewModelScoped → ViewModel lifetime
  @FragmentScoped  → fragment lifetime

Rule: outer scopes can inject INTO inner scopes. Never the reverse.
  @Singleton can inject into @ActivityScoped. ✓
  @ActivityScoped CANNOT inject into @Singleton. ✗ (scope violation)
```

```
HILT SCOPE LADDER
┌─────────────────────┐
│    @Singleton       │ ← app
├─────────────────────┤
│  @ActivityScoped    │ ← activity
├─────────────────────┤
│  @ViewModelScoped   │ ← VM
├─────────────────────┤
│   @FragmentScoped   │ ← fragment
└─────────────────────┘
Inject DOWN ↓ only (outer → inner)
Cannot inject UP ↑ (inner → outer)
```

---

## `@Binds` vs `@Provides`

```kotlin
// @Provides — you write the construction code:
@Provides @Singleton
fun provideOkHttp(auth: AuthInterceptor): OkHttpClient =
    OkHttpClient.Builder().addInterceptor(auth).build()

// @Binds — declaration only, no code needed:
@Binds
abstract fun bindUserRepo(impl: UserRepositoryImpl): UserRepository
// "When UserRepository is needed, give UserRepositoryImpl"
```

`@Binds` generates more efficient code — no extra factory class. Prefer `@Binds` for interface binding, `@Provides` for object construction.

---

## ## Traps

**Trap — Koin is not DI:**

If asked "Is Koin DI?", the precise answer: Koin is a **Service Locator** with DI-like syntax. It uses a global `KoinContext` that objects query at runtime. It is not compile-time verified; missing bindings fail at runtime, not at build time.

**Trap — `@Singleton` scope on wrong component:**

```kotlin
@Module @InstallIn(ActivityComponent::class)
object WrongModule {
    @Provides @Singleton  // WRONG — ActivityComponent outlives the scope
    fun provideRepo(): UserRepository = UserRepositoryImpl()
}
// Hilt will throw a compile error — scope mismatch is caught at build time
```

---

## Memory Trick

```
DI: "I declare what I need" (constructor params) → framework pushes it in.
SL: "I fetch what I need" (inject() call) → global registry lookup.

Hilt scopes — remember the ladder:
  Singleton → Activity → ViewModel → Fragment
  Outer can flow into inner. Inner cannot flow out.

@Binds = declare (interface → impl). No code.
@Provides = construct (build the object). Has code.

Koin = Service Locator. Runtime errors for missing bindings.
Hilt = compile-time graph. Missing bindings = build failure.
```

---

## Self-Test

1. What is the mechanical difference between DI and Service Locator? Give a code example.
2. Is Koin DI? What's the precise answer?
3. What does `@HiltViewModel` generate and where is it used?
4. When does `@Binds` work? When must you use `@Provides`?
5. Can a `@ViewModelScoped` dependency be injected into a `@Singleton`? Why not?

---

# Q13.6 — Repository and Offline-First

> **Builds on:** [Q13.2 (Clean Architecture)](13_android_architecture.md#q132--clean-architecture-layer-boundaries) · [Q11.3 (StateFlow)](11_flow.md#q113--stateflow-vs-sharedflow)
> **Connects to:** [Q13.7 (Error handling)](13_android_architecture.md#q137--error-handling-across-layers) · [Q14.1 (Room)](14_jetpack_components.md#q141--room--internals)

---

## The Core Rule

```
Single Source of Truth: Network feeds Room. Room feeds UI. 
Network NEVER feeds UI directly.
```

---

## SSoT Pattern — Before and After

**Without SSoT:**

```
UI ──► Network ──► UI directly
           ↑ network down → blank screen, no offline
```

**With SSoT (Room as source of truth):**

```
UI  ──observe──►  Room DB  ◄──write──  Network
         ↑              ↑
  Flow<List<T>>    InvalidationTracker emits on write
  emits immediately    → UI auto-updates
```

```kotlin
class UserRepository(private val api: UserApi, private val dao: UserDao) {

    // UI observes Room — always has data, even offline:
    fun observeUsers(): Flow<List<User>> = dao.observeAll().map { it.toDomain() }

    // Trigger network refresh — writes to Room, Room notifies UI:
    suspend fun refreshUsers() {
        val users = api.getUsers()     // fetch
        dao.insertAll(users.toEntity()) // write to DB
        // Room's InvalidationTracker fires → Flow emits → UI updates
    }
}
```

---

## Optimistic Updates — Local First, Sync Later

```kotlin
// Show result immediately in UI, sync to server in background:
suspend fun likePost(postId: String): Result<Unit> {
    postDao.updateLikeCount(postId, +1)   // 1. Write locally (t=0ms) → UI updates instantly
    return try {
        api.likePost(postId)               // 2. Sync to server (t=~300ms)
        Result.success(Unit)
    } catch (e: Exception) {
        postDao.updateLikeCount(postId, -1) // 3. Rollback on failure → Room emits → UI reverts
        Result.failure(e)
    }
}
```

```
t=0ms:   User taps Like → DB +1 → UI shows "Liked" ✓
t=300ms: Network success → nothing to do (DB already correct)
    OR
t=300ms: Network fails → DB rollback -1 → Flow emits → UI reverts automatically
```

**Why rollback is free:** UI observes Room via Flow. The rollback write triggers a new emission automatically — no manual UI state management needed.

---

## Conflict Resolution Strategies

| Strategy | Rule | Use When |
|---|---|---|
| Last-Write-Wins | Most recent timestamp wins | Simple data, infrequent edits |
| Server-Wins | Server data always overrides | Financial, inventory |
| Client-Wins | Local data always wins | User's own drafts |
| Field-Level Merge | Merge non-conflicting fields | Collaborative editing |
| CRDTs | Mathematically conflict-free | Distributed counters, sets |

```kotlin
// Last-Write-Wins:
fun resolveConflict(local: Note, server: Note): Note =
    if (local.updatedAt > server.updatedAt) local else server
```

---

## Memory Trick

```
SSoT: Network → Room → UI (never Network → UI directly).
Room's Flow re-emits on any write — this is the auto-refresh mechanism.

Optimistic update = write local first, sync later, rollback if network fails.
Rollback is automatic because UI observes Room (no manual setState).
```

---

## Self-Test

1. In the SSoT pattern, what triggers the UI to refresh when the network returns new data?
2. Why is optimistic update rollback "free" when using Room + Flow?
3. You have a note-taking app. User edits on phone while offline; server has a newer version. What conflict strategy fits? Why?

---

# Q13.7 — Error Handling Across Layers

> **Builds on:** [Q13.6 (Repository)](13_android_architecture.md#q136--repository-and-offline-first) · [Q10.3 (CancellationException)](10_structured_concurrency.md#q103--exception-handling-rules)
> **Connects to:** [Q13.2 (Layer boundaries)](13_android_architecture.md#q132--clean-architecture-layer-boundaries)

---

## The Core Rule

```
Translate errors at each layer boundary.
HTTP codes belong in Data layer.
Domain errors belong in Domain layer.
UI strings belong in Presentation layer.
No layer speaks another layer's vocabulary.
```

---

## Error Translation Pipeline

```
Data layer:
  HttpException(401)  →  throw AppError.Unauthorized
  HttpException(404)  →  throw AppError.NotFound("User $id")
  HttpException(5xx)  →  throw AppError.ServerError
  IOException         →  throw AppError.NetworkError

Domain boundary (sealed class AppError — no Retrofit imports)

ViewModel:
  catch AppError.Unauthorized  →  UiState.Error.SessionExpired
  catch AppError.NetworkError  →  UiState.Error.Offline
  catch AppError.NotFound      →  UiState.Error.NotFound(resource)

UI:
  SessionExpired  →  navController.navigate(loginScreen)
  Offline         →  show snackbar + retry button
```

---

## Sealed `AppError` — The Contract

```kotlin
// Domain layer — no Retrofit or Android imports:
sealed class AppError : Exception() {
    object Unauthorized : AppError()
    object NetworkError : AppError()
    object ServerError : AppError()
    data class NotFound(val resource: String) : AppError()
    data class ValidationError(val field: String, val message: String) : AppError()
    data class Unknown(val cause: String?) : AppError()
}
```

**Why sealed?** `when (e)` on a sealed class is exhaustive. Add a new `AppError.RateLimit` subtype → compiler error in every ViewModel that doesn't handle it. Silent unhandled errors become impossible.

---

## The `CancellationException` Trap — Most Common Production Bug

```kotlin
// WRONG — swallows CancellationException:
viewModelScope.launch {
    try {
        val user = repo.getUser(id)
        _state.value = UiState.Content(user)
    } catch (e: Exception) {               // catches CancellationException!
        _state.value = UiState.Error.Generic  // shows error when user navigated away!
    }
}
```

**What happens:**
1. User navigates away → `viewModelScope.cancel()` called
2. `CancellationException` thrown inside `repo.getUser()`
3. `catch (e: Exception)` catches it (CE is a subclass of Exception)
4. `_state.value = UiState.Error.Generic` executes on a cancelled scope
5. Coroutine appears to complete normally → no cleanup → **leak**

```kotlin
// CORRECT — always re-throw CancellationException first:
viewModelScope.launch {
    try {
        val user = repo.getUser(id)
        _state.value = UiState.Content(user)
    } catch (e: CancellationException) {
        throw e                              // re-throw FIRST
    } catch (e: AppError) {
        _state.value = mapToUiError(e)
    }
}
```

---

## ## Traps

**Trap — `HttpException` in ViewModel:**

Any import of `retrofit2.HttpException` in a ViewModel is a layer boundary violation. Fix by translating in `RepositoryImpl`.

**Trap — Generic catch without CancellationException re-throw:**

This is the #1 coroutine bug in production Android code. Every `catch (e: Exception)` block needs a `CancellationException` guard.

---

## Memory Trick

```
Error translation: "Each layer speaks its own language."
  Data speaks HTTP. Domain speaks business. UI speaks UX.

Sealed AppError = exhaustive when() → compiler forces you to handle new subtypes.

CancellationException rule — "CE is-a Exception → always re-throw first."
  Swallowed CE = coroutine keeps running despite scope cancellation = LEAK.
  Pattern: catch (CE) { throw it } before any other catch.
```

---

## Self-Test

1. `HttpException` is thrown in `UserRepositoryImpl`. Should the ViewModel catch it? What should catch it?
2. You add `AppError.RateLimit` to the sealed class. How does the compiler help you find all the places that need updating?
3. What is the exact bug sequence when `catch (e: Exception)` swallows a `CancellationException`?
4. Write the correct try-catch pattern for a ViewModel coroutine that catches domain errors but correctly handles cancellation.

---

## Phase 13 — Summary

```
┌────────────────────────────────────────────────────────────────────┐
│  1. MVVM ≠ UDF. MVI enforces UDF. Use MVI on top of MVVM.        │
│     VM = pure Kotlin island. No Context, View, or Framework refs. │
│                                                                    │
│  2. Repository interfaces in Domain. Dependency rule: arrows      │
│     point inward. Domain never depends on Data.                   │
│                                                                    │
│  3. ViewModel survives rotation (NonConfigInstances). NOT process │
│     death. SavedStateHandle survives both via Binder (~1MB limit).│
│                                                                    │
│  4. StateFlow filters duplicates → wrong for navigation events.  │
│     Channel for single consumer. SharedFlow(replay=0) for multi. │
│     Always use repeatOnLifecycle for collection.                  │
│                                                                    │
│  5. SSoT: Network → Room → UI. Optimistic update rollback is     │
│     free with Room + Flow (write triggers emission automatically).│
│                                                                    │
│  6. Translate errors at layer boundaries. CancellationException  │
│     must always be re-thrown — never swallowed by catch(Exception)│
└────────────────────────────────────────────────────────────────────┘
```

---

*← [Phase 12 — Reference Operators and Reflection](12_reference_operators_and_reflection.md) | [Phase 14 — Jetpack Components →](14_jetpack_components.md)*