<?php

namespace App\Models;

use App\Contracts\UserInterface;
use App\Traits\Timestampable;

/**
 * User model class
 *
 * Represents a user in the system with authentication and profile management.
 */
#[Table('users')]
#[Entity]
class User implements UserInterface
{
    use Timestampable;

    // Constants
    public const STATUS_ACTIVE = 'active';
    public const STATUS_INACTIVE = 'inactive';
    private const MAX_LOGIN_ATTEMPTS = 3;

    // Properties
    private int $id;
    public string $username;
    public string $email;
    private string $passwordHash;
    public readonly \DateTime $createdAt;
    protected ?string $lastLoginAt = null;
    private static int $instanceCount = 0;

    /**
     * Constructor
     */
    public function __construct(string $username, string $email)
    {
        $this->username = $username;
        $this->email = $email;
        $this->createdAt = new \DateTime();
        self::$instanceCount++;
    }

    /**
     * Get user ID
     */
    public function getId(): int
    {
        return $this->id;
    }

    /**
     * Set user ID
     */
    public function setId(int $id): void
    {
        $this->id = $id;
    }

    /**
     * Get username
     */
    public function getUsername(): string
    {
        return $this->username;
    }

    /**
     * Authenticate user
     */
    #[Route('/auth/login')]
    public function authenticate(string $password): bool
    {
        return password_verify($password, $this->passwordHash);
    }

    /**
     * Update profile
     */
    public function updateProfile(array $data): void
    {
        if (isset($data['email'])) {
            $this->email = $data['email'];
        }
        $this->touch();
    }

    /**
     * Magic getter
     */
    public function __get(string $name): mixed
    {
        return $this->$name ?? null;
    }

    /**
     * Magic setter
     */
    public function __set(string $name, mixed $value): void
    {
        $this->$name = $value;
    }

    /**
     * Get instance count (static method)
     */
    public static function getInstanceCount(): int
    {
        return self::$instanceCount;
    }

    /**
     * Find user by email (static method)
     */
    public static function findByEmail(string $email): ?self
    {
        // Database query logic here
        return null;
    }
}

/**
 * Admin user class
 */
class AdminUser extends User
{
    private array $permissions = [];

    public function __construct(string $username, string $email, array $permissions)
    {
        parent::__construct($username, $email);
        $this->permissions = $permissions;
    }

    public function hasPermission(string $permission): bool
    {
        return in_array($permission, $this->permissions);
    }

    public function grantPermission(string $permission): void
    {
        if (!$this->hasPermission($permission)) {
            $this->permissions[] = $permission;
        }
    }
}

/**
 * User repository interface
 */
interface UserRepositoryInterface
{
    public function find(int $id): ?User;
    public function save(User $user): void;
    public function delete(User $user): void;
}

/**
 * Loggable trait
 */
trait Loggable
{
    protected array $logs = [];

    public function log(string $message): void
    {
        $this->logs[] = [
            'message' => $message,
            'timestamp' => time(),
        ];
    }

    public function getLogs(): array
    {
        return $this->logs;
    }
}

/**
 * User status enum (PHP 8.1+)
 */
enum UserStatus: string
{
    case Active = 'active';
    case Inactive = 'inactive';
    case Suspended = 'suspended';
    case Deleted = 'deleted';

    public function label(): string
    {
        return match($this) {
            self::Active => 'Active User',
            self::Inactive => 'Inactive User',
            self::Suspended => 'Suspended User',
            self::Deleted => 'Deleted User',
        };
    }
}

/**
 * Helper function to create user
 */
function createUser(string $username, string $email): User
{
    return new User($username, $email);
}

/**
 * Helper function to hash password
 */
function hashPassword(string $password): string
{
    return password_hash($password, PASSWORD_BCRYPT);
}
