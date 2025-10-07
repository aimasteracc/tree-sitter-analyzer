/**
 * TypeScript 宣言ファイルの包括的なテスト
 * Comprehensive TypeScript declarations test file
 * 
 * @author TypeScript Analyzer Test
 * @version 1.0.0
 * @since 2025-01-07
 */

// ===== グローバル型宣言 (Global Type Declarations) =====

declare global {
    /**
     * ウィンドウオブジェクトの拡張
     * Window object extension
     */
    interface Window {
        APP_CONFIG: AppConfig;
        analytics: AnalyticsService;
        __DEVELOPMENT__: boolean;
        __VERSION__: string;
    }

    /**
     * NodeJS プロセス環境変数の拡張
     * NodeJS process environment variables extension
     */
    namespace NodeJS {
        interface ProcessEnv {
            NODE_ENV: 'development' | 'production' | 'test';
            API_BASE_URL: string;
            DATABASE_URL: string;
            JWT_SECRET: string;
            LOG_LEVEL: 'debug' | 'info' | 'warn' | 'error';
        }
    }

    /**
     * カスタムJSX要素の宣言
     * Custom JSX elements declaration
     */
    namespace JSX {
        interface IntrinsicElements {
            'custom-element': CustomElementProps;
            'web-component': WebComponentProps;
        }
    }
}

// ===== 基本型定義 (Basic Type Definitions) =====

/**
 * アプリケーション設定型
 * Application configuration type
 */
export interface AppConfig {
    readonly apiBaseUrl: string;
    readonly version: string;
    readonly features: FeatureFlags;
    readonly theme: ThemeConfig;
    readonly localization: LocalizationConfig;
}

/**
 * 機能フラグ型
 * Feature flags type
 */
export interface FeatureFlags {
    readonly enableAnalytics: boolean;
    readonly enableDarkMode: boolean;
    readonly enableExperimentalFeatures: boolean;
    readonly enableOfflineMode: boolean;
}

/**
 * テーマ設定型
 * Theme configuration type
 */
export interface ThemeConfig {
    readonly colors: ColorPalette;
    readonly typography: TypographyConfig;
    readonly spacing: SpacingConfig;
    readonly breakpoints: BreakpointConfig;
}

/**
 * カラーパレット型
 * Color palette type
 */
export interface ColorPalette {
    readonly primary: string;
    readonly secondary: string;
    readonly success: string;
    readonly warning: string;
    readonly error: string;
    readonly info: string;
    readonly background: string;
    readonly surface: string;
    readonly text: {
        readonly primary: string;
        readonly secondary: string;
        readonly disabled: string;
    };
}

/**
 * タイポグラフィ設定型
 * Typography configuration type
 */
export interface TypographyConfig {
    readonly fontFamily: {
        readonly primary: string;
        readonly secondary: string;
        readonly monospace: string;
    };
    readonly fontSize: {
        readonly xs: string;
        readonly sm: string;
        readonly md: string;
        readonly lg: string;
        readonly xl: string;
        readonly xxl: string;
    };
    readonly fontWeight: {
        readonly light: number;
        readonly normal: number;
        readonly medium: number;
        readonly bold: number;
    };
}

/**
 * スペーシング設定型
 * Spacing configuration type
 */
export interface SpacingConfig {
    readonly xs: string;
    readonly sm: string;
    readonly md: string;
    readonly lg: string;
    readonly xl: string;
    readonly xxl: string;
}

/**
 * ブレークポイント設定型
 * Breakpoint configuration type
 */
export interface BreakpointConfig {
    readonly xs: number;
    readonly sm: number;
    readonly md: number;
    readonly lg: number;
    readonly xl: number;
}

/**
 * ローカライゼーション設定型
 * Localization configuration type
 */
export interface LocalizationConfig {
    readonly defaultLocale: string;
    readonly supportedLocales: string[];
    readonly fallbackLocale: string;
    readonly dateFormat: string;
    readonly timeFormat: string;
    readonly numberFormat: Intl.NumberFormatOptions;
}

// ===== API関連型定義 (API-related Type Definitions) =====

/**
 * API レスポンス基底型
 * API response base type
 */
export interface ApiResponse<T = any> {
    readonly success: boolean;
    readonly data: T;
    readonly message?: string;
    readonly errors?: ApiError[];
    readonly meta?: ApiMeta;
}

/**
 * API エラー型
 * API error type
 */
export interface ApiError {
    readonly code: string;
    readonly message: string;
    readonly field?: string;
    readonly details?: Record<string, any>;
}

/**
 * API メタデータ型
 * API metadata type
 */
export interface ApiMeta {
    readonly page?: number;
    readonly limit?: number;
    readonly total?: number;
    readonly totalPages?: number;
    readonly hasNext?: boolean;
    readonly hasPrev?: boolean;
}

/**
 * ページネーション型
 * Pagination type
 */
export interface Pagination {
    readonly page: number;
    readonly limit: number;
    readonly offset: number;
    readonly sort?: SortConfig[];
}

/**
 * ソート設定型
 * Sort configuration type
 */
export interface SortConfig {
    readonly field: string;
    readonly direction: 'asc' | 'desc';
}

// ===== ユーザー関連型定義 (User-related Type Definitions) =====

/**
 * ユーザー型
 * User type
 */
export interface User {
    readonly id: string;
    readonly username: string;
    readonly email: string;
    readonly firstName: string;
    readonly lastName: string;
    readonly avatar?: string;
    readonly role: UserRole;
    readonly permissions: Permission[];
    readonly profile: UserProfile;
    readonly preferences: UserPreferences;
    readonly createdAt: string;
    readonly updatedAt: string;
    readonly lastLoginAt?: string;
}

/**
 * ユーザー役割型
 * User role type
 */
export type UserRole = 'super_admin' | 'admin' | 'moderator' | 'user' | 'guest';

/**
 * 権限型
 * Permission type
 */
export interface Permission {
    readonly id: string;
    readonly name: string;
    readonly resource: string;
    readonly actions: PermissionAction[];
    readonly conditions?: PermissionCondition[];
}

/**
 * 権限アクション型
 * Permission action type
 */
export type PermissionAction = 'create' | 'read' | 'update' | 'delete' | 'execute';

/**
 * 権限条件型
 * Permission condition type
 */
export interface PermissionCondition {
    readonly field: string;
    readonly operator: 'eq' | 'ne' | 'gt' | 'gte' | 'lt' | 'lte' | 'in' | 'nin';
    readonly value: any;
}

/**
 * ユーザープロフィール型
 * User profile type
 */
export interface UserProfile {
    readonly bio?: string;
    readonly website?: string;
    readonly location?: string;
    readonly birthDate?: string;
    readonly phoneNumber?: string;
    readonly socialLinks?: SocialLinks;
}

/**
 * ソーシャルリンク型
 * Social links type
 */
export interface SocialLinks {
    readonly twitter?: string;
    readonly linkedin?: string;
    readonly github?: string;
    readonly facebook?: string;
    readonly instagram?: string;
}

/**
 * ユーザー設定型
 * User preferences type
 */
export interface UserPreferences {
    readonly theme: 'light' | 'dark' | 'auto';
    readonly language: string;
    readonly timezone: string;
    readonly notifications: NotificationPreferences;
    readonly privacy: PrivacyPreferences;
}

/**
 * 通知設定型
 * Notification preferences type
 */
export interface NotificationPreferences {
    readonly email: boolean;
    readonly push: boolean;
    readonly sms: boolean;
    readonly inApp: boolean;
    readonly frequency: 'immediate' | 'daily' | 'weekly' | 'never';
}

/**
 * プライバシー設定型
 * Privacy preferences type
 */
export interface PrivacyPreferences {
    readonly profileVisibility: 'public' | 'friends' | 'private';
    readonly showEmail: boolean;
    readonly showPhoneNumber: boolean;
    readonly allowAnalytics: boolean;
    readonly allowMarketing: boolean;
}

// ===== イベント関連型定義 (Event-related Type Definitions) =====

/**
 * カスタムイベント型
 * Custom event type
 */
export interface CustomEvent<T = any> {
    readonly type: string;
    readonly data: T;
    readonly timestamp: number;
    readonly source?: string;
    readonly metadata?: Record<string, any>;
}

/**
 * イベントハンドラー型
 * Event handler type
 */
export type EventHandler<T = any> = (event: CustomEvent<T>) => void | Promise<void>;

/**
 * イベントリスナー型
 * Event listener type
 */
export interface EventListener<T = any> {
    readonly type: string;
    readonly handler: EventHandler<T>;
    readonly options?: EventListenerOptions;
}

/**
 * イベントリスナーオプション型
 * Event listener options type
 */
export interface EventListenerOptions {
    readonly once?: boolean;
    readonly passive?: boolean;
    readonly capture?: boolean;
}

// ===== サービス関連型定義 (Service-related Type Definitions) =====

/**
 * 分析サービス型
 * Analytics service type
 */
export interface AnalyticsService {
    track(event: string, properties?: Record<string, any>): void;
    identify(userId: string, traits?: Record<string, any>): void;
    page(name?: string, properties?: Record<string, any>): void;
    group(groupId: string, traits?: Record<string, any>): void;
    alias(userId: string, previousId?: string): void;
    reset(): void;
}

/**
 * ログサービス型
 * Log service type
 */
export interface LogService {
    debug(message: string, ...args: any[]): void;
    info(message: string, ...args: any[]): void;
    warn(message: string, ...args: any[]): void;
    error(message: string, error?: Error, ...args: any[]): void;
    setLevel(level: 'debug' | 'info' | 'warn' | 'error'): void;
}

/**
 * ストレージサービス型
 * Storage service type
 */
export interface StorageService {
    get<T = any>(key: string): T | null;
    set<T = any>(key: string, value: T): void;
    remove(key: string): void;
    clear(): void;
    has(key: string): boolean;
    keys(): string[];
}

/**
 * HTTP クライアント型
 * HTTP client type
 */
export interface HttpClient {
    get<T = any>(url: string, config?: RequestConfig): Promise<ApiResponse<T>>;
    post<T = any>(url: string, data?: any, config?: RequestConfig): Promise<ApiResponse<T>>;
    put<T = any>(url: string, data?: any, config?: RequestConfig): Promise<ApiResponse<T>>;
    patch<T = any>(url: string, data?: any, config?: RequestConfig): Promise<ApiResponse<T>>;
    delete<T = any>(url: string, config?: RequestConfig): Promise<ApiResponse<T>>;
}

/**
 * リクエスト設定型
 * Request configuration type
 */
export interface RequestConfig {
    readonly headers?: Record<string, string>;
    readonly params?: Record<string, any>;
    readonly timeout?: number;
    readonly retries?: number;
    readonly cache?: boolean;
}

// ===== ユーティリティ型 (Utility Types) =====

/**
 * 深い読み取り専用型
 * Deep readonly type
 */
export type DeepReadonly<T> = {
    readonly [P in keyof T]: T[P] extends object ? DeepReadonly<T[P]> : T[P];
};

/**
 * 深い部分型
 * Deep partial type
 */
export type DeepPartial<T> = {
    [P in keyof T]?: T[P] extends object ? DeepPartial<T[P]> : T[P];
};

/**
 * 必須フィールド型
 * Required fields type
 */
export type RequiredFields<T, K extends keyof T> = T & Required<Pick<T, K>>;

/**
 * オプショナルフィールド型
 * Optional fields type
 */
export type OptionalFields<T, K extends keyof T> = Omit<T, K> & Partial<Pick<T, K>>;

/**
 * 値の型を取得
 * Extract value types
 */
export type ValueOf<T> = T[keyof T];

/**
 * 関数の引数型を取得
 * Extract function parameter types
 */
export type Parameters<T extends (...args: any) => any> = T extends (...args: infer P) => any ? P : never;

/**
 * 関数の戻り値型を取得
 * Extract function return type
 */
export type ReturnType<T extends (...args: any) => any> = T extends (...args: any) => infer R ? R : any;

/**
 * Promise の解決型を取得
 * Extract Promise resolution type
 */
export type Awaited<T> = T extends PromiseLike<infer U> ? U : T;

/**
 * 配列の要素型を取得
 * Extract array element type
 */
export type ArrayElement<T> = T extends readonly (infer U)[] ? U : never;

// ===== カスタム要素型定義 (Custom Element Type Definitions) =====

/**
 * カスタム要素プロパティ型
 * Custom element properties type
 */
export interface CustomElementProps {
    'data-testid'?: string;
    'data-analytics'?: string;
    className?: string;
    style?: React.CSSProperties;
    children?: React.ReactNode;
}

/**
 * Webコンポーネントプロパティ型
 * Web component properties type
 */
export interface WebComponentProps {
    'data-config'?: string;
    'data-theme'?: string;
    slot?: string;
    children?: React.ReactNode;
}

// ===== モジュール拡張 (Module Augmentation) =====

/**
 * React モジュールの拡張
 * React module augmentation
 */
declare module 'react' {
    interface HTMLAttributes<T> {
        'data-testid'?: string;
        'data-analytics'?: string;
    }
}

/**
 * styled-components モジュールの拡張
 * styled-components module augmentation
 */
declare module 'styled-components' {
    export interface DefaultTheme extends ThemeConfig {}
}

// ===== 外部ライブラリ型定義 (External Library Type Definitions) =====

/**
 * jQuery プラグインの型定義
 * jQuery plugin type definitions
 */
declare global {
    interface JQuery {
        customPlugin(options?: CustomPluginOptions): JQuery;
        anotherPlugin(): JQuery;
    }
}

/**
 * カスタムプラグインオプション型
 * Custom plugin options type
 */
export interface CustomPluginOptions {
    readonly animation?: boolean;
    readonly duration?: number;
    readonly easing?: string;
    readonly callback?: () => void;
}

// ===== 環境変数型定義 (Environment Variables Type Definitions) =====

/**
 * 環境変数型
 * Environment variables type
 */
export interface EnvironmentVariables {
    readonly NODE_ENV: 'development' | 'production' | 'test';
    readonly PORT: string;
    readonly HOST: string;
    readonly API_BASE_URL: string;
    readonly DATABASE_URL: string;
    readonly REDIS_URL: string;
    readonly JWT_SECRET: string;
    readonly JWT_EXPIRES_IN: string;
    readonly CORS_ORIGIN: string;
    readonly LOG_LEVEL: 'debug' | 'info' | 'warn' | 'error';
    readonly UPLOAD_MAX_SIZE: string;
    readonly RATE_LIMIT_WINDOW: string;
    readonly RATE_LIMIT_MAX: string;
}

// ===== テスト関連型定義 (Test-related Type Definitions) =====

/**
 * テストコンテキスト型
 * Test context type
 */
export interface TestContext {
    readonly describe: (name: string, fn: () => void) => void;
    readonly it: (name: string, fn: () => void | Promise<void>) => void;
    readonly beforeEach: (fn: () => void | Promise<void>) => void;
    readonly afterEach: (fn: () => void | Promise<void>) => void;
    readonly expect: ExpectFunction;
}

/**
 * Expect 関数型
 * Expect function type
 */
export interface ExpectFunction {
    <T>(actual: T): Matchers<T>;
}

/**
 * マッチャー型
 * Matchers type
 */
export interface Matchers<T> {
    toBe(expected: T): void;
    toEqual(expected: T): void;
    toBeTruthy(): void;
    toBeFalsy(): void;
    toBeNull(): void;
    toBeUndefined(): void;
    toContain(expected: any): void;
    toThrow(expected?: string | RegExp): void;
}

// ===== エクスポート (Exports) =====

export * from './types/api';
export * from './types/user';
export * from './types/events';
export * from './types/services';

// デフォルトエクスポート (Default export)
declare const TypeScriptDeclarations: {
    readonly version: string;
    readonly types: string[];
    readonly interfaces: string[];
    readonly utilities: string[];
};

export default TypeScriptDeclarations;
