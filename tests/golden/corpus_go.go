/*
Package main is the Go Golden Corpus for Grammar Coverage MECE Test.

This file contains all key node types from tree-sitter-go grammar
to verify complete coverage of Go language features.

Coverage includes:
- Function declarations (regular, methods, variadic)
- Type declarations (struct, interface, alias)
- Variable and constant declarations (var, const, short var)
- Import and package declarations
- Control flow (defer, go, select)
- Go-specific features (channels, goroutines, interfaces)
*/
package main

import (
	"context"
	"fmt"
	"io"
	"math"
	"os"
	"sync"
	"time"
)

// ============================================================================
// Package and Import Declarations
// ============================================================================

// Package clause is at the top of the file

// Import declarations are shown above with various styles:
// - Individual imports
// - Grouped imports
// - Aliased imports (demonstrated below)

import (
	. "fmt"     // dot import
	_ "image/png" // blank import (side effects only)
	customname "encoding/json" // aliased import
)

// ============================================================================
// Constant Declarations
// ============================================================================

// Single constant
const Pi = 3.14159

// Grouped constants
const (
	StatusOK = 200
	StatusNotFound = 404
	StatusInternalError = 500
)

// Constants with iota
const (
	Sunday = iota
	Monday
	Tuesday
	Wednesday
	Thursday
	Friday
	Saturday
)

// Constants with type
const (
	MaxInt int = int(^uint(0) >> 1)
	MinInt int = -MaxInt - 1
)

// ============================================================================
// Variable Declarations
// ============================================================================

// Single variable
var globalVar int = 42

// Multiple variables
var (
	x int = 10
	y int = 20
	z int = 30
)

// Variables with type inference
var (
	name = "Alice"
	age = 30
	active = true
)

// Multiple variables in one line
var a, b, c int = 1, 2, 3

// ============================================================================
// Type Declarations
// ============================================================================

// Type alias
type Integer = int
type StringAlias = string

// Simple type definition
type Age int
type Name string

// Struct type
type Person struct {
	Name    string
	Age     int
	Email   string
	Address *Address
}

// Nested struct
type Address struct {
	Street  string
	City    string
	Country string
	ZipCode int
}

// Struct with embedded fields
type Employee struct {
	Person  // embedded struct
	EmployeeID int
	Department string
	Salary float64
}

// Struct with tags
type User struct {
	ID       int    `json:"id" db:"user_id"`
	Username string `json:"username" db:"username"`
	Password string `json:"-" db:"password"`
}

// Interface type
type Reader interface {
	Read(p []byte) (n int, err error)
}

type Writer interface {
	Write(p []byte) (n int, err error)
}

// Interface composition
type ReadWriter interface {
	Reader
	Writer
}

// Empty interface
type Any interface{}

// Interface with type constraint (Go 1.18+)
type Number interface {
	int | int64 | float64
}

// Function type
type HandlerFunc func(w io.Writer, r io.Reader) error
type CompareFunc func(a, b interface{}) bool

// Channel type
type IntChannel chan int
type SendOnlyChannel chan<- string
type ReceiveOnlyChannel <-chan int

// Map type
type StringMap map[string]string
type IntMap map[int]interface{}

// Slice type
type IntSlice []int
type StringSlice []string

// Array type
type FixedArray [10]int

// Pointer type
type IntPointer *int

// ============================================================================
// Function Declarations
// ============================================================================

// Simple function
func add(a, b int) int {
	return a + b
}

// Function with multiple return values
func divide(a, b float64) (float64, error) {
	if b == 0 {
		return 0, fmt.Errorf("division by zero")
	}
	return a / b, nil
}

// Function with named return values
func namedReturns(x, y int) (sum int, diff int) {
	sum = x + y
	diff = x - y
	return // naked return
}

// Variadic function
func sum(numbers ...int) int {
	total := 0
	for _, n := range numbers {
		total += n
	}
	return total
}

// Function with variadic and regular parameters
func printf(format string, args ...interface{}) {
	fmt.Printf(format, args...)
}

// Function returning function (closure)
func makeAdder(x int) func(int) int {
	return func(y int) int {
		return x + y
	}
}

// Function with context
func processWithContext(ctx context.Context, data string) error {
	select {
	case <-ctx.Done():
		return ctx.Err()
	default:
		// process data
		return nil
	}
}

// Function with defer
func deferExample() {
	defer fmt.Println("defer 1")
	defer fmt.Println("defer 2")
	fmt.Println("normal")
}

// ============================================================================
// Method Declarations
// ============================================================================

// Method with value receiver
func (p Person) FullName() string {
	return fmt.Sprintf("%s (age %d)", p.Name, p.Age)
}

// Method with pointer receiver
func (p *Person) SetAge(age int) {
	p.Age = age
}

// Method on custom type
func (a Age) IsAdult() bool {
	return a >= 18
}

// Method on slice type
func (s IntSlice) Sum() int {
	total := 0
	for _, v := range s {
		total += v
	}
	return total
}

// Method implementing interface
func (p Person) Read(buf []byte) (int, error) {
	data := []byte(p.Name)
	n := copy(buf, data)
	return n, nil
}

func (p Person) Write(buf []byte) (int, error) {
	return len(buf), nil
}

// ============================================================================
// Short Variable Declarations
// ============================================================================

func shortVarExample() {
	// Short variable declaration
	message := "Hello, World!"
	count := 42
	enabled := true

	// Multiple short declarations
	x, y := 10, 20
	name, age := "Bob", 25

	// Short declaration in if
	if err := doSomething(); err != nil {
		fmt.Println(err)
	}

	// Short declaration in for
	for i := 0; i < 10; i++ {
		fmt.Println(i)
	}

	// Short declaration in switch
	switch val := getValue(); val {
	case 1:
		fmt.Println("one")
	case 2:
		fmt.Println("two")
	}

	// Use variables to avoid unused errors
	_ = message
	_ = count
	_ = enabled
	_ = x
	_ = y
	_ = name
	_ = age
}

func doSomething() error {
	return nil
}

func getValue() int {
	return 1
}

// ============================================================================
// Goroutines and Channels
// ============================================================================

// Function demonstrating goroutines
func goroutineExample() {
	// Go statement (launch goroutine)
	go fmt.Println("goroutine 1")

	// Go statement with anonymous function
	go func() {
		fmt.Println("anonymous goroutine")
	}()

	// Go statement with function call
	go processData("data")

	// Using channels
	ch := make(chan int)

	// Send to channel in goroutine
	go func() {
		ch <- 42
	}()

	// Receive from channel
	value := <-ch
	fmt.Println(value)

	// Buffered channel
	buffered := make(chan string, 10)
	buffered <- "message"
	msg := <-buffered
	_ = msg
}

func processData(data string) {
	fmt.Println(data)
}

// ============================================================================
// Select Statement
// ============================================================================

func selectExample() {
	ch1 := make(chan int)
	ch2 := make(chan string)
	timeout := time.After(1 * time.Second)

	// Select statement
	select {
	case val := <-ch1:
		fmt.Println("received int:", val)
	case msg := <-ch2:
		fmt.Println("received string:", msg)
	case <-timeout:
		fmt.Println("timeout")
	default:
		fmt.Println("no channel ready")
	}

	// Select for sending
	select {
	case ch1 <- 42:
		fmt.Println("sent to ch1")
	case ch2 <- "hello":
		fmt.Println("sent to ch2")
	default:
		fmt.Println("no channel ready for send")
	}
}

// ============================================================================
// Defer Statement
// ============================================================================

func deferStatements() {
	// Defer statement
	defer cleanup()

	// Multiple defer statements
	defer fmt.Println("first defer")
	defer fmt.Println("second defer")

	// Defer with anonymous function
	defer func() {
		fmt.Println("anonymous defer")
	}()

	// Defer with function call
	file, err := os.Open("file.txt")
	if err != nil {
		return
	}
	defer file.Close()
}

func cleanup() {
	fmt.Println("cleanup")
}

// ============================================================================
// Complex Types and Generics (Go 1.18+)
// ============================================================================

// Generic function
func GenericMax[T Number](a, b T) T {
	if a > b {
		return a
	}
	return b
}

// Generic type
type Stack[T any] struct {
	items []T
}

// Generic method
func (s *Stack[T]) Push(item T) {
	s.items = append(s.items, item)
}

func (s *Stack[T]) Pop() (T, bool) {
	if len(s.items) == 0 {
		var zero T
		return zero, false
	}
	item := s.items[len(s.items)-1]
	s.items = s.items[:len(s.items)-1]
	return item, true
}

// ============================================================================
// Struct Methods and Embedding
// ============================================================================

// Methods on embedded structs
type Engine struct {
	Power int
	Type  string
}

func (e *Engine) Start() {
	fmt.Printf("Starting %s engine with %d HP\n", e.Type, e.Power)
}

type Car struct {
	Engine  // embedding
	Make    string
	Model   string
	Year    int
}

func (c *Car) Drive() {
	c.Start() // can call embedded method directly
	fmt.Printf("Driving %d %s %s\n", c.Year, c.Make, c.Model)
}

// ============================================================================
// Interface Implementation
// ============================================================================

// Stringer interface implementation
type Point struct {
	X, Y float64
}

func (p Point) String() string {
	return fmt.Sprintf("Point(%f, %f)", p.X, p.Y)
}

// Error interface implementation
type CustomError struct {
	Code    int
	Message string
}

func (e *CustomError) Error() string {
	return fmt.Sprintf("Error %d: %s", e.Code, e.Message)
}

// ============================================================================
// Concurrency Patterns
// ============================================================================

func concurrencyPatterns() {
	// WaitGroup
	var wg sync.WaitGroup

	for i := 0; i < 5; i++ {
		wg.Add(1)
		go func(id int) {
			defer wg.Done()
			fmt.Printf("Goroutine %d\n", id)
		}(i)
	}

	wg.Wait()

	// Mutex
	var mu sync.Mutex
	counter := 0

	for i := 0; i < 10; i++ {
		go func() {
			mu.Lock()
			counter++
			mu.Unlock()
		}()
	}

	// Channel patterns
	ch := make(chan int, 5)
	done := make(chan bool)

	// Producer
	go func() {
		for i := 0; i < 5; i++ {
			ch <- i
		}
		close(ch)
	}()

	// Consumer
	go func() {
		for val := range ch {
			fmt.Println(val)
		}
		done <- true
	}()

	<-done
}

// ============================================================================
// Advanced Control Flow
// ============================================================================

func controlFlow() {
	// If statement with short declaration
	if value := compute(); value > 10 {
		fmt.Println("value is large")
	} else if value > 5 {
		fmt.Println("value is medium")
	} else {
		fmt.Println("value is small")
	}

	// Switch with multiple cases
	switch day := time.Now().Weekday(); day {
	case time.Saturday, time.Sunday:
		fmt.Println("Weekend")
	case time.Monday, time.Tuesday, time.Wednesday, time.Thursday, time.Friday:
		fmt.Println("Weekday")
	default:
		fmt.Println("Invalid day")
	}

	// Type switch
	var i interface{} = "hello"
	switch v := i.(type) {
	case int:
		fmt.Printf("int: %d\n", v)
	case string:
		fmt.Printf("string: %s\n", v)
	case bool:
		fmt.Printf("bool: %t\n", v)
	default:
		fmt.Printf("unknown type: %T\n", v)
	}

	// For loop variations
	for i := 0; i < 10; i++ {
		if i == 5 {
			continue
		}
		if i == 8 {
			break
		}
	}

	// Range loop
	numbers := []int{1, 2, 3, 4, 5}
	for index, value := range numbers {
		fmt.Printf("Index: %d, Value: %d\n", index, value)
	}

	// Range over map
	m := map[string]int{"a": 1, "b": 2, "c": 3}
	for key, value := range m {
		fmt.Printf("Key: %s, Value: %d\n", key, value)
	}

	// Range over channel
	ch := make(chan int, 3)
	ch <- 1
	ch <- 2
	ch <- 3
	close(ch)

	for val := range ch {
		fmt.Println(val)
	}
}

func compute() int {
	return 42
}

// ============================================================================
// Package Initialization
// ============================================================================

func init() {
	// init function runs before main
	fmt.Println("Package initialized")
}

// ============================================================================
// Main Function
// ============================================================================

func main() {
	// Test various features
	fmt.Println("Testing Go golden corpus")

	// Functions
	result := add(10, 20)
	fmt.Printf("Add: %d\n", result)

	// Structs
	p := Person{
		Name:  "Alice",
		Age:   30,
		Email: "alice@example.com",
	}
	fmt.Println(p.FullName())

	// Methods
	p.SetAge(31)
	fmt.Printf("New age: %d\n", p.Age)

	// Short var declarations
	shortVarExample()

	// Goroutines
	goroutineExample()

	// Generics
	maxInt := GenericMax(10, 20)
	maxFloat := GenericMax(3.14, 2.71)
	fmt.Printf("Max int: %d, Max float: %f\n", maxInt, maxFloat)

	// Stack
	stack := Stack[int]{}
	stack.Push(1)
	stack.Push(2)
	val, ok := stack.Pop()
	if ok {
		fmt.Printf("Popped: %d\n", val)
	}

	// Use math to avoid unused import
	_ = math.Pi

	// Use customname to avoid unused import
	_ = customname.Marshal
}
