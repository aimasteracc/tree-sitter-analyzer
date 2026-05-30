"""Built-in Rust corpus for grammar coverage auto-discovery."""

CORPUS: str = """\
#![allow(unused)]
use std::collections::HashMap;
use std::fmt;

extern crate serde;

const MAX_SIZE: usize = 100;
static COUNTER: std::sync::atomic::AtomicUsize = std::sync::atomic::AtomicUsize::new(0);

type Result<T> = std::result::Result<T, Error>;

#[derive(Debug, Clone, PartialEq)]
pub struct Point {
    pub x: f64,
    pub y: f64,
}

impl Point {
    pub fn new(x: f64, y: f64) -> Self {
        Self { x, y }
    }
}

impl fmt::Display for Point {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "({}, {})", self.x, self.y)
    }
}

pub trait Shape {
    fn area(&self) -> f64;
    fn describe(&self) -> String { format!("area={:.2}", self.area()) }
}

#[derive(Debug)]
pub enum Color {
    Red,
    Green,
    Custom(u8, u8, u8),
}

pub union Bits {
    as_int: u32,
    as_bytes: [u8; 4],
}

macro_rules! my_macro {
    ($x:expr) => { $x * 2 };
}

#[cfg(feature = "experimental")]
pub mod experimental {
    pub fn beta() {}
}

extern "C" {
    fn c_function(x: i32) -> i32;
}

;

pub fn process<T: Clone + fmt::Debug>(items: &[T]) -> Vec<T> {
    let result: Vec<T> = items.iter().cloned().collect();
    result
}

async fn fetch_data(url: &str) -> Result<String> {
    Ok(url.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_basic() {
        assert_eq!(my_macro!(2), 4);
    }
}
"""
