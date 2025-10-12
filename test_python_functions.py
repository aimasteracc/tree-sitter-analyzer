def get_value() -> str:
    return "test"

def set_value(value: int) -> None:
    self.value = value

async def create_list(item: str) -> list[str]:
    return [item]

def is_valid(input: str, strict: bool = False) -> bool:
    return input is not None and len(input) > 0

class TestClass:
    def __init__(self, value: int):
        self.value = value
    
    def _private_method(self) -> None:
        pass
    
    def __dunder_method__(self) -> str:
        return "dunder"