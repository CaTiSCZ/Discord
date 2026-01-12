from dataclasses import dataclass
from collections.abc import Callable
from typing import Any
from threading import Lock

class Event:
    @dataclass    
    class Function:
        function: Callable[[Any], None]
        args: list[Any]
        kwargs: dict[str, Any]

    def __init__(self) -> None:
        self._functions: list[Event.Function] = []
        self._lock = Lock()

    def connect(self, function: Callable[[Any], None], args: list[Any] = [], kwargs: dict[str, Any] = {}) -> None:
        with self._lock:
            self._functions.append(Event.Function(function, args, kwargs))

    def disconnect(self, function: Callable[[Any], None]) -> None:
        with self._lock:
            self._functions = [f for f in self._functions if f.function != function]

    def emit(self, *args, **kwargs) -> None:
        with self._lock:
            for func in self._functions:
                try:
                    func.function(*args, *func.args, **(func.kwargs | kwargs))
                except Exception as e:
                    print(f"Error emitting event to {func.function}: {e}")
on_panel_update = Event()
                