import inspect
from typing import Dict, Any, Callable, List

_WRAPPER_KEYS = {
    "function_name",
    "function",
    "tool",
    "tool_name",
    "name",
    "type",
}


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, Dict[str, Any]] = {}
        self._implementations: Dict[str, Callable] = {}

    def register(self, schema: Dict[str, Any], func: Callable):
        name = schema["function"]["name"]
        self._tools[name] = schema
        self._implementations[name] = func

    def get_schemas(self) -> List[Dict[str, Any]]:
        return list(self._tools.values())

    def call_tool(self, name: str, arguments: Dict[str, Any]) -> Any:
        if name not in self._implementations:
            raise ValueError(f"Tool '{name}' is not registered.")

        func = self._implementations[name]
        actual_args = _unwrap_tool_arguments(arguments)

        sig = inspect.signature(func)
        params = sig.parameters
        accepts_var_kw = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())
        if not accepts_var_kw:
            # Always filter to declared params — this is the hard safety net that
            # prevents any wrapper key (function_name, etc.) from reaching the
            # underlying Python function even if _unwrap missed it.
            actual_args = {k: v for k, v in actual_args.items() if k in params}

        try:
            return func(**actual_args)
        except TypeError as e:
            # Last-resort: if an unexpected kwarg slipped through (shouldn't happen
            # after the filter above, but guard against dynamic or *args signatures)
            err_msg = str(e)
            if "unexpected keyword argument" in err_msg:
                # Extract the offending key name and retry without it
                import re as _re
                m = _re.search(r"unexpected keyword argument '([^']+)'", err_msg)
                if m:
                    bad_key = m.group(1)
                    actual_args.pop(bad_key, None)
                    print(f"⚠️ registry: dropped unexpected kwarg '{bad_key}' from {name}() call and retrying")
                    try:
                        return func(**actual_args)
                    except Exception as retry_e:
                        print(f"Error executing tool '{name}' on retry: {retry_e}")
                        return f"Error executing tool '{name}': {str(retry_e)}"
            print(f"Error executing tool '{name}': {e}")
            return f"Error executing tool '{name}': {str(e)}"
        except Exception as e:
            print(f"Error executing tool '{name}': {e}")
            return f"Error executing tool '{name}': {str(e)}"


def _unwrap_tool_arguments(arguments: Dict[str, Any]) -> Dict[str, Any]:
    actual_args = dict(arguments or {})
    for nest_key in ("parameters", "arguments", "args"):
        nested = actual_args.get(nest_key)
        if not isinstance(nested, dict):
            continue
        leftover = {
            k: v
            for k, v in actual_args.items()
            if k not in _WRAPPER_KEYS and k != nest_key
        }
        if not leftover or set(leftover.keys()) <= {"session_id"}:
            session = leftover.get("session_id") or actual_args.get("session_id")
            actual_args = dict(nested)
            if session is not None:
                actual_args.setdefault("session_id", session)
            break
        merged = dict(nested)
        merged.update(leftover)
        actual_args = merged
        break

    # Always strip wrapper/meta keys — they must never reach the function
    for key in list(actual_args.keys()):
        if key in _WRAPPER_KEYS:
            actual_args.pop(key, None)
    return actual_args


# Global tool registry instance
registry = ToolRegistry()