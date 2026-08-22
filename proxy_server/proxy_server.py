import zmq
import time
import threading
from prog.proxy_server.registry_mng import ManagerRegistry
from prog.proxy_server.balance_mng import BalanceMng
from prog.proxy_server.pos_mng import PositionMng
from prog.proxy_server.active_order_mng import ActiveOrderMng
from prog.proxy_server.ticker_mng import TickerManager


class ProxyServer:
    def __init__(self, shared_proxy):
        self.driver = shared_proxy.exchange_driver
        self.logger = shared_proxy.logger
        
        # Инициализация менеджеров данных
        self.registry = ManagerRegistry(shared_proxy=shared_proxy)
        self.balance_service = BalanceMng(exchange_driver=self.driver)
        self.position_service = PositionMng(exchange_driver=self.driver, logger=self.logger)
        self.ticker_mng = TickerManager()
        
        # Автономный менеджер истории
        self.active_order_mng = ActiveOrderMng(shared_proxy=shared_proxy)
        
        # Настройка ZMQ контекста
        self.context = zmq.Context.instance()
        self.num_workers = 15 # Количество потоков для обработки запросов

    def _worker_routine(self, worker_id):
        """Логика одного потока-обработчика (воркера)"""
        # Каждый воркер — это REP сокет, подключенный к внутреннему DEALER
        worker_socket = self.context.socket(zmq.REP)
        worker_socket.connect("inproc://workers")
        
        self.logger.info(f"👷 Worker-{worker_id} запущен")
        
        while True:
            try:
                # Получаем запрос от брокера
                request = worker_socket.recv_json()
                # ДОБАВЬ ЭТУ СТРОКУ, ЧТОБЫ ВИДЕТЬ ЗАПРОСЫ В КОНСОЛИ
                self.logger.debug(f"📥 Воркер-{worker_id} получил запрос: {request}")
                cmd = request.get("cmd")
                payload = request.get("data", {})
                
                # Выполняем команду
                result = self._route_command(cmd, payload)
                
                # Отправляем ответ обратно брокеру
                worker_socket.send_json(result)

            # САМОЕ ВАЖНОЕ: Ловим закрытие контекста
            except zmq.ContextTerminated:
                break
                
            except Exception as e:
                self.logger.error(f"❌ Ошибка в воркере {worker_id}: {e}")
                try:
                    worker_socket.send_json({"error": str(e)})
                except:
                    pass

    def _route_command(self, cmd, payload):
        """Внутренняя маршрутизация команд"""
        if cmd == "get_candle_data":
            manager = self.registry.get_manager(payload['symbol'], payload['tf'])
            return manager.get_data()

        elif cmd == "get_bb_ohlc":
            manager = self.registry.get_manager(payload['symbol'], payload['tf'])
            return manager.get_bb_ohlc()
        
        elif cmd == "get_atr_ohlc":
            manager = self.registry.get_manager(payload['symbol'], payload['tf'])
            # Получаем период из payload, по умолчанию 14
            length = int(payload.get('length', 14))
            return manager.get_atr_ohlc(length=length)

        elif cmd == "get_balance":
            return {"balance": self.balance_service.get_val()}

        elif cmd == "get_positions":
            return self._handle_positions(payload)

        elif cmd == "get_active_orders":
            symbol = payload.get('symbol')
            orders_list = self.active_order_mng.get_active_orders(symbol)
            return {"orders": orders_list}
        
        elif cmd == "get_cci":
            manager = self.registry.get_manager(payload['symbol'], payload['tf'])
            length = int(payload.get('length', 20))
            return manager.get_cci(length=length)      

        elif cmd == "get_adx":
            manager = self.registry.get_manager(payload['symbol'], payload['tf'])
            # Получаем период из payload, по умолчанию 14
            length = int(payload.get('length', 14))
            return manager.get_adx(length=length)  
        
        elif cmd == "get_ha":
            manager = self.registry.get_manager(payload['symbol'], payload['tf'])
            return manager.get_ha()        
        
        elif cmd == "get_rsi":
            manager = self.registry.get_manager(payload['symbol'], payload['tf'])
            length = int(payload.get('length', 14))
            return manager.get_rsi(length=length)  

        elif cmd == "get_ema":
            manager = self.registry.get_manager(payload['symbol'], payload['tf'])
            length = int(payload.get('length', 21))
            return manager.get_ema(length=length)     

        elif cmd == "get_ohlc":
            manager = self.registry.get_manager(payload['symbol'], payload['tf'])
            n = int(payload.get("n", 50))
            return {"candles": manager.get_ohlc(n=n)}    

        elif cmd == "get_ticker":
            symbol = payload["symbol"]
            return self.ticker_mng.get(symbol)                     
            
        elif cmd == "proxy":
            return self._handle_direct_proxy(payload)

        return {"error": f"Unknown command: {cmd}"}

    def _handle_positions(self, payload):
        symbol = payload.get('symbol')
        side = payload.get('side')
        if symbol and side:
            return self.position_service.get_pos(symbol, side)
        return self.position_service.get_all()

    def _handle_direct_proxy(self, payload):
        """Прямой проброс методов в BybitDriver."""
        method_name = payload.get("method")
        kwargs = payload.get("kwargs", {})
        
        # Минимальная пауза для ордеров, как и была в твоем коде
        if "order" in method_name.lower():
            time.sleep(0.1)
        
        method = getattr(self.driver, method_name, None)
        if method and callable(method):
            # Здесь вызывается твой BybitDriver с декоратором @limits
            return method(**kwargs)
        
        return {"error": f"Method {method_name} not found"}

    def run(self):
        self.logger.info(f"🚀 Запуск многопоточного ProxyServer (workers: {self.num_workers})")

        # 1. Frontend: Принимает запросы от ботов через IPC
        frontend = self.context.socket(zmq.ROUTER)

        # Выносим адрес в переменную для наглядности
        pipe_address = "ipc:///tmp/bybit_data.pipe.v22"
        frontend.bind(pipe_address)
        self.logger.info(f"🔗 СЛУШАЮ ПАЙП: {pipe_address}")

        # 2. Backend: Раздает задачи воркерам внутри процесса
        backend = self.context.socket(zmq.DEALER)
        backend.bind("inproc://workers")

        # 3. Запускаем пул потоков-воркеров
        for i in range(self.num_workers):
            t = threading.Thread(target=self._worker_routine, args=(i,), daemon=True)
            t.start()

        # 4. Запускаем брокер (прокси), который связывает вход и выход
        try:
            # Эта функция берет сообщение из ROUTER и перекидывает в свободный DEALER
            zmq.proxy(frontend, backend)
        except (zmq.ContextTerminated, KeyboardInterrupt):
            pass # Нормальный выход
        except Exception as e:
            self.logger.error(f"💥 Критическая ошибка брокера ZMQ: {e}")
        finally:
            frontend.close()
            backend.close()
            self.context.term()

    def stop(self):
        """Безопасная остановка всех потоков и соединений."""
        self.logger.info("♻️ Завершение работы ProxyServer...")
        self.ticker_mng.stop()
        self.active_order_mng.stop()
        self.position_service.stop()
        self.context.term()