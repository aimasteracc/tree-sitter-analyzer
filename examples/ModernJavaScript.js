/**
 * Modern JavaScript Demo - Comprehensive Feature Showcase
 *
 * This file demonstrates modern JavaScript features and patterns
 * that the enhanced JavaScript plugin can analyze and extract.
 *
 * @author tree-sitter-analyzer
 * @version 1.0.0
 */

// ES6+ Import statements
import { debounce } from 'lodash';
import React, { useCallback, useEffect, useState } from 'react';

// Dynamic imports
const loadModule = async (moduleName) => {
    const module = await import(`./modules/${moduleName}`);
    return module.default;
};

// Constants and variables with different scopes
const API_BASE_URL = 'https://api.example.com';
let globalCounter = 0;
var legacyVariable = 'still supported';

// Destructuring assignments
const { name, age, ...otherProps } = userProfile;
const [first, second, ...rest] = arrayData;

// Modern class with various method types
class ModernComponent extends React.Component {
    // Class fields (properties)
    state = {
        count: 0,
        isLoading: false,
        data: null
    };

    // Private fields
    #privateCounter = 0;
    #secretKey = 'hidden-value';

    /**
     * Constructor with parameter destructuring
     * @param {Object} props - Component properties
     * @param {string} props.title - Component title
     * @param {Function} props.onUpdate - Update callback
     */
    constructor({ title, onUpdate, ...otherProps }) {
        super(otherProps);
        this.title = title;
        this.onUpdate = onUpdate;
    }

    // Static methods
    static createInstance(config) {
        return new ModernComponent(config);
    }

    static validateProps(props) {
        return props && typeof props === 'object';
    }

    // Getter and setter methods
    get displayTitle() {
        return `Component: ${this.title}`;
    }

    set displayTitle(value) {
        this.title = value.replace('Component: ', '');
    }

    // Async methods
    async fetchData(endpoint) {
        try {
            this.setState({ isLoading: true });

            const response = await fetch(`${API_BASE_URL}${endpoint}`);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();
            this.setState({ data, isLoading: false });
            return data;
        } catch (error) {
            console.error('Failed to fetch data:', error);
            this.setState({ isLoading: false });
            throw error;
        } finally {
            // Cleanup code
            this.#logActivity('fetch_completed');
        }
    }

    // Private methods
    #logActivity(activity) {
        this.#privateCounter++;
        console.log(`Activity: ${activity}, Count: ${this.#privateCounter}`);
    }

    #validateData(data) {
        return data && typeof data === 'object' && Object.keys(data).length > 0;
    }

    // Event handlers with arrow functions
    handleClick = (event) => {
        event.preventDefault();
        this.setState(prevState => ({
            count: prevState.count + 1
        }));

        // Callback with optional chaining
        this.onUpdate?.(this.state.count + 1);
    };

    handleSubmit = async (formData) => {
        if (!this.#validateData(formData)) {
            return false;
        }

        try {
            await this.fetchData('/submit');
            return true;
        } catch (error) {
            return false;
        }
    };

    // Generator method
    *generateSequence(start = 0, end = 10) {
        for (let i = start; i < end; i++) {
            yield i * 2;
        }
    }

    // Method with complex control flow
    processData(items, options = {}) {
        const { filter = null, transform = null, sort = false } = options;
        let result = [...items]; // Spread operator

        // Conditional processing
        if (filter) {
            result = result.filter(filter);
        }

        // Transform with optional chaining and nullish coalescing
        if (transform) {
            result = result.map(item => transform(item) ?? item);
        }

        // Sorting with multiple conditions
        if (sort) {
            result.sort((a, b) => {
                if (a.priority !== b.priority) {
                    return b.priority - a.priority;
                } else if (a.name && b.name) {
                    return a.name.localeCompare(b.name);
                } else {
                    return 0;
                }
            });
        }

        return result;
    }

    // JSX render method
    render() {
        const { count, isLoading, data } = this.state;

        return (
            <div className="modern-component">
                <h1>{this.displayTitle}</h1>

                {isLoading ? (
                    <div className="loading">Loading...</div>
                ) : (
                    <div className="content">
                        <p>Count: {count}</p>
                        <button onClick={this.handleClick}>
                            Increment
                        </button>

                        {data && (
                            <div className="data-display">
                                {Object.entries(data).map(([key, value]) => (
                                    <div key={key} className="data-item">
                                        <span className="key">{key}:</span>
                                        <span className="value">{JSON.stringify(value)}</span>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                )}
            </div>
        );
    }
}

// Function declarations with various patterns
function traditionalFunction(param1, param2) {
    return param1 + param2;
}

// Async function declaration
async function fetchUserData(userId) {
    const user = await fetch(`/api/users/${userId}`);
    return user.json();
}

// Generator function
function* fibonacciSequence(limit = 10) {
    let a = 0, b = 1;
    let count = 0;

    while (count < limit) {
        yield a;
        [a, b] = [b, a + b];
        count++;
    }
}

// Arrow functions with various syntaxes
const simpleArrow = x => x * 2;
const multiParamArrow = (a, b) => a + b;
const blockArrow = (items) => {
    return items
        .filter(item => item.active)
        .map(item => item.name)
        .sort();
};

// Async arrow function
const fetchAndProcess = async (url) => {
    try {
        const response = await fetch(url);
        const data = await response.json();
        return data.map(item => ({ ...item, processed: true }));
    } catch (error) {
        console.error('Fetch error:', error);
        return [];
    }
};

// Higher-order functions and closures
const createCounter = (initialValue = 0) => {
    let count = initialValue;

    return {
        increment: () => ++count,
        decrement: () => --count,
        getValue: () => count,
        reset: () => { count = initialValue; }
    };
};

// Function with destructuring parameters
const processUser = ({
    name,
    email,
    age = 18,
    preferences = {},
    ...metadata
}) => {
    const { theme = 'light', language = 'en' } = preferences;

    return {
        displayName: name.toUpperCase(),
        contact: email.toLowerCase(),
        isAdult: age >= 18,
        settings: { theme, language },
        extra: metadata
    };
};

// Template literals and tagged templates
const createMessage = (user, action) => {
    const timestamp = new Date().toISOString();
    return `
        User: ${user.name}
        Action: ${action}
        Time: ${timestamp}
        Status: ${user.isActive ? 'Active' : 'Inactive'}
    `;
};

// Tagged template function
const html = (strings, ...values) => {
    return strings.reduce((result, string, i) => {
        const value = values[i] ? String(values[i]).replace(/[<>&'"]/g, char => {
            switch (char) {
                case '<': return '&lt;';
                case '>': return '&gt;';
                case '&': return '&amp;';
                case "'": return '&#x27;';
                case '"': return '&quot;';
                default: return char;
            }
        }) : '';
        return result + string + value;
    }, '');
};

// Complex object with method properties
const apiClient = {
    baseURL: API_BASE_URL,
    timeout: 5000,

    // Method shorthand
    async get(endpoint, params = {}) {
        const url = new URL(endpoint, this.baseURL);
        Object.entries(params).forEach(([key, value]) => {
            url.searchParams.append(key, value);
        });

        const response = await fetch(url, {
            method: 'GET',
            headers: this.getHeaders(),
            signal: AbortSignal.timeout(this.timeout)
        });

        return this.handleResponse(response);
    },

    // Computed property names
    [`post`](endpoint, data) {
        return fetch(`${this.baseURL}${endpoint}`, {
            method: 'POST',
            headers: {
                ...this.getHeaders(),
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(data)
        }).then(response => this.handleResponse(response));
    },

    getHeaders() {
        return {
            'Authorization': `Bearer ${this.getToken()}`,
            'X-Client-Version': '1.0.0'
        };
    },

    getToken() {
        return localStorage.getItem('authToken') || '';
    },

    async handleResponse(response) {
        if (!response.ok) {
            const error = await response.text();
            throw new Error(`API Error: ${response.status} - ${error}`);
        }

        const contentType = response.headers.get('content-type');
        if (contentType?.includes('application/json')) {
            return response.json();
        }

        return response.text();
    }
};

// Event handling and DOM manipulation
const setupEventListeners = () => {
    document.addEventListener('DOMContentLoaded', () => {
        const buttons = document.querySelectorAll('.action-button');

        buttons.forEach(button => {
            button.addEventListener('click', debounce(async (event) => {
                const action = event.target.dataset.action;

                try {
                    await handleAction(action, event.target);
                } catch (error) {
                    console.error(`Action failed: ${action}`, error);
                }
            }, 300));
        });
    });

    // Custom event handling
    window.addEventListener('customEvent', (event) => {
        const { detail } = event;
        console.log('Custom event received:', detail);
    });
};

// Async/await with error handling
const handleAction = async (action, element) => {
    const loadingClass = 'loading';
    element.classList.add(loadingClass);

    try {
        switch (action) {
            case 'save':
                await apiClient.post('/save', { data: 'example' });
                break;
            case 'delete':
                await apiClient.post('/delete', { id: element.dataset.id });
                break;
            case 'refresh':
                location.reload();
                break;
            default:
                throw new Error(`Unknown action: ${action}`);
        }

        // Success feedback
        element.classList.add('success');
        setTimeout(() => element.classList.remove('success'), 2000);

    } finally {
        element.classList.remove(loadingClass);
    }
};

// Module pattern with IIFE
const AppModule = (() => {
    let privateState = {
        initialized: false,
        config: {}
    };

    const privateMethod = (data) => {
        console.log('Private method called with:', data);
        return data.processed = true;
    };

    return {
        init(config = {}) {
            if (privateState.initialized) {
                console.warn('App already initialized');
                return;
            }

            privateState.config = { ...config };
            privateState.initialized = true;

            setupEventListeners();
            console.log('App initialized with config:', config);
        },

        getState() {
            return { ...privateState };
        },

        processData(data) {
            return privateMethod(data);
        }
    };
})();

// React hooks (custom)
const useCounter = (initialValue = 0) => {
    const [count, setCount] = useState(initialValue);

    const increment = useCallback(() => {
        setCount(prev => prev + 1);
    }, []);

    const decrement = useCallback(() => {
        setCount(prev => prev - 1);
    }, []);

    const reset = useCallback(() => {
        setCount(initialValue);
    }, [initialValue]);

    return { count, increment, decrement, reset };
};

// React functional component
const FunctionalComponent = ({ title, items = [], onItemClick }) => {
    const { count, increment } = useCounter(0);
    const [filter, setFilter] = useState('');

    useEffect(() => {
        console.log(`Component mounted with ${items.length} items`);

        return () => {
            console.log('Component cleanup');
        };
    }, [items.length]);

    const filteredItems = items.filter(item =>
        item.name.toLowerCase().includes(filter.toLowerCase())
    );

    const handleItemClick = useCallback((item) => {
        increment();
        onItemClick?.(item);
    }, [increment, onItemClick]);

    return (
        <div className="functional-component">
            <h2>{title} (Clicked: {count})</h2>

            <input
                type="text"
                placeholder="Filter items..."
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
            />

            <ul className="item-list">
                {filteredItems.map((item, index) => (
                    <li
                        key={item.id || index}
                        onClick={() => handleItemClick(item)}
                        className={item.active ? 'active' : 'inactive'}
                    >
                        {item.name}
                        {item.description && (
                            <span className="description">
                                {item.description}
                            </span>
                        )}
                    </li>
                ))}
            </ul>

            {filteredItems.length === 0 && (
                <p className="no-items">No items found</p>
            )}
        </div>
    );
};

// Export statements (various types)
export default ModernComponent;
export * from './utils/helpers';
export { apiClient as API, FunctionalComponent, useCounter };

// CommonJS compatibility
if (typeof module !== 'undefined' && module.exports) {
    module.exports = ModernComponent;
    module.exports.FunctionalComponent = FunctionalComponent;
    module.exports.useCounter = useCounter;
}

// Global initialization
if (typeof window !== 'undefined') {
    window.AppModule = AppModule;

    // Initialize when DOM is ready
    document.addEventListener('DOMContentLoaded', () => {
        AppModule.init({
            debug: process.env.NODE_ENV === 'development',
            apiUrl: API_BASE_URL
        });
    });
}
