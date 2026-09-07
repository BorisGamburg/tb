from action_resolver.resolve_result import ResolveResult


class BaseStrategy:

    def resolve(self) -> ResolveResult:
        raise NotImplementedError