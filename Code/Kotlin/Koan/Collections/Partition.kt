package Kotlin.Koan.Collections

// Return customers who have more undelivered orders than delivered
fun Shop.getCustomersWithMoreUndeliveredOrders(): Set<Customer> =
    customers.filter {
        val (delivered, undelivered) = it.orders.partition { it.isDelivered }
        undelivered.size > delivered.size
    }.toSet()

fun main() {
    val london = City("London")

    // Products
    val laptop = Product("Laptop", 1200.0)
    val phone = Product("Phone", 800.0)

    // Orders
    val deliveredOrder = Order(
        products = listOf(laptop),
        isDelivered = true
    )

    val undeliveredOrder = Order(
        products = listOf(phone),
        isDelivered = false
    )

    // Customers with different delivery patterns
    val customers = listOf(
        Customer(
            name = "Alice",
            city = london,
            orders = listOf(undeliveredOrder, undeliveredOrder, deliveredOrder)
            // 2 undelivered, 1 delivered -> INCLUDED
        ),
        Customer(
            name = "Bob",
            city = london,
            orders = listOf(deliveredOrder, deliveredOrder)
            // 0 undelivered, 2 delivered -> NOT included
        ),
        Customer(
            name = "Charlie",
            city = london,
            orders = listOf(undeliveredOrder, deliveredOrder)
            // 1 undelivered, 1 delivered -> NOT included
        ),
        Customer(
            name = "Diana",
            city = london,
            orders = listOf(undeliveredOrder, undeliveredOrder)
            // 2 undelivered, 0 delivered -> INCLUDED
        )
    )

    val shop = Shop(
        name = "Delivery Shop",
        customers = customers
    )

    // Run the function
    val result = shop.getCustomersWithMoreUndeliveredOrders()

    println("Customers with more undelivered orders:\n")
    result.forEach { customer ->
        val deliveredCount = customer.orders.count { it.isDelivered }
        val undeliveredCount = customer.orders.count { !it.isDelivered }

        println(
            "${customer.name} -> " +
                    "Delivered: $deliveredCount, " +
                    "Undelivered: $undeliveredCount"
        )
    }
}
