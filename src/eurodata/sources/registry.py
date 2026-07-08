from eurodata.sources.base import BaseFetcher

_REGISTRY: dict[str, type[BaseFetcher]] = {}


def register(cls: type[BaseFetcher]) -> type[BaseFetcher]:
    _REGISTRY[cls.source_name] = cls
    return cls


def get_fetcher(name: str) -> BaseFetcher:
    return _REGISTRY[name]()


def all_sources() -> list[str]:
    return sorted(_REGISTRY)
