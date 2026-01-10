package Kotlin.Koan.Introduction

fun containsEven(collection: Collection<Int>): Boolean =
    collection.any { it % 2 == 0 }

fun main() {
    println(containsEven(collection = arrayListOf(1, 2, 3, 4)))
}