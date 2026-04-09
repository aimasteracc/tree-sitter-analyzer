/**
 * JavaScript Golden Corpus - Grammar Coverage MECE Test
 *
 * This file contains all key node types from tree-sitter-javascript grammar
 * to verify complete coverage of JavaScript language features.
 *
 * Coverage includes:
 * - Function declarations (regular, async, generator, async generator)
 * - Arrow functions (sync, async)
 * - Classes (declaration, expression, with inheritance)
 * - Methods (regular, static, async, getter, setter, constructor)
 * - Variables (var, let, const)
 * - Imports (ES6 named, default, namespace, dynamic)
 * - Exports (ES6 named, default, re-export)
 * - Modern ES6+ syntax (destructuring, spread, template literals)
 */

// ============================================================================
// Function Declarations
// ============================================================================

/**
 * Regular function declaration
 */
function regularFunction(param1, param2) {
    return param1 + param2;
}

/**
 * Async function declaration
 */
async function asyncFunction(url) {
    const response = await fetch(url);
    return response.json();
}

/**
 * Generator function declaration
 */
function* generatorFunction() {
    yield 1;
    yield 2;
    yield 3;
}

/**
 * Async generator function declaration
 */
async function* asyncGeneratorFunction() {
    yield await Promise.resolve(1);
    yield await Promise.resolve(2);
}

// ============================================================================
// Arrow Functions
// ============================================================================

/**
 * Arrow function with single parameter (no parentheses)
 */
const singleParamArrow = x => x * 2;

/**
 * Arrow function with multiple parameters
 */
const multiParamArrow = (a, b) => a + b;

/**
 * Arrow function with block body
 */
const blockBodyArrow = (x) => {
    const result = x * 2;
    return result;
};

/**
 * Async arrow function
 */
const asyncArrow = async (url) => {
    const data = await fetch(url);
    return data;
};

// ============================================================================
// Function Expressions
// ============================================================================

/**
 * Named function expression
 */
const namedFuncExpr = function namedExpression(x) {
    return x + 1;
};

/**
 * Anonymous function expression
 */
const anonFuncExpr = function(x) {
    return x - 1;
};

// ============================================================================
// Classes
// ============================================================================

/**
 * Class declaration with all method types
 */
class BaseClass {
    // Constructor
    constructor(name) {
        this.name = name;
        this._privateValue = 0;
    }

    // Regular method
    regularMethod() {
        return this.name;
    }

    // Static method
    static staticMethod() {
        return "static";
    }

    // Async method
    async asyncMethod() {
        const result = await Promise.resolve("async");
        return result;
    }

    // Getter
    get value() {
        return this._privateValue;
    }

    // Setter
    set value(newValue) {
        this._privateValue = newValue;
    }

    // Generator method
    *generatorMethod() {
        yield 1;
        yield 2;
    }

    // Async generator method
    async *asyncGeneratorMethod() {
        yield await Promise.resolve(1);
    }
}

/**
 * Class declaration with inheritance
 */
class DerivedClass extends BaseClass {
    constructor(name, extra) {
        super(name);
        this.extra = extra;
    }

    // Override method
    regularMethod() {
        return super.regularMethod() + " extended";
    }
}

/**
 * Class expression
 */
const ClassExpression = class {
    constructor(x) {
        this.x = x;
    }

    method() {
        return this.x;
    }
};

// ============================================================================
// Variables
// ============================================================================

// var declarations
var varDeclaration = "var";
var multiVar1 = 1, multiVar2 = 2;

// let declarations
let letDeclaration = "let";
let multiLet1 = 1, multiLet2 = 2;

// const declarations
const constDeclaration = "const";
const constObject = { key: "value" };
const constArray = [1, 2, 3];

// Destructuring declarations
const { destructuredProp1, destructuredProp2 } = { destructuredProp1: 1, destructuredProp2: 2 };
const [arrayItem1, arrayItem2] = [1, 2];
let { nestedObj: { nestedProp } } = { nestedObj: { nestedProp: "nested" } };

// ============================================================================
// Imports (ES6 Modules)
// ============================================================================

// Default import
import defaultExport from './module1.js';

// Named imports
import { namedExport1, namedExport2 } from './module2.js';

// Namespace import
import * as namespace from './module3.js';

// Mixed import (default + named)
import defaultMixed, { namedMixed1, namedMixed2 } from './module4.js';

// Import with alias
import { originalName as aliasName } from './module5.js';

// Side-effect import
import './module6.js';

// ============================================================================
// Exports (ES6 Modules)
// ============================================================================

// Named export declaration
export const exportedConst = "exported";
export let exportedLet = "exported let";
export var exportedVar = "exported var";

// Export function
export function exportedFunction() {
    return "exported";
}

// Export class
export class ExportedClass {
    constructor() {
        this.exported = true;
    }
}

// Export list
const toExport1 = 1;
const toExport2 = 2;
export { toExport1, toExport2 };

// Export with alias
const internal = "internal";
export { internal as external };

// Re-export from another module
export { reexported1, reexported2 } from './module7.js';
export * from './module8.js';

// Default export (function)
export default function defaultExportFunc() {
    return "default";
}

// ============================================================================
// Template Literals
// ============================================================================

const templateBasic = `basic template`;
const templateWithExpr = `expression: ${1 + 1}`;
const templateMultiline = `
    line 1
    line 2
`;
const templateNested = `outer ${`inner ${1}`}`;

// Tagged template literal
function tag(strings, ...values) {
    return strings[0] + values[0];
}
const tagged = tag`value: ${42}`;

// ============================================================================
// Object Methods
// ============================================================================

const objectWithMethods = {
    // Method shorthand
    methodShorthand() {
        return "shorthand";
    },

    // Async method
    async asyncObjectMethod() {
        return await Promise.resolve("async");
    },

    // Generator method
    *generatorObjectMethod() {
        yield 1;
    },

    // Getter
    get objectGetter() {
        return this._value;
    },

    // Setter
    set objectSetter(val) {
        this._value = val;
    },

    // Computed property name
    ["computed" + "Key"]() {
        return "computed";
    }
};

// ============================================================================
// Modern JavaScript Features
// ============================================================================

// Spread operator in array
const spreadArray = [...[1, 2], 3];

// Spread operator in object
const spreadObject = { ...{ a: 1 }, b: 2 };

// Rest parameters
function restParams(...args) {
    return args.length;
}

// Default parameters
function defaultParams(x = 10, y = 20) {
    return x + y;
}

// Optional chaining
const optionalChain = constObject?.key?.nested;

// Nullish coalescing
const nullishCoalesce = null ?? "default";

// ============================================================================
// Dynamic Import
// ============================================================================

// Dynamic import (import() expression)
async function dynamicImportExample() {
    const module = await import('./dynamic-module.js');
    return module.default;
}

// ============================================================================
// CommonJS (for compatibility testing)
// ============================================================================

// Note: These are in a separate scope to avoid conflicts with ES6 modules
// In real code, you wouldn't mix CommonJS and ES6 modules in the same file

/*
// CommonJS require
const commonjsModule = require('./commonjs-module.js');

// CommonJS exports
module.exports = {
    exported: true
};

// CommonJS named export
exports.namedExport = function() {
    return "named";
};
*/

// ============================================================================
// JSX (if supported by parser)
// ============================================================================

/*
// React functional component
function ReactComponent({ prop1, prop2 }) {
    return (
        <div className="container">
            <h1>{prop1}</h1>
            <p>{prop2}</p>
        </div>
    );
}

// React class component
class ReactClassComponent extends React.Component {
    constructor(props) {
        super(props);
        this.state = { count: 0 };
    }

    render() {
        return <div>{this.state.count}</div>;
    }
}

// JSX self-closing element
const jsxSelfClosing = <input type="text" />;

// JSX fragment
const jsxFragment = (
    <>
        <div>Item 1</div>
        <div>Item 2</div>
    </>
);
*/

// ============================================================================
// End of Golden Corpus
// ============================================================================
