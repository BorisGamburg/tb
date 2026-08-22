import requests
import logging
from pathlib import Path
import os 

class Telegram:
    def __init__(self, logger: logging.Logger, config_file: Path):
        self.logger = logger
        
        # 1. Вызываем метод экземпляра через 'self'
        # Теперь вызов выглядит логично: self.load_config(...)
        self.telegram_token, self.telegram_chat_id = self.load_config(config_file, logger)
        
        # 2. Проверка
        if not self.telegram_token:
            self.logger.warning("Telegram token не загружен. Уведомления будут отключены.")
    
    # --- ОБЫЧНЫЙ МЕТОД ЭКЗЕМПЛЯРА ---
    # Принимает 'self', но не использует его, поскольку функция не работает с состоянием экземпляра.
    def load_config(self, config_path: Path, logger: logging.Logger):
        """
        Загружает Telegram token и chat_id из файла конфигурации по переданному пути.
        """
        token = ""
        chat_id = ""
        
        if not config_path.exists():
            logger.warning(f"Файл конфигурации Telegram не найден по пути: {config_path}")
            return "", ""

        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                
                if len(lines) >= 2:
                    # Читаем первую строку (Token) и вторую (Chat ID)
                    token_line = lines[0].strip()
                    chat_id_line = lines[1].strip()

                    # 1. Извлечение токена: Ищем '=' и берем все, что после него.
                    if token_line.startswith('telegram_token='):
                        # Разбиваем строку по первому знаку '=', берем элемент с индексом [1]
                        token = token_line.split('=', 1)[1].strip() 
                    
                    # 2. Извлечение Chat ID:
                    if chat_id_line.startswith('telegram_chat_id='):
                        # Разбиваем строку по первому знаку '=', берем элемент с индексом [1]
                        chat_id = chat_id_line.split('=', 1)[1].strip()
                else:
                    logger.warning(f"Файл {config_path} содержит недостаточно строк.")

        except Exception as e:
            logger.error(f"Ошибка чтения конфигурации Telegram из {config_path}: {e}")
            
        return token, chat_id
    # --- КОНЕЦ ОБЫЧНОГО МЕТОДА ---


    def send_telegram_message(self, message):
        """Отправляет сообщение в Telegram."""
        if not self.telegram_token or not self.telegram_chat_id:
            return
            
        url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
        params = {
            "chat_id": self.telegram_chat_id,
            "text": message
        }
        try:
            response = requests.get(url, params=params, timeout=5)
            if response.status_code != 200:
                self.logger.error(f"Не удалось отправить сообщение в Telegram: {response.text}")
        except Exception as e:
            self.logger.error(f"Ошибка при отправке сообщения в Telegram: {e}")