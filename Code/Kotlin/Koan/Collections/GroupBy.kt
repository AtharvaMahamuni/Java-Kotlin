package Kotlin.Koan.Collections

// Build a map that stores the customers living in a given city
fun Shop.groupCustomersByCity(): Map<City, List<Customer>> =
    customers.groupBy { it.city }

fun main() {
    // Cities
    val london = City("London")
    val paris = City("Paris")
    val berlin = City("Berlin")

    // Dummy order
    val order = Order(
        products = listOf(Product("Laptop", 1200.0)),
        isDelivered = true
    )

    // Customers
    val customers = listOf(
        Customer("Alice", london, listOf(order)),
        Customer("Bob", paris, listOf(order)),
        Customer("Charlie", london, listOf(order)),
        Customer("Diana", berlin, listOf(order)),
        Customer("Eve", london, listOf(order))
    )

    // Shop
    val shop = Shop(
        name = "Grouping Shop",
        customers = customers
    )

    // Group customers by city
    val customersByCity = shop.groupCustomersByCity()

    println("Customers grouped by city:\n")

    customersByCity.forEach { (city, customersInCity) ->
        println("${city.name}:")
        customersInCity.forEach { customer ->
            println("  - ${customer.name}")
        }
    }
}
