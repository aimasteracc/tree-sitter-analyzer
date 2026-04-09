/**
 * Swift Golden Corpus - Grammar Coverage MECE Test
 *
 * This file contains all key node types from tree-sitter-swift grammar
 * to verify complete coverage of Swift language features.
 *
 * Coverage includes:
 * - Function declarations (regular, async, throwing, generic)
 * - Classes, Structs, Protocols, Extensions
 * - Properties (stored, computed, static, lazy)
 * - Subscripts
 * - Closures
 * - Type aliases
 * - Enums and associated values
 * - Imports
 * - Modern Swift features (async/await, actors, property wrappers)
 */

// ============================================================================
// Imports
// ============================================================================

import Foundation
import UIKit
import SwiftUI

// ============================================================================
// Function Declarations
// ============================================================================

/// Regular function with parameters and return type
func regularFunction(param1: Int, param2: String) -> String {
    return "\(param1): \(param2)"
}

/// Function with default parameters
func functionWithDefaults(x: Int = 10, y: Int = 20) -> Int {
    return x + y
}

/// Throwing function
func throwingFunction(value: Int) throws -> Int {
    if value < 0 {
        throw NSError(domain: "Invalid", code: -1)
    }
    return value * 2
}

/// Async function
func asyncFunction() async -> String {
    return await fetchData()
}

/// Async throwing function
func asyncThrowingFunction() async throws -> Data {
    return try await loadData()
}

/// Generic function
func genericFunction<T>(value: T) -> T {
    return value
}

/// Generic function with constraint
func constrainedGeneric<T: Comparable>(a: T, b: T) -> T {
    return a > b ? a : b
}

/// Function with inout parameter
func inoutFunction(value: inout Int) {
    value += 1
}

/// Variadic function
func variadicFunction(numbers: Int...) -> Int {
    return numbers.reduce(0, +)
}

// Helper functions for async examples
private func fetchData() async -> String {
    return "data"
}

private func loadData() async throws -> Data {
    return Data()
}

// ============================================================================
// Closures
// ============================================================================

/// Closure assigned to constant
let simpleClosure = { (x: Int) -> Int in
    return x * 2
}

/// Closure with shorthand argument names
let shorthandClosure = { $0 + $1 }

/// Trailing closure
func performOperation(operation: (Int, Int) -> Int) -> Int {
    return operation(5, 3)
}

let resultTrailing = performOperation { a, b in
    a + b
}

/// Closure capturing values
func makeIncrementer(incrementAmount: Int) -> () -> Int {
    var total = 0
    return {
        total += incrementAmount
        return total
    }
}

/// Escaping closure
func asyncOperation(completion: @escaping (String) -> Void) {
    completion("done")
}

// ============================================================================
// Classes
// ============================================================================

/// Base class with properties and methods
class BaseClass {
    // Stored property
    var storedProperty: String

    // Lazy stored property
    lazy var lazyProperty: String = {
        return "lazy value"
    }()

    // Static property
    static var staticProperty: Int = 0

    // Class property
    class var classProperty: String {
        return "class property"
    }

    // Computed property
    var computedProperty: String {
        get {
            return "computed: \(storedProperty)"
        }
        set {
            storedProperty = newValue
        }
    }

    // Read-only computed property
    var readOnlyComputed: String {
        return "read-only"
    }

    // Property with observers
    var observedProperty: Int = 0 {
        willSet {
            print("Will set to \(newValue)")
        }
        didSet {
            print("Did set from \(oldValue)")
        }
    }

    // Initializer
    init(value: String) {
        self.storedProperty = value
    }

    // Convenience initializer
    convenience init() {
        self.init(value: "default")
    }

    // Regular method
    func regularMethod() -> String {
        return "regular method"
    }

    // Static method
    static func staticMethod() -> String {
        return "static method"
    }

    // Class method
    class func classMethod() -> String {
        return "class method"
    }

    // Deinitializer
    deinit {
        print("Deinitializing")
    }
}

/// Derived class
class DerivedClass: BaseClass {
    var additionalProperty: Int = 0

    override init(value: String) {
        super.init(value: value)
        self.additionalProperty = 10
    }

    override func regularMethod() -> String {
        return super.regularMethod() + " overridden"
    }
}

/// Final class (cannot be inherited)
final class FinalClass {
    var value: Int = 0
}

// ============================================================================
// Structs
// ============================================================================

/// Basic struct
struct Point {
    var x: Double
    var y: Double

    // Computed property
    var magnitude: Double {
        return (x * x + y * y).squareRoot()
    }

    // Method
    func distance(to other: Point) -> Double {
        let dx = x - other.x
        let dy = y - other.y
        return (dx * dx + dy * dy).squareRoot()
    }

    // Mutating method
    mutating func moveBy(dx: Double, dy: Double) {
        x += dx
        y += dy
    }

    // Static method
    static func zero() -> Point {
        return Point(x: 0, y: 0)
    }
}

/// Struct with memberwise initializer
struct Rectangle {
    var width: Double
    var height: Double

    var area: Double {
        return width * height
    }
}

/// Generic struct
struct Stack<Element> {
    private var items: [Element] = []

    mutating func push(_ item: Element) {
        items.append(item)
    }

    mutating func pop() -> Element? {
        return items.popLast()
    }
}

// ============================================================================
// Protocols
// ============================================================================

/// Basic protocol
protocol Describable {
    var description: String { get }
    func describe() -> String
}

/// Protocol with static requirements
protocol Factory {
    static func create() -> Self
}

/// Protocol with associated type
protocol Container {
    associatedtype Item
    func add(_ item: Item)
    func get(at index: Int) -> Item?
}

/// Protocol inheritance
protocol AdvancedDescribable: Describable {
    var detailedDescription: String { get }
}

/// Protocol with default implementation (via extension)
extension Describable {
    func describe() -> String {
        return description
    }
}

// ============================================================================
// Extensions
// ============================================================================

/// Extension adding computed property
extension Int {
    var squared: Int {
        return self * self
    }
}

/// Extension adding method
extension String {
    func reversed() -> String {
        return String(self.reversed())
    }
}

/// Extension conforming to protocol
extension Point: Describable {
    var description: String {
        return "Point(x: \(x), y: \(y))"
    }
}

/// Extension with where clause
extension Array where Element: Comparable {
    func sorted() -> [Element] {
        return sorted(by: <)
    }
}

// ============================================================================
// Enums
// ============================================================================

/// Simple enum
enum Direction {
    case north
    case south
    case east
    case west
}

/// Enum with raw values
enum Planet: Int {
    case mercury = 1
    case venus = 2
    case earth = 3
    case mars = 4
}

/// Enum with associated values
enum Result<Success, Failure> {
    case success(Success)
    case failure(Failure)
}

/// Enum with methods
enum CompassPoint {
    case north, south, east, west

    func opposite() -> CompassPoint {
        switch self {
        case .north: return .south
        case .south: return .north
        case .east: return .west
        case .west: return .east
        }
    }
}

/// Enum with computed property
enum TrafficLight {
    case red, yellow, green

    var duration: Int {
        switch self {
        case .red: return 30
        case .yellow: return 5
        case .green: return 25
        }
    }
}

// ============================================================================
// Subscripts
// ============================================================================

/// Struct with subscript
struct Matrix {
    let rows: Int
    let columns: Int
    var grid: [Double]

    init(rows: Int, columns: Int) {
        self.rows = rows
        self.columns = columns
        self.grid = Array(repeating: 0.0, count: rows * columns)
    }

    subscript(row: Int, column: Int) -> Double {
        get {
            return grid[row * columns + column]
        }
        set {
            grid[row * columns + column] = newValue
        }
    }
}

/// Class with subscript
class Dictionary<Key: Hashable, Value> {
    private var storage: [Key: Value] = [:]

    subscript(key: Key) -> Value? {
        get {
            return storage[key]
        }
        set {
            storage[key] = newValue
        }
    }
}

// ============================================================================
// Type Aliases
// ============================================================================

typealias StringDictionary = [String: String]
typealias IntPair = (Int, Int)
typealias CompletionHandler = (Bool) -> Void
typealias GenericResult<T> = Result<T, Error>

// ============================================================================
// Property Wrappers
// ============================================================================

/// Property wrapper definition
@propertyWrapper
struct Capitalized {
    private var value: String = ""

    var wrappedValue: String {
        get { value }
        set { value = newValue.capitalized }
    }
}

/// Using property wrapper
struct Person {
    @Capitalized var name: String
    var age: Int
}

// ============================================================================
// Actors (Swift 5.5+)
// ============================================================================

/// Actor for thread-safe state management
actor Counter {
    private var value: Int = 0

    func increment() {
        value += 1
    }

    func getValue() -> Int {
        return value
    }
}

// ============================================================================
// Modern Swift Features
// ============================================================================

/// Async/await usage
func performAsyncWork() async {
    let data = await asyncFunction()
    print(data)
}

/// Task groups
func parallelWork() async {
    await withTaskGroup(of: String.self) { group in
        group.addTask { await asyncFunction() }
        group.addTask { await asyncFunction() }
    }
}

/// Property with result builder
@resultBuilder
struct StringBuilder {
    static func buildBlock(_ components: String...) -> String {
        components.joined(separator: "\n")
    }
}

// ============================================================================
// Operators
// ============================================================================

/// Custom operator
infix operator **: MultiplicationPrecedence

func ** (base: Double, exponent: Double) -> Double {
    return pow(base, exponent)
}

// ============================================================================
// Nested Types
// ============================================================================

class OuterClass {
    struct NestedStruct {
        enum NestedEnum {
            case option1
            case option2
        }

        func nestedMethod() -> String {
            return "nested"
        }
    }

    func useNested() -> NestedStruct {
        return NestedStruct()
    }
}

// ============================================================================
// Generic Constraints
// ============================================================================

/// Generic function with multiple constraints
func combine<T, U>(_ a: T, _ b: U) -> String where T: CustomStringConvertible, U: CustomStringConvertible {
    return "\(a.description), \(b.description)"
}

/// Generic type with constraints
struct Wrapper<T: Equatable> {
    var value: T

    func isEqual(to other: Wrapper<T>) -> Bool {
        return value == other.value
    }
}

// ============================================================================
// Error Handling
// ============================================================================

enum FileError: Error {
    case notFound
    case permissionDenied
    case corrupted
}

func readFile() throws -> String {
    throw FileError.notFound
}

func handleErrors() {
    do {
        let content = try readFile()
        print(content)
    } catch FileError.notFound {
        print("File not found")
    } catch {
        print("Other error: \(error)")
    }
}

// ============================================================================
// End of Golden Corpus
// ============================================================================
