import inspect
import json
from typing import Any, Callable, Dict, List, Optional


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, Dict[str, Any]] = {}

    def register(self, name: str, description: str, parameters: Dict[str, Any]):
        """Decorator to register a python function as an agent tool."""

        def decorator(func: Callable):
            self._tools[name] = {
                "name": name,
                "description": description,
                "parameters": parameters,
                "func": func,
            }
            return func

        return decorator

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """Returns tool specs formatted for OpenAI API-compatible local LLMs."""
        definitions = []
        for name, tool in self._tools.items():
            definitions.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool["name"],
                        "description": tool["description"],
                        "parameters": tool["parameters"],
                    },
                }
            )
        return definitions

    async def execute(self, name: str, arguments: Dict[str, Any], **context) -> Any:
        """Executes a registered tool by name with arguments."""
        if name not in self._tools:
            raise ValueError(f"Tool '{name}' is not registered.")

        tool = self._tools[name]
        func = tool["func"]  # Access key 'func'
        sig = inspect.signature(func)

        # Inject contextual kwargs (like session, task_id, context_engine) if expected
        kwargs = dict(arguments) if isinstance(arguments, dict) else {}
        for param_name in sig.parameters:
            if param_name in context and param_name not in kwargs:
                kwargs[param_name] = context[param_name]

        if inspect.iscoroutinefunction(func):
            return await func(**kwargs)
        return func(**kwargs)


registry = ToolRegistry()
