from action_resolver.base_strategy import BaseStrategy
from action_processor.state.state import State
from action_processor.bootstrap import AppContext
from action_resolver.resolve_result import ResolveResult


class OrchestratorStrategy(BaseStrategy):

    def __init__(
        self,
        state_store: State,
        app_ctx: AppContext,
    ):
        super().__init__()

        self.state_store = state_store
        self.app_ctx = app_ctx

    def resolve(self, ctx) -> ResolveResult:
        raise NotImplementedError
