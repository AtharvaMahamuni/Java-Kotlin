# Phase 13: Android Architecture

## Navigation
[← Master Index](master_chains.md)

## Questions in This File
- [Q13.1 — MVVM and Unidirectional Data Flow](#q131--mvvm-and-unidirectional-data-flow)
- [Q13.2 — Clean Architecture Layer Boundaries](#q132--clean-architecture-layer-boundaries)
- [Q13.3 — ViewModel Internals](#q133--viewmodel-internals)
- [Q13.4 — LiveData vs StateFlow vs SharedFlow](#q134--livedata-vs-stateflow-vs-sharedflow)
- [Q13.5 — Dependency Injection](#q135--dependency-injection)
- [Q13.6 — Repository and Offline-First Patterns](#q136--repository-and-offline-first-patterns)
- [Q13.7 — Error Handling Across Layers](#q137--error-handling-across-layers)

---

## Q13.1 — MVVM and Unidirectional Data Flow

> **Builds on:** [Q10.4 — Lifecycle Scopes](10_structured_concurrency.md#q104--lifecycle-scopes-and-process-death) · [Q11.3 — StateFlow for state](11_flow.md#q113--stateflow-vs-sharedflow)
> **Connects to:** [Q13.2 — Clean Architecture](13_android_architecture.md#q132--clean-architecture-layer-boundaries) · [Q13.3 — ViewModel](13_android_architecture.md#q133--viewmodel-internals)
> **Reference:** [Android Docs — Guide to app architecture](https://developer.android.com/topic/architecture)

### The Concrete Picture

Starting point — the MassiveViewActivity anti-pattern:
```
UserProfileActivity.kt (500 lines)
    ├── onClick()  → calls Retrofit directly
    ├── onResponse() → parses JSON, updates UI, writes to DB
    ├── onConfigurationChanged() → tries to save state manually
    └── everything tangled — rotation = data loss, tests = impossible
```

MVVM with UDF layered on top:
```
UserProfileActivity
    │  onEvent(UserEvent.LoadProfile(id))          ──►  ViewModel.onEvent()
    │                                                        │
    │                                                        ▼
    │                                               GetUserUseCase(userId)
    │                                                        │
    │                                                        ▼
    │  collect { state ->  render(state) }  ◄──  _uiState: StateFlow<UserUiState>
```
Direction: events flow UP (View → VM), state flows DOWN (VM → View). One way only.

### First Principles: Why Architecture Patterns?

Without a defined architecture, Android code tends toward **MassiveViewActivity** — Activities/Fragments that handle UI, business logic, network calls, database access, and state management. This makes code:
- Hard to test (Activity requires Android emulator)
- Impossible to maintain (everything tangled)
- Fragile during configuration changes (rotation kills your state)

Architecture patterns separate concerns: UI code only handles UI, business logic is in its own layer, etc.

### Is MVVM Unidirectional? — The Precise Answer

**MVVM is NOT strictly unidirectional by design, but can be implemented in a unidirectional way.**

Classic MVVM has:
- **V** (View) observes **VM** (ViewModel) — one direction
- **V** can also call methods on **VM** directly — creating two-way flow

```
Traditional MVVM (bidirectional possible):
View ←──── observes ──── ViewModel
View ──── calls ────────► ViewModel   ← bidirectional!
```

**MVI (Model-View-Intent) is the strictly unidirectional pattern:**
```
       ┌──────────────────────────────────────────┐
       │                                          │
       ▼                                          │
  View emits Intents ──► ViewModel processes ──► State
  (user actions)         (business logic)         │
                                                  │
  View renders State ◄───────────────────────────┘
       ▲                                          │
       └──────────────────────────────────────────┘
                    one direction only
```

**Interview answer:** "MVVM as a pattern doesn't enforce unidirectionality — it's about separation of concerns. You can add UDF on top of MVVM with a single `StateFlow<UiState>` for state output and a single `onEvent(event: UiEvent)` entry point for View actions. Pure MVI enforces UDF as a contract."

### MVVM vs MVP vs MVI

| Pattern | Key Contract | State management | Testability |
|---------|-------------|-----------------|-------------|
| MVP | Presenter holds reference to View interface | Manual | Medium (mock View) |
| MVVM | ViewModel exposes observable state; View observes | LiveData/StateFlow | High (no View ref in VM) |
| MVI | Single immutable state; events are explicit | Single StateFlow<State> | Very High (pure functions) |

**When MVI's single state object makes sense:**
- Complex screens with many interdependent state variables
- When you need perfect reproducibility (replay any state from intent sequence)
- Teams needing strict contracts about what state is possible

**When plain MVVM is sufficient:**
- Simple screens (a list, a form)
- When the overhead of sealed class events + single state is more than the problem is worth

### What Should and Should NOT Live in a ViewModel

**SHOULD live in ViewModel:**
- Business logic calls (to UseCases/Repositories)
- UI state (`_uiState: MutableStateFlow<UiState>`)
- User action handlers (`fun onButtonClicked()`)
- Long-running coroutines (via `viewModelScope`)
- Transformation of domain data to UI models

**Should NOT live in ViewModel:**
- Context references (memory leak risk — ViewModel outlives Activity)
- View references (same reason)
- Android Framework APIs that require Context (use `AndroidViewModel` if you must)
- Navigation logic (debated — some pass navController, others use events)

```kotlin
// GOOD ViewModel:
class UserViewModel(
    private val getUserUseCase: GetUserUseCase  // pure Kotlin — no Android deps!
) : ViewModel() {

    private val _uiState = MutableStateFlow<UserUiState>(UserUiState.Loading)
    val uiState: StateFlow<UserUiState> = _uiState.asStateFlow()

    fun loadUser(userId: String) {
        viewModelScope.launch {
            _uiState.value = UserUiState.Loading
            try {
                val user = getUserUseCase(userId)
                _uiState.value = UserUiState.Content(user)
            } catch (e: Exception) {
                _uiState.value = UserUiState.Error(e.message ?: "Unknown error")
            }
        }
    }
}
```

### Memory Trick

```
MVVM vs MVI:
  MVVM = separation (View and VM can still talk both ways)
  MVI  = one-way contract (View emits Intents, VM emits State, no return path)

What lives in ViewModel:
  IN:  UiState (StateFlow), action handlers (fun onClick), viewModelScope coroutines
  OUT: Context refs, View refs, Navigation logic, Android Framework calls

"VM is a pure Kotlin island — no Android waves can reach it"
```

---

## Q13.2 — Clean Architecture Layer Boundaries

> **Builds on:** [Q13.1 — MVVM](13_android_architecture.md#q131--mvvm-and-unidirectional-data-flow)
> **Connects to:** [Q13.5 — Dependency Injection](13_android_architecture.md#q135--dependency-injection) · [Q13.7 — Error Handling](13_android_architecture.md#q137--error-handling-across-layers)
> **Reference:** [Android Docs — Presentation, domain, and data layers](https://developer.android.com/topic/architecture/domain-layer)

### The Concrete Picture

Starting state — no layer separation, Data leaks everywhere:
```
UserViewModel
    │ imports retrofit2.HttpException          ← Data-layer type in Presentation!
    │ imports com.app.data.UserRepositoryImpl  ← Concrete impl, not interface!
    └── val repo = UserRepositoryImpl(api, db) ← ViewModel constructs its own deps!
```

After applying Clean Architecture dependency rule:
```
Presentation (ViewModel)
    │  imports only: UserRepository (interface), User (domain model)
    │  knows nothing about: Retrofit, Room, HttpException
    ▼
Domain (UserRepository interface, User model, GetUserUseCase)
    │  imports nothing from Android or Retrofit — pure Kotlin
    ▼
Data (UserRepositoryImpl)
    │  imports: Retrofit, Room, Domain interfaces
    └── implements UserRepository → direction of dependency points inward
```
Arrow direction: Presentation → Domain ← Data (arrow = "depends on")

### First Principles: The Dependency Rule

Clean Architecture's core rule: **dependencies can only point inward**. Outer layers depend on inner layers, never the reverse.

```
┌─────────────────────────────────────────────────────┐
│  UI / Presentation Layer                            │
│  (Activities, Fragments, ViewModels, Composables)   │
│                    │                                │
│                    │ depends on                     │
│                    ▼                                │
│  Domain Layer                                       │
│  (UseCases/Interactors, Domain Models, Interfaces) │
│                    │                                │
│                    │ depends on (via interfaces)    │
│                    ▼                                │
│  Data Layer                                         │
│  (Repositories impl, APIs, Database, DataStore)    │
└─────────────────────────────────────────────────────┘

Dependencies:
UI → Domain ✓
Domain → Data ✗ (Domain doesn't know Data exists)
UI → Data ✗ (UI doesn't know Data exists)
```

### Where Do Repository Interfaces Live?

**Repository interfaces live in the DOMAIN layer.**

This is the answer that reveals understanding of **Dependency Inversion Principle (DIP)**:

```kotlin
// Domain layer — defines the CONTRACT, knows nothing about implementation:
interface UserRepository {
    suspend fun getUser(id: String): User
    suspend fun saveUser(user: User)
}

// Data layer — provides the IMPLEMENTATION, depends on Domain interface:
class UserRepositoryImpl(
    private val api: UserApi,
    private val db: UserDao
) : UserRepository {
    override suspend fun getUser(id: String): User {
        return try { api.getUser(id).toDomain() }
        catch (e: Exception) { db.getUser(id).toDomain() }
    }
}
```

If the interface lived in the Data layer, the Domain layer would depend on Data — violating the dependency rule.

### When Is a UseCase Justified?

**UseCase is justified when:**
- Business logic is complex and reusable across multiple ViewModels
- The operation combines data from multiple repositories
- There's meaningful transformation or validation logic

**UseCase is over-engineering when:**
- It's a single line that just delegates to a repository
- Only one ViewModel uses it
- The "logic" is just a pass-through

```kotlin
// JUSTIFIED UseCase — complex business logic:
class PlaceOrderUseCase(
    private val cartRepository: CartRepository,
    private val inventoryRepository: InventoryRepository,
    private val paymentRepository: PaymentRepository,
    private val orderRepository: OrderRepository
) {
    suspend operator fun invoke(userId: String): Order {
        val cart = cartRepository.getCart(userId)
        inventoryRepository.reserveItems(cart.items)  // complex operation
        val payment = paymentRepository.charge(cart.total)
        return orderRepository.createOrder(userId, cart, payment)
    }
}

// OVER-ENGINEERING (just a pass-through):
class GetUserUseCase(private val repo: UserRepository) {
    suspend operator fun invoke(id: String) = repo.getUser(id)
    // This adds zero value — ViewModel can call repo directly
}
```

**Testing a UseCase in isolation:**
```kotlin
// Pure Kotlin — no Android imports! Can run on JVM without emulator:
class PlaceOrderUseCaseTest {
    private val cartRepo = FakeCartRepository()    // Fake — not Mock
    private val inventoryRepo = FakeInventoryRepository()
    private val useCase = PlaceOrderUseCase(cartRepo, inventoryRepo, ...)

    @Test
    fun `placing order reserves inventory`() = runTest {
        cartRepo.addItem(testItem)
        useCase(userId = "test")
        assertTrue(inventoryRepo.isReserved(testItem.id))
    }
}
```

### Memory Trick

```
Layer dependencies — only arrows pointing INWARD are allowed:
  UI ──► Domain ◄── Data
         (center)

Repository interface location test:
  "Can Domain compile without the Data module?"
  YES → interface is in Domain (correct)
  NO  → interface is in Data (violates DIP — fix it)

UseCase justified? Ask: "Does removing it require rewriting TWO ViewModels?"
  YES → justify the abstraction
  NO  → it's over-engineering; call the repo directly
```

---

## Q13.3 — ViewModel Internals

> **Builds on:** [Q10.4 — Lifecycle Scopes](10_structured_concurrency.md#q104--lifecycle-scopes-and-process-death) · [Q0.3 — Class loading (ViewModelStore)](00_jvm_mental_model.md#q03--class-loading-and-the-static--block)
> **Connects to:** [Q11.3 — StateFlow in ViewModel](11_flow.md#q113--stateflow-vs-sharedflow) · [Q13.4 — LiveData vs StateFlow](13_android_architecture.md#q134--livedata-vs-stateflow-vs-sharedflow) · [Q16.1 — Activity lifecycle](16_android_system_internals.md#q161--activity-and-fragment-lifecycle)
> **Reference:** [Android Docs — ViewModel overview](https://developer.android.com/topic/libraries/architecture/viewmodel)

### The Concrete Picture

Starting point — screen rotation without ViewModel:
```
Activity onCreate()  →  creates UserRepository, loads data, stores in field
User rotates device  →  Activity.onDestroy() called, all fields = gone
Activity onCreate()  →  starts fresh, blank screen, re-fetches everything
```

What actually happens with ViewModelStore across a rotation:
```
Rotation start:
  Activity.onRetainNonConfigurationInstance()
      └── saves ViewModelStore  ──►  NonConfigurationInstances (held by ActivityThread)

Activity destroyed and recreated:
  new Activity.onCreate()
      └── getLastNonConfigurationInstance()
          └── restores ViewModelStore  ──►  same ViewModel instance returned!

ViewModelProvider("UserViewModel")
  First time   → creates new UserViewModel, stores in ViewModelStore
  After rotate → finds existing UserViewModel in ViewModelStore — same object!
```
The ViewModel reference count in ViewModelStore never hits zero during rotation.

### How ViewModel Survives Configuration Changes

**Configuration change** (rotation, locale change, etc.) destroys and recreates the Activity. Without ViewModel, all data would be lost.

**The mechanism:**

```
Activity onCreate()
    │
    ▼
ViewModelProvider(activity, factory)
    │
    ├── First time: ViewModelStore doesn't have ViewModel
    │   → Creates new ViewModel
    │   → Stores in ViewModelStore
    │
    └── After rotation: Activity is recreated but
        ViewModelStore is RETAINED (via NonConfigurationInstances)
        → ViewModel retrieved from store — same instance!
```

**`ViewModelStore` and `NonConfigurationInstances`:**

```kotlin
// Simplified Android source:
class ComponentActivity : Activity() {
    private val mViewModelStore: ViewModelStore = ViewModelStore()

    // Called by Android system when config changes — BEFORE destroy:
    override fun onRetainNonConfigurationInstance(): Any {
        return NonConfigurationInstances(
            viewModelStore = mViewModelStore,  // ← saved here!
            // ... other non-configuration data
        )
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // Restore ViewModelStore if available:
        val nc = lastNonConfigurationInstance as? NonConfigurationInstances
        if (nc != null) {
            mViewModelStore.putAll(nc.viewModelStore)  // ← restored here!
        }
    }
}
```

The `NonConfigurationInstances` mechanism is specifically designed for data that should survive configuration changes but NOT process death ([Q16.1 — Activity lifecycle](16_android_system_internals.md#q161--activity-and-fragment-lifecycle)).

### Does ViewModel Survive Process Death?

**NO.** ViewModel does NOT survive process death.

```
Scenarios:
┌─────────────────────────────────────────────────┐
│  Screen rotation (config change):               │
│  ViewModel ✓ SURVIVES (via NonConfigInstances)  │
│                                                 │
│  User puts app in background (process still alive):
│  ViewModel ✓ SURVIVES (in memory)              │
│                                                 │
│  Android kills process (low memory):           │
│  ViewModel ✗ DIES (it's in memory — gone!)     │
│                                                 │
│  User force-quits the app:                     │
│  ViewModel ✗ DIES                              │
└─────────────────────────────────────────────────┘
```

**The exact boundary:**
- `onCleared()` is called when the user navigates away (back press, clear recent apps)
- Process death doesn't call `onCleared()` — the process just dies

### `SavedStateHandle` — Process Death Survivor

[`SavedStateHandle`](16_android_system_internals.md#q161--activity-and-fragment-lifecycle) hooks into Android's `onSaveInstanceState` mechanism. Data stored in it is serialized to a Bundle (Binder IPC) and persisted.

```kotlin
class UserViewModel(
    private val savedState: SavedStateHandle  // auto-injected by Hilt/ViewModelFactory
) : ViewModel() {

    // Survives BOTH configuration changes AND process death:
    var userId: String?
        get() = savedState["userId"]
        set(value) { savedState["userId"] = value }

    // Also as StateFlow:
    val userIdFlow = savedState.getStateFlow("userId", defaultValue = "")
}
```

**How it works under the hood:**
1. `SavedStateHandle` is backed by a `Bundle` that is saved in `onSaveInstanceState`
2. `onSaveInstanceState` stores this Bundle via [Binder IPC](16_android_system_internals.md#q163--binder-ipc) to the system server
3. System server persists it
4. On process restore, the Bundle is passed back via `intent.extras`

### The Bundle Size Limit — ~1MB

Binder transactions have a ~1MB limit. `onSaveInstanceState` uses Binder IPC, so it inherits this limit.

```kotlin
// DANGEROUS: storing large data in SavedStateHandle
savedState["users"] = listOf<User>(/* 10,000 users */)
// TransactionTooLargeException! May be 500KB or more

// CORRECT: store only identifiers, re-fetch data from Room/DataStore
savedState["selectedUserId"] = "user_42"  // tiny
// Recreate Activity → read selectedUserId → fetch from DB
```

**When to use what:**
- Small primitive state (selected tab, scroll position): `SavedStateHandle`
- Large data: Room database (auto-persisted to SQLite)
- User preferences: DataStore

### ViewModel Scoped to Navigation Graph

```kotlin
// Standard: each screen creates its own ViewModel:
val viewModel: UserViewModel by viewModels()  // unique per screen

// Scoped to nav graph: shared between all screens in the graph:
val viewModel: SharedViewModel by navGraphViewModels(R.id.nav_graph_orders)
// Same instance in OrderListFragment AND OrderDetailFragment!
```

**Use case:** Sharing state between screens that are part of a single flow (checkout flow, onboarding, etc.).

### Memory Trick

```
Survival matrix — what persists what?

  Event                 ViewModel    SavedStateHandle   Room/DataStore
  Rotation              YES          YES                YES
  Process death         NO           YES                YES
  Force quit            NO           NO                 YES

"ViewModel lives in RAM — RAM dies with the process.
 SavedStateHandle rides the Binder (system server keeps it).
 Room is on disk — nothing kills it."

SavedStateHandle size limit: ~1MB (Binder transaction limit)
  SAFE:  String, Int, Boolean, small data classes
  UNSAFE: List<User> with thousands of items → TransactionTooLargeException
```

---

## Q13.4 — LiveData vs StateFlow vs SharedFlow

> **Builds on:** [Q11.3 — StateFlow vs SharedFlow](11_flow.md#q113--stateflow-vs-sharedflow) · [Q13.3 — ViewModel](13_android_architecture.md#q133--viewmodel-internals)
> **Connects to:** [Q11.4 — Flow collection lifecycle](11_flow.md#q114--flow-collection-and-lifecycle)

### The Concrete Picture

Starting state — LiveData in a ViewModel, needs migration to StateFlow:
```kotlin
// Before — LiveData (Android dependency, can be null, no duplicate filter):
private val _user = MutableLiveData<User>()
val user: LiveData<User> = _user

// In Activity:
viewModel.user.observe(this) { user -> render(user) }
// Problem: observe() always active — emits in background, no lifecycle safety
```

After — StateFlow with `repeatOnLifecycle`:
```kotlin
// After — StateFlow (no Android dep, duplicate-filtered, coroutine-native):
private val _user = MutableStateFlow<User?>(null)
val user: StateFlow<User?> = _user.asStateFlow()

// In Activity (lifecycle-safe collection):
lifecycleScope.launch {
    repeatOnLifecycle(Lifecycle.State.STARTED) {  ← stops when backgrounded
        viewModel.user.collect { user -> render(user) }
    }
}
```
Key change: `observe()` → `repeatOnLifecycle + collect`

For one-shot navigation events — StateFlow drops duplicates (bug!):
```
StateFlow: "DetailScreen" → "DetailScreen"  ──►  second value DROPPED (equals check)
Channel:   "DetailScreen" → "DetailScreen"  ──►  both delivered, each consumed once
```

### The Four Key Differences: LiveData vs StateFlow

| Aspect | LiveData | StateFlow |
|--------|---------|-----------|
| Android dependency | Yes (`androidx.lifecycle`) | No (`kotlinx.coroutines`) |
| Null support | Yes (can hold null) | Only if explicitly `StateFlow<T?>` |
| Lifecycle awareness | Built-in (observe on LifecycleOwner) | Requires `repeatOnLifecycle` |
| Duplicate filtering | No | Yes (uses equals()) |

**StateFlow is better when:**
- Domain layer shouldn't know about Android (LiveData IS Android)
- You're already using coroutines throughout
- You need compose compatibility (`collectAsStateWithLifecycle`)

### When Does StateFlow NOT Replace LiveData?

**When consecutive duplicate filtering is a bug:**

```kotlin
// Navigation event:
val navigateTo = MutableStateFlow<String?>(null)
navigateTo.value = "DetailScreen"
// User navigates back...
navigateTo.value = "DetailScreen"  // DROPPED — same as previous! Bug!
```

For this, use `SharedFlow(replay=0)` or `Channel<T>`.

### One-Shot Events: `SharedFlow` or `Channel`?

**`SharedFlow(replay=0)`:**
```kotlin
private val _events = MutableSharedFlow<UiEvent>()
val events = _events.asSharedFlow()

// Emit:
viewModelScope.launch { _events.emit(UiEvent.Navigate("Detail")) }

// Collect (must be lifecycle-aware!):
lifecycleScope.launch {
    repeatOnLifecycle(Lifecycle.State.STARTED) {
        viewModel.events.collect { event ->
            when (event) {
                is UiEvent.Navigate -> navController.navigate(event.route)
            }
        }
    }
}
```

**`Channel<T>`:**
```kotlin
private val _events = Channel<UiEvent>(Channel.BUFFERED)
val events = _events.receiveAsFlow()

// Emit:
viewModelScope.launch { _events.send(UiEvent.Navigate("Detail")) }
```

**Preference:** `Channel` is simpler for one-shot events where there's exactly one consumer (UI). `SharedFlow` is better for broadcast (multiple observers).

### Memory Trick

```
Pick the right observable type:
  Current UI state (show loading/content/error)  →  StateFlow
  One-shot event, single consumer (navigation)   →  Channel
  One-shot event, multiple observers             →  SharedFlow(replay=0)
  Legacy View system, simple lifecycle           →  LiveData (acceptable)

StateFlow duplicate trap mnemonic:
  "StateFlow COMPARES, Channel DELIVERS"
  navigate("Detail") twice via StateFlow → second is LOST (same value)
  navigate("Detail") twice via Channel   → both arrive (queue-based)
```

---

## Q13.5 — Dependency Injection

> **Builds on:** [Q2.5.6 — Constructor visibility and factory](02_5_initialization_mechanics.md#q256--constructor-visibility-and-factory-patterns) · [Q2.5.2 — @Inject constructor](02_5_initialization_mechanics.md#q252--primary-vs-secondary-constructors)
> **Connects to:** [Q13.2 — Clean Architecture layers](13_android_architecture.md#q132--clean-architecture-layer-boundaries)
> **Reference:** [Hilt Docs](https://developer.android.com/training/dependency-injection/hilt-android)

### The Concrete Picture

Starting state — manual dependency construction (no DI):
```kotlin
class MainActivity : AppCompatActivity() {
    override fun onCreate(...) {
        val db = Room.databaseBuilder(this, AppDatabase::class.java, "app.db").build()
        val dao = db.userDao()
        val api = Retrofit.Builder().baseUrl("...").build().create(UserApi::class.java)
        val repo = UserRepositoryImpl(api, dao)        // manual wiring
        val vm = UserViewModel(repo)                   // manual wiring
        // Problem: every Activity recreates the graph; no sharing; testing = nightmare
    }
}
```

After Hilt — construction graph generated at compile time:
```
@HiltAndroidApp MyApp
    └── generates: SingletonComponent (Dagger component)
            ├── @Singleton AppDatabase (one instance, lives forever)
            ├── @Singleton UserApi
            └── @Singleton UserRepositoryImpl

@AndroidEntryPoint MainActivity
    └── by viewModels()
            └── Hilt generates UserViewModel_Factory
                    └── injects UserRepositoryImpl from SingletonComponent
```
Direction: Hilt PUSHES deps into objects; objects do not PULL from a registry.

### First Principles: DI vs Service Locator

**Dependency Injection:** Dependencies are provided TO an object FROM outside — the object declares what it needs in its constructor, and something else provides those dependencies.

```kotlin
// DI: UserRepository tells you what it needs (API, DB), someone provides them
class UserRepository(
    private val api: UserApi,  // injected by DI container
    private val db: UserDao   // injected by DI container
)
```

**Service Locator:** The object itself asks a global registry for its dependencies.

```kotlin
// Service Locator: object pulls from global registry
class UserRepository {
    private val api = ServiceLocator.get<UserApi>()    // pull from global registry
    private val db = ServiceLocator.get<UserDao>()     // pull from global registry
}
```

**Is Koin DI or Service Locator?**
Koin is technically a **Service Locator** with DI syntax. It uses a global module registry that objects query at runtime (`inject()` or `get()`). True DI (like Dagger/Hilt) uses code generation to provide dependencies at compile time with no global registry.

This matters for testing: with true DI, you provide test doubles through the constructor. With Koin, you must configure the global registry for tests.

### How Hilt Works Under the Hood

`@HiltAndroidApp` on your `Application` class triggers code generation:

```kotlin
@HiltAndroidApp
class MyApp : Application()
```

Hilt's annotation processor (KAPT/KSP) generates:

```java
// Generated by Hilt:
public final class MyApp_HiltComponents {
    // Dagger component hierarchy:
    // SingletonComponent → ActivityComponent → ViewModelComponent → ...

    @Component
    @Singleton
    public interface SingletonC extends // all singleton bindings
}
```

At runtime, a `DaggerMyApp_HiltComponents_SingletonC` Dagger component is created and provides all `@Singleton` bindings.

### Hilt Scopes

| Annotation | Lifetime | Component |
|-----------|---------|-----------|
| `@Singleton` | App lifetime (one instance per app) | `SingletonComponent` |
| `@ActivityScoped` | Activity lifetime | `ActivityComponent` |
| `@ViewModelScoped` | ViewModel lifetime | `ViewModelComponent` |
| `@FragmentScoped` | Fragment lifetime | `FragmentComponent` |

```kotlin
@Module
@InstallIn(SingletonComponent::class)
object DatabaseModule {
    @Provides
    @Singleton  // one database for the whole app
    fun provideDatabase(@ApplicationContext context: Context): AppDatabase {
        return Room.databaseBuilder(context, AppDatabase::class.java, "app.db").build()
    }

    @Provides
    @Singleton
    fun provideUserDao(db: AppDatabase): UserDao = db.userDao()
}
```

### `@Binds` vs `@Provides`

**`@Provides`:** Used when you need to write code to construct the instance:
```kotlin
@Provides
fun provideOkHttp(interceptor: AuthInterceptor): OkHttpClient {
    return OkHttpClient.Builder()
        .addInterceptor(interceptor)
        .build()
}
```

**`@Binds`:** Tells Hilt "use THIS implementation when THAT interface is requested." No code needed — just a declaration:
```kotlin
@Binds
abstract fun bindUserRepository(impl: UserRepositoryImpl): UserRepository
// When UserRepository is needed, provide UserRepositoryImpl
```

`@Binds` generates more efficient code than `@Provides` — no extra factory class.

### How `@HiltViewModel` Generates a ViewModelFactory

```kotlin
@HiltViewModel
class UserViewModel @Inject constructor(
    private val repository: UserRepository,
    private val savedState: SavedStateHandle
) : ViewModel()
```

Hilt generates a `UserViewModel_HiltModules` that registers a factory in the `ViewModelComponent`. When `by viewModels()` is called, Android's `ViewModelProvider` uses this factory, which asks Hilt's component for the dependencies.

You never write a `ViewModelFactory` — Hilt generates it from the `@HiltViewModel` annotation.

### Memory Trick

```
DI vs Service Locator:
  DI: "Here are your dependencies" (pushed in via constructor)
  SL: "Go get your dependencies" (object calls global registry)
  Koin = Service Locator with DI syntax (global module, runtime lookup)
  Hilt/Dagger = true DI (compile-time graph, no global registry)

@Binds vs @Provides:
  @Binds   = declaration ("use THIS impl for THAT interface") — no code
  @Provides = construction ("here is how to BUILD the instance") — has code

Hilt scope ladder: Singleton → Activity → ViewModel → Fragment
  "Outer scopes can inject into inner, never the reverse"
```

---

## Q13.6 — Repository and Offline-First Patterns

> **Builds on:** [Q13.2 — Clean Architecture](13_android_architecture.md#q132--clean-architecture-layer-boundaries) · [Q11.3 — StateFlow](11_flow.md#q113--stateflow-vs-sharedflow)
> **Connects to:** [Q13.7 — Error Handling](13_android_architecture.md#q137--error-handling-across-layers) · [Q14.1 — Room](14_jetpack_components.md#q141--room--internals) · [Q15.1 — OkHttp](15_networking.md#q151--okhttp-interceptor-chain)

### The Concrete Picture

Starting state — UI reads directly from network (no offline support):
```
User opens app
    │
    ▼
ViewModel calls api.getUsers()           ← network-only
    │ network available  →  list appears
    │ network unavailable →  blank screen, error
    └── no local cache, no persistence
```

After Single Source of Truth with Room:
```
User opens app
    │
    ▼
ViewModel calls userDao.observeAll()     ← Flow<List<User>> from Room
    │  immediately emits cached DB data  →  list appears instantly (even offline)
    │
    ▼ (in parallel)
refreshUsers()
    │  api.getUsers()                    ← network fetch
    │  userDao.insertAll(response)       ← write to Room
    │  Room InvalidationTracker fires
    └──────────────────────────────────► Flow emits new data → UI auto-updates

Offline scenario: network step fails → Room still has old data → no blank screen
```

Optimistic update direction:
```
User taps Like
    │
    ├──► DB write immediately (+1 like)  →  UI shows "Liked" instantly (t=0ms)
    │
    └──► api.likePost() in background    (t=~300ms)
              │ success → nothing to do (DB already correct)
              └── failure → DB write (-1 like) → Flow emits → UI shows "Not liked"
```

### The Single Source of Truth Pattern

```
WITHOUT single source of truth:
┌──────────┐  fetch  ┌──────────┐       ┌──────────┐
│   UI     │────────►│  Network │       │ Database │
└──────────┘◄────────└──────────┘       └──────────┘
             display   data                (unused)
Problem: UI shows network data directly; no offline support

WITH single source of truth (Room as SSoT):
┌──────────┐  observe  ┌──────────┐  write  ┌──────────┐
│   UI     │──────────►│ Room DB  │◄────────│  Network │
└──────────┘◄──────────└──────────┘         └──────────┘
             display    (source of truth)     (updates DB)
Benefit: UI always shows DB state; offline works; network updates DB
```

```kotlin
// Repository implementing SSoT:
class UserRepository(
    private val api: UserApi,
    private val userDao: UserDao
) {
    // UI observes Room — always shows fresh DB state:
    fun observeUsers(): Flow<List<User>> = userDao.observeAll().map { it.toDomain() }

    // Trigger network refresh:
    suspend fun refreshUsers() {
        val users = api.getUsers()  // fetch from network
        userDao.insertAll(users.toEntity())  // write to DB
        // Room Flow auto-emits the new data to UI!
    }
}
```

### The `NetworkBoundResource` Pattern

```
1. Emit cached data immediately (fast first load)
2. Start network request in background
3. On network success: update cache (DB)
4. Room auto-emits updated data to UI
5. On network failure: UI already has cached data — no blank screen

Flow:
emit(db.getData())    ← step 1: immediate
api.getData()         ← step 2: background
db.insert(newData)    ← step 3: update cache
                      ← step 4: Room emits → UI updates
```

```kotlin
fun <T, E> networkBoundResource(
    dbQuery: () -> Flow<T>,
    networkFetch: suspend () -> E,
    saveToDb: suspend (E) -> Unit,
    shouldFetch: (T) -> Boolean = { true }
) = flow {
    val cachedData = dbQuery().first()
    emit(Resource.Loading(cachedData))  // emit cached immediately

    if (shouldFetch(cachedData)) {
        try {
            val networkData = networkFetch()
            saveToDb(networkData)
            emitAll(dbQuery().map { Resource.Success(it) })
        } catch (e: Exception) {
            emitAll(dbQuery().map { Resource.Error(e, it) })
        }
    } else {
        emitAll(dbQuery().map { Resource.Success(it) })
    }
}
```

### Optimistic Updates — Write Locally, Sync in Background

Optimistic updates improve perceived performance: show the result immediately in the UI, then sync to the server in the background. If the server rejects it, roll back.

```kotlin
// Repository — optimistic update with rollback:
class PostRepository(private val api: PostApi, private val postDao: PostDao) {

    suspend fun likePost(postId: String): Result<Unit> {
        // 1. Optimistic write — update DB immediately:
        postDao.updateLikeCount(postId, increment = +1)

        return try {
            // 2. Sync to server:
            api.likePost(postId)
            Result.success(Unit)
        } catch (e: Exception) {
            // 3. Rollback on failure:
            postDao.updateLikeCount(postId, increment = -1)
            Result.failure(e)
        }
    }
}
```

```
Timeline:
t=0ms:   User taps Like → DB updated immediately → UI shows "Liked" ✓
t=0ms:   Network call starts in background
t=300ms: Network succeeds → no action needed (DB already correct)
         OR
t=300ms: Network fails → DB rolled back → UI shows "Not liked" again
```

**Why Room + Flow makes rollback automatic:** Because UI observes Room via Flow, the rollback write automatically triggers a new emission — the UI reverts without any manual state management.

### Conflict Resolution Strategies

When offline edits and server data diverge, you need a strategy:

| Strategy | Description | Use When |
|----------|-------------|----------|
| **Last-Write-Wins (LWW)** | Most recent timestamp wins, overwriting earlier writes | Simple data with infrequent edits; user settings |
| **Server-Wins** | Server data always overrides local | Financial data, inventory; correctness > UX |
| **Client-Wins** | Local data overrides server | Drafts; user's own content |
| **Field-Level Merge** | Merge non-conflicting fields, flag conflicts for user | Collaborative documents; contact edits |
| **CRDTs** (Conflict-free Replicated Data Types) | Mathematically guaranteed convergence, no conflicts possible | Counters, sets, distributed text editing |

```kotlin
// Last-Write-Wins implementation:
data class Note(
    val id: String,
    val content: String,
    val updatedAt: Long  // timestamp — LWW key
)

fun resolveConflict(local: Note, server: Note): Note {
    return if (local.updatedAt > server.updatedAt) local else server
    // Whoever wrote most recently wins
}

// Field-level merge (non-conflicting fields):
fun mergeUser(local: User, server: User): User {
    return User(
        id = server.id,
        name = if (local.nameUpdatedAt > server.nameUpdatedAt) local.name else server.name,
        email = if (local.emailUpdatedAt > server.emailUpdatedAt) local.email else server.email,
        // Fields not modified locally always take server value:
        avatar = server.avatar
    )
}
```

### Memory Trick

```
SSoT flow direction:
  Network ──► Room ◄── UI observes
  "Network feeds Room; Room feeds UI; network never feeds UI directly"

Conflict resolution decision tree:
  Simple / infrequent edits    →  Last-Write-Wins (timestamp comparison)
  Financial / inventory        →  Server-Wins (correctness > UX)
  User's own content / drafts  →  Client-Wins
  Collaborative docs           →  Field-Level Merge or CRDTs

Optimistic update rollback is FREE when using Room + Flow:
  Rollback write → Room emits → UI reverts automatically (no setState needed)
```

---

## Q13.7 — Error Handling Across Layers

> **Builds on:** [Q13.6 — Repository](13_android_architecture.md#q136--repository-and-offline-first-patterns) · [Q10.3 — Coroutine exception handling](10_structured_concurrency.md#q103--exception-handling-rules)
> **Connects to:** [Q4.3 — CancellationException](04_functions_lambdas_inlining.md#q43--higher-order-functions-with-suspend)

### The Concrete Picture

Starting state — HttpException leaking across all layers:
```kotlin
// ViewModel (Presentation layer) — knows about HTTP status codes: BAD
catch (e: HttpException) {
    if (e.code() == 401) navigateToLogin()   // HTTP vocabulary in UI layer!
    if (e.code() == 404) showNotFound()
}
```

After translation at the Data→Domain boundary:
```
Data layer (UserRepositoryImpl):
    HttpException(401)  ──►  throw AppError.Unauthorized
    HttpException(404)  ──►  throw AppError.NotFound("User $id")
    HttpException(5xx)  ──►  throw AppError.ServerError
    IOException         ──►  throw AppError.NetworkError

Domain boundary (sealed class AppError — no Retrofit imports)

ViewModel (Presentation):
    catch (e: AppError) {
        AppError.Unauthorized  ──►  UiState.Error.SessionExpired
        AppError.NetworkError  ──►  UiState.Error.Offline
        AppError.NotFound      ──►  UiState.Error.NotFound(e.resource)
    }

UI:
    UiState.Error.SessionExpired  ──►  navController.navigate(loginScreen)
    UiState.Error.Offline         ──►  show snackbar + retry button
```
Each layer translates to its own vocabulary — no type crosses the boundary.

### First Principles: Why Layers Need Different Error Types

The Data layer speaks HTTP (status codes, IOExceptions). The Domain layer should speak business language (UserNotFound, Unauthorized). The UI layer speaks user experience (show error dialog, navigate to login). Each layer has its own vocabulary — translation happens at the boundary.

```
HTTP 401 (Data layer term)
    │ translated at Data→Domain boundary
    ▼
AppError.Unauthorized (Domain term)
    │ translated at Domain→Presentation boundary
    ▼
UiState.Error.SessionExpired (UI term)
    │
    ▼
Navigate to LoginScreen (user experience)
```

### Where HTTP Exceptions Should Be Converted

**In the Data layer** — specifically in the repository implementation. Never let `HttpException` or `IOException` leak into the domain or presentation layers. Those are framework/library types — the domain should be framework-agnostic.

```kotlin
// WRONG — HttpException leaks into Domain/ViewModel:
class UserViewModel : ViewModel() {
    fun loadUser(id: String) {
        viewModelScope.launch {
            try {
                val user = repository.getUser(id)
                _state.value = UiState.Content(user)
            } catch (e: HttpException) {       // HttpException is a Retrofit type!
                if (e.code() == 401) { ... }   // domain logic knows about HTTP — BAD
            }
        }
    }
}

// CORRECT — Data layer translates, ViewModel speaks domain language:
// Data layer:
class UserRepositoryImpl : UserRepository {
    override suspend fun getUser(id: String): User {
        try {
            return api.getUser(id).toDomain()
        } catch (e: HttpException) {
            throw when (e.code()) {
                401 -> AppError.Unauthorized           // domain error
                404 -> AppError.NotFound("User $id")   // domain error
                500, 503 -> AppError.ServerError        // domain error
                else -> AppError.Unknown(e.message())
            }
        } catch (e: IOException) {
            throw AppError.NetworkError                 // domain error
        }
    }
}
```

### The `sealed class AppError` Pattern

A sealed class for domain errors gives the ViewModel exhaustive, type-safe error handling:

```kotlin
// Domain layer — AppError sealed hierarchy:
sealed class AppError : Exception() {
    object Unauthorized : AppError()            // needs re-login
    object NetworkError : AppError()            // no connection
    object ServerError : AppError()             // 5xx
    data class NotFound(val resource: String) : AppError()
    data class ValidationError(val field: String, val message: String) : AppError()
    data class Unknown(val cause: String?) : AppError()
}
```

**What this enables in the ViewModel:**

```kotlin
class UserViewModel(private val repository: UserRepository) : ViewModel() {

    fun loadUser(id: String) {
        viewModelScope.launch {
            _state.value = UiState.Loading
            try {
                val user = repository.getUser(id)
                _state.value = UiState.Content(user)
            } catch (e: CancellationException) {
                throw e  // MUST re-throw — never swallow!
            } catch (e: AppError) {
                _state.value = when (e) {
                    is AppError.Unauthorized -> UiState.Error.SessionExpired
                    is AppError.NetworkError -> UiState.Error.Offline
                    is AppError.NotFound -> UiState.Error.NotFound(e.resource)
                    is AppError.ServerError -> UiState.Error.ServerError
                    else -> UiState.Error.Generic
                }
            }
        }
    }
}
```

The `when (e)` is **exhaustive** — if you add a new `AppError` subtype and forget to handle it in the ViewModel, the compiler forces you to add the case. No silent unhandled errors.

### Differentiating 401 vs 500 in the ViewModel

```kotlin
// UI state models for different error types:
sealed class UiState {
    object Loading : UiState()
    data class Content(val user: User) : UiState()
    sealed class Error : UiState() {
        object SessionExpired : Error()   // 401 → navigate to login
        object Offline : Error()          // no network → show retry
        object ServerError : Error()      // 5xx → show "try again later"
        data class NotFound(val resource: String) : Error()
        object Generic : Error()
    }
}

// Activity/Fragment observes and routes:
viewModel.uiState.collect { state ->
    when (state) {
        is UiState.Error.SessionExpired -> {
            // Clear auth tokens, navigate to login
            authManager.clearTokens()
            navController.navigate(R.id.loginFragment)
        }
        is UiState.Error.Offline -> {
            snackbar.show("No internet connection. Tap to retry.")
            retryButton.isVisible = true
        }
        is UiState.Error.ServerError -> {
            snackbar.show("Something went wrong. Try again later.")
        }
        // ...
    }
}
```

### What Happens When `CancellationException` Hits `catch (e: Exception)`

`CancellationException` is a subclass of `Exception` (via `IllegalStateException`). A `catch (e: Exception)` block will catch it — and if you don't re-throw, the coroutine continues running despite being cancelled.

```kotlin
// WRONG — swallows CancellationException:
viewModelScope.launch {
    try {
        val user = repository.getUser(id)
        _state.value = UiState.Content(user)
    } catch (e: Exception) {          // catches CancellationException!
        _state.value = UiState.Error.Generic  // runs even after cancel!
    }
}
// viewModel.onCleared() calls viewModelScope.cancel()
// → CancellationException thrown at repository.getUser()
// → catch(e: Exception) catches it
// → _state.value = UiState.Error.Generic  ← wrong! Should not show error on cancel
// → coroutine finishes "normally" from scope's perspective — but scope is cancelled
```

```kotlin
// CORRECT — always re-throw CancellationException:
viewModelScope.launch {
    try {
        val user = repository.getUser(id)
        _state.value = UiState.Content(user)
    } catch (e: CancellationException) {
        throw e  // re-throw FIRST, before general catch
    } catch (e: AppError) {
        _state.value = mapToUiError(e)
    }
}

// OR: use the coroutines helper:
try {
    ...
} catch (e: Exception) {
    if (e is CancellationException) throw e  // re-throw
    // handle other exceptions
}
```

```
CancellationException flow when swallowed vs re-thrown:

Swallowed:
  cancel() → CancellationException → catch(Exception) catches → coroutine
  runs error handling → scope thinks it's still running → LEAK

Re-thrown:
  cancel() → CancellationException → re-thrown → coroutine terminates
  cleanly → scope cleanup completes → no leak
```

> **Interview Trap:** This is one of the most common production bugs. `catch (e: Exception)` blocks in ViewModels that don't re-throw `CancellationException` cause coroutine leaks and show error UI when the user simply navigated away.

### Memory Trick

```
Error translation direction — always translate INWARD:
  Data    →  throws AppError (translates HTTP codes)
  Domain  →  catches AppError (passes it up or handles it)
  UI      →  maps AppError to UiState.Error (user-facing language)

CancellationException rule — "FIRST or RETHROW":
  catch (e: CancellationException) { throw e }  ← always first catch block
  catch (e: AppError) { ... }                   ← then domain errors

Why CancellationException must be rethrown:
  It IS-A Exception → generic catch swallows it
  Swallowed = coroutine keeps running despite scope cancellation = LEAK

Sealed AppError wins = exhaustive when() → compiler enforces all cases
  "Add AppError.RateLimit → compiler error in ViewModel → can't miss it"
```

---

## Master Summary: Android Architecture in 5 Points

```
┌──────────────────────────────────────────────────────────────────────┐
│  1. MVVM ≠ UDF. MVVM separates concerns. UDF is enforced by MVI.    │
│     Add UDF to MVVM with single StateFlow<State> + onEvent().       │
│                                                                       │
│  2. Repository interfaces in the DOMAIN layer — this is dependency  │
│     inversion. Domain doesn't depend on Data — Data depends on      │
│     Domain's interfaces.                                             │
│                                                                       │
│  3. ViewModel survives rotation (NonConfigInstances) but NOT         │
│     process death. SavedStateHandle survives both — uses Binder IPC │
│     with ~1MB limit. Large data → Room/DataStore.                   │
│                                                                       │
│  4. StateFlow filters duplicates — wrong for navigation events.     │
│     Use SharedFlow(replay=0) or Channel for one-shot events.        │
│                                                                       │
│  5. Room as single source of truth: UI observes Room, network       │
│     updates Room, Room auto-emits to UI. Enables offline-first.     │
└──────────────────────────────────────────────────────────────────────┘
```

---

*← [Phase 12 — Reflection & References](12_reference_operators_and_reflection.md) | [Phase 14 — Jetpack Components →](14_jetpack_components.md)*
