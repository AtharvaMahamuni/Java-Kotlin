package Kotlin.Koan.Classes

// Expression evaluator using a sealed interface
// comment to run the SmartCasts, conflicting code

sealed interface Expr

class Num(val value: Int) : Expr

class Sum(val left: Expr, val right: Expr) : Expr

fun eval(expr: Expr): Int =
    when (expr) {
        is Num -> expr.value
        is Sum -> eval(expr.left) + eval(expr.right)
        // no else needed because Expr is sealed
    }

fun main() {
    // Represents the expression: (1 + 2) + 3
    val expr = Sum(
        Sum(Num(1), Num(2)),
        Num(3)
    )

    val result = eval(expr)
    println("Result: $result")
}
