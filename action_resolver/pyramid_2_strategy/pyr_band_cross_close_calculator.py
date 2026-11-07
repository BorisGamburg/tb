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
        Рассчитывает полный план закрытия пары уровней при пересечении
        Close Band насквозь.

        Прибыльный уровень закрывается полностью.
        Убыточный уровень закрывается частично, в количестве,
        необходимом для компенсации убытка от закрытия прибыльного.

        В расчёте учитываются входные и выходные комиссии обоих уровней.

        Количество убыточного уровня округляется вниз до qty_step.
        Это гарантирует, что округление не увеличит планируемый убыток.

        Если безубыточное закрытие невозможно либо после него
        не останется убыточного уровня, план не формируется.
        """
        self._validate_levels(
            profitable_level,
            losing_level,
            close_price,
        )

        # Рассчитываем чистый PnL закрытия прибыльного уровня с учётом комиссий.
        profitable_net = self._calculate_profitable_net(
            profitable_level,
            close_price,
        )

        if profitable_net <= 0:
            return PyrBandCrossCloseResult(found=False)

        # Определяем чистый результат закрытия одной единицы
        # убыточного уровня с учётом входной и выходной комиссий.
        losing_net_per_unit = self._calculate_losing_net_per_unit(
            losing_level,
            close_price,
        )
        if losing_net_per_unit >= 0:
            return PyrBandCrossCloseResult(found=False)

        # Определяем количество убыточного уровня,
        # необходимое для компенсации прибыли прибыльного уровня.
        required_losing_qty = (
            profitable_net / abs(losing_net_per_unit)
        )

        # Округляем количество убыточного уровня вниз
        # до допустимого шага биржи.
        losing_qty = self.trading_info.get_valid_order_qty(
            min(required_losing_qty, losing_level.qty)
        )
        if losing_qty <= 0:
            return PyrBandCrossCloseResult(found=False)

        # Проверяем, что полный объём прибыльного уровня
        # допустим для выставления биржевого ордера.
        valid_profitable_qty = self.trading_info.get_valid_order_qty(
            profitable_level.qty
        )
        if valid_profitable_qty != profitable_level.qty:
            return PyrBandCrossCloseResult(found=False)

        # Формируем полный план закрытия.
        total_qty = profitable_level.qty + losing_qty

        return PyrBandCrossCloseResult(
            found=True,
            profitable_level=profitable_level,
            losing_level=losing_level,
            profitable_qty=profitable_level.qty,
            losing_qty=losing_qty,
            total_qty=total_qty,
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