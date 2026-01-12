package Kotlin.Koan.Collections

// Return true if all customers are from a given city
fun Shop.checkAllCustomersAreFrom(city: City): Boolean =
    customers.all {
        it.city == city
    }

// Return true if there is at least one customer from a given city
fun Shop.hasCustomerFrom(city: City): Boolean =
    customers.any {
        it.city == city
    }

// Return the number of customers from a given city
fun Shop.countCustomersFrom(city: City): Int =
    customers.count {
        it.city == city
    }

// Return a customer who lives in a given city, or null if there is none
fun Shop.findCustomerFrom(city: City): Customer? =
    customers.find {
        it.city == city
    }

fun main() {
    // Cities
    val london = City("London")
    val paris = City("Paris")

    // Dummy product & order
    val product = Product("Phone", 800.0)
    val order = Order(
        products = listOf(product),
        isDelivered = true
    )

    // Customers
    val customers = listOf(
        Customer("Alice", london, listOf(order)),
        Customer("Bob", london, listOf(order)),
        Customer("Charlie", paris, listOf(order))
    )

    // Shop
    val shop = Shop(
        name = "City Shop",
        customers = customers
    )

    // 1 Check if all customers are from London
    println("All customers from London? " +
            shop.checkAllCustomersAreFrom(london))

    // 2 Check if there is at least one customer from Paris
    println("Has customer from Paris? " +
            shop.hasCustomerFrom(paris))

    // 3 Count customers from London
    println("Number of customers from London: " +
            shop.countCustomersFrom(london))

    // 4 Find a customer from Paris
    val customerFromParis = shop.findCustomerFrom(paris)
    println("Customer from Paris: $customerFromParis")
}
