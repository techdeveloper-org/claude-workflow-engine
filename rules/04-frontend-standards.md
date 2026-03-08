---
description: "Level 2.1 - Frontend development standards (React, TypeScript, Angular)"
paths:
  - "src/**/*.ts"
  - "src/**/*.tsx"
  - "src/**/*.js"
  - "src/**/*.jsx"
  - "app/**/*.ts"
  - "app/**/*.tsx"
priority: high
---

# Frontend Standards (Level 2.1 - React/TypeScript/Angular)

**PURPOSE:** Enforce frontend development standards for consistency, performance, accessibility, and maintainability.

---

## 1. Project Structure & Organization

✅ **Feature-based folder organization:**

```
src/
├── features/
│   ├── auth/
│   │   ├── components/
│   │   │   ├── LoginForm.tsx
│   │   │   ├── RegisterForm.tsx
│   │   │   └── AuthGuard.tsx
│   │   ├── services/
│   │   │   └── authService.ts
│   │   ├── hooks/
│   │   │   ├── useAuth.ts
│   │   │   └── useLogin.ts
│   │   ├── store/
│   │   │   └── authSlice.ts
│   │   ├── types/
│   │   │   └── auth.types.ts
│   │   ├── constants/
│   │   │   └── authConstants.ts
│   │   └── index.ts
│   ├── users/
│   │   ├── components/
│   │   ├── services/
│   │   ├── hooks/
│   │   ├── store/
│   │   └── types/
│   └── dashboard/
│       ├── components/
│       └── ...
├── shared/
│   ├── components/          # Reusable components
│   │   ├── Button.tsx
│   │   ├── Modal.tsx
│   │   ├── Spinner.tsx
│   │   └── ErrorBoundary.tsx
│   ├── hooks/               # Reusable hooks
│   │   ├── useApi.ts
│   │   ├── useLocalStorage.ts
│   │   └── useDebounce.ts
│   ├── utils/               # Utility functions
│   │   ├── formatters.ts
│   │   ├── validators.ts
│   │   └── apiHelpers.ts
│   ├── types/               # Global types
│   │   └── common.types.ts
│   ├── constants/           # Global constants
│   │   └── appConstants.ts
│   └── styles/              # Global styles
│       └── globals.css
├── assets/
│   ├── images/
│   ├── icons/
│   └── fonts/
├── config/
│   └── apiConfig.ts
├── App.tsx
├── main.tsx
└── index.css
```

---

## 2. Component Patterns

✅ **Functional components with TypeScript:**

```typescript
// ✅ CORRECT - Functional component with proper typing
import React from 'react';

interface UserCardProps {
  userId: number;
  userName: string;
  email: string;
  onDelete?: (id: number) => void;
}

export const UserCard: React.FC<UserCardProps> = ({
  userId,
  userName,
  email,
  onDelete
}) => {
  const handleDelete = () => {
    onDelete?.(userId);
  };

  return (
    <div className="user-card">
      <h3>{userName}</h3>
      <p>{email}</p>
      <button onClick={handleDelete}>Delete</button>
    </div>
  );
};

// ✗ WRONG - Class component (outdated)
class UserCard extends React.Component { }

// ✗ WRONG - No TypeScript types
function UserCard({ userId, userName, email, onDelete }) { }
```

✅ **Custom hooks for logic reuse:**

```typescript
// ✅ CORRECT - Custom hook with proper typing
interface UseUserReturn {
  user: User | null;
  loading: boolean;
  error: Error | null;
  refetch: () => Promise<void>;
}

export const useUser = (userId: number): UseUserReturn => {
  const [user, setUser] = React.useState<User | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<Error | null>(null);

  const fetchUser = React.useCallback(async () => {
    try {
      setLoading(true);
      const data = await apiClient.get(`/users/${userId}`);
      setUser(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err : new Error('Unknown error'));
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, [userId]);

  React.useEffect(() => {
    fetchUser();
  }, [fetchUser]);

  return { user, loading, error, refetch: fetchUser };
};

// ✗ WRONG - Logic in component
function UserCard({ userId }) {
  const [user, setUser] = React.useState(null);
  // Fetch logic mixed in component
}
```

---

## 3. Type Safety (TypeScript)

✅ **Always use explicit types:**

```typescript
// ✅ CORRECT - Explicit types throughout
interface ApiResponse<T> {
  status: 'success' | 'error';
  data: T | null;
  error: string | null;
  timestamp: string;
}

interface User {
  id: number;
  name: string;
  email: string;
  role: 'admin' | 'user' | 'guest';
  createdAt: Date;
}

const fetchUser = async (userId: number): Promise<User> => {
  const response = await fetch(`/api/users/${userId}`);
  if (!response.ok) {
    throw new Error('Failed to fetch user');
  }
  const data = await response.json();
  return data as User;
};

// ✗ WRONG - No types
const fetchUser = (userId) => {
  return fetch(`/api/users/${userId}`)
    .then(r => r.json());
};

// ✗ WRONG - Using 'any'
const fetchUser = (userId: any): any => {
  // ...
};
```

✅ **Avoid 'any' type:**

```typescript
// ✗ WRONG
const handleChange = (e: any) => {
  setState(e.target.value);
};

// ✓ CORRECT
const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
  setState(e.currentTarget.value);
};
```

---

## 4. State Management

✅ **Use Redux/Redux Toolkit or Context for global state:**

```typescript
// ✅ CORRECT - Redux Toolkit slice
import { createSlice, createAsyncThunk, PayloadAction } from '@reduxjs/toolkit';

interface UserState {
  users: User[];
  loading: boolean;
  error: string | null;
}

export const fetchUsers = createAsyncThunk(
  'users/fetchUsers',
  async (_, { rejectWithValue }) => {
    try {
      const response = await apiClient.get('/users');
      return response.data;
    } catch (error) {
      return rejectWithValue((error as Error).message);
    }
  }
);

const userSlice = createSlice({
  name: 'users',
  initialState: {
    users: [],
    loading: false,
    error: null
  } as UserState,
  reducers: {
    clearError: (state) => {
      state.error = null;
    }
  },
  extraReducers: (builder) => {
    builder
      .addCase(fetchUsers.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(fetchUsers.fulfilled, (state, action: PayloadAction<User[]>) => {
        state.loading = false;
        state.users = action.payload;
      })
      .addCase(fetchUsers.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload as string;
      });
  }
});

export default userSlice.reducer;
```

✅ **Local state with useState for component-specific data:**

```typescript
// ✅ CORRECT - useState for form fields
const [formData, setFormData] = React.useState<FormData>({
  name: '',
  email: '',
  password: ''
});

const handleChange = (field: keyof FormData) => (
  e: React.ChangeEvent<HTMLInputElement>
) => {
  setFormData(prev => ({
    ...prev,
    [field]: e.currentTarget.value
  }));
};
```

❌ **NEVER use Redux for local component state:**

```typescript
// ✗ WRONG - Overkill for local state
// Don't store form field values in Redux
```

---

## 5. API Integration

✅ **Centralized API client:**

```typescript
// services/apiClient.ts
import axios, { AxiosInstance, AxiosError } from 'axios';

class ApiClient {
  private instance: AxiosInstance;

  constructor(baseURL: string) {
    this.instance = axios.create({
      baseURL,
      timeout: 10000,
      headers: {
        'Content-Type': 'application/json'
      }
    });

    // Add auth token to requests
    this.instance.interceptors.request.use((config) => {
      const token = localStorage.getItem('authToken');
      if (token) {
        config.headers.Authorization = `Bearer ${token}`;
      }
      return config;
    });

    // Handle errors globally
    this.instance.interceptors.response.use(
      (response) => response,
      (error: AxiosError) => {
        if (error.response?.status === 401) {
          // Handle unauthorized - clear token, redirect to login
          localStorage.removeItem('authToken');
          window.location.href = '/login';
        }
        return Promise.reject(error);
      }
    );
  }

  async get<T>(url: string) {
    return this.instance.get<T>(url);
  }

  async post<T>(url: string, data: unknown) {
    return this.instance.post<T>(url, data);
  }

  async put<T>(url: string, data: unknown) {
    return this.instance.put<T>(url, data);
  }

  async delete<T>(url: string) {
    return this.instance.delete<T>(url);
  }
}

export const apiClient = new ApiClient(import.meta.env.VITE_API_URL);
```

✅ **Custom hook for API calls:**

```typescript
interface UseApiOptions<T> {
  onSuccess?: (data: T) => void;
  onError?: (error: Error) => void;
}

export const useApi = <T,>(
  url: string,
  options?: UseApiOptions<T>
) => {
  const [data, setData] = React.useState<T | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<Error | null>(null);

  React.useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        const response = await apiClient.get<T>(url);
        setData(response.data);
        options?.onSuccess?.(response.data);
      } catch (err) {
        const error = err instanceof Error ? err : new Error('API call failed');
        setError(error);
        options?.onError?.(error);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [url]);

  return { data, loading, error };
};
```

---

## 6. Error Handling

✅ **Error boundaries for component errors:**

```typescript
interface ErrorBoundaryProps {
  children: React.ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends React.Component<
  ErrorBoundaryProps,
  ErrorBoundaryState
> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error('Error caught:', error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="error-container">
          <h2>Something went wrong</h2>
          <p>{this.state.error?.message}</p>
          <button onClick={() => window.location.reload()}>
            Reload Page
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}
```

✅ **Error handling in async operations:**

```typescript
// ✅ CORRECT
const handleSubmit = async (data: FormData) => {
  try {
    setLoading(true);
    setError(null);
    const response = await apiClient.post('/users', data);
    setSuccess('User created successfully');
    // Reset form or navigate
  } catch (err) {
    const errorMessage = err instanceof AxiosError
      ? err.response?.data?.message || err.message
      : 'An unexpected error occurred';
    setError(errorMessage);
    console.error('Submission error:', err);
  } finally {
    setLoading(false);
  }
};

// ✗ WRONG - Silent error
const handleSubmit = async (data) => {
  try {
    const response = await apiClient.post('/users', data);
    setSuccess(true);
  } catch (err) {
    // Silently fails!
  }
};
```

---

## 7. Styling & CSS

✅ **Use CSS modules or styled-components with TypeScript:**

```typescript
// ✅ CORRECT - CSS Modules
import styles from './UserCard.module.css';

export const UserCard: React.FC<UserCardProps> = (props) => (
  <div className={styles.card}>
    <h3 className={styles.title}>{props.userName}</h3>
  </div>
);
```

```typescript
// ✅ CORRECT - Styled Components with TypeScript
import styled from 'styled-components';

interface CardProps {
  isHighlighted: boolean;
}

const StyledCard = styled.div<CardProps>`
  padding: 16px;
  background-color: ${props => props.isHighlighted ? '#f0f0f0' : 'white'};
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
`;

export const UserCard = (props) => (
  <StyledCard isHighlighted={props.isAdmin}>
    {/* Content */}
  </StyledCard>
);
```

❌ **NEVER use inline styles or global CSS classes:**

```typescript
// ✗ WRONG - Inline styles
<div style={{ color: 'red', padding: '10px' }}>Text</div>

// ✗ WRONG - Global class names without scoping
<div className="card">Text</div>
```

---

## 8. Accessibility (a11y)

✅ **Always include semantic HTML and ARIA labels:**

```typescript
// ✅ CORRECT - Semantic HTML with accessibility
export const NavigationMenu: React.FC = () => (
  <nav aria-label="Main navigation">
    <ul role="menubar">
      <li role="presentation">
        <a href="/dashboard" role="menuitem">Dashboard</a>
      </li>
    </ul>
  </nav>
);

export const SearchForm: React.FC = () => (
  <form onSubmit={handleSearch} aria-label="Search users">
    <label htmlFor="search-input">Search:</label>
    <input
      id="search-input"
      type="text"
      placeholder="Enter user name"
      aria-describedby="search-help"
    />
    <p id="search-help">Enter at least 3 characters</p>
    <button type="submit" aria-label="Submit search">Search</button>
  </form>
);
```

✅ **Use semantic elements (article, section, main, etc.):**

```typescript
// ✗ WRONG - Using div for everything
<div className="container">
  <div className="header">Title</div>
  <div className="content">Content</div>
</div>

// ✓ CORRECT - Semantic HTML
<article className="container">
  <header className="header">Title</header>
  <main className="content">Content</main>
</article>
```

---

## 9. Performance

✅ **Use React.memo for expensive components:**

```typescript
// ✅ CORRECT - Memoized component
interface UserListProps {
  users: User[];
  onSelect: (user: User) => void;
}

export const UserList = React.memo<UserListProps>(
  ({ users, onSelect }) => (
    <ul>
      {users.map(user => (
        <li key={user.id} onClick={() => onSelect(user)}>
          {user.name}
        </li>
      ))}
    </ul>
  ),
  (prevProps, nextProps) => {
    // Return true if props are equal (don't re-render)
    return (
      prevProps.users === nextProps.users &&
      prevProps.onSelect === nextProps.onSelect
    );
  }
);
```

✅ **Code splitting with React.lazy:**

```typescript
// ✅ CORRECT - Lazy load routes
const Dashboard = React.lazy(() => import('./features/dashboard/Dashboard'));
const Users = React.lazy(() => import('./features/users/Users'));

export const App = () => (
  <Routes>
    <Route
      path="/dashboard"
      element={
        <React.Suspense fallback={<Spinner />}>
          <Dashboard />
        </React.Suspense>
      }
    />
  </Routes>
);
```

✅ **useCallback and useMemo for expensive operations:**

```typescript
// ✅ CORRECT - Memoized callbacks
const UserForm = ({ onSave }: UserFormProps) => {
  const [formData, setFormData] = React.useState<FormData>(initialState);

  const handleSave = React.useCallback(async () => {
    await onSave(formData);
  }, [formData, onSave]);

  const computedTotal = React.useMemo(() => {
    return items.reduce((sum, item) => sum + item.price, 0);
  }, [items]);

  return (
    <div>
      <button onClick={handleSave}>Save</button>
      <p>Total: {computedTotal}</p>
    </div>
  );
};
```

---

## 10. Testing Standards

✅ **Unit tests for components and hooks:**

```typescript
import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { UserCard } from './UserCard';

describe('UserCard Component', () => {
  it('should render user information', () => {
    render(<UserCard userId={1} userName="John" email="john@example.com" />);

    expect(screen.getByText('John')).toBeInTheDocument();
    expect(screen.getByText('john@example.com')).toBeInTheDocument();
  });

  it('should call onDelete when delete button is clicked', async () => {
    const handleDelete = jest.fn();
    const user = userEvent.setup();

    render(
      <UserCard
        userId={1}
        userName="John"
        email="john@example.com"
        onDelete={handleDelete}
      />
    );

    const deleteButton = screen.getByText('Delete');
    await user.click(deleteButton);

    expect(handleDelete).toHaveBeenCalledWith(1);
  });
});
```

---

## 11. Code Organization

✅ **Organize imports logically:**

```typescript
// ✅ CORRECT - Organized imports
import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useDispatch, useSelector } from 'react-redux';

import { UserCard } from '../components/UserCard';
import { useUser } from '../hooks/useUser';
import { selectUsers } from '../store/userSlice';
import type { User } from '../types/user.types';
import { API_ENDPOINTS } from '../constants/apiConstants';
import { formatDate } from '../utils/formatters';

// Component implementation
```

✅ **Keep component files focused:**

```
UserCard/
├── UserCard.tsx           # Component
├── UserCard.module.css    # Styles
├── UserCard.test.tsx      # Tests
└── index.ts               # Export
```

---

## 12. Security

❌ **NEVER store sensitive data in localStorage:**

```typescript
// ✗ WRONG - Exposing sensitive data
localStorage.setItem('apiKey', 'sk-abc123def456');
localStorage.setItem('userPassword', password);

// ✓ CORRECT - Use secure cookies (httpOnly, Secure, SameSite)
// Store in backend, use session cookies
```

✅ **Sanitize user input:**

```typescript
// ✓ CORRECT - Use DOMPurify for untrusted HTML
import DOMPurify from 'dompurify';

const UserProfile = ({ bio }: { bio: string }) => (
  <div
    dangerouslySetInnerHTML={{
      __html: DOMPurify.sanitize(bio)
    }}
  />
);
```

✅ **Validate input before API calls:**

```typescript
// ✓ CORRECT - Validate before sending
const handleSubmit = async (formData: FormData) => {
  if (!formData.email || !formData.email.includes('@')) {
    setError('Invalid email');
    return;
  }

  await submitForm(formData);
};
```

---

## 13. Naming Conventions

✅ **PascalCase for components:**
```typescript
// ✓ CORRECT
export const UserCard = () => {}
export const LoginForm = () => {}

// ✗ WRONG
export const userCard = () => {}
export const login_form = () => {}
```

✅ **camelCase for functions and variables:**
```typescript
// ✓ CORRECT
const handleUserSubmit = () => {}
const formatUserName = (name: string) => {}

// ✗ WRONG
const HandleUserSubmit = () => {}
const format_user_name = () => {}
```

✅ **UPPER_SNAKE_CASE for constants:**
```typescript
// ✓ CORRECT
const API_BASE_URL = 'https://api.example.com';
const MAX_RETRIES = 3;
const STORAGE_KEYS = {
  AUTH_TOKEN: 'authToken',
  USER_PREFERENCES: 'userPreferences'
};

// ✗ WRONG
const apiBaseUrl = 'https://api.example.com';
const max_retries = 3;
```

---

## 14. Environment Variables

✅ **Use .env files with proper prefixes:**

```bash
# .env
VITE_API_URL=https://api.example.com
VITE_APP_NAME=MyApp
VITE_MAX_RETRIES=3
```

```typescript
// Access with proper types
const API_URL = import.meta.env.VITE_API_URL;
const APP_NAME = import.meta.env.VITE_APP_NAME;
const MAX_RETRIES = parseInt(import.meta.env.VITE_MAX_RETRIES || '3');
```

---

**ENFORCEMENT:** These standards apply to all frontend code. Violations caught during code review and pre-commit hooks.
