from dataclasses import dataclass

from action_processor.state.stack_schema import StackElem
from common.trading_info import TradingInfo


@dataclass(frozen=True)
class PyrBandCrossCloseResult:
    found: bool
    profitable_level: StackElem | None = None
    losing_level: StackElem | None = None
    profitable_qty: float = 0.0
    losing_qty: float = 0.0
    total_qty: float = 0.0


class PyrBandCrossCloseCalculator:

    def __init__(
        self,
        hedge_side: str,
        trading_info: TradingInfo,
    ):
        if hedge_side not in ("Buy", "Sell"):
            raise ValueError(f"Unsupported side: {hedge_side}")

        self.hedge_side = hedge_side
        self.trading_info = trading_info
        self.fee_taker = trading_info.fee_taker

    def calculate(
        self,
        profitable_level: StackElem,
        losing_level: StackElem,
        close_price: float,
    ) -> PyrBandCrossCloseResult:
        """
        Рассчитывает план закрытия пары уровней при пересечении Close Band.

        Прибыльный уровень закрывается полностью.
        Убыточный уровень закрывается частично или полностью.

        В расчёте учитываются входные и выходные комиссии.
        Количество закрытия округляется вниз до qty_step.
        """
        self._validate_levels(
            profitable_level,
            losing_level,
            close_price,
        )

        # Рассчитываем чистую прибыль от закрытия прибыльного уровня.
        profitable_net = self._calculate_profitable_net(
            profitable_level,
            close_price,
        )
        if profitable_net <= 0:
            # Прибыль не положительная -> выходим
            return PyrBandCrossCloseResult(found=False)

        # Рассчитываем количество убыточного уровня, которое можно закрыть без убытка.
        losing_qty = self._calculate_losing_qty(
            losing_level,
            close_price,
            profitable_net,
        )
        if losing_qty <= 0:
            # Ничего закрыть не получится -> выходим
            return PyrBandCrossCloseResult(found=False)

        return self._build_result(
            profitable_level,
            losing_level,
            losing_qty,
        )


    def _calculate_profitable_net(
        self,
        level: StackElem,
        close_price: float,
    ) -> float:
        # Валовая прибыль от полного закрытия уровня.
        if self.hedge_side == "Buy":
            pnl = (close_price - level.price) * level.qty
        else:
            pnl = (level.price - close_price) * level.qty

        # Входная комиссия, относящаяся к закрываемому количеству.
        entry_fee = self._get_entry_fee(level, level.qty)

        # Комиссия за закрытие всего уровня.
        close_fee = close_price * level.qty * self.fee_taker

        return pnl - entry_fee - close_fee

    def _calculate_losing_net_per_unit(
        self,
        level: StackElem,
        close_price: float,
    ) -> float:
        # Валовой результат на одну единицу количества.
        if self.hedge_side == "Buy":
            pnl_per_unit = close_price - level.price
        else:
            pnl_per_unit = level.price - close_price

        # Входная комиссия на одну единицу количества.
        entry_fee_per_unit = (
            level.fee / self._get_initial_qty(level)
        )

        # Комиссия за закрытие одной единицы количества.
        close_fee_per_unit = close_price * self.fee_taker

        return (
            pnl_per_unit
            - entry_fee_per_unit
            - close_fee_per_unit
        )

    def _get_entry_fee(
        self,
        level: StackElem,
        close_qty: float,
    ) -> float:
        # Распределяем исходную входную комиссию
        # пропорционально закрываемому количеству.
        return (
            level.fee
            * close_qty
            / self._get_initial_qty(level)
        )

    @staticmethod
    def _get_initial_qty(level: StackElem) -> float:
        # Для старых уровней без initial_qty используем текущий qty.
        if level.initial_qty > 0:
            return level.initial_qty

        return level.qty

    @staticmethod
    def _validate_levels(
        profitable_level: StackElem,
        losing_level: StackElem,
        close_price: float,
    ) -> None:
        if close_price <= 0:
            raise ValueError(
                f"Invalid close price: {close_price}"
            )

        if profitable_level is losing_level:
            raise ValueError(
                "Profitable and losing levels must be different"
            )

        if profitable_level.qty <= 0 or losing_level.qty <= 0:
            raise ValueError(
                f"Invalid level qty | "
                f"profitable={profitable_level.qty} | "
                f"losing={losing_level.qty}"
            )

        if PyrBandCrossCloseCalculator._get_initial_qty(
            profitable_level
        ) <= 0:
            raise ValueError(
                "Invalid profitable level initial_qty"
            )

        if PyrBandCrossCloseCalculator._get_initial_qty(
            losing_level
        ) <= 0:
            raise ValueError(
                "Invalid losing level initial_qty"
            )

    def _calculate_losing_qty(
        self,
        level: StackElem,
        close_price: float,
        profitable_net: float,
    ) -> float:
        # Чистый результат закрытия одной единицы убыточного уровня.
        losing_net_per_unit = self._calculate_losing_net_per_unit(
            level,
            close_price,
        )
        if losing_net_per_unit >= 0:
            return 0.0

        # Количество, необходимое для компенсации прибыли.
        required_qty = profitable_net / abs(losing_net_per_unit)

        # Не превышаем доступное количество уровня.
        return self.trading_info.get_valid_order_qty(
            min(required_qty, level.qty)
        )

    @staticmethod
    def _build_result(
        profitable_level: StackElem,
        losing_level: StackElem,
        losing_qty: float,
    ) -> PyrBandCrossCloseResult:
        total_qty = profitable_level.qty + losing_qty

        return PyrBandCrossCloseResult(
            found=True,
            profitable_level=profitable_level,
            losing_level=losing_level,
            profitable_qty=profitable_level.qty,
            losing_qty=losing_qty,
            total_qty=total_qty,
        )            