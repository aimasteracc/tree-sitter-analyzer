/**
 * エッジケース用JavaScriptファイル
 * 特殊な構文や境界条件をテストするためのサンプル
 */

// 空の関数
function emptyFunction() {}

// 単一行の関数
const singleLineFunction = () => 42;

// 非常に長い関数名
function thisIsAVeryLongFunctionNameThatMightCauseIssuesWithSomeAnalyzers() {
    return "long name function";
}

// Unicode文字を含む変数名
const 変数名 = "日本語変数";
const αβγ = "ギリシャ文字";
const 🚀rocket = "絵文字変数";

// 特殊文字を含む文字列
const specialStrings = [
    "改行を含む\n文字列",
    "タブを含む\t文字列",
    "引用符を含む\"文字列",
    "バックスラッシュを含む\\文字列",
    `テンプレート
    リテラル`,
    /正規表現/g
];

// ネストした構造
const deeplyNested = {
    level1: {
        level2: {
            level3: {
                level4: {
                    level5: "deep value"
                }
            }
        }
    }
};

// 複雑な分割代入
const [a, [b, c], ...rest] = [1, [2, 3], 4, 5, 6];
const {x: {y: z}} = {x: {y: "nested destructuring"}};

// 即座に実行される関数式 (IIFE)
(function() {
    console.log("IIFE executed");
})();

// アロー関数の様々な形式
const arrow1 = x => x;
const arrow2 = (x, y) => x + y;
const arrow3 = x => {
    return x * 2;
};
const arrow4 = () => ({key: "value"});

// 非同期関数
async function asyncFunction() {
    await new Promise(resolve => setTimeout(resolve, 1));
    return "async result";
}

// ジェネレーター関数
function* generatorFunction() {
    yield 1;
    yield 2;
    yield 3;
}

// クラスの継承
class Parent {
    constructor(name) {
        this.name = name;
    }
    
    parentMethod() {
        return `Parent: ${this.name}`;
    }
}

class Child extends Parent {
    constructor(name, age) {
        super(name);
        this.age = age;
    }
    
    childMethod() {
        return `Child: ${this.name}, ${this.age}`;
    }
}

// プライベートフィールド
class PrivateFieldClass {
    #privateField = "private";
    
    getPrivate() {
        return this.#privateField;
    }
}

// 動的インポート
async function dynamicImport() {
    const module = await import('./some-module.js');
    return module.default;
}

// try-catch-finally
function errorHandling() {
    try {
        throw new Error("test error");
    } catch (e) {
        console.error(e.message);
    } finally {
        console.log("cleanup");
    }
}

// switch文
function switchStatement(value) {
    switch (value) {
        case 1:
            return "one";
        case 2:
        case 3:
            return "two or three";
        default:
            return "other";
    }
}

// 複雑な正規表現
const complexRegex = /^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$/;

// WeakMap, WeakSet
const weakMap = new WeakMap();
const weakSet = new WeakSet();

// Symbol
const sym1 = Symbol();
const sym2 = Symbol('description');

// BigInt
const bigInt = 123456789012345678901234567890n;

// Proxy
const proxy = new Proxy({}, {
    get(target, prop) {
        return `Property ${prop} accessed`;
    }
});

// 複雑なオブジェクト
const complexObject = {
    // 計算されたプロパティ名
    [Symbol.iterator]: function*() {
        yield 1;
        yield 2;
    },
    
    // メソッド定義
    method() {
        return "method result";
    },
    
    // getter/setter
    get computed() {
        return this._computed || 0;
    },
    
    set computed(value) {
        this._computed = value;
    }
};

// 分割代入のデフォルト値
function destructuringDefaults({a = 1, b = 2} = {}) {
    return a + b;
}

// 残余パラメータ
function restParameters(first, ...rest) {
    return [first, rest];
}

// 末尾のコンマ
const arrayWithTrailingComma = [
    1,
    2,
    3,
];

const objectWithTrailingComma = {
    a: 1,
    b: 2,
    c: 3,
};

// エクスポート（モジュール）
export { emptyFunction, singleLineFunction };
export default complexObject;