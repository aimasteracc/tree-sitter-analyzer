/**
 * React TypeScript コンポーネントの包括的なテストファイル
 * Comprehensive React TypeScript component test file
 * 
 * @author React TypeScript Analyzer Test
 * @version 1.0.0
 * @since 2025-01-07
 */

import React, { 
    useState, 
    useEffect, 
    useCallback, 
    useMemo, 
    useRef, 
    useContext,
    createContext,
    Component,
    PureComponent,
    ReactNode,
    ReactElement,
    FC,
    PropsWithChildren,
    CSSProperties
} from 'react';

// ===== 型定義 (Type Definitions) =====

interface User {
    id: string;
    name: string;
    email: string;
    avatar?: string;
    role: 'admin' | 'user' | 'guest';
}

interface Theme {
    primary: string;
    secondary: string;
    background: string;
    text: string;
}

type ButtonVariant = 'primary' | 'secondary' | 'danger' | 'success';
type Size = 'small' | 'medium' | 'large';

// ===== コンテキスト (Context) =====

interface AppContextType {
    user: User | null;
    theme: Theme;
    setUser: (user: User | null) => void;
    setTheme: (theme: Theme) => void;
}

const AppContext = createContext<AppContextType | undefined>(undefined);

// カスタムフック (Custom Hook)
const useAppContext = (): AppContextType => {
    const context = useContext(AppContext);
    if (!context) {
        throw new Error('useAppContext must be used within AppProvider');
    }
    return context;
};

// ===== プロップス型定義 (Props Type Definitions) =====

interface ButtonProps {
    variant?: ButtonVariant;
    size?: Size;
    disabled?: boolean;
    loading?: boolean;
    onClick?: (event: React.MouseEvent<HTMLButtonElement>) => void;
    children: ReactNode;
    className?: string;
    style?: CSSProperties;
}

interface UserCardProps {
    user: User;
    onEdit?: (user: User) => void;
    onDelete?: (userId: string) => void;
    showActions?: boolean;
}

interface UserListProps {
    users: User[];
    loading?: boolean;
    error?: string | null;
    onUserSelect?: (user: User) => void;
    onUserEdit?: (user: User) => void;
    onUserDelete?: (userId: string) => void;
}

interface FormData {
    name: string;
    email: string;
    role: User['role'];
}

interface UserFormProps {
    initialData?: Partial<FormData>;
    onSubmit: (data: FormData) => Promise<void>;
    onCancel: () => void;
    loading?: boolean;
}

// ===== 関数コンポーネント (Functional Components) =====

/**
 * 再利用可能なボタンコンポーネント
 * Reusable button component
 */
const Button: FC<ButtonProps> = ({
    variant = 'primary',
    size = 'medium',
    disabled = false,
    loading = false,
    onClick,
    children,
    className = '',
    style
}) => {
    const baseClasses = 'btn';
    const variantClass = `btn-${variant}`;
    const sizeClass = `btn-${size}`;
    const disabledClass = disabled || loading ? 'btn-disabled' : '';
    
    const classes = [baseClasses, variantClass, sizeClass, disabledClass, className]
        .filter(Boolean)
        .join(' ');

    return (
        <button
            type="button"
            className={classes}
            disabled={disabled || loading}
            onClick={onClick}
            style={style}
        >
            {loading ? (
                <>
                    <span className="spinner" />
                    読み込み中...
                </>
            ) : (
                children
            )}
        </button>
    );
};

/**
 * ユーザーカードコンポーネント
 * User card component
 */
const UserCard: FC<UserCardProps> = ({
    user,
    onEdit,
    onDelete,
    showActions = true
}) => {
    const handleEdit = useCallback(() => {
        onEdit?.(user);
    }, [user, onEdit]);

    const handleDelete = useCallback(() => {
        if (window.confirm(`${user.name}を削除しますか？`)) {
            onDelete?.(user.id);
        }
    }, [user, onDelete]);

    const roleColor = useMemo(() => {
        switch (user.role) {
            case 'admin': return '#ff6b6b';
            case 'user': return '#4ecdc4';
            case 'guest': return '#95a5a6';
            default: return '#95a5a6';
        }
    }, [user.role]);

    return (
        <div className="user-card">
            <div className="user-card-header">
                {user.avatar && (
                    <img 
                        src={user.avatar} 
                        alt={`${user.name}のアバター`}
                        className="user-avatar"
                    />
                )}
                <div className="user-info">
                    <h3 className="user-name">{user.name}</h3>
                    <p className="user-email">{user.email}</p>
                    <span 
                        className="user-role"
                        style={{ backgroundColor: roleColor }}
                    >
                        {user.role}
                    </span>
                </div>
            </div>
            
            {showActions && (
                <div className="user-card-actions">
                    <Button
                        variant="secondary"
                        size="small"
                        onClick={handleEdit}
                    >
                        編集
                    </Button>
                    <Button
                        variant="danger"
                        size="small"
                        onClick={handleDelete}
                    >
                        削除
                    </Button>
                </div>
            )}
        </div>
    );
};

/**
 * ユーザーフォームコンポーネント
 * User form component
 */
const UserForm: FC<UserFormProps> = ({
    initialData = {},
    onSubmit,
    onCancel,
    loading = false
}) => {
    const [formData, setFormData] = useState<FormData>({
        name: initialData.name || '',
        email: initialData.email || '',
        role: initialData.role || 'user'
    });

    const [errors, setErrors] = useState<Partial<FormData>>({});

    const handleInputChange = useCallback((
        field: keyof FormData,
        value: string
    ) => {
        setFormData(prev => ({ ...prev, [field]: value }));
        
        // エラーをクリア (Clear errors)
        if (errors[field]) {
            setErrors(prev => ({ ...prev, [field]: undefined }));
        }
    }, [errors]);

    const validateForm = useCallback((): boolean => {
        const newErrors: Partial<FormData> = {};

        if (!formData.name.trim()) {
            newErrors.name = '名前は必須です';
        }

        if (!formData.email.trim()) {
            newErrors.email = 'メールアドレスは必須です';
        } else if (!/\S+@\S+\.\S+/.test(formData.email)) {
            newErrors.email = '有効なメールアドレスを入力してください';
        }

        setErrors(newErrors);
        return Object.keys(newErrors).length === 0;
    }, [formData]);

    const handleSubmit = useCallback(async (e: React.FormEvent) => {
        e.preventDefault();
        
        if (!validateForm()) {
            return;
        }

        try {
            await onSubmit(formData);
        } catch (error) {
            console.error('フォーム送信エラー:', error);
        }
    }, [formData, validateForm, onSubmit]);

    return (
        <form onSubmit={handleSubmit} className="user-form">
            <div className="form-group">
                <label htmlFor="name">名前</label>
                <input
                    id="name"
                    type="text"
                    value={formData.name}
                    onChange={(e) => handleInputChange('name', e.target.value)}
                    className={errors.name ? 'error' : ''}
                    disabled={loading}
                />
                {errors.name && <span className="error-message">{errors.name}</span>}
            </div>

            <div className="form-group">
                <label htmlFor="email">メールアドレス</label>
                <input
                    id="email"
                    type="email"
                    value={formData.email}
                    onChange={(e) => handleInputChange('email', e.target.value)}
                    className={errors.email ? 'error' : ''}
                    disabled={loading}
                />
                {errors.email && <span className="error-message">{errors.email}</span>}
            </div>

            <div className="form-group">
                <label htmlFor="role">役割</label>
                <select
                    id="role"
                    value={formData.role}
                    onChange={(e) => handleInputChange('role', e.target.value as User['role'])}
                    disabled={loading}
                >
                    <option value="guest">ゲスト</option>
                    <option value="user">ユーザー</option>
                    <option value="admin">管理者</option>
                </select>
            </div>

            <div className="form-actions">
                <Button
                    type="submit"
                    variant="primary"
                    loading={loading}
                    disabled={loading}
                >
                    保存
                </Button>
                <Button
                    type="button"
                    variant="secondary"
                    onClick={onCancel}
                    disabled={loading}
                >
                    キャンセル
                </Button>
            </div>
        </form>
    );
};

/**
 * ユーザーリストコンポーネント
 * User list component
 */
const UserList: FC<UserListProps> = ({
    users,
    loading = false,
    error = null,
    onUserSelect,
    onUserEdit,
    onUserDelete
}) => {
    const [selectedUserId, setSelectedUserId] = useState<string | null>(null);

    const handleUserClick = useCallback((user: User) => {
        setSelectedUserId(user.id);
        onUserSelect?.(user);
    }, [onUserSelect]);

    if (loading) {
        return (
            <div className="user-list-loading">
                <div className="spinner" />
                <p>ユーザーを読み込み中...</p>
            </div>
        );
    }

    if (error) {
        return (
            <div className="user-list-error">
                <p>エラー: {error}</p>
            </div>
        );
    }

    if (users.length === 0) {
        return (
            <div className="user-list-empty">
                <p>ユーザーが見つかりません</p>
            </div>
        );
    }

    return (
        <div className="user-list">
            {users.map(user => (
                <div
                    key={user.id}
                    className={`user-list-item ${selectedUserId === user.id ? 'selected' : ''}`}
                    onClick={() => handleUserClick(user)}
                >
                    <UserCard
                        user={user}
                        onEdit={onUserEdit}
                        onDelete={onUserDelete}
                        showActions={true}
                    />
                </div>
            ))}
        </div>
    );
};

// ===== クラスコンポーネント (Class Components) =====

interface UserManagerState {
    users: User[];
    loading: boolean;
    error: string | null;
    showForm: boolean;
    editingUser: User | null;
}

/**
 * ユーザー管理クラスコンポーネント
 * User management class component
 */
class UserManager extends Component<{}, UserManagerState> {
    private abortController: AbortController | null = null;

    constructor(props: {}) {
        super(props);
        this.state = {
            users: [],
            loading: false,
            error: null,
            showForm: false,
            editingUser: null
        };
    }

    componentDidMount(): void {
        this.loadUsers();
    }

    componentWillUnmount(): void {
        if (this.abortController) {
            this.abortController.abort();
        }
    }

    private loadUsers = async (): Promise<void> => {
        this.setState({ loading: true, error: null });
        this.abortController = new AbortController();

        try {
            // シミュレートされたAPI呼び出し (Simulated API call)
            await new Promise(resolve => setTimeout(resolve, 1000));
            
            const mockUsers: User[] = [
                {
                    id: '1',
                    name: '田中太郎',
                    email: 'tanaka@example.com',
                    role: 'admin',
                    avatar: 'https://via.placeholder.com/50'
                },
                {
                    id: '2',
                    name: '佐藤花子',
                    email: 'sato@example.com',
                    role: 'user'
                },
                {
                    id: '3',
                    name: '鈴木次郎',
                    email: 'suzuki@example.com',
                    role: 'guest'
                }
            ];

            this.setState({ users: mockUsers, loading: false });
        } catch (error) {
            if (!this.abortController?.signal.aborted) {
                this.setState({ 
                    error: 'ユーザーの読み込みに失敗しました', 
                    loading: false 
                });
            }
        }
    };

    private handleUserEdit = (user: User): void => {
        this.setState({ editingUser: user, showForm: true });
    };

    private handleUserDelete = async (userId: string): Promise<void> => {
        try {
            // シミュレートされた削除処理 (Simulated delete operation)
            await new Promise(resolve => setTimeout(resolve, 500));
            
            this.setState(prevState => ({
                users: prevState.users.filter(user => user.id !== userId)
            }));
        } catch (error) {
            this.setState({ error: 'ユーザーの削除に失敗しました' });
        }
    };

    private handleFormSubmit = async (formData: FormData): Promise<void> => {
        try {
            // シミュレートされた保存処理 (Simulated save operation)
            await new Promise(resolve => setTimeout(resolve, 1000));

            if (this.state.editingUser) {
                // 更新 (Update)
                const updatedUser: User = {
                    ...this.state.editingUser,
                    ...formData
                };

                this.setState(prevState => ({
                    users: prevState.users.map(user =>
                        user.id === updatedUser.id ? updatedUser : user
                    ),
                    showForm: false,
                    editingUser: null
                }));
            } else {
                // 新規作成 (Create new)
                const newUser: User = {
                    id: Date.now().toString(),
                    ...formData
                };

                this.setState(prevState => ({
                    users: [...prevState.users, newUser],
                    showForm: false,
                    editingUser: null
                }));
            }
        } catch (error) {
            this.setState({ error: 'ユーザーの保存に失敗しました' });
        }
    };

    private handleFormCancel = (): void => {
        this.setState({ showForm: false, editingUser: null });
    };

    private handleAddUser = (): void => {
        this.setState({ showForm: true, editingUser: null });
    };

    render(): ReactElement {
        const { users, loading, error, showForm, editingUser } = this.state;

        return (
            <div className="user-manager">
                <div className="user-manager-header">
                    <h1>ユーザー管理</h1>
                    <Button
                        variant="primary"
                        onClick={this.handleAddUser}
                        disabled={loading}
                    >
                        新規ユーザー追加
                    </Button>
                </div>

                {showForm && (
                    <div className="user-form-modal">
                        <div className="modal-content">
                            <h2>{editingUser ? 'ユーザー編集' : '新規ユーザー'}</h2>
                            <UserForm
                                initialData={editingUser || {}}
                                onSubmit={this.handleFormSubmit}
                                onCancel={this.handleFormCancel}
                                loading={loading}
                            />
                        </div>
                    </div>
                )}

                <UserList
                    users={users}
                    loading={loading}
                    error={error}
                    onUserEdit={this.handleUserEdit}
                    onUserDelete={this.handleUserDelete}
                />
            </div>
        );
    }
}

// ===== PureComponent の例 (PureComponent Example) =====

interface CounterProps {
    initialCount?: number;
    step?: number;
    onCountChange?: (count: number) => void;
}

interface CounterState {
    count: number;
}

/**
 * パフォーマンス最適化されたカウンターコンポーネント
 * Performance-optimized counter component
 */
class Counter extends PureComponent<CounterProps, CounterState> {
    static defaultProps: Partial<CounterProps> = {
        initialCount: 0,
        step: 1
    };

    constructor(props: CounterProps) {
        super(props);
        this.state = {
            count: props.initialCount || 0
        };
    }

    private increment = (): void => {
        const { step = 1, onCountChange } = this.props;
        this.setState(
            prevState => ({ count: prevState.count + step }),
            () => onCountChange?.(this.state.count)
        );
    };

    private decrement = (): void => {
        const { step = 1, onCountChange } = this.props;
        this.setState(
            prevState => ({ count: prevState.count - step }),
            () => onCountChange?.(this.state.count)
        );
    };

    private reset = (): void => {
        const { initialCount = 0, onCountChange } = this.props;
        this.setState(
            { count: initialCount },
            () => onCountChange?.(this.state.count)
        );
    };

    render(): ReactElement {
        const { count } = this.state;
        const { step = 1 } = this.props;

        return (
            <div className="counter">
                <div className="counter-display">
                    <span className="counter-value">{count}</span>
                </div>
                <div className="counter-controls">
                    <Button
                        variant="secondary"
                        onClick={this.decrement}
                    >
                        -{step}
                    </Button>
                    <Button
                        variant="secondary"
                        onClick={this.reset}
                    >
                        リセット
                    </Button>
                    <Button
                        variant="primary"
                        onClick={this.increment}
                    >
                        +{step}
                    </Button>
                </div>
            </div>
        );
    }
}

// ===== カスタムフック (Custom Hooks) =====

/**
 * ローカルストレージを使用するカスタムフック
 * Custom hook for using localStorage
 */
function useLocalStorage<T>(
    key: string,
    initialValue: T
): [T, (value: T | ((val: T) => T)) => void] {
    const [storedValue, setStoredValue] = useState<T>(() => {
        try {
            const item = window.localStorage.getItem(key);
            return item ? JSON.parse(item) : initialValue;
        } catch (error) {
            console.error(`localStorage読み込みエラー: ${key}`, error);
            return initialValue;
        }
    });

    const setValue = useCallback((value: T | ((val: T) => T)) => {
        try {
            const valueToStore = value instanceof Function ? value(storedValue) : value;
            setStoredValue(valueToStore);
            window.localStorage.setItem(key, JSON.stringify(valueToStore));
        } catch (error) {
            console.error(`localStorage保存エラー: ${key}`, error);
        }
    }, [key, storedValue]);

    return [storedValue, setValue];
}

/**
 * API呼び出し用カスタムフック
 * Custom hook for API calls
 */
function useApi<T>(
    url: string,
    options?: RequestInit
): {
    data: T | null;
    loading: boolean;
    error: string | null;
    refetch: () => void;
} {
    const [data, setData] = useState<T | null>(null);
    const [loading, setLoading] = useState<boolean>(true);
    const [error, setError] = useState<string | null>(null);

    const fetchData = useCallback(async () => {
        setLoading(true);
        setError(null);

        try {
            // シミュレートされたAPI呼び出し (Simulated API call)
            await new Promise(resolve => setTimeout(resolve, 1000));
            
            const mockData = {
                message: `データが正常に取得されました: ${url}`,
                timestamp: new Date().toISOString()
            } as T;

            setData(mockData);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'APIエラーが発生しました');
        } finally {
            setLoading(false);
        }
    }, [url, options]);

    useEffect(() => {
        fetchData();
    }, [fetchData]);

    return { data, loading, error, refetch: fetchData };
}

// ===== プロバイダーコンポーネント (Provider Component) =====

interface AppProviderProps {
    children: ReactNode;
}

/**
 * アプリケーションコンテキストプロバイダー
 * Application context provider
 */
const AppProvider: FC<AppProviderProps> = ({ children }) => {
    const [user, setUser] = useLocalStorage<User | null>('currentUser', null);
    const [theme, setTheme] = useLocalStorage<Theme>('theme', {
        primary: '#007bff',
        secondary: '#6c757d',
        background: '#ffffff',
        text: '#333333'
    });

    const contextValue = useMemo<AppContextType>(() => ({
        user,
        theme,
        setUser,
        setTheme
    }), [user, theme, setUser, setTheme]);

    return (
        <AppContext.Provider value={contextValue}>
            {children}
        </AppContext.Provider>
    );
};

// ===== メインアプリケーションコンポーネント (Main Application Component) =====

/**
 * メインアプリケーションコンポーネント
 * Main application component
 */
const App: FC = () => {
    const { user, theme } = useAppContext();
    const { data: apiData, loading: apiLoading, error: apiError } = useApi('/api/status');
    const [counterValue, setCounterValue] = useState<number>(0);

    const appStyle: CSSProperties = {
        backgroundColor: theme.background,
        color: theme.text,
        minHeight: '100vh',
        padding: '20px'
    };

    return (
        <div style={appStyle}>
            <header className="app-header">
                <h1>React TypeScript 包括的テストアプリケーション</h1>
                {user && (
                    <div className="user-info">
                        ようこそ、{user.name}さん！
                    </div>
                )}
            </header>

            <main className="app-main">
                <section className="api-status">
                    <h2>API ステータス</h2>
                    {apiLoading && <p>読み込み中...</p>}
                    {apiError && <p>エラー: {apiError}</p>}
                    {apiData && <pre>{JSON.stringify(apiData, null, 2)}</pre>}
                </section>

                <section className="counter-section">
                    <h2>カウンター</h2>
                    <Counter
                        initialCount={0}
                        step={5}
                        onCountChange={setCounterValue}
                    />
                    <p>現在の値: {counterValue}</p>
                </section>

                <section className="user-management">
                    <UserManager />
                </section>
            </main>
        </div>
    );
};

// ===== エクスポート (Exports) =====

export default App;
export { 
    AppProvider, 
    Button, 
    UserCard, 
    UserForm, 
    UserList, 
    UserManager, 
    Counter,
    useAppContext,
    useLocalStorage,
    useApi
};

export type { 
    User, 
    Theme, 
    ButtonProps, 
    UserCardProps, 
    UserFormProps, 
    UserListProps,
    AppContextType,
    ButtonVariant,
    Size,
    FormData
};

// ===== アプリケーションのルート (Application Root) =====

/**
 * アプリケーションのルートコンポーネント
 * Application root component
 */
const AppRoot: FC = () => {
    return (
        <AppProvider>
            <App />
        </AppProvider>
    );
};

export { AppRoot };
