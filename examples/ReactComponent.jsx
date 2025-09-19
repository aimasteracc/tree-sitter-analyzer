/**
 * React Component Example - JSX and Modern React Patterns
 *
 * This file demonstrates React-specific JavaScript patterns that the
 * enhanced JavaScript plugin can detect and analyze.
 */

import PropTypes from 'prop-types';
import React, {
    createContext,
    forwardRef,
    memo,
    useCallback,
    useContext,
    useEffect,
    useMemo,
    useRef,
    useState
} from 'react';

// Context creation
const ThemeContext = createContext({
    theme: 'light',
    toggleTheme: () => { }
});

// Custom hooks
const useLocalStorage = (key, initialValue) => {
    const [storedValue, setStoredValue] = useState(() => {
        try {
            const item = window.localStorage.getItem(key);
            return item ? JSON.parse(item) : initialValue;
        } catch (error) {
            console.error(`Error reading localStorage key "${key}":`, error);
            return initialValue;
        }
    });

    const setValue = useCallback((value) => {
        try {
            setStoredValue(value);
            window.localStorage.setItem(key, JSON.stringify(value));
        } catch (error) {
            console.error(`Error setting localStorage key "${key}":`, error);
        }
    }, [key]);

    return [storedValue, setValue];
};

const useDebounce = (value, delay) => {
    const [debouncedValue, setDebouncedValue] = useState(value);

    useEffect(() => {
        const handler = setTimeout(() => {
            setDebouncedValue(value);
        }, delay);

        return () => {
            clearTimeout(handler);
        };
    }, [value, delay]);

    return debouncedValue;
};

const useFetch = (url, options = {}) => {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    useEffect(() => {
        const fetchData = async () => {
            try {
                setLoading(true);
                setError(null);

                const response = await fetch(url, options);
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }

                const result = await response.json();
                setData(result);
            } catch (err) {
                setError(err.message);
            } finally {
                setLoading(false);
            }
        };

        if (url) {
            fetchData();
        }
    }, [url, JSON.stringify(options)]);

    return { data, loading, error };
};

// Higher-order component
const withTheme = (WrappedComponent) => {
    const WithThemeComponent = (props) => {
        const theme = useContext(ThemeContext);
        return <WrappedComponent {...props} theme={theme} />;
    };

    WithThemeComponent.displayName = `withTheme(${WrappedComponent.displayName || WrappedComponent.name})`;
    return WithThemeComponent;
};

// Functional component with hooks
const SearchInput = memo(({ onSearch, placeholder = "Search...", debounceMs = 300 }) => {
    const [query, setQuery] = useState('');
    const debouncedQuery = useDebounce(query, debounceMs);
    const inputRef = useRef(null);

    useEffect(() => {
        if (debouncedQuery) {
            onSearch(debouncedQuery);
        }
    }, [debouncedQuery, onSearch]);

    const handleClear = useCallback(() => {
        setQuery('');
        inputRef.current?.focus();
    }, []);

    const handleKeyPress = useCallback((event) => {
        if (event.key === 'Enter') {
            onSearch(query);
        }
    }, [query, onSearch]);

    return (
        <div className="search-input">
            <input
                ref={inputRef}
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyPress={handleKeyPress}
                placeholder={placeholder}
                className="search-field"
            />
            {query && (
                <button
                    onClick={handleClear}
                    className="clear-button"
                    aria-label="Clear search"
                >
                    ×
                </button>
            )}
        </div>
    );
});

SearchInput.propTypes = {
    onSearch: PropTypes.func.isRequired,
    placeholder: PropTypes.string,
    debounceMs: PropTypes.number
};

// Forwarded ref component
const FancyButton = forwardRef(({
    children,
    variant = 'primary',
    size = 'medium',
    disabled = false,
    loading = false,
    onClick,
    ...props
}, ref) => {
    const handleClick = useCallback((event) => {
        if (!disabled && !loading && onClick) {
            onClick(event);
        }
    }, [disabled, loading, onClick]);

    const buttonClasses = useMemo(() => {
        return [
            'fancy-button',
            `fancy-button--${variant}`,
            `fancy-button--${size}`,
            disabled && 'fancy-button--disabled',
            loading && 'fancy-button--loading'
        ].filter(Boolean).join(' ');
    }, [variant, size, disabled, loading]);

    return (
        <button
            ref={ref}
            className={buttonClasses}
            onClick={handleClick}
            disabled={disabled || loading}
            {...props}
        >
            {loading ? (
                <span className="spinner" aria-hidden="true" />
            ) : null}
            <span className={loading ? 'button-text--hidden' : 'button-text'}>
                {children}
            </span>
        </button>
    );
});

FancyButton.displayName = 'FancyButton';

FancyButton.propTypes = {
    children: PropTypes.node.isRequired,
    variant: PropTypes.oneOf(['primary', 'secondary', 'danger']),
    size: PropTypes.oneOf(['small', 'medium', 'large']),
    disabled: PropTypes.bool,
    loading: PropTypes.bool,
    onClick: PropTypes.func
};

// Class component (legacy but still supported)
class DataTable extends React.Component {
    static propTypes = {
        data: PropTypes.arrayOf(PropTypes.object).isRequired,
        columns: PropTypes.arrayOf(PropTypes.shape({
            key: PropTypes.string.isRequired,
            title: PropTypes.string.isRequired,
            render: PropTypes.func
        })).isRequired,
        onRowClick: PropTypes.func,
        loading: PropTypes.bool,
        emptyMessage: PropTypes.string
    };

    static defaultProps = {
        loading: false,
        emptyMessage: 'No data available'
    };

    constructor(props) {
        super(props);

        this.state = {
            sortColumn: null,
            sortDirection: 'asc',
            selectedRows: new Set()
        };

        this.tableRef = React.createRef();
    }

    componentDidMount() {
        this.focusTable();
    }

    componentDidUpdate(prevProps) {
        if (prevProps.data !== this.props.data) {
            this.setState({ selectedRows: new Set() });
        }
    }

    focusTable = () => {
        if (this.tableRef.current) {
            this.tableRef.current.focus();
        }
    };

    handleSort = (columnKey) => {
        this.setState(prevState => ({
            sortColumn: columnKey,
            sortDirection:
                prevState.sortColumn === columnKey && prevState.sortDirection === 'asc'
                    ? 'desc'
                    : 'asc'
        }));
    };

    handleRowSelect = (rowIndex) => {
        this.setState(prevState => {
            const newSelectedRows = new Set(prevState.selectedRows);
            if (newSelectedRows.has(rowIndex)) {
                newSelectedRows.delete(rowIndex);
            } else {
                newSelectedRows.add(rowIndex);
            }
            return { selectedRows: newSelectedRows };
        });
    };

    handleSelectAll = () => {
        const { data } = this.props;
        this.setState(prevState => {
            const allSelected = prevState.selectedRows.size === data.length;
            return {
                selectedRows: allSelected
                    ? new Set()
                    : new Set(data.map((_, index) => index))
            };
        });
    };

    getSortedData() {
        const { data } = this.props;
        const { sortColumn, sortDirection } = this.state;

        if (!sortColumn) {
            return data;
        }

        return [...data].sort((a, b) => {
            const aValue = a[sortColumn];
            const bValue = b[sortColumn];

            if (aValue === bValue) return 0;

            const comparison = aValue < bValue ? -1 : 1;
            return sortDirection === 'asc' ? comparison : -comparison;
        });
    }

    renderHeader() {
        const { columns } = this.props;
        const { sortColumn, sortDirection, selectedRows } = this.state;
        const { data } = this.props;

        return (
            <thead>
                <tr>
                    <th className="select-column">
                        <input
                            type="checkbox"
                            checked={selectedRows.size === data.length && data.length > 0}
                            onChange={this.handleSelectAll}
                            aria-label="Select all rows"
                        />
                    </th>
                    {columns.map(column => (
                        <th
                            key={column.key}
                            onClick={() => this.handleSort(column.key)}
                            className={`sortable-header ${sortColumn === column.key ? 'sorted' : ''}`}
                            aria-sort={
                                sortColumn === column.key
                                    ? sortDirection === 'asc' ? 'ascending' : 'descending'
                                    : 'none'
                            }
                        >
                            {column.title}
                            {sortColumn === column.key && (
                                <span className="sort-indicator">
                                    {sortDirection === 'asc' ? '↑' : '↓'}
                                </span>
                            )}
                        </th>
                    ))}
                </tr>
            </thead>
        );
    }

    renderBody() {
        const { columns, onRowClick } = this.props;
        const { selectedRows } = this.state;
        const sortedData = this.getSortedData();

        return (
            <tbody>
                {sortedData.map((row, index) => (
                    <tr
                        key={row.id || index}
                        className={`data-row ${selectedRows.has(index) ? 'selected' : ''}`}
                        onClick={() => onRowClick?.(row, index)}
                    >
                        <td className="select-column">
                            <input
                                type="checkbox"
                                checked={selectedRows.has(index)}
                                onChange={() => this.handleRowSelect(index)}
                                onClick={(e) => e.stopPropagation()}
                                aria-label={`Select row ${index + 1}`}
                            />
                        </td>
                        {columns.map(column => (
                            <td key={column.key} className={`column-${column.key}`}>
                                {column.render ? column.render(row[column.key], row, index) : row[column.key]}
                            </td>
                        ))}
                    </tr>
                ))}
            </tbody>
        );
    }

    render() {
        const { data, loading, emptyMessage } = this.props;

        if (loading) {
            return (
                <div className="table-loading">
                    <div className="spinner" />
                    <p>Loading data...</p>
                </div>
            );
        }

        if (data.length === 0) {
            return (
                <div className="table-empty">
                    <p>{emptyMessage}</p>
                </div>
            );
        }

        return (
            <div className="data-table-container">
                <table
                    ref={this.tableRef}
                    className="data-table"
                    tabIndex={0}
                    role="grid"
                    aria-label="Data table"
                >
                    {this.renderHeader()}
                    {this.renderBody()}
                </table>
            </div>
        );
    }
}

// Main application component
const App = () => {
    const [theme, setTheme] = useLocalStorage('theme', 'light');
    const [searchQuery, setSearchQuery] = useState('');
    const [selectedItems, setSelectedItems] = useState([]);

    // Fetch data with custom hook
    const { data: users, loading, error } = useFetch('/api/users');

    const themeContextValue = useMemo(() => ({
        theme,
        toggleTheme: () => setTheme(prev => prev === 'light' ? 'dark' : 'light')
    }), [theme, setTheme]);

    const filteredUsers = useMemo(() => {
        if (!users || !searchQuery) return users || [];

        return users.filter(user =>
            user.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
            user.email.toLowerCase().includes(searchQuery.toLowerCase())
        );
    }, [users, searchQuery]);

    const tableColumns = useMemo(() => [
        {
            key: 'name',
            title: 'Name',
            render: (value, user) => (
                <div className="user-name">
                    <img
                        src={user.avatar || '/default-avatar.png'}
                        alt={`${value}'s avatar`}
                        className="user-avatar"
                    />
                    <span>{value}</span>
                </div>
            )
        },
        {
            key: 'email',
            title: 'Email'
        },
        {
            key: 'role',
            title: 'Role',
            render: (value) => (
                <span className={`role-badge role-${value.toLowerCase()}`}>
                    {value}
                </span>
            )
        },
        {
            key: 'lastActive',
            title: 'Last Active',
            render: (value) => new Date(value).toLocaleDateString()
        }
    ], []);

    const handleSearch = useCallback((query) => {
        setSearchQuery(query);
    }, []);

    const handleRowClick = useCallback((user, index) => {
        console.log('Row clicked:', user, index);
        setSelectedItems(prev =>
            prev.includes(user.id)
                ? prev.filter(id => id !== user.id)
                : [...prev, user.id]
        );
    }, []);

    const handleRefresh = useCallback(async () => {
        window.location.reload();
    }, []);

    if (error) {
        return (
            <div className="error-state">
                <h2>Error Loading Data</h2>
                <p>{error}</p>
                <FancyButton onClick={handleRefresh}>
                    Try Again
                </FancyButton>
            </div>
        );
    }

    return (
        <ThemeContext.Provider value={themeContextValue}>
            <div className={`app app--${theme}`}>
                <header className="app-header">
                    <h1>User Management</h1>
                    <div className="header-controls">
                        <SearchInput
                            onSearch={handleSearch}
                            placeholder="Search users..."
                        />
                        <FancyButton
                            variant="secondary"
                            onClick={themeContextValue.toggleTheme}
                        >
                            {theme === 'light' ? '🌙' : '☀️'}
                        </FancyButton>
                    </div>
                </header>

                <main className="app-main">
                    {selectedItems.length > 0 && (
                        <div className="selection-info">
                            <p>{selectedItems.length} user(s) selected</p>
                            <FancyButton
                                variant="danger"
                                size="small"
                                onClick={() => setSelectedItems([])}
                            >
                                Clear Selection
                            </FancyButton>
                        </div>
                    )}

                    <DataTable
                        data={filteredUsers}
                        columns={tableColumns}
                        onRowClick={handleRowClick}
                        loading={loading}
                        emptyMessage={
                            searchQuery
                                ? `No users found matching "${searchQuery}"`
                                : "No users available"
                        }
                    />
                </main>

                <footer className="app-footer">
                    <p>React Component Example - {filteredUsers.length} users displayed</p>
                </footer>
            </div>
        </ThemeContext.Provider>
    );
};

App.displayName = 'App';

// Export components
export default App;
export {
    DataTable, FancyButton, SearchInput, ThemeContext, useDebounce,
    useFetch, useLocalStorage, withTheme
};
