from flask import Flask, current_app
from multiprocessing import Process, Manager
import time
import logging
from waitress import serve
import os

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - PID:%(process)d - %(message)s')

# Функция для сервера
def run_server(shared_dict):
    app = Flask(__name__)
    app.config['SHARED_DICT'] = shared_dict

    @app.route('/status', methods=['GET'])
    def status():
        # Доступ к словарю не требует явной блокировки, т.к. Manager управляет этим
        value = current_app.config['SHARED_DICT']['counter']
        ts = current_app.config['SHARED_DICT']['timestamp']
        dict = current_app.config['SHARED_DICT']
        logging.info(f"Запрос /status, текущее значение counter={value}")
        return f"hello, counter={value}, ts={ts} dict={dict}", 200

    logging.info(f"Запуск сервера, PID={os.getpid()}, начальное значение словаря: {shared_dict}")
    try:
        serve(app, host='0.0.0.0', port=5000)
    except Exception as e:
        logging.error(f"Ошибка сервера: {e}")

# Функция для бесконечного цикла с инкрементом i
def run_counter(shared_dict):
    logging.info(f"Запуск счётчика, PID={os.getpid()}, начальное значение словаря: {shared_dict}")
    try:
        i = 0
        while True:
            i += 1
            logging.info(f"Счётчик увеличен: counter={i}")

            # Заполнение shared_dict
            shared_dict['counter'] = i
            shared_dict['timestamp'] = time.time()
            
            time.sleep(1)
    except Exception as e:
        logging.error(f"Ошибка счётчика: {e}")

if __name__ == '__main__':
    # Используем Manager для создания общего словаря
    with Manager() as manager:
        # Общий словарь для процессов, созданный в главном процессе
        shared_dict = manager.dict({'counter': 0, 'timestamp': time.time()})

        # Логируем создание словаря
        logging.info(f"Главный процесс, PID={os.getpid()}, Создан shared_dict с начальным значением: {shared_dict}")

        # Создаём процесс для сервера, передавая ему общий словарь
        server_process = Process(target=run_server, args=(shared_dict,))

        # Запускаем процесс сервера
        logging.info("Запуск процесса сервера")
        server_process.start()

        # Запускаем run_counter в главном процессе
        logging.info("Запуск счётчика в главном процессе")
        try:
            run_counter(shared_dict)
        except KeyboardInterrupt:
            logging.info("Завершение процессов")
            server_process.terminate()