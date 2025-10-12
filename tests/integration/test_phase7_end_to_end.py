#!/usr/bin/env python3
"""
Phase 7: Integration & Validation - End-to-End Tests

エンタープライズグレードの統合テストスイート:
- 完全なワークフローテスト
- 実世界のユースケース検証
- パフォーマンス・セキュリティ統合検証
- 品質保証の最終確認
"""

import asyncio
import json
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List
import pytest
import psutil

from tree_sitter_analyzer.mcp.server import TreeSitterAnalyzerMCPServer
from tree_sitter_analyzer.mcp.tools.analyze_scale_tool import AnalyzeScaleTool
from tree_sitter_analyzer.mcp.tools.table_format_tool import TableFormatTool
from tree_sitter_analyzer.mcp.tools.read_partial_tool import ReadPartialTool
from tree_sitter_analyzer.mcp.tools.query_tool import QueryTool
from tree_sitter_analyzer.mcp.tools.list_files_tool import ListFilesTool
from tree_sitter_analyzer.mcp.tools.search_content_tool import SearchContentTool
from tree_sitter_analyzer.mcp.tools.find_and_grep_tool import FindAndGrepTool


class TestPhase7EndToEnd:
    """Phase 7 エンドツーエンド統合テスト"""

    @pytest.fixture(scope="class")
    def enterprise_project(self):
        """エンタープライズ規模のテストプロジェクト作成"""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            
            # 大規模Javaプロジェクト構造
            self._create_java_enterprise_structure(project_root)
            
            # 大規模Pythonプロジェクト構造
            self._create_python_enterprise_structure(project_root)
            
            # 大規模JavaScriptプロジェクト構造
            self._create_javascript_enterprise_structure(project_root)
            
            # 設定ファイルとドキュメント
            self._create_config_and_docs(project_root)
            
            yield str(project_root)

    def _create_java_enterprise_structure(self, project_root: Path):
        """エンタープライズJavaプロジェクト構造"""
        java_root = project_root / "backend" / "src" / "main" / "java" / "com" / "enterprise"
        java_root.mkdir(parents=True)
        
        # Core domain models
        (java_root / "domain").mkdir()
        (java_root / "domain" / "User.java").write_text("""
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
""")

        # Service layer
        (java_root / "service").mkdir()
        (java_root / "service" / "UserService.java").write_text("""
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
""")

    def _create_python_enterprise_structure(self, project_root: Path):
        """エンタープライズPythonプロジェクト構造"""
        python_root = project_root / "backend" / "python" / "enterprise_app"
        python_root.mkdir(parents=True)
        
        # Core models
        (python_root / "models").mkdir()
        (python_root / "models" / "__init__.py").write_text("")
        (python_root / "models" / "user.py").write_text('''
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
''')

    def _create_javascript_enterprise_structure(self, project_root: Path):
        """エンタープライズJavaScriptプロジェクト構造"""
        js_root = project_root / "frontend" / "src"
        js_root.mkdir(parents=True)
        
        # Components
        (js_root / "components").mkdir()
        (js_root / "components" / "UserManagement.js").write_text('''
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
''')

    def _create_config_and_docs(self, project_root: Path):
        """設定ファイルとドキュメント作成"""
        # README
        (project_root / "README.md").write_text("""
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
""")

        # Package.json
        (project_root / "package.json").write_text(json.dumps({
            "name": "enterprise-app",
            "version": "1.0.0",
            "description": "Enterprise application with multi-language support",
            "main": "index.js",
            "scripts": {
                "start": "react-scripts start",
                "build": "react-scripts build",
                "test": "react-scripts test",
                "eject": "react-scripts eject"
            },
            "dependencies": {
                "react": "^18.0.0",
                "react-dom": "^18.0.0",
                "antd": "^5.0.0",
                "axios": "^1.0.0"
            },
            "devDependencies": {
                "react-scripts": "^5.0.0",
                "@testing-library/react": "^13.0.0",
                "@testing-library/jest-dom": "^5.0.0"
            }
        }, indent=2))

    @pytest.mark.asyncio
    async def test_complete_enterprise_workflow(self, enterprise_project):
        """完全なエンタープライズワークフローテスト"""
        server = TreeSitterAnalyzerMCPServer()
        server.set_project_path(enterprise_project)
        
        # Phase 1: プロジェクト全体の概要把握
        overview_results = await self._analyze_project_overview(server, enterprise_project)
        
        # Phase 2: 各言語の詳細分析
        detailed_results = await self._analyze_language_details(server, enterprise_project)
        
        # Phase 3: セキュリティ・パフォーマンス検証
        security_results = await self._verify_security_compliance(server, enterprise_project)
        performance_results = await self._verify_performance_requirements(server, enterprise_project)
        
        # Phase 4: 統合検証
        integration_results = await self._verify_integration_quality(
            server, enterprise_project, overview_results, detailed_results
        )
        
        # 最終検証
        assert overview_results["success"]
        assert detailed_results["success"]
        assert security_results["success"]
        assert performance_results["success"]
        assert integration_results["success"]

    async def _analyze_project_overview(self, server: TreeSitterAnalyzerMCPServer, project_path: str) -> Dict[str, Any]:
        """プロジェクト全体の概要分析"""
        results = {"success": True, "analyses": []}
        
        # 1. ファイル一覧取得
        list_tool = ListFilesTool(project_path)
        file_list_result = await list_tool.execute({
            "roots": [project_path],
            "extensions": ["java", "py", "js", "md", "json"],
            "limit": 1000
        })
        
        assert file_list_result["success"]
        assert file_list_result["count"] > 0
        results["analyses"].append(("file_listing", file_list_result))
        
        # 2. 主要ファイルの規模チェック
        scale_tool = AnalyzeScaleTool(project_path)
        main_files = [
            "backend/src/main/java/com/enterprise/domain/User.java",
            "backend/python/enterprise_app/models/user.py",
            "frontend/src/components/UserManagement.js"
        ]
        
        for file_path in main_files:
            full_path = Path(project_path) / file_path
            if full_path.exists():
                scale_result = await scale_tool.execute({
                    "file_path": str(full_path),
                    "include_complexity": True,
                    "include_guidance": True
                })
                assert scale_result["success"]
                results["analyses"].append((f"scale_{file_path}", scale_result))
        
        return results

    async def _analyze_language_details(self, server: TreeSitterAnalyzerMCPServer, project_path: str) -> Dict[str, Any]:
        """各言語の詳細分析"""
        results = {"success": True, "analyses": []}
        
        # Java分析
        java_results = await self._analyze_java_components(server, project_path)
        results["analyses"].append(("java_analysis", java_results))
        
        # Python分析
        python_results = await self._analyze_python_components(server, project_path)
        results["analyses"].append(("python_analysis", python_results))
        
        # JavaScript分析
        js_results = await self._analyze_javascript_components(server, project_path)
        results["analyses"].append(("javascript_analysis", js_results))
        
        return results

    async def _analyze_java_components(self, server: TreeSitterAnalyzerMCPServer, project_path: str) -> Dict[str, Any]:
        """Java コンポーネント分析"""
        results = {"success": True, "components": []}
        
        # User.java の詳細分析
        user_java_path = Path(project_path) / "backend/src/main/java/com/enterprise/domain/User.java"
        if user_java_path.exists():
            # 構造分析
            table_tool = TableFormatTool(project_path)
            structure_result = await table_tool.execute({
                "file_path": str(user_java_path),
                "format_type": "full"
            })
            assert structure_result["success"]
            results["components"].append(("user_structure", structure_result))
            
            # クエリ分析
            query_tool = QueryTool(project_path)
            methods_result = await query_tool.execute({
                "file_path": str(user_java_path),
                "query_key": "methods",
                "output_format": "json"
            })
            assert methods_result["success"]
            results["components"].append(("user_methods", methods_result))
        
        return results

    async def _analyze_python_components(self, server: TreeSitterAnalyzerMCPServer, project_path: str) -> Dict[str, Any]:
        """Python コンポーネント分析"""
        results = {"success": True, "components": []}
        
        # user.py の詳細分析
        user_py_path = Path(project_path) / "backend/python/enterprise_app/models/user.py"
        if user_py_path.exists():
            # 構造分析
            table_tool = TableFormatTool(project_path)
            structure_result = await table_tool.execute({
                "file_path": str(user_py_path),
                "format_type": "full"
            })
            assert structure_result["success"]
            results["components"].append(("user_structure", structure_result))
            
            # 部分読み取り
            read_tool = ReadPartialTool(project_path)
            partial_result = await read_tool.execute({
                "file_path": str(user_py_path),
                "start_line": 1,
                "end_line": 50,
                "format": "json"
            })
            assert partial_result["success"]
            results["components"].append(("user_partial", partial_result))
        
        return results

    async def _analyze_javascript_components(self, server: TreeSitterAnalyzerMCPServer, project_path: str) -> Dict[str, Any]:
        """JavaScript コンポーネント分析"""
        results = {"success": True, "components": []}
        
        # UserManagement.js の詳細分析
        user_js_path = Path(project_path) / "frontend/src/components/UserManagement.js"
        if user_js_path.exists():
            # 構造分析
            table_tool = TableFormatTool(project_path)
            structure_result = await table_tool.execute({
                "file_path": str(user_js_path),
                "format_type": "full"
            })
            assert structure_result["success"]
            results["components"].append(("user_management_structure", structure_result))
        
        return results

    async def _verify_security_compliance(self, server: TreeSitterAnalyzerMCPServer, project_path: str) -> Dict[str, Any]:
        """セキュリティコンプライアンス検証"""
        results = {"success": True, "security_checks": []}
        
        # 1. パストラバーサル攻撃テスト
        scale_tool = AnalyzeScaleTool(project_path)
        
        malicious_paths = [
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32\\config\\sam",
            "/etc/shadow"
        ]
        
        for malicious_path in malicious_paths:
            try:
                await scale_tool.execute({"file_path": malicious_path})
                results["success"] = False  # Should not reach here
            except Exception:
                # Expected to fail - security working
                results["security_checks"].append(f"blocked_{malicious_path}")
        
        # 2. 入力サニタイゼーションテスト
        try:
            await scale_tool.execute({
                "file_path": str(Path(project_path) / "README.md"),
                "language": "<script>alert('xss')</script>"
            })
            # Should handle malicious input safely
            results["security_checks"].append("input_sanitization_passed")
        except Exception:
            # Also acceptable if it rejects malicious input
            results["security_checks"].append("input_sanitization_rejected")
        
        return results

    async def _verify_performance_requirements(self, server: TreeSitterAnalyzerMCPServer, project_path: str) -> Dict[str, Any]:
        """パフォーマンス要件検証"""
        results = {"success": True, "performance_metrics": []}
        
        # 1. 単一ツール実行時間テスト（3秒以内）
        scale_tool = AnalyzeScaleTool(project_path)
        readme_path = Path(project_path) / "README.md"
        
        start_time = time.time()
        scale_result = await scale_tool.execute({
            "file_path": str(readme_path),
            "include_complexity": True
        })
        execution_time = time.time() - start_time
        
        assert scale_result["success"]
        assert execution_time < 3.0, f"実行時間が3秒を超過: {execution_time:.2f}秒"
        results["performance_metrics"].append(("scale_tool_time", execution_time))
        
        # 2. メモリ使用量テスト
        process = psutil.Process()
        initial_memory = process.memory_info().rss
        
        # 複数ツールの並行実行
        table_tool = TableFormatTool(project_path)
        read_tool = ReadPartialTool(project_path)
        
        tasks = [
            scale_tool.execute({"file_path": str(readme_path)}),
            table_tool.execute({"file_path": str(readme_path)}),
            read_tool.execute({
                "file_path": str(readme_path),
                "start_line": 1,
                "end_line": 10
            })
        ]
        
        await asyncio.gather(*tasks)
        
        final_memory = process.memory_info().rss
        memory_increase = (final_memory - initial_memory) / 1024 / 1024  # MB
        
        assert memory_increase < 100, f"メモリ使用量増加が100MBを超過: {memory_increase:.2f}MB"
        results["performance_metrics"].append(("memory_usage", memory_increase))
        
        return results

    async def _verify_integration_quality(self, server: TreeSitterAnalyzerMCPServer, 
                                        project_path: str, overview_results: Dict, 
                                        detailed_results: Dict) -> Dict[str, Any]:
        """統合品質検証"""
        results = {"success": True, "integration_checks": []}
        
        # 1. ワークフロー一貫性テスト
        search_tool = SearchContentTool(project_path)
        
        # クラス定義の検索
        search_result = await search_tool.execute({
            "roots": [project_path],
            "query": "class",
            "include_globs": ["*.java", "*.py", "*.js"],
            "max_count": 50
        })
        
        assert search_result["success"]
        results["integration_checks"].append(("class_search", search_result["count"]))
        
        # 2. ファイル出力機能テスト
        output_file = "integration_test_output"
        search_with_output = await search_tool.execute({
            "roots": [project_path],
            "query": "function",
            "include_globs": ["*.js", "*.py"],
            "output_file": output_file,
            "suppress_output": True,
            "max_count": 20
        })
        
        assert search_with_output["success"]
        results["integration_checks"].append(("file_output_test", "passed"))
        
        # 3. 多言語対応テスト
        languages_tested = []
        test_files = [
            ("java", "backend/src/main/java/com/enterprise/domain/User.java"),
            ("python", "backend/python/enterprise_app/models/user.py"),
            ("javascript", "frontend/src/components/UserManagement.js")
        ]
        
        scale_tool = AnalyzeScaleTool(project_path)
        for lang, file_path in test_files:
            full_path = Path(project_path) / file_path
            if full_path.exists():
                try:
                    result = await scale_tool.execute({
                        "file_path": str(full_path),
                        "language": lang
                    })
                    if result["success"]:
                        languages_tested.append(lang)
                except Exception as e:
                    # 言語サポートがない場合はスキップ
                    if "not supported" in str(e).lower():
                        continue
                    raise
        
        assert len(languages_tested) >= 1, "少なくとも1つの言語がテストされる必要があります"
        results["integration_checks"].append(("languages_tested", languages_tested))
        
        return results

    @pytest.mark.asyncio
    async def test_real_world_development_workflow(self, enterprise_project):
        """実世界の開発ワークフローシミュレーション"""
        server = TreeSitterAnalyzerMCPServer()
        server.set_project_path(enterprise_project)
        
        # シナリオ1: 新機能開発のためのコード調査
        investigation_results = await self._simulate_code_investigation(server, enterprise_project)
        
        # シナリオ2: バグ修正のためのコード分析
        bug_analysis_results = await self._simulate_bug_analysis(server, enterprise_project)
        
        # シナリオ3: リファクタリングのための影響範囲調査
        refactoring_results = await self._simulate_refactoring_analysis(server, enterprise_project)
        
        # 全シナリオが成功することを確認
        assert investigation_results["success"]
        assert bug_analysis_results["success"]
        assert refactoring_results["success"]

    async def _simulate_code_investigation(self, server: TreeSitterAnalyzerMCPServer, project_path: str) -> Dict[str, Any]:
        """新機能開発のためのコード調査シミュレーション"""
        results = {"success": True, "steps": []}
        
        # Step 1: 関連するユーザー管理機能を検索
        search_tool = SearchContentTool(project_path)
        user_search = await search_tool.execute({
            "roots": [project_path],
            "query": "user",
            "case": "insensitive",
            "include_globs": ["*.java", "*.py", "*.js"],
            "max_count": 30
        })
        assert user_search["success"]
        results["steps"].append(("user_search", user_search["count"]))
        
        # Step 2: 主要なユーザークラスの詳細分析
        user_java_path = Path(project_path) / "backend/src/main/java/com/enterprise/domain/User.java"
        if user_java_path.exists():
            table_tool = TableFormatTool(project_path)
            structure_analysis = await table_tool.execute({
                "file_path": str(user_java_path),
                "format_type": "full"
            })
            assert structure_analysis["success"]
            results["steps"].append(("structure_analysis", "completed"))
        
        # Step 3: 認証関連のメソッドを検索
        auth_search = await search_tool.execute({
            "roots": [project_path],
            "query": "auth|login|password",
            "case": "insensitive",
            "include_globs": ["*.java", "*.py"],
            "max_count": 20
        })
        assert auth_search["success"]
        results["steps"].append(("auth_search", auth_search["count"]))
        
        return results

    async def _simulate_bug_analysis(self, server: TreeSitterAnalyzerMCPServer, project_path: str) -> Dict[str, Any]:
        """バグ修正のためのコード分析シミュレーション"""
        results = {"success": True, "steps": []}
        
        # Step 1: エラーハンドリング関連のコードを検索
        search_tool = SearchContentTool(project_path)
        error_search = await search_tool.execute({
            "roots": [project_path],
            "query": "exception|error|throw|catch",
            "case": "insensitive",
            "include_globs": ["*.java", "*.py", "*.js"],
            "max_count": 25
        })
        assert error_search["success"]
        results["steps"].append(("error_search", error_search["count"]))
        
        # Step 2: 特定のメソッドの詳細確認
        user_service_path = Path(project_path) / "backend/src/main/java/com/enterprise/service/UserService.java"
        if user_service_path.exists():
            read_tool = ReadPartialTool(project_path)
            method_details = await read_tool.execute({
                "file_path": str(user_service_path),
                "start_line": 30,
                "end_line": 60,
                "format": "text"
            })
            assert method_details["success"]
            results["steps"].append(("method_analysis", "completed"))
        
        # Step 3: バリデーション関連のコードを検索
        validation_search = await search_tool.execute({
            "roots": [project_path],
            "query": "validate|validation",
            "case": "insensitive",
            "include_globs": ["*.java", "*.py"],
            "max_count": 15
        })
        assert validation_search["success"]
        results["steps"].append(("validation_search", validation_search["count"]))
        
        return results

    async def _simulate_refactoring_analysis(self, server: TreeSitterAnalyzerMCPServer, project_path: str) -> Dict[str, Any]:
        """リファクタリングのための影響範囲調査シミュレーション"""
        results = {"success": True, "steps": []}
        
        # Step 1: 特定のクラス/メソッドの使用箇所を検索
        search_tool = SearchContentTool(project_path)
        usage_search = await search_tool.execute({
            "roots": [project_path],
            "query": "UserService|User\\.",
            "case": "sensitive",
            "include_globs": ["*.java", "*.py", "*.js"],
            "max_count": 40
        })
        assert usage_search["success"]
        results["steps"].append(("usage_search", usage_search["count"]))
        
        # Step 2: 依存関係の分析
        import_search = await search_tool.execute({
            "roots": [project_path],
            "query": "import.*User|from.*user",
            "case": "insensitive",
            "include_globs": ["*.java", "*.py"],
            "max_count": 20
        })
        assert import_search["success"]
        results["steps"].append(("import_search", import_search["count"]))
        
        # Step 3: 設定ファイルの確認
        config_files = ["package.json", "README.md"]
        for config_file in config_files:
            config_path = Path(project_path) / config_file
            if config_path.exists():
                scale_tool = AnalyzeScaleTool(project_path)
                config_analysis = await scale_tool.execute({
                    "file_path": str(config_path)
                })
                assert config_analysis["success"]
                results["steps"].append((f"config_analysis_{config_file}", "completed"))
        
        return results

    @pytest.mark.asyncio
    async def test_performance_under_load(self, enterprise_project):
        """負荷下でのパフォーマンステスト"""
        server = TreeSitterAnalyzerMCPServer()
        server.set_project_path(enterprise_project)
        
        # 並行処理テスト
        concurrent_tasks = []
        tools = [
            AnalyzeScaleTool(enterprise_project),
            TableFormatTool(enterprise_project),
            SearchContentTool(enterprise_project),
            ListFilesTool(enterprise_project)
        ]
        
        # 複数のタスクを並行実行
        for i in range(5):
            for tool in tools:
                if isinstance(tool, AnalyzeScaleTool):
                    task = tool.execute({
                        "file_path": str(Path(enterprise_project) / "README.md")
                    })
                elif isinstance(tool, TableFormatTool):
                    task = tool.execute({
                        "file_path": str(Path(enterprise_project) / "README.md"),
                        "format_type": "compact"
                    })
                elif isinstance(tool, SearchContentTool):
                    task = tool.execute({
                        "roots": [enterprise_project],
                        "query": "test",
                        "max_count": 5
                    })
                elif isinstance(tool, ListFilesTool):
                    task = tool.execute({
                        "roots": [enterprise_project],
                        "limit": 10
                    })
                
                concurrent_tasks.append(task)
        
        # 全タスクの実行時間を測定
        start_time = time.time()
        results = await asyncio.gather(*concurrent_tasks, return_exceptions=True)
        execution_time = time.time() - start_time
        
        # 結果検証
        successful_results = [r for r in results if isinstance(r, dict) and r.get("success")]
        error_results = [r for r in results if isinstance(r, Exception)]
        
        # 大部分のタスクが成功することを確認
        success_rate = len(successful_results) / len(results)
        assert success_rate >= 0.8, f"成功率が低すぎます: {success_rate:.2f}"
        
        # 実行時間が合理的であることを確認（20タスクで30秒以内）
        assert execution_time < 30.0, f"並行実行時間が長すぎます: {execution_time:.2f}秒"
        
        print(f"並行実行結果: {len(successful_results)}/{len(results)} 成功, {execution_time:.2f}秒")

    @pytest.mark.asyncio
    async def test_error_recovery_and_resilience(self, enterprise_project):
        """エラー回復と回復力テスト"""
        server = TreeSitterAnalyzerMCPServer()
        server.set_project_path(enterprise_project)
        
        # 1. 存在しないファイルでのエラーハンドリング
        scale_tool = AnalyzeScaleTool(enterprise_project)
        result = await scale_tool.execute({
            "file_path": "nonexistent_file.py"
        })
        assert not result["success"]
        assert "error" in result
        
        # 2. 無効な入力でのエラーハンドリング
        search_tool = SearchContentTool(enterprise_project)
        result = await search_tool.execute({
            "roots": ["nonexistent_directory"],
            "query": "test"
        })
        # エラーが適切に処理されることを確認
        assert not result["success"] or result["count"] == 0
        
        # 3. 正常なファイルでの回復確認
        normal_result = await scale_tool.execute({
            "file_path": str(Path(enterprise_project) / "README.md")
        })
        assert normal_result["success"]
        
        print("エラー回復テスト完了: システムは適切にエラーを処理し、回復しています")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])