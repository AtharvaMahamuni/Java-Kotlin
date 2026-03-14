# Section 1 — Java Core Language (Q1–Q26)

> **Mental model for this entire file:** The JVM is a stack-based virtual machine that
> loads class metadata into metaspace, creates object instances on the heap, and
> manages references on the thread stack. Every question in this file is a consequence
> of that one sentence.

```
   STACK (per thread)        HEAP (shared)         METASPACE
   ─────────────────    ─────────────────────    ─────────────
   local variables      object instances         class metadata
   references ────────► fields                   static vars
   return addresses     arrays                   method bytecode
```

---

## Question Map

| Q | Topic | Key Mechanism |
|---|---|---|
| Q1 | Class | Class loading, metaspace |
| Q2 | Object | Heap allocation, `new` steps |
| Q3 | `==` vs `.equals()` + `hashCode` | Reference vs structural equality |
| Q4 | Encapsulation | Access modifiers, getter/setter |
| Q5 | Access Modifiers | 4 levels, visibility rules |
| Q6 | Inheritance | `extends`, vtable, `super()` |
| Q7 | Polymorphism | Dynamic dispatch, `invokevirtual` |
| Q8 | `instanceof` + Casting | Upcasting vs downcasting, `ClassCastException` |
| Q9 | Abstraction | Abstract class / interface |
| Q10 | Method Overloading | Compile-time resolution |
| Q11 | Method Overriding | vtable, `@Override` |
| Q12 | Interface | Contract, default methods |
| Q13 | Abstract Class | Partial implementation |
| Q14 | Interface vs Abstract Class | Decision table |
| Q15 | Constructor | Object initialization sequence |
| Q16 | Constructor Overloading | `this(...)` chaining |
| Q17 | Static Method | `invokestatic`, no vtable |
| Q18 | Static Variable | Metaspace, class-level state |
| Q19 | Autoboxing / Unboxing | Primitive boxing, null trap |
| Q20 | `final` keyword | Reference vs object immutability |
| Q21 | Immutability | Thread safety without locks |
| Q22 | String Pool + `StringBuilder` | Interning, `+` in loops |
| Q23 | Checked vs Unchecked Exceptions | `throws` table, Kotlin difference |
| Q24 | `this` keyword | Self-reference, constructor chaining |
| Q25 | `super` keyword | Parent delegation |
| Q26 | `volatile` keyword | CPU cache visibility, memory fence |

---

## Q1. What is a class?

## Concrete Picture
You write `class Dog { }` once. The JVM reads it once and stores the blueprint in
metaspace. Every `new Dog()` after that creates a *separate* object on the heap using
that same blueprint. The class itself never lives on the heap.

## The Core Rule
A class is the blueprint stored in metaspace; objects are instances of it on the heap.

## Mechanism
When `javac` compiles `Dog.java` it produces `Dog.class` — a bytecode file describing
fields, methods, and the constant pool. On the first use of `Dog`, the ClassLoader
reads that file and stores the class metadata in **metaspace** (native memory, not
heap). Subsequent `new Dog()` calls allocate space on the heap using the metadata as
the template. The class definition is loaded exactly once per ClassLoader.

```
Source              Compile          Load                  Runtime
─────────           ────────         ────────              ───────
Dog.java  ─javac──► Dog.class ─CL──► metaspace ──new()──► heap object
```

## Traps
- **Trap:** "A class occupies heap memory." **Reality:** Class metadata goes in
  metaspace (native memory). Only object *instances* go on the heap.
- **Trap:** "Every `new Dog()` re-reads `Dog.class`." **Reality:** ClassLoader reads
  the file once; subsequent `new` calls reuse the cached metadata.

## Memory Trick
`class` = blueprint in metaspace. `new` = instance on heap.

## Self-Test
1. Where in JVM memory does a class definition live after loading?
2. If you create 1000 `Dog` objects, how many copies of the `bark()` bytecode exist?
3. What triggers the ClassLoader to load `Dog.class` the first time?

## Builds on
Nothing — this is the foundation.

## Connects to
Q2 (object creation), Q18 (static variables also live in metaspace)

---

## Q2. What is an object?

## Concrete Picture
`Dog d = new Dog("Rex")` does five things in sequence. After they complete, `d` on the
stack holds a 4-byte reference pointing to the Dog object on the heap. Null out `d` and
the object becomes eligible for garbage collection.

## The Core Rule
An object = heap memory + fields initialized by the constructor + a reference on the stack.

## Mechanism
`new Dog("Rex")` triggers this sequence in the JVM:
```
1. Check if Dog.class is loaded → load if not
2. Allocate space on heap (object header + fields)
3. Zero-initialize all fields (int→0, ref→null, bool→false)
4. Execute the constructor (your code runs here)
5. Return reference → stored in stack variable `d`
```

Object layout on heap:
```
heap
┌──────────────────────────────┐
│  Mark Word (8B)              │  ← hashCode, GC age, lock state
│  Klass Pointer (4-8B)        │  ← points to Dog metadata in metaspace
│  name: "Rex" (ref)           │  ← field
└──────────────────────────────┘
        ▲
        │ reference (4B on stack)
   d ───┘
```

Two objects can have identical field values but different heap addresses:
```java
Dog a = new Dog("Rex");
Dog b = new Dog("Rex");
a == b      // false — different heap addresses
a.equals(b) // true  — same field values (if equals() is overridden)
```

## Traps
- **Trap:** "`d = null` deletes the object." **Reality:** It removes the reference from
  the stack. The object persists until no more references point to it and GC collects it.
- **Trap:** "The constructor creates the object." **Reality:** The JVM allocates heap
  memory *before* the constructor runs. The constructor only initializes fields.

## Memory Trick
Stack holds the leash (reference). Heap holds the dog (object). Null = drop the leash.

## Self-Test
1. Trace the 5 steps of `new Dog("Rex")` in order.
2. After `Dog a = new Dog(); Dog b = a; a = null;` — is the object collected?
3. What is the object header and what does the mark word store?

## Builds on
Q1 (class loading must happen before object creation)

## Connects to
Q3 (identity vs equality), Q15 (constructor detail)

---

## Q3. `==` vs `.equals()` — and the `hashCode` Contract

## Concrete Picture
Two bank accounts with the same balance: `==` asks "are they the same account?" (same
safe in the vault). `.equals()` asks "do they have the same balance?" (same value).
Getting this wrong silently breaks `HashMap` and `HashSet`.

## The Core Rule
`==` compares heap addresses. `.equals()` compares logical content. **If you override
`equals()`, you MUST override `hashCode()`.**

## Mechanism

### `==` — reference equality
```java
String a = new String("hello");
String b = new String("hello");
a == b   // false — different heap addresses
```
Bytecode: `if_acmpeq` — compares the two references as raw pointers.

### `.equals()` — structural equality
```java
a.equals(b)  // true — same character sequence
```
`Object.equals()` defaults to `==`. Override it to define what "equal" means for your
class.

### The `hashCode` contract
HashMap works by: `bucket = hashCode() % capacity`. Then it walks the bucket checking
`equals()`.

```
put("Rex", dog):
  1. bucket = "Rex".hashCode() % 16  → bucket #7
  2. store in bucket #7

get("Rex"):
  1. bucket = "Rex".hashCode() % 16  → bucket #7
  2. walk bucket #7, find entry where key.equals("Rex")
```

**The contract:** If `a.equals(b)` is `true`, then `a.hashCode()` MUST equal
`b.hashCode()`. Violating this breaks HashMap silently.

## Wrong Code
```java
class Dog {
    String name;
    @Override
    public boolean equals(Object o) {
        return ((Dog) o).name.equals(this.name);
    }
    // hashCode NOT overridden ← silent bug
}

Dog a = new Dog("Rex");
Dog b = new Dog("Rex");
a.equals(b);              // true ✓
Set<Dog> set = new HashSet<>();
set.add(a);
set.contains(b);          // FALSE — different hashCodes → different buckets!
```

## Right Code
```java
@Override
public boolean equals(Object o) {
    if (this == o) return true;
    if (!(o instanceof Dog)) return false;
    return Objects.equals(name, ((Dog) o).name);
}

@Override
public int hashCode() {
    return Objects.hash(name); // same fields as equals()
}
```

## Bytecode
```
a == b        →  if_acmpeq   (reference comparison, no method call)
a.equals(b)   →  invokevirtual java/lang/Object.equals:(Ljava/lang/Object;)Z
```

## Traps
- **Trap:** "Overriding `equals()` is enough for HashSet to work." **Reality:** Without
  matching `hashCode()`, equal objects land in different buckets — `contains()` returns
  `false`.
- **Trap:** "`==` on `String` always returns `false`." **Reality:** String literals are
  interned — `"hello" == "hello"` is `true` (same pool reference). See Q22.

## Memory Trick
`==` = same house. `equals()` = same blueprint. hashCode = street address for the
mailman. Same house → same address. But address is only meaningful if it's consistent
with equals.

## Self-Test
1. What happens to a `HashMap` when you override `equals()` but not `hashCode()`?
2. What bytecode instruction does `==` on objects compile to?
3. Can two objects be `==` but not `.equals()`? Can two objects be `.equals()` but not `==`?

## Builds on
Q2 (objects have identity = heap address)

## Connects to
Q22 (String pool — strings with same content can be `==`)

---

## Q4. What is Encapsulation?

## Concrete Picture
A bank account with a public `balance` field: any code can do `account.balance = -9999`.
Encapsulation replaces the raw field with `private balance + public deposit()/withdraw()`
— now you can validate every change.

## The Core Rule
Private fields + public methods = you control access logic. Callers can't bypass your
validation.

## Mechanism
`private` fields are only accessible within the class. The compiler rejects any outside
access. Getters/setters are public methods that enforce invariants.

```java
public class BankAccount {
    private double balance;  // field hidden

    public void deposit(double amount) {
        if (amount <= 0) throw new IllegalArgumentException();
        balance += amount;
    }

    public double getBalance() { return balance; }
    // No setter — balance can only increase via deposit/withdraw
}
```

The bytecode benefit: `balance` becomes `private` → `ACC_PRIVATE` flag in the field
descriptor → compiler enforces at compile time, verifier enforces at load time.

## Traps
- **Trap:** "Encapsulation means making everything private." **Reality:** It means
  controlling access. Some fields should be public constants. Some classes have package
  visibility intentionally.
- **Trap:** "`public getBalance()` is as good as a public field." **Reality:** A getter
  gives you the option to add logic later (lazy loading, access logging, computed
  values) without changing the API.

## Memory Trick
Encapsulation = bouncer at the door. Raw field = no bouncer, anyone walks in.

## Self-Test
1. What happens at the bytecode level when you access a `private` field from outside the class?
2. How does encapsulation allow you to change internal representation without breaking callers?
3. Is it possible to break encapsulation in Java? (hint: reflection)

## Builds on
Q1 (class structure), Q5 (access modifiers)

## Connects to
Q5 (access modifier mechanics), Q17 (immutability via final + no setters)

---

## Q5. Access Modifiers — Complete Picture

## Concrete Picture
Four doors into a room. `private` = only you have the key. Package-private = everyone
on your floor. `protected` = your floor + your family abroad (subclasses). `public` =
anyone in the world.

## The Core Rule
Access modifiers control which code can *see* a member at compile time and are enforced
again by the bytecode verifier at load time.

## Mechanism

```
Modifier        Same Class   Same Package   Subclass (any pkg)   Everywhere
─────────────   ──────────   ────────────   ──────────────────   ─────────
private         ✓            ✗              ✗                    ✗
(none/pkg-priv) ✓            ✓              ✗                    ✗
protected       ✓            ✓              ✓                    ✗
public          ✓            ✓              ✓                    ✓
```

**Kotlin difference:** Kotlin has no package-private. `internal` (same **module**, not
same package) replaces it. Default in Kotlin is `public`.

```kotlin
// Kotlin
internal fun internalFun() {}  // visible within the same Gradle module
```

## Traps
- **Trap:** "`protected` means only subclasses can access it." **Reality:** `protected`
  = same package OR subclass in ANY package. A class in package `com.evil` that extends
  yours can access your `protected` members.
- **Trap:** "No modifier = private." **Reality:** No modifier = package-private — any
  class in the same package can access it.
- **Trap:** "Kotlin's `internal` = Java's package-private." **Reality:** `internal` is
  module-scoped, which is much larger than a package. A module = one Gradle build unit.

## Memory Trick
`private → package → protected → public` = tightest to widest.
Kotlin swaps "package" for "module" → `private → internal → protected → public`.

## Self-Test
1. Can a class in `package com.a` access a `protected` member of a class in `package com.b` if it extends it?
2. What is the default visibility in Java? In Kotlin?
3. What does `internal` mean in Kotlin, and how does it differ from package-private?

## Builds on
Q4 (encapsulation uses access modifiers to enforce it)

## Connects to
Q6 (inheritance respects access rules), Q12 (interface members are public by default)

---

## Q6. What is Inheritance?

## Concrete Picture
`class GoldenRetriever extends Dog` — the JVM sets up a parent-child vtable link. Every
`GoldenRetriever` object physically contains all `Dog` fields. Calling `goldie.bark()`
walks the vtable from `GoldenRetriever` up to `Dog` if `bark()` isn't overridden.

## The Core Rule
`extends` creates an IS-A relationship. The child class gets all non-private parent
members. The JVM builds a vtable that includes both parent and child methods.

## Mechanism
```
vtable for GoldenRetriever:
┌─────────────────────────────┐
│ Object.toString()           │ ← inherited from Object
│ Object.equals()             │
│ Dog.bark()                  │ ← inherited from Dog
│ Dog.eat()                   │
│ GoldenRetriever.fetch()     │ ← new in child
└─────────────────────────────┘
```

Object layout (child contains parent fields):
```
heap — GoldenRetriever object
┌────────────────────────────────┐
│ Object header (mark + klass)   │
│ Dog.name (String ref)          │ ← parent field
│ Dog.breed (String ref)         │ ← parent field
│ GoldenRetriever.color (String) │ ← child field
└────────────────────────────────┘
```

Java supports **single inheritance** for classes. The diamond problem is prevented:
only one parent class allowed. Multiple interfaces are allowed (see Q12).

## Wrong Code
```java
class Animal {
    private String name; // private — NOT inherited
    Animal(String name) { this.name = name; }
}

class Dog extends Animal {
    Dog() {
        // super() not called explicitly
        // Compiler inserts super() — but Animal has no no-arg constructor!
        // → COMPILE ERROR: no suitable constructor found
    }
}
```

## Right Code
```java
class Dog extends Animal {
    Dog(String name) {
        super(name); // explicit call — first statement
    }
}
```

## Traps
- **Trap:** "Private fields are inherited." **Reality:** The memory is there (child
  object contains parent fields), but the child code cannot *access* them. They're
  invisible, not absent.
- **Trap:** "Calling `super()` is optional." **Reality:** If the parent has no no-arg
  constructor, the compiler will reject the child constructor unless you explicitly call
  `super(args)`.

## Memory Trick
Inheritance = the child object *physically contains* the parent. vtable links methods.
`super()` must be first — parent initializes before child.

## Self-Test
1. Does a child object contain the parent's private fields in memory?
2. What vtable entry does `GoldenRetriever.bark()` resolve to if `bark()` is not overridden?
3. Why does Java forbid multiple class inheritance?

## Builds on
Q1 (class loading), Q2 (object layout)

## Connects to
Q7 (vtable enables polymorphism), Q11 (overriding rewrites vtable entries)

---

## Q7. What is Polymorphism?

## Concrete Picture
`Animal a = new Dog(); a.speak()` — the compiler sees `Animal.speak()` exists (type
check passes). At runtime, the JVM looks up `a`'s actual vtable, finds `Dog.speak()`,
and calls that. The reference type decides what's *legal*; the object type decides
what *runs*.

## The Core Rule
The **reference type** is checked at compile time. The **actual object type** decides
the method call at runtime via vtable lookup. This is `invokevirtual`.

## Mechanism
```
Compile time:
  Animal a = new Dog();
  a.speak();
  └── compiler checks: does Animal have speak()? ✓ (type check passes)

Runtime:
  a.speak()
  └── invokevirtual instruction:
      1. Load reference `a` from stack
      2. Follow klass pointer → Dog's vtable
      3. Lookup speak() in Dog's vtable → Dog.speak()
      4. Call it
```

This is why you CAN'T call `a.fetch()` even if the object is a `Dog`:
```java
Animal a = new Dog();
a.fetch(); // COMPILE ERROR — Animal reference has no fetch()
           // compiler only sees Animal's vtable
```

## Wrong Code (static method "override" trap)
```java
class Animal {
    static void describe() { System.out.println("Animal"); }
}
class Dog extends Animal {
    static void describe() { System.out.println("Dog"); } // HIDING, not overriding
}

Animal a = new Dog();
a.describe(); // prints "Animal" — NOT "Dog"!
// Static methods use invokestatic → resolved at compile time by reference type
```

## Right Code (instance method — actual polymorphism)
```java
class Animal { void speak() { System.out.println("..."); } }
class Dog extends Animal { @Override void speak() { System.out.println("Woof"); } }

Animal a = new Dog();
a.speak(); // prints "Woof" — invokevirtual → Dog's vtable
```

## Bytecode
```
a.speak()    →  invokevirtual  (runtime vtable lookup)
Animal.x()   →  invokestatic   (compile-time resolution, no vtable)
```

## Traps
- **Trap:** "Static methods can be overridden polymorphically." **Reality:** Static
  methods are resolved at compile time using the reference type. They're *hidden*, not
  *overridden*. No vtable lookup occurs.
- **Trap:** "The reference type determines which method runs." **Reality:** Reference
  type determines what's legal. The actual object type determines what runs.

## Memory Trick
`invokevirtual` = "look up the vtable at runtime." Reference type = which vtable to
*look at*. Object type = which *row* in that table to actually use.

## Self-Test
1. Trace what happens byte-by-byte when `invokevirtual` executes `a.speak()` where `a` is `Animal` reference to a `Dog`.
2. Why can't you call `a.fetch()` through an `Animal` reference even if the actual object is a `Dog`?
3. What bytecode instruction does a static method call compile to, and why does that prevent polymorphism?

## Builds on
Q6 (vtable is set up by inheritance)

## Connects to
Q8 (`instanceof` checks the actual object type), Q11 (overriding rewrites vtable entries)

---

## Q8. `instanceof` and Casting

## Concrete Picture
`instanceof` is the runtime type check — it asks "what is this object *actually*?" Safe
upcast is implicit (Dog IS-A Animal). Unsafe downcast requires `(Dog)` — if the object
isn't actually a Dog, you get `ClassCastException` at runtime, not compile time.

## The Core Rule
Upcasting (child → parent) is always safe, always implicit. Downcasting (parent → child)
requires explicit cast and throws `ClassCastException` if the actual object isn't that
type.

## Mechanism
```
Upcasting — implicit, always safe:
  Dog d = new Dog();
  Animal a = d;    // no cast needed — Dog IS-A Animal

Downcasting — explicit, can fail:
  Animal a = new Dog();
  Dog d = (Dog) a;   // OK at runtime — actual object IS a Dog
  Cat c = (Cat) a;   // ClassCastException — actual object is NOT a Cat
```

`instanceof` checks the actual object type at runtime:
```java
Animal a = new Dog();
a instanceof Dog    // true  — actual object is Dog
a instanceof Cat    // false
a instanceof Animal // true  — Dog IS-A Animal
```

Modern Java 16+ pattern matching:
```java
if (a instanceof Dog d) {  // checks AND casts in one step
    d.fetch();             // d is already cast, no separate cast needed
}
```

## Wrong Code
```java
Animal a = new Animal();
Dog d = (Dog) a;  // Compiles fine! But...
                  // ClassCastException at runtime: Animal cannot be cast to Dog
```

## Right Code
```java
if (a instanceof Dog) {
    Dog d = (Dog) a;  // safe — you verified type first
    d.fetch();
}
// Or (Java 16+):
if (a instanceof Dog d) { d.fetch(); }
```

## Traps
- **Trap:** "The compiler catches wrong downcasts." **Reality:** The compiler only
  rejects casts that are provably wrong (e.g., `String` → `Dog` — unrelated hierarchy).
  For related types, it trusts you and fails at runtime.
- **Trap:** "`instanceof` checks if the variable type matches." **Reality:** It checks
  the *actual object* on the heap, not the declared type of the variable.

## Memory Trick
Upcast = wider bucket — always fits. Downcast = narrower bucket — check first or it spills.

## Self-Test
1. `Animal a = new Dog(); Cat c = (Cat) a;` — compile error or runtime error? Why?
2. What is the JVM bytecode instruction for `instanceof`?
3. Why does upcasting not require an explicit cast?

## Builds on
Q6 (inheritance creates the type hierarchy), Q7 (actual object type determines behavior)

## Connects to
Q12 (interfaces use `instanceof` checks)

---

## Q9. What is Abstraction?

## Concrete Picture
You call `list.add("hello")` without caring whether it's an `ArrayList` or `LinkedList`
under the hood. The `List` interface is the abstraction — it defines the contract (what),
not the implementation (how). You can swap the backing class without changing your code.

## The Core Rule
Abstraction = exposing the "what" (interface/abstract class), hiding the "how" (implementation).

## Mechanism
Two tools:
1. **Abstract class** — partial implementation, some methods filled in
2. **Interface** — pure contract, all methods abstract (until Java 8 `default`)

```java
// Caller codes to abstraction
List<String> list = new ArrayList<>();  // reference type = List (abstraction)
list.add("hello");                       // doesn't know or care it's ArrayList

// Later, can swap:
List<String> list = new LinkedList<>(); // same calling code works
```

The abstraction layer creates a **stable API contract**. Internal implementation can
change without breaking callers.

## Traps
- **Trap:** "Abstraction = making things abstract." **Reality:** Abstraction is a design
  principle. It's about hiding complexity behind a clean interface. `private` methods are
  also abstraction — you hide how a class does something internally.

## Memory Trick
Abstraction = TV remote. You press "volume up" without knowing the circuit inside.

## Self-Test
1. What are the two Java language constructs used to achieve abstraction?
2. How does programming to an interface (`List` vs `ArrayList`) help with abstraction?

## Builds on
Q7 (polymorphism is how abstraction is implemented at runtime)

## Connects to
Q12 (interfaces), Q13 (abstract classes)

---

## Q10. What is Method Overloading?

## Concrete Picture
`System.out.println("hi")` and `System.out.println(42)` call different methods. The
*name* is the same; the *parameter types* differ. The compiler picks the right one at
compile time — no vtable, no runtime decision.

## The Core Rule
Overloading is resolved **at compile time** by the reference type and argument types.
It is NOT runtime polymorphism.

## Mechanism
The compiler builds the method signature: `methodName + parameterTypes`. Return type
alone is NOT part of the signature — you can't overload by return type only.

Resolution order when multiple overloads match:
```
1. Exact type match
2. Widening (int → long → float → double)
3. Autoboxing (int → Integer)
4. Varargs
```

```java
void print(int x)    {}
void print(long x)   {}
void print(double x) {}

print(5);    // resolves to print(int)  — exact match
print(5L);   // resolves to print(long) — exact match
print(5.0);  // resolves to print(double) — exact match
print('A');  // resolves to print(int) — widening (char→int)
```

## Wrong Code (return type overload attempt)
```java
int getValue()    { return 1; }
double getValue() { return 1.0; } // COMPILE ERROR — same signature
```

## Bytecode
```
// Compiler resolves at compile time → call site has exact target:
invokevirtual java/io/PrintStream.println:(I)V  // for print(int)
invokevirtual java/io/PrintStream.println:(D)V  // for print(double)
// Different descriptors — resolved statically, no runtime dispatch
```

## Traps
- **Trap:** "Overloading is runtime polymorphism." **Reality:** Overloading is
  compile-time. The compiler picks the method based on the *declared types* of the
  arguments at the call site. The actual object type doesn't matter.
- **Trap:** "Return type can differentiate overloads." **Reality:** Return type is NOT
  part of the method signature for overload resolution.

## Memory Trick
Overloading = compile-time. Overriding = runtime. "Load" vs "ride" — load is before
departure, ride is during the trip.

## Self-Test
1. `print(null)` where `print(String)` and `print(Object)` both exist — which is called? Why?
2. Can overloading and overriding coexist on the same method name?
3. What bytecode difference distinguishes a virtual call from an overloaded static call?

## Builds on
Q7 (contrast: overriding IS runtime polymorphism)

## Connects to
Q11 (overriding — the runtime counterpart)

---

## Q11. What is Method Overriding?

## Concrete Picture
`Dog` rewrites `Animal.speak()`. The compiler writes a new row in `Dog`'s vtable
pointing to `Dog.speak()`. Every time `invokevirtual` runs on a `Dog` object, it finds
`Dog.speak()` in that row, not `Animal.speak()`.

## The Core Rule
Overriding rewrites a **vtable entry** in the child class. The actual runtime type
determines which row is consulted. This is what makes polymorphism work.

## Mechanism
```
Animal vtable:           Dog vtable (after override):
┌─────────────┐          ┌────────────────────────┐
│ toString()  │          │ toString()  (inherited) │
│ equals()    │          │ equals()    (inherited) │
│ speak()  ───┼──────────► speak()  [Dog.speak()]  │ ← rewritten
└─────────────┘          └────────────────────────┘
```

Overriding rules:
- Same name, same parameter types, same or covariant return type
- Cannot override `static` (no vtable entry), `final` (vtable entry locked), `private`
  (not in vtable at all)
- `@Override` tells the compiler to verify the signature matches — use it always

```java
class Animal { void speak() {} }
class Dog extends Animal {
    @Override void speak() { System.out.println("Woof"); }
}
```

## Wrong Code
```java
class Animal { void speak() {} }
class Dog extends Animal {
    // Forgot @Override — typo in signature
    void Speak() {} // Different name! Not an override — new method added.
    // Animal.speak() is still the inherited one.
}
// @Override would have caught this: "method does not override"
```

## Traps
- **Trap:** "You can override `static` or `final` methods." **Reality:** `static` uses
  `invokestatic` (no vtable). `final` locks the vtable entry. Neither can be overridden.
- **Trap:** "`@Override` is just style." **Reality:** It instructs the compiler to verify
  the override. Without it, a typo silently creates a new method instead of overriding.

## Memory Trick
Override = new row in the child's vtable. `invokevirtual` reads that row at runtime.

## Self-Test
1. Why can't a `final` method be overridden? Trace the vtable mechanism.
2. What happens if you "override" a static method? What bytecode instruction is used?
3. What does `@Override` do at compile time vs runtime?

## Builds on
Q6 (vtable comes from inheritance), Q7 (override makes polymorphism work)

## Connects to
Q14 (abstract class requires subclass to override), Q17 (final prevents override)

---

## Q12. What is an Interface?

## Concrete Picture
`Runnable`, `Comparable`, `Clickable` — all describe *what* something can do, not
*what* it is. A `Dog` can implement `Runnable` AND `Serializable` — the diamond problem
doesn't apply because interfaces carry no state to conflict.

## The Core Rule
An interface is a pure contract: method signatures (and default/static implementations
since Java 8), no instance state. A class can implement many.

## Mechanism
Interface method flags in bytecode: `ACC_PUBLIC | ACC_ABSTRACT` (unless `default`).
No instance fields — only `public static final` constants.

```java
interface Clickable {
    void onClick();                     // implicitly public abstract
    int MAX_SIZE = 100;                 // implicitly public static final
    default void onLongClick() { }      // Java 8+: concrete, but no state
    static Clickable noop() { return () -> {}; } // Java 8+: factory
}
```

Why multiple interfaces are safe (no diamond problem):
```
class Dog implements Runnable, Comparable<Dog>
        │                │              │
   Dog fields        run() contract   compareTo() contract
        └── single set of fields, no ambiguity
```

If two interfaces have the same `default` method → compile error in implementing class
(must override to resolve).

## Traps
- **Trap:** "Interfaces can have state." **Reality:** Interface fields are implicitly
  `public static final` — they're class-level constants, not instance state.
- **Trap:** "Adding a method to an interface breaks all implementations." **Reality:**
  Java 8 `default` methods allow adding implementations without breaking existing code.
  But a non-default method addition still breaks all implementors.

## Memory Trick
Interface = contract. No body = no state. Multiple allowed because no memory conflict.

## Self-Test
1. What are the implicit modifiers on an interface field?
2. Two interfaces both declare `default void log()`. A class implements both. What happens?
3. Why can a class implement multiple interfaces but only extend one class?

## Builds on
Q9 (interfaces are a tool for abstraction)

## Connects to
Q13 (abstract class — when interface isn't enough), Q14 (decision table)

---

## Q13. What is an Abstract Class?

## Concrete Picture
`Shape` has a concrete `print()` method and an abstract `area()`. Subclasses provide
`area()`. The concrete method calls the abstract one — this is the Template Method
pattern. You can't instantiate `Shape` directly because the JVM can't call an unresolved
`area()`.

## The Core Rule
An abstract class is a partial implementation. It can have fields, constructors,
concrete methods, and abstract methods. Subclasses must implement all abstract methods.

## Mechanism
```java
abstract class Shape {
    String color;  // instance state — allowed
    Shape(String color) { this.color = color; }  // constructor — allowed

    abstract double area();  // no body — must be overridden

    void print() {           // concrete — inherited as-is
        System.out.println(color + ": " + area());
    }
}
```

Why you can't instantiate an abstract class:
```java
Shape s = new Shape("red"); // COMPILE ERROR
// JVM can't call s.area() — no implementation exists
```

The constructor exists because subclass constructors call `super(color)` — it's used
indirectly.

## Traps
- **Trap:** "Abstract classes can't have constructors." **Reality:** They have and need
  constructors — called via `super()` from subclass constructors.
- **Trap:** "Abstract class = interface." **Reality:** Abstract class can have instance
  state, constructors, access modifiers. Interface cannot have instance state.

## Memory Trick
Abstract class = partially assembled furniture. Has the frame (shared state/methods),
missing the drawer (abstract methods you must fill in).

## Self-Test
1. Can an abstract class have zero abstract methods? What would that mean?
2. Why does an abstract class need a constructor if you can't instantiate it?
3. Can an abstract class implement an interface and leave interface methods unimplemented?

## Builds on
Q6 (inheritance is how abstract classes are used)

## Connects to
Q14 (abstract class vs interface decision), Q11 (abstract methods must be overridden)

---

## Q14. Interface vs Abstract Class

## The Core Rule
Interface when: pure contract, multiple inheritance needed, no shared state.
Abstract class when: shared state or partial implementation needed.

## Comparison Table

| Dimension | Interface | Abstract Class |
|---|---|---|
| Instance fields | ✗ (only `public static final`) | ✓ (any visibility) |
| Constructor | ✗ | ✓ |
| Multiple | ✓ (implements many) | ✗ (extends one) |
| Method body | Only `default`/`static` | Both abstract and concrete |
| Access modifiers | Methods must be `public` | Any modifier |
| Use when | Defining a capability | Sharing partial implementation |

## Decision Rule
```
Does the base type need instance state?
    YES → Abstract class
    NO  → Does it need multiple inheritance?
              YES → Interface
              NO  → Either works; prefer interface for flexibility
```

## Common Android Patterns
```
Interface:  Clickable, Runnable, Lifecycle.Observer, Parcelable
Abstract:   AsyncTask (deprecated), RecyclerView.Adapter (has state)
```

## Traps
- **Trap:** "Use abstract class because it can do everything an interface can." **Reality:**
  You can only extend ONE abstract class. Choosing it closes off multiple inheritance.
  Prefer interface unless you specifically need shared state.

## Memory Trick
Interface = job description (what you can do). Abstract class = half-built blueprint (what you already have).

## Self-Test
1. A class needs to be both a `Drawable` and a `Clickable`. Should these be interfaces or abstract classes?
2. From Java 8 onward, what narrowed the gap between interfaces and abstract classes?
3. If an abstract class implements an interface but doesn't implement all its methods, what happens?

## Builds on
Q12, Q13

## Connects to
Q6 (inheritance applies to both)

---

## Q15. What is a Constructor?

## Concrete Picture
The five-step sequence of `new Dog("Rex")` ends with the constructor running. The
constructor doesn't *create* the object — the JVM does that first. The constructor
*initializes* it. This is why `this.field` assignments in the constructor find an
already-allocated object.

## The Core Rule
A constructor initializes a freshly allocated object. It runs after allocation and
zero-initialization, before the reference is returned to the caller.

## Mechanism
```
Full sequence of: Dog d = new Dog("Rex");

1. ClassLoader ensures Dog.class is loaded
2. JVM allocates heap space for Dog object
3. All fields zero-initialized (null, 0, false)
4. Superclass constructor runs (implicit super() or your super(args))
5. Your constructor body runs
6. Reference returned to caller → stored in d
```

Constructors are NOT inherited (a child doesn't get the parent's constructor). The
compiler injects `super()` (no-arg) as the first statement if you don't write it.

```java
class Animal {
    String name;
    Animal(String name) { this.name = name; }
    // No no-arg constructor → child MUST explicitly call super(name)
}

class Dog extends Animal {
    Dog(String name) {
        super(name); // MUST be first — parent initializes before child
    }
}
```

## Traps
- **Trap:** "Constructors are inherited." **Reality:** They are not. Child has no parent
  constructor — it must call `super()` explicitly or implicitly (when parent has no-arg).
- **Trap:** "The constructor creates the object." **Reality:** The JVM allocates and
  zero-initializes. The constructor runs afterward to set meaningful values.

## Memory Trick
Constructor = interior decorator. JVM builds the shell first, decorator sets it up inside.

## Self-Test
1. What is the first thing that happens before any constructor body runs?
2. What does the compiler insert if you don't write `super()` as the first line?
3. Can a constructor call an instance method? Is it safe? (Think: when is the object fully initialized?)

## Builds on
Q2 (object creation sequence), Q6 (super() calls parent constructor)

## Connects to
Q16 (constructor overloading), Q24 (this() for chaining)

---

## Q16. Constructor Overloading

## Concrete Picture
`new Dog()`, `new Dog("Rex")`, `new Dog("Rex", 3)` — three ways to create a `Dog`.
Instead of duplicating initialization logic, chain them: each shorter constructor calls
the next one via `this(...)`.

## The Core Rule
Multiple constructors differ by parameter list. Chain with `this(...)` — must be the
first statement — to avoid duplicated initialization logic.

## Mechanism
```java
class Dog {
    String name;
    int age;

    Dog() {
        this("Unknown"); // chains to Dog(String)
    }

    Dog(String name) {
        this(name, 0);   // chains to Dog(String, int)
    }

    Dog(String name, int age) {
        this.name = name; // canonical constructor — all logic here
        this.age = age;
    }
}
```

```
new Dog()
    └── this("Unknown")
            └── this("Unknown", 0)
                    └── actual initialization
```

## Wrong Code
```java
Dog(String name) {
    this.name = name;
    this(name, 0);  // COMPILE ERROR — this() must be FIRST statement
}
```

## Traps
- **Trap:** "You can call `this(...)` anywhere in the constructor." **Reality:** It must
  be the very first statement. The constructor chain must form a DAG that eventually
  calls one "canonical" constructor.
- **Trap:** "Constructor chaining is better replaced by default parameters." **Reality:**
  In Java, yes — chaining is the idiom. In Kotlin, default parameters are cleaner and
  replace most secondary constructors.

## Memory Trick
`this(...)` = "delegate to my sibling constructor." Must go first or the compiler complains.

## Self-Test
1. Can `this(...)` and `super(...)` both be used in the same constructor?
2. What Kotlin feature largely eliminates the need for multiple constructors?
3. What is the risk of calling an instance (overridable) method from a constructor?

## Builds on
Q15 (constructor mechanics)

## Connects to
Q24 (this keyword)

---

## Q17. Static Methods

## Concrete Picture
`Math.sqrt(4)` — no `Math` object needed. The method lives in class metadata, not in
any object. The compiler resolves the call completely at compile time using
`invokestatic`. No vtable, no runtime lookup.

## The Core Rule
Static methods belong to the class, resolved at compile time with `invokestatic`.
They cannot be overridden — only hidden.

## Mechanism
```
invokestatic   → target is fixed at compile time, no vtable lookup
invokevirtual  → target is resolved at runtime via vtable
```

```java
class Animal {
    static void describe() { System.out.println("Animal"); }
    void speak()           { System.out.println("...");    }
}
class Dog extends Animal {
    static void describe() { System.out.println("Dog"); } // HIDING
    @Override void speak() { System.out.println("Woof"); } // OVERRIDING
}

Animal a = new Dog();
a.describe(); // "Animal" — invokestatic, compile-time, reference type wins
a.speak();    // "Woof"   — invokevirtual, runtime, actual type wins
```

## Bytecode
```
a.speak()    →  invokevirtual Animal.speak:()V   (vtable lookup at runtime)
a.describe() →  invokestatic  Animal.describe:()V (fixed at compile time)
```

## Traps
- **Trap:** "Static methods can be overridden by subclasses." **Reality:** They can be
  *hidden* — a subclass can declare a method with the same name, but calling through a
  parent reference always calls the parent's version.
- **Trap:** "Calling a static method through an object instance is fine." **Reality:**
  It works syntactically but is misleading — `dog.describe()` calls `Animal.describe()`.
  Always call static methods on the class name.

## Memory Trick
`invokestatic` = post office address is written on the envelope at send time. No
post office decides the route later.

## Self-Test
1. Trace the bytecode difference between calling `a.speak()` (instance) vs `a.describe()` (static) on a `Dog` through an `Animal` reference.
2. Why can't a static method reference `this`?
3. In Kotlin, what replaces Java's static methods? What bytecode does it produce?

## Builds on
Q7 (polymorphism uses invokevirtual; static doesn't)

## Connects to
Q18 (static variable — same class-level scope), Q11 (final also prevents override)

---

## Q18. Static Variables

## Concrete Picture
`static int instanceCount` — one counter for all `Dog` objects combined. Every `Dog`
constructor increments the same variable. It lives in metaspace, not in any object.
Zeroed when the class is first loaded.

## The Core Rule
One copy per class, shared by all instances. Lives in metaspace. Initialized when the
class is loaded. Not thread-safe by default.

## Mechanism
```
class Dog {
    static int count = 0;
    Dog() { count++; }
}

new Dog(); new Dog(); new Dog();

metaspace — Dog class data:
┌───────────────────┐
│ count = 3         │  ← one field, shared by all Dog objects
└───────────────────┘

heap — individual Dog objects:
[Dog@1] [Dog@2] [Dog@3]  ← no count field in any of them
```

Thread safety: `count++` is NOT atomic (read + increment + write = 3 operations). Two
threads incrementing simultaneously can produce a lost update.

```java
// Thread-safe alternatives:
static AtomicInteger count = new AtomicInteger(0);
count.incrementAndGet(); // CAS — atomic compare-and-swap

// Or:
synchronized static void increment() { count++; }
```

## Traps
- **Trap:** "Static variables are initialized when the object is created." **Reality:**
  They're initialized when the class is *loaded* — before any object exists.
- **Trap:** "`static int count = 0` is thread-safe because it's a primitive." **Reality:**
  `count++` is three JVM instructions. Threads can interleave between them.

## Memory Trick
Static = class's own pocket, not any object's pocket. Only one pocket regardless of
how many objects exist.

## Self-Test
1. Where in JVM memory does a static variable live?
2. What is the exact sequence of JVM instructions in `count++`, and where can a thread interleave to cause a race?
3. How does `AtomicInteger` avoid the race condition?

## Builds on
Q1 (metaspace = class metadata storage)

## Connects to
Q19 (autoboxing: static AtomicInteger involves boxing), Q26 (volatile for single-writer visibility)

---

## Q19. Autoboxing and Unboxing

## Concrete Picture
Java generics only work with objects: `List<int>` is illegal. So `List<Integer>` wraps
primitive `int` in an `Integer` object. The compiler auto-inserts `Integer.valueOf(5)`
when you write `list.add(5)`. This is invisible — until it causes a `NullPointerException`
or unexpected GC pressure.

## The Core Rule
Autoboxing = compiler auto-wraps primitive → wrapper (`int` → `Integer`).
Unboxing = compiler auto-unwraps wrapper → primitive (`Integer` → `int`).
Both can fail silently: unboxing `null` throws `NullPointerException`.

## Mechanism
```java
int x = 5;
Integer y = x;         // autoboxing — compiler inserts: Integer.valueOf(5)
int z = y;             // unboxing  — compiler inserts: y.intValue()

List<Integer> list = new ArrayList<>();
list.add(42);          // autoboxing: Integer.valueOf(42)
int val = list.get(0); // unboxing: list.get(0).intValue()
```

## Wrong Code — Null Unboxing
```java
Map<String, Integer> scores = new HashMap<>();
int score = scores.get("Alice"); // NullPointerException!
// scores.get("Alice") returns null (Integer)
// null.intValue() → NPE at unboxing
```

## Wrong Code — Performance
```java
Long sum = 0L;
for (long i = 0; i < 1_000_000; i++) {
    sum += i; // autoboxing on EVERY iteration: Long.valueOf(sum + i)
              // creates 1 million Long objects → GC pressure
}
```

## Right Code
```java
long sum = 0L; // primitive — no boxing
for (long i = 0; i < 1_000_000; i++) {
    sum += i;
}
```

## Integer Cache Trap
```java
Integer a = 127;
Integer b = 127;
a == b; // true — Integer.valueOf() caches -128..127, same object returned

Integer c = 128;
Integer d = 128;
c == d; // false — outside cache range, new objects
```

## Bytecode
```
int → Integer:  invokestatic java/lang/Integer.valueOf:(I)Ljava/lang/Integer;
Integer → int:  invokevirtual java/lang/Integer.intValue:()I
```

## Traps
- **Trap:** "Autoboxing is free." **Reality:** Each box = a heap object + GC cost.
  In hot loops (RecyclerView, animations), prefer primitive arrays.
- **Trap:** "`Integer a = 127; Integer b = 127; a == b` is always false." **Reality:**
  `Integer` caches -128..127. `==` returns `true` in that range.

## Memory Trick
Autobox = courier wraps your letter (int) in an envelope (Integer). Unbox = opening
the envelope. Unboxing null = opening an envelope that was never sent → NPE.

## Self-Test
1. `Integer a = 200; Integer b = 200; System.out.println(a == b);` — what prints and why?
2. Why does unboxing a null `Integer` to `int` throw NPE?
3. In Android, what collection class avoids boxing for `int` keys?

## Builds on
Q18 (static variables are primitives; understanding boxing matters for performance)

## Connects to
Q20 (final can be applied to boxed types)

---

## Q20. The `final` Keyword

## Concrete Picture
`final Dog d = new Dog("Rex")` — the leash is padlocked to `d`. You can't attach it
to a different dog. But the dog itself can still learn new tricks: `d.name = "Max"` is
perfectly legal.

## The Core Rule
`final` locks the **reference** (or variable), not the **object**. On methods: prevents
vtable entry from being overridden. On classes: prevents subclassing entirely.

## Mechanism

Three uses, one principle — "cannot be changed after initial binding":

```
VARIABLE:  final int x = 5;        x can never be reassigned
           final Dog d = new Dog(); d cannot point to another Dog
                                    but d.name = "Max" is fine

METHOD:    final void doWork()      vtable entry is locked — no subclass override
                                    JIT can inline this call (no vtable lookup needed)

CLASS:     final class String       no subclass can exist
                                    all String methods are final → JIT optimizes freely
```

Bytecode: `ACC_FINAL` flag on the field/method/class descriptor.

## Wrong Assumption
```java
final Dog d = new Dog("Rex");
d.name = "Max";    // ✓ ALLOWED — the object's field changed
d = new Dog("Max");// ✗ COMPILE ERROR — reference reassignment blocked
```

## Traps
- **Trap:** "A `final` object can't be mutated." **Reality:** `final` on a reference
  prevents reassigning the reference. The object's own fields can still be mutated unless
  they are also `final`.
- **Trap:** "`final` methods are slower because they can't be overridden." **Reality:**
  The opposite — `final` methods allow the JIT to **devirtualize** the call (inline it
  instead of vtable lookup) → often faster.

## Memory Trick
`final` = padlock on the leash, not the dog. You can walk the dog (mutate it). You
can't hand the leash to a different dog (reassign).

## Self-Test
1. Can a `final` field be null? Can it be reassigned to null after initialization?
2. How does `final` on a method improve JIT performance?
3. Why is `String` a `final` class? What guarantee does that provide?

## Builds on
Q7 (final prevents vtable override), Q2 (object vs reference distinction)

## Connects to
Q21 (immutability requires final fields + no setters)

---

## Q21. Immutability

## Concrete Picture
`String s = "hello"; s.toUpperCase()` — the original string is untouched. A new string
is created. This is safe to share between 1000 threads without a single lock.

## The Core Rule
Immutable = object state cannot change after construction. Requires: `final` class +
`final` fields + no setters + defensive copy of mutable inputs.

## Mechanism
Why immutability = thread safety: thread safety problems require *shared mutable state*.
If state can't mutate, no two threads can race on a write. After construction, the JVM's
memory model guarantees all threads see the fully initialized `final` fields — the
constructor's writes are "visible to all threads after the constructor completes."

```java
public final class Money {
    private final int amount;
    private final String currency;

    public Money(int amount, String currency) {
        this.amount = amount;
        this.currency = currency;
    }

    public Money add(Money other) {
        // Returns a NEW object — never modifies this
        return new Money(this.amount + other.amount, this.currency);
    }
    // No setters
}
```

Immutability checklist:
```
✓  final class      (no subclass can break immutability)
✓  final fields     (no reassignment)
✓  no setters       (no external mutation)
✓  defensive copy   (constructor copies mutable inputs like Date, arrays)
✓  return copies    (methods that expose mutable fields return copies)
```

## Traps
- **Trap:** "`final` fields = immutable object." **Reality:** `final` prevents field
  reassignment but the *object* the field points to can still be mutable. A `final
  List<String>` can have items added to it.
- **Trap:** "Immutability is expensive because you always create new objects." **Reality:**
  It's a tradeoff. For small, frequently used values (String, Integer), the JVM uses a
  pool (String) or cache (Integer -128..127) to avoid excess allocation.

## Memory Trick
Immutable = set in stone at construction. Thread-safe by design — no lock needed when
nothing can change.

## Self-Test
1. Why does the JVM's memory model make `final` fields safe to share between threads without `synchronized`?
2. `final List<String> names` — is this immutable? What would make it truly immutable?
3. What design pattern naturally produces immutable objects?

## Builds on
Q20 (final is the tool), Q18 (static + final = constant)

## Connects to
Q22 (String is immutable; String pool uses that property)

---

## Q22. String Pool and `StringBuilder`

## Concrete Picture
`"hello"` in source code is a string literal. The JVM stores it in the string pool once.
`"hello" == "hello"` is `true` — same pool address. But `+` in a loop creates a new
`String` object on each iteration, filling the heap with garbage.

## The Core Rule
String literals are interned in the string pool (heap, since Java 7). `new String()`
bypasses the pool. String `+` in a loop is O(n²) — use `StringBuilder`.

## Mechanism

### String pool
```java
String a = "hello";           // literal → stored in pool
String b = "hello";           // same literal → same pool reference
a == b                        // true ← same object

String c = new String("hello"); // explicitly NOT from pool
a == c                          // false ← different object
a.equals(c)                     // true ← same content

String d = c.intern();          // manually add to pool (or return existing)
a == d                          // true ← now from pool
```

### String concatenation trap
```java
String result = "";
for (int i = 0; i < 1000; i++) {
    result += i; // Each iteration: new String(result + i) → O(n²) allocations
}
```

Bytecode for `result += i` compiles to: `new StringBuilder(result).append(i).toString()`
— creates a new StringBuilder AND a new String on every iteration.

```java
// Right:
StringBuilder sb = new StringBuilder();
for (int i = 0; i < 1000; i++) {
    sb.append(i); // amortized O(1) — internal char array, doubles capacity when full
}
String result = sb.toString(); // one final String created
```

### StringBuilder vs StringBuffer
```
StringBuilder   — not thread-safe, use in single-threaded (most cases)
StringBuffer    — thread-safe (synchronized methods), slower, rarely needed
```

## Traps
- **Trap:** "`String a = "hello"; String b = "hello"; a == b` is `false`." **Reality:**
  String literals are interned — `a == b` is `true`. `new String("hello") == new
  String("hello")` is `false`.
- **Trap:** "`+` on strings is always O(n)." **Reality:** `a + b + c` in a single
  statement is optimized by the compiler to one `StringBuilder` chain. The problem is
  `+` inside a loop across iterations.

## Memory Trick
Pool = one copy per unique literal. `+` in loop = fresh envelope every time. `StringBuilder` = keep adding to same envelope.

## Self-Test
1. `String a = "cat"; String b = "c" + "at";` — is `a == b` true? Why?
2. Explain why `result += s` inside a loop is O(n²) at the bytecode level.
3. When would you use `StringBuffer` over `StringBuilder`?

## Builds on
Q21 (String is immutable — that's why pooling is safe)

## Connects to
Q3 (== on Strings trips people up because of the pool)

---

## Q23. Checked vs Unchecked Exceptions

## Concrete Picture
`FileNotFoundException` = checked. The compiler forces you to handle it. `NullPointerException`
= unchecked. It can happen anywhere; forcing a `try-catch` everywhere would be noise.
Kotlin removes this distinction entirely — all exceptions are unchecked at the language
level.

## The Core Rule
Checked extends `Exception` (not `RuntimeException`) — compiler enforces `try-catch`
or `throws`. Unchecked extends `RuntimeException` — optional handling.

## Mechanism

Exception hierarchy:
```
Throwable
├── Error           (JVM internal: OutOfMemoryError, StackOverflowError)
│                    → unchecked, never catch these in production logic
└── Exception
    ├── RuntimeException  → UNCHECKED (NullPointerException, ArrayIndexOutOfBounds...)
    └── (everything else) → CHECKED (IOException, SQLException...)
```

How the compiler tracks checked exceptions — the `throws` table in bytecode:
```java
// Declaring: puts IOException in this method's throws table
void readFile() throws IOException { ... }

// Calling: compiler checks: does this method throw a checked exception?
//          if yes, you must catch or declare
try { readFile(); } catch (IOException e) { ... }
// OR:
void myMethod() throws IOException { readFile(); } // propagate up
```

Kotlin: NO checked exceptions. All `@Throws` annotations are for Java interop only.
```kotlin
// Kotlin — no compiler error without try-catch:
fun readFile() { File("x").readText() } // IOException is unchecked here
```

## Wrong Code
```java
// Silently swallowing a checked exception — worst practice
try {
    readFile();
} catch (IOException e) {
    // empty catch — exception disappears with no trace
}
```

## Right Code
```java
catch (IOException e) {
    log.error("Failed to read file", e); // at minimum, log it
    throw new RuntimeException("File read failed", e); // or rethrow
}
```

## Traps
- **Trap:** "Kotlin's `@Throws` annotation makes Kotlin exceptions checked." **Reality:**
  It only affects Java callers — tells the Java compiler to expect that checked
  exception. Within Kotlin, exceptions are still unchecked.
- **Trap:** "`Error` subclasses should be caught in production code." **Reality:**
  `Error` means the JVM is in a broken state (OOM, stack overflow). Catching and
  recovering is almost always wrong.

## Memory Trick
Checked = compiler is your safety net. Unchecked = programmer is responsible.
Kotlin trusts you entirely (no checked exceptions).

## Self-Test
1. Where in bytecode does the `throws IOException` declaration appear?
2. Why did Kotlin remove checked exceptions? What tradeoff does that make?
3. What is the difference between catching `Exception` and catching `Throwable`?

## Builds on
Q9 (abstraction — exception handling is about separating error concerns)

## Connects to
Nothing specific — standalone topic.

---

## Q24. The `this` Keyword

## Concrete Picture
Inside `Dog.setName(String name)`, both `name` (parameter) and `name` (field) exist.
`this.name` explicitly refers to the field — the instance calling the method. Without
`this`, Java uses the parameter (closer scope wins).

## The Core Rule
`this` = reference to the current instance. Disambiguates fields from parameters.
`this(...)` in a constructor delegates to another constructor — must be first.

## Mechanism
```java
class Dog {
    String name;

    void setName(String name) {
        this.name = name; // this.name = field; name = parameter
    }

    Dog() { this("Unknown"); }   // delegates to Dog(String) — must be first
    Dog(String name) { this.name = name; }
}
```

`this` is not available in static methods — static methods have no instance, so there
is no "current object" to reference.

## Traps
- **Trap:** "`this` is the object." **Reality:** `this` is a reference to the object —
  another stack variable pointing to the same heap address.
- **Trap:** "You can use `this(...)` anywhere in the constructor." **Reality:** It must
  be the first statement. The compiler enforces this to ensure delegation is explicit.

## Memory Trick
`this` = mirror inside the class showing you yourself. Static methods have no mirror.

## Self-Test
1. Why is `this` not available in a static method?
2. Can you pass `this` to another method from a constructor? What risk does that create?
3. In Kotlin, how do you refer to the outer class `this` from an inner class?

## Builds on
Q2 (this IS the object reference), Q15 (constructors use this for chaining)

## Connects to
Q25 (super — the parent's this)

---

## Q25. The `super` Keyword

## Concrete Picture
`Dog.speak()` calls `super.speak()` — forces the vtable lookup to use `Animal`'s row
instead of `Dog`'s. `super()` in a constructor — forces execution of the parent
constructor before any child code runs.

## The Core Rule
`super` = reference to the parent class's implementation. `super()` calls the parent
constructor and must be the first statement.

## Mechanism
```java
class Animal {
    String name;
    Animal(String name) { this.name = name; }
    void speak() { System.out.println(name + " speaks"); }
}

class Dog extends Animal {
    String breed;

    Dog(String name, String breed) {
        super(name);    // FIRST — parent initializes this.name
        this.breed = breed; // then child initializes this.breed
    }

    @Override
    void speak() {
        super.speak();                 // calls Animal.speak()
        System.out.println("Woof!");   // then adds Dog behavior
    }
}
```

Initialization order:
```
new Dog("Rex", "Lab")
  └── super("Rex")          [Animal constructor runs first]
      └── this.name = "Rex"
  └── this.breed = "Lab"    [Dog constructor runs second]
```

## Traps
- **Trap:** "The compiler inserts `super()` automatically." **Reality:** Only if the parent
  has a no-arg constructor. If the parent requires arguments, the compiler rejects the
  child constructor until you add an explicit `super(args)`.
- **Trap:** "`super.method()` bypasses the entire vtable." **Reality:** `super.method()`
  calls the parent class's implementation using `invokespecial` bytecode — it targets the
  named class, bypassing virtual dispatch.

## Bytecode
```
super.speak()   →  invokespecial Animal.speak:()V  (exact target, no vtable)
this.speak()    →  invokevirtual Dog.speak:()V     (vtable lookup)
```

## Memory Trick
`super` = parent version. `this` = my version. `super()` in constructor = "let my parent
set up their part first."

## Self-Test
1. What bytecode instruction does `super.speak()` compile to, and why is it different from `this.speak()`?
2. What happens if you don't call `super()` first in a child constructor?
3. Can `super()` and `this()` both appear in the same constructor?

## Builds on
Q6 (inheritance establishes the parent-child relationship), Q15 (constructors)

## Connects to
Q11 (overriding uses super to delegate to parent implementation)

---

## Q26. `volatile` Keyword

## Concrete Picture
Thread A writes `flag = true`. Thread B is in a loop checking `flag`. Without `volatile`,
Thread B may never see the update — its CPU is reading a cached copy from its L1 cache,
not main memory. `volatile` forces the write to main memory and the read to bypass cache.

## The Core Rule
`volatile` guarantees **visibility** across threads. It does NOT guarantee **atomicity**.
`flag = true` is safe with volatile. `count++` is NOT safe even with volatile.

## Mechanism
Modern CPUs have per-core caches:
```
CPU Core 0              CPU Core 1
L1 Cache                L1 Cache
flag = false            flag = false (stale copy!)
   │                        │
   └──── Main Memory ───────┘
         flag = true   ← Thread A wrote here
```

Without `volatile`: Core 1 keeps reading its cached `false`. Thread B loops forever.

With `volatile`:
```
flag is marked volatile → ACC_VOLATILE in bytecode
writes:  LOCK XCHG (x86) — flush to main memory immediately
reads:   bypass L1/L2 cache — read from main memory
```

```java
class StopFlag {
    private volatile boolean stop = false;  // must be volatile

    void stop() { stop = true; }           // Thread A calls this
    void run()  { while (!stop) { ... } }  // Thread B calls this
}
```

## Wrong Code (non-volatile, always-loop bug)
```java
private boolean stop = false; // no volatile
// Thread B may loop forever — sees stale cached 'false' from L1 cache
```

## Wrong Code (volatile ≠ atomic)
```java
private volatile int count = 0;
count++; // STILL a race condition!
// count++ = read count + increment + write count (3 instructions)
// Two threads can interleave between read and write
// volatile only guarantees the FINAL write is visible, not that it's atomic
```

## Traps
- **Trap:** "`volatile` makes the variable thread-safe." **Reality:** It guarantees
  visibility. For compound operations (increment, compare-then-set), use `AtomicInteger`
  or `synchronized`.
- **Trap:** "`volatile` is needed on every shared variable." **Reality:** Only needed
  when one thread writes and others read, and you need visibility without full
  synchronization. If multiple threads write, `volatile` alone isn't enough.

## Memory Trick
`volatile` = skip the CPU cache, go straight to main memory. Read fresh. Write immediately.
But one operation at a time — not atomic for multi-step operations.

## Self-Test
1. Why is `volatile boolean stop` sufficient for a stop flag, but `volatile int count` with `count++` is not thread-safe?
2. What hardware mechanism enforces `volatile` reads/writes on x86?
3. How does Kotlin's `@Volatile` annotation differ from Java's `volatile` at the bytecode level?

## Builds on
Q18 (static variables — shared state between threads is the problem domain)

## Connects to
File 03 — Q46-Q52 (full concurrency: synchronized, AtomicInteger, locks)

---

```
╔══════════════════════════════════════════════════════════════════╗
║         Section 1 — One-Minute Recall Summary                   ║
╠══════════════════════════════════════════════════════════════════╣
║ Class vs Object      class → metaspace. new → heap object       ║
║ == vs equals()       == heap addr. equals() logic. hashCode!    ║
║ Polymorphism         invokevirtual → vtable → actual type       ║
║ Static               invokestatic → compile-time, no vtable     ║
║ final                locks reference (not object), devirtualize ║
║ Immutability         final + no setters = thread-safe free      ║
║ String pool          literals interned, + loop = O(n²) allocs   ║
║ Checked exceptions   compiler enforces. Kotlin: all unchecked   ║
║ volatile             visibility only. count++ still a race      ║
╚══════════════════════════════════════════════════════════════════╝
```

← [Index](00_index.md) | [02 JVM Architecture →](02_jvm_architecture_memory.md)
