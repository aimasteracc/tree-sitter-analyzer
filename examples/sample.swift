import Foundation

public protocol Greeter {
    func greet(name: String) -> String
}

public struct Greeting: Greeter {
    public let prefix: String
    private var count: Int = 0

    public init(prefix: String) {
        self.prefix = prefix
    }

    public mutating func greet(name: String) -> String {
        count += 1
        return "\(prefix), \(name)"
    }
}

final class GreetingService {
    private var greeting = Greeting(prefix: "Hello")

    func welcome(_ user: String) -> String {
        return greeting.greet(name: user)
    }
}
