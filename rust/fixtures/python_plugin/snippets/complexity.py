"""控制流形态:复杂度公式涉及的全部决策节点。"""


def classify(value: int) -> str:
    """if / elif / else 阶梯 + 三元表达式。"""
    if value < 0:
        label = "negative"
    elif value == 0:
        label = "zero"
    elif value < 10:
        label = "small"
    else:
        label = "large"
    parity = "even" if value % 2 == 0 else "odd"
    return f"{label}/{parity}"


def scan(items: list) -> dict:
    """for / while / 布尔运算 / 各类推导式。"""
    found = {}
    for index, item in enumerate(items):
        if item and isinstance(item, (int, float)):
            found[index] = item
    cursor = 0
    while cursor < len(items) and items[cursor] is not None:
        cursor += 1
    squares = [x * x for x in items if x is not None]
    lookup = {x: i for i, x in enumerate(items)}
    unique = {abs(x) for x in squares}
    total = sum(x for x in squares if x > 0)
    return found if not lookup or len(squares) > 0 else lookup


def risky(text) -> str:
    """try / except / else / finally。"""
    try:
        result = text.strip()
    except AttributeError as error:
        result = str(error)
    except (TypeError, ValueError):
        result = ""
    else:
        result = result or "empty"
    finally:
        done = True
    return result


def route(command: str) -> str:
    """match / case 分派。"""
    match command:
        case "start" | "run":
            state = "running"
        case "stop":
            state = "stopped"
        case str() as name if name.isupper():
            state = "signal"
        case _:
            state = "unknown"
    return state
