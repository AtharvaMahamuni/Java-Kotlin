# Phase J0 — JVM Mental Model

These four questions build the foundational mental model every Java developer must have. Before you can understand garbage collection, generics, concurrency, or performance tuning, you need to understand how the JVM represents data, why primitives and references behave differently, and what the bytecode layer actually looks like. Everything else in Java builds on top of this foundation.

---

## J0.1 — Primitives vs References in Java

> **Connects to:** [J0.2 — Autoboxing & Integer Cache](J0_jvm_mental_model.md#j02--autoboxing--integer-cache)

### WHY This Distinction Exists

Java was designed with two fundamentally different kinds of data, and confusing them is the source of some of the most common bugs and performance problems in Java code. The distinction exists for a simple reason: performance. If every integer required a heap allocation, a garbage collector write barrier, and an indirection through a pointer just to do arithmetic, Java would be unusably slow. Primitives exist so that the JVM can work with raw CPU-native data directly on the stack or in registers, with no object overhead whatsoever.

References, on the other hand, exist because Java needs a uniform way to point to heap objects whose lifetimes are managed by the garbage collector. A reference is just a typed pointer — a memory address stored in a variable. The object itself lives on the heap; the variable on the stack holds only the address.

### The 8 Primitive Types

Java has exactly eight primitive types, and they are the only types in the language that are not objects:

| Type | Size | Value range | Default value |
|------|------|-------------|---------------|
| `boolean` | 1 bit (JVM uses int) | `true` / `false` | `false` |
| `byte` | 8 bits, signed | -128 to 127 | `0` |
| `char` | 16 bits, unsigned | 0 to 65535 (Unicode BMP) | `'\u0000'` |
| `short` | 16 bits, signed | -32768 to 32767 | `0` |
| `int` | 32 bits, signed | -2,147,483,648 to 2,147,483,647 | `0` |
| `long` | 64 bits, signed | -2^63 to 2^63-1 | `0L` |
| `float` | 32 bits, IEEE 754 | ~±3.4×10^38 | `0.0f` |
| `double` | 64 bits, IEEE 754 | ~±1.8×10^308 | `0.0` |

All eight are stored directly — their value is the variable. There is no pointer, no header, no metadata.

### Stack vs Heap: A Memory Diagram

Consider these two declarations:

```java
int x = 5;
Integer y = 5;
```

The memory layout is completely different:

```
STACK (current stack frame)
┌─────────────────────────────────┐
│  x = 5              [4 bytes]   │  ← the value itself, right here
│  y = 0x7fa3b200     [8 bytes]   │  ← a pointer (address) to heap
└─────────────────────────────────┘
                │
                │  (reference/pointer)
                ▼
HEAP
┌──────────────────────────────────────────┐
│  Integer object @ 0x7fa3b200             │
│  ┌─────────────────────────────────────┐ │
│  │ Mark Word         [8 bytes]         │ │  ← GC state, hash, lock info
│  │ Class Pointer     [4 bytes]         │ │  ← compressed oop → Integer.class
│  │ int value = 5     [4 bytes]         │ │  ← the actual integer
│  └─────────────────────────────────────┘ │
│  Total: 16 bytes                         │
└──────────────────────────────────────────┘
```

`int x` costs 4 bytes, period. `Integer y` costs 4 bytes for the reference on the stack plus 16 bytes on the heap for the object — a 4× memory overhead just to store the same number. On a 64-bit JVM with compressed ordinary object pointers (compressed oops, which are **enabled by default** on 64-bit JVMs — you'd need `-XX:-UseCompressedOops` to disable them), the class pointer is compressed to 4 bytes, which is why the header totals 12 bytes (8-byte mark word + 4-byte class pointer). The `int` field then adds 4 bytes, giving 16 bytes total (JVM aligns objects to 8-byte boundaries).

### JVM Object Header Detail

Every Java object on the heap starts with a header that the JVM uses internally:

```
Object Header (64-bit JVM with compressed oops)
┌────────────────────────────────────────────┐
│ Mark Word (8 bytes)                        │
│   bits 0-1:  lock state (unlocked/biased)  │
│   bits 2+:   identity hashCode             │
│              GC age bits                   │
│              forwarding pointer (during GC) │
├────────────────────────────────────────────┤
│ Class Pointer (4 bytes, compressed oop)    │
│   → points to the class's metadata         │
└────────────────────────────────────────────┘
Total header: 12 bytes
Then: instance fields (aligned)
```

This header is why even an object with a single `boolean` field costs 16 bytes (12 byte header + 1 byte field + 3 bytes padding to align to 8 bytes). The JVM cannot store anything smaller than 16 bytes on the heap.

### Assignment Semantics: Value Copy vs Pointer Copy

This is the most important behavioral difference. When you assign a primitive, you copy the actual bits:

```java
int a = 10;
int b = a;   // b gets a COPY of the value 10
b = 99;      // a is still 10 — completely independent
```

When you assign a reference, you copy the pointer — both variables now point to the same object:

```java
StringBuilder sb1 = new StringBuilder("hello");
StringBuilder sb2 = sb1;   // sb2 gets a COPY of the pointer
sb2.append(" world");      // modifies the SAME object
System.out.println(sb1);   // prints "hello world" — sb1 sees the change!
```

```
Before mutation:
  sb1 → [StringBuilder @ 0x1000: "hello"]
  sb2 → [StringBuilder @ 0x1000: "hello"]   ← same address

After sb2.append():
  sb1 → [StringBuilder @ 0x1000: "hello world"]
  sb2 → [StringBuilder @ 0x1000: "hello world"]  ← same object was mutated
```

### Interview Trap: Java is Always Pass-by-Value

This is one of the most debated Java interview questions, and the answer is definitive: Java is always pass-by-value. Always. No exceptions. The confusion arises because for reference types, the "value" being passed is the pointer itself.

```java
// This does NOT swap the original variables
void swap(int a, int b) {
    int temp = a;
    a = b;
    b = temp;
    // a and b here are LOCAL COPIES — the caller's variables are unchanged
}

// This also does NOT reassign the caller's reference
void replaceString(String s) {
    s = "new value";   // s is a local copy of the pointer
                       // the caller's reference still points to the original
}

// But this DOES modify the caller's object (because the pointer is shared)
void appendToBuilder(StringBuilder sb) {
    sb.append(" extra");  // sb is a copy of the pointer, but points to same object
                          // mutating through the pointer IS visible to caller
}
```

The mental model: think of a reference as a piece of paper with an address written on it. Passing a reference passes a photocopy of that piece of paper. The recipient can use the address to go modify the house at that address (and the caller will see the change), but they cannot change what address is written on the caller's original paper.

---

## J0.2 — Autoboxing & Integer Cache

> **Builds on:** [J0.1 — Primitives vs References in Java](J0_jvm_mental_model.md#j01--primitives-vs-references-in-java)
> **Connects to:** [J0.3 — String Pool & Interning](J0_jvm_mental_model.md#j03--string-pool--interning)

### WHY Autoboxing Exists

Java's generics system (added in Java 5) only works with reference types. You cannot write `List<int>` — the type parameter must be an object type. But you often want to put integers in a list. Autoboxing is the compiler's solution: it automatically converts between primitives and their wrapper types (`int` ↔ `Integer`, `long` ↔ `Long`, `double` ↔ `Double`, etc.) so you can write `List<Integer>` and use it almost as if it were `List<int>`.

Autoboxing is entirely a compiler feature — the JVM knows nothing about it. The compiler inserts the conversion calls for you at compile time.

### What Autoboxing Actually Compiles To

This is the most critical point: autoboxing does NOT use `new Integer(5)`. It calls `Integer.valueOf(5)`. This distinction matters enormously because `valueOf` uses a cache.

```java
// Source code:
Integer x = 5;

// What the compiler actually generates (decompiles to):
Integer x = Integer.valueOf(5);
```

The bytecode for `Integer x = 5` looks like this:

```bytecode
BIPUSH 5                              ; push the constant 5 (fits in a byte) onto operand stack
INVOKESTATIC java/lang/Integer.valueOf (I)Ljava/lang/Integer;
                                      ; call Integer.valueOf(int) → returns Integer
ASTORE_1                              ; store the returned reference in local variable slot 1
```

Unboxing (`int y = x` where x is `Integer`) compiles to:

```bytecode
ALOAD_1                               ; push the Integer reference onto operand stack
INVOKEVIRTUAL java/lang/Integer.intValue ()I
                                      ; call x.intValue() → returns int value
ISTORE_2                              ; store the int in local variable slot 2
```

### The Integer Cache: -128 to +127

`Integer.valueOf()` is not a simple wrapper around `new Integer()`. The JDK implementation maintains a static cache of `Integer` objects for values in the range -128 to +127 (inclusive). This range is guaranteed by the Java Language Specification. Some JVMs allow extending the upper bound with `-XX:AutoBoxCacheMax=N`, but -128 is always the lower bound.

Here is the relevant JDK source (simplified):

```java
// From java.lang.Integer (simplified)
private static class IntegerCache {
    static final Integer[] cache = new Integer[256];  // -128 to 127
    static {
        for (int i = 0; i < cache.length; i++) {
            cache[i] = new Integer(i - 128);
        }
    }
}

public static Integer valueOf(int i) {
    if (i >= -128 && i <= 127) {
        return IntegerCache.cache[i + 128];  // return cached object
    }
    return new Integer(i);  // only creates new object outside cache range
}
```

### The == Trap

This cache produces one of Java's most famous interview traps:

```java
Integer a = 127;
Integer b = 127;
System.out.println(a == b);    // TRUE — same cached object in IntegerCache

Integer c = 128;
Integer d = 128;
System.out.println(c == d);    // FALSE — two different new Integer objects on heap

System.out.println(c.equals(d)); // TRUE — .equals() compares int values
```

Memory layout for the 127 case:

```
IntegerCache (static, lives in heap)
┌─────────────────────────────────┐
│  cache[255] = Integer(127)      │ ← a and b both point HERE
└─────────────────────────────────┘
       ▲           ▲
       │           │
   a (ref)     b (ref)       ← a == b is TRUE (same address)
```

Memory layout for the 128 case:

```
HEAP
┌─────────────────────┐   ┌─────────────────────┐
│ Integer(128) @ 0x10 │   │ Integer(128) @ 0x20 │
└─────────────────────┘   └─────────────────────┘
         ▲                          ▲
         │                          │
     c (ref)                    d (ref)       ← c == d is FALSE (different addresses)
```

Always use `.equals()` when comparing `Integer` objects. Never use `==` unless you specifically need reference equality.

### NPE on Unboxing Null

Unboxing is a method call under the hood (`intValue()`), and calling a method on `null` always throws `NullPointerException`:

```java
Integer x = null;
int y = x;            // NullPointerException here!
// Compiles to: int y = x.intValue();  — calling intValue() on null → NPE
```

This is a surprisingly common bug. It appears in contexts like:

```java
Map<String, Integer> map = new HashMap<>();
int count = map.get("key");  // NPE if "key" not in map! get() returns null, then unboxing throws
```

The fix is to always check for null before unboxing, or use a default value:

```java
int count = map.getOrDefault("key", 0);  // safe — returns 0 if key absent
```

### Performance: Autoboxing in Loops

Every time the JVM autoboxes a primitive outside the cache range, it allocates a new object on the heap. In a tight loop, this creates massive GC pressure:

```java
// TERRIBLE: creates 1,000,000 Long objects on the heap
Long sum = 0L;
for (int i = 0; i < 1_000_000; i++) {
    sum += i;
    // sum += i compiles to:
    //   LLOAD sum_slot              ; push Long reference
    //   INVOKEVIRTUAL Long.longValue ; unbox to long
    //   ILOAD i_slot                ; push int i
    //   I2L                         ; widen i to long
    //   LADD                        ; add
    //   INVOKESTATIC Long.valueOf    ; rebox to Long  ← NEW OBJECT EVERY ITERATION
    //   ASTORE sum_slot             ; store new Long reference
}

// CORRECT: use primitive long — zero allocations
long sum = 0L;
for (int i = 0; i < 1_000_000; i++) {
    sum += i;  // pure primitive arithmetic, stays on stack
}
```

The first version creates one million `Long` objects. Each allocation is small but the cumulative GC pressure — filling Eden space, triggering minor GCs, causing stop-the-world pauses — can degrade throughput by an order of magnitude in hot paths.

---

## J0.3 — String Pool & Interning

> **Builds on:** [J0.2 — Autoboxing & Integer Cache](J0_jvm_mental_model.md#j02--autoboxing--integer-cache)
> **Connects to:** [J0.4 — Java Bytecode Basics](J0_jvm_mental_model.md#j04--java-bytecode-basics)

### WHY the String Pool Exists

`String` is by far the most commonly used reference type in Java programs. In a typical enterprise application, the same string values — field names, status codes, HTTP headers, log messages — appear thousands of times. Without pooling, each occurrence would allocate a separate object on the heap with its own character array. The String Pool (also called the String Intern Pool or String Constant Pool) solves this by ensuring that identical string literals share the same object in memory.

Strings are immutable in Java, which makes this sharing safe — no thread can modify a pooled string and corrupt another reference to it.

### Where the Pool Lives

Before Java 7: the String Pool lived in `PermGen` (Permanent Generation), a fixed-size memory region separate from the regular heap. This caused `OutOfMemoryError: PermGen space` if too many strings were interned.

Java 7+: the String Pool was moved to the main heap. This means it can grow with the heap, is subject to garbage collection (unreferenced pool strings can be collected), and benefits from the same GC tuning as the rest of your objects.

### How String Literals Work

When the JVM loads a class, it processes all string literals at class-load time. Each unique literal is added to the pool once. At runtime, whenever code encounters a string literal, it gets a reference to the pool entry — no new object is created.

```java
String a = "hello";   // JVM checks pool: "hello" exists? No → create in pool, a points to it
String b = "hello";   // JVM checks pool: "hello" exists? Yes → b points to SAME object as a
String c = "hello";   // Same pool object again
```

Memory layout:

```
String Pool (in heap since Java 7)
┌──────────────────────────────────────┐
│  "hello" @ 0x5000                    │
│    value[] = ['h','e','l','l','o']   │
└──────────────────────────────────────┘
       ▲         ▲         ▲
       │         │         │
     a (ref)  b (ref)   c (ref)     ← all three variables reference the SAME object
```

`a == b == c` evaluates to `true` — they all hold the identical pointer.

### `new String()` Bypasses the Pool

```java
String pool = "hello";                     // pool entry
String heap = new String("hello");         // explicitly creates NEW object, ignores pool
System.out.println(pool == heap);          // FALSE — different objects
System.out.println(pool.equals(heap));     // TRUE  — same content
```

`new String("hello")` is an explicit constructor call and the JVM always allocates a new object when you use `new`. The pool entry for `"hello"` still exists (it was created when the literal `"hello"` was processed), but `heap` points to a different object.

### The Four Cases: `==` Comparisons

These four cases cover every scenario you'll see in interviews:

```java
// Case 1: literal vs literal — SAME pool object
"hello" == "hello"                       // TRUE

// Case 2: new String vs literal — different objects
new String("hello") == "hello"           // FALSE

// Case 3: compile-time constant folding — compiler resolves this at compile time
"hel" + "lo" == "hello"                  // TRUE!
// The compiler sees two string literals and folds them to "hello" at compile time
// Both sides become references to the same pool entry

// Case 4: runtime concatenation — creates a new object at runtime
String prefix = "hel";
prefix + "lo" == "hello"                 // FALSE
// prefix is a variable (not a compile-time constant), so + is evaluated at runtime
// creating a new String object that is NOT in the pool
```

Case 3 is the one that surprises people most. If every operand in a string concatenation is a compile-time constant (a literal or a `static final` field), the Java compiler folds the entire expression to a single string literal at compile time. The bytecode will contain `LDC "hello"` — it never even sees the `+` operator.

### String.intern()

`String.intern()` manually moves a string into the pool (or returns the existing pool entry if the content is already there):

```java
String heap = new String("hello");        // NOT in pool (new object)
String pooled = heap.intern();            // returns the pool entry for "hello"
System.out.println(pooled == "hello");    // TRUE — pooled IS the pool entry
```

Use `intern()` carefully. In some systems with enormous numbers of unique strings (e.g., user-supplied data), interning can exhaust the pool and cause performance problems because pool lookups require hash computation and contention on the pool's internal lock.

### StringBuilder vs String Concatenation

String `+` in a loop is a classic performance mistake:

```java
// BAD: O(n²) — each iteration creates a new String
String result = "";
for (int i = 0; i < n; i++) {
    result = result + items[i];  // creates a new String object every time
}
// After iteration 1: "item0"           (6 chars copied)
// After iteration 2: "item0item1"      (11 chars copied)
// After iteration 3: "item0item1item2" (17 chars copied)
// Total work: O(1+2+3+...+n) = O(n²)
```

For concatenation in Java 8, the compiler compiles `a + b` (where a and b are non-constant expressions) to `StringBuilder.append()` chains. But a loop that accumulates into a String variable still creates new objects every iteration because the compiler does not lift the StringBuilder outside the loop:

```java
// Bytecode for:  result = result + items[i];
NEW java/lang/StringBuilder
DUP
INVOKESPECIAL java/lang/StringBuilder.<init> ()V
ALOAD result_slot          ; push result
INVOKEVIRTUAL StringBuilder.append (Ljava/lang/String;)Ljava/lang/StringBuilder;
ALOAD items_slot           ; push items
ILOAD i_slot               ; push i
AALOAD                     ; items[i]
INVOKEVIRTUAL StringBuilder.append (Ljava/lang/String;)Ljava/lang/StringBuilder;
INVOKEVIRTUAL StringBuilder.toString ()Ljava/lang/String;
ASTORE result_slot         ; store new String in result
```

A new `StringBuilder` is created EVERY ITERATION. Instead:

```java
// GOOD: O(n) — StringBuilder amortizes its internal array growth
StringBuilder sb = new StringBuilder();
for (int i = 0; i < n; i++) {
    sb.append(items[i]);
}
String result = sb.toString();   // one final allocation
```

In Java 9+, concatenation outside loops uses `invokedynamic StringConcatFactory` which can be even more efficient than `StringBuilder`, choosing the optimal strategy at JIT compile time.

### Interview Trap: How Many Objects Does `new String("hello")` Create?

The answer is 1 or 2, depending on whether `"hello"` is already in the pool:

- If `"hello"` is NOT yet in the pool (first time this code runs in this JVM): 2 objects are created — the pool entry for the literal `"hello"`, and the new heap object.
- If `"hello"` IS already in the pool: 1 object is created — just the new heap object. The pool entry already exists.

In practice, in almost all programs, the pool entry exists because the literal `"hello"` appears in the source code somewhere and was placed in the pool at class load time.

---

## J0.4 — Java Bytecode Basics

> **Builds on:** [J0.3 — String Pool & Interning](J0_jvm_mental_model.md#j03--string-pool--interning)

### WHY Understanding Bytecode Matters

Java's promise is "write once, run anywhere." The mechanism that makes this work is bytecode: the Java compiler (`javac`) compiles `.java` source files to `.class` files containing bytecode — a platform-independent instruction set for the Java Virtual Machine. Each JVM (HotSpot on Linux, on Windows, on macOS, on ARM, on x86) interprets or JIT-compiles the same bytecode to that platform's native instructions.

Understanding bytecode lets you reason about:
- Why certain patterns are faster than others (what the JIT actually compiles)
- What "autoboxing" and "type erasure" actually produce
- How the JVM's Just-In-Time compiler optimizes your code (it works on bytecode)
- What happens when generics are involved (type erasure leaves CHECKCAST instructions)

### The JVM is a Stack-Based Machine

Unlike the x86/ARM CPUs in your computer (which use registers — `rax`, `rbx`, etc. — to hold operands), the JVM's execution model is stack-based. Each method invocation gets its own stack frame containing:

1. **Operand stack**: a LIFO stack where all operations happen. You push operands, invoke an instruction, and it pops operands and pushes results.
2. **Local variable array**: indexed slots (0, 1, 2, ...) that hold the method's parameters and local variables. Slot 0 is always `this` for instance methods.

```
Method Stack Frame
┌─────────────────────────────────┐
│ Local Variables (array)         │
│   slot 0: this (instance ref)   │
│   slot 1: param1                │
│   slot 2: param2                │
│   slot 3: local variable        │
│   ...                           │
├─────────────────────────────────┤
│ Operand Stack (top-of-stack →)  │
│   [ ][ ][ ][val3][val2][val1]   │
│                         ↑ top   │
└─────────────────────────────────┘
```

### Core Opcodes

#### Load Instructions (local variable → operand stack)

| Opcode | Meaning |
|--------|---------|
| `ILOAD n` | Push int from local slot n |
| `LLOAD n` | Push long from local slot n |
| `FLOAD n` | Push float from local slot n |
| `DLOAD n` | Push double from local slot n |
| `ALOAD n` | Push reference (object/array) from local slot n |
| `ILOAD_0` through `ILOAD_3` | Shorthand for slots 0–3 (more compact encoding) |

#### Store Instructions (operand stack → local variable)

| Opcode | Meaning |
|--------|---------|
| `ISTORE n` | Pop int and store in local slot n |
| `ASTORE n` | Pop reference and store in local slot n |

#### Push Constants

| Opcode | Meaning |
|--------|---------|
| `ICONST_m1` to `ICONST_5` | Push int constant -1 through 5 (single-byte instruction) |
| `BIPUSH n` | Push byte-sized int constant (-128 to 127) |
| `SIPUSH n` | Push short-sized int constant (-32768 to 32767) |
| `LDC` | Push constant from constant pool (String, larger int, float, Class) |
| `LDC2_W` | Push long or double constant from constant pool |

#### Arithmetic

| Opcode | Meaning |
|--------|---------|
| `IADD` | Pop two ints, push sum |
| `ISUB` | Pop two ints, push difference (second - top) |
| `IMUL` | Pop two ints, push product |
| `IDIV` | Pop two ints, push quotient |
| `IREM` | Pop two ints, push remainder |
| `INEG` | Negate top int |
| `LADD`, `DADD` | Same for long, double |

#### Method Invocation (most important for interviews)

| Opcode | Used for | Dispatch mechanism |
|--------|----------|-------------------|
| `INVOKEVIRTUAL` | Non-final instance methods on classes | vtable lookup |
| `INVOKEINTERFACE` | Methods declared in an interface | itable lookup |
| `INVOKESPECIAL` | Constructors, private methods, super calls | direct (no polymorphism) |
| `INVOKESTATIC` | Static methods | direct (no dispatch) |
| `INVOKEDYNAMIC` | Lambda factories, string concatenation (Java 9+) | bootstrap method |

#### Type Operations

| Opcode | Meaning |
|--------|---------|
| `CHECKCAST` | Verify top-of-stack reference is instance of type; throw ClassCastException if not |
| `INSTANCEOF` | Pop reference, push 1 if instance of type, 0 if not (never throws) |
| `I2L`, `I2D` | Widen int to long or double |
| `L2I`, `D2I` | Narrow long/double to int (may lose data) |

### Worked Example: Arithmetic Expression

```java
int result = a * b + c;
// Local variables: a=slot1, b=slot2, c=slot3, result=slot4
```

Bytecode (with operand stack state shown):

```bytecode
; Stack: []
ILOAD_1    ; push a         Stack: [a]
ILOAD_2    ; push b         Stack: [a, b]
IMUL       ; pop a,b → a*b  Stack: [a*b]
ILOAD_3    ; push c         Stack: [a*b, c]
IADD       ; pop both → sum Stack: [a*b+c]
ISTORE_4   ; pop → result   Stack: []
```

### Worked Example: Object Creation and Method Call

```java
String s = new String("hello");
int len = s.length();
```

```bytecode
; Create new String object
NEW java/lang/String                 ; allocate uninitialized String object, push ref
DUP                                  ; duplicate ref (one for ASTORE, one for constructor)
LDC "hello"                          ; push string literal from constant pool
INVOKESPECIAL java/lang/String.<init> (Ljava/lang/String;)V
                                     ; call constructor (pops ref + arg, initializes object)
ASTORE_1                             ; store ref in local slot 1 (s)

; Call s.length()
ALOAD_1                              ; push s
INVOKEVIRTUAL java/lang/String.length ()I
                                     ; virtual dispatch: call length() on String (or subclass)
                                     ; pops ref, pushes int result
ISTORE_2                             ; store int in local slot 2 (len)
```

### INVOKEVIRTUAL vs INVOKEINTERFACE

Both support polymorphism, but through different lookup mechanisms:

**INVOKEVIRTUAL** uses the vtable (virtual method table). Each class has a vtable — an array of method pointers. The JVM looks up the method by its index in the vtable. This index is fixed at class-load time and is the same for all classes in the hierarchy. Lookup is O(1).

```
ArrayList's vtable (excerpt):
  [0]: Object.hashCode
  [1]: Object.equals
  ...
  [k]: List.size      ← fixed index k for all List implementations
  ...
```

**INVOKEINTERFACE** uses the itable (interface method table). An interface can be implemented by any class in any hierarchy, so the method's position is not fixed. The JVM must search the itable — a secondary table — to find the correct implementation. This is slightly more expensive than vtable lookup, though the JIT often optimizes both to direct calls when it can determine the receiver type is monomorphic (always the same type).

```java
List<String> list = new ArrayList<>();
list.size();   // INVOKEINTERFACE — lookup via itable (List interface)

ArrayList<String> al = new ArrayList<>();
al.size();     // INVOKEVIRTUAL — lookup via vtable (ArrayList class)
```

### INVOKEDYNAMIC and Lambdas

`INVOKEDYNAMIC` (added in Java 7, heavily used since Java 8) defers method dispatch to a "bootstrap method" that runs once to wire up the actual call target. The JVM calls the bootstrap method on first invocation; it returns a `CallSite` whose target is then used for all subsequent invocations.

Lambdas compile to `INVOKEDYNAMIC` that calls `LambdaMetafactory.metafactory()`. This is why lambdas in Java 8+ are NOT anonymous inner classes — they are dynamically generated at runtime using `INVOKEDYNAMIC` plus a generated class (much more efficient):

```java
Runnable r = () -> System.out.println("hello");
// Compiles to:
INVOKEDYNAMIC run()Ljava/lang/Runnable;
  [BootstrapMethod: LambdaMetafactory.metafactory, ...]
```

String concatenation in Java 9+ uses the same mechanism:

```java
String s = a + b;
// Java 9+ compiles to:
INVOKEDYNAMIC makeConcatWithConstants(Ljava/lang/String;Ljava/lang/String;)Ljava/lang/String;
  [BootstrapMethod: StringConcatFactory.makeConcatWithConstants, ...]
```

This allows the JDK to choose the optimal concatenation strategy per use site, without recompiling your code.

### Interview Trap: INVOKEVIRTUAL vs INVOKEINTERFACE Performance

Both `INVOKEVIRTUAL` and `INVOKEINTERFACE` are subject to JIT devirtualization — if the JIT can prove that a call site always dispatches to the same concrete type (monomorphic call site), it replaces the dispatch with a direct call (inline or direct jump). This eliminates the table lookup entirely.

The theoretical slowness of `INVOKEINTERFACE` is rarely significant in practice because of this optimization. However, if a call site is polymorphic (two types) or megamorphic (three or more types), the JIT falls back to the table lookup, and `INVOKEINTERFACE` is genuinely slightly slower due to the itable search.

### JIT Speculative Inlining and Deoptimization

This is the mechanism that makes call-site polymorphism a real performance concern — not just a theoretical one.

**Phase 1 — Monomorphic inlining:**
When a call site has only ever seen one concrete type, the JIT speculatively inlines the method body directly at the call site, as if you had written the code inline. No vtable lookup, no indirect call — just a direct register-to-register sequence.

```
// Source:
renderer.draw(shape);   // shape is always Circle at this call site

// JIT compiles to (roughly):
// No virtual dispatch — inlined directly:
// [draw_circle_asm_code here]
```

**Phase 2 — Type check guard:**
The JIT inserts a cheap type guard before the inlined code: "if the receiver is still a `Circle`, execute the inlined code. Otherwise, jump to the *uncommon trap*."

```
if (shape.class != Circle.class) goto uncommon_trap;
// inlined Circle.draw() code:
...
```

The guard costs ~1 cycle — essentially free on a well-predicted branch.

**Phase 3 — Deoptimization trigger:**
The first time a `Rectangle` arrives at this call site, the guard fails. The JVM enters the **uncommon trap**: the currently executing frame is unwound, native compiled code is discarded for this method, and execution falls back to the interpreter.

**Phase 4 — Re-compilation:**
After enough interpreter cycles, the JIT recompiles the method. Now it emits a bimorphic inline cache (two type guards, two inlined paths). If a third type appears, the cache overflows and becomes megamorphic — the JIT gives up on inlining and reverts to a plain vtable/itable lookup.

```
Call site states:
  UNINITIALIZED  →  MONOMORPHIC (1 type, inlined, fast)
                 →  BIMORPHIC   (2 types, two guards, still fast)
                 →  MEGAMORPHIC (3+ types, table lookup, no inlining)
```

**Why this matters for interviews:**
> "Why does adding a second implementation of an interface slow down my hot path?"
> Because the call site transitions from monomorphic → bimorphic, the JIT must deoptimize, discard the compiled code, and recompile with two type guards. During that window the method runs interpreted. In microbenchmarks this shows up as a sudden spike in latency when the second type first appears.

> "I introduced a logging proxy that wraps my service. Performance dropped 30%. Why?"
> The proxy introduces a second concrete type at every call site that previously saw only the real implementation — all those sites become bimorphic and lose their inlined fast paths.

---

## Master Summary: JVM Mental Model in 4 Points

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  MASTER SUMMARY: JVM Mental Model in 4 Points                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│  1. PRIMITIVES vs REFERENCES                                                  │
│     • Primitives live on stack BY VALUE (int = 4 bytes, that's it)           │
│     • References live on stack but POINT to heap objects                      │
│     • Integer on heap = 16 bytes (12 header + 4 field) → 4× overhead vs int  │
│     • Java is ALWAYS pass-by-value — references pass a copy of the pointer   │
│                                                                               │
│  2. AUTOBOXING = Integer.valueOf(), NOT new Integer()                         │
│     • Cache covers -128 to +127: Integer a=127; Integer b=127; a==b is TRUE  │
│     • Outside cache: Integer a=128; Integer b=128; a==b is FALSE             │
│     • Unboxing null throws NPE (calls null.intValue())                        │
│     • Autoboxing in loops creates massive GC pressure — use primitives        │
│                                                                               │
│  3. STRING POOL                                                               │
│     • Literals share pool objects — all "hello" literals are the SAME object │
│     • new String("hello") bypasses pool → creates new heap object            │
│     • == is pointer equality; always use .equals() for content comparison    │
│     • Compile-time constants are folded: "hel"+"lo" == "hello" is TRUE       │
│     • String + in loops is O(n²) — use StringBuilder                         │
│                                                                               │
│  4. JVM IS STACK-BASED                                                        │
│     • Operands are pushed/popped from operand stack (not CPU registers)       │
│     • INVOKEVIRTUAL: class method via vtable (O(1) lookup)                   │
│     • INVOKEINTERFACE: interface method via itable (slightly slower)          │
│     • INVOKESTATIC: direct call, no dispatch                                  │
│     • INVOKEDYNAMIC: bootstrap → CallSite (used for lambdas, String concat)  │
│                                                                               │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

*Next: [Phase J1 — Type System →](J1_type_system.md)*
