# Phase A3 — Android Architecture Patterns

Architecture is the first thing senior Android engineers are tested on. "Walk me through how you'd design this feature" and "why did you choose MVVM over MVP" separate junior developers who know how to code from senior engineers who know how to build systems. Android makes architecture uniquely hard: your components (Activity, Fragment, Service) have lifecycles the OS controls, your state can be destroyed at any moment, and your app must remain responsive while doing network I/O and database work on background threads. Every architecture pattern in Android exists to answer the same question: who owns state, who updates it, and how does the UI react to changes without getting into an inconsistent state?

---

## A3.1 — Why Architecture Matters in Android

> **Connects to:** [A1.1 — Activity Lifecycle](A1_activity_fragment.md#a11--activity-lifecycle) · [A1.2 — Configuration Changes](A1_activity_fragment.md#a12--configuration-changes)

### WHY: The Three Forces That Make Android Architecture Hard

```
Force 1: LIFECYCLE
  Activities and Fragments are created and destroyed by the OS.
  You don't control when. Your code must handle being interrupted
  at any point.

Force 2: CONFIGURATION CHANGES
  Rotation, locale change, multi-window resize → Activity is
  DESTROYED and RECREATED. All local state is lost unless you
  explicitly save and restore it.

Force 3: PROCESS DEATH
  The OS can kill your process at any time when backgrounded.
  The next launch looks like a cold start. All in-memory state
  is gone. Only persisted data (DB, SharedPreferences, Files)
  survives.

A bad architecture fails one or more of these forces.
A good architecture handles all three.
```

### The God Object: What Bad Android Code Looks Like

This is the codebase almost every Android developer inherits at some point:

```kotlin
class MainActivity : AppCompatActivity() {
    // State owned by the Activity — lost on rotation
    private var users = mutableListOf<User>()
    private var currentPage = 0
    private var isLoading = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        // Business logic in the Activity
        if (currentUser.isAdmin) {
            showAdminPanel()
        }

        // Network calls on the main thread (ANR risk)
        val users = URL("https://api.example.com/users").readText()

        // Or: async network that callbacks into a destroyed Activity
        fetchUsersFromNetwork { result ->
            // Is this Activity still alive? We don't know!
            updateUI(result)  // Crash if Activity is destroyed
        }

        // Direct DB access
        val db = Room.databaseBuilder(this, AppDatabase::class.java, "db").build()
        val localUsers = db.userDao().getAll()   // BLOCKS MAIN THREAD → ANR
    }
}
```

**Problems with this approach:**
1. `users` and `currentPage` are lost on rotation → user sees empty list after rotating
2. Network callback fires into a destroyed Activity → NullPointerException or crash
3. DB query on main thread → ANR after 5 seconds
4. Testing is impossible: you cannot instantiate an Activity in a JUnit test
5. 500-line Activity files where nothing is reusable

### What Good Architecture Buys

```
Testability:    Business logic can be tested with pure JUnit/Kotlin tests,
                no Android emulator needed.

Maintainability: Features are isolated. Changing the data layer doesn't
                 break the UI layer. Adding a new screen doesn't require
                 touching existing code.

Predictability: The UI is a function of the state. Given the same state,
                the UI always looks the same. No accidental mutations.

Survivability:  Handles rotation, process death, and lifecycle changes
                without losing state or crashing.
```

### The Three Architectural Principles

These three principles run through every pattern (MVP, MVVM, MVI, Clean):

```
1. SEPARATION OF CONCERNS
   Each class has one job. UI draws. Business logic computes.
   Data layer fetches. Nobody does everything.

2. SINGLE SOURCE OF TRUTH
   Each piece of data has exactly ONE canonical location.
   UI reads from it. Updates write to it. Everyone reads the
   same version. No two copies that can go out of sync.

3. UNIDIRECTIONAL DATA FLOW (UDF)
   Data flows in one direction: from source → state → UI.
   User interactions flow the opposite way: UI → action → state mutation.

   State          →      UI
                         │
   (updated)             │ user action
        ↑                ↓
       ViewModel  ←  UI sends intent/event
```

---

## A3.2 — MVC: The Starting Point (and Why It Fails)

> **Connects to:** [A3.3 — MVP](A3_architecture_patterns.md#a33--mvp-extracting-the-presenter)

### WHY This Matters

MVC is the pattern you inherit in legacy codebases and the pattern that every question about "why did you choose X" references as the thing being improved upon. Understanding exactly WHY it breaks in Android lets you explain your architectural choices intelligently.

### MVC in Theory

```
Model-View-Controller (theory):

  ┌──────────┐  updates   ┌──────────┐
  │  Model   │ ─────────► │   View   │
  │  (data)  │            │  (UI)    │
  └──────────┘            └──────────┘
       ▲                       │
       │ manipulates           │ user events
       │                       ▼
       └──────────────── Controller
```

- **Model**: data + business rules. Knows nothing about UI.
- **View**: displays data. Knows nothing about business logic.
- **Controller**: handles user input, updates Model, tells View what to show.

Clean separation. Each layer independently testable. Works great in desktop apps where the Controller is a stable, long-lived object.

### MVC in Android Reality

```
Android MVC (reality):

  Activity / Fragment
  ┌─────────────────────────────────────────────────────┐
  │  Controller role: handles button clicks, navigation  │
  │  View role:       inflates layout, updates TextView   │
  │  Also:            manages lifecycle, handles rotation │
  │  Also:            calls network, queries database      │
  └─────────────────────────────────────────────────────┘
            │
            │  barely separated
            ▼
        Model (User.kt, UserRepository.kt)
```

The Activity is BOTH the View AND the Controller. It cannot be separated because:
1. Layout inflation (`setContentView`) lives in Activity
2. Lifecycle callbacks (`onResume`, `onStop`) live in Activity
3. Context (needed for almost everything) lives in Activity
4. You cannot instantiate Activity in a JUnit test

### Directory Structure

```
com.example.app/
├── MainActivity.kt              ← View + Controller merged
├── ProfileActivity.kt
├── model/
│   ├── User.kt                  ← POJO / data class
│   └── UserRepository.kt        ← sometimes here, often still in Activity
└── utils/
    └── NetworkUtils.kt
```

### The Two Critical Failure Modes

**Failure 1: Lifecycle callback after destruction**

```kotlin
class UserActivity : AppCompatActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // Callback-based network call
        userApi.fetchUser(userId) { user ->
            // ❌ Activity may be destroyed by now (user pressed Back while fetching)
            nameTextView.text = user.name  // NullPointerException or no-op
        }
    }
}
```

**Failure 2: Untestable business logic**

```kotlin
// You want to test "if user is admin, show admin panel"
// But this logic is inside onCreate() — cannot call without Android runtime

// No way to write:
// val activity = UserActivity()   ← FAILS: needs Activity context, instrumentation
// activity.testAdminLogic()
```

### When MVC Is Acceptable

- Proof-of-concept or throwaway prototype
- Single-screen, no network, no background work
- Screens that will be deleted/rewritten soon

### Interview Traps

**"Why doesn't pure MVC work in Android?"**
The Activity serves as both View and Controller simultaneously. It cannot be separated because layout inflation, lifecycle callbacks, and Android Context access all live in Activity. The combined View+Controller cannot be unit tested without an Android runtime.

**"What specific bugs does MVC cause?"**
1. Network callbacks fire into destroyed Activities → crash
2. State stored in Activity → lost on rotation → user sees blank screen after rotating
3. Cannot mock the View layer → cannot write unit tests for business logic

---

## A3.3 — MVP: Extracting the Presenter

> **Builds on:** [A3.2 — MVC](A3_architecture_patterns.md#a32--mvc-the-starting-point-and-why-it-fails)
> **Connects to:** [A3.4 — MVVM](A3_architecture_patterns.md#a34--mvvm-viewmodel--observable-state)

### WHY MVP

MVP extracts the business logic from the Activity into a **Presenter** — a plain Kotlin/Java class with no Android dependencies. The Activity becomes a thin "View" that implements a View interface. The Presenter talks to the View through that interface. Now the Presenter can be unit-tested with a mock View.

### Structure

```
MVP Data Flow:

  ┌─────────────────────────┐
  │  View (Activity/Fragment)│
  │  implements UserView      │
  └──────────┬───────────────┘
             │ calls presenter.loadUser(id)
             ▼
  ┌─────────────────────────┐
  │      UserPresenter       │
  │  (pure Kotlin class)     │◄── View interface (not Activity!)
  └──────────┬───────────────┘
             │ calls repository
             ▼
  ┌─────────────────────────┐
  │     UserRepository       │
  │  (data layer)            │
  └─────────────────────────┘
```

### Directory Structure

```
com.example.app/
├── ui/
│   ├── user/
│   │   ├── UserActivity.kt         ← implements UserView, has NO business logic
│   │   ├── UserView.kt             ← interface: showUser(), showLoading(), showError()
│   │   └── UserPresenter.kt        ← pure JVM class, all business logic here
│   ├── product/
│   │   ├── ProductFragment.kt
│   │   ├── ProductView.kt
│   │   └── ProductPresenter.kt
│   └── base/
│       ├── BaseView.kt             ← showLoading(), hideLoading() (common contract)
│       └── BasePresenter.kt        ← attachView(), detachView()
├── data/
│   ├── repository/
│   │   ├── UserRepository.kt       ← interface
│   │   └── UserRepositoryImpl.kt
│   ├── remote/
│   │   └── UserApiService.kt
│   └── model/
│       └── User.kt
└── di/
    └── AppComponent.kt
```

### The View Interface Contract

```kotlin
// UserView.kt
interface UserView {
    fun showUser(user: User)
    fun showLoading()
    fun hideLoading()
    fun showError(message: String)
    fun navigateToDetail(userId: String)
}

// UserActivity.kt
class UserActivity : AppCompatActivity(), UserView {
    private lateinit var presenter: UserPresenter

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_user)
        presenter = UserPresenter(UserRepositoryImpl())
        presenter.attachView(this)
        presenter.loadUser(intent.getStringExtra("userId")!!)
    }

    override fun onDestroy() {
        presenter.detachView()  // CRITICAL: prevent memory leak
        super.onDestroy()
    }

    override fun showUser(user: User) {
        nameTextView.text = user.name    // pure UI, no logic
    }

    override fun showLoading() { progressBar.isVisible = true }
    override fun hideLoading() { progressBar.isVisible = false }
    override fun showError(message: String) {
        Toast.makeText(this, message, Toast.LENGTH_SHORT).show()
    }
    override fun navigateToDetail(userId: String) {
        startActivity(Intent(this, UserDetailActivity::class.java)
            .putExtra("userId", userId))
    }
}
```

```kotlin
// UserPresenter.kt — 100% pure JVM, testable with JUnit
class UserPresenter(private val repository: UserRepository) {
    private var view: UserView? = null

    fun attachView(view: UserView) { this.view = view }

    fun detachView() { this.view = null }    // breaks strong reference

    fun loadUser(userId: String) {
        view?.showLoading()
        repository.getUser(userId) { result ->
            view?.hideLoading()
            when (result) {
                is Result.Success -> view?.showUser(result.data)
                is Result.Error   -> view?.showError(result.message)
            }
        }
    }
}
```

### Unit Testing the Presenter

```kotlin
// UserPresenterTest.kt — runs on JVM, no emulator needed
class UserPresenterTest {
    private val mockView = mock(UserView::class.java)
    private val mockRepo = mock(UserRepository::class.java)
    private val presenter = UserPresenter(mockRepo)

    @Before fun setup() { presenter.attachView(mockView) }

    @Test fun `loadUser shows user on success`() {
        val user = User("Alice")
        whenever(mockRepo.getUser(any(), any())).thenAnswer {
            (it.arguments[1] as (Result<User>) -> Unit)(Result.Success(user))
        }
        presenter.loadUser("123")

        verify(mockView).showLoading()
        verify(mockView).hideLoading()
        verify(mockView).showUser(user)
        verify(mockView, never()).showError(any())
    }
}
```

### The Memory Leak Problem and Solution

```
Without detachView():

   Presenter  ────────────── strong ref ──────────────► Activity
   (lives in callback)                                   (destroyed)

   Background thread keeps Presenter alive.
   Presenter keeps Activity alive.
   Activity cannot be GC'd → LEAK.

With detachView() in onDestroy():

   Presenter  ──── view = null ─── Activity is free to be GC'd
```

**WeakReference alternative** (Presenter survives config change):

```kotlin
class UserPresenter(private val repository: UserRepository) {
    private var viewRef: WeakReference<UserView>? = null

    fun attachView(view: UserView) {
        viewRef = WeakReference(view)
    }

    private fun getView(): UserView? = viewRef?.get()

    fun loadUser(userId: String) {
        repository.getUser(userId) { result ->
            getView()?.let { view ->   // null if Activity is gone
                when (result) {
                    is Result.Success -> view.showUser(result.data)
                    is Result.Error   -> view.showError(result.message)
                }
            }
        }
    }
}
```

### MVP Problems That MVVM Solves

```
Problem 1: Presenter still holds View reference (even if weak)
           → if rotation creates new Activity, old Presenter
             needs to be handed to new Activity (complex)

Problem 2: Each screen requires: View interface + Activity + Presenter
           → 3 files per screen, boilerplate explosion at scale

Problem 3: Presenter is recreated on rotation
           → Data must be refetched or re-saved → bad UX

Problem 4: Presenter-View coupling is 1:1
           → cannot share Presenter between screens easily
```

### Interview Q&A

**"How do you prevent a memory leak in MVP?"**
Call `presenter.detachView()` in `onDestroy()`, setting the View reference to null. Alternatively, use a `WeakReference<ViewInterface>` so the Presenter doesn't prevent the Activity from being garbage collected.

**"What happens if a network response returns after the Activity is destroyed in MVP?"**
Without `detachView()`: the callback fires, `view.showUser()` is called on a null or destroyed view → either NPE (no null check) or no-op (with null check) + the Activity is leaked in memory. With proper detach: `getView()` returns null, the callback is a no-op, Activity is GC'd normally.

**"How does MVP handle rotation?"**
Poorly, without extra work. On rotation, the Activity is destroyed and recreated, but the Presenter is also recreated (unless you manually retain it). You have to re-fetch or re-display data from scratch. This is why MVVM's `ViewModel` (which survives rotation via `ViewModelStore`) is a significant improvement.

---

## A3.4 — MVVM: ViewModel + Observable State

> **Builds on:** [A3.3 — MVP](A3_architecture_patterns.md#a33--mvp-extracting-the-presenter)
> **Connects to:** [A1.2 — Configuration Changes & ViewModel](A1_activity_fragment.md#a12--configuration-changes)

### WHY MVVM Is the Recommended Android Architecture

MVVM solves all three MVP problems at once:
1. **No View reference in ViewModel**: ViewModel exposes observable state; UI observes it. No leaks.
2. **ViewModel survives config changes**: `ViewModelStore` is retained on rotation; no data re-fetch.
3. **Less boilerplate**: no View interface required — any observer can collect state.

### Structure

```
MVVM Unidirectional Data Flow:

  User Action
     │
     ▼
  Fragment/Activity
     │ calls ViewModel.loadUsers()
     ▼
  ViewModel  ──── calls ──── Repository  ──── calls ──── Remote API
     │                          │                            │
     │                          │◄─── fetches data ──────────┘
     │                          │
     │                          ▼
     │                        Room DB
     │                          │
     │◄─── observes Flow ───────┘
     │
  StateFlow<UiState> updated
     │
     ▼
  Fragment observes stateFlow
     │
     ▼
  UI renders new state
```

### Complete MVVM Implementation

```kotlin
// UiState — the single source of truth for the screen
sealed class UserUiState {
    object Loading : UserUiState()
    data class Success(val users: List<User>) : UserUiState()
    data class Error(val message: String) : UserUiState()
}

// UserViewModel.kt
class UserViewModel(
    private val getUsersUseCase: GetUsersUseCase    // or Repository directly for simpler apps
) : ViewModel() {

    // StateFlow: always has a value, replays current state to new collectors
    private val _uiState = MutableStateFlow<UserUiState>(UserUiState.Loading)
    val uiState: StateFlow<UserUiState> = _uiState.asStateFlow()

    // SharedFlow: one-shot events (navigation, toasts) — no replay, no initial value
    private val _events = MutableSharedFlow<UserEvent>()
    val events: SharedFlow<UserEvent> = _events.asSharedFlow()

    init { loadUsers() }

    fun loadUsers() {
        viewModelScope.launch {             // cancelled when ViewModel is cleared
            _uiState.value = UserUiState.Loading
            try {
                val users = getUsersUseCase()
                _uiState.value = UserUiState.Success(users)
            } catch (e: Exception) {
                _uiState.value = UserUiState.Error(e.message ?: "Unknown error")
            }
        }
    }

    fun onUserClicked(userId: String) {
        viewModelScope.launch {
            _events.emit(UserEvent.NavigateToDetail(userId))
        }
    }

    fun onDeleteUser(user: User) {
        viewModelScope.launch {
            // Optimistic update: update state immediately
            val currentUsers = (_uiState.value as? UserUiState.Success)?.users ?: return@launch
            _uiState.value = UserUiState.Success(currentUsers - user)
            try {
                deleteUserUseCase(user.id)
            } catch (e: Exception) {
                // Revert on failure
                _uiState.value = UserUiState.Success(currentUsers)
                _events.emit(UserEvent.ShowError("Delete failed: ${e.message}"))
            }
        }
    }
}
```

```kotlin
// UserFragment.kt
class UserFragment : Fragment(R.layout.fragment_user) {

    private val viewModel: UserViewModel by viewModels()
    private var _binding: FragmentUserBinding? = null
    private val binding get() = _binding!!

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)
        _binding = FragmentUserBinding.bind(view)

        // Collect state — use viewLifecycleOwner (NOT this Fragment)
        viewLifecycleOwner.lifecycleScope.launch {
            viewLifecycleOwner.repeatOnLifecycle(Lifecycle.State.STARTED) {
                // Collect state (persistent state — survives back/restore)
                launch {
                    viewModel.uiState.collect { state ->
                        when (state) {
                            is UserUiState.Loading -> showLoading()
                            is UserUiState.Success -> showUsers(state.users)
                            is UserUiState.Error   -> showError(state.message)
                        }
                    }
                }
                // Collect events (one-time)
                launch {
                    viewModel.events.collect { event ->
                        when (event) {
                            is UserEvent.NavigateToDetail -> navigateToDetail(event.userId)
                            is UserEvent.ShowError -> showToast(event.message)
                        }
                    }
                }
            }
        }

        binding.retryButton.setOnClickListener { viewModel.loadUsers() }
    }

    override fun onDestroyView() {
        super.onDestroyView()
        _binding = null     // prevent ViewBinding memory leak (see A1.3)
    }
}
```

### Directory Structure

```
com.example.app/
├── ui/
│   ├── user/
│   │   ├── UserFragment.kt          ← thin UI, observes ViewModel
│   │   ├── UserViewModel.kt         ← state + business orchestration
│   │   ├── UserUiState.kt           ← sealed class for screen state
│   │   ├── UserEvent.kt             ← sealed class for one-time events
│   │   └── UserAdapter.kt           ← RecyclerView adapter
│   ├── product/
│   │   ├── ProductFragment.kt
│   │   ├── ProductViewModel.kt
│   │   └── ProductUiState.kt
│   └── shared/
│       └── SharedViewModel.kt       ← shared between fragments (activityViewModels)
├── domain/
│   ├── model/
│   │   └── User.kt                  ← domain entity (not Room entity!)
│   └── usecase/
│       ├── GetUsersUseCase.kt
│       └── DeleteUserUseCase.kt
├── data/
│   ├── repository/
│   │   ├── UserRepository.kt        ← interface
│   │   └── UserRepositoryImpl.kt
│   ├── remote/
│   │   ├── UserApiService.kt        ← Retrofit interface
│   │   └── dto/
│   │       └── UserDto.kt
│   └── local/
│       ├── AppDatabase.kt
│       ├── UserDao.kt
│       └── entity/
│           └── UserEntity.kt
├── di/
│   ├── AppModule.kt                 ← Hilt module
│   ├── NetworkModule.kt
│   └── DatabaseModule.kt
└── MyApplication.kt
```

### LiveData vs StateFlow vs SharedFlow Decision Guide

```
Observable Type    Lifecycle-aware?  Always has value?  Best for
─────────────────────────────────────────────────────────────────────
LiveData           YES (auto-stop   YES (nullable)       Legacy code, Databinding
                   on background)
StateFlow          NO (manual       YES (non-null)       Current screen state,
                   repeatOnLifecycle)                    active UI state
SharedFlow         NO               NO (configurable     One-time events:
                   (use             replay)              navigation, toasts,
                   repeatOnLifecycle)                    snackbars

Use StateFlow for: "what the screen looks like right now"
Use SharedFlow for: "something happened once, consume it once"
```

### Why ViewModel Survives Configuration Changes

```
Rotation sequence:
  1. Activity.onStop()
  2. Activity.onSaveInstanceState()
  3. Activity.onDestroy()  ← Activity object destroyed
     BUT:  ActivityThread retains Activity's NonConfigurationInstance
           which contains the ViewModelStore
           which contains all ViewModel objects
  4. New Activity created
  5. new Activity.getViewModelStore() returns the RETAINED store
  6. viewModels() delegate finds existing ViewModel in store
     → same ViewModel object, same StateFlow, same coroutine jobs

The ViewModel is only cleared when Activity.finish() is called
(user presses Back) or ActivityThread decides the Activity
is permanently done.
```

### Interview Traps

**"Can ViewModel hold a reference to Activity or Fragment?"**
No. ViewModel must never hold a reference to a Context, Activity, View, or Fragment. These objects are destroyed on rotation. A ViewModel holding a reference prevents garbage collection → memory leak. If you need context, use `AndroidViewModel` which holds `Application` context (never destroyed). If you need to update UI, use StateFlow or LiveData and let the UI observe.

**"What's the difference between LiveData and StateFlow?"**
LiveData is lifecycle-aware (auto-stops delivering values when Fragment is in the background without code), works with DataBinding, is nullable. StateFlow is Kotlin-first, always has a non-null value, requires `repeatOnLifecycle` for lifecycle awareness, works with Coroutines. For new code, prefer StateFlow.

**"How do you handle navigation events in MVVM?"**
Navigation is a one-time event — pressing Back should not re-navigate. Use a `SharedFlow` (replay=0) for navigation events and collect it in `repeatOnLifecycle`. A common mistake is putting navigation in a `StateFlow` which would replay the navigation on back-stack restoration, causing double navigation.

---

## A3.5 — MVI: Unidirectional Data Flow

> **Builds on:** [A3.4 — MVVM](A3_architecture_patterns.md#a34--mvvm-viewmodel--observable-state)

### WHY MVI

MVVM with multiple StateFlows and SharedFlows can still have inconsistent states: what if `isLoading` is true while `error` is also non-null? MVI solves this by collapsing ALL UI state into a SINGLE immutable data class. There is exactly one state. Any transition from one state to another goes through a defined reducer. Impossible states become impossible.

### MVI in Android: The Three Pillars

```
MVI Contract:

┌─────────────┐      Intent         ┌──────────────────┐
│    View      │ ─── (user action) ──►│                  │
│  (Compose /  │                      │    ViewModel     │
│  Fragment)   │                      │  (Reducer logic) │
│              │◄─── State update ───│                  │
│              │      (new state)     └────────┬─────────┘
└─────────────┘                               │
                                     SideEffect (emit once)
                                     └───► Navigation, Toast


Intent:     What the USER DID (sealed class of actions)
State:      What the SCREEN LOOKS LIKE (single data class)
SideEffect: What HAPPENS ONCE (navigation, snackbar, analytics)
```

### The Contract Object Pattern

```kotlin
// UserContract.kt — everything for this screen in one place
object UserContract {

    // The entire screen state in ONE data class
    // Impossible to have isLoading=true AND error="something" at the same time
    data class State(
        val isLoading: Boolean = false,
        val users: List<User> = emptyList(),
        val searchQuery: String = "",
        val selectedFilter: Filter = Filter.All,
        val error: String? = null
    ) {
        // Derived state — no duplication, always consistent
        val filteredUsers: List<User>
            get() = users.filter { user ->
                (selectedFilter == Filter.All || user.role == selectedFilter.role) &&
                (searchQuery.isEmpty() || user.name.contains(searchQuery, ignoreCase = true))
            }
        val isEmpty: Boolean get() = !isLoading && filteredUsers.isEmpty() && error == null
    }

    // What the USER CAN DO on this screen (sealed = exhaustive)
    sealed class Intent {
        object LoadUsers : Intent()
        object RetryLoad : Intent()
        data class SearchQueryChanged(val query: String) : Intent()
        data class FilterSelected(val filter: Filter) : Intent()
        data class UserClicked(val userId: String) : Intent()
        data class DeleteUserClicked(val user: User) : Intent()
        data class ConfirmDelete(val user: User) : Intent()
    }

    // One-time events that should NOT be replayed on re-collection
    sealed class SideEffect {
        data class NavigateToDetail(val userId: String) : SideEffect()
        data class ShowSnackbar(val message: String) : SideEffect()
        data class ShowDeleteConfirmation(val user: User) : SideEffect()
    }
}
```

### MVI ViewModel

```kotlin
class UserViewModel(
    private val getUsersUseCase: GetUsersUseCase,
    private val deleteUserUseCase: DeleteUserUseCase
) : ViewModel() {

    private val _state = MutableStateFlow(UserContract.State())
    val state: StateFlow<UserContract.State> = _state.asStateFlow()

    private val _sideEffects = MutableSharedFlow<UserContract.SideEffect>()
    val sideEffects: SharedFlow<UserContract.SideEffect> = _sideEffects.asSharedFlow()

    // Single entry point for ALL user actions
    fun handleIntent(intent: UserContract.Intent) {
        when (intent) {
            is UserContract.Intent.LoadUsers         -> loadUsers()
            is UserContract.Intent.RetryLoad         -> loadUsers()
            is UserContract.Intent.SearchQueryChanged -> updateSearch(intent.query)
            is UserContract.Intent.FilterSelected    -> updateFilter(intent.filter)
            is UserContract.Intent.UserClicked       -> navigateToDetail(intent.userId)
            is UserContract.Intent.DeleteUserClicked -> confirmDelete(intent.user)
            is UserContract.Intent.ConfirmDelete     -> deleteUser(intent.user)
        }
    }

    // State transitions are explicit, traceable, testable
    private fun loadUsers() {
        viewModelScope.launch {
            _state.update { it.copy(isLoading = true, error = null) }
            try {
                val users = getUsersUseCase()
                _state.update { it.copy(isLoading = false, users = users) }
            } catch (e: Exception) {
                _state.update { it.copy(isLoading = false, error = e.message) }
            }
        }
    }

    private fun updateSearch(query: String) {
        _state.update { it.copy(searchQuery = query) }
        // filteredUsers is derived — updates automatically in the data class
    }

    private fun navigateToDetail(userId: String) {
        viewModelScope.launch {
            _sideEffects.emit(UserContract.SideEffect.NavigateToDetail(userId))
        }
    }

    private fun confirmDelete(user: User) {
        viewModelScope.launch {
            _sideEffects.emit(UserContract.SideEffect.ShowDeleteConfirmation(user))
        }
    }

    private fun deleteUser(user: User) {
        viewModelScope.launch {
            val previousUsers = _state.value.users
            // Optimistic update
            _state.update { it.copy(users = it.users - user) }
            try {
                deleteUserUseCase(user.id)
            } catch (e: Exception) {
                // Rollback
                _state.update { it.copy(users = previousUsers) }
                _sideEffects.emit(UserContract.SideEffect.ShowSnackbar("Delete failed"))
            }
        }
    }
}
```

### MVI View (Compose)

```kotlin
@Composable
fun UserScreen(viewModel: UserViewModel = hiltViewModel()) {
    val state by viewModel.state.collectAsStateWithLifecycle()

    // Collect side effects
    val context = LocalContext.current
    LaunchedEffect(Unit) {
        viewModel.sideEffects.collect { effect ->
            when (effect) {
                is UserContract.SideEffect.NavigateToDetail ->
                    /* navigate */ Unit
                is UserContract.SideEffect.ShowSnackbar ->
                    Toast.makeText(context, effect.message, Toast.LENGTH_SHORT).show()
                is UserContract.SideEffect.ShowDeleteConfirmation ->
                    /* show dialog */ Unit
            }
        }
    }

    // UI is purely a function of state
    when {
        state.isLoading -> LoadingContent()
        state.error != null -> ErrorContent(
            message = state.error!!,
            onRetry = { viewModel.handleIntent(UserContract.Intent.RetryLoad) }
        )
        state.isEmpty -> EmptyContent()
        else -> UserList(
            users = state.filteredUsers,
            onUserClick = { viewModel.handleIntent(UserContract.Intent.UserClicked(it.id)) },
            onDeleteClick = { viewModel.handleIntent(UserContract.Intent.DeleteUserClicked(it)) }
        )
    }
}
```

### MVI Directory Structure

```
com.example.app/
├── ui/
│   └── user/
│       ├── UserScreen.kt            ← Compose UI (or Fragment)
│       ├── UserViewModel.kt         ← state machine + reducer
│       ├── UserContract.kt          ← State + Intent + SideEffect
│       └── components/
│           ├── UserList.kt
│           └── UserListItem.kt
```

### MVVM vs MVI: The Decision

```
                    MVVM                        MVI
─────────────────────────────────────────────────────────────────
State model:        Multiple StateFlows          Single State object
                    + SharedFlow for events
State transitions:  Anywhere in ViewModel        Through handleIntent()
Impossible states:  Possible (isLoading=true      Impossible (one data class)
                    + error != null)
Boilerplate:        Less                          More (Contract object)
Testing:            Good                          Excellent (pure reducer)
Traceability:       Moderate                      Full (every action logged)
Best for:           Simple to medium screens      Complex screens, large teams
Compose fit:        Good                          Natural
```

### Interview Q&A

**"What's the difference between MVVM and MVI?"**
MVVM can have multiple observable state streams that can get out of sync; MVI has a single immutable State object that the entire screen derives from. In MVVM you call ViewModel functions directly; in MVI all user actions go through a single `handleIntent()` entry point, making the state machine explicit and traceable.

**"How do you handle one-time events in MVI (like navigation)?"**
A `SharedFlow` with `replay=0`. Navigation is a SideEffect — it should not re-occur if the collector restarts (e.g., Fragment goes to background and comes back). StateFlow would re-deliver navigation on re-collection, causing double navigation.

**"What's an 'impossible state' and why does MVI prevent it?"**
An impossible state is a combination of fields that should never occur together — like `isLoading = true` AND `error = "Network failed"`. In MVVM, these are separate fields that must be set consistently by hand. In MVI they live in one data class and transition atomically via `_state.update { it.copy(...) }` — you change all fields at once, so there's no window where they're inconsistent.

---

## A3.6 — Clean Architecture: The Full Stack

> **Builds on:** [A3.4 — MVVM](A3_architecture_patterns.md#a34--mvvm-viewmodel--observable-state) · [A3.5 — MVI](A3_architecture_patterns.md#a35--mvi-unidirectional-data-flow)

### WHY Clean Architecture

MVVM and MVI define how the **UI layer** is organized. Clean Architecture defines how the **entire application** is layered. As a codebase grows, the data layer becomes complex: multiple APIs, multiple databases, complex caching, business rules that span multiple data sources. Clean Architecture separates these concerns into layers that can evolve independently.

### The Three-Layer Model

```
Clean Architecture Dependency Rule:
  Outer layers depend on inner layers. NEVER the reverse.

  ┌─────────────────────────────────────────────────┐
  │                   PRESENTATION                   │  ← Android module
  │   Activity, Fragment, ViewModel, Compose UI      │
  │   Depends on: Domain only                        │
  └───────────────────┬─────────────────────────────┘
                      │ depends on
                      ▼
  ┌─────────────────────────────────────────────────┐
  │                    DOMAIN                        │  ← Pure Kotlin module
  │   Use Cases, Domain Models, Repository interfaces│
  │   Depends on: NOTHING (no Android, no Retrofit)  │
  └───────────────────┬─────────────────────────────┘
                      │ depends on
                      ▼ (interface — Dependency Inversion)
  ┌─────────────────────────────────────────────────┐
  │                     DATA                         │  ← Android module
  │   RepositoryImpl, Room Entities, Retrofit DTOs   │
  │   Depends on: Domain (implements its interfaces) │
  └─────────────────────────────────────────────────┘
```

The critical insight: **Domain depends on nothing**. It is a pure Kotlin module. It can be compiled and tested entirely on the JVM, no emulator needed. The Data layer IMPLEMENTS Domain interfaces (Dependency Inversion), so Domain never imports Data.

### Complete Directory Structure

**Single-module (smaller projects):**

```
com.example.app/
├── presentation/
│   ├── user/
│   │   ├── UserFragment.kt
│   │   ├── UserViewModel.kt
│   │   └── UserContract.kt
│   └── di/
│       └── PresentationModule.kt
│
├── domain/
│   ├── model/
│   │   └── User.kt                 ← domain entity (NOT Room entity)
│   ├── repository/
│   │   └── UserRepository.kt       ← interface only
│   └── usecase/
│       ├── GetUsersUseCase.kt
│       ├── DeleteUserUseCase.kt
│       └── UpdateUserUseCase.kt
│
└── data/
    ├── repository/
    │   └── UserRepositoryImpl.kt   ← implements UserRepository
    ├── remote/
    │   ├── UserApiService.kt
    │   └── dto/
    │       └── UserDto.kt
    ├── local/
    │   ├── AppDatabase.kt
    │   ├── UserDao.kt
    │   └── entity/
    │       └── UserEntity.kt
    └── mapper/
        └── UserMapper.kt
```

**Multi-module (large teams, feature-based):**

```
MyApp/
├── app/                            ← application entry point
│   └── src/main/
│       ├── MyApplication.kt
│       └── di/
│           └── AppComponent.kt
│
├── feature-users/                  ← self-contained feature module
│   └── src/main/
│       ├── presentation/
│       │   ├── UserListScreen.kt
│       │   ├── UserListViewModel.kt
│       │   └── UserDetailScreen.kt
│       ├── domain/
│       │   ├── model/User.kt
│       │   ├── usecase/GetUsersUseCase.kt
│       │   └── repository/UserRepository.kt
│       └── data/
│           ├── UserRepositoryImpl.kt
│           ├── UserApiService.kt
│           └── UserEntity.kt
│
├── feature-products/               ← another self-contained feature
│   └── src/main/ ...
│
├── core-network/                   ← shared Retrofit + OkHttp setup
│   └── src/main/
│       └── NetworkModule.kt
│
├── core-database/                  ← shared Room database
│   └── src/main/
│       └── AppDatabase.kt
│
└── core-ui/                        ← shared Compose components
    └── src/main/
        ├── theme/
        └── components/
```

### The Use Case Pattern

```kotlin
// Domain model — no Room annotations, no Retrofit annotations
data class User(
    val id: String,
    val name: String,
    val email: String,
    val role: UserRole
)

// Domain repository interface — in the DOMAIN layer
interface UserRepository {
    suspend fun getUsers(): List<User>
    suspend fun getUserById(id: String): User?
    suspend fun deleteUser(id: String)
    fun observeUsers(): Flow<List<User>>
}

// Use case — orchestrates one piece of business logic
class GetUsersUseCase(private val repository: UserRepository) {
    // operator fun invoke() = callable as a function
    suspend operator fun invoke(): List<User> {
        return repository.getUsers()
            .filter { it.role != UserRole.DELETED }
            .sortedBy { it.name }
    }
}

// ViewModel uses the use case (not the repository directly)
class UserViewModel(
    private val getUsersUseCase: GetUsersUseCase,       // domain dependency
    private val deleteUserUseCase: DeleteUserUseCase    // domain dependency
) : ViewModel() {

    fun loadUsers() {
        viewModelScope.launch {
            val users = getUsersUseCase()   // called as a function
            _state.update { it.copy(users = users) }
        }
    }
}
```

### The Mapper Triple

Three separate model types, each optimized for its layer:

```
API Response (DTO)         Room Entity            Domain Model
──────────────────         ───────────────        ───────────────
@SerializedName            @Entity                data class User(
("user_name")              @PrimaryKey               id: String,
val userName: String       val id: String            name: String,
val email: String          val userName: String      email: String,
val roles: List<String>    val email: String         role: UserRole
                           val rolesCsv: String   )
```

```kotlin
// UserMapper.kt
object UserMapper {
    fun UserDto.toDomain(): User = User(
        id = id,
        name = userName,    // DTO field name differs from domain
        email = email,
        role = UserRole.from(roles.firstOrNull())
    )

    fun UserEntity.toDomain(): User = User(
        id = id,
        name = userName,
        email = email,
        role = UserRole.from(rolesCsv.split(",").first())
    )

    fun User.toEntity(): UserEntity = UserEntity(
        id = id,
        userName = name,
        email = email,
        rolesCsv = role.value
    )
}
```

**Why three models instead of one?**
- The API changes its field from `user_name` to `username` → update the DTO only, domain and Room unchanged
- Room adds a new column for caching → update the Entity only, API and domain unchanged
- Domain gains a new computed field → update domain only, no DB migration needed

### Interview Q&A

**"Why does the domain layer have no Android dependencies?"**
Three reasons: (1) Testability — domain logic can be tested with pure JUnit on the JVM, no emulator or Robolectric needed. (2) Portability — domain could theoretically run on a server, a desktop app, or be shared via KMP. (3) Stability — domain is insulated from Android framework changes; if Google changes how Room or Retrofit work, domain code is unaffected.

**"Who calls the repository — ViewModel or Use Case?"**
Use Case. The ViewModel knows about Use Cases and calls them. It does not know about Repository implementations. This means business logic (filtering, sorting, combining multiple repositories) lives in the Use Case, not the ViewModel. A ViewModel with direct Repository access tends to accumulate business logic over time.

**"Could you skip the domain layer for a simple CRUD app?"**
Yes — pragmatically. Clean Architecture has overhead: more files, more mappers, more indirection. For a 3-screen CRUD app with a single developer, MVVM + Repository without Use Cases is appropriate. Add Clean Architecture when: multiple developers work on different features simultaneously (module boundaries prevent conflicts), business logic is complex enough to need isolated unit tests, or the app is expected to grow significantly.

---

## A3.7 — Architecture Decision Matrix & Real Interview Scenarios

### Comparison Table

```
Architecture  Testability  Boilerplate  Team Size   Good For
─────────────────────────────────────────────────────────────────────────────
MVC           ✗ Very low   ✗ None       1 dev       Throwaway prototypes
MVP           ✓ Good       ✗ High       1-3 devs    Legacy code, simple screens
MVVM          ✓✓ Great     ✓ Medium     2-10 devs   Most Android apps today
MVI           ✓✓✓ Excel    ✗ High       3-15 devs   Complex state, Compose apps
Clean Arch    ✓✓✓ Excel    ✗ Very High  5-50+ devs  Large teams, feature modules
```

### When to Use Each

```
Start-up / MVP / Weekend project
└── MVVM + Repository (no use cases)
    Files: Feature + ViewModel + UiState + Repository + ApiService
    → Fast iteration, clean enough, not over-engineered

Growing product (2-10 devs)
└── MVVM + Clean Architecture (with domain layer, no feature modules)
    Files: all of above + UseCase + DomainModel + Entity + Mapper + DTO
    → Business logic is testable, presentation and data can evolve independently

Large team / feature teams (10+ devs)
└── Clean Architecture + Feature Modules
    Modules: :feature-users, :feature-products, :core-network, :core-ui
    → Parallel development without merge conflicts, fast build times (only
      changed module recompiles), clear ownership boundaries

App with complex real-time UI (Compose)
└── MVI + Clean Architecture
    → Single state object makes Compose recomposition predictable
       Each handleIntent() call produces exactly one new State
```

### Real-World Interview Scenarios

**Scenario 1: "Walk me through how you'd architect a product listing feature with offline support, search, and add-to-cart."**

Full answer structure:
1. Architecture choice: MVVM + Clean Architecture + offline-first repository
2. Presentation: `ProductListContract` (State: products, isLoading, searchQuery, cartCount / Intent: LoadProducts, SearchQueryChanged, AddToCart, RetryLoad)
3. Domain: `GetProductsUseCase`, `AddToCartUseCase`, `Product` (domain model)
4. Data: `ProductRepository` (interface) → `ProductRepositoryImpl` (Room + Retrofit), `ProductEntity` (Room), `ProductDto` (API), `ProductMapper`
5. Offline: Room as source of truth, repository fetches API → writes to Room → Fragment observes `Flow<List<Product>>` from Room
6. Search: Room query `WHERE name LIKE :query` or in-memory filter depending on data size
7. Cart: `CartRepository` with Room (persists cart between sessions), or in-memory if session-only

**Scenario 2: "Your ViewModel has 500 lines. A junior dev asks what to do. What do you say?"**

Signs of over-loaded ViewModel:
- Multiple unrelated features on one screen → split to separate ViewModels
- Complex business logic (filtering, combining, transforming) → extract to Use Cases
- Complex state management → extract to a State reducer

Action plan: (1) Identify each distinct responsibility. (2) Extract business logic to Use Cases. (3) If screen has distinct sections (tabs, panels), consider separate ViewModels composed with `activityViewModels` for shared state.

**Scenario 3: "A junior dev stored Context in the ViewModel. What problems does this cause?"**

1. **Memory leak**: ViewModel outlives the Activity on rotation. Activity (Context) cannot be GC'd as long as ViewModel holds a reference. → 1 leaked Activity per rotation.
2. **Wrong Context**: After rotation, the ViewModel still holds the OLD Activity's Context, not the new one. Resources (strings, drawables) from the old configuration may be wrong.
3. **Architecture violation**: ViewModel is a presentation-layer class that should be framework-independent. Context couples it to Android.

Fix: Use `Application` context via `AndroidViewModel`, or pass context only at the point of use (don't store it), or move context-dependent logic to the View layer.

**Scenario 4: "How would you migrate a 3-year-old 1000-line Activity to a modern architecture?"**

The Strangler Fig pattern:
1. Add a ViewModel alongside the existing Activity (don't refactor, add)
2. Move state management (data fields) to ViewModel StateFlow first
3. Gradually extract business logic methods from Activity to ViewModel
4. Introduce a Repository for data access; redirect Activity's direct API calls through it
5. Once Activity only does UI work (observe + display), split the screen into Fragments if needed
6. Tests: write tests for each piece before moving it (ensure behavior doesn't change)
Key principle: never do a "big bang" rewrite. Incremental migration keeps the app shippable throughout.

---

## Master Summary: Android Architecture Patterns

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  PHASE A3 — ANDROID ARCHITECTURE PATTERNS MASTER SUMMARY                      │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  THREE FORCES that make Android architecture hard:                           │
│  Lifecycle (OS destroys components), Config changes (rotation recreates),   │
│  Process death (OS kills process when backgrounded).                         │
│                                                                              │
│  THREE PRINCIPLES: Separation of Concerns, Single Source of Truth,          │
│  Unidirectional Data Flow. Every good pattern implements all three.          │
│                                                                              │
│  MVC: Activity is View + Controller. Untestable. Use only for prototypes.   │
│                                                                              │
│  MVP: Presenter is pure JVM (testable). View interface decouples Activity.  │
│  Memory leak: detachView() + null ref in onDestroy(). Recreated on rotation.│
│                                                                              │
│  MVVM: ViewModel survives rotation (ViewModelStore). No View reference.     │
│  StateFlow for persistent state. SharedFlow (replay=0) for one-time events. │
│  Never store Context/View in ViewModel. repeatOnLifecycle for collection.   │
│                                                                              │
│  MVI: Single immutable State object. All actions through handleIntent().    │
│  SideEffects for one-time events. Eliminates impossible states.             │
│  Contract object (State + Intent + SideEffect) documents the screen.        │
│                                                                              │
│  CLEAN ARCHITECTURE: Presentation → Domain → Data.                          │
│  Dependency Rule: only inward. Domain has NO Android deps (pure Kotlin).    │
│  Use Cases own business logic. Three model types: DTO / Entity / Domain.    │
│  Feature modules for large teams: parallel dev, fast builds, clear ownership│
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

*← [Phase A2 — Main Thread & View System](A2_main_thread_and_views.md) | [Phase A4 — Offline & Data Layer →](A4_offline_and_data.md)*

---

**Cross-references:**
- Kotlin coroutines (used in all ViewModels): [Kotlin 09 — Coroutines](../../Kotlin/Questions/09_coroutines_execution_mechanics.md)
- Kotlin Flow (StateFlow/SharedFlow): [Kotlin 11 — Flow](../../Kotlin/Questions/11_flow.md)
- Kotlin architecture patterns (MVVM with Kotlin): [Kotlin 13 — Android Architecture](../../Kotlin/Questions/13_android_architecture.md)
- Jetpack components (Room, Hilt, Navigation): [Kotlin 14 — Jetpack Components](../../Kotlin/Questions/14_jetpack_components.md)
- Java concurrency (threading model): [J6 — Concurrency Fundamentals](../../Java/Questions/J6_concurrency_fundamentals.md) · [J7 — Concurrent Utilities](../../Java/Questions/J7_concurrent_utilities.md)
