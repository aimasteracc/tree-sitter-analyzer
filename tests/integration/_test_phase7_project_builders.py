"""Project builders for Phase 7 end-to-end integration tests."""

import json
from pathlib import Path


def create_java_enterprise_structure(project_root: Path) -> None:
    """エンタープライズJavaプロジェクト構造"""
    java_root = (
        project_root / "backend" / "src" / "main" / "java" / "com" / "enterprise"
    )
    java_root.mkdir(parents=True)

    # Core domain models
    (java_root / "domain").mkdir()
    (java_root / "domain" / "User.java").write_text(
        """
package com.enterprise.domain;

import java.time.LocalDateTime;
import java.util.List;
import java.util.UUID;

/**
 * User domain entity for enterprise application
 */
public class User {
    private UUID id;
    private String username;
    private String email;
    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;
    private List<Role> roles;

    public User(String username, String email) {
        this.id = UUID.randomUUID();
        this.username = username;
        this.email = email;
        this.createdAt = LocalDateTime.now();
        this.updatedAt = LocalDateTime.now();
    }

    // Getters and setters
    public UUID getId() { return id; }
    public String getUsername() { return username; }
    public String getEmail() { return email; }
    public LocalDateTime getCreatedAt() { return createdAt; }
    public LocalDateTime getUpdatedAt() { return updatedAt; }
    public List<Role> getRoles() { return roles; }

    public void setUsername(String username) {
        this.username = username;
        this.updatedAt = LocalDateTime.now();
    }

    public void setEmail(String email) {
        this.email = email;
        this.updatedAt = LocalDateTime.now();
    }

    public void setRoles(List<Role> roles) {
        this.roles = roles;
        this.updatedAt = LocalDateTime.now();
    }

    public boolean hasRole(String roleName) {
        return roles.stream()
            .anyMatch(role -> role.getName().equals(roleName));
    }

    public void addRole(Role role) {
        if (!roles.contains(role)) {
            roles.add(role);
            this.updatedAt = LocalDateTime.now();
        }
    }

    public void removeRole(Role role) {
        if (roles.remove(role)) {
            this.updatedAt = LocalDateTime.now();
        }
    }
}
"""
    )

    # Service layer
    (java_root / "service").mkdir()
    (java_root / "service" / "UserService.java").write_text(
        """
package com.enterprise.service;

import com.enterprise.domain.User;
import com.enterprise.repository.UserRepository;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

/**
 * User service for business logic
 */
@Service
@Transactional
public class UserService {

    @Autowired
    private UserRepository userRepository;

    @Autowired
    private EmailService emailService;

    @Autowired
    private AuditService auditService;

    public User createUser(String username, String email) {
        validateUserInput(username, email);

        if (userRepository.existsByUsername(username)) {
            throw new UserAlreadyExistsException("Username already exists: " + username);
        }

        if (userRepository.existsByEmail(email)) {
            throw new UserAlreadyExistsException("Email already exists: " + email);
        }

        User user = new User(username, email);
        User savedUser = userRepository.save(user);

        auditService.logUserCreation(savedUser);
        emailService.sendWelcomeEmail(savedUser);

        return savedUser;
    }

    public Optional<User> findById(UUID id) {
        return userRepository.findById(id);
    }

    public Optional<User> findByUsername(String username) {
        return userRepository.findByUsername(username);
    }

    public List<User> findAllUsers() {
        return userRepository.findAll();
    }

    public User updateUser(UUID id, String username, String email) {
        User user = userRepository.findById(id)
            .orElseThrow(() -> new UserNotFoundException("User not found: " + id));

        validateUserInput(username, email);

        user.setUsername(username);
        user.setEmail(email);

        User updatedUser = userRepository.save(user);
        auditService.logUserUpdate(updatedUser);

        return updatedUser;
    }

    public void deleteUser(UUID id) {
        User user = userRepository.findById(id)
            .orElseThrow(() -> new UserNotFoundException("User not found: " + id));

        userRepository.delete(user);
        auditService.logUserDeletion(user);
    }

    private void validateUserInput(String username, String email) {
        if (username == null || username.trim().isEmpty()) {
            throw new IllegalArgumentException("Username cannot be empty");
        }

        if (email == null || email.trim().isEmpty()) {
            throw new IllegalArgumentException("Email cannot be empty");
        }

        if (!isValidEmail(email)) {
            throw new IllegalArgumentException("Invalid email format: " + email);
        }
    }

    private boolean isValidEmail(String email) {
        return email.contains("@") && email.contains(".");
    }
}
"""
    )


def create_python_enterprise_structure(project_root: Path) -> None:
    """エンタープライズPythonプロジェクト構造"""
    python_root = project_root / "backend" / "python" / "enterprise_app"
    python_root.mkdir(parents=True)

    # Core models
    (python_root / "models").mkdir()
    (python_root / "models" / "__init__.py").write_text("")
    (python_root / "models" / "user.py").write_text(
        '''
#!/usr/bin/env python3
"""
User model for enterprise application
"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID, uuid4
from dataclasses import dataclass, field
from enum import Enum


class UserStatus(Enum):
    """User status enumeration"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    DELETED = "deleted"


@dataclass
class Role:
    """User role model"""
    id: UUID = field(default_factory=uuid4)
    name: str = ""
    description: str = ""
    permissions: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)

    def has_permission(self, permission: str) -> bool:
        """Check if role has specific permission"""
        return permission in self.permissions

    def add_permission(self, permission: str) -> None:
        """Add permission to role"""
        if permission not in self.permissions:
            self.permissions.append(permission)

    def remove_permission(self, permission: str) -> None:
        """Remove permission from role"""
        if permission in self.permissions:
            self.permissions.remove(permission)


@dataclass
class User:
    """User model for enterprise application"""
    id: UUID = field(default_factory=uuid4)
    username: str = ""
    email: str = ""
    first_name: str = ""
    last_name: str = ""
    status: UserStatus = UserStatus.ACTIVE
    roles: List[Role] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    last_login: Optional[datetime] = None
    login_count: int = 0

    def __post_init__(self):
        """Post-initialization validation"""
        self.validate()

    def validate(self) -> None:
        """Validate user data"""
        if not self.username:
            raise ValueError("Username is required")

        if not self.email:
            raise ValueError("Email is required")

        if "@" not in self.email:
            raise ValueError("Invalid email format")

    @property
    def full_name(self) -> str:
        """Get user's full name"""
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def is_active(self) -> bool:
        """Check if user is active"""
        return self.status == UserStatus.ACTIVE

    def has_role(self, role_name: str) -> bool:
        """Check if user has specific role"""
        return any(role.name == role_name for role in self.roles)

    def has_permission(self, permission: str) -> bool:
        """Check if user has specific permission"""
        return any(role.has_permission(permission) for role in self.roles)

    def add_role(self, role: Role) -> None:
        """Add role to user"""
        if not self.has_role(role.name):
            self.roles.append(role)
            self.updated_at = datetime.now()

    def remove_role(self, role_name: str) -> None:
        """Remove role from user"""
        self.roles = [role for role in self.roles if role.name != role_name]
        self.updated_at = datetime.now()

    def update_login(self) -> None:
        """Update login information"""
        self.last_login = datetime.now()
        self.login_count += 1
        self.updated_at = datetime.now()

    def deactivate(self) -> None:
        """Deactivate user"""
        self.status = UserStatus.INACTIVE
        self.updated_at = datetime.now()

    def activate(self) -> None:
        """Activate user"""
        self.status = UserStatus.ACTIVE
        self.updated_at = datetime.now()

    def suspend(self) -> None:
        """Suspend user"""
        self.status = UserStatus.SUSPENDED
        self.updated_at = datetime.now()

    def to_dict(self) -> dict:
        """Convert user to dictionary"""
        return {
            "id": str(self.id),
            "username": self.username,
            "email": self.email,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "full_name": self.full_name,
            "status": self.status.value,
            "roles": [{"name": role.name, "permissions": role.permissions} for role in self.roles],
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "last_login": self.last_login.isoformat() if self.last_login else None,
            "login_count": self.login_count,
            "is_active": self.is_active
        }
'''
    )


def create_javascript_enterprise_structure(project_root: Path) -> None:
    """エンタープライズJavaScriptプロジェクト構造"""
    js_root = project_root / "frontend" / "src"
    js_root.mkdir(parents=True)

    # Components
    (js_root / "components").mkdir()
    (js_root / "components" / "UserManagement.js").write_text(
        """
/**
 * User Management Component
 * Enterprise-grade React component for user management
 */

import React, { useState, useEffect, useCallback } from 'react';

const UserManagement = () => {
    const [users, setUsers] = useState([]);
    const [loading, setLoading] = useState(false);
    const [modalVisible, setModalVisible] = useState(false);
    const [editingUser, setEditingUser] = useState(null);

    // Load users on component mount
    useEffect(() => {
        loadUsers();
    }, []);

    /**
     * Load all users from the server
     */
    const loadUsers = useCallback(async () => {
        setLoading(true);
        try {
            const response = await fetch('/api/users');
            const data = await response.json();
            setUsers(data);
        } catch (error) {
            console.error('Failed to load users:', error);
        } finally {
            setLoading(false);
        }
    }, []);

    /**
     * Handle user creation or update
     */
    const handleSubmit = async (values) => {
        try {
            setLoading(true);

            let response;
            if (editingUser) {
                response = await fetch(`/api/users/${editingUser.id}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(values)
                });
            } else {
                response = await fetch('/api/users', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(values)
                });
            }

            if (response.ok) {
                setModalVisible(false);
                setEditingUser(null);
                await loadUsers();
            }

        } catch (error) {
            console.error('Operation failed:', error);
        } finally {
            setLoading(false);
        }
    };

    /**
     * Handle user deletion
     */
    const handleDelete = async (userId) => {
        try {
            setLoading(true);
            const response = await fetch(`/api/users/${userId}`, {
                method: 'DELETE'
            });

            if (response.ok) {
                await loadUsers();
            }
        } catch (error) {
            console.error('Failed to delete user:', error);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="user-management">
            <h2>User Management</h2>
            <button onClick={() => setModalVisible(true)}>
                Add User
            </button>

            <table>
                <thead>
                    <tr>
                        <th>Username</th>
                        <th>Email</th>
                        <th>Status</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
                    {users.map(user => (
                        <tr key={user.id}>
                            <td>{user.username}</td>
                            <td>{user.email}</td>
                            <td>{user.status}</td>
                            <td>
                                <button onClick={() => setEditingUser(user)}>
                                    Edit
                                </button>
                                <button onClick={() => handleDelete(user.id)}>
                                    Delete
                                </button>
                            </td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
};

export default UserManagement;
"""
    )


def create_config_and_docs(project_root: Path) -> None:
    """設定ファイルとドキュメント作成"""
    # README
    (project_root / "README.md").write_text(
        """
# Enterprise Application

This is a comprehensive enterprise application demonstrating:
- Multi-language architecture (Java, Python, JavaScript)
- Microservices design patterns
- Modern frontend with React
- RESTful API design
- Security best practices

## Architecture

- Backend: Java Spring Boot + Python FastAPI
- Frontend: React with modern JavaScript
- Database: PostgreSQL
- Authentication: JWT tokens
- Monitoring: Prometheus + Grafana

## Getting Started

1. Clone the repository
2. Install dependencies
3. Configure environment variables
4. Run the application

## Testing

Run the test suite with:
```bash
npm test
mvn test
pytest
```
"""
    )

    # Package.json
    (project_root / "package.json").write_text(
        json.dumps(
            {
                "name": "enterprise-app",
                "version": "1.0.0",
                "description": "Enterprise application with multi-language support",
                "main": "index.js",
                "scripts": {
                    "start": "react-scripts start",
                    "build": "react-scripts build",
                    "test": "react-scripts test",
                    "eject": "react-scripts eject",
                },
                "dependencies": {
                    "react": "^18.0.0",
                    "react-dom": "^18.0.0",
                    "antd": "^5.0.0",
                    "axios": "^1.0.0",
                },
                "devDependencies": {
                    "react-scripts": "^5.0.0",
                    "@testing-library/react": "^13.0.0",
                    "@testing-library/jest-dom": "^5.0.0",
                },
            },
            indent=2,
        )
    )
