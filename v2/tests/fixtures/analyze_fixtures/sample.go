package main

import "fmt"

type Calculator struct {
	Value int
}

func (c *Calculator) Add(a, b int) int {
	return a + b
}

func Greet(name string) string {
	return "Hello, " + name
}

func main() {
	c := Calculator{Value: 0}
	fmt.Println(c.Add(1, 2))
	fmt.Println(Greet("World"))
}
