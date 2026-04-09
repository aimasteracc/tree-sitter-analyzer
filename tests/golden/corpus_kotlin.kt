/**
 * Kotlin Golden Corpus - Grammar Coverage MECE Test
 *
 * This file contains all key node types from tree-sitter-kotlin grammar
 * to verify complete coverage of Kotlin language features.
 *
 * Coverage includes:
 * - Function declarations (regular, inline, suspend, operator)
 * - Anonymous functions
 * - Class declarations (regular, data, sealed, enum, inner, companion)
 * - Object declarations
 * - Interface declarations
 * - Property declarations (val, var, with accessors)
 * - Variable declarations
 * - Lambda literals
 * - When expressions
 * - Type aliases
 * - Annotations
 */

package com.example.goldencorpus

import kotlin.collections.HashMap
import kotlin.collections.mutableListOf
import kotlin.math.sqrt

// ============================================================================
// TYPE ALIASES
// ============================================================================

typealias StringMap = HashMap<String, String>
typealias IntPredicate = (Int) -> Boolean
typealias PersonList = List<Person>

// ============================================================================
// ANNOTATIONS
// ============================================================================

@Target(AnnotationTarget.CLASS, AnnotationTarget.FUNCTION)
@Retention(AnnotationRetention.RUNTIME)
annotation class CustomAnnotation(val value: String)

@Target(AnnotationTarget.PROPERTY)
annotation class Validated

@Deprecated("Use newFunction instead", ReplaceWith("newFunction()"))
annotation class OldAnnotation

// ============================================================================
// CLASS DECLARATIONS - DATA CLASSES
// ============================================================================

/**
 * Data class with primary constructor
 */
data class Person(
    val name: String,
    val age: Int,
    val email: String? = null
) {
    // Secondary constructor
    constructor(name: String) : this(name, 0, null)

    // Property with custom getter
    val isAdult: Boolean
        get() = age >= 18

    // Method in data class
    fun greet(): String {
        return "Hello, I'm $name and I'm $age years old"
    }

    // Companion object
    companion object {
        const val MAX_AGE = 150

        fun createDefault(): Person {
            return Person("Unknown", 0)
        }
    }
}

// ============================================================================
// CLASS DECLARATIONS - REGULAR CLASSES
// ============================================================================

/**
 * Regular class with properties and methods
 */
class Animal(val name: String, val species: String) {
    // Property declaration with backing field
    var sound: String = ""
        get() = field.uppercase()
        set(value) {
            field = value.lowercase()
        }

    // Property with private setter
    var age: Int = 0
        private set

    // Late-initialized property
    lateinit var owner: String

    // Lazy property
    val description: String by lazy {
        "$name is a $species"
    }

    // Public method
    fun makeSound(): String {
        return sound
    }

    // Method with default parameters
    fun feed(food: String = "generic food", amount: Int = 1) {
        println("Feeding $name with $amount $food")
    }

    // Infix function
    infix fun likes(food: String): Boolean {
        return true
    }

    // Operator overloading
    operator fun plus(other: Animal): String {
        return "$name and ${other.name}"
    }
}

// ============================================================================
// CLASS DECLARATIONS - ABSTRACT CLASSES
// ============================================================================

abstract class Shape(val color: String) {
    // Abstract property declaration
    abstract val area: Double

    // Abstract method
    abstract fun draw(): String

    // Concrete method in abstract class
    open fun describe(): String {
        return "A $color shape with area $area"
    }

    // Protected method
    protected open fun validate(): Boolean {
        return area > 0
    }
}

class Circle(color: String, val radius: Double) : Shape(color) {
    override val area: Double
        get() = Math.PI * radius * radius

    override fun draw(): String {
        return "Drawing a $color circle"
    }

    override fun describe(): String {
        return super.describe() + " (circle)"
    }
}

// ============================================================================
// CLASS DECLARATIONS - SEALED CLASSES
// ============================================================================

sealed class Result<out T> {
    data class Success<T>(val data: T) : Result<T>()
    data class Error(val message: String, val code: Int) : Result<Nothing>()
    object Loading : Result<Nothing>()
}

sealed interface Vehicle {
    val wheels: Int
}

// ============================================================================
// CLASS DECLARATIONS - ENUM CLASSES
// ============================================================================

enum class Status {
    ACTIVE,
    INACTIVE,
    PENDING
}

enum class Color(val rgb: Int) {
    RED(0xFF0000),
    GREEN(0x00FF00),
    BLUE(0x0000FF);

    fun toHex(): String = "#${rgb.toString(16).padStart(6, '0')}"
}

enum class Direction {
    NORTH, SOUTH, EAST, WEST;

    fun opposite(): Direction = when (this) {
        NORTH -> SOUTH
        SOUTH -> NORTH
        EAST -> WEST
        WEST -> EAST
    }
}

// ============================================================================
// CLASS DECLARATIONS - INNER CLASSES
// ============================================================================

class Outer(val value: String) {
    private val outerProperty = "outer"

    inner class Inner {
        fun getOuterValue(): String {
            return this@Outer.value
        }

        fun accessOuter(): String {
            return outerProperty
        }
    }

    class Nested {
        fun nestedFunction(): String {
            return "nested"
        }
    }
}

// ============================================================================
// OBJECT DECLARATIONS
// ============================================================================

/**
 * Singleton object
 */
object DatabaseConfig {
    const val HOST = "localhost"
    const val PORT = 5432

    private val connections = mutableListOf<String>()

    fun connect(database: String) {
        connections.add(database)
    }

    fun getConnections(): List<String> = connections
}

/**
 * Object expression (anonymous object)
 */
fun createAnonymousObject(): Any {
    return object {
        val x = 10
        val y = 20

        fun sum() = x + y
    }
}

// ============================================================================
// COMPANION OBJECTS
// ============================================================================

class Factory {
    companion object Creator {
        const val VERSION = "1.0"

        fun create(): Factory {
            return Factory()
        }
    }
}

class WithDefaultCompanion {
    companion object {
        fun createDefault() = WithDefaultCompanion()
    }
}

// ============================================================================
// INTERFACE DECLARATIONS
// ============================================================================

interface Drawable {
    // Abstract property in interface
    val name: String

    // Abstract method
    fun draw(): String

    // Method with default implementation
    fun describe(): String {
        return "Drawing $name"
    }
}

interface Clickable {
    fun click(): String
    fun doubleClick(): String = "Double clicked"
}

// Interface with properties
interface Named {
    val firstName: String
    val lastName: String
    val fullName: String
        get() = "$firstName $lastName"
}

// ============================================================================
// FUNCTION DECLARATIONS
// ============================================================================

/**
 * Regular function declaration
 */
fun regularFunction(x: Int, y: Int): Int {
    return x + y
}

/**
 * Function with default parameters
 */
fun functionWithDefaults(name: String, age: Int = 18, city: String = "Unknown"): String {
    return "$name, $age, from $city"
}

/**
 * Function with named parameters
 */
fun createPerson(name: String, age: Int, email: String? = null): Person {
    return Person(name, age, email)
}

/**
 * Inline function declaration
 */
inline fun <T> measureTime(block: () -> T): Pair<T, Long> {
    val startTime = System.currentTimeMillis()
    val result = block()
    val endTime = System.currentTimeMillis()
    return result to (endTime - startTime)
}

/**
 * Suspend function (for coroutines)
 */
suspend fun fetchData(url: String): String {
    // Simulated async operation
    return "Data from $url"
}

/**
 * Operator function
 */
operator fun Point.plus(other: Point): Point {
    return Point(this.x + other.x, this.y + other.y)
}

/**
 * Infix function declaration
 */
infix fun Int.times(str: String): String {
    return str.repeat(this)
}

/**
 * Extension function
 */
fun String.isPalindrome(): Boolean {
    return this == this.reversed()
}

/**
 * Function with vararg
 */
fun concatenate(separator: String, vararg items: String): String {
    return items.joinToString(separator)
}

/**
 * Generic function declaration
 */
fun <T> singletonList(item: T): List<T> {
    return listOf(item)
}

/**
 * Function with reified type parameter
 */
inline fun <reified T> isInstanceOf(value: Any): Boolean {
    return value is T
}

/**
 * Tail-recursive function
 */
tailrec fun factorial(n: Int, accumulator: Int = 1): Int {
    return if (n <= 1) accumulator else factorial(n - 1, n * accumulator)
}

// ============================================================================
// ANONYMOUS FUNCTIONS
// ============================================================================

fun anonymousFunctionExamples() {
    // Anonymous function
    val sum = fun(x: Int, y: Int): Int {
        return x + y
    }

    // Anonymous function with type inference
    val multiply = fun(x: Int, y: Int) = x * y

    // Anonymous function as argument
    listOf(1, 2, 3).map(fun(x: Int): Int {
        return x * 2
    })

    // Anonymous function with receiver
    val operation = fun Int.(other: Int): Int {
        return this + other
    }
}

// ============================================================================
// LAMBDA LITERALS
// ============================================================================

fun lambdaExamples() {
    // Simple lambda literal
    val square: (Int) -> Int = { x -> x * x }

    // Lambda with multiple parameters
    val add: (Int, Int) -> Int = { a, b -> a + b }

    // Lambda with no parameters
    val greeting: () -> String = { "Hello" }

    // Lambda with implicit parameter (it)
    val double: (Int) -> Int = { it * 2 }

    // Lambda with destructuring
    val sumPair: (Pair<Int, Int>) -> Int = { (a, b) -> a + b }

    // Higher-order function with lambda
    val numbers = listOf(1, 2, 3, 4, 5)
    val doubled = numbers.map { it * 2 }
    val evens = numbers.filter { it % 2 == 0 }

    // Lambda with return label
    val result = numbers.map {
        if (it > 3) return@map it * 2
        it
    }

    // Trailing lambda syntax
    numbers.forEach { number ->
        println(number)
    }

    // Lambda with receiver
    val builder: StringBuilder.() -> Unit = {
        append("Hello")
        append(" ")
        append("World")
    }
}

// ============================================================================
// PROPERTY DECLARATIONS
// ============================================================================

// Top-level property declaration (val)
val globalConstant: String = "constant"

// Top-level property declaration (var)
var globalVariable: Int = 42

// Property with custom getter
val computedProperty: Int
    get() = globalVariable * 2

// Property with custom getter and setter
var propertyWithAccessors: String = ""
    get() = field.uppercase()
    set(value) {
        field = value.lowercase()
    }

// Delegated property
class PropertyDelegateExample {
    var delegatedProperty: String by lazy {
        "initialized"
    }

    @Validated
    var annotatedProperty: String = ""
}

// ============================================================================
// VARIABLE DECLARATIONS
// ============================================================================

fun variableDeclarations() {
    // val declaration (read-only)
    val immutableValue: Int = 42

    // var declaration (mutable)
    var mutableValue: Int = 10
    mutableValue += 5

    // Type inference
    val inferredString = "Hello"
    val inferredInt = 100

    // Multiple variable declarations
    val (x, y) = Pair(1, 2)

    // Destructuring declaration
    val (name, age) = Person("Alice", 30)

    // Destructuring in for loop
    val map = mapOf("a" to 1, "b" to 2)
    for ((key, value) in map) {
        println("$key -> $value")
    }
}

// ============================================================================
// WHEN EXPRESSIONS
// ============================================================================

fun whenExpressions(value: Any): String {
    // When with subject
    val result1 = when (value) {
        is String -> "String: $value"
        is Int -> "Int: $value"
        is Person -> "Person: ${value.name}"
        else -> "Unknown type"
    }

    // When with conditions
    val number = 42
    val result2 = when {
        number < 0 -> "Negative"
        number == 0 -> "Zero"
        number in 1..10 -> "Small"
        number in 11..100 -> "Medium"
        else -> "Large"
    }

    // When with enum
    val status = Status.ACTIVE
    val result3 = when (status) {
        Status.ACTIVE -> "Active"
        Status.INACTIVE -> "Inactive"
        Status.PENDING -> "Pending"
    }

    // When with multiple conditions
    val result4 = when (value) {
        1, 2, 3 -> "Small number"
        in 4..10 -> "Medium number"
        !in 11..20 -> "Outside range"
        else -> "Other"
    }

    // Sealed class when (exhaustive)
    val apiResult: Result<String> = Result.Success("data")
    val result5 = when (apiResult) {
        is Result.Success -> "Success: ${apiResult.data}"
        is Result.Error -> "Error: ${apiResult.message}"
        Result.Loading -> "Loading..."
    }

    return "$result1 | $result2 | $result3 | $result4 | $result5"
}

// ============================================================================
// DATA STRUCTURES
// ============================================================================

data class Point(val x: Double, val y: Double) {
    fun distance(): Double {
        return sqrt(x * x + y * y)
    }

    operator fun component1() = x
    operator fun component2() = y
}

data class Rectangle(val topLeft: Point, val bottomRight: Point)

// ============================================================================
// GENERICS
// ============================================================================

class Box<T>(val value: T) {
    fun get(): T = value
}

interface Producer<out T> {
    fun produce(): T
}

interface Consumer<in T> {
    fun consume(item: T)
}

// Generic class with constraint
class Container<T : Comparable<T>>(val item: T) {
    fun compare(other: T): Int {
        return item.compareTo(other)
    }
}

// ============================================================================
// MAIN FUNCTION
// ============================================================================

fun main() {
    println("Kotlin Golden Corpus")

    // Test data class
    val person = Person("Alice", 30, "alice@example.com")
    println(person.greet())

    // Test regular class
    val dog = Animal("Buddy", "Dog")
    dog.sound = "woof"
    println(dog.makeSound())

    // Test when expressions
    println(whenExpressions(person))
    println(whenExpressions(42))

    // Test lambdas
    lambdaExamples()

    // Test object
    DatabaseConfig.connect("mydb")
    println(DatabaseConfig.getConnections())

    // Test sealed class
    val result: Result<String> = Result.Success("Hello")
    when (result) {
        is Result.Success -> println("Success: ${result.data}")
        is Result.Error -> println("Error: ${result.message}")
        Result.Loading -> println("Loading...")
    }

    // Test enum
    println(Color.RED.toHex())
    println(Direction.NORTH.opposite())

    // Test extension function
    println("radar".isPalindrome())

    // Test infix
    println(3 times "Hi ")

    // Test companion object
    val factory = Factory.create()
    println("Factory version: ${Factory.VERSION}")
}
