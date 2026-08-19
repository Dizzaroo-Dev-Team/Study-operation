"""Simple per-call memoization for factor resolution (avoid duplicate work within one request)."""


def cache_key(*parts: object) -> str:
    return "|".join(str(p) for p in parts)


class RequestMemo:
    def __init__(self) -> None:
        self._store: dict[str, object] = {}

    def has(self, key: str) -> bool:
        return key in self._store

    def get(self, key: str) -> object | None:
        return self._store.get(key)

    def set(self, key: str, value: object) -> None:
        self._store[key] = value
