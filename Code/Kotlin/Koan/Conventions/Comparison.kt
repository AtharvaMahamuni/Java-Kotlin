package Kotlin.Koan.Conventions

//data class MyDate(
//    val year: Int,
//    val month: Int,
//    val dayOfMonth: Int
//) : Comparable<MyDate> {
//
//    override fun compareTo(other: MyDate) = when {
//        year != other.year -> year - other.year
//        month != other.month -> month - other.month
//        else -> dayOfMonth - other.dayOfMonth
//    }
//}
//
//fun test(date1: MyDate, date2: MyDate) {
//    println("test(): date1 < date2 = ${date1 < date2}")
//}
//
//fun main() {
//
//    println("=== Example 1: Same month, different days ===")
//    val e1a = MyDate(2024, 5, 10)
//    val e1b = MyDate(2024, 5, 12)
//    println(e1a < e1b)   // true
//    println(e1a > e1b)   // false
//
//    println("\n=== Example 2: Different months ===")
//    val e2a = MyDate(2024, 4, 30)
//    val e2b = MyDate(2024, 5, 1)
//    println(e2a < e2b)   // true
//    println(e2a >= e2b)  // false
//
//    println("\n=== Example 3: Different years ===")
//    val e3a = MyDate(2023, 12, 31)
//    val e3b = MyDate(2024, 1, 1)
//    println(e3a < e3b)   // true
//    println(e3a <= e3b)  // true
//
//    println("\n=== Example 4: Same date ===")
//    val e4a = MyDate(2024, 6, 15)
//    val e4b = MyDate(2024, 6, 15)
//    println(e4a == e4b)  // true
//    println(e4a <= e4b)  // true
//    println(e4a >= e4b)  // true
//
//    println("\n=== Example 5: Sorting dates ===")
//    val dates = listOf(
//        MyDate(2024, 12, 1),
//        MyDate(2023, 1, 1),
//        MyDate(2024, 1, 1)
//    )
//    println(dates.sorted())
//
//    println("\n=== Example 6: Using test() function ===")
//    val e6a = MyDate(2024, 7, 10)
//    val e6b = MyDate(2024, 7, 20)
//    test(e6a, e6b)
//}
