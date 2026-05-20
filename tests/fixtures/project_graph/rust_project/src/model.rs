pub struct User {
    name: String,
}

impl User {
    pub fn new() -> Self {
        User { name: String::new() }
    }
}
