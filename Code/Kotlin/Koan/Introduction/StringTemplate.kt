package Kotlin.Koan.Introduction

const val month = "(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)"

fun main() {
    val date = "13 JUN 1992"

    val regex = Regex(getPattern())

    println(regex.matches(date)) // should print: true
}

fun getPattern(): String =
    """\d{2}\s$month\s\d{4}"""
