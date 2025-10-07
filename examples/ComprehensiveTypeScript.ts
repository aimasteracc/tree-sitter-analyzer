/**
 * 包含所有TypeScript特性的综合测试文件
 * Comprehensive TypeScript features test file
 * 
 * @author TypeScript Analyzer Test
 * @version 1.0.0
 * @since 2025-01-07
 */

// ===== インポートとエクスポート (Imports and Exports) =====
import { Observable, Subject } from 'rxjs';
import * as fs from 'fs';
import type { EventEmitter } from 'events';
import { readFile as readFileAsync } from 'fs/promises';
import defaultExport, { namedExport } from './utils';

// ===== 型定義 (Type Definitions) =====

// 基本型エイリアス (Basic Type Aliases)
type StringOrNumber = string | number;
type UserID = string;
type Callback<T> = (value: T) => void;

// 条件型 (Conditional Types)
type NonNullable<T> = T extends null | undefined ? never : T;
type ReturnType<T> = T extends (...args: any[]) => infer R ? R : any;

// マップ型 (Mapped Types)
type Partial<T> = {
    [P in keyof T]?: T[P];
};

type Required<T> = {
    [P in keyof T]-?: T[P];
};

// テンプレートリテラル型 (Template Literal Types)
type EventName<T extends string> = `on${Capitalize<T>}`;
type CSSProperty = `--${string}`;

// ===== インターフェース (Interfaces) =====

/**
 * ユーザー情報を表すインターフェース
 * Interface representing user information
 */
interface User {
    readonly id: UserID;
    name: string;
    email?: string;
    age: number;
    preferences: UserPreferences;
    [key: string]: any; // インデックスシグネチャ (Index signature)
}

interface UserPreferences {
    theme: 'light' | 'dark';
    language: 'ja' | 'en' | 'zh';
    notifications: boolean;
}

// インターフェース継承 (Interface Inheritance)
interface AdminUser extends User {
    permissions: Permission[];
    lastLogin: Date;
}

interface Permission {
    resource: string;
    actions: ('read' | 'write' | 'delete')[];
}

// ジェネリックインターフェース (Generic Interface)
interface Repository<T, K = string> {
    findById(id: K): Promise<T | null>;
    save(entity: T): Promise<T>;
    delete(id: K): Promise<boolean>;
    findAll(filter?: Partial<T>): Promise<T[]>;
}

// 関数型インターフェース (Function Type Interface)
interface EventHandler<T = any> {
    (event: T): void;
}

// ===== 列挙型 (Enums) =====

/**
 * ユーザーの役割を表す列挙型
 * Enum representing user roles
 */
enum UserRole {
    GUEST = 'guest',
    USER = 'user',
    ADMIN = 'admin',
    SUPER_ADMIN = 'super_admin'
}

// 数値列挙型 (Numeric Enum)
enum HttpStatusCode {
    OK = 200,
    CREATED = 201,
    BAD_REQUEST = 400,
    UNAUTHORIZED = 401,
    NOT_FOUND = 404,
    INTERNAL_SERVER_ERROR = 500
}

// const列挙型 (Const Enum)
const enum Direction {
    Up,
    Down,
    Left,
    Right
}

// ===== クラス (Classes) =====

/**
 * 抽象基底クラス
 * Abstract base class
 */
abstract class BaseEntity {
    protected readonly id: string;
    protected createdAt: Date;
    protected updatedAt: Date;

    constructor(id: string) {
        this.id = id;
        this.createdAt = new Date();
        this.updatedAt = new Date();
    }

    abstract validate(): boolean;

    protected updateTimestamp(): void {
        this.updatedAt = new Date();
    }

    public getId(): string {
        return this.id;
    }
}

/**
 * ユーザーサービスクラス
 * User service class with comprehensive TypeScript features
 */
class UserService extends BaseEntity implements Repository<User> {
    private static instance: UserService;
    private users: Map<string, User> = new Map();
    private eventEmitter: EventEmitter;

    // プライベートコンストラクタ (Private constructor for Singleton)
    private constructor(id: string) {
        super(id);
        this.eventEmitter = new EventEmitter();
    }

    // 静的ファクトリーメソッド (Static factory method)
    public static getInstance(id: string = 'default'): UserService {
        if (!UserService.instance) {
            UserService.instance = new UserService(id);
        }
        return UserService.instance;
    }

    // ジェネリックメソッド (Generic method)
    public async findById<T extends User = User>(id: string): Promise<T | null> {
        const user = this.users.get(id);
        return user as T | null;
    }

    // オーバーロード (Method overloading)
    public save(user: User): Promise<User>;
    public save(users: User[]): Promise<User[]>;
    public async save(userOrUsers: User | User[]): Promise<User | User[]> {
        if (Array.isArray(userOrUsers)) {
            const savedUsers: User[] = [];
            for (const user of userOrUsers) {
                this.users.set(user.id, user);
                savedUsers.push(user);
                this.eventEmitter.emit('userSaved', user);
            }
            return savedUsers;
        } else {
            this.users.set(userOrUsers.id, userOrUsers);
            this.eventEmitter.emit('userSaved', userOrUsers);
            return userOrUsers;
        }
    }

    public async delete(id: string): Promise<boolean> {
        const deleted = this.users.delete(id);
        if (deleted) {
            this.eventEmitter.emit('userDeleted', id);
        }
        return deleted;
    }

    public async findAll(filter?: Partial<User>): Promise<User[]> {
        let users = Array.from(this.users.values());
        
        if (filter) {
            users = users.filter(user => {
                return Object.entries(filter).every(([key, value]) => {
                    return user[key as keyof User] === value;
                });
            });
        }
        
        return users;
    }

    // バリデーション実装 (Validation implementation)
    public validate(): boolean {
        return this.users.size >= 0;
    }

    // イベントハンドラー (Event handlers)
    public onUserSaved(handler: EventHandler<User>): void {
        this.eventEmitter.on('userSaved', handler);
    }

    public onUserDeleted(handler: EventHandler<string>): void {
        this.eventEmitter.on('userDeleted', handler);
    }
}

// ===== デコレーター (Decorators) =====

/**
 * ログ出力デコレーター
 * Logging decorator
 */
function Log(target: any, propertyName: string, descriptor: PropertyDescriptor) {
    const method = descriptor.value;
    
    descriptor.value = function (...args: any[]) {
        console.log(`呼び出し中: ${propertyName} with args:`, args);
        const result = method.apply(this, args);
        console.log(`完了: ${propertyName} with result:`, result);
        return result;
    };
}

/**
 * バリデーションデコレーター
 * Validation decorator
 */
function Validate(validator: (value: any) => boolean) {
    return function (target: any, propertyName: string) {
        let value = target[propertyName];
        
        const getter = () => value;
        const setter = (newValue: any) => {
            if (!validator(newValue)) {
                throw new Error(`無効な値: ${propertyName}`);
            }
            value = newValue;
        };
        
        Object.defineProperty(target, propertyName, {
            get: getter,
            set: setter,
            enumerable: true,
            configurable: true
        });
    };
}

// デコレーター使用例 (Decorator usage example)
class ValidatedUser {
    @Validate((value: string) => value.length > 0)
    public name: string = '';

    @Validate((value: number) => value >= 0 && value <= 150)
    public age: number = 0;

    @Log
    public greet(message: string): string {
        return `こんにちは、${this.name}さん！ ${message}`;
    }
}

// ===== 高度な型機能 (Advanced Type Features) =====

// ユーティリティ型 (Utility Types)
type UserUpdate = Partial<Pick<User, 'name' | 'email' | 'preferences'>>;
type UserKeys = keyof User;
type UserValues = User[keyof User];

// 条件型の使用例 (Conditional Types Usage)
type ApiResponse<T> = T extends string 
    ? { message: T } 
    : T extends number 
    ? { code: T } 
    : { data: T };

// インデックス型 (Index Types)
function getProperty<T, K extends keyof T>(obj: T, key: K): T[K] {
    return obj[key];
}

// ===== 非同期処理 (Async/Await) =====

/**
 * 非同期データ処理クラス
 * Asynchronous data processing class
 */
class AsyncDataProcessor {
    private cache: Map<string, any> = new Map();

    /**
     * データを非同期で取得
     * Fetch data asynchronously
     */
    public async fetchData<T>(url: string): Promise<T> {
        if (this.cache.has(url)) {
            return this.cache.get(url);
        }

        try {
            // シミュレートされた非同期処理 (Simulated async operation)
            const response = await this.simulateApiCall<T>(url);
            this.cache.set(url, response);
            return response;
        } catch (error) {
            console.error(`データ取得エラー: ${url}`, error);
            throw error;
        }
    }

    private async simulateApiCall<T>(url: string): Promise<T> {
        return new Promise((resolve, reject) => {
            setTimeout(() => {
                if (url.includes('error')) {
                    reject(new Error('API呼び出しエラー'));
                } else {
                    resolve({ url, timestamp: Date.now() } as T);
                }
            }, 100);
        });
    }

    /**
     * 複数のデータを並行取得
     * Fetch multiple data concurrently
     */
    public async fetchMultipleData<T>(urls: string[]): Promise<T[]> {
        const promises = urls.map(url => this.fetchData<T>(url));
        return Promise.all(promises);
    }

    /**
     * ジェネレーター関数 (Generator function)
     */
    public async* processDataStream<T>(data: T[]): AsyncGenerator<T, void, unknown> {
        for (const item of data) {
            // 非同期処理をシミュレート (Simulate async processing)
            await new Promise(resolve => setTimeout(resolve, 10));
            yield item;
        }
    }
}

// ===== モジュールとネームスペース (Modules and Namespaces) =====

namespace DataProcessing {
    export interface ProcessorConfig {
        batchSize: number;
        timeout: number;
        retries: number;
    }

    export class BatchProcessor<T> {
        private config: ProcessorConfig;

        constructor(config: ProcessorConfig) {
            this.config = config;
        }

        public async processBatch(items: T[]): Promise<T[]> {
            const batches = this.createBatches(items);
            const results: T[] = [];

            for (const batch of batches) {
                const processed = await this.processSingleBatch(batch);
                results.push(...processed);
            }

            return results;
        }

        private createBatches(items: T[]): T[][] {
            const batches: T[][] = [];
            for (let i = 0; i < items.length; i += this.config.batchSize) {
                batches.push(items.slice(i, i + this.config.batchSize));
            }
            return batches;
        }

        private async processSingleBatch(batch: T[]): Promise<T[]> {
            // バッチ処理のシミュレート (Simulate batch processing)
            return new Promise(resolve => {
                setTimeout(() => resolve(batch), this.config.timeout);
            });
        }
    }
}

// ===== 関数とアロー関数 (Functions and Arrow Functions) =====

/**
 * 高階関数の例 (Higher-order function example)
 */
function createValidator<T>(
    predicate: (value: T) => boolean,
    errorMessage: string
): (value: T) => T {
    return (value: T): T => {
        if (!predicate(value)) {
            throw new Error(errorMessage);
        }
        return value;
    };
}

// カリー化関数 (Curried function)
const add = (a: number) => (b: number) => a + b;
const multiply = (a: number) => (b: number) => a * b;

// 関数合成 (Function composition)
const compose = <T, U, V>(f: (x: U) => V, g: (x: T) => U) => (x: T): V => f(g(x));

// ===== 実用例 (Practical Examples) =====

/**
 * アプリケーションのメインクラス
 * Main application class
 */
class Application {
    private userService: UserService;
    private dataProcessor: AsyncDataProcessor;
    private batchProcessor: DataProcessing.BatchProcessor<User>;

    constructor() {
        this.userService = UserService.getInstance();
        this.dataProcessor = new AsyncDataProcessor();
        this.batchProcessor = new DataProcessing.BatchProcessor({
            batchSize: 10,
            timeout: 1000,
            retries: 3
        });

        this.setupEventHandlers();
    }

    private setupEventHandlers(): void {
        this.userService.onUserSaved((user: User) => {
            console.log(`ユーザーが保存されました: ${user.name}`);
        });

        this.userService.onUserDeleted((userId: string) => {
            console.log(`ユーザーが削除されました: ${userId}`);
        });
    }

    /**
     * アプリケーションの初期化
     * Initialize the application
     */
    public async initialize(): Promise<void> {
        try {
            // サンプルユーザーの作成 (Create sample users)
            const sampleUsers: User[] = [
                {
                    id: '1',
                    name: '田中太郎',
                    email: 'tanaka@example.com',
                    age: 30,
                    preferences: {
                        theme: 'light',
                        language: 'ja',
                        notifications: true
                    }
                },
                {
                    id: '2',
                    name: '佐藤花子',
                    email: 'sato@example.com',
                    age: 25,
                    preferences: {
                        theme: 'dark',
                        language: 'ja',
                        notifications: false
                    }
                }
            ];

            // バッチ処理でユーザーを保存 (Save users in batch)
            const processedUsers = await this.batchProcessor.processBatch(sampleUsers);
            await this.userService.save(processedUsers);

            console.log('アプリケーションの初期化が完了しました');
        } catch (error) {
            console.error('初期化エラー:', error);
            throw error;
        }
    }

    /**
     * ユーザー検索のデモ (User search demo)
     */
    public async demonstrateUserSearch(): Promise<void> {
        const allUsers = await this.userService.findAll();
        console.log('全ユーザー:', allUsers);

        const adultUsers = await this.userService.findAll({ age: 30 });
        console.log('30歳のユーザー:', adultUsers);

        const specificUser = await this.userService.findById('1');
        console.log('特定ユーザー:', specificUser);
    }

    /**
     * データストリーム処理のデモ (Data stream processing demo)
     */
    public async demonstrateStreamProcessing(): Promise<void> {
        const users = await this.userService.findAll();
        
        console.log('ストリーム処理開始...');
        for await (const user of this.dataProcessor.processDataStream(users)) {
            console.log(`処理中: ${user.name}`);
        }
        console.log('ストリーム処理完了');
    }
}

// ===== エクスポート (Exports) =====

export default Application;
export { 
    User, 
    UserService, 
    AsyncDataProcessor, 
    UserRole, 
    HttpStatusCode,
    ValidatedUser,
    DataProcessing
};

export type { 
    UserPreferences, 
    AdminUser, 
    Permission, 
    Repository, 
    EventHandler,
    StringOrNumber,
    UserID,
    Callback
};

// ===== 型アサーションとキャスト (Type Assertions and Casting) =====

const unknownValue: unknown = "これは文字列です";
const stringValue = unknownValue as string;
const anotherStringValue = <string>unknownValue;

// 非null アサーション (Non-null assertion)
function processUser(user: User | null): string {
    return user!.name; // userがnullでないことを保証
}

// ===== 型ガード (Type Guards) =====

function isUser(obj: any): obj is User {
    return obj && 
           typeof obj.id === 'string' &&
           typeof obj.name === 'string' &&
           typeof obj.age === 'number';
}

function isAdminUser(user: User): user is AdminUser {
    return 'permissions' in user && 'lastLogin' in user;
}

// 使用例 (Usage example)
function handleUser(user: User | AdminUser): void {
    if (isAdminUser(user)) {
        console.log(`管理者: ${user.name}, 権限数: ${user.permissions.length}`);
    } else {
        console.log(`一般ユーザー: ${user.name}`);
    }
}

// ===== 最終的な使用例 (Final usage example) =====

async function main(): Promise<void> {
    const app = new Application();
    
    try {
        await app.initialize();
        await app.demonstrateUserSearch();
        await app.demonstrateStreamProcessing();
        
        // バリデーション付きユーザーのテスト (Validated user test)
        const validatedUser = new ValidatedUser();
        validatedUser.name = "検証済みユーザー";
        validatedUser.age = 25;
        
        const greeting = validatedUser.greet("TypeScript分析のテストです！");
        console.log(greeting);
        
    } catch (error) {
        console.error('アプリケーションエラー:', error);
    }
}

// アプリケーション実行 (Run application)
if (require.main === module) {
    main().catch(console.error);
}
