import logging
import time
from prog.proxy_server.proxy_driver import ProxyDriver
# Импортируем ваши классы из файлов
from tools.ha_revers import HARevers
from prog.managers.chase_mng import ChaseMng
from prog.utils.utils import get_inverse_side

# --- Настройки ---
SYMBOL = "OPUSDT"  # Укажите нужный символ
TIMEFRAME = "60"    # H1 в минутах для Bybit/ProxyDriver
SIDE_TO_WATCH = "Buy"  # Мы ищем разворот в Short
QUANTITY = 50   # Объем позиции
POLL_INTERVAL = 20  # Частота проверки сигнала (в секундах)

# Настройка логирования
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("ShortEntry")

def main():
    # 1. Инициализация драйвера (предполагаем наличие запущенного прокси)
    # Здесь нужно передать реальный URL вашего прокси-сервера
    proxy_driver = ProxyDriver(logger=logger) 
    
    # 2. Инициализация менеджеров
    ha_handler = HARevers(
        symbol=SYMBOL, 
        side=SIDE_TO_WATCH, 
        prov_driver=proxy_driver, 
        logger=logger,
        label="Short_Hunter"
    )
    ha_handler.reset(timeframe=TIMEFRAME)
    
    chase_mngr = ChaseMng(proxy_driver=proxy_driver, logger=logger)

    logger.info(f"Запуск мониторинга {SYMBOL} на ТФ {TIMEFRAME}")

    # 3. Цикл ожидания сигнала
    while True:
        try:
            # Проверяем, произошел ли разворот в Short (с Green на Red)
            if ha_handler.check_revers():
                logger.info(f"🚀 Сигнал получен! Разворот HA подтвержден.")
                
                # 4. Вход в позицию через Chase Order
                # Метод возьмет дальний лимитный ордер из пула и подтянет его к Ask
                status, order_id, price = chase_mngr.wait_chase_order(
                    symbol=SYMBOL,
                    side=get_inverse_side(SIDE_TO_WATCH),
                    qty=QUANTITY,
                    poll_interval=2 # Более частая проверка при исполнении
                )
                
                if status == "OK":
                    logger.info(f"✅ Шорт открыт! Ордер: {order_id}, Цена: {price}")
                    break # Выходим из цикла после входа
            
            else:
                logger.debug("Сигнала на разворот пока нет...")
                
        except Exception as e:
            logger.error(f"Ошибка в цикле: {e}")
        
        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()