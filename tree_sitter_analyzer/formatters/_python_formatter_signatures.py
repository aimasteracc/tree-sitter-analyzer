"""Signature and type helpers for Python formatter output."""

from typing import Any

_SHORT_TYPE_MAPPING = {
    "str": "s",
    "int": "i",
    "float": "f",
    "bool": "b",
    "None": "N",
    "Any": "A",
    "List": "L",
    "Dict": "D",
    "Optional": "O",
    "Union": "U",
    "Calculator": "Calculator",
}


def create_compact_signature(method: dict[str, Any]) -> str:
    """Create compact method signature for Python"""
    if method is None or not isinstance(method, dict):
        raise TypeError(f"Expected dict, got {type(method)}")

    params_str = ",".join(_compact_param_types(method.get("parameters", [])))
    return_type = _compact_return_type(method.get("return_type", "Any"))
    return f"({params_str}):{return_type}"


def _compact_param_types(params: Any) -> list[str]:
    if isinstance(params, str):
        return []
    if not isinstance(params, list):
        return []
    return [_compact_param_type(param) for param in params]


def _compact_param_type(param: Any) -> Any:
    if not isinstance(param, dict):
        return "Any"

    param_type = param.get("type", "Any")
    if param_type == "Any" or param_type is None:
        return "Any"
    return param_type


def _compact_return_type(return_type: Any) -> str:
    if isinstance(return_type, dict):
        return str(return_type.get("type", "Any") or str(return_type))
    if not isinstance(return_type, str):
        return str(return_type)
    return return_type


def shorten_type(type_name: Any) -> str:
    """Shorten type name for Python tables"""
    if type_name is None:
        return "Any"

    if not isinstance(type_name, str):
        type_name = str(type_name)

    shortened_generic = _shorten_generic_type(type_name)
    if shortened_generic is not None:
        return shortened_generic

    result = _SHORT_TYPE_MAPPING.get(
        type_name, type_name[:3] if len(type_name) > 3 else type_name
    )
    return str(result)


def _shorten_generic_type(type_name: str) -> str | None:
    if "List[" in type_name:
        result = (
            type_name.replace("List[", "L[").replace("str", "s").replace("int", "i")
        )
        return str(result)

    if "Dict[" in type_name:
        result = (
            type_name.replace("Dict[", "D[").replace("str", "s").replace("int", "i")
        )
        return str(result.replace(", ", ","))

    if "Optional[" in type_name:
        result = (
            type_name.replace("Optional[", "O[")
            .replace("str", "s")
            .replace("float", "f")
        )
        return str(result)

    return None


def format_python_signature(method: dict[str, Any]) -> str:
    """Create Python method signature"""
    param_strs = [_format_python_param(param) for param in _params_list(method)]
    params_str = ", ".join(param_strs)
    return_type = method.get("return_type", "")

    if return_type and return_type != "Any":
        return f"({params_str}) -> {return_type}"
    return f"({params_str})"


def _params_list(method: dict[str, Any]) -> list[Any]:
    params = method.get("parameters", [])
    if params is None:
        return []
    return params


def _format_python_param(param: Any) -> str:
    if not isinstance(param, dict):
        return str(param)

    param_name = param.get("name", "")
    param_type = param.get("type", "")
    if param_type:
        return f"{param_name}: {param_type}"
    return param_name


def format_python_signature_compact(method: dict[str, Any]) -> str:
    """Create compact Python method signature for class sections"""
    param_strs = [_format_compact_python_param(param) for param in _params_list(method)]
    params_str = ", ".join(param_strs)
    return_type = method.get("return_type", "")

    if return_type and return_type != "Any":
        return f"({params_str}):{return_type}"
    return f"({params_str}):Any"


def _format_compact_python_param(param: Any) -> str:
    if not isinstance(param, dict):
        return str(param)

    param_name = param.get("name", "")
    param_type = param.get("type", "")
    if param_type and param_type != "Any":
        return f"{param_name}:{param_type}"
    return f"{param_name}:Any"
