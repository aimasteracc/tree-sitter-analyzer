# frozen_string_literal: true

=begin
Ruby Golden Corpus - Grammar Coverage MECE Test

This file contains all key node types from tree-sitter-ruby grammar
to verify complete coverage of Ruby language features.

Coverage includes:
- Methods (regular, singleton, class methods)
- Classes (class, module, singleton class)
- Assignments (regular, operator, multiple)
- Method calls (call, yield, super)
- Control flow (if, unless, case, for, while, until)
- Blocks and iterators
- Ruby-specific features (attr_accessor, alias, define_method)
=end

require 'json'
require 'set'
require 'time'

# ============================================================================
# Module Definitions
# ============================================================================

# Simple module
module Printable
  def print_info
    puts "Printable module"
  end
end

# Nested module
module Outer
  module Inner
    def inner_method
      "inner"
    end
  end
end

# Module with class methods
module Utilities
  module_function

  def self.class_method
    "class method in module"
  end

  def helper_method
    "helper"
  end
end

# ============================================================================
# Class Definitions
# ============================================================================

# Simple class
class Animal
  attr_reader :name
  attr_writer :age
  attr_accessor :species

  # Class variable
  @@count = 0

  # Class method using self
  def self.count
    @@count
  end

  # Class method using class << self
  class << self
    def total_count
      @@count
    end

    def reset_count
      @@count = 0
    end
  end

  # Constructor
  def initialize(name, species)
    @name = name
    @species = species
    @age = 0
    @@count += 1
  end

  # Instance method
  def speak
    "Animal sound"
  end

  # Method with parameters
  def describe(prefix = "This is", suffix = "!")
    "#{prefix} #{@name}#{suffix}"
  end

  # Method with keyword arguments
  def update(name: nil, species: nil, age: nil)
    @name = name unless name.nil?
    @species = species unless species.nil?
    @age = age unless age.nil?
  end

  # Method with splat operator
  def eat(*foods)
    foods.each { |food| puts "Eating #{food}" }
  end

  # Method with double splat (keyword arguments)
  def configure(**options)
    options.each { |key, value| puts "#{key}: #{value}" }
  end

  # Method with block parameter
  def process(&block)
    block.call if block_given?
  end

  # Private methods
  private

  def private_helper
    "private"
  end

  # Protected methods
  protected

  def protected_helper
    "protected"
  end
end

# Class with inheritance
class Dog < Animal
  def initialize(name, breed)
    super(name, "dog")
    @breed = breed
  end

  # Override method
  def speak
    "Woof!"
  end

  # Call super with arguments
  def describe(prefix = "Dog:")
    super(prefix, "!")
  end

  # Getter for breed
  def breed
    @breed
  end
end

# Class with module inclusion
class Cat < Animal
  include Printable
  extend Utilities

  def initialize(name)
    super(name, "cat")
  end

  def speak
    "Meow!"
  end
end

# Singleton class
class Database
  @instance = nil

  private_class_method :new

  def self.instance
    @instance ||= new
  end

  def connect
    puts "Connected to database"
  end
end

# ============================================================================
# Singleton Methods
# ============================================================================

# Singleton method on object
obj = Object.new

def obj.singleton_method
  "singleton method on object"
end

# Singleton method on class
class SingletonExample
  def self.class_singleton_method
    "class singleton method"
  end
end

# Using class << self syntax
class AnotherSingleton
  class << self
    def another_class_method
      "another class method"
    end

    def chained_method
      "chained"
    end
  end
end

# ============================================================================
# Method Definitions (Various Types)
# ============================================================================

# Regular method at top level
def top_level_method
  "top level"
end

# Method with explicit return
def explicit_return(x)
  return x * 2 if x > 10
  x
end

# Method with multiple return values
def multiple_returns
  return 1, 2, 3
end

# Method with optional parameters
def optional_params(a, b = 10, c = 20)
  a + b + c
end

# Method with keyword arguments
def keyword_method(name:, age: 0, city: "Unknown")
  "#{name}, #{age}, #{city}"
end

# Method with splat and double splat
def complex_params(required, *args, keyword: nil, **kwargs, &block)
  puts "Required: #{required}"
  puts "Args: #{args.inspect}"
  puts "Keyword: #{keyword}"
  puts "Kwargs: #{kwargs.inspect}"
  block.call if block
end

# Method with rescue
def method_with_rescue
  risky_operation
rescue StandardError => e
  puts "Error: #{e.message}"
ensure
  puts "Cleanup"
end

def risky_operation
  raise "Something went wrong"
end

# Method with yield
def method_with_yield
  puts "Before yield"
  yield if block_given?
  yield 10 if block_given?
  puts "After yield"
end

# Method calling yield with arguments
def iterator_method
  yield 1
  yield 2
  yield 3
end

# ============================================================================
# Assignments
# ============================================================================

# Simple assignment
simple = 10

# Multiple assignment
a, b, c = 1, 2, 3

# Splat in assignment
first, *rest, last = [1, 2, 3, 4, 5]

# Parallel assignment
x, y = y, x if defined?(y)

# Assignment with rescue
value = begin
  risky_operation
rescue
  "default"
end

# Operator assignments
counter = 0
counter += 1
counter -= 1
counter *= 2
counter /= 2
counter %= 3
counter **= 2
counter ||= 10
counter &&= 20

# Assignment in condition
if (match = "hello".match(/h(.)ll(.)/))
  puts match[1]
end

# Instance variable assignment
@instance_var = "instance"

# Class variable assignment (in class context)
class AssignmentExample
  @@class_var = "class"

  def self.show_class_var
    @@class_var
  end
end

# Global variable assignment
$global_var = "global"

# Constant assignment
CONSTANT = 42
MAX_SIZE = 100

# ============================================================================
# Method Calls
# ============================================================================

# Simple method call
puts "Hello, World!"

# Method call with arguments
puts("With parentheses")

# Method call on object
"string".upcase

# Chained method calls
result = "hello".upcase.reverse.chars.join("-")

# Method call with block
[1, 2, 3].each { |n| puts n }

# Method call with do-end block
[1, 2, 3].each do |n|
  puts n * 2
end

# Method call with multiple arguments
[1, 2, 3].reduce(0) { |sum, n| sum + n }

# Safe navigation operator
object = nil
object&.method_call

# Method call with keyword arguments
keyword_method(name: "Alice", age: 30)

# Method call with splat
args = [1, 2, 3]
optional_params(*args)

# Method call with double splat
options = { name: "Bob", age: 25 }
keyword_method(**options)

# ============================================================================
# Blocks and Procs
# ============================================================================

# Block with single line
lambda_single = -> { puts "lambda" }

# Lambda with parameters
lambda_with_params = ->(x, y) { x + y }

# Lambda with do-end
lambda_multi = lambda do |x|
  x * 2
end

# Proc
proc_example = Proc.new { |x| x * 2 }

# Block variable
block_var = proc { |a, b| a + b }

# Method accepting block
def accept_block(&block)
  block.call(10)
end

# Call with block
accept_block { |x| x * 2 }

# ============================================================================
# Control Flow - If/Unless
# ============================================================================

# If statement
if true
  puts "true branch"
end

# If-else
if false
  puts "false"
else
  puts "true"
end

# If-elsif-else
value = 10
if value > 20
  puts "large"
elsif value > 10
  puts "medium"
else
  puts "small"
end

# Inline if (modifier)
puts "positive" if value > 0

# Unless statement
unless false
  puts "unless true"
end

# Unless-else
unless true
  puts "false branch"
else
  puts "true branch"
end

# Inline unless (modifier)
puts "not zero" unless value == 0

# Ternary operator
status = value > 0 ? "positive" : "negative"

# ============================================================================
# Control Flow - Case
# ============================================================================

# Case statement with when
day = "Monday"
case day
when "Monday"
  puts "Start of week"
when "Tuesday", "Wednesday", "Thursday"
  puts "Middle of week"
when "Friday"
  puts "End of week"
when "Saturday", "Sunday"
  puts "Weekend"
else
  puts "Unknown"
end

# Case with range
score = 85
grade = case score
when 90..100
  "A"
when 80..89
  "B"
when 70..79
  "C"
when 60..69
  "D"
else
  "F"
end

# Case with regex
input = "hello"
case input
when /^h/
  puts "Starts with h"
when /o$/
  puts "Ends with o"
end

# Case with class
obj = "string"
case obj
when String
  puts "It's a string"
when Integer
  puts "It's an integer"
when Array
  puts "It's an array"
end

# ============================================================================
# Control Flow - Loops
# ============================================================================

# While loop
counter = 0
while counter < 5
  puts counter
  counter += 1
end

# While modifier
begin
  puts "loop"
  counter += 1
end while counter < 10

# Until loop
counter = 0
until counter >= 5
  puts counter
  counter += 1
end

# Until modifier
begin
  puts "loop"
  counter -= 1
end until counter <= 0

# For loop
for i in 1..5
  puts i
end

# For loop with array
for item in ["a", "b", "c"]
  puts item
end

# Loop with break
loop do
  puts "infinite"
  break
end

# Loop with next (continue)
5.times do |i|
  next if i == 2
  puts i
end

# Loop with redo
counter = 0
5.times do
  counter += 1
  redo if counter == 3 && counter < 4
  puts counter
end

# ============================================================================
# Iterators and Enumerables
# ============================================================================

# Each
[1, 2, 3].each { |n| puts n }

# Map
squares = [1, 2, 3].map { |n| n ** 2 }

# Select (filter)
evens = [1, 2, 3, 4, 5].select { |n| n.even? }

# Reject
odds = [1, 2, 3, 4, 5].reject { |n| n.even? }

# Reduce
sum = [1, 2, 3, 4, 5].reduce(0) { |acc, n| acc + n }

# Each with index
["a", "b", "c"].each_with_index do |item, index|
  puts "#{index}: #{item}"
end

# Times
5.times { |i| puts i }

# Upto/Downto
1.upto(5) { |i| puts i }
5.downto(1) { |i| puts i }

# Step
0.step(10, 2) { |i| puts i }

# ============================================================================
# Exception Handling
# ============================================================================

# Begin-rescue-end
begin
  raise "Error"
rescue => e
  puts "Caught: #{e.message}"
end

# Rescue with specific exception
begin
  1 / 0
rescue ZeroDivisionError => e
  puts "Division by zero: #{e}"
rescue StandardError => e
  puts "Standard error: #{e}"
end

# Rescue with else
begin
  puts "No error"
rescue
  puts "Error"
else
  puts "Success"
end

# Rescue with ensure
begin
  puts "Try"
rescue
  puts "Rescue"
ensure
  puts "Always executed"
end

# Inline rescue
result = 1 / 0 rescue "error"

# Raise with custom message
def custom_error
  raise ArgumentError, "Invalid argument"
end

# ============================================================================
# String Interpolation and Literals
# ============================================================================

# String interpolation
name = "Alice"
greeting = "Hello, #{name}!"

# Expression in interpolation
total = "Total: #{1 + 2 + 3}"

# String with escape sequences
escaped = "Line 1\nLine 2\tTabbed"

# Single-quoted string (no interpolation)
literal = 'No #{interpolation} here'

# Multiline string
multiline = <<~HEREDOC
  This is a
  multiline string
  with indentation removed
HEREDOC

# Symbol
symbol = :symbol_name
symbol_with_string = :"symbol from string"

# ============================================================================
# Array and Hash Literals
# ============================================================================

# Array literals
empty_array = []
number_array = [1, 2, 3, 4, 5]
mixed_array = [1, "two", :three, [4, 5]]

# Array with %w
word_array = %w[one two three four]

# Array with %i (symbols)
symbol_array = %i[one two three]

# Hash literals
empty_hash = {}
string_hash = { "key1" => "value1", "key2" => "value2" }
symbol_hash = { key1: "value1", key2: "value2" }
mixed_hash = { "string_key" => 1, symbol_key: 2 }

# Nested structures
nested = {
  array: [1, 2, 3],
  hash: { inner: "value" },
  mixed: [{ a: 1 }, { b: 2 }]
}

# ============================================================================
# Regular Expressions
# ============================================================================

# Regex literal
regex = /hello/
regex_with_flags = /hello/i

# Regex match
if "hello world" =~ /world/
  puts "Match found"
end

# Match with capture groups
if (match = "hello world".match(/(\w+) (\w+)/))
  puts "First word: #{match[1]}"
  puts "Second word: #{match[2]}"
end

# Regex substitution
replaced = "hello world".gsub(/world/, "Ruby")

# ============================================================================
# Metaprogramming
# ============================================================================

# Define method dynamically
class DynamicClass
  define_method(:dynamic_method) do
    "dynamically defined"
  end

  # Method missing
  def method_missing(method_name, *args, &block)
    "Called missing method: #{method_name}"
  end

  def respond_to_missing?(method_name, include_private = false)
    true
  end
end

# Attr methods
class AttributeExample
  attr_reader :read_only
  attr_writer :write_only
  attr_accessor :read_write

  def initialize
    @read_only = "read"
    @write_only = "write"
    @read_write = "both"
  end
end

# Alias
class AliasExample
  def original_method
    "original"
  end

  alias aliased_method original_method
  alias :symbol_alias :original_method
end

# Class eval
String.class_eval do
  def custom_method
    "custom method on String"
  end
end

# Instance eval
obj = Object.new
obj.instance_eval do
  def singleton_via_eval
    "singleton via eval"
  end
end

# ============================================================================
# Operators
# ============================================================================

# Arithmetic operators
addition = 1 + 2
subtraction = 5 - 3
multiplication = 4 * 5
division = 10 / 2
modulo = 10 % 3
exponentiation = 2 ** 3

# Comparison operators
equal = (1 == 1)
not_equal = (1 != 2)
greater = (5 > 3)
less = (3 < 5)
greater_or_equal = (5 >= 5)
less_or_equal = (3 <= 5)
spaceship = (1 <=> 2)

# Logical operators
and_op = true && false
or_op = true || false
not_op = !true

# Bitwise operators
bitwise_and = 5 & 3
bitwise_or = 5 | 3
bitwise_xor = 5 ^ 3
bitwise_not = ~5
left_shift = 5 << 1
right_shift = 5 >> 1

# Range operators
inclusive_range = 1..10
exclusive_range = 1...10

# ============================================================================
# Special Variables and Constants
# ============================================================================

# Special variables
# $0 - script name
# $$ - process id
# $: - load path
# $" - loaded features

# Class and module constants
class ConstantExample
  VERSION = "1.0.0"
  MAX_RETRIES = 3
end

# ============================================================================
# Main Execution
# ============================================================================

# Only run if this is the main file
if __FILE__ == $PROGRAM_NAME
  puts "=== Ruby Golden Corpus Test ==="

  # Test classes
  dog = Dog.new("Buddy", "Golden Retriever")
  puts dog.speak
  puts dog.describe

  # Test methods
  puts top_level_method
  a, b, c = multiple_returns
  puts "Multiple returns: #{a}, #{b}, #{c}"

  # Test blocks
  method_with_yield do
    puts "Inside block"
  end

  # Test iterators
  iterator_method { |n| puts "Yielded: #{n}" }

  # Test control flow
  result = case 85
  when 90..100 then "A"
  when 80..89 then "B"
  else "C"
  end
  puts "Grade: #{result}"

  # Test arrays and hashes
  puts squares.inspect
  puts evens.inspect

  puts "=== Test Complete ==="
end
