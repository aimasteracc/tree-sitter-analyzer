"""Built-in TypeScript corpus for grammar coverage auto-discovery."""

CORPUS: str = """\
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
"""
