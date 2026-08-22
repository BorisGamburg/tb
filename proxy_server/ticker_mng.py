import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from prog.proxy_server.bybit_ws import BybitWS

class SubscriptionState(Enum):
    UNSUBSCRIBED = "unsubscribed"
    SUBSCRIBING = "subscribing"
    SUBSCRIBED = "subscribed"
    UNSUBSCRIBING = "unsubscribing"

@dataclass
class UnsubscribeResult:
    success: bool
    message: str | None = None    

@dataclass(frozen=True)
class TickerSnapshot:
    symbol: str
    bid: float
    ask: float
    last: float
    timestamp: float    

@dataclass
class TickerData:
    symbol: str

    bid: float | None = None
    ask: float | None = None
    last: float | None = None

    last_update: float = 0.0
    last_access: float = 0.0

    state: SubscriptionState = SubscriptionState.UNSUBSCRIBED

    initialized: bool = False

    lock: threading.Lock = field(default_factory=threading.Lock)

@dataclass
class GarbageCollectionResult:
    messages: list[UnsubscribeResult]
    errors: list[UnsubscribeResult]

class TickerManager:
    def __init__(
        self,
        gc_interval: float = 60.0,
        idle_timeout: float = 10 * 60.0,
    ):
        self.driver = BybitWS(testnet=False)
        self.driver.set_callback(self.on_ticker)
        self._tickers: dict[str, TickerData] = {}
        # защищает только словарь
        self._dict_lock = threading.Lock()
        self.gc_interval = gc_interval
        self.idle_timeout = idle_timeout

        # Создаем поток сборщика мусора, который будет периодически отписывать неиспользуемые тикеры.
        self._stop_event = threading.Event()
        self._gc_thread = threading.Thread(
            target=self._gc_loop,
            daemon=True,
            name="TickerGC",
        )
        self._gc_thread.start()   

    def _gc_loop(self):
        while not self._stop_event.wait(self.gc_interval):
            self._collect_garbage()   


    def stop(self):
        self._stop_event.set()
        self._gc_thread.join()                     

    def _find_entry(self, symbol: str) -> TickerData | None:
        with self._dict_lock:
            return self._tickers.get(symbol)

    def on_ticker(self, symbol: str, bid: float, ask: float, last: float):
        # Ищем запись по инструменту
        entry = self._find_entry(symbol)
        if entry is None:
            return

        # Быстро обновляем данные
        with entry.lock:
            entry.bid = bid
            entry.ask = ask
            entry.last = last

            entry.last_update = time.time()

            entry.initialized = True


    def _get_entry(self, symbol: str) -> TickerData:
        with self._dict_lock:
            entry = self._tickers.get(symbol)
            if entry is None:
                entry = TickerData(symbol=symbol)
                self._tickers[symbol] = entry

            return entry            

    def _wait_until_initialized(
        self,
        entry: TickerData,
        timeout: float = 5.0,
    ):
        deadline = time.time() + timeout

        while True:
            with entry.lock:
                if entry.initialized:
                    return

            if time.time() >= deadline:
                raise TimeoutError(
                    f"Timeout waiting first ticker for {entry.symbol}"
                )

            time.sleep(0.001)            

    def _subscribe(self, entry: TickerData):
        try:
            self.driver.subscribe_ticker(entry.symbol)

            self._wait_until_initialized(entry)

        except Exception:
            with entry.lock:
                entry.state = SubscriptionState.UNSUBSCRIBED
            raise

        with entry.lock:
            entry.state = SubscriptionState.SUBSCRIBED     

    def get(self, symbol: str) -> TickerSnapshot:
        """
        Возвращает актуальные данные тикера.
        """

        entry = self._get_entry(symbol)
        with entry.lock:
            if entry.state == SubscriptionState.SUBSCRIBED:
                action = "snapshot"
            elif entry.state == SubscriptionState.UNSUBSCRIBED:
                entry.state = SubscriptionState.SUBSCRIBING
                action = "subscribe"
            elif entry.state == SubscriptionState.SUBSCRIBING:
                raise RuntimeError(
                    f"Тикер '{symbol}' сейчас находится в процессе подписки.\n"
                    "Возникла крайне редкая ситуация, которая в нормальной работе происходить не должна.\n"
                    "Перезапустите бота. Если ошибка повторится, необходимо разбираться с TickerManager."
                )
            elif entry.state == SubscriptionState.UNSUBSCRIBING:
                raise RuntimeError(
                    f"Тикер '{symbol}' сейчас находится в процессе отписки.\n"
                    "Возникла крайне редкая ситуация, которая в нормальной работе происходить не должна.\n"
                    "Перезапустите бота. Если ошибка повторится, необходимо разбираться с TickerManager."
                )

        if action == "snapshot":
            return self._snapshot(entry)

        if action == "subscribe":
            self._subscribe(entry)
            return self._snapshot(entry)

        raise AssertionError(f"Unknown action: {action}")

    def _unsubscribe(self, symbol: str) -> UnsubscribeResult:
        entry = self._find_entry(symbol)
        if entry is None:
            return UnsubscribeResult(
                success=True,
                message=f"Тикер '{symbol}' отсутствует в TickerManager."
            )

        with entry.lock:
            if entry.state == SubscriptionState.UNSUBSCRIBED:
                return UnsubscribeResult(
                    success=True,
                    message=f"Тикер '{symbol}' уже отписан."
                )

            if entry.state == SubscriptionState.SUBSCRIBING:
                return UnsubscribeResult(
                    success=True,
                    message=(
                            f"Тикер '{symbol}' сейчас находится в процессе подписки.\n"
                            "Отписка не выполнялась."
                        )
                )

            if entry.state == SubscriptionState.UNSUBSCRIBING:
                return UnsubscribeResult(
                    success=True,
                    message=(
                        f"Тикер '{symbol}' уже находится в процессе отписки.\n"
                        "Повторная отписка не требуется."
                    )                    
                )

            entry.state = SubscriptionState.UNSUBSCRIBING

        try:
            if not self.driver.unsubscribe_ticker(symbol):
                raise TimeoutError(
                    f"Timeout unsubscribing from ticker {symbol}"
                )

        except Exception:
            with entry.lock:
                entry.state = SubscriptionState.SUBSCRIBED
            raise

        with entry.lock:
            entry.state = SubscriptionState.UNSUBSCRIBED
            entry.initialized = False
            entry.bid = None
            entry.ask = None
            entry.last = None
            entry.last_update = 0.0

        return UnsubscribeResult(
            success=True,
            message=f"Тикер '{symbol}' успешно отписан."
        )    

    def _collect_garbage(self) -> GarbageCollectionResult:
        """
        Отписывает тикеры, которые не использовались более IDLE_TIMEOUT.

        Записи из словаря не удаляются.
        """

        result = GarbageCollectionResult(
            messages=[],
            errors=[],
        )

        now = time.time()

        #
        # Быстро копируем ссылки на записи.
        #
        with self._dict_lock:
            entries = list(self._tickers.values())

        #
        # Ищем кандидатов на отписку.
        #
        candidates = []

        for entry in entries:
            with entry.lock:
                if entry.state != SubscriptionState.SUBSCRIBED:
                    continue

                if now - entry.last_access < self.idle_timeout:
                    continue

                candidates.append(entry.symbol)

        #
        # Выполняем отписку.
        #
        for symbol in candidates:
            try:
                unsubscribe_result = self._unsubscribe(symbol)

                if unsubscribe_result.success:
                    result.messages.append(unsubscribe_result)
                else:
                    result.errors.append(unsubscribe_result)

            except Exception as e:
                result.errors.append(
                    UnsubscribeResult(
                        success=False,
                        message=(
                            f"Ошибка сборщика мусора при отписке "
                            f"тикера '{symbol}': {e}"
                        ),
                    )
                )

        return result

    def _snapshot(self, entry: TickerData) -> dict:
        with entry.lock:
            if not entry.initialized:
                raise RuntimeError(
                    f"Ticker {entry.symbol} is not initialized"
                )

            entry.last_access = time.time()

            # =====================================================================
            # ВНИМАНИЕ!
            #
            # В этот словарь РАЗРЕШАЕТСЯ помещать ТОЛЬКО НЕИЗМЕНЯЕМЫЕ объекты
            # (str, int, float, bool, None и т.п.).
            #
            # НЕ ДОБАВЛЯТЬ сюда списки, словари, set, dataclass и любые другие
            # изменяемые объекты. Они будут переданы по ссылке, что может привести
            # к трудноуловимым ошибкам и гонкам данных.
            #
            # Если когда-нибудь понадобится передавать изменяемый объект —
            # сначала сделать его полную копию.
            # =====================================================================
            return {
                "symbol": entry.symbol,
                "bid": entry.bid,
                "ask": entry.ask,
                "last": entry.last,
                "timestamp": entry.last_update,
            }    