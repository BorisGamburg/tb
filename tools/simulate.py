import time

from prog.sim.sim_price_feed import PriceFeed
from prog.sim.sim_exchange import SimExchange
from prog.hedge_emergency.hedge_mng import HedgeMng
from prog.sim.sim_proxy_driver import SimProxyDriver


def print_sim_state(step, data, hedge):

    short = data["s_size"]
    long = data["l_size"]
    price = data["last_p"]

    short_unpnl = data["s_pnl"]
    long_unpnl = data["l_pnl"]

    unpnl = short_unpnl + long_unpnl
    realpnl = data.get("rpnl", 0.0)
    total = data.get("tpnl", unpnl + realpnl)

    ratio = long / short if short > 0 else 0

    fl_pct = hedge.cur_float_loss_pct * 100

    print(
        f"{step:04d} | "
        f"Price={price:7.2f} | "
        f"S={short:7.3f} | "
        f"L={long:7.3f} | "
        f"R={ratio:4.2f} | "
        f"S_uPnL={short_unpnl:8.2f} | "
        f"L_uPnL={long_unpnl:8.2f} | "
        f"uPnL={unpnl:8.2f} | "
        f"rPnL={realpnl:8.2f} | "
        f"PnL={total:8.2f} | "
        f"FL={fl_pct:6.3f}%"
    )

class HedgeState:
    def __init__(self):
        self.symbol = "BTCUSDT"

        # пороги убытка
        self.warning_fl = 0.01
        self.panic_fl = 0.02
        self.emergency_fl = 0.03
        self.hysteresis = 0.002

hedge_state = HedgeState()
exchange = SimExchange()
proxy_driver = SimProxyDriver(exchange)

hedge = HedgeMng(
    hedge_state,
    proxy_driver,
    "sim_state.json"
)
    
# стартовая позиция
exchange.set_short_position(size=100, price=100)

# уже есть существующий лонг
exchange.set_long_position(size=60, price=101)  # существующий хедж


prices = [
    100,    # старт
    100.5,
    101.0,  # warning (ничего не делаем)
    101.5,
    102.0,  # panic → добавить только 15
    102.2,
    102.5,

    102.0,  # вниз
    101.5,
    101.0,  # выход из panic
    100.8,
    100.5,  # warning
    100.2,
    100.0,  # ниже warning → закрыть 15
]
price_feed = PriceFeed(prices)

for step in range(30):

    price = price_feed.next_price()

    exchange.update_price("BTCUSDT", price)

    hedge.run_step()

    data = hedge._get_data()

    data["rpnl"] = exchange.realized_pnl()
    data["tpnl"] = exchange.total_pnl()

    print_sim_state(step, data, hedge)


