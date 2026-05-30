"""Built-in Ruby corpus for grammar coverage auto-discovery."""

CORPUS: str = """\
require "json"
require_relative "utils"

CONSTANT = 42
MAX_RETRIES = 3

module Greetable
  def greet
    "Hello, I am #{name}"
  end
end

class Animal
  include Greetable
  attr_accessor :name, :age
  attr_reader :id
  @@count = 0

  def initialize(name, age)
    @name = name; @age = age; @id = @@count += 1
  end

  def self.count; @@count; end
  def speak; raise NotImplementedError; end
  def to_s; "#<#{self.class.name} name=#{@name}>"; end

  protected
  def internal_state; { name: @name }; end

  private
  def secret; "shhh"; end  # pragma: allowlist secret
end

class Dog < Animal
  def initialize(name, breed)
    super(name, 0); @breed = breed
  end
  def speak; "Woof!"; end
end

module DataProcessor
  def self.process(items, &block)
    items.map(&block).compact
  end
end

result = [1, 2, 3].map { |x| x * 2 }.select { |x| x > 2 }
hash = { key: "value", number: 42 }

begin
  risky_operation
rescue ArgumentError => e
  puts e.message
rescue StandardError
  retry if (MAX_RETRIES -= 1) > 0
ensure
  cleanup
end

;
"""
