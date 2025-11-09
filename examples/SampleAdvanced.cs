using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;

namespace MyApp.Services
{
    /// <summary>
    /// Advanced C# features demonstration.
    /// </summary>
    public class UserService
    {
        private readonly IUserRepository _repository;
        private readonly ILogger<UserService> _logger;

        // Event
        public event EventHandler<UserEventArgs>? UserCreated;

        public UserService(IUserRepository repository, ILogger<UserService> logger)
        {
            _repository = repository;
            _logger = logger;
        }

        // Async method
        public async Task<User?> GetUserAsync(int id)
        {
            _logger.LogInformation($"Fetching user with ID: {id}");

            try
            {
                var user = await Task.Run(() => _repository.GetById(id));
                return user;
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, $"Error fetching user {id}");
                return null;
            }
        }

        // Async method with LINQ
        public async Task<IEnumerable<User>> SearchUsersAsync(string query)
        {
            var allUsers = await Task.Run(() => _repository.GetAll());

            return allUsers
                .Where(u => u.Name.Contains(query, StringComparison.OrdinalIgnoreCase) ||
                           u.Email.Contains(query, StringComparison.OrdinalIgnoreCase))
                .OrderBy(u => u.Name)
                .Take(10);
        }

        // Method with pattern matching
        public string GetUserStatus(User user) => user switch
        {
            { IsActive: true, Role: UserRole.Administrator } => "Active Administrator",
            { IsActive: true, Role: UserRole.User } => "Active User",
            { IsActive: false } => "Inactive",
            _ => "Unknown"
        };

        // Generic method
        public T GetValue<T>(string key, T defaultValue)
        {
            // Implementation
            return defaultValue;
        }

        // Extension method (must be in static class)
        protected void OnUserCreated(User user)
        {
            UserCreated?.Invoke(this, new UserEventArgs { User = user });
        }
    }

    // Record type (C# 9+)
    public record UserDto(int Id, string Name, string Email);

    // Record with additional properties
    public record UserDetailsDto : UserDto
    {
        public DateTime CreatedAt { get; init; }
        public UserRole Role { get; init; }
        public bool IsActive { get; init; }

        public UserDetailsDto(int id, string name, string email) : base(id, name, email)
        {
        }
    }

    // Nullable reference types example
    public class UserValidator
    {
        public bool Validate(User? user, out string? errorMessage)
        {
            if (user == null)
            {
                errorMessage = "User cannot be null";
                return false;
            }

            if (string.IsNullOrWhiteSpace(user.Name))
            {
                errorMessage = "Name is required";
                return false;
            }

            errorMessage = null;
            return true;
        }
    }

    // Event args
    public class UserEventArgs : EventArgs
    {
        public User? User { get; set; }
    }

    // Interface definitions
    public interface IUserRepository
    {
        User GetById(int id);
        IEnumerable<User> GetAll();
        void Add(User user);
    }

    public interface ILogger<T>
    {
        void LogInformation(string message);
        void LogError(Exception ex, string message);
    }

    // Supporting types
    public class User
    {
        public int Id { get; set; }
        public string Name { get; set; } = string.Empty;
        public string Email { get; set; } = string.Empty;
        public bool IsActive { get; set; }
        public UserRole Role { get; set; }
    }

    public enum UserRole
    {
        User,
        Administrator
    }
}
