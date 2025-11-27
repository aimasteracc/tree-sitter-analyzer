/// A sample Rust module to demonstrate analysis capabilities
pub mod sample_module {
    use std::collections::HashMap;

    /// A public struct representing a user
    #[derive(Debug, Clone, PartialEq)]
    pub struct User {
        pub id: u64,
        pub username: String,
        email: String,
        active: bool,
    }

    /// An enum for user roles
    #[derive(Debug, Copy, Clone)]
    pub enum UserRole {
        Admin,
        Moderator,
        User,
        Guest,
    }

    /// A trait for items that can be displayed
    pub trait Displayable {
        fn display(&self) -> String;

        fn summary(&self) -> String {
            String::from("No summary available")
        }
    }

    impl User {
        /// Creates a new user
        pub fn new(id: u64, username: String, email: String) -> Self {
            User {
                id,
                username,
                email,
                active: true,
            }
        }

        /// Deactivates the user
        pub fn deactivate(&mut self) {
            self.active = false;
        }

        /// Checks if the user is active
        pub fn is_active(&self) -> bool {
            self.active
        }
    }

    impl Displayable for User {
        fn display(&self) -> String {
            format!("User {}: {} ({})", self.id, self.username, self.email)
        }
    }

    /// An async function to fetch user data
    pub async fn fetch_user_data(user_id: u64) -> Result<User, String> {
        // Simulating async operation
        Ok(User::new(user_id, "async_user".to_string(), "async@example.com".to_string()))
    }

    /// A generic struct
    pub struct Container<T> {
        pub item: T,
    }

    impl<T> Container<T> {
        pub fn new(item: T) -> Self {
            Container { item }
        }

    /// Struct with lifetime annotation
    pub struct BorrowedItem<'a> {
        pub name: &'a str,
    }
    }

    // Macro definition
    macro_rules! say_hello {
        () => {
            println!("Hello!");
        };
    }
}

/// A standalone function
fn main() {
    println!("Running sample...");
}
