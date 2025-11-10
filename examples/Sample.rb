require 'date'
require 'json'
require_relative 'concerns/timestampable'

module Authentication
  # Authentication module for user management

  # User class represents a user in the system
  class User
    include Timestampable

    # Constants
    STATUS_ACTIVE = 'active'
    STATUS_INACTIVE = 'inactive'
    MAX_LOGIN_ATTEMPTS = 3

    # Attribute accessors
    attr_accessor :username, :email
    attr_reader :id, :created_at
    attr_writer :password_hash

    # Class variables
    @@instance_count = 0

    # Initialize a new user
    def initialize(username, email)
      @username = username
      @email = email
      @created_at = DateTime.now
      @password_hash = nil
      @last_login_at = nil
      @@instance_count += 1
    end

    # Instance method: Authenticate user
    def authenticate(password)
      return false unless @password_hash
      # Password verification logic here
      BCrypt::Password.new(@password_hash) == password
    end

    # Instance method: Update profile
    def update_profile(data)
      @email = data[:email] if data.key?(:email)
      @username = data[:username] if data.key?(:username)
      touch
    end

    # Instance method: Check if user is active
    def active?
      @status == STATUS_ACTIVE
    end

    # Instance method: Deactivate user
    def deactivate!
      @status = STATUS_INACTIVE
      @deactivated_at = DateTime.now
    end

    # Class method: Get instance count
    def self.instance_count
      @@instance_count
    end

    # Class method: Find user by email
    def self.find_by_email(email)
      # Database query logic here
      nil
    end

    # Class method: Create user with password
    def self.create_with_password(username, email, password)
      user = new(username, email)
      user.password_hash = BCrypt::Password.create(password)
      user
    end

    # Private methods
    private

    def validate_email
      @email.match?(/\A[\w+\-.]+@[a-z\d\-]+(\.[a-z\d\-]+)*\.[a-z]+\z/i)
    end

    def generate_token
      SecureRandom.hex(32)
    end
  end

  # AdminUser class extends User with additional permissions
  class AdminUser < User
    attr_accessor :permissions

    def initialize(username, email, permissions = [])
      super(username, email)
      @permissions = permissions
    end

    def has_permission?(permission)
      @permissions.include?(permission)
    end

    def grant_permission(permission)
      @permissions << permission unless has_permission?(permission)
    end

    def revoke_permission(permission)
      @permissions.delete(permission)
    end

    # Override parent method
    def update_profile(data)
      super(data)
      @permissions = data[:permissions] if data.key?(:permissions)
    end
  end

  # Session module for managing user sessions
  module Session
    # Start a new session
    def self.start(user)
      {
        user_id: user.id,
        token: generate_session_token,
        expires_at: Time.now + 3600
      }
    end

    # Validate session
    def self.valid?(session)
      session[:expires_at] > Time.now
    end

    # Generate session token
    def self.generate_session_token
      SecureRandom.hex(32)
    end
  end
end

# UserRepository class for database operations
class UserRepository
  def initialize(database)
    @database = database
    @cache = {}
  end

  def find(id)
    return @cache[id] if @cache.key?(id)

    user = @database.query("SELECT * FROM users WHERE id = ?", id).first
    @cache[id] = user if user
    user
  end

  def save(user)
    if user.id
      update(user)
    else
      insert(user)
    end
  end

  def delete(user)
    @database.execute("DELETE FROM users WHERE id = ?", user.id)
    @cache.delete(user.id)
  end

  private

  def insert(user)
    @database.execute(
      "INSERT INTO users (username, email, created_at) VALUES (?, ?, ?)",
      user.username, user.email, user.created_at
    )
  end

  def update(user)
    @database.execute(
      "UPDATE users SET username = ?, email = ? WHERE id = ?",
      user.username, user.email, user.id
    )
  end
end

# Helper methods
def create_user(username, email)
  Authentication::User.new(username, email)
end

def hash_password(password)
  BCrypt::Password.create(password)
end

# Lambda examples
validate_email = ->(email) { email.match?(/\A[\w+\-.]+@[a-z\d\-]+(\.[a-z\d\-]+)*\.[a-z]+\z/i) }
format_username = ->(username) { username.strip.downcase }

# Proc examples
log_action = Proc.new do |action, user|
  puts "[#{Time.now}] User #{user.username} performed: #{action}"
end

# Block examples
def with_transaction(&block)
  begin
    # Start transaction
    yield
    # Commit transaction
  rescue => e
    # Rollback transaction
    raise e
  end
end

# Usage with block
with_transaction do
  user = create_user("john_doe", "john@example.com")
  user.update_profile(email: "newemail@example.com")
end
