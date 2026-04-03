"""Built-in code corpus for Phase 3 Auto-Discovery Engine.

每种语言提供覆盖主要语法结构的代码片段，用于：
1. Wrapper node 结构分析（解析 AST 提取特征）
2. 语法路径枚举（BFS 遍历发现节点类型组合）
3. 覆盖率缺口分析（对比 grammar 全量 vs corpus 中出现的）

注意：BUILTIN_CORPUS 存储 str（UTF-8 文本），但某些语言需要
BUILTIN_CORPUS_EXTRA 中额外的字节级 corpus（如 Python 2 语法片段）。
auto_discovery._collect_node_stats 会自动合并两者。
"""

# 所有支持语言的内置 corpus 代码片段
# key: 语言名（与 language_loader.LANGUAGE_MODULES 一致）
BUILTIN_CORPUS: dict[str, str] = {
    "python": '''\
from __future__ import annotations
import os
import sys
from typing import Optional

CONSTANT = 42
_private: int = 0

type Point = tuple[int, int]


@decorator
def simple_function(x: int, y: int = 0) -> int:
    """Docstring."""
    assert x >= 0, "x must be non-negative"
    global _private
    _private = x
    while x > 0:
        x -= 1
        if x == 5:
            continue
        if x == 2:
            break
    return x + y


@decorator1
@decorator2
class MyClass(BaseClass):
    class_var: int = 0

    def __init__(self, value: int) -> None:
        self.value = value

    @property
    def prop(self) -> int:
        return self.value

    @staticmethod
    def static_method() -> None:
        pass

    @classmethod
    def class_method(cls) -> "MyClass":
        return cls(0)

    def nested(self) -> None:
        nonlocal_val = 0
        def inner() -> None:
            nonlocal nonlocal_val
            nonlocal_val = 1
        inner()


async def async_func(items: list[int]) -> None:
    await some_coroutine()
    async for item in items:
        async with context() as ctx:
            pass


def with_types(x: int, *args: str, **kwargs: bool) -> Optional[str]:
    if x > 0:
        return str(x)
    elif x == 0:
        return None
    else:
        raise ValueError("negative")


result = [x * 2 for x in range(10) if x % 2 == 0]
gen = (x for x in range(10))
d = {k: v for k, v in enumerate(range(5))}
s = {x for x in range(5)}

try:
    risky()
except ValueError as e:
    pass
except (TypeError, RuntimeError):
    raise
finally:
    cleanup()

with open("file") as f:
    data = f.read()

match command:
    case "quit":
        sys.exit(0)
    case "hello":
        print("hi")
    case _:
        pass

lam = lambda x, y: x + y

x = 10
del x
''',

    "javascript": '''\
import { foo, bar } from "./module.js";
import DefaultExport from "./other.js";

const CONSTANT = 42;
let mutable = "hello";
var legacy = 0;

function regularFunction(x, y = 0) {
  return x + y;
}

function* generatorFunc() {
  yield 1;
  yield 2;
}

const arrowFunction = (x) => x * 2;

class Animal {
  #privateField = 0;

  constructor(name) {
    this.name = name;
  }

  get displayName() { return this.name; }
  set displayName(value) { this.name = value; }
  speak() { return `${this.name} makes a sound.`; }
  static create(name) { return new Animal(name); }
}

class Dog extends Animal {
  speak() { return `${this.name} barks.`; }
}

async function fetchData(url) {
  try {
    const response = await fetch(url);
    return await response.json();
  } catch (error) {
    throw new Error(`Failed: ${error.message}`);
  } finally {
    console.log("done");
  }
}

for (let i = 0; i < 10; i++) {
  if (i === 3) continue;
  if (i === 7) break;
}

for (const key in obj) { }
for (const item of items) { }

let i = 0;
do { i++; } while (i < 5);

while (condition) {
  if (done) break;
}

switch (x) {
  case 1: break;
  case 2: break;
  default: break;
}

loop: for (let j = 0; j < 10; j++) {
  break loop;
}

if (x > 0) { } else if (x < 0) { } else { }

;

with (obj) { }

debugger;

const [first, ...rest] = [1, 2, 3];
const { a, b: renamed } = { a: 1, b: 2 };

class StandaloneClass {
  constructor() {}
}

const ExprClass = class {};
const NamedExprClass = class MyClass {};

export { regularFunction };
export default arrowFunction;
''',

    "typescript": '''\
import { Component, OnInit } from "@angular/core";

interface User {
  id: number;
  name: string;
  email?: string;
}

type Status = "active" | "inactive" | "pending";

enum Direction { Up = "UP", Down = "DOWN" }

function identity<T>(arg: T): T { return arg; }
function* gen(): Generator<number> { yield 1; }

const genericArrow = <T>(x: T): T => x;

abstract class Base {
  abstract method(): void;
}

@Component({ selector: "app-root", template: "<div>Hello</div>" })
class AppComponent extends Base implements OnInit {
  private readonly items: User[] = [];
  public title: string = "App";

  constructor(private service: UserService) { super(); }

  method(): void {}
  ngOnInit(): void { this.loadData(); }

  async loadData(): Promise<void> {
    const users: User[] = await this.service.getUsers();
    this.items.push(...users);
  }

  get count(): number { return this.items.length; }
}

declare module "some-module" {
  export function helper(): void;
}

for (let i = 0; i < 10; i++) {
  if (i === 3) continue;
  if (i === 7) break;
}
for (const key in obj) { }
for (const item of items) { }
let i = 0;
do { i++; } while (i < 5);
while (condition) { if (done) break; }
switch (x) { case 1: break; default: break; }
loop: for (let j = 0; j < 10; j++) { break loop; }
if (x > 0) { } else { }
;
with (obj) { }
debugger;

try {
  throw new Error("oops");
} catch (e) {
  console.error(e);
} finally {
  cleanup();
}

class StandaloneClass {
  constructor() {}
}

const ExprClass = class {};
const NamedExprClass = class MyClass {};

const v: string = "hello";
let mutable: number = 0;
var legacy = 0;

type Nullable<T> = T | null;
type Result<T, E = Error> = { ok: true; value: T } | { ok: false; error: E };

export { AppComponent, Direction };
export type { User, Status };
''',

    "java": '''\
package com.example;

import java.util.List;
import java.util.Optional;

@SuppressWarnings("unused")
public class Example {
    private static final int CONSTANT = 42;
    private final String name;
    private int value;

    public Example(String name, int value) {
        this.name = name;
        this.value = value;
    }

    @Override
    public String toString() {
        return "Example{name=" + name + "}";
    }

    public static <T> Optional<T> findFirst(List<T> items) {
        return items.stream().findFirst();
    }

    public void controlFlow(int x) {
        assert x >= 0 : "must be non-negative";
        if (x > 0) {
        } else if (x < 0) {
        } else {
        }
        for (int i = 0; i < x; i++) {
            if (i == 3) continue;
            if (i == 7) break;
        }
        for (String s : List.of("a", "b")) { }
        while (x > 0) { x--; }
        do { x++; } while (x < 5);
        switch (x) {
            case 1: break;
            default: break;
        }
        label: for (int i = 0; i < 10; i++) { break label; }
        try {
            throw new Exception("oops");
        } catch (Exception e) {
        } finally { }
        try (var res = openResource()) { }
        synchronized (this) { }
        int result = switch (x) { case 1 -> 1; default -> { yield 0; } };
    }
}

interface Processor<T, R> {
    R process(T input) throws Exception;
    default void validate(T input) { }
}

enum Status {
    ACTIVE("active"), INACTIVE("inactive");
    private final String label;
    Status(String label) { this.label = label; }
    public String getLabel() { return label; }
}

record Point(double x, double y) {
    public Point {
        assert x >= 0;
    }
}

@interface CustomAnnotation {
    String value() default "";
    int count() default 1;
}

module com.example {
    exports com.example;
}

interface WithConstants {
    int CONSTANT = 42;
    String NAME = "hello";
}
''',

    "go": '''\
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
''',

    "rust": '''\
#![allow(unused)]
use std::collections::HashMap;
use std::fmt;

extern crate serde;

const MAX_SIZE: usize = 100;
static COUNTER: std::sync::atomic::AtomicUsize = std::sync::atomic::AtomicUsize::new(0);

type Result<T> = std::result::Result<T, Error>;

#[derive(Debug, Clone, PartialEq)]
pub struct Point {
    pub x: f64,
    pub y: f64,
}

impl Point {
    pub fn new(x: f64, y: f64) -> Self {
        Self { x, y }
    }
}

impl fmt::Display for Point {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "({}, {})", self.x, self.y)
    }
}

pub trait Shape {
    fn area(&self) -> f64;
    fn describe(&self) -> String { format!("area={:.2}", self.area()) }
}

#[derive(Debug)]
pub enum Color {
    Red,
    Green,
    Custom(u8, u8, u8),
}

pub union Bits {
    as_int: u32,
    as_bytes: [u8; 4],
}

macro_rules! my_macro {
    ($x:expr) => { $x * 2 };
}

#[cfg(feature = "experimental")]
pub mod experimental {
    pub fn beta() {}
}

extern "C" {
    fn c_function(x: i32) -> i32;
}

;

pub fn process<T: Clone + fmt::Debug>(items: &[T]) -> Vec<T> {
    let result: Vec<T> = items.iter().cloned().collect();
    result
}

async fn fetch_data(url: &str) -> Result<String> {
    Ok(url.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_basic() {
        assert_eq!(my_macro!(2), 4);
    }
}
''',

    "c": '''\
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define MAX_SIZE 100
#define SQUARE(x) ((x) * (x))

typedef struct { int x; int y; } Point;
typedef enum { STATUS_OK = 0, STATUS_ERROR = 1 } Status;
typedef int (*Comparator)(const void *, const void *);

__attribute__((visibility("default")))
void attributed_func(void);

static int counter = 0;

Status process_array(int *arr, size_t len, Comparator cmp) {
    if (arr == NULL || len == 0) { return STATUS_ERROR; }

    for (size_t i = 0; i < len; i++) {
        if (arr[i] < 0) continue;
        if (arr[i] > MAX_SIZE) break;
    }

    int i = 0;
    while (i < 10) { i++; }
    do { i--; } while (i > 0);

    switch (len) {
        case 0: break;
        case 1: return STATUS_OK;
        default: break;
    }

    label_a:
    goto label_b;
    label_b: ;

    [[fallthrough]] ;
    __attribute__((unused)) int attr_var = 0;
    [[nodiscard]] int attr_stmt_var = 0;
    __try { __leave; } __finally { }

    return STATUS_OK;
}

int main(int argc, char *argv[]) {
    int nums[] = {5, 3, 1};
    process_array(nums, 3, NULL);
    return EXIT_SUCCESS;
}
''',

    "cpp": '''\
#include <iostream>
#include <vector>
#include <memory>
#include <concepts>

template<typename T>
concept Printable = requires(T t) {
    { std::cout << t } -> std::same_as<std::ostream&>;
};

template<typename T>
class Container {
public:
    friend class ContainerHelper;
    using iterator = typename std::vector<T>::iterator;
    explicit Container(size_t cap = 16) { data_.reserve(cap); }
    void push(T item) { data_.push_back(std::move(item)); }
    [[nodiscard]] size_t size() const noexcept { return data_.size(); }
    iterator begin() { return data_.begin(); }
    iterator end() { return data_.end(); }
private:
    std::vector<T> data_;
};

struct Point {
    double x, y;
    Point operator+(const Point& o) const { return {x+o.x, y+o.y}; }
    auto operator<=>(const Point&) const = default;
};

namespace alias = std::vector<int>;
namespace N = std::chrono;
using MyInt = int;
using std::string;

typedef unsigned long ulong;

static_assert(sizeof(int) == 4, "int must be 4 bytes");

template<typename T, typename... Args>
class Variadic { };

template<typename... Ts>
void variadic_func(Ts... args) { }

template<int N>
struct TemplateInt { };

class Base {
public:
    virtual ~Base() = default;
    virtual double area() const = 0;
};

class Circle final : public Base {
public:
    explicit Circle(double r) : radius_(r) {}
    double area() const override { return 3.14159 * radius_ * radius_; }
private:
    double radius_;
};

void control_flow(int x) {
    if (x > 0) { } else if (x < 0) { } else { }
    for (int i = 0; i < x; i++) {
        if (i == 3) continue;
        if (i == 7) break;
    }
    while (x > 0) { x--; }
    do { x++; } while (x < 5);
    switch (x) { case 1: break; default: break; }
    label: goto label;
    try { throw std::runtime_error("oops"); }
    catch (const std::exception& e) { }
    catch (...) { }
    __try { __leave; } __finally { }

    if (int y = x * 2; y > 10) { }

    namespace MyNS { void foo() {} }
    namespace alias2 = MyNS;

    template<template<typename> class C>
    void tmpl_tmpl_func() {}

    template<typename T = int>
    void opt_tmpl() {}

    auto coro = []() -> std::coroutine_handle<> {
        co_return;
        co_yield 1;
    };

    [[nodiscard]] int attr_stmt = 0;
    [[maybe_unused]] ;
}

int main() {
    auto circle = std::make_unique<Circle>(5.0);
    auto lambda = [](int x) -> int { return x * x; };
    std::cout << lambda(4) << "\\n";
    return 0;
}
''',

    "csharp": '''\
using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;

// Top-level statements (C# 9+ global_statement)
Console.WriteLine("global statement");
int topLevel = 42;

namespace Example;

[AttributeUsage(AttributeTargets.Class)]
public class ServiceAttribute : Attribute { public string Name { get; init; } = ""; }

public interface IRepository<T> where T : class {
    Task<T?> FindAsync(int id);
    Task<IEnumerable<T>> FindAllAsync();
}

public record Point(double X, double Y);
public enum Status { Active, Inactive, Pending }

public delegate void EventHandler(object sender, EventArgs e);

public struct ValuePoint { public int X, Y; }

[Service(Name = "UserService")]
public class UserService : IRepository<User>
{
    private readonly List<User> _users = [];
    public event EventHandler? Changed;
    public event EventHandler MyEvent { add { } remove { } }

    public async Task<User?> FindAsync(int id) {
        await Task.Delay(0);
        return _users.FirstOrDefault(u => u.Id == id);
    }

    public async Task<IEnumerable<User>> FindAllAsync() {
        await Task.Delay(0);
        return _users.AsEnumerable();
    }

    ~UserService() { }

    public int this[int index] { get => _users[index].Id; }

    public void ControlFlow(int x) {
        if (x > 0) { } else if (x < 0) { } else { }
        for (int i = 0; i < x; i++) { if (i==3) continue; if (i==7) break; }
        foreach (var u in _users) { }
        while (x > 0) { x--; }
        do { x++; } while (x < 5);
        switch (x) { case 1: break; default: break; }
        label: goto label;
        try { throw new Exception(); }
        catch (ArgumentException e) when (e != null) { }
        catch (Exception) { }
        finally { }
        checked { int y = x + 1; }
        unsafe { int* p = &x; }
        lock (this) { }
        using var res = new System.IO.MemoryStream();
        fixed (char* p = "hello") { }
        int result = x switch { 1 => 1, _ => 0 };
        yield return x;
        yield break;
        int local = 0;
        void LocalFn() { local++; }
        LocalFn();
    }

}

namespace Example.Sub
{
    public class SubClass
    {
        public SubClass() { }

        public event EventHandler? MyEvent;

        public void GlobalAndUsing()
        {
            ;
            using var r = new System.IO.MemoryStream();
            using (var r2 = new System.IO.MemoryStream()) { }
        }
    }

    global using System.Collections.Generic;
}

public class User
{
    public int Id { get; set; }
    public required string Name { get; set; }
    public string? Email { get; set; }
    public override string ToString() => $"User({Id}, {Name})";
}
''',

    "ruby": '''\
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
  def secret; "shhh"; end
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
''',

    "php": '''\
<?php
declare(strict_types=1);
namespace App\\Controllers;
use App\\Models\\User;
use App\\Services\\UserService;

const MAX_ITEMS = 100;

interface Repository {
    public function find(int $id): ?User;
    public function findAll(): array;
}

#[\\Attribute(\\Attribute::TARGET_CLASS)]
class Controller {
    public function __construct(public readonly string $prefix = "") {}
}

#[Controller(prefix: "/users")]
class UserController {
    public function __construct(
        private readonly UserService $service,
        private readonly int $maxItems = MAX_ITEMS
    ) {}

    public function show(int $id): ?User { return $this->service->find($id); }
    public static function create(UserService $s): static { return new static($s); }

    public function controlFlow(int $x): void {
        if ($x > 0) { } elseif ($x < 0) { } else { }
        for ($i = 0; $i < $x; $i++) { if ($i==3) continue; if ($i==7) break; }
        foreach ($this->service->findAll() as $item) { }
        while ($x > 0) { $x--; }
        do { $x++; } while ($x < 5);
        switch ($x) { case 1: break; default: break; }
        label_a: goto label_a;
        try { throw new \\Exception(); }
        catch (\\Exception $e) { } finally { }
        echo "hello";
        exit(0);
        unset($x);
        global $globalVar;
        static $staticVar = 0;
        ;
        use \\Some\\Namespace\\ClassName;
    }

    public function funcDef(): void { function inner() {} }
}

trait Timestampable {
    private \\DateTimeImmutable $createdAt;
    public function getCreatedAt(): \\DateTimeImmutable { return $this->createdAt; }
}

class WithTraits {
    use Timestampable;
}

enum Status: string {
    case Active = "active";
    case Inactive = "inactive";
    public function label(): string {
        return match($this) { Status::Active => "Active", default => "Inactive" };
    }
}

$items = array_filter(array_map(fn($x) => $x * 2, range(1, 10)), fn($x) => $x > 10);
''',

    "kotlin": '''\
package com.example

import kotlinx.coroutines.*

const val MAX_RETRIES = 3

data class Point(val x: Double, val y: Double) {
    operator fun plus(other: Point) = Point(x + other.x, y + other.y)
}

sealed class Result<out T> {
    data class Success<T>(val value: T) : Result<T>()
    data class Error(val message: String) : Result<Nothing>()
}

interface Repository<T> {
    suspend fun find(id: Int): T?
    suspend fun findAll(): List<T>
}

enum class Status(val label: String) {
    ACTIVE("active"), INACTIVE("inactive"), PENDING("pending");
    fun isActive() = this == ACTIVE
}

annotation class Service(val name: String = "")

object Singleton { val value = 42 }

@Service(name = "UserService")
class UserService : Repository<User> {
    private val users = mutableListOf<User>()
    val (first, second) = Pair(1, 2)

    override suspend fun find(id: Int): User? = users.firstOrNull { it.id == id }
    override suspend fun findAll(): List<User> = users.toList()

    fun controlFlow(x: Int) {
        if (x > 0) { } else if (x < 0) { } else { }
        for (i in 0..x) { if (i == 3) continue; if (i == 7) break }
        while (x > 0) { }
        do { } while (false)
        when (x) { 1 -> println("one"); else -> println("other") }
    }
}

data class User(val id: Int, val name: String, val email: String? = null)

typealias UserList = List<User>
typealias Predicate<T> = (T) -> Boolean

suspend fun main() {
    val service = UserService()
    coroutineScope {
        launch { service.findAll() }
        async { service.findAll() }.await()
    }
}
''',

    "yaml": '''\
---
name: my-application
version: "1.0.0"
description: A sample application

settings:
  debug: false
  log_level: info
  max_retries: 3
  timeout: 30.0

database:
  host: localhost
  port: 5432
  name: mydb
  credentials:
    username: admin
    password: secret

services:
  - name: web
    image: nginx:latest
    ports:
      - "80:80"
      - "443:443"
    environment:
      NODE_ENV: production
      API_URL: https://api.example.com
    volumes:
      - ./config:/etc/nginx/conf.d

  - name: worker
    image: python:3.11
    command: ["python", "-m", "worker"]
    replicas: 2

tags:
  - production
  - stable

metadata:
  created_at: "2026-01-01"
  owner: devops-team
  labels:
    app: myapp
    tier: backend
''',

    "sql": '''\
-- Create tables
CREATE TABLE users (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(255) NOT NULL,
    email       VARCHAR(255) UNIQUE NOT NULL,
    created_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    status      VARCHAR(50) DEFAULT "active"
);

CREATE TABLE orders (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    total       DECIMAL(10, 2) NOT NULL,
    created_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_orders_user_id ON orders(user_id);

-- Insert data
INSERT INTO users (name, email) VALUES
    ("Alice", "alice@example.com"),
    ("Bob", "bob@example.com");

-- Queries
SELECT
    u.id,
    u.name,
    COUNT(o.id) AS order_count,
    SUM(o.total) AS total_spent
FROM users u
LEFT JOIN orders o ON o.user_id = u.id
WHERE u.status = "active"
GROUP BY u.id, u.name
HAVING COUNT(o.id) > 0
ORDER BY total_spent DESC
LIMIT 10;

-- Subquery
SELECT name FROM users
WHERE id IN (
    SELECT DISTINCT user_id FROM orders
    WHERE total > 100
);

-- CTE
WITH active_users AS (
    SELECT id, name FROM users WHERE status = "active"
),
ranked AS (
    SELECT *, ROW_NUMBER() OVER (ORDER BY name) AS rn
    FROM active_users
)
SELECT * FROM ranked WHERE rn <= 5;

-- Update & Delete
UPDATE users SET status = "inactive" WHERE created_at < NOW() - INTERVAL "1 year";
DELETE FROM orders WHERE user_id NOT IN (SELECT id FROM users);

-- View
CREATE VIEW user_summary AS
SELECT u.name, COUNT(o.id) AS orders FROM users u
LEFT JOIN orders o ON o.user_id = u.id
GROUP BY u.name;
''',
}

# 额外的字节级 corpus（用于需要非 UTF-8 或特殊语法的场景）
# key: 语言名，value: bytes 列表（每项是一段独立代码）
# 这些片段由 auto_discovery._collect_node_stats 追加解析，与 BUILTIN_CORPUS 合并。
BUILTIN_CORPUS_EXTRA: dict[str, list[bytes]] = {
    # Python 2 遗留语句：tree-sitter-python grammar 包含 exec_statement /
    # print_statement 以支持 Python 2 代码分析。
    # Python 3 解释器无法执行这些语法，但 tree-sitter 解析器可以正常识别。
    "python": [
        b'exec "import os"\n',
        b'print "hello"\n',
        b'print "a", "b"\n',
    ],
}

# 语言名到文件扩展名的映射（用于 CLI 显示）
LANGUAGE_EXTENSIONS: dict[str, str] = {
    "python": "py",
    "javascript": "js",
    "typescript": "ts",
    "java": "java",
    "go": "go",
    "rust": "rs",
    "c": "c",
    "cpp": "cpp",
    "csharp": "cs",
    "ruby": "rb",
    "php": "php",
    "kotlin": "kt",
    "yaml": "yaml",
    "sql": "sql",
}

# 分析目标语言列表（仅包含有 corpus 且有安装包的语言）
TARGET_LANGUAGES: list[str] = list(BUILTIN_CORPUS.keys())
