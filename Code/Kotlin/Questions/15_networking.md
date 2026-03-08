# Phase 15 — Networking

> OkHttp's interceptor chain is a linked list of functions. Each node can observe, modify, or short-circuit the request before passing it to the next node. Token refresh, logging, and authentication all live here — but placement relative to OkHttp's own cache and redirect logic determines what you actually see.

## Navigation

[← Phase 14 — Jetpack Components](14_jetpack_components.md) | [→ Phase 16 — Android System Internals](16_android_system_internals.md)

## Questions in This File

- [Q15.1 — OkHttp Interceptor Chain](#q151--okhttp-interceptor-chain)
- [Q15.2 — Token Refresh Pattern](#q152--token-refresh-pattern)
- [Q15.3 — JSON Serialization Pitfalls](#q153--json-serialization-pitfalls)

---

# Q15.1 — OkHttp Interceptor Chain

> **Builds on:** [Q10.3 (CancellationException in network calls)](10_structured_concurrency.md#q103--exception-handling-rules)
> **Connects to:** [Q15.2 (Token refresh)](15_networking.md#q152--token-refresh-pattern)

---

## The Core Rule

```
Application interceptor: added via addInterceptor().
  Runs BEFORE OkHttp's cache/redirect logic.
  Called ONCE per logical call, even for cached responses.

Network interceptor: added via addNetworkInterceptor().
  Runs AFTER OkHttp's cache/redirect logic.
  Only called for real network requests (not for cache hits).
  Called for EACH redirect and retry.
```

---

## How the Chain Works

Every request passes through interceptors in order. Every response returns in reverse order. Each interceptor calls `chain.proceed(request)` to hand off.

```kotlin
class LoggingInterceptor : Interceptor {
    override fun intercept(chain: Interceptor.Chain): Response {
        val request = chain.request()
        println("→ ${request.url}")            // runs BEFORE sending

        val response = chain.proceed(request)  // hand off to next interceptor

        println("← ${response.code}")          // runs AFTER receiving
        return response
    }
}
```

```
Request:   Your code → [App Interceptors] → OkHttp cache/redirect → [Net Interceptors] → Wire
Response:  Your code ← [App Interceptors] ← OkHttp cache/redirect ← [Net Interceptors] ← Wire
```

---

## Application vs Network Interceptor — Difference Table

| | Application Interceptor | Network Interceptor |
|---|---|---|
| Sees cached responses | Yes | No (cache hit = skipped entirely) |
| Sees redirects | No (called once, redirect hidden) | Yes (called per redirect) |
| Called on retry | No | Yes (once per network attempt) |
| Use for | Auth headers, business-level logging | Wire-level logging, modify bytes |

**Practical rule:**
- `addInterceptor` → auth headers, request-level logging, business metrics
- `addNetworkInterceptor` → `HttpLoggingInterceptor` for exact bytes on the wire

```kotlin
OkHttpClient.Builder()
    .addInterceptor(AuthInterceptor(tokenProvider))      // adds token to every request
    .addNetworkInterceptor(HttpLoggingInterceptor())     // logs actual wire traffic
    .build()
```

---

## `Authenticator` vs `Interceptor` for 401

**`Interceptor`** — runs proactively on every request:

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

**`Authenticator`** — invoked by OkHttp reactively, only after a 401:

```kotlin
class TokenAuthenticator(private val tokenProvider: TokenProvider) : Authenticator {
    override fun authenticate(route: Route?, response: Response): Request? {
        val newToken = tokenProvider.refreshToken() ?: return null  // null = give up
        return response.request.newBuilder()
            .header("Authorization", "Bearer $newToken")
            .build()   // OkHttp retries with this new request automatically
    }
}
```

```
Interceptor:    proactive — adds current token to EVERY request at send time
Authenticator:  reactive — called ONLY when a 401 is received, refreshes token
Use BOTH:       Interceptor adds token. Authenticator handles expiry and refresh.
```

---

## ## Traps

**Trap — Modifying the request without `.newBuilder().build()`:**

```kotlin
// WRONG — Request is immutable, can't modify directly:
chain.request().header("Authorization", "Bearer $token")  // does nothing

// CORRECT:
val newRequest = chain.request().newBuilder()
    .header("Authorization", "Bearer $token")
    .build()
chain.proceed(newRequest)
```

**Trap — `addNetworkInterceptor` for auth headers:**

```kotlin
// WRONG — network interceptor is skipped on cache hits:
.addNetworkInterceptor(AuthInterceptor())
// Cache hit → interceptor never runs → request goes out without auth!

// CORRECT:
.addInterceptor(AuthInterceptor())  // always runs
```

---

## Memory Trick

```
addInterceptor      = BEFORE cache. Always called. One call per logical request.
addNetworkInterceptor = AFTER cache. Only for real network. Called per redirect.

Auth headers → addInterceptor (must be on every request, even cache bypass).
Wire logging → addNetworkInterceptor (shows real bytes after redirects).

Interceptor = proactive (adds token before send).
Authenticator = reactive (refreshes token after 401).
```

---

## Self-Test

1. A user makes a request that is served from OkHttp's cache. Is the application interceptor called? Is the network interceptor called?
2. Your auth interceptor is in `addNetworkInterceptor`. User is offline, OkHttp serves a cached response. What happens to the `Authorization` header?
3. What is the difference between an `Interceptor` and an `Authenticator`? When would you use both simultaneously?
4. Why must you call `chain.request().newBuilder()...build()` instead of modifying the request directly?

---

# Q15.2 — Token Refresh Pattern

> **Builds on:** [Q15.1 (Interceptor chain)](15_networking.md#q151--okhttp-interceptor-chain) · [Q14.4 (Mutex)](14_jetpack_components.md#q144--thread-safe-caching)
> **Connects to:** [Q10.3 (CancellationException)](10_structured_concurrency.md#q103--exception-handling-rules)

---

## The Core Rule

```
Token refresh must be guarded by a Mutex.
Without it: 3 parallel 401s = 3 parallel refresh calls = server invalidates first token = chaos.
Inside the lock: re-check if another coroutine already refreshed before doing it again.
```

---

## The Race Condition Without Mutex

```
3 parallel API calls, token expires simultaneously:

Without Mutex:
  Request 1 → 401 → refreshToken() → POST /refresh → new token T2
  Request 2 → 401 → refreshToken() → POST /refresh → new token T3 (server invalidates T2!)
  Request 3 → 401 → refreshToken() → POST /refresh → new token T4 (server invalidates T3!)

Result: Request 1 retries with T2 → 401 again (T2 was invalidated by Request 2's refresh)
```

---

## Correct Pattern — Mutex + Double-Check

```kotlin
class TokenAuthenticator(
    private val tokenStorage: TokenStorage,
    private val authApi: AuthApi
) : Authenticator {

    private val mutex = Mutex()

    override fun authenticate(route: Route?, response: Response): Request? {
        // Authenticator is a Java sync interface → use runBlocking
        return runBlocking {
            mutex.withLock {
                // Double-check: did another coroutine already refresh?
                val currentToken = tokenStorage.getAccessToken()
                if (response.request.header("Authorization") != "Bearer $currentToken") {
                    // Token was refreshed while we waited for the lock — just retry
                    return@runBlocking response.request.newBuilder()
                        .header("Authorization", "Bearer $currentToken")
                        .build()
                }

                // Still the same old token — we need to refresh:
                try {
                    val newTokens = authApi.refresh(tokenStorage.getRefreshToken())
                    tokenStorage.saveTokens(newTokens)
                    response.request.newBuilder()
                        .header("Authorization", "Bearer ${newTokens.accessToken}")
                        .build()
                } catch (e: Exception) {
                    null  // refresh failed → propagate 401 to caller
                }
            }
        }
    }
}
```

**Why the double-check inside the lock?**

```
Request 1 arrives at mutex first → refreshes → stores new token T2
Request 2 was waiting → acquires lock → WITHOUT double-check: would refresh AGAIN
                                      → WITH double-check: sees token changed → skips refresh
```

---

## Why `runBlocking` Here Is Acceptable

`Authenticator.authenticate()` is a **synchronous Java interface** — it cannot be a suspend function. `runBlocking` creates a coroutine that blocks the current thread (OkHttp's internal thread pool thread). This is acceptable because:

1. OkHttp's threads are not the main thread — blocking them doesn't cause ANR
2. The block is short (one network call for token refresh)
3. There is no alternative — you cannot call suspend functions from a non-suspend context

---

## Preventing Infinite Retry Loop

```kotlin
override fun authenticate(route: Route?, response: Response): Request? {
    // Guard: if we've already retried once, give up:
    if (response.request.header("X-Auth-Retry") != null) {
        tokenStorage.clearTokens()  // refresh token expired → force logout
        return null                 // null tells OkHttp: stop retrying
    }

    return runBlocking {
        mutex.withLock {
            try {
                val newTokens = authApi.refresh(tokenStorage.getRefreshToken())
                tokenStorage.saveTokens(newTokens)
                response.request.newBuilder()
                    .header("Authorization", "Bearer ${newTokens.accessToken}")
                    .header("X-Auth-Retry", "true")  // mark so we don't retry again
                    .build()
            } catch (e: Exception) {
                null
            }
        }
    }
}
```

---

## ## Traps

**Trap — No double-check inside the lock:**

```kotlin
// WRONG — all 3 requests refresh even though only 1 needs to:
mutex.withLock {
    val newTokens = authApi.refresh(...)   // 3 calls instead of 1
    ...
}

// CORRECT — re-check if the token already changed:
mutex.withLock {
    if (response.request.header("Authorization") == "Bearer ${tokenStorage.getAccessToken()}") {
        // Token unchanged → we are the one who needs to refresh
        val newTokens = authApi.refresh(...)
    }
    // Otherwise → someone else refreshed → just use the new token
}
```

**Trap — Returning null without clearing tokens when refresh token is expired:**

```kotlin
// WRONG — null silently fails, user stays stuck:
} catch (e: HttpException) { null }

// CORRECT — clear credentials and trigger logout:
} catch (e: HttpException) {
    if (e.code() == 401) tokenStorage.clearTokens()
    null
}
```

---

## Memory Trick

```
Token refresh = Mutex + double-check pattern:
  1. Acquire lock (only 1 coroutine refreshes at a time)
  2. Check if token already changed (someone else refreshed while you waited)
  3. If yes: skip refresh, retry with new token
  4. If no: refresh, store, retry

runBlocking in Authenticator = acceptable (OkHttp's thread, not main thread).

Return null = tell OkHttp to stop retrying (propagate the 401 to caller).
"X-Auth-Retry" header = prevents infinite loop (refresh token also expired).
```

---

## Self-Test

1. Three parallel API calls all receive 401 simultaneously. Without a Mutex, what is the worst-case outcome?
2. Why is the double-check inside the lock necessary? Describe the exact race it prevents.
3. Why is `runBlocking` acceptable in `Authenticator.authenticate()`?
4. How do you detect that the refresh token itself is expired? What should you do when that happens?

---

# Q15.3 — JSON Serialization Pitfalls

> **Builds on:** [Q3.3 (reified type parameters)](03_generics_and_variance.md#q33--reified-type-parameters) · [Q2.2 (data classes)](02_classes_and_objects.md#q22--data-classes)
> **Connects to:** [Q13.2 (Data layer mapping)](13_android_architecture.md#q132--clean-architecture-layer-boundaries)

---

## The Core Rule

```
Gson uses Unsafe.allocateInstance() — skips constructors, bypasses null safety.
Non-nullable properties can be null at runtime. NPE happens LATER, not at parse time.

Kotlin Serialization calls the constructor — respects default values, fails fast.
Moshi KSP codegen generates null-safe adapters at compile time.
```

---

## Gson — The Null Safety Bypass

```kotlin
data class User(
    val name: String,    // non-nullable — should never be null
    val age: Int
)

val json = """{"age": 30}"""   // "name" is missing
val user = Gson().fromJson(json, User::class.java)

println(user.name)         // null — Gson bypassed the constructor!
println(user.name.length)  // NullPointerException — here, not at parse time
```

**What Gson actually does:**

```java
// Gson's deserialization path (simplified):
User instance = (User) Unsafe.allocateInstance(User.class);  // no constructor called!
Field nameField = User.class.getDeclaredField("name");
nameField.setAccessible(true);
nameField.set(instance, null);  // sets null despite @NotNull annotation
```

`Unsafe.allocateInstance` bypasses ALL constructors. Kotlin's `@NotNull` annotations are compile-time metadata — they don't prevent field assignment via reflection. The NPE surfaces far from the parse site, making it hard to debug.

---

## Kotlin Serialization — Fails Fast, Respects Defaults

```kotlin
@Serializable
data class User(
    val name: String,
    val age: Int = 0    // default value
)

// Missing required field → exception AT parse time:
Json.decodeFromString<User>("""{"age": 30}""")
// SerializationException: Field 'name' is required but was missing

// Missing optional field → uses default:
Json.decodeFromString<User>("""{"name": "Alice"}""")
// User(name="Alice", age=0)  ← default value used
```

Kotlin Serialization calls the primary constructor — default values work, null-safety is enforced at the boundary.

---

## Moshi — Reflection vs KSP Codegen

**Reflection (runtime):**

```kotlin
val moshi = Moshi.Builder().build()
val adapter = moshi.adapter(User::class.java)
// Inspects class at runtime → null-safety gaps for Kotlin, slower startup
```

**KSP Codegen (compile-time):**

```kotlin
@JsonClass(generateAdapter = true)
data class User(val name: String, val age: Int)
```

```java
// Generated at compile time:
final class UserJsonAdapter {
    public User fromJson(JsonReader reader) throws IOException {
        String name = null;
        int age = 0;
        // ...
        if (name == null) throw new JsonDataException("Required value 'name' missing");
        return new User(name, age);   // calls the real constructor
    }
}
```

```
Reflection Moshi:  runtime inspection → gaps for Kotlin nullability → slower
KSP Moshi codegen: compile-time adapter → null-safe → faster startup → slightly larger APK
```

---

## Annotation Comparison — Same Purpose, Different Libraries

```kotlin
// Gson:
data class User(
    @SerializedName("user_name") val name: String
)

// Kotlin Serialization:
@Serializable
data class User(
    @SerialName("user_name") val name: String
)

// Moshi codegen:
@JsonClass(generateAdapter = true)
data class User(
    @Json(name = "user_name") val name: String
)
```

All three map the JSON key `"user_name"` to the Kotlin property `name`. They cannot be mixed — each annotation belongs to its own library.

---

## Decision Table

| Library | Null safety | Default values | Speed | Use when |
|---|---|---|---|---|
| Gson | ✗ Bypassed | ✗ Ignored | Fast | Legacy code only |
| Kotlin Serialization | ✓ Enforced | ✓ Respected | Fast (codegen) | New code, KMP |
| Moshi + Reflection | ✗ Gaps | ✗ Ignored | Slow startup | — |
| Moshi + KSP codegen | ✓ Enforced | ✓ Respected | Fast | New View-based Android |

---

## ## Traps

**Trap — Gson with a `data class` that has a non-null property missing in JSON:**

```kotlin
// The NPE appears in business logic, not in the parsing code:
val user = Gson().fromJson(json, User::class.java)
showProfile(user)  // NPE here — user.name is null
// Stack trace points to showProfile(), not to the Gson call. Hard to debug.
```

**Trap — Gson ignoring default parameter values:**

```kotlin
data class Config(
    val timeout: Int = 5000   // default
)
val config = Gson().fromJson("""{}""", Config::class.java)
println(config.timeout)   // 0, not 5000 — Gson set the field directly, bypassing constructor
```

**Trap — `@Transient` vs `@kotlinx.serialization.Transient`:**

```kotlin
// Java's @Transient — Gson respects this:
@Transient val secret: String = ""

// Kotlin Serialization needs its own annotation:
@kotlinx.serialization.Transient val secret: String = ""
// Using Java's @Transient here does nothing for kotlinx.serialization
```

---

## Memory Trick

```
Gson = Unsafe.allocateInstance() → no constructor → null safety bypassed.
  Missing field → null in non-nullable prop → NPE far from parse site.
  Fix: switch to Kotlin Serialization or Moshi KSP codegen.

Kotlin Serialization = constructor-based → defaults respected → fails at boundary.
  @SerialName for field renaming. @Transient to exclude fields.

Moshi KSP = compile-time adapter → null-safe → faster → larger APK.
  @JsonClass(generateAdapter = true) on data class.
  @Json(name = "...") for field renaming.

Annotation cheat sheet:
  Gson:              @SerializedName("key")
  kotlinx.serial:    @SerialName("key")
  Moshi:             @Json(name = "key")
  Never mix them.
```

---

## Self-Test

1. You parse `{"age": 30}` into `data class User(val name: String, val age: Int)` with Gson. What is `user.name`? Where does the NPE occur?
2. How does Gson create an instance without calling the constructor? What JVM API does it use?
3. You add `val timeout: Int = 5000` to a data class and parse an empty JSON `{}` with Gson. What value does `timeout` have?
4. What does `@JsonClass(generateAdapter = true)` do? What is generated and when?
5. You need to exclude a field from Kotlin Serialization. What annotation do you use?

---

## Phase 15 — Summary

```
┌──────────────────────────────────────────────────────────────────────┐
│  1. addInterceptor = before cache, always runs.                      │
│     addNetworkInterceptor = after cache, only real network calls.   │
│     Auth headers → addInterceptor. Wire logs → addNetworkInterceptor│
│                                                                      │
│  2. Authenticator = reactive 401 handler. Interceptor = proactive.  │
│     Use both: interceptor adds token, authenticator refreshes it.   │
│                                                                      │
│  3. Token refresh = Mutex + double-check inside lock.               │
│     Without: parallel 401s cause duplicate refresh calls.           │
│     Return null from Authenticator = tell OkHttp to stop retrying.  │
│                                                                      │
│  4. Gson bypasses constructors via Unsafe → null safety broken.     │
│     Kotlin Serialization calls constructor → defaults + fast-fail.  │
│     Moshi KSP = compile-time null-safe adapters.                    │
└──────────────────────────────────────────────────────────────────────┘
```

---

*← [Phase 14 — Jetpack Components](14_jetpack_components.md) | [Phase 16 — Android System Internals →](16_android_system_internals.md)*