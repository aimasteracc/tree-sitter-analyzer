# Facade Test Contracts

Measured on 2026-06-20.

| Surface | Count |
|---|---:|
| `tests/unit/mcp` Python files | 219 |
| Facade-named files in `tests/unit/mcp` | 11 |

## Contract

Facade tests should prove routing and stable public behavior. They should not
duplicate the full implementation tests for each underlying tool.

Facade tests should cover:

- command/tool name to implementation routing;
- required argument validation;
- output shape that callers depend on;
- error translation at the boundary;
- parity with the matching CLI surface when one exists.

Facade tests should not cover:

- every implementation branch already owned by the tool unit test;
- broad smoke tests with only `result is not None`;
- duplicate copies of the same assertion under multiple facade names.

## Review Rule

When adding a facade test, name the boundary contract in the test name. If the
test cannot name a boundary contract, it belongs in the implementation test
file or should not be added.
