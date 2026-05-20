package model

type User struct {
	Name string
}

func NewUser() *User {
	return &User{}
}
