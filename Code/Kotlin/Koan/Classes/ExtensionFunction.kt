package Kotlin.Koan.Classes

fun Int.r(): RationalNumber = RationalNumber(this, 1)

fun Pair<Int, Int>.r(): RationalNumber = RationalNumber(this.first, this.second)

data class RationalNumber(val numerator: Int, val denominator: Int) {
    override fun toString(): String = "$numerator/$denominator"
}

fun main() {
    // Using Int extension
    val a = 5.r()
    println("From Int: $a")

    // Using Pair<Int, Int> extension
    val b = Pair(3, 4).r()
    println("From Pair: $b")

    // Another example
    val c = (10 to 2).r()
    println("From 'to': $c")
}
