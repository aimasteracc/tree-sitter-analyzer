#!/usr/bin/env python3
"""
Test script to verify Python support matches JavaScript capabilities
"""

def test_sample_python_code():
    """Test function with docstring"""
    pass

@property
def sample_property(self):
    """Sample property with decorator"""
    return "test"

@staticmethod
async def async_static_method(param: str) -> str:
    """Async static method with type hints"""
    await some_async_call()
    return param.upper()

class SampleClass:
    """Sample class with various features"""
    
    def __init__(self, name: str):
        self.name = name
    
    @classmethod
    def from_string(cls, data: str):
        return cls(data)
    
    def __str__(self) -> str:
        return f"SampleClass({self.name})"

# Test various Python features
if __name__ == "__main__":
    # List comprehension
    numbers = [x**2 for x in range(10) if x % 2 == 0]
    
    # Context manager
    with open("test.txt", "w") as f:
        f.write("test")
    
    # Exception handling
    try:
        result = 10 / 0
    except ZeroDivisionError as e:
        print(f"Error: {e}")
    
    # Match statement (Python 3.10+)
    match numbers[0]:
        case 0:
            print("Zero")
        case _:
            print("Other")