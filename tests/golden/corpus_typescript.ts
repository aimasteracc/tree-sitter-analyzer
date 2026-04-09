/**
 * TypeScript Golden Corpus - Grammar Coverage MECE Test
 *
 * This file contains all key node types from tree-sitter-typescript grammar
 * to verify complete coverage of TypeScript language features.
 *
 * Coverage includes:
 * - Function declarations (regular, async, generator, async generator)
 * - Arrow functions (sync, async, typed)
 * - Classes (declaration, expression, with inheritance, abstract)
 * - Methods (regular, static, async, getter, setter, constructor, abstract)
 * - Type annotations (primitive, union, intersection, generic)
 * - Interfaces and type aliases
 * - Enums and namespaces
 * - Import/export with types
 * - Decorators (experimental)
 * - Modern TypeScript features (satisfies, as const, etc.)
 */

// ============================================================================
// Type Definitions
// ============================================================================

/**
 * Type alias declaration
 */
type StringOrNumber = string | number;
type Point = { x: number; y: number };
type Predicate<T> = (value: T) => boolean;
type ReadonlyPoint = Readonly<Point>;

/**
 * Interface declaration
 */
interface Animal {
    name: string;
    age: number;
    makeSound(): string;
}

/**
 * Interface with generics
 */
interface Container<T> {
    value: T;
    getValue(): T;
    setValue(value: T): void;
}

/**
 * Interface with index signature
 */
interface Dictionary {
    [key: string]: string | number;
}

/**
 * Interface with call signature
 */
interface Callable {
    (arg: string): number;
}

/**
 * Interface extension
 */
interface Dog extends Animal {
    breed: string;
    fetch(item: string): void;
}

/**
 * Intersection type
 */
type DogWithOwner = Dog & { owner: string };

/**
 * Union type
 */
type Result = { success: true; data: string } | { success: false; error: string };

// ============================================================================
// Enum Declarations
// ============================================================================

/**
 * Regular enum
 */
enum Direction {
    North,
    South,
    East,
    West
}

/**
 * String enum
 */
enum Color {
    Red = "RED",
    Green = "GREEN",
    Blue = "BLUE"
}

/**
 * Const enum
 */
const enum HttpStatus {
    OK = 200,
    NotFound = 404,
    ServerError = 500
}

// ============================================================================
// Function Declarations
// ============================================================================

/**
 * Regular function with type annotations
 */
function add(a: number, b: number): number {
    return a + b;
}

/**
 * Function with optional and default parameters
 */
function greet(name: string, greeting: string = "Hello", punctuation?: string): string {
    return `${greeting}, ${name}${punctuation || "!"}`;
}

/**
 * Function with rest parameters
 */
function sum(...numbers: number[]): number {
    return numbers.reduce((acc, n) => acc + n, 0);
}

/**
 * Generic function
 */
function identity<T>(value: T): T {
    return value;
}

/**
 * Function with multiple generic parameters
 */
function pair<T, U>(first: T, second: U): [T, U] {
    return [first, second];
}

/**
 * Async function
 */
async function fetchData(url: string): Promise<any> {
    const response = await fetch(url);
    return response.json();
}

/**
 * Generator function
 */
function* numberGenerator(max: number): Generator<number> {
    for (let i = 0; i < max; i++) {
        yield i;
    }
}

/**
 * Async generator function
 */
async function* asyncNumberGenerator(max: number): AsyncGenerator<number> {
    for (let i = 0; i < max; i++) {
        yield await Promise.resolve(i);
    }
}

/**
 * Function overloads
 */
function process(value: string): string;
function process(value: number): number;
function process(value: string | number): string | number {
    return typeof value === "string" ? value.toUpperCase() : value * 2;
}

// ============================================================================
// Arrow Functions
// ============================================================================

/**
 * Arrow function with type annotation
 */
const multiply = (a: number, b: number): number => a * b;

/**
 * Arrow function with generic type
 */
const wrapInArray = <T>(value: T): T[] => [value];

/**
 * Async arrow function
 */
const asyncFetch = async (url: string): Promise<Response> => {
    return await fetch(url);
};

/**
 * Arrow function with destructured parameters
 */
const getFullName = ({ firstName, lastName }: { firstName: string; lastName: string }): string => {
    return `${firstName} ${lastName}`;
};

// ============================================================================
// Classes
// ============================================================================

/**
 * Class with all member types
 */
class Person {
    // Public field
    public name: string;

    // Private field
    private _age: number;

    // Protected field
    protected email: string;

    // Readonly field
    readonly id: number;

    // Static field
    static species: string = "Homo sapiens";

    // Constructor
    constructor(name: string, age: number, email: string) {
        this.name = name;
        this._age = age;
        this.email = email;
        this.id = Math.random();
    }

    // Regular method
    greet(): string {
        return `Hello, I'm ${this.name}`;
    }

    // Getter
    get age(): number {
        return this._age;
    }

    // Setter
    set age(value: number) {
        if (value < 0) throw new Error("Age cannot be negative");
        this._age = value;
    }

    // Static method
    static getSpecies(): string {
        return Person.species;
    }

    // Async method
    async fetchProfile(): Promise<any> {
        return await fetchData(`/api/profile/${this.id}`);
    }

    // Private method
    private validateEmail(): boolean {
        return this.email.includes("@");
    }

    // Protected method
    protected sendNotification(message: string): void {
        console.log(`Sending to ${this.email}: ${message}`);
    }
}

/**
 * Class with generics
 */
class Box<T> {
    private value: T;

    constructor(value: T) {
        this.value = value;
    }

    getValue(): T {
        return this.value;
    }

    setValue(value: T): void {
        this.value = value;
    }
}

/**
 * Abstract class
 */
abstract class Shape {
    abstract area(): number;
    abstract perimeter(): number;

    describe(): string {
        return `Area: ${this.area()}, Perimeter: ${this.perimeter()}`;
    }
}

/**
 * Class extending abstract class
 */
class Circle extends Shape {
    constructor(private radius: number) {
        super();
    }

    area(): number {
        return Math.PI * this.radius ** 2;
    }

    perimeter(): number {
        return 2 * Math.PI * this.radius;
    }
}

/**
 * Class implementing interface
 */
class MyDog implements Dog {
    name: string;
    age: number;
    breed: string;

    constructor(name: string, age: number, breed: string) {
        this.name = name;
        this.age = age;
        this.breed = breed;
    }

    makeSound(): string {
        return "Woof!";
    }

    fetch(item: string): void {
        console.log(`${this.name} fetched ${item}`);
    }
}

// ============================================================================
// Decorators (Experimental)
// ============================================================================

/**
 * Class decorator
 */
function sealed(constructor: Function) {
    Object.seal(constructor);
    Object.seal(constructor.prototype);
}

/**
 * Method decorator
 */
function log(target: any, propertyKey: string, descriptor: PropertyDescriptor) {
    const originalMethod = descriptor.value;
    descriptor.value = function(...args: any[]) {
        console.log(`Calling ${propertyKey} with`, args);
        return originalMethod.apply(this, args);
    };
    return descriptor;
}

/**
 * Property decorator
 */
function required(target: any, propertyKey: string) {
    // Implementation
}

/**
 * Decorated class
 */
@sealed
class DecoratedClass {
    @required
    name: string = "";

    @log
    greet(greeting: string): string {
        return `${greeting}, ${this.name}`;
    }
}

// ============================================================================
// Import/Export Statements
// ============================================================================

// Type-only imports
import type { SomeType } from "./types";
import type * as Types from "./all-types";

// Regular imports
import { something } from "./module";
import * as Utils from "./utils";
import defaultExport from "./default";

// Import with type and value
import { type TypeImport, valueImport } from "./mixed";

// Export declarations
export const exportedConst: number = 42;
export let exportedLet: string = "exported";

export function exportedFunction(x: number): number {
    return x * 2;
}

export class ExportedClass {
    value: number = 0;
}

// Type-only exports
export type ExportedType = { field: string };
export interface ExportedInterface {
    method(): void;
}

// Re-exports
export { something as renamedExport } from "./module";
export type { SomeType as RenamedType } from "./types";

// Default export
export default class DefaultExport {
    constructor() {}
}

// ============================================================================
// Namespace Declaration
// ============================================================================

namespace Utilities {
    export function helper(): void {
        console.log("Helper function");
    }

    export class HelperClass {
        value: number = 0;
    }

    export namespace Nested {
        export function nestedHelper(): void {
            console.log("Nested helper");
        }
    }
}

// ============================================================================
// Module Augmentation
// ============================================================================

declare global {
    interface Window {
        customProperty: string;
    }
}

// ============================================================================
// Type Guards and Assertions
// ============================================================================

/**
 * Type guard function
 */
function isString(value: unknown): value is string {
    return typeof value === "string";
}

/**
 * Type assertion
 */
const someValue: unknown = "hello";
const strValue = someValue as string;
const strValue2 = <string>someValue;

// ============================================================================
// Advanced Types
// ============================================================================

/**
 * Conditional type
 */
type IsString<T> = T extends string ? true : false;

/**
 * Mapped type
 */
type Optional<T> = {
    [P in keyof T]?: T[P];
};

/**
 * Template literal type
 */
type Greeting = `Hello ${string}`;
type Direction2D = `${"top" | "bottom"}-${"left" | "right"}`;

/**
 * Utility types usage
 */
type PartialPerson = Partial<Person>;
type RequiredPerson = Required<Person>;
type PickedPerson = Pick<Person, "name" | "email">;
type OmittedPerson = Omit<Person, "id">;

// ============================================================================
// Variable Declarations with Types
// ============================================================================

// Const declarations
const constNumber: number = 42;
const constString: string = "hello";
const constArray: number[] = [1, 2, 3];
const constTuple: [string, number] = ["age", 30];
const constObject: Point = { x: 10, y: 20 };

// Let declarations
let letNumber: number = 100;
let letString: string = "world";
let letUnion: string | number = "text";

// Var declarations (legacy)
var varNumber: number = 999;

// Type inference
const inferred = "inferred string"; // type is inferred as string literal "inferred string"

// As const assertion
const asConstObject = { x: 10, y: 20 } as const;
const asConstArray = [1, 2, 3] as const;

// Satisfies operator (TypeScript 4.9+)
const config = {
    host: "localhost",
    port: 8080
} satisfies Record<string, string | number>;

// Non-null assertion
const maybeNull: string | null = "value";
const definitelyNotNull = maybeNull!;

// ============================================================================
// Generic Constraints
// ============================================================================

/**
 * Generic with constraint
 */
function getLength<T extends { length: number }>(value: T): number {
    return value.length;
}

/**
 * Multiple generic constraints
 */
function merge<T extends object, U extends object>(obj1: T, obj2: U): T & U {
    return { ...obj1, ...obj2 };
}

// ============================================================================
// Async/Await Pattern
// ============================================================================

async function complexAsyncOperation(): Promise<Result> {
    try {
        const data = await fetchData("/api/data");
        return { success: true, data: JSON.stringify(data) };
    } catch (error) {
        return { success: false, error: String(error) };
    }
}

// ============================================================================
// Object and Array Destructuring
// ============================================================================

// Object destructuring with types
const { name: personName, age: personAge }: { name: string; age: number } = { name: "John", age: 30 };

// Array destructuring with types
const [first, second]: [number, number] = [1, 2];

// Rest in destructuring
const { x, ...rest }: { x: number; y: number; z: number } = { x: 1, y: 2, z: 3 };

// ============================================================================
// This Type
// ============================================================================

interface Counter {
    count: number;
    increment(this: Counter): void;
}

const counter: Counter = {
    count: 0,
    increment(this: Counter) {
        this.count++;
    }
};

// ============================================================================
// Index Access Types
// ============================================================================

type PersonName = Person["name"]; // string
type PersonKeys = keyof Person; // "name" | "age" | "email" | ...

// ============================================================================
// End of Golden Corpus
// ============================================================================
