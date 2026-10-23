"""Java / TypeScript 已知答案用例（#1740 / #1743 / #1762 / #1764 / #1766 / #1768 / #1769）。"""

from __future__ import annotations

from tests.known_answer.cases import Case

# #1740（gson 形态）+ #1743：转型接收者无法绑定；声明类型的字段 / 形参可以绑定。
GSON_DELEGATE = Case(
    case_id="java-1740-1743-cast-and-typed-receivers",
    issue="#1740 #1743",
    target_name="getDelegateAdapter",
    owner="Gson",
    files={
        "src/com/google/gson/Gson.java": (
            "package com.google.gson;\n\n"
            "public final class Gson {\n"
            "  public Object getDelegateAdapter(Object skipPast, Object type) {  // target\n"
            "    return null;\n"
            "  }\n"
            "}\n"
        ),
        "src/com/google/gson/internal/Excluder.java": (
            "package com.google.gson.internal;\n\n"
            "import com.google.gson.Gson;\n\n"
            "public final class Excluder {\n"
            "  private final Gson gson;\n\n"
            "  public Excluder(Gson gson) {\n"
            "    this.gson = gson;\n"
            "  }\n\n"
            "  public Object create(Object holder, Object type) {\n"
            "    return ((Gson) holder).getDelegateAdapter(null, type);  // gt\n"
            "  }\n\n"
            "  public Object viaField(Object type) {\n"
            "    return gson.getDelegateAdapter(this, type);  // gt listed\n"
            "  }\n\n"
            "  public Object viaParam(Gson other, Object type) {\n"
            "    return other.getDelegateAdapter(this, type);  // gt listed\n"
            "  }\n"
            "}\n"
        ),
    },
)

# #1743：经父类 / 接口接收者的虚分派调用是覆盖方法的可能调用方。
VIRTUAL_DISPATCH = Case(
    case_id="java-1743-supertype-receiver-virtual-dispatch",
    issue="#1743",
    target_name="write",
    owner="FooAdapter",
    files={
        "src/a/TypeAdapter.java": (
            "package a;\n\n"
            "public abstract class TypeAdapter<T> {\n"
            "  public abstract void write(Object out, T value);\n"
            "}\n"
        ),
        "src/a/FooAdapter.java": (
            "package a;\n\n"
            "public final class FooAdapter extends TypeAdapter<String> {\n"
            "  @Override\n"
            "  public void write(Object out, String value) {  // target\n"
            "  }\n"
            "}\n"
        ),
        "src/a/Writer.java": (
            "package a;\n\n"
            "public final class Writer {\n"
            "  public void emit(TypeAdapter<String> adapter, Object out) {\n"
            '    adapter.write(out, "x");  // gt\n'
            "  }\n\n"
            "  public void direct(FooAdapter foo, Object out) {\n"
            '    foo.write(out, "y");  // gt listed\n'
            "  }\n"
            "}\n"
        ),
    },
)

INTERFACE_DISPATCH = Case(
    case_id="java-1743-interface-receiver",
    issue="#1743",
    target_name="accept",
    owner="FileSink",
    files={
        "src/b/Sink.java": "package b;\n\npublic interface Sink {\n  void accept(String line);\n}\n",
        "src/b/FileSink.java": (
            "package b;\n\n"
            "public final class FileSink implements Sink {\n"
            "  @Override\n"
            "  public void accept(String line) {  // target\n"
            "  }\n"
            "}\n"
        ),
        "src/b/Pump.java": (
            "package b;\n\n"
            "public final class Pump {\n"
            "  private final Sink sink;\n\n"
            "  public Pump(Sink sink) {\n"
            "    this.sink = sink;\n"
            "  }\n\n"
            "  public void run() {\n"
            '    sink.accept("a");  // gt\n'
            "  }\n"
            "}\n"
        ),
    },
)

# #1762（zod ``ZodType."~validate"``）：字符串字面量下标调用 ``this["~validate"](data)``。
ELEMENT_ACCESS = Case(
    case_id="ts-1762-string-literal-element-access",
    issue="#1762",
    target_name='"~validate"',
    owner="ZodType",
    files={
        "src/types.ts": (
            "export class ZodType {\n"
            "  standard: { validate: (data: unknown) => unknown };\n"
            "  constructor() {\n"
            "    this.standard = {\n"
            '      validate: (data: unknown) => this["~validate"](data),  // gt listed\n'
            "    };\n"
            "  }\n"
            '  "~validate"(data: unknown): unknown {  // target\n'
            "    return data;\n"
            "  }\n"
            "}\n"
        ),
    },
)

# #1763 / #1766（hono ``cors``）：箭头函数常量是定义；内层同名函数不能抢走外部调用方。
ARROW_CONST = Case(
    case_id="ts-1766-arrow-const-false-callers",
    issue="#1763 #1766",
    target_name="cors",
    owner=None,
    files={
        "src/cors.ts": (
            "export const cors = (origin?: string) => {  // target\n"
            "  return async function cors(c: string, next: string) {\n"
            "    return `${origin}${c}${next}`;\n"
            "  };\n"
            "};\n"
        ),
        "src/app.ts": (
            "import { cors } from './cors';\n\n"
            "export function install(): unknown[] {\n"
            "  return [cors(), cors('x')];  // gt listed\n"
            "}\n"
        ),
    },
)

# #1764 / #1769：具名、改名、命名空间导入与 barrel 再导出都是跨文件调用。
ES_IMPORTS = Case(
    case_id="ts-1764-es-module-imports",
    issue="#1764 #1769",
    target_name="verifying",
    owner=None,
    files={
        "src/jwt/jws.ts": (
            "export async function verifying(key: string): Promise<boolean> {  // target\n"
            "  return key.length === 3;\n"
            "}\n"
        ),
        "src/jwt/index.ts": "export { verifying } from './jws';\n",
        "src/jwt/jwt.ts": (
            "import { verifying } from './jws';\n\n"
            "export async function verify(key: string): Promise<boolean> {\n"
            "  return await verifying(key);  // gt listed\n"
            "}\n"
        ),
        "src/jwt/alias.ts": (
            "import { verifying as check } from './jws';\n\n"
            "export function aliased(key: string): Promise<boolean> {\n"
            "  return check(key);  // gt listed\n"
            "}\n"
        ),
        "src/jwt/ns.ts": (
            "import * as jws from './jws';\n\n"
            "export function namespaced(key: string): Promise<boolean> {\n"
            "  return jws.verifying(key);  // gt listed\n"
            "}\n"
        ),
        "src/app.ts": (
            "import { verifying } from './jwt/index';\n\n"
            "export function viaBarrel(key: string): Promise<boolean> {\n"
            "  return verifying(key);  // gt listed\n"
            "}\n"
        ),
    },
)

# #1768：改名的默认导入 ``import makeSig from './jws'; makeSig()``。
RENAMED_DEFAULT = Case(
    case_id="ts-1768-renamed-default-import",
    issue="#1768",
    target_name="signer",
    owner=None,
    files={
        "src/jws.ts": (
            "export default function signer(k: string): string {  // target\n"
            "  return k;\n"
            "}\n"
        ),
        "src/sign.ts": (
            "import makeSig from './jws';\n\n"
            "export function sign(k: string): string {\n"
            "  return makeSig(k);  // gt listed\n"
            "}\n"
        ),
    },
)

JAVA_TS_CASES: tuple[Case, ...] = (
    GSON_DELEGATE,
    VIRTUAL_DISPATCH,
    INTERFACE_DISPATCH,
    ELEMENT_ACCESS,
    ARROW_CONST,
    ES_IMPORTS,
    RENAMED_DEFAULT,
)
