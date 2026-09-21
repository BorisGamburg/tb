# ========== Main ================
from ks.keys import DB_PASSWORD, AP

# Logging Setup
logger = logging.getLogger()
logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
ch = logging.StreamHandler()
ch.setFormatter(formatter)
logger.addHandler(ch)

# Telegram Setup
PROJECT_ROOT = Path(__file__).resolve().parent 
CONFIG_DIR = PROJECT_ROOT / "data" / "config"
TELEGRAM_CONFIG_PATH = CONFIG_DIR / "telegram_config.txt"
telegram = Telegram(logger=logger, config_path=TELEGRAM_CONFIG_PATH)

# Symbol
symbol = "BTCUSDT"
timeframe = "1"

# Создаем exchange_driver
exchange_driver = BybitDriver(api_key=AP, api_secret=DB_PASSWORD, logger=logger, telegram=telegram)

# Создаем HeikenAshiRevers
ha_rev = HARevers(
    exchange_driver=exchange_driver, 
    symbol=symbol, 
    side=""
    timeframe=timeframe,
    logger=logger
)

# Основной цикл для поддержания работы скрипта
while True:
    # Вызываем проверку
    ha_rev.check_revers() 
    #print("Разворот=", ha_calc.revers)

    sleep(10)