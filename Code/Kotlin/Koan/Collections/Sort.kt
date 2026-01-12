package Kotlin.Koan.Collections

// Return a list of customers, sorted descending by number of orders
fun Shop.getCustomersSortedByOrders(): List<Customer> =
    customers.sortedByDescending { it.orders.size }

fun main() {
    val london = City("London")
    val paris = City("Paris")

    // Products
    val laptop = Product("Laptop", 1300.0)
    val phone = Product("Phone", 800.0)
    val tablet = Product("Tablet", 600.0)
    val monitor = Product("Monitor", 400.0)

    // Orders
    val smallOrder = Order(
        products = listOf(phone),
        isDelivered = true
    )

    val mediumOrder = Order(
        products = listOf(laptop, monitor),
        isDelivered = true
    )

    val largeOrder = Order(
        products = listOf(laptop, phone, tablet),
        isDelivered = false
    )

    // Customers with different number of orders
    val customers = listOf(

        Customer(
            name = "Bob",
            city = paris,
            orders = listOf(mediumOrder) // 1 order
        ),
        Customer(
            name = "Charlie",
            city = london,
            orders = listOf(smallOrder, largeOrder) // 2 orders
        ),Customer(
                name = "Alice",
        city = london,
        orders = listOf(smallOrder, mediumOrder, largeOrder) // 3 orders
    ),
    )

    val shop = Shop(
        name = "Tech Store",
        customers = customers
    )

    println("Customers sorted by number of orders:\n")

    shop.getCustomersSortedByOrders().forEach { customer ->
        val totalProducts = customer.orders.sumOf { it.products.size }

        println(
            "${customer.name} (${customer.city}) -> " +
                    "${customer.orders.size} orders, " +
                    "$totalProducts total products"
        )
    }
}
