package Kotlin.Koan.Collections

// Find all the different cities the customers are from
fun Shop.getCustomerCities(): Set<City> =
    customers.map { customer ->
        customer.city
    }.toSet()

// Find the customers living in a given city
fun Shop.getCustomersFrom(city: City): List<Customer> =
    customers.filter { customer ->
        customer.city == city
    }


fun main() {
    // Cities
    val london = City("London")
    val paris = City("Paris")
    val berlin = City("Berlin")

    // Dummy orders (not important for this example)
    val order = Order(
        products = listOf(Product("Laptop", 1200.0)),
        isDelivered = true
    )

    // Customers
    val customers = listOf(
        Customer("Alice", london, listOf(order)),
        Customer("Bob", paris, listOf(order)),
        Customer("Charlie", london, listOf(order)),
        Customer("Diana", berlin, listOf(order))
    )

    // Shop
    val shop = Shop(
        name = "Demo Shop",
        customers = customers
    )

    // 1 Get all different cities
    val cities = shop.getCustomerCities()
    println("Customer cities: $cities")

    // 2 Get customers from a specific city
    val customersFromLondon = shop.getCustomersFrom(london)
    println("\nCustomers from London:")
    customersFromLondon.forEach { customer ->
        println("- ${customer.name}")
    }
}
