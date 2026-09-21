    def retry_api_call(self, func, *args, **kwargs):
        """Оборачивает вызов API в цикл с попытками (без блокировок)."""
        import time

        for attempt in range(1, self.max_attempts + 1):
            try:
                stack = inspect.stack()
        
                # Получаем только имя функции
                caller_name = stack[1].function

                # Логируем успешный вызов
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                log_entry = (
                    f"[{timestamp}] "
                    f"{caller_name}\n"
                )
                
                # Записываем в файл
                with open("data/log/api_profiling.log", "a", encoding="utf-8") as f:
                    f.write(log_entry)


                # Прямой вызов без ожидания замка Redis
                result = func(*args, **kwargs)
                
                # Небольшая пауза для соблюдения базового лимита (RPS)
                time.sleep(0.2) 
                return result
                        
            except Exception as e:
                error_msg = f"Ошибка API (попытка {attempt}/{self.max_attempts}): {str(e)}"
                self.logger.error(error_msg)
                
                if attempt == self.max_attempts:
                    raise Exception(f"Не удалось выполнить API после {self.max_attempts} попыток: {str(e)}")
                
                # Если поймали ошибку — пересоздаем коннект
                self.logger.info("Пересоздаем клиент из-за ошибки...")
                self.create_http_client()
                
                # Ждем перед следующей попыткой
                time.sleep(self.retry_delay)
