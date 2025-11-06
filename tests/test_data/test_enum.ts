// TypeScript enum test

enum Color {
    Red = "RED",
    Green = "GREEN",
    Blue = "BLUE"
}

enum Status {
    Active = 1,
    Inactive = 0,
    Pending = 2
}

// Enum with methods (TypeScript allows this via namespace merging)
enum MathConstants {
    PI = 3.14159,
    E = 2.71828
}

namespace MathConstants {
    export function getPrecision(): number {
        return 5;
    }
}

// Interface test
interface Person {
    name: string;
    age: number;
    greet(): void;
}

// Type alias test
type Point = {
    x: number;
    y: number;
}

// Class test
class User implements Person {
    constructor(public name: string, public age: number) {}

    greet(): void {
        console.log(`Hello, ${this.name}`);
    }
}
