from action_resolver.resolve_result import ResolveResult


class BaseStrategy:

    # Стратегия ставит True, когда работа завершена и бот надо остановить.
    finished: bool = False

    def resolve(self) -> ResolveResult:
        raise NotImplementedError