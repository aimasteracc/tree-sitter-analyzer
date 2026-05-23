# Fixture: method resolution via self.X.
# `m1` calls `self.m2()` — the resolver should recognise `self.m2` as a
# call to the sibling method `m2` defined on the same class, and emit
# callee_resolution='local' with callee_symbol_id pointing at m2.


class Widget:
    def m1(self):
        self.m2()

    def m2(self):
        pass
