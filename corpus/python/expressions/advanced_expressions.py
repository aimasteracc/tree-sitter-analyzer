"""
Advanced Python expressions corpus file.

This file provides examples of all expression-related node types that the
Python plugin can extract, including:
- Lambda expressions (lambda_expression)
- List comprehensions (list_comprehension)
- Set comprehensions (set_comprehension)
- Dictionary comprehensions (dictionary_comprehension)
- Generator expressions (generator_expression)
- Conditional expressions (conditional_expression)
- Subscript expressions (subscript)
- List literals (list)
- Default parameters in function definitions (default_parameter)

Purpose: Validate 100% coverage of Python grammar node types.
"""

# Lambda expressions
add_one = lambda x: x + 1
multiply = lambda x, y: x * y
with_default = lambda x, y=10: x + y
nested = lambda x: (lambda y: x + y)

# Comprehensions - Lists
list_comp = [x**2 for x in range(10)]
list_comp_cond = [x for x in range(100) if x % 2 == 0]
nested_comp = [[y for y in range(3)] for x in range(3)]

# Comprehensions - Sets
set_comp = {x**2 for x in range(10)}
set_comp_cond = {x for x in range(100) if x > 50}

# Comprehensions - Dictionaries
dict_comp = {x: x**2 for x in range(10)}
dict_comp_cond = {k: v for k, v in enumerate(range(100)) if v % 3 == 0}

# Generator expressions
gen_exp = (x**2 for x in range(10))
gen_exp_cond = (x for x in range(100) if x % 5 == 0)

# Conditional expressions (ternary)
result = "positive" if 5 > 0 else "negative"
nested_cond = "a" if True else ("c" if False else "e")

# Subscript expressions
my_list = [1, 2, 3, 4, 5]
my_dict = {'key': 'value', 'number': 42}
matrix = [[1, 2], [3, 4]]

item = my_list[0]
key_value = my_dict['key']
matrix_elem = matrix[1][0]
slice_result = my_list[1:5]

# List literals
empty_list = []
simple_list = [1, 2, 3]
nested_list = [[1, 2], [3, 4]]
mixed_list = [1, "two", 3.0, True]

# Default parameters (covered by function extraction)
def with_defaults(x=1, y="hello", z=3.14):
    """Function with default parameters."""
    pass

def mixed_params(a, b=2, c="test"):
    """Function with mixed parameters."""
    pass

def complex_defaults(x=[1, 2, 3], y={'key': 'value'}, z=lambda x: x + 1):
    """Function with complex default values."""
    pass
