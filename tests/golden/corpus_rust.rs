//! Rust Golden Corpus - Grammar Coverage MECE Test
//!
//! This file contains all key node types from tree-sitter-rust grammar
//! to verify complete coverage of Rust language features.
//!
//! Coverage includes:
//! - Function items (regular, async, const, unsafe)
//! - Impl blocks (inherent, trait)
//! - Trait definitions
//! - Struct items (regular, tuple, unit)
//! - Enum items
//! - Type aliases
//! - Module declarations
//! - Use declarations
//! - Macro invocations and definitions
//! - Closures and match expressions
//! - Attributes and derive macros

use std::collections::HashMap;
use std::fmt::{Display, Formatter, Result as FmtResult};
use std::io::{Read, Write};

// ============================================================================
// MODULE AND USE DECLARATIONS
// ============================================================================

/// Inner module
mod inner_module {
    pub fn inner_function() -> i32 {
        42
    }
}

/// Re-export from inner module
pub use inner_module::inner_function;

/// Multiple use declarations
use std::sync::{Arc, Mutex};
use std::thread;

// ============================================================================
// TYPE ALIASES
// ============================================================================

/// Simple type alias
type StringMap = HashMap<String, String>;

/// Generic type alias
type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;

/// Complex type alias with lifetimes
type BoxedFn<'a> = Box<dyn Fn(&str) -> String + 'a>;

// ============================================================================
// STRUCT DEFINITIONS
// ============================================================================

/// Regular struct with named fields
#[derive(Debug, Clone)]
struct Person {
    name: String,
    age: u32,
    email: Option<String>,
}

/// Tuple struct
#[derive(Debug)]
struct Point3D(f64, f64, f64);

/// Unit struct
struct UnitMarker;

/// Generic struct
#[derive(Debug, Clone)]
struct Container<T> {
    value: T,
    metadata: HashMap<String, String>,
}

/// Struct with lifetimes
struct Reference<'a> {
    data: &'a str,
}

// ============================================================================
// ENUM DEFINITIONS
// ============================================================================

/// Simple enum
#[derive(Debug, Clone, PartialEq)]
enum Status {
    Active,
    Inactive,
    Pending,
}

/// Enum with data
#[derive(Debug)]
enum Message {
    Quit,
    Move { x: i32, y: i32 },
    Write(String),
    ChangeColor(u8, u8, u8),
}

/// Generic enum
enum Option2<T> {
    Some(T),
    None,
}

// ============================================================================
// TRAIT DEFINITIONS
// ============================================================================

/// Basic trait
trait Animal {
    fn make_sound(&self) -> String;
    fn age(&self) -> u32;
}

/// Trait with associated types
trait Iterator2 {
    type Item;
    fn next(&mut self) -> Option<Self::Item>;
}

/// Trait with default implementation
trait Describable {
    fn describe(&self) -> String {
        "No description".to_string()
    }
}

/// Trait with generics
trait Converter<T, U> {
    fn convert(&self, value: T) -> U;
}

// ============================================================================
// IMPL BLOCKS - INHERENT IMPLEMENTATIONS
// ============================================================================

impl Person {
    /// Constructor (associated function)
    fn new(name: String, age: u32) -> Self {
        Person {
            name,
            age,
            email: None,
        }
    }

    /// Method with self reference
    fn greet(&self) -> String {
        format!("Hello, I'm {} and I'm {} years old", self.name, self.age)
    }

    /// Mutable method
    fn set_email(&mut self, email: String) {
        self.email = Some(email);
    }

    /// Method consuming self
    fn consume(self) -> String {
        self.name
    }

    /// Associated constant
    const MAX_AGE: u32 = 150;
}

impl Point3D {
    fn distance(&self) -> f64 {
        (self.0 * self.0 + self.1 * self.1 + self.2 * self.2).sqrt()
    }
}

impl<T> Container<T> {
    fn new(value: T) -> Self {
        Container {
            value,
            metadata: HashMap::new(),
        }
    }

    fn get_value(&self) -> &T {
        &self.value
    }
}

// ============================================================================
// IMPL BLOCKS - TRAIT IMPLEMENTATIONS
// ============================================================================

impl Animal for Person {
    fn make_sound(&self) -> String {
        "Hello!".to_string()
    }

    fn age(&self) -> u32 {
        self.age
    }
}

impl Display for Person {
    fn fmt(&self, f: &mut Formatter<'_>) -> FmtResult {
        write!(f, "{} (age {})", self.name, self.age)
    }
}

impl Describable for Person {
    fn describe(&self) -> String {
        format!("{} is {} years old", self.name, self.age)
    }
}

// ============================================================================
// FUNCTION ITEMS
// ============================================================================

/// Regular function
fn regular_function(x: i32, y: i32) -> i32 {
    x + y
}

/// Function with generic parameters
fn generic_function<T: Display>(value: T) -> String {
    format!("Value: {}", value)
}

/// Function with where clause
fn where_clause_function<T, U>(t: T, u: U) -> String
where
    T: Display,
    U: Display,
{
    format!("{} and {}", t, u)
}

/// Async function
async fn async_function(url: &str) -> Result<String> {
    Ok(format!("Fetched: {}", url))
}

/// Const function
const fn const_function(x: i32) -> i32 {
    x * 2
}

/// Unsafe function
unsafe fn unsafe_function(ptr: *const i32) -> i32 {
    *ptr
}

/// Function with multiple return points
fn early_return(x: i32) -> i32 {
    if x < 0 {
        return 0;
    }
    if x > 100 {
        return 100;
    }
    x
}

/// Function with lifetimes
fn longest<'a>(x: &'a str, y: &'a str) -> &'a str {
    if x.len() > y.len() {
        x
    } else {
        y
    }
}

// ============================================================================
// CONST AND STATIC ITEMS
// ============================================================================

/// Constant item
const MAX_POINTS: u32 = 100_000;

/// Static item
static GLOBAL_COUNT: std::sync::atomic::AtomicU32 = std::sync::atomic::AtomicU32::new(0);

/// Static mutable (unsafe)
static mut GLOBAL_STATE: i32 = 0;

/// Const with type annotation
const PI: f64 = 3.14159265359;

// ============================================================================
// LET DECLARATIONS
// ============================================================================

fn let_declarations_demo() {
    // Simple let binding
    let x = 5;

    // Type annotated let binding
    let y: i32 = 10;

    // Mutable let binding
    let mut counter = 0;
    counter += 1;

    // Pattern matching in let
    let (a, b, c) = (1, 2, 3);

    // Destructuring struct
    let Person { name, age, .. } = Person::new("Alice".to_string(), 30);

    // If let
    let maybe_value = Some(42);
    if let Some(value) = maybe_value {
        println!("Value: {}", value);
    }

    // While let
    let mut stack = vec![1, 2, 3];
    while let Some(top) = stack.pop() {
        println!("{}", top);
    }
}

// ============================================================================
// CLOSURES
// ============================================================================

fn closure_examples() {
    // Simple closure
    let add_one = |x: i32| x + 1;

    // Multi-parameter closure
    let add = |a: i32, b: i32| a + b;

    // Closure with block body
    let complex_closure = |x: i32| {
        let doubled = x * 2;
        doubled + 1
    };

    // Closure capturing environment
    let y = 10;
    let capture_closure = |x| x + y;

    // Closure with move
    let s = String::from("hello");
    let move_closure = move || {
        println!("{}", s);
    };

    // Higher-order function with closure
    let numbers = vec![1, 2, 3, 4, 5];
    let doubled: Vec<i32> = numbers.iter().map(|x| x * 2).collect();
    let filtered: Vec<i32> = numbers.into_iter().filter(|x| x % 2 == 0).collect();
}

// ============================================================================
// MATCH EXPRESSIONS
// ============================================================================

fn match_examples(status: Status, message: Message) -> String {
    // Simple match
    let status_str = match status {
        Status::Active => "active",
        Status::Inactive => "inactive",
        Status::Pending => "pending",
    };

    // Match with destructuring
    let msg_str = match message {
        Message::Quit => "Quitting".to_string(),
        Message::Move { x, y } => format!("Move to ({}, {})", x, y),
        Message::Write(text) => format!("Write: {}", text),
        Message::ChangeColor(r, g, b) => format!("Color: rgb({}, {}, {})", r, g, b),
    };

    // Match with guards
    let number = 42;
    let result = match number {
        n if n < 0 => "negative",
        n if n == 0 => "zero",
        n if n < 10 => "small",
        n if n < 100 => "medium",
        _ => "large",
    };

    format!("{} - {} - {}", status_str, msg_str, result)
}

// ============================================================================
// MACRO INVOCATIONS
// ============================================================================

fn macro_invocations() {
    // println! macro
    println!("Hello, world!");

    // vec! macro
    let numbers = vec![1, 2, 3, 4, 5];

    // format! macro
    let formatted = format!("Number: {}", 42);

    // assert! macro
    assert!(2 + 2 == 4);

    // assert_eq! macro
    assert_eq!(2 + 2, 4);

    // matches! macro
    let result = matches!(Status::Active, Status::Active);

    // dbg! macro
    let value = dbg!(2 + 2);

    // Custom macro invocation (assuming it exists)
    // my_macro!();
}

// ============================================================================
// MACRO DEFINITIONS
// ============================================================================

/// Simple declarative macro
macro_rules! say_hello {
    () => {
        println!("Hello!");
    };
}

/// Macro with parameters
macro_rules! create_function {
    ($func_name:ident) => {
        fn $func_name() {
            println!("You called {:?}()", stringify!($func_name));
        }
    };
}

/// Macro with multiple patterns
macro_rules! calculate {
    (add $a:expr, $b:expr) => {
        $a + $b
    };
    (mul $a:expr, $b:expr) => {
        $a * $b
    };
}

// ============================================================================
// ATTRIBUTES
// ============================================================================

/// Function with multiple attributes
#[inline]
#[allow(dead_code)]
fn attributed_function() -> i32 {
    42
}

/// Conditional compilation
#[cfg(target_os = "linux")]
fn linux_only_function() {
    println!("This only runs on Linux");
}

/// Test attribute
#[cfg(test)]
mod tests {
    #[test]
    fn test_addition() {
        assert_eq!(2 + 2, 4);
    }

    #[test]
    #[should_panic]
    fn test_panic() {
        panic!("This test should panic");
    }

    #[test]
    #[ignore]
    fn expensive_test() {
        // Long-running test
    }
}

// ============================================================================
// ASYNC/AWAIT
// ============================================================================

async fn async_examples() {
    // Async function call
    let _result = async_function("https://example.com").await;

    // Async block
    let async_block = async {
        let value = 42;
        value * 2
    };

    let _value = async_block.await;
}

// ============================================================================
// ERROR HANDLING
// ============================================================================

fn error_handling_examples() -> Result<()> {
    // Question mark operator
    let _file_content = std::fs::read_to_string("test.txt")?;

    // Result matching
    match std::fs::read_to_string("test.txt") {
        Ok(content) => println!("{}", content),
        Err(e) => eprintln!("Error: {}", e),
    }

    Ok(())
}

// ============================================================================
// MAIN FUNCTION
// ============================================================================

fn main() {
    println!("Rust Golden Corpus");

    // Create instances
    let person = Person::new("Alice".to_string(), 30);
    println!("{}", person.greet());
    println!("{}", person);

    let point = Point3D(3.0, 4.0, 0.0);
    println!("Distance: {}", point.distance());

    // Test enums
    let status = Status::Active;
    let message = Message::Write("Hello".to_string());
    println!("{}", match_examples(status, message));

    // Test closures
    closure_examples();

    // Test macros
    macro_invocations();
    say_hello!();

    // Test let declarations
    let_declarations_demo();
}
