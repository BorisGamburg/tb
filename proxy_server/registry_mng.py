import time
import threading
from prog.proxy_server.candle_data_mng import CandleDataMng
from prog.proxy_server.shared_proxy import SharedProxy

class ManagerRegistry:
    def __init__(self, shared_proxy: SharedProxy):
        self.shared_proxy = shared_proxy
        
        # Основное хранилище: { "BTCUSDT_1": CandleDataMng_object }
        self.managers = {}
        # Блокировка для самого словаря (на случай одновременного создания менеджеров)
        self.registry_lock = threading.Lock()

        # Запуск фонового потока-дворника
        self.cleanup_thread = threading.Thread(target=self.watch_dog, daemon=True)
        self.cleanup_thread.start()
        self.shared_proxy.logger.info("🚀 Registry Manager запущен. Дворник на посту.")

    def get_manager(self, symbol, tf):
        """
        Безопасное получение или создание менеджера пары.
        """
        key = f"{symbol.upper()}_{tf}"
        
        with self.registry_lock:
            if key not in self.managers:
                #self.shared_proxy.logger.info(f"🆕 Регистрация новой пары: {key}")
                self.managers[key] = CandleDataMng(
                    symbol=symbol, 
                    timeframe=tf, 
                    shared_proxy=self.shared_proxy
                )
        
        return self.managers[key]

    def watch_dog(self):
        """
        Фоновый процесс очистки. Проверяет 'протухшие' объекты каждые 30 минут.
        """
        while True:
            # Спим (секунд)
            time.sleep(120)
            
            # Делаем снимок ключей, чтобы не менять словарь во время перебора
            with self.registry_lock:
                keys_to_check = list(self.managers.keys())
            
            for key in keys_to_check:
                manager = self.managers.get(key)
                
                # Если к менеджеру не обращались более 5 min
                if manager and manager.is_stale(minutes=5):
                    self.shared_proxy.logger.info(f"🧹 [CLEANUP] Пара {key} неактивна. Начинаю удаление...")
                    
                    # 1. Останавливаем WebSocket внутри менеджера
                    manager.stop()
                    
                    # 2. Удаляем ссылку из словаря
                    with self.registry_lock:
                        if key in self.managers:
                            del self.managers[key]
                    
                    self.shared_proxy.logger.info(f"✅ [CLEANUP] Ресурсы для {key} успешно освобождены.")

    def remove_manager(self, symbol, tf):
        """
        Метод для принудительного удаления (если понадобится).
        """
        key = f"{symbol.upper()}_{tf}"
        with self.registry_lock:
            if key in self.managers:
                self.managers[key].stop()
                del self.managers[key]
                self.shared_proxy.logger.info(f"🗑️ Пара {key} удалена вручную.")