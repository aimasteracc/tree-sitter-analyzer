/**
 * Scala Golden Corpus - Grammar Coverage MECE Test
 *
 * This file contains all key node types from tree-sitter-scala grammar
 * to verify complete coverage of Scala language features.
 *
 * Coverage includes:
 * - Function definitions and declarations
 * - Classes, Objects, Traits, Case Classes
 * - Val/Var definitions
 * - Type definitions and aliases
 * - Pattern matching
 * - For comprehensions
 * - Lambda expressions
 * - Imports and packages
 * - Implicit/given conversions
 */

// ============================================================================
// Package and Imports
// ============================================================================

package com.example.golden

import scala.collection.mutable.{ArrayBuffer, HashMap}
import scala.concurrent.Future
import scala.util.{Try, Success, Failure}

// ============================================================================
// Object Definitions
// ============================================================================

/** Companion object (singleton) */
object Constants {
  val PI: Double = 3.14159
  val E: Double = 2.71828

  def greeting: String = "Hello, Scala!"
}

/** Object with main method (application entry point) */
object MainApp extends App {
  println("Golden Corpus Test")
  val result = Calculator.add(5, 3)
  println(s"Result: $result")
}

/** Utility object */
object Calculator {
  def add(a: Int, b: Int): Int = a + b
  def subtract(a: Int, b: Int): Int = a - b
  def multiply(a: Int, b: Int): Int = a * b
  def divide(a: Int, b: Int): Option[Int] = {
    if (b != 0) Some(a / b) else None
  }
}

// ============================================================================
// Class Definitions
// ============================================================================

/** Basic class with primary constructor */
class Person(val name: String, var age: Int) {
  // Secondary constructor
  def this(name: String) = this(name, 0)

  // Method
  def greet(): String = s"Hello, I'm $name"

  // Method with default parameter
  def introduce(greeting: String = "Hi"): String = {
    s"$greeting, my name is $name"
  }

  // Method with multiple parameter lists
  def describe(prefix: String)(suffix: String): String = {
    s"$prefix $name $suffix"
  }
}

/** Class with private constructor */
class PrivateConstructor private(value: Int) {
  def getValue: Int = value
}

object PrivateConstructor {
  def create(value: Int): PrivateConstructor = new PrivateConstructor(value)
}

/** Class with type parameters (generics) */
class Container[T](val item: T) {
  def get: T = item
  def map[U](f: T => U): Container[U] = new Container(f(item))
}

/** Abstract class */
abstract class Shape {
  def area: Double
  def perimeter: Double

  def describe(): String = {
    s"Area: $area, Perimeter: $perimeter"
  }
}

/** Concrete class extending abstract class */
class Circle(val radius: Double) extends Shape {
  override def area: Double = Math.PI * radius * radius
  override def perimeter: Double = 2 * Math.PI * radius
}

class Rectangle(val width: Double, val height: Double) extends Shape {
  override def area: Double = width * height
  override def perimeter: Double = 2 * (width + height)
}

// ============================================================================
// Case Classes
// ============================================================================

/** Simple case class (immutable data holder) */
case class Point(x: Double, y: Double)

/** Case class with methods */
case class Vector(x: Double, y: Double) {
  def magnitude: Double = Math.sqrt(x * x + y * y)
  def normalized: Vector = {
    val mag = magnitude
    if (mag != 0) Vector(x / mag, y / mag) else this
  }

  def +(other: Vector): Vector = Vector(x + other.x, y + other.y)
  def -(other: Vector): Vector = Vector(x - other.x, y - other.y)
}

/** Nested case classes for ADT (Algebraic Data Type) */
sealed trait Expression
case class Number(value: Int) extends Expression
case class Add(left: Expression, right: Expression) extends Expression
case class Multiply(left: Expression, right: Expression) extends Expression

/** Case class with type parameters */
case class Box[T](content: T) {
  def map[U](f: T => U): Box[U] = Box(f(content))
}

// ============================================================================
// Traits
// ============================================================================

/** Basic trait (similar to Java interface) */
trait Describable {
  def description: String
}

/** Trait with concrete method */
trait Loggable {
  def log(message: String): Unit = println(s"[LOG] $message")
}

/** Trait with abstract and concrete methods */
trait Identifiable {
  def id: String
  def displayId(): String = s"ID: $id"
}

/** Trait with type parameters */
trait Comparable[T] {
  def compareTo(other: T): Int
}

/** Multiple trait inheritance */
trait Named {
  def name: String
}

trait Aged {
  def age: Int
}

class Employee(val name: String, val age: Int, val id: String)
    extends Named with Aged with Identifiable

// ============================================================================
// Function Definitions
// ============================================================================

/** Simple function definition */
def simpleFunction(x: Int): Int = x * 2

/** Function with multiple parameters */
def addNumbers(a: Int, b: Int): Int = a + b

/** Function with default parameters */
def greet(name: String, greeting: String = "Hello"): String = {
  s"$greeting, $name!"
}

/** Function with type parameters */
def identity[T](value: T): T = value

/** Function with bounded type parameter */
def max[T <: Comparable[T]](a: T, b: T): T = {
  if (a.compareTo(b) > 0) a else b
}

/** Function with multiple parameter lists (currying) */
def multiply(x: Int)(y: Int): Int = x * y

/** Higher-order function */
def applyTwice(f: Int => Int, x: Int): Int = f(f(x))

/** Function with by-name parameter */
def executeConditionally(condition: Boolean)(block: => Unit): Unit = {
  if (condition) block
}

/** Recursive function */
def factorial(n: Int): Int = {
  if (n <= 1) 1 else n * factorial(n - 1)
}

/** Tail-recursive function */
def fibonacciTail(n: Int): Int = {
  @scala.annotation.tailrec
  def loop(n: Int, a: Int, b: Int): Int = {
    if (n == 0) a
    else loop(n - 1, b, a + b)
  }
  loop(n, 0, 1)
}

// ============================================================================
// Lambda Expressions
// ============================================================================

/** Simple lambda */
val square: Int => Int = x => x * x

/** Lambda with multiple parameters */
val add: (Int, Int) => Int = (a, b) => a + b

/** Lambda with block body */
val complexLambda: Int => String = x => {
  val result = x * 2
  s"Result: $result"
}

/** Lambda with underscore syntax */
val increment: Int => Int = _ + 1
val sum: (Int, Int) => Int = _ + _

/** Lambda used in higher-order functions */
val numbers = List(1, 2, 3, 4, 5)
val doubled = numbers.map(x => x * 2)
val evens = numbers.filter(x => x % 2 == 0)
val total = numbers.reduce((a, b) => a + b)

// ============================================================================
// Val and Var Definitions
// ============================================================================

/** Immutable values (val) */
val immutableInt: Int = 42
val immutableString: String = "constant"
val inferredType = 3.14

/** Mutable variables (var) */
var mutableInt: Int = 0
var mutableString: String = "changeable"
var counter = 10

/** Multiple val/var declarations */
val (x, y) = (1, 2)
val Point(px, py) = Point(3.0, 4.0)

/** Lazy val */
lazy val expensiveComputation: Int = {
  println("Computing...")
  42
}

// ============================================================================
// Type Definitions
// ============================================================================

/** Type alias */
type UserId = String
type UserMap = Map[UserId, Person]
type Callback = String => Unit

/** Type member */
trait Container2 {
  type Element
  def get: Element
}

/** Opaque type alias (Scala 3 feature, shown as type alias here) */
type Temperature = Double

// ============================================================================
// Pattern Matching
// ============================================================================

/** Pattern matching with case clauses */
def describeNumber(x: Int): String = x match {
  case 0 => "zero"
  case 1 => "one"
  case n if n < 0 => "negative"
  case _ => "positive"
}

/** Pattern matching with case classes */
def evaluateExpression(expr: Expression): Int = expr match {
  case Number(n) => n
  case Add(left, right) => evaluateExpression(left) + evaluateExpression(right)
  case Multiply(left, right) => evaluateExpression(left) * evaluateExpression(right)
}

/** Pattern matching with Option */
def handleOption(opt: Option[Int]): String = opt match {
  case Some(value) => s"Got value: $value"
  case None => "No value"
}

/** Pattern matching with tuple */
def describePair(pair: (Int, Int)): String = pair match {
  case (0, 0) => "origin"
  case (x, 0) => s"on x-axis at $x"
  case (0, y) => s"on y-axis at $y"
  case (x, y) => s"point at ($x, $y)"
}

// ============================================================================
// For Comprehensions
// ============================================================================

/** Simple for comprehension */
val forResult = for {
  i <- 1 to 5
} yield i * 2

/** For comprehension with filter */
val evenSquares = for {
  i <- 1 to 10
  if i % 2 == 0
} yield i * i

/** Nested for comprehension */
val pairs = for {
  i <- 1 to 3
  j <- 1 to 3
  if i != j
} yield (i, j)

/** For comprehension with multiple generators */
val combinations = for {
  x <- List(1, 2, 3)
  y <- List("a", "b")
} yield (x, y)

// ============================================================================
// Exception Handling
// ============================================================================

/** Try-catch */
def safeDivide(a: Int, b: Int): Try[Int] = Try {
  a / b
}

def handleException(x: Int): String = {
  try {
    val result = 100 / x
    s"Result: $result"
  } catch {
    case _: ArithmeticException => "Division by zero"
    case e: Exception => s"Error: ${e.getMessage}"
  } finally {
    println("Cleanup")
  }
}

// ============================================================================
// Implicit Conversions (Scala 2 style)
// ============================================================================

/** Implicit class for extension methods */
implicit class StringOps(val s: String) extends AnyVal {
  def exclaim: String = s + "!"
  def repeat(n: Int): String = s * n
}

/** Implicit parameter */
def greetImplicit(name: String)(implicit greeting: String): String = {
  s"$greeting, $name"
}

implicit val defaultGreeting: String = "Welcome"

// ============================================================================
// Anonymous Classes
// ============================================================================

/** Anonymous class implementing trait */
val describableInstance: Describable = new Describable {
  override def description: String = "anonymous instance"
}

/** Anonymous class with multiple traits */
val multiTraitInstance: Named with Aged = new Named with Aged {
  override def name: String = "Anonymous"
  override def age: Int = 25
}

// ============================================================================
// Nested Structures
// ============================================================================

object NestedExample {
  class Outer {
    class Inner {
      def innerMethod(): String = "inner"
    }

    def outerMethod(): String = "outer"
  }

  def nestedFunction(): String = {
    def innerFunction(): String = "nested function"
    innerFunction()
  }
}

// ============================================================================
// Method Declaration (without implementation)
// ============================================================================

trait Service {
  def start(): Unit
  def stop(): Unit
  def restart(): Unit = {
    stop()
    start()
  }
}

// ============================================================================
// Self-type annotation
// ============================================================================

trait Component {
  self: Loggable =>
  def initialize(): Unit = {
    log("Initializing component")
  }
}

// ============================================================================
// Companion Pattern
// ============================================================================

class User(val username: String, private val password: String)

object User {
  def apply(username: String, password: String): User = {
    new User(username, password)
  }

  def unapply(user: User): Option[String] = Some(user.username)
}

// ============================================================================
// End of Golden Corpus
// ============================================================================
