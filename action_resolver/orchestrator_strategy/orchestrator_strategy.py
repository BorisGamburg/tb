from action_resolver.base_strategy import BaseStrategy
from action_processor.state.state import State
from action_processor.bootstrap import AppContext
from action_resolver.resolve_result import ResolveResult
from orchestrator.orchestrator import Orchestrator


class OrchestratorStrategy(BaseStrategy):

    def __init__(
        self,
        state_store: State,
        app_ctx: AppContext,
    ):
        super().__init__()

        self.state_store = state_store
        self.symbol = state_store.data.symbol
        self.managed_strategies = state_store.data.managed_strategies
        self.app_ctx = app_ctx

    def resolve(self, ctx) -> ResolveResult:
        for strategy in self.managed_strategies:
            endpoint = f"ipc:///tmp/{self.symbol}_{strategy}.sock"

            orchestrator = Orchestrator(endpoint)

            try:
                result = orchestrator.send_command(
                    {"command": "CLOSE_POSITION"},
                    timeout=5.0,
                )
                self.app_ctx.logger.info(
                    f"{strategy}: {result}"
                )
            finally:
                orchestrator.close()

        return ResolveResult(
            action_command=None,
            status="CLOSE_POSITION SENT",
            skip_sleep=False,
        )    