# Phase 15: Networking

## Navigation
| Phase | File |
|-------|------|
| 14 — Jetpack Components | [14_jetpack_components.md](14_jetpack_components.md) |
| **15 — Networking** | ← You are here |
| 16 — Android System Internals | [16_android_system_internals.md](16_android_system_internals.md) |

---

## Q15.1 — OkHttp Interceptor Chain

> **Reference:** [OkHttp Docs — Interceptors](https://square.github.io/okhttp/features/interceptors/)

### First Principles: What Is an Interceptor?

An interceptor is a function that sits in the middle of a request/response flow. Every request passes through each interceptor in order, and every response passes through them in reverse order. You can modify, observe, log, or short-circuit the request at any point.

```
Request flow:
Your code → Interceptor 1 → Interceptor 2 → Network → Server
Response:   Your code ← Interceptor 1 ← Interceptor 2 ← Network ← Server
```

OkHttp has an **interceptor chain** — each interceptor calls `chain.proceed(request)` to pass the request along. The response comes back when `proceed()` returns.

```kotlin
class LoggingInterceptor : Interceptor {
    override fun intercept(chain: Interceptor.Chain): Response {
        val request = chain.request()
        println("→ ${request.url}")            // before sending

        val response = chain.proceed(request)   // send request, get response

        println("← ${response.code}")          // after receiving
        return response
    }
}
```

### Application Interceptor vs Network Interceptor

**Application Interceptors** (`addInterceptor`) — sit BEFORE OkHttp's network/cache logic:

```
Your code → [Application Interceptors] → OkHttp Cache/Redirect logic → Network
```

**Network Interceptors** (`addNetworkInterceptor`) — sit AFTER OkHttp's cache/redirect logic, only for actual network calls:

```
Your code → OkHttp Cache/Redirect logic → [Network Interceptors] → Network
```

| Aspect | Application Interceptor | Network Interceptor |
|--------|------------------------|---------------------|
| Sees cached responses | Yes | No (never called for cache hits) |
| Sees redirects | No (called once, redirect handled internally) | Yes (called for each redirect) |
| Sees retries | No (called once per call) | Yes (called for each retry) |
| Correct for: | Auth headers, logging business events | Wire-level logging, modifying actual bytes sent |
| `response.cacheControl()` available | After cache decision | Always the server's response |

**Where should logging go?** Application interceptor for business-level (what was requested), Network interceptor for wire-level debugging (what was actually sent/received, after redirects).

```kotlin
// Correct placement of logging:
OkHttpClient.Builder()
    .addInterceptor(HttpLoggingInterceptor().apply {
        level = HttpLoggingInterceptor.Level.BODY  // logs request + response body
    })
    // OR for strict network-level logging:
    .addNetworkInterceptor(HttpLoggingInterceptor().apply {
        level = HttpLoggingInterceptor.Level.BODY
    })
    .build()
```

### `Authenticator` vs `Interceptor` for 401 Handling

**`Interceptor`** handles all responses — you must manually check for 401:
```kotlin
class AuthInterceptor(private val tokenProvider: TokenProvider) : Interceptor {
    override fun intercept(chain: Interceptor.Chain): Response {
        val request = chain.request().newBuilder()
            .header("Authorization", "Bearer ${tokenProvider.getToken()}")
            .build()
        return chain.proceed(request)
    }
}
```

**`Authenticator`** is specifically invoked by OkHttp when it receives a 401. It's called AFTER the request has been made and a 401 received:
```kotlin
class TokenAuthenticator(private val tokenProvider: TokenProvider) : Authenticator {
    override fun authenticate(route: Route?, response: Response): Request? {
        // Called only on 401 — refresh token logic here
        val newToken = tokenProvider.refreshToken() ?: return null  // null = give up
        return response.request.newBuilder()
            .header("Authorization", "Bearer $newToken")
            .build()  // OkHttp will retry with this new request
    }
}
```

**Difference:**
- `AuthInterceptor`: adds token to every request proactively
- `Authenticator`: handles expired tokens reactively (called only on 401)
- Usually use BOTH: interceptor adds current token, authenticator handles refresh on 401

---

## Q15.2 — Token Refresh Pattern

> **Reference:** [OkHttp Docs — Authenticator](https://square.github.io/okhttp/recipes/#handling-authentication-kt)

### Why Token Refresh Needs a Mutex

Imagine 3 parallel API calls all get a 401 simultaneously (token expired):

```
Without Mutex:
Request 1 → 401 → refresh token → POST /refresh → new token
Request 2 → 401 → refresh token → POST /refresh → new token (DUPLICATE!)
Request 3 → 401 → refresh token → POST /refresh → new token (DUPLICATE!)
3 refresh calls! Some may fail if the server invalidates the old token on first refresh.
```

```kotlin
class TokenAuthenticator(
    private val tokenStorage: TokenStorage,
    private val authApi: AuthApi
) : Authenticator {

    private val mutex = Mutex()

    override fun authenticate(route: Route?, response: Response): Request? {
        // runBlocking is acceptable here — Authenticator is a sync Java interface
        return runBlocking {
            mutex.withLock {
                // Check if another coroutine already refreshed the token:
                val currentToken = tokenStorage.getAccessToken()
                if (response.request.header("Authorization") != "Bearer $currentToken") {
                    // Token was already refreshed by another request — just retry
                    return@runBlocking response.request.newBuilder()
                        .header("Authorization", "Bearer $currentToken")
                        .build()
                }

                // We need to refresh:
                try {
                    val newTokens = authApi.refresh(tokenStorage.getRefreshToken())
                    tokenStorage.saveTokens(newTokens)
                    response.request.newBuilder()
                        .header("Authorization", "Bearer ${newTokens.accessToken}")
                        .build()
                } catch (e: Exception) {
                    null  // refresh failed — propagate 401 to caller
                }
            }
        }
    }
}
```

### Why `runBlocking` Works Here

`Authenticator.authenticate()` is a **Java interface** — not a suspend function. You can't call `suspend` functions from it directly. `runBlocking` creates a coroutine that blocks the current thread until the token refresh completes.

This is acceptable because `Authenticator` is already called on OkHttp's internal thread pool — blocking it doesn't block the main thread. The thread will be unblocked when the refresh call completes.

### Preventing Infinite Retry Loop

OkHttp calls `Authenticator.authenticate()` up to a limit, but you should also protect yourself:

```kotlin
// OkHttp stops calling authenticate() when it returns null
// But also protect against: refresh token is expired

override fun authenticate(route: Route?, response: Response): Request? {
    // Check if we've already retried (response has our retry header):
    if (response.request.header("X-Auth-Retry") != null) {
        return null  // Already retried once — give up, propagate 401
    }

    return runBlocking {
        try {
            val newTokens = authApi.refresh(tokenStorage.getRefreshToken())
            tokenStorage.saveTokens(newTokens)
            response.request.newBuilder()
                .header("Authorization", "Bearer ${newTokens.accessToken}")
                .header("X-Auth-Retry", "true")  // mark as retried
                .build()
        } catch (e: HttpException) {
            if (e.code() == 401) {
                // Refresh token itself is expired — log out user
                tokenStorage.clearTokens()
                navigateToLogin()
            }
            null  // return null → OkHttp gives up
        }
    }
}
```

---

## Q15.3 — JSON Serialization Pitfalls

> **Reference:** [Kotlin Serialization Docs](https://kotlinlang.org/docs/serialization.html)

### Why Gson Is Dangerous With Kotlin Data Classes

Gson uses **Java reflection** to create objects. It doesn't call constructors — it creates instances using `Unsafe.allocateInstance()` and sets fields directly. This bypasses Kotlin's null safety:

```kotlin
data class User(
    val name: String,       // @NotNull — should never be null!
    val age: Int
)

// JSON with missing "name" field:
val json = """{"age": 30}"""
val user = Gson().fromJson(json, User::class.java)

println(user.name)  // null! — Gson set it to null despite non-nullable type
println(user.name.length)  // NullPointerException — null was smuggled in!
```

**Why this is dangerous:** The NPE doesn't happen at deserialization — it happens later when you use the property. The stack trace points to your business logic, not the JSON parsing. Very hard to debug.

**Fix with Gson:** Add `@SerializedName` + use `@field:SerializedName` and add a Gson null-check adapter. Or just switch to Moshi/Kotlin Serialization.

### What Kotlin Serialization Does Differently

```kotlin
@Serializable
data class User(
    val name: String,
    val age: Int = 0  // default value respected!
)

// Missing "name" → SerializationException at parse time (fast fail!)
val user = Json.decodeFromString<User>("""{"age": 30}""")
// Exception: Field 'name' is required but missing

// Missing "age" → uses default value:
val user2 = Json.decodeFromString<User>("""{"name": "Alice"}""")
// User(name="Alice", age=0) — default value used!
```

**Key differences from Gson:**
1. **Fails fast** — throws at deserialization, not later
2. **Respects default values** — Gson ignores them; Kotlin Serialization uses them
3. **Respects `@Transient`** — Gson's `@Transient` (Java transient) vs Kotlin's `@kotlinx.serialization.Transient`

### Moshi KSP Codegen vs Reflection

**Reflection-based Moshi:**
```kotlin
val moshi = Moshi.Builder().build()
val adapter = moshi.adapter(User::class.java)  // inspects at runtime via reflection
```
- Slower startup (reflection at first use)
- No null-safety guarantees (same Gson-style issues for Kotlin)
- Works without code generation

**KSP Codegen Moshi:**
```kotlin
@JsonClass(generateAdapter = true)  // triggers code generation!
data class User(val name: String, val age: Int)
```
```kotlin
// Generated at compile time:
class UserJsonAdapter {
    fun fromJson(reader: JsonReader): User {
        // null checks enforced:
        val name = reader.nextString() ?: throw JsonDataException("name is null")
        val age = reader.nextInt()
        return User(name, age)
    }
}
```
- **Faster** (no reflection — generated code is direct)
- **Null-safe** (generated code enforces nullability)
- **Build-time errors** for bad annotations
- **Larger APK** (generated code is included)

### `@SerializedName` vs `@SerialName`

```kotlin
// Gson:
data class User(
    @SerializedName("user_name") val name: String  // maps JSON "user_name" to "name"
)

// Kotlin Serialization:
@Serializable
data class User(
    @SerialName("user_name") val name: String  // same purpose, different annotation
)

// Moshi (codegen):
data class User(
    @Json(name = "user_name") val name: String
)
```

All three do the same thing (map a different JSON key to a Kotlin property name) but come from different libraries. You cannot mix them.

---

## Master Summary: Networking in 4 Points

```
┌────────────────────────────────────────────────────────────────────────┐
│  1. Application interceptors see cached responses and run once per   │
│     call. Network interceptors see only real network traffic — once  │
│     per redirect. Use Application for auth; Network for wire logs.   │
│                                                                        │
│  2. Token refresh MUST use a Mutex — without it, multiple parallel   │
│     401s trigger multiple refresh calls. Check if token was already  │
│     refreshed before making the API call inside the lock.            │
│                                                                        │
│  3. Gson is dangerous: bypasses Kotlin null safety by using Unsafe.  │
│     Non-nullable properties can be null at runtime. Fail occurs late.│
│     Kotlin Serialization fails fast and respects default values.     │
│                                                                        │
│  4. Moshi KSP codegen generates null-safe adapters at compile time   │
│     vs reflection-based adapters at runtime. Codegen = faster + safe.│
└────────────────────────────────────────────────────────────────────────┘
```

---

*← [Phase 14 — Jetpack Components](14_jetpack_components.md) | [Phase 16 — Android System Internals →](16_android_system_internals.md)*
