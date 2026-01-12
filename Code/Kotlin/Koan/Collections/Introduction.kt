package Kotlin.Koan.Collections

fun Shop.getSetOfCustomers(): Set<Customer> =
    customers.toSet()

fun main() {
    val numbersMap = mutableMapOf<String, String>().apply {
        this["one"] = "1"
        this["two"] = "2"
    }

    println("Numbers map: $numbersMap")

    val london = City("London")

    val product = Product("Laptop", 1200.0)
    val order = Order(listOf(product), isDelivered = true)

    val customers = listOf(
        Customer("Alice", london, listOf(order)),
        Customer("Bob", london, listOf(order)),
        Customer("Alice", london, listOf(order)) // duplicate
    )

    val shop = Shop(
        name = "My Shop",
        customers = customers
    )

    val customerSet = shop.customers.toSet()
    println("Customers as set: $customerSet")
}
