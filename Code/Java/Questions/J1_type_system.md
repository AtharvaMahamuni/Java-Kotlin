# Phase J1 — Type System

This phase covers the mechanics of Java's type system: the eight primitive types, how the JVM handles type conversions, the casting rules, how null fits into the type hierarchy, and the famous array covariance problem. These questions explain the why behind rules that Java developers often memorize without truly understanding.

---

## J1.1 — Java's 8 Primitive Types

> **Builds on:** [J0.1 — Primitives vs References in Java](J0_jvm_mental_model.md#j01--primitives-vs-references-in-java)
> **Connects to:** [J1.2 — Type Casting & instanceof](J1_type_system.md#j12--type-casting--instanceof)

### The Concrete Picture

Starting reality: Java has 8 types that live outside the object hierarchy.

```
int x = 5;        // stack slot, 4 bytes, direct value
Integer obj = 5;  // heap pointer → Integer object (header + int field)

Widening chain (implicit, left to right):
  byte(8b) → short(16b) → int(32b) → long(64b) → float(32b) → double(64b)
                                char(16b) ──►  int

Narrowing (requires cast, may truncate):
  int 300 = 0x0000_0001_0010_1100
  (byte)300 ──► keeps only low 8 bits ──► 0010_1100 = 44

JVM operand stack: boolean/byte/char/short ALL become int slots
  byte a = 10; byte b = 20;
  ILOAD a ──► (int)10   ILOAD b ──► (int)20   IADD ──► 30   I2B ──► (byte)30
```

### WHY Primitives Exist

Java is an object-oriented language, but it is not a purely object-oriented language. Unlike Smalltalk or Kotlin (with its value classes), Java has eight types that are not objects and do not inherit from `Object`. They exist entirely for performance.

Consider what it would cost to make `int` a full object: every arithmetic operation would require a heap allocation, a garbage collector write barrier, a pointer dereference, and eventually a GC cycle to clean up. On modern hardware, a CPU can execute a 32-bit integer addition in a single clock cycle (~0.3 nanoseconds). An object allocation requires finding free space, zeroing memory, and updating GC metadata — thousands of times slower. For a numerical computation doing millions of arithmetic operations, this difference is existential.

Primitives let the JVM and JIT compiler work with data the same way native code does: values in registers, on the stack, or in tightly-packed arrays without pointer indirection.

### The Complete Primitive Type Table

| Type | Size | Range | Default | JVM operand stack type |
|------|------|-------|---------|------------------------|
| `boolean` | 1 bit (stored as int in JVM) | `true` / `false` | `false` | int |
| `byte` | 8 bits, signed | -128 to 127 | `0` | int |
| `char` | 16 bits, unsigned | 0 to 65535 (Unicode BMP) | `'\u0000'` | int |
| `short` | 16 bits, signed | -32768 to 32767 | `0` | int |
| `int` | 32 bits, signed | -2^31 to 2^31-1 | `0` | int |
| `long` | 64 bits, signed | -2^63 to 2^63-1 | `0L` | long |
| `float` | 32 bits, IEEE 754 | ~±3.4×10^38 | `0.0f` | float |
| `double` | 64 bits, IEEE 754 | ~±1.8×10^308 | `0.0` | double |

### JVM Treats Small Types as int on the Operand Stack

This is a crucial implementation detail: the JVM operand stack has no native support for `boolean`, `byte`, `char`, or `short`. All four are represented as 32-bit `int` values on the operand stack. The JVM specification says:

- `boolean` is stored as int (0 = false, 1 = true)
- `byte` arithmetic is done as int, then truncated when stored
- `char` arithmetic is done as int (unsigned 16-bit)
- `short` arithmetic is done as int, then truncated when stored

The smaller representations only matter for arrays (`boolean[]`, `byte[]`, `char[]`, `short[]`) and object fields, where the JVM DOES use the compact representation to save memory. But on the operand stack and in local variable slots, they are always int.

This means the bytecode for `byte + byte` is exactly the same as `int + int`:

```java
byte a = 10;
byte b = 20;
byte c = (byte)(a + b);

// Bytecode:
ILOAD_1       ; push a (as int)
ILOAD_2       ; push b (as int)
IADD          ; add as ints → result is 30 (as int)
I2B           ; convert int to byte (truncate to 8 bits, sign-extend)
ISTORE_3      ; store as int in local slot, but narrowed to byte range
```

### Widening Conversions (Implicit, Always Safe)

Widening conversions go from a smaller type to a larger type. The compiler inserts them automatically — you never need a cast:

```
byte → short → int → long → float → double
                char ↗
```

The rule is: you can always go right along this chain without losing information... mostly. There is one subtle exception: converting a large `int` or `long` to `float` or a large `long` to `double` can lose precision (not magnitude, but precision — the floating point type has fewer mantissa bits than the integer type):

```java
int bigInt = 123456789;
float f = bigInt;         // widening — no cast needed
System.out.println(f);    // prints 1.23456792E8 — NOT 123456789!
                          // float only has 23 mantissa bits (~7 decimal digits)
                          // int has 32 bits — precision is lost!

long bigLong = 123456789012345678L;
double d = bigLong;       // widening — no cast needed
System.out.println(d);    // prints 1.2345678901234568E17 — last digits wrong
```

### Narrowing Conversions (Explicit Cast Required, May Lose Data)

Going the other direction requires an explicit cast, which is the programmer telling the compiler "I know this might lose information; I accept responsibility":

```java
int i = 300;
byte b = (byte) i;
// 300 in binary: 0000_0001_0010_1100
// byte keeps only the low 8 bits: 0010_1100 = 44
System.out.println(b);   // prints 44 — not 300!
```

Let's trace this through the bit pattern:

```
i = 300
Binary: 0000 0000 0000 0000 0000 0001 0010 1100
        ^^^^^^^^^^^^^^^^^^^^^^^^ ← discarded (high 24 bits)
                                 0010 1100 ← kept (low 8 bits)

0010 1100 as signed byte = 44 (positive, since MSB is 0)
```

Another example where the sign changes:

```java
int i = 200;
byte b = (byte) i;
// 200 in binary: 0000 0000 0000 0000 0000 0000 1100 1000
// Low 8 bits: 1100 1000 = -56 as signed byte (MSB is 1 → negative)
System.out.println(b);   // prints -56!
```

### Integer Overflow: Silent Wraparound

Java integer arithmetic never throws an exception on overflow. It simply wraps around using two's complement arithmetic:

```java
int max = Integer.MAX_VALUE;    // 2,147,483,647 = 0x7FFFFFFF
System.out.println(max + 1);   // prints -2,147,483,648 = 0x80000000
                               // Integer.MIN_VALUE — no exception!

// This is actually defined behavior in Java (unlike C/C++ where it's UB)
System.out.println(Integer.MAX_VALUE + 1 == Integer.MIN_VALUE); // true
```

Memory layout of two's complement overflow:

```
0x7FFFFFFF = 0111 1111 1111 1111 1111 1111 1111 1111 = MAX_VALUE
+ 1
= 1000 0000 0000 0000 0000 0000 0000 0000 = 0x80000000 = MIN_VALUE
```

This is a source of security bugs. If you are doing arithmetic that might overflow (computing array indices, financial calculations), use `Math.addExact(a, b)` which throws `ArithmeticException` on overflow, or use `long`/`BigInteger`.

### IEEE 754 Traps with float and double

Floating point arithmetic is not the same as mathematical real arithmetic. The IEEE 754 standard defines a binary representation that cannot exactly represent most decimal fractions:

```java
System.out.println(0.1 + 0.2);          // 0.30000000000000004 — NOT 0.3!
System.out.println(0.1 + 0.2 == 0.3);   // FALSE

// Reason: 0.1 in binary is 0.0001100110011... (repeating) — not exactly representable
// The stored value is slightly off, and the errors accumulate

// Fix: use BigDecimal for exact decimal arithmetic
BigDecimal result = new BigDecimal("0.1").add(new BigDecimal("0.2"));
System.out.println(result);              // 0.3 (exact)
```

Special IEEE 754 values (these all exist as actual bit patterns):

```java
double posInf = 1.0 / 0.0;              // Double.POSITIVE_INFINITY
double negInf = -1.0 / 0.0;             // Double.NEGATIVE_INFINITY
double nan    = 0.0 / 0.0;              // NaN (Not a Number)

System.out.println(posInf);             // Infinity
System.out.println(Double.isInfinite(posInf)); // true

// NaN is not equal to anything — including itself!
System.out.println(nan == nan);         // FALSE — this is the only value in Java where x == x is false
System.out.println(Double.isNaN(nan));  // TRUE — the correct way to check for NaN

// Infinity arithmetic
System.out.println(posInf + 1);         // Infinity
System.out.println(posInf - posInf);    // NaN
```

### Interview Trap: char Arithmetic Promotion

`char` is a 16-bit unsigned integer type (0 to 65535). When you do arithmetic on `char` values, the JVM promotes them to `int` first, and the result is an `int`. This means:

```java
char c = 'A';          // 'A' = 65
char c2 = c + 1;       // COMPILE ERROR: possible lossy conversion from int to char!
                       // c + 1 produces an int (66), which doesn't fit in char without cast

char c3 = (char)(c + 1);  // OK: explicit cast back to char
char c4 = 'A' + 1;         // OK! 'A' + 1 is a COMPILE-TIME CONSTANT (both are literals)
                           // the compiler evaluates it to 66 at compile time and checks it fits char
```

The key distinction: if the entire expression is a compile-time constant and the value fits in the target type, no cast is needed. If any operand is a variable, promotion to `int` occurs and an explicit cast is required.

### Memory Trick

```
WIDENING   = byte → short → int → long → float → double (char → int branch)
           = NO CAST needed, always safe (precision may slip: int→float)
NARROWING  = MUST CAST, high bits discarded: (byte)300 = 44, (byte)200 = -56
OVERFLOW   = silent wraparound: MAX_VALUE + 1 = MIN_VALUE (two's complement)
IEEE 754   = 0.1 + 0.2 != 0.3   |   NaN != NaN (only value not equal to itself)
JVM STACK  = boolean/byte/char/short → all stored as int on operand stack
char TRAP  = char c='A'; char c2 = c+1; // ERROR: result is int, not char
```

---

## J1.2 — Type Casting & instanceof

> **Builds on:** [J1.1 — Java's 8 Primitive Types](J1_type_system.md#j11--javas-8-primitive-types)
> **Connects to:** [J1.3 — Null in Java](J1_type_system.md#j13--null-in-java)

### The Concrete Picture

Starting hierarchy: Dog extends Animal extends Object.

```
Dog dog = new Dog();              // heap: [Dog object @ 0x1000]

Upcast (implicit, always safe):
  dog ──► Animal animal = dog;   // same pointer, narrower declared type
  dog ──► Object  obj   = dog;   // same pointer, even narrower view

Downcast (explicit, runtime check):
  Object obj = Integer.valueOf(42);   // declared: Object, actual: Integer
  String s = (String) obj;           // compiles → CHECKCAST String
                                     // runtime: Integer != String → ClassCastException

CHECKCAST bytecode flow:
  ALOAD obj ──► peek stack ──► actual type Integer?
                ──► target type String?
                ──► mismatch ──► throw ClassCastException

instanceof (never throws, returns boolean):
  obj instanceof String  ──► false (Integer, not String)
  null instanceof String ──► always false, never NPE
```

### WHY Casting Exists

Java's type system is static — the compiler knows the declared type of every variable. But Java also supports polymorphism: a variable declared as `Animal` might hold a `Dog` object at runtime. Sometimes you need to use the object as its actual runtime type (to call `Dog`-specific methods), but the compiler only knows the declared type. Casting is the mechanism to tell the compiler "at runtime, this reference will be of type X — let me treat it as such."

The compiler cannot always verify this claim at compile time, so the JVM checks it at runtime. This is a fundamental tension between static typing (compile-time safety) and polymorphism (runtime flexibility).

### Upcasting: Always Safe, Always Implicit

Moving up the type hierarchy (from a more specific type to a more general type) is always safe and never loses information. The compiler allows it without any syntax:

```java
Dog dog = new Dog();
Animal animal = dog;     // upcast: Dog → Animal, implicit, no cast syntax needed
Object obj = dog;        // upcast: Dog → Object, also implicit

// No bytecode cast instruction is generated for upcasting
// The JVM simply uses the same reference with a different declared type
```

```
Type Hierarchy:
  Object
    └── Animal
          └── Dog    ← actual runtime type

  dog  → [Dog object on heap]
  animal → [same Dog object]   // same pointer, but declared type is Animal
  obj    → [same Dog object]   // same pointer, but declared type is Object
```

### Downcasting: Compiles but Checked at Runtime

Moving down the hierarchy (from general to specific) requires an explicit cast. The compiler cannot guarantee this is safe — it depends on the actual runtime type of the object:

```java
Object obj = "hello";          // upcast String → Object
String s = (String) obj;       // downcast Object → String — compiler allows this
System.out.println(s.length()); // works: obj really IS a String at runtime
```

What happens when the cast is wrong:

```java
Object obj = Integer.valueOf(42);    // obj is actually an Integer at runtime
String s = (String) obj;            // COMPILES — compiler can't prove it's wrong
                                    // throws ClassCastException at RUNTIME!
```

### CHECKCAST Bytecode

Every explicit downcast compiles to the `CHECKCAST` bytecode instruction:

```java
String s = (String) obj;

// Bytecode:
ALOAD_1                              ; push obj reference
CHECKCAST java/lang/String           ; if top-of-stack is not a String → throw ClassCastException
                                     ; if it IS a String (or null) → leave ref on stack unchanged
ASTORE_2                             ; store as String s
```

`CHECKCAST` peeks at the top of the stack but does NOT pop it. If the check passes, the same reference stays on the stack — it's just a type assertion. If the check fails, `ClassCastException` is thrown immediately.

Note: `CHECKCAST` does NOT throw if the reference is `null`. Casting `null` to any reference type always succeeds (you can cast `null` to `String`, `Integer`, etc. without exception).

### INSTANCEOF Bytecode

`instanceof` is like CHECKCAST but returns a boolean instead of throwing:

```java
boolean result = obj instanceof String;

// Bytecode:
ALOAD_1                              ; push obj reference
INSTANCEOF java/lang/String          ; pop ref, push 1 if String instance, 0 if not
ISTORE_2                             ; store boolean result
```

`instanceof` with null always returns false — it does not throw:

```java
Object obj = null;
System.out.println(obj instanceof String);  // false — no NPE
```

### Pattern Matching instanceof (Java 16+)

Before Java 16, checking and casting required two operations and a redundant variable:

```java
// Pre-Java 16: verbose and redundant
if (obj instanceof String) {
    String s = (String) obj;   // we KNOW it's a String, but must cast anyway
    System.out.println(s.length());
}
```

Java 16 introduced pattern matching for `instanceof`, combining the check and the cast into a single expression:

```java
// Java 16+: pattern matching
if (obj instanceof String s) {
    // s is already declared as String, no cast needed
    System.out.println(s.length());
    // s is in scope only within this if block where the check passed
}
```

The scope of the pattern variable follows the flow of control. In an `&&` expression, the pattern variable is in scope to the right of the `&&` (because we know the check passed):

```java
// s is in scope for the second condition and the body
if (obj instanceof String s && s.length() > 5) {
    System.out.println(s.toUpperCase());
}

// But NOT after the if block, and NOT in the else block
```

Under the hood, the bytecode still uses `INSTANCEOF` followed by `CHECKCAST` — the compiler generates them for you. There is no additional runtime cost compared to writing the check and cast manually. The benefit is purely in code clarity and eliminating the possibility of forgetting to cast after the check.

Java 21 extended this further with pattern matching in `switch`:

```java
// Java 21: switch on type
switch (obj) {
    case Integer i -> System.out.println("int: " + i);
    case String s  -> System.out.println("string of length: " + s.length());
    case null      -> System.out.println("null");
    default        -> System.out.println("other: " + obj);
}
```

### The Compiler Catches Obviously Wrong Casts

The Java compiler DOES detect some casts as provably impossible at compile time and rejects them:

```java
String s = "hello";
Integer i = (Integer) s;   // COMPILE ERROR: incompatible types
                           // String and Integer are unrelated classes
                           // the compiler knows this can NEVER succeed
```

But the compiler only catches this when both types are concrete classes with no inheritance relationship. If one side is an interface or the types could potentially be related:

```java
Object obj = "hello";
Integer i = (Integer) obj;  // COMPILES — obj is Object, which could hold an Integer
                            // ClassCastException at RUNTIME
```

The key rule: the compiler rejects a cast only when it can prove the cast is ALWAYS wrong. If there is any path where it might be correct, the compiler allows it and the JVM checks at runtime.

### Interview Trap: ClassCastException is a Runtime Exception

`ClassCastException` is a `RuntimeException` — it is unchecked and can be thrown anywhere a downcast occurs. It is NOT caught by `catch (Exception e)` by default (well, it is, since RuntimeException extends Exception), but it is NEVER a compile-time error for cross-castable types.

The practical implication: when working with generics and type erasure, CHECKCAST instructions can appear unexpectedly in generated code, causing `ClassCastException` in places that look perfectly safe in the source code (this is called a "heap pollution" scenario).

### Memory Trick

```
UPCAST   = implicit, Dog → Animal, always safe, no bytecode instruction
DOWNCAST = explicit (String)obj, CHECKCAST at runtime, ClassCastException if wrong
INSTANCEOF = INSTANCEOF bytecode, returns bool, null → false, never throws
PATTERN  = if (obj instanceof String s) { s.length(); }  // Java 16+
COMPILER = rejects IMPOSSIBLE casts (String → Integer) but allows obj → String
NULL CAST= (String) null → OK (CHECKCAST passes for null)
```

---

## J1.3 — Null in Java

> **Builds on:** [J1.2 — Type Casting & instanceof](J1_type_system.md#j12--type-casting--instanceof)
> **Connects to:** [J1.4 — Array Covariance Trap](J1_type_system.md#j14--array-covariance-trap)

### The Concrete Picture

Starting state: every reference type variable can hold the null reference (address 0x0).

```
String s  = null;   // s points to address 0x0000...
Integer i = null;   // also address 0x0000...

NPE sources (what happens when you dereference 0x0):
  s.length()          ──► OS: segfault on addr 0 ──► JVM: NullPointerException
  int n = i           ──► unboxing: i.intValue() ──► NPE (i is null)
  arr.length          ──► arr is null, not an array ──► NPE
  throw t             ──► t is null ──► NPE

Safe null patterns:
  "literal".equals(s)         ──► literal is never null, safe
  Objects.equals(a, b)        ──► handles both sides null
  Optional.ofNullable(value)  ──► forces caller to handle absence

null instanceof T ──► always false, never throws (INSTANCEOF bytecode returns 0 for null)
null == null      ──► true (both are address 0x0)
```

### WHY Null Is Complicated

`null` is one of the most controversial design decisions in Java's history. Tony Hoare, who invented the null reference in ALGOL W (1965), famously called it his "billion-dollar mistake" — the cost of null pointer exceptions and null checks in software worldwide over the decades. Java inherited null from C++ and made it even more pervasive by making every reference type nullable by default.

Understanding null's exact semantics — what it is, what it isn't, and how to work with it safely — is essential for writing correct Java code.

### What null Actually Is

`null` is a special literal value that represents the absence of an object reference. It is not an object. It has no type, no class, no methods. It can be assigned to any reference type variable:

```java
String s = null;
Integer i = null;
Object o = null;
int[] arr = null;
Runnable r = null;
```

All of these are valid. `null` is the zero value for all reference types, just as `0` is the zero value for all integer primitives.

At the JVM level, null is simply a zero-valued reference (the memory address 0x0000...0000). When the JVM tries to dereference null (follow the pointer to access the object), the underlying OS raises a memory protection fault, which the JVM catches and converts to a `NullPointerException`.

### NPE Sources: A Taxonomy

`NullPointerException` can occur in exactly these situations:

```java
// 1. Calling a method on a null reference
String s = null;
s.length();               // NPE

// 2. Accessing a field on a null reference
class Point { int x; }
Point p = null;
int x = p.x;              // NPE

// 3. Unboxing a null wrapper type
Integer i = null;
int n = i;                // NPE — i.intValue() is called, throws NPE
int n2 = i + 1;          // NPE — same reason

// 4. Null as array variable (not null elements)
int[] arr = null;
int len = arr.length;     // NPE — arr is null, not an array
arr[0] = 5;               // NPE — same

// 5. Throwing null
Throwable t = null;
throw t;                  // NPE — you cannot throw null

// 6. Synchronized on null
Object lock = null;
synchronized(lock) { }   // NPE
```

Java 14+ (JEP 358) introduced "helpful NullPointerExceptions" which tell you WHICH variable was null in the error message:

```
Exception in thread "main" java.lang.NullPointerException:
    Cannot invoke "String.length()" because "s" is null
```

### Null and Type Checks

`null instanceof T` is always `false` for ANY type T. The `INSTANCEOF` instruction was specifically designed to return 0 for null references without throwing:

```java
Object obj = null;
System.out.println(obj instanceof String);   // false — never throws
System.out.println(obj instanceof Object);   // false — even Object!
System.out.println(obj == null);             // true — this is the null check
```

`null == null` is `true`. Null comparison uses reference equality, and both sides are the null reference (address 0), so they are equal.

### Null in Arrays

Creating an array of reference type fills it with null references, not with default objects:

```java
String[] names = new String[3];
// names[0] == null  ← default, not ""
// names[1] == null
// names[2] == null

// Careful:
for (String name : names) {
    System.out.println(name.length());   // NPE on first iteration!
}

// Safe pattern:
for (String name : names) {
    if (name != null) {
        System.out.println(name.length());
    }
}
```

### @NonNull / @Nullable Annotations

Java itself does not enforce non-nullability at runtime (unless you explicitly check). But various annotation processors and tools provide compile-time null analysis:

```java
import org.springframework.lang.NonNull;
import org.springframework.lang.Nullable;

// @NonNull: callers must not pass null; you must not return null
@NonNull
public String getDisplayName(@NonNull User user) {
    return user.getName();  // safe — user is annotated NonNull
}

// @Nullable: this might return null; callers must check
@Nullable
public String findById(int id) {
    return repository.get(id);  // might be null
}
```

These annotations are NOT enforced by the JVM. They are hints for tools like:
- **IntelliJ IDEA**: highlights code that violates nullability contracts
- **NullAway** (by Uber): enforces @NonNull/@Nullable at compile time via Error Prone
- **Checker Framework**: powerful compile-time null analysis

### Optional as Null-Avoidance

`Optional<T>` (introduced in Java 8) is a container object that explicitly represents the presence or absence of a value. It forces callers to consciously handle the "missing" case:

```java
// Bad: returns null — caller might forget to check
public String findUserName(int id) {
    User user = userMap.get(id);
    return user == null ? null : user.getName();  // returns null if not found
}

// Bad usage:
String name = findUserName(99);
System.out.println(name.toUpperCase());  // NPE if user not found — forgot null check!

// Good: returns Optional — callers are forced to handle absence
public Optional<String> findUserName(int id) {
    return Optional.ofNullable(userMap.get(id))
                   .map(User::getName);
}

// Good usage:
Optional<String> name = findUserName(99);

// Option 1: provide a default
String display = name.orElse("Unknown");

// Option 2: transform if present, otherwise use default
String display2 = name.map(String::toUpperCase).orElse("UNKNOWN");

// Option 3: throw if absent
String display3 = name.orElseThrow(() -> new EntityNotFoundException("User not found"));

// Option 4: execute code only if present
name.ifPresent(n -> System.out.println("Found: " + n));
```

### Optional Anti-Patterns

Optional is designed specifically as a return type for methods that might not return a value. Misusing it leads to code that is harder to read and slightly less efficient:

```java
// BAD: Optional as field — adds overhead, nulls are fine for fields
class User {
    private Optional<String> nickname;  // Don't do this! Use String nickname (nullable)
}

// BAD: Optional as method parameter — forces callers to wrap in Optional unnecessarily
void process(Optional<String> name) { }    // Bad
void process(@Nullable String name) { }    // Better — use null directly

// BAD: calling .get() without checking — defeats the purpose entirely
Optional<String> opt = findUserName(99);
String name = opt.get();   // throws NoSuchElementException if empty — just as bad as NPE!

// GOOD: use orElse, orElseGet, orElseThrow, ifPresent, map, etc.
```

### Interview Trap: Which Side to Call .equals() On

A common NPE source is calling `.equals()` on a potentially-null variable. The fix is to always call `.equals()` on the side you KNOW is not null:

```java
// BAD: userInput might be null
if (userInput.equals("logout")) { }    // NPE if userInput is null

// GOOD: string literal is never null — call equals on the known-non-null side
if ("logout".equals(userInput)) { }   // safe — if userInput is null, equals() returns false

// Also good: use Objects.equals() for symmetric null-safe comparison
if (Objects.equals(userInput, "logout")) { }  // safe for both sides being null
```

`Objects.equals(a, b)` is implemented as `a == b || (a != null && a.equals(b))` — it handles all null combinations safely.

### Memory Trick

```
NULL = address 0x0, not an object, no type, no methods
NPE sources: method call, field access, unboxing, arr.length, throw null, sync(null)
null instanceof T  = always false (safe, no throw)
(T) null           = always OK (CHECKCAST passes)
SAFE EQUALS: "known".equals(variable)  not  variable.equals("known")
OPTIONAL: return type only; not field, not param; never .get() without .isPresent()
```

---

## J1.4 — Array Covariance Trap

> **Builds on:** [J1.3 — Null in Java](J1_type_system.md#j13--null-in-java)

### The Concrete Picture

Starting state: `String[] strings = {"Alice", "Bob"}` — the actual heap type is `String[]`.

```
Step 1 — covariant upcast (compiles silently):
  String[] strings = {"Alice", "Bob"};
  Object[] objects = strings;   // String[] IS-A Object[] in Java
  // Both variables point to the SAME String[] array on the heap

Step 2 — write through widened reference (compiler approves, runtime rejects):
  objects[0] = "Charlie";       // OK: String compatible with String[]
  objects[1] = Integer.valueOf(42);   // COMPILES (Object[] can hold Integer)
                                      // RUNTIME ──► AASTORE checks actual type
                                      // actual type is String[], not Object[]
                                      // ──► ArrayStoreException!

AASTORE guard (every array write goes through this):
  ALOAD objects  ──► push array ref
  ICONST_1       ──► push index
  ALOAD integer  ──► push value
  AASTORE        ──► check: is Integer assignable to String[]? NO ──► throw

Generics fix (invariant, compile-time safety):
  List<String> strings = new ArrayList<>();
  List<Object> objects = strings;  // COMPILE ERROR — caught before runtime
```

### WHY This Is a Famous Design Flaw

Array covariance is one of the most commonly cited design flaws in Java's type system. It was introduced in Java 1.0 as a pragmatic workaround for not having generics, and by the time generics were added in Java 5, it was too late to remove it without breaking every Java program ever written. Understanding it is critical for understanding why generics made different design choices.

### Arrays Are Covariant

In type theory, a container type `Container<T>` is covariant if `A extends B` implies `Container<A> extends Container<B>`. Java arrays are covariant:

- `String extends Object` → therefore `String[] extends Object[]`
- `Dog extends Animal` → therefore `Dog[] extends Animal[]`

This means the following compiles without any warning:

```java
String[] strings = new String[3];
Object[] objects = strings;          // compiles! String[] is-a Object[]
```

```
Runtime view:
  strings → [String[] @ 0x1000: "a", "b", "c"]
  objects → [String[] @ 0x1000: same array]   ← same actual object!
             The DECLARED type is Object[], but the ACTUAL type is still String[]
```

### The Problem: Compile-Time Safety Is Broken

Here is where covariance causes trouble. Through the `objects` reference, the compiler thinks you have an `Object[]` — so it allows you to put any object into it:

```java
String[] strings = new String[3];
Object[] objects = strings;            // upcast — compiles
objects[0] = "hello";                  // compiles: Object[] can store strings — fine
objects[1] = 42;                       // compiles: Object[] can store Integer — compiler says OK
                                       // BUT: throws ArrayStoreException at RUNTIME!
                                       // because the actual array is String[], not Object[]!
```

The third line is the problem: the compiler sees `Object[] = Integer` and approves it. But at runtime, the JVM knows the actual array is `String[]` and rejects the write.

### AASTORE: The Runtime Guard

Every write to a reference array goes through the `AASTORE` bytecode instruction, which performs a runtime type check:

```java
objects[1] = 42;

// Bytecode:
ALOAD objects_slot      ; push array reference
ICONST_1               ; push index 1
BIPUSH 42              ; push 42 (autoboxed to Integer by the compiler's INVOKESTATIC)
INVOKESTATIC Integer.valueOf
AASTORE                ; pop array ref, index, value; CHECK value type against array's element type
                       ; if check fails → throw ArrayStoreException
                       ; if check passes → store value in array
```

The AASTORE instruction is the JVM's safety net for array covariance. Without it, the heap would be corrupted: you'd have a `String[]` where element 1 is secretly an `Integer`, and any code that reads it expecting a `String` would crash unpredictably.

### Full Scenario with Failure Mode

```java
String[] names = {"Alice", "Bob", null};
Object[] objects = names;         // covariant upcast — compiles, OK

// ATTEMPT 1: storing a String — works, it IS a String
objects[0] = "Charlie";           // OK — String is compatible with String[]

// ATTEMPT 2: storing an Integer — runtime failure
objects[1] = Integer.valueOf(42); // ArrayStoreException!

// ATTEMPT 3: storing null — works, null is always valid
objects[2] = null;                // OK — null is type-compatible with any reference type
```

After the successful store, `names` now contains `["Charlie", "Bob", null]` — the modifications through `objects` ARE visible through `names` because they reference the same array.

### Why Generics Don't Have This Problem

When Java 5 introduced generics, the designers made a deliberate choice: generics are INVARIANT. `List<String>` is NOT a `List<Object>`, even though `String extends Object`. This was specifically to avoid the array covariance trap:

```java
List<String> strings = new ArrayList<>();
List<Object> objects = strings;   // COMPILE ERROR: incompatible types
                                  // List<String> cannot be assigned to List<Object>
```

The compiler rejects this at compile time — you never reach runtime. The type safety is enforced statically.

This is also why you cannot do:

```java
void printAll(List<Object> list) {
    for (Object o : list) System.out.println(o);
}

List<String> names = List.of("Alice", "Bob");
printAll(names);   // COMPILE ERROR — List<String> is not List<Object>
```

The fix is to use wildcard types:

```java
// ? extends Object means: some List of some subtype of Object — read-only
void printAll(List<?> list) {
    for (Object o : list) System.out.println(o);   // can READ as Object — safe
    // list.add("hello");   // COMPILE ERROR — can't write, don't know the element type
}

// ? extends Animal means: some List of some subtype of Animal — read-only
void processAnimals(List<? extends Animal> animals) {
    for (Animal a : animals) a.makeSound();    // can READ as Animal
    // animals.add(new Dog());   // COMPILE ERROR — producer, can't write
}

// ? super Dog means: some List of some supertype of Dog — can write Dog
void addDogs(List<? super Dog> list) {
    list.add(new Dog());    // can write Dogs — always safe (list accepts Dog or supertype)
    // Dog d = list.get(0); // COMPILE ERROR — reading gives Object, not Dog
}
```

This is the PECS principle (Producer Extends, Consumer Super): use `? extends T` when you only read from a collection, use `? super T` when you only write to it.

### Jagged Arrays: Multidimensional Arrays Are Not Matrices

In Java, `int[][]` is not a true two-dimensional array. It is an array of references to `int[]` arrays. Each inner array is an independently allocated object and can have a different length:

```java
int[][] jagged = new int[3][];
jagged[0] = new int[5];   // row 0: 5 elements
jagged[1] = new int[2];   // row 1: 2 elements
jagged[2] = new int[8];   // row 2: 8 elements
```

```
Memory layout:
jagged → [int[][] @ 0x1000]
           [0]: → [int[5] @ 0x2000: 0,0,0,0,0]
           [1]: → [int[2] @ 0x3000: 0,0]
           [2]: → [int[8] @ 0x4000: 0,0,0,0,0,0,0,0]
```

For a true rectangular matrix, all inner arrays happen to have the same length, but that is a programmer convention — not a JVM guarantee. This means:

- Memory is non-contiguous: each inner array is a separate heap object
- No bounds relation: `jagged[0].length` may differ from `jagged[1].length`
- Cache efficiency: for large matrices, non-contiguous layout can hurt CPU cache performance compared to a single flat array (`int[]` of size `rows * cols`)

### Interview Trap: List\<String\> and List\<Object\>

The most common interview question on this topic:

> "Why can't I pass `List<String>` where `List<Object>` is expected?"

The answer is: because generics are invariant. `List<String>` is NOT a subtype of `List<Object>`, even though `String` IS a subtype of `Object`. The reason for this design decision is exactly the array covariance lesson: if `List<String>` WERE a `List<Object>`, you could add an `Integer` to it (through the `List<Object>` reference), corrupting the `List<String>`. Generics prevent this at compile time rather than relying on runtime checks.

```java
// This is why the following would be dangerous if allowed (and it isn't):
List<String> strings = new ArrayList<>();
// If this were allowed:
List<Object> objects = strings;       // NOT allowed (compile error)
objects.add(Integer.valueOf(42));     // would corrupt the String list!
String s = strings.get(0);           // would cause ClassCastException or heap pollution
```

The type-safe alternatives are:
- `List<?>` for read-only access to a list of unknown element type
- `List<? extends T>` for read-only access to a list of T or any subtype
- `List<? super T>` for write access to a list of T or any supertype

### Memory Trick

```
ARRAYS     = covariant: String[] IS-A Object[] (Java 1.0 design choice)
AASTORE    = runtime guard on every array write → ArrayStoreException if type wrong
GENERICS   = invariant: List<String> is NOT List<Object> → compile error (safe)
PECS       = Producer Extends (read), Consumer Super (write)
List<?>    = existential type: read as Object, write nothing (except null)
int[][]    = array of int[] references, jagged, non-contiguous heap layout
```

---

## Master Summary: Type System in 4 Points

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  MASTER SUMMARY: Java Type System in 4 Points                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│  1. PRIMITIVE TYPES AND THE JVM                                               │
│     • JVM has 4 integer stack types: boolean/byte/char/short all use int     │
│     • Widening is implicit (byte→int→long→double), narrowing requires cast   │
│     • Narrowing may silently truncate: (byte) 300 == 44, (byte) 200 == -56  │
│     • int overflow wraps silently: MAX_VALUE + 1 == MIN_VALUE, no exception  │
│     • IEEE 754: 0.1+0.2 ≠ 0.3; NaN≠NaN; 1.0/0.0 == POSITIVE_INFINITY      │
│                                                                               │
│  2. CASTING AND INSTANCEOF                                                    │
│     • Upcasting is implicit and always safe (Dog → Animal, no cast syntax)   │
│     • Downcasting compiles but is checked at runtime: CHECKCAST bytecode     │
│       → throws ClassCastException if actual type doesn't match               │
│     • instanceof: INSTANCEOF bytecode → returns false for wrong type or null │
│     • Pattern matching (Java 16+): instanceof String s combines check+cast   │
│     • null instanceof T is always false; (T) null never throws               │
│                                                                               │
│  3. NULL SEMANTICS                                                            │
│     • null is the zero-value for ALL reference types, not an object          │
│     • NPE sources: method call, field access, unboxing, arr.length on null   │
│     • null instanceof T → always false (safe, never throws)                  │
│     • Call .equals() on the known-non-null side: "literal".equals(variable)  │
│     • Use Optional as return type for missing values; don't use as field     │
│       or parameter; never call .get() without checking .isPresent()          │
│                                                                               │
│  4. ARRAY COVARIANCE vs GENERIC INVARIANCE                                    │
│     • Arrays are covariant: String[] is-a Object[] (Java 1.0 design choice)  │
│     • But writes are runtime-checked via AASTORE → ArrayStoreException       │
│     • Generics are invariant by design: List<String> is NOT List<Object>     │
│       → compiler rejects at compile time, no runtime check needed            │
│     • Wildcard types: List<?> for read-only, List<? extends T> (PECS),      │
│       List<? super T> for write access                                        │
│     • int[][] is an array of int[] references — jagged arrays are valid      │
│                                                                               │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

*← [Phase J0 — JVM Mental Model](J0_jvm_mental_model.md) | [Phase J2 — OOP →](J2_oop.md)*
