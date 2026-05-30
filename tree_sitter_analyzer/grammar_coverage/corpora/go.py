"""Built-in Go corpus for grammar coverage auto-discovery."""

CORPUS: str = """\
package main

import (
    "context"
    "errors"
    "fmt"
    "sync"
)

const MaxRetries = 3

var ErrNotFound = errors.New("not found")

type Status int

const (
    StatusActive Status = iota
    StatusInactive
    StatusPending
)

type User struct {
    ID    int
    Name  string
    Email string `json:"email,omitempty"`
}

type Repository interface {
    Find(ctx context.Context, id int) (*User, error)
    Save(ctx context.Context, user *User) error
}

func (u *User) String() string {
    return fmt.Sprintf("User{ID: %d, Name: %s}", u.ID, u.Name)
}

func NewUser(name, email string) *User {
    return &User{Name: name, Email: email}
}

func process[T any](items []T, fn func(T) T) []T {
    result := make([]T, len(items))
    for i, item := range items {
        result[i] = fn(item)
    }
    return result
}

func controlFlow(ctx context.Context) {
    x := 0
    x++
    x--

    for i := 0; i < 10; i++ {
        if i == 3 {
            continue
        }
        if i == 7 {
            break
        }
    }

loop:
    for i := 0; i < 5; i++ {
        switch i {
        case 2:
            break loop
        case 3:
            fallthrough
        default:
        }
    }

    switch v := x; {
    case v > 0:
    default:
    }

    switch x.(type) {
    case int:
    case string:
    }

    ch := make(chan int)
    select {
    case <-ctx.Done():
        return
    case v := <-ch:
        _ = v
    default:
    }

    _ = ctx
    goto done
done:
    ;
}

func variadics(vals ...int) int {
    sum := 0
    for _, v := range vals {
        sum += v
    }
    return sum
}

func main() {
    var wg sync.WaitGroup
    ch := make(chan int, 10)
    wg.Add(1)
    go func() {
        defer wg.Done()
        ch <- 42
    }()
    wg.Wait()

    defer func() {
        if r := recover(); r != nil {
            fmt.Println("recovered")
        }
    }()
}
"""
