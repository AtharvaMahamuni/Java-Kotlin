package Kotlin.Koan.Conventions

// ----------------------
// Model: Date
// ----------------------
data class MyDate(
    val year: Int,
    val month: Int,
    val dayOfMonth: Int
) : Comparable<MyDate> {

    override fun compareTo(other: MyDate): Int = when {
        year != other.year -> year - other.year
        month != other.month -> month - other.month
        else -> dayOfMonth - other.dayOfMonth
    }

    // Simple implementation for demo purposes
    // (normally this would handle month/year boundaries)
    fun followingDate(): MyDate =
        copy(dayOfMonth = dayOfMonth + 1)
}

// ----------------------
// Range: makes ".." work
// ----------------------
class DateRange(
    private val start: MyDate,
    private val end: MyDate
) : Iterable<MyDate> {

    // This is REQUIRED by Iterable<T>
    override fun iterator(): Iterator<MyDate> {

        // Object expression = anonymous class (Java equivalent)
        return object : Iterator<MyDate> {

            // Internal state of the iterator
            private var current: MyDate = start

            // Called BEFORE every loop iteration
            override fun hasNext(): Boolean {
                return current <= end
            }

            // Called to fetch the next element
            override fun next(): MyDate {
                val result = current       // value to return
                current = current.followingDate() // move forward
                return result
            }
        }
    }
}

// ----------------------
// Enables: date1..date2
// ----------------------
operator fun MyDate.rangeTo(other: MyDate): DateRange =
    DateRange(this, other)

// ----------------------
// Usage
// ----------------------
fun main() {

    val start = MyDate(2024, 5, 1)
    val end = MyDate(2024, 5, 3)

    // PUT A BREAKPOINT HERE
    for (date in start..end) {
        println("Iterating: $date")
    }
}
