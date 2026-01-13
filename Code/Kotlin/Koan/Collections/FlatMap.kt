package Kotlin.Koan.Collections

// Return all products the given customer has ordered
fun Customer.getOrderedProducts(): List<Product> =
    orders.flatMap(Order::products)

// Return all products that were ordered by at least one customer
fun Shop.getOrderedProducts(): Set<Product> =
    customers.flatMap(Customer::getOrderedProducts).toSet()

fun main() {
    // Cities
    val london = City("London")
    val paris = City("Paris")

    // Products
    val milk = Product("Milk", 1.5)
    val bread = Product("Bread", 2.0)
    val cheese = Product("Cheese", 4.5)
    val eggs = Product("Eggs", 3.0)

    // Orders
    val order1 = Order(
        products = listOf(milk, bread),
        isDelivered = true
    )

    val order2 = Order(
        products = listOf(cheese),
        isDelivered = false
    )

    val order3 = Order(
        products = listOf(bread, eggs),
        isDelivered = true
    )

    // Customers
    val alice = Customer(
        name = "Alice",
        city = london,
        orders = listOf(order1, order2)
    )

    val bob = Customer(
        name = "Bob",
        city = paris,
        orders = listOf(order3)
    )

    // Shop
    val shop = Shop(
        name = "My Shop",
        customers = listOf(alice, bob)
    )

    // ---- Tests ----

    println("Products ordered by Alice:")
    println(alice.getOrderedProducts())

    println("\nProducts ordered by Bob:")
    println(bob.getOrderedProducts())

    println("\nAll products ordered in the shop:")
    println(shop.getOrderedProducts())
}
