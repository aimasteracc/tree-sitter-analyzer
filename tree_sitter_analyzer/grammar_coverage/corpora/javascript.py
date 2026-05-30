"""Built-in JavaScript corpus for grammar coverage auto-discovery."""

CORPUS: str = """\
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
"""
