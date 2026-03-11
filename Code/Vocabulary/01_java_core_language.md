# Section 1 — Java Core Language (Q1–Q19)

---

### Q1. What is a class?
**Definition:** A blueprint/template that defines fields (state) and methods (behavior).
**Core Idea:** Classes are templates; objects are instances of those templates.
**How it Works:** The JVM loads the class definition. You use `new` to create instances.
**Example:** `class Dog { String name; void bark() {} }`
**Interview Insight:** Classes don't occupy heap memory themselves — only objects do.

---

### Q2. What is an object?
**Definition:** A runtime instance of a class, allocated on the heap.
**Core Idea:** An object = state (fields) + behavior (methods) + identity (reference).
**How it Works:** `new Dog()` allocates memory on the heap and calls the constructor.
**Example:** `Dog d = new Dog();` — `d` is a reference on the stack pointing to the object on the heap.
**Interview Insight:** Two objects can have the same state but different identity (`==` vs `.equals()`).

---

### Q3. What is encapsulation?
**Definition:** Bundling data and methods together, hiding internal state via access modifiers.
**Core Idea:** Private fields + public getters/setters. Control HOW data is accessed.
**How it Works:** Mark fields `private`, expose them through `public` methods with validation logic.
**Example:** `private int age; public void setAge(int a) { if (a > 0) age = a; }`
**Interview Insight:** Encapsulation enables you to change internal implementation without breaking callers.

---

### Q4. What is inheritance?
**Definition:** A class (child) acquires fields and methods of another class (parent) using `extends`.
**Core Idea:** "IS-A" relationship. Promotes code reuse.
**How it Works:** Child class inherits all non-private members of the parent. Java supports single inheritance only.
**Example:** `class GoldenRetriever extends Dog { void fetch() {} }`
**Interview Insight:** Java uses single inheritance for classes but multiple inheritance via interfaces. `super` calls the parent constructor/method.

---

### Q5. What is polymorphism?
**Definition:** One interface, many implementations. The same method call behaves differently based on the actual object.
**Core Idea:** Runtime polymorphism (method overriding) = the JVM decides which method to call at runtime.
**How it Works:** Parent reference pointing to child object: `Animal a = new Dog(); a.speak();` calls `Dog.speak()`.
**Example:** `Animal[] animals = {new Dog(), new Cat()}; for (Animal a : animals) a.speak();`
**Interview Insight:** Enabled by dynamic dispatch. The JVM checks the actual object type at runtime, not the reference type.

---

### Q6. What is abstraction?
**Definition:** Hiding implementation details and exposing only what is necessary.
**Core Idea:** "WHAT it does" vs "HOW it does it." Focus on the interface, not the implementation.
**How it Works:** Achieved via abstract classes (`abstract class`) or interfaces. Callers use the abstraction, not the concrete class.
**Example:** `List<String> list = new ArrayList<>();` — you code to the `List` abstraction.
**Interview Insight:** Abstraction reduces coupling. You can swap `ArrayList` for `LinkedList` without changing the calling code.

---

### Q7. What is method overloading?
**Definition:** Multiple methods with the same name but different parameter lists in the same class.
**Core Idea:** Compile-time (static) polymorphism — the compiler picks the method based on arguments.
**How it Works:** Methods must differ in parameter count, type, or order. Return type alone is NOT enough.
**Example:** `int add(int a, int b)` and `double add(double a, double b)` in the same class.
**Interview Insight:** Overloading is resolved at compile time. It is NOT polymorphism in the runtime sense.

---

### Q8. What is method overriding?
**Definition:** A subclass provides a different implementation for a method already defined in its parent.
**Core Idea:** Runtime (dynamic) polymorphism — the actual object type determines which method runs.
**How it Works:** Use `@Override` annotation. Method signature must match exactly. Cannot override `static`, `final`, or `private` methods.
**Example:** `class Cat extends Animal { @Override void speak() { System.out.println("Meow"); } }`
**Interview Insight:** `@Override` is optional but catches signature mismatches at compile time — always use it.

---

### Q9. What is an interface?
**Definition:** A contract that defines method signatures (and default/static methods since Java 8) without implementation state.
**Core Idea:** Classes that `implement` an interface agree to provide the defined behavior. Supports multiple implementation.
**How it Works:** All methods are implicitly `public abstract` (unless `default`/`static`). No instance fields (only `public static final` constants).
**Example:** `interface Clickable { void onClick(); }` → `class Button implements Clickable { public void onClick() {...} }`
**Interview Insight:** An interface is a pure contract. A class can implement multiple interfaces — this is Java's answer to multiple inheritance.

---

### Q10. What is an abstract class?
**Definition:** A class that cannot be instantiated and may have both abstract methods (no body) and concrete methods (with body).
**Core Idea:** A partial implementation. Subclasses must implement abstract methods.
**How it Works:** Declared with `abstract` keyword. Can have constructors, fields, and any access modifiers.
**Example:** `abstract class Shape { abstract double area(); void print() { System.out.println(area()); } }`
**Interview Insight:** Use abstract class when subclasses share common state or partial implementation. Use interface when you just need a contract.

---

### Q11. Difference between interface and abstract class?

| | Interface | Abstract Class |
|---|---|---|
| State | No instance fields | Can have fields |
| Constructor | No | Yes |
| Multiple | A class implements many | A class extends one |
| Access modifiers | Methods are `public` | Any modifier |
| Use when | Pure contract | Shared partial implementation |

**Interview Insight:** Since Java 8, interfaces can have `default` methods, narrowing the gap. But abstract classes still win when you need shared state.

---

### Q12. What is a constructor?
**Definition:** A special method called when an object is created. It initializes the object's state.
**Core Idea:** Same name as the class, no return type. Called automatically with `new`.
**How it Works:** If you don't define one, Java provides a no-arg default constructor. It can call `super()` to initialize the parent.
**Example:** `class Dog { String name; Dog(String name) { this.name = name; } }`
**Interview Insight:** Constructors are NOT inherited. The first line must be `this(...)` or `super(...)` if used; compiler inserts `super()` otherwise.

---

### Q13. What is constructor overloading?
**Definition:** Multiple constructors in the same class with different parameter lists.
**Core Idea:** Allows creating objects in different ways.
**How it Works:** Use `this(...)` to chain constructors and avoid duplication.
**Example:** `Dog() { this("Unknown"); }` and `Dog(String name) { this.name = name; }`
**Interview Insight:** Constructor chaining with `this(...)` should be the first statement. Reduces duplicate initialization code.

---

### Q14. What is a static method?
**Definition:** A method that belongs to the class, not to any instance. Called via the class name.
**Core Idea:** No `this` reference. Cannot access instance fields or instance methods directly.
**How it Works:** Loaded when the class is loaded. Lives in the method area.
**Example:** `Math.sqrt(4)` — no `Math` object needed.
**Interview Insight:** Static methods cannot be overridden (they can be hidden). They are resolved at compile time, not runtime.

---

### Q15. What is a static variable?
**Definition:** A variable shared across ALL instances of a class. One copy exists per class, not per object.
**Core Idea:** Class-level state. All objects see the same value.
**How it Works:** Stored in the method area (metaspace). Initialized when the class is loaded.
**Example:** `static int instanceCount = 0;` — incremented in the constructor to count objects created.
**Interview Insight:** Static variables are NOT thread-safe by default. Use `AtomicInteger` or `synchronized` if multiple threads modify them.

---

### Q16. What is the `final` keyword?
**Definition:** Prevents modification — on variables (can't reassign), methods (can't override), classes (can't extend).
**Core Idea:** A final variable must be initialized once and never changed.
**How it Works:**
- `final int x = 5;` — x can never be reassigned
- `final void doWork()` — subclass can't override
- `final class String` — can't be subclassed
**Example:** `final class String` — why you can't extend String in Java.
**Interview Insight:** `final` on a reference means the reference can't point elsewhere — but the object it points to CAN still be mutated.

---

### Q17. What is immutability?
**Definition:** An object whose state cannot be changed after construction.
**Core Idea:** Thread-safe by design. No synchronization needed if an object can't change.
**How it Works:** `final` class + `final` fields + no setters + deep copy in constructor for mutable fields.
**Example:** `String`, `Integer`, `LocalDate` in Java are immutable.
**Interview Insight:** Immutable objects can be safely shared between threads. The cost is creating new objects on mutation (see String pool optimization).

---

### Q18. What is the `this` keyword?
**Definition:** A reference to the current instance of the class.
**Core Idea:** Used to disambiguate field names from parameter names, and to chain constructors.
**How it Works:** Available in all instance methods and constructors. Not available in static methods.
**Example:** `this.name = name;` — `this.name` is the field; `name` is the parameter.
**Interview Insight:** `this(...)` must be the first statement in a constructor if used for chaining.

---

### Q19. What is the `super` keyword?
**Definition:** A reference to the parent class from within a subclass.
**Core Idea:** Used to call parent constructors and parent methods that have been overridden.
**How it Works:** `super()` calls parent constructor (must be first line). `super.method()` calls parent's version of an overridden method.
**Example:** `class Cat extends Animal { Cat() { super("Cat"); } }` — passes name to Animal's constructor.
**Interview Insight:** If you don't explicitly call `super()`, Java inserts `super()` (no-arg) automatically. If parent has no no-arg constructor, you MUST call `super(args)` explicitly.

---

← [Index](00_index.md) | [02 JVM Architecture →](02_jvm_architecture_memory.md)
