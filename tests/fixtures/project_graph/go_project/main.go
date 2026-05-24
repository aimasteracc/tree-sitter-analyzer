package main

import (
	"fmt"
	"./internal/handler"
	"./internal/model"
)

func main() {
	fmt.Println("hello")
	handler.Serve()
	model.NewUser()
}
