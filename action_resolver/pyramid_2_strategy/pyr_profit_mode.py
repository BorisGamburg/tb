from action_processor.action import Action, ActionCommand
from action_resolver.resolve_result import ResolveResult
from common.level_distance_checker import is_level_distance_allowed
from utils.utils import get_inverse_side


class PyrProfitMode:

    def __init__(
        self,
        state_store,
        app_ctx,
        trading_info,
        action_service,
        open_checker,
        close_processor,
    ):
        self.state_store = state_store
        self.app_ctx = app_ctx
        self.trading_info = trading_info
        self.action_service = action_service
        self.open_checker = open_checker
        self.close_processor = close_processor

        # Используем тот же HA Breakout, который уже создан в EntryChecker.
        self.ha_signal = open_checker.ha_signal

    def resolve(self) -> ResolveResult:
        close_result = self._process_extension_close()

        if close_result is not None:
            return close_result

        return self._process_ha_breakout()

    def _get_extension_levels(self):
        data = self.state_store.data
        entries = data.stack.entries

        if not entries:
            return []

        if data.side == "Buy":
            base_level = min(entries, key=lambda level: level.price)
        else:
            base_level = max(entries, key=lambda level: level.price)

        return [
            level
            for level in entries
            if level is not base_level
        ]

    def _process_extension_close(self) -> ResolveResult | None:
        data = self.state_store.data
        extensions = self._get_extension_levels()

        if not extensions:
            return None

        # Получаем Ask/Bid 
        ticker = self.app_ctx.proxy_driver.get_ticker(data.symbol)
        bid = float(ticker["bid"])
        ask = float(ticker["ask"])

        step_ratio = self.open_checker.step_ratio

        close_level = None

        # Ищем уровеня для закрытия
        close_level = self.find_close_level(data, extensions, bid, ask, step_ratio)
        if close_level is None:
            return None

        # Уровеень для закрытия найден, формируем команду на закрытие.
        close_command = ActionCommand(
            action=Action.CLOSE,
            symbol=data.symbol,
            side=get_inverse_side(data.side),
            qty=close_level.qty,
            levels=[close_level],
            reason="PYRAMID_PROFIT_CLOSE",
        )

        # Отправляем команду на закрытие через CloseProcessor.
        close_result = self.close_processor.execute_profit_close(
            close_command
        )

        exec_result = close_result.execution_result

        # Проверяем результат исполнения команды.
        if not exec_result.executed:
            return ResolveResult(
                executed=False,
                status="PROFIT CLOSE: NOT FILLED",
            )

        # Проверяем закрылся уровень полностью или частично.
        if not close_result.fully_closed:
            # Частичное закрытие уровня -> rearm не выполняем
            return ResolveResult(
                executed=True,
                status=(
                    f"PROFIT CLOSE: PARTIAL "
                    f"| price={close_level.price}"
                ),
            )

        # Полное закрытие уровня -> пробуем выполнить rearm.
        rearm_status = self._try_rearm()

        # Возвращаем результат закрытия уровня с информацией о rearm.
        return ResolveResult(
            executed=True,
            status=(
                f"PROFIT CLOSE: FULL "
                f"| price={close_level.price} "
                f"| {rearm_status}"
            ),
        )

    def find_close_level(self, data, extensions, bid, ask, step_ratio):
        for level in extensions:
            if data.side == "Buy":
                close_price_reached = (
                    bid >= level.price * (1 + step_ratio)
                )
            else:
                close_price_reached = (
                    ask <= level.price * (1 - step_ratio)
                )

            if close_price_reached:
                return level

        return None

    def _try_rearm(self) -> str:
        data = self.state_store.data
        entries = data.stack.entries

        cur_price = float(
            self.app_ctx.proxy_driver.get_last_price(data.symbol)
        )

        # Проверяем дистанцию 
        distance_allowed = is_level_distance_allowed(
            cur_price=cur_price,
            entries=entries,
            hedge_step_ratio=self.open_checker.step_ratio,
        )
        if not distance_allowed:
            # Дистанция меньше шага -> rearm не выполняем
            self.app_ctx.logger.info(
                "[REARM] skipped: distance to stack < step"
            )
            return "REARM: SKIPPED DISTANCE"

        # Дистанция ОК -> пробуем выполнить rearm
        # Получаем количество для rearm
        qty = self.open_checker.get_rearm_qty()
        if qty <= 0:
            self.app_ctx.logger.info(
                "[REARM] skipped: qty = 0"
            )
            return "REARM: SKIPPED QTY"

        # Формируем команду на rearm
        rearm_command = ActionCommand(
            action=Action.OPEN,
            symbol=data.symbol,
            side=data.side,
            qty=qty,
            reason="REARM",
        )

        # Отправляем команду на rearm через ActionService.
        # Повторяем, пока ордер не исполнится (как в PyramidStrategy._try_rearm).
        while True:
            rearm_result = self.action_service.process_action(
                rearm_command
            )
            if rearm_result.executed:
                break

        return "REARM: EXECUTED"

    def _process_ha_breakout(self) -> ResolveResult:
        data = self.state_store.data

        # Без существующего уровня открывать Extension нельзя:
        # первый уровень стека является Base.
        if not data.stack.entries:
            return ResolveResult(
                executed=False,
                status="HA BREAKOUT: SKIPPED (NO STACK)",
            )

        signal_price = float(
            self.app_ctx.proxy_driver.get_last_price(data.symbol)
        )

        signal_result = self.ha_signal.is_entry(
            tf=data.entry_tf,
            side=data.side,
            price=signal_price,
        )

        if not signal_result.ok:
            return ResolveResult(
                executed=False,
                status="HA BREAKOUT: NO SIGNAL",
            )

        # Цена той же стороны спреда, по которой открывается лимитный ордер.
        active_price = self.app_ctx.price_service.get_active_price(
            symbol=data.symbol,
            side=data.side,
        )
        if active_price <= 0:
            raise ValueError(
                f"Invalid active price for HA Breakout: {active_price}"
            )

        qty = self.open_checker.get_rearm_qty()

        if qty <= 0:
            return ResolveResult(
                executed=False,
                status="HA BREAKOUT: SKIPPED (QTY = 0)",
            )

        # Моделируем новый уровень, не меняя реальный стек.
        fee_taker = self.trading_info.fee_taker
        simulated_stack = self.state_store.stack_mng.clone()

        estimated_entry_fee = (
            active_price * qty * fee_taker
        )

        # Добавляем новый уровень к simulated_stack
        simulated_stack.push(
            price=active_price,
            qty=qty,
            initial_qty=qty,
            fee=estimated_entry_fee,
        )

        # Вычисляем безубыток simulated_stack
        new_be = simulated_stack.calculate_break_even_price(
            side=data.side,
            fee_taker=fee_taker,
        )
        if new_be is None:
            raise RuntimeError(
                "Cannot calculate BE after simulated HA Breakout entry"
            )

        # Получаем текущий буфер
        if data.side == "Buy":
            buffer_pct = (
                (active_price - new_be) / active_price * 100
            )
        else:
            buffer_pct = (
                (new_be - active_price) / active_price * 100
            )
        min_buffer_pct = float(data.min_be_buffer_pct)

        self.app_ctx.logger.info(
            f"[HA BREAKOUT] "
            f"active_price={active_price} "
            f"new_be={new_be} "
            f"buffer={buffer_pct:.4f}% "
            f"min_buffer={min_buffer_pct:.4f}%"
        )

        # Сравниваем текущий буфер с минимальным
        if buffer_pct < min_buffer_pct:
            # Текущий буфер слишком маленький -> выходим
            return ResolveResult(
                executed=False,
                status=(
                    f"HA BREAKOUT: SKIPPED "
                    f"| BUFFER {buffer_pct:.4f}% "
                    f"< {min_buffer_pct:.4f}%"
                ),
            )

        # Текущий буфер достаточного размера
        # Формируем команду
        open_command = ActionCommand(
            action=Action.OPEN,
            symbol=data.symbol,
            side=data.side,
            qty=qty,
            reason="PYRAMID_HA_BREAKOUT",
        )

        # Выполняем команду
        # Ошибки открытия не перехватываем: исключение должно выйти наружу.
        open_result = self.action_service.process_action(
            open_command
        )
        if not open_result.executed:
            # Команда не выполнена
            return ResolveResult(
                executed=False,
                status="HA BREAKOUT: NOT FILLED",
            )

        # Команда выполнена
        return ResolveResult(
            executed=True,
            status=(
                f"HA BREAKOUT: OPENED "
                f"| BUFFER {buffer_pct:.4f}%"
            ),
        )