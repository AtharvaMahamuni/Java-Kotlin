package Kotlin.Koan.Conventions

class Invokable {
    var numberOfInvocations: Int = 0
        private set

    operator fun invoke(): Invokable {
        numberOfInvocations++
        return this
    }
}

fun invokeTwice(invokable: Invokable): Invokable =
    invokable()()//()() // to invoke 4 times

fun main() {
    val invokable = Invokable()

    invokeTwice(invokable)

    println("Number of invocations: ${invokable.numberOfInvocations}")
}
