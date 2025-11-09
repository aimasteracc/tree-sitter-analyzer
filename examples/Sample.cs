using System;
using System.Collections.Generic;
using System.Linq;

namespace MyApp.Models
{
    /// <summary>
    /// Represents a user in the system.
    /// </summary>
    public class User
    {
        // Fields
        private int _id;
        private readonly string _createdBy;
        public const int MaxNameLength = 100;

        // Properties
        public int Id
        {
            get => _id;
            set => _id = value > 0 ? value : throw new ArgumentException("ID must be positive");
        }

        public string Name { get; set; }
        public string Email { get; set; }
        public DateTime CreatedAt { get; init; }

        // Auto-property with init-only setter
        public string? PhoneNumber { get; init; }

        // Computed property
        public string DisplayName => $"{Name} ({Email})";

        // Constructor
        public User(string name, string email, string createdBy)
        {
            Name = name;
            Email = email;
            _createdBy = createdBy;
            CreatedAt = DateTime.UtcNow;
        }

        // Methods
        public void UpdateEmail(string newEmail)
        {
            if (string.IsNullOrWhiteSpace(newEmail))
            {
                throw new ArgumentException("Email cannot be empty");
            }

            Email = newEmail;
        }

        public bool IsValid()
        {
            return !string.IsNullOrWhiteSpace(Name) &&
                   !string.IsNullOrWhiteSpace(Email) &&
                   Email.Contains("@");
        }

        public override string ToString()
        {
            return $"User: {Name} <{Email}>";
        }
    }

    /// <summary>
    /// Interface for user repository operations.
    /// </summary>
    public interface IUserRepository
    {
        User GetById(int id);
        IEnumerable<User> GetAll();
        void Add(User user);
        void Update(User user);
        void Delete(int id);
    }

    /// <summary>
    /// User role enumeration.
    /// </summary>
    public enum UserRole
    {
        Guest = 0,
        User = 1,
        Moderator = 2,
        Administrator = 3
    }

    /// <summary>
    /// User settings structure.
    /// </summary>
    public struct UserSettings
    {
        public bool EmailNotifications { get; set; }
        public bool SmsNotifications { get; set; }
        public string Theme { get; set; }

        public UserSettings(bool emailNotifications, bool smsNotifications, string theme)
        {
            EmailNotifications = emailNotifications;
            SmsNotifications = smsNotifications;
            Theme = theme;
        }
    }
}
