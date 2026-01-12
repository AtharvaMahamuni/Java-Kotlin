package Kotlin.Koan.Collections

// Build a map from the customer name to the customer
fun Shop.nameToCustomerMap(): Map<String, Customer> =
    customers.associateBy { it.name }

// Build a map from the customer to their city
fun Shop.customerToCityMap(): Map<Customer, City> =
    customers.associateWith { it.city }

// Build a map from the customer name to their city
fun Shop.customerNameToCityMap(): Map<String, City> =
    customers.associate { it.name to it.city }

fun main() {
    // Cities
    val london = City("London")
    val paris = City("Paris")

    // Dummy order
    val order = Order(
        products = listOf(Product("Laptop", 1200.0)),
        isDelivered = true
    )

    // Customers
    val customers = listOf(
        Customer("Alice", london, listOf(order)),
        Customer("Bob", paris, listOf(order)),
        Customer("Charlie", london, listOf(order))
    )

    // Shop
    val shop = Shop(
        name = "Map Demo Shop",
        customers = customers
    )

    // 1 Name -> Customer
    val nameToCustomer = shop.nameToCustomerMap()
    println("Name to Customer map:")
    nameToCustomer.forEach { (name, customer) ->
        println("$name -> ${customer.city}")
    }

    // 2 Customer -> City
    val customerToCity = shop.customerToCityMap()
    println("\nCustomer to City map:")
    customerToCity.forEach { (customer, city) ->
        println("${customer.name} -> $city")
    }

    // 3 Customer Name -> City
    val nameToCity = shop.customerNameToCityMap()
    println("\nCustomer name to City map:")
    nameToCity.forEach { (name, city) ->
        println("$name -> $city")
    }
}
