use std::collections::HashMap;
use crate::handler::serve;
use crate::model::User;

fn main() {
    let mut map = HashMap::new();
    serve();
    let u = User::new();
}
