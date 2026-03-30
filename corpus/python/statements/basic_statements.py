# Node type: if_statement
if True:
    pass

# Node type: for_statement
for i in range(10):
    pass

# Node type: while_statement
while False:
    pass

# Node type: try_statement
try:
    pass
except Exception:
    pass

# Node type: with_statement
with open('file.txt') as f:
    pass

# Node type: return_statement
def f():
    return 1

# Node type: raise_statement
raise ValueError('error')

# Node type: assert_statement
assert True

# Node type: pass_statement
pass

# Node type: break_statement
while True:
    break

# Node type: continue_statement
for i in range(10):
    continue

# Node type: delete_statement
x = 1
del x

# Node type: global_statement
global x

# Node type: nonlocal_statement
def outer():
    x = 1
    def inner():
        nonlocal x

