import logging
import tomlkit
from pathlib import Path
from typing import Dict, Any, Optional
from prog.state_store.state_data_schema import StateDataSchema # Корректное имя Pydantic-схемы

class StateStoreMng:
    """
    Управляет загрузкой, сохранением и валидацией StateDataSchema
    из/в файл TOML с использованием библиотеки tomlkit.
    Менеджер теперь является контейнером для объекта состояния.
    """
    state_store_data: Optional[StateDataSchema] = None

    def __init__(self, config_file: Path, logger: logging.Logger, state_data: Optional[StateDataSchema] = None):
        self.config_file = config_file
        self.logger = logger
        self.state_store_data = state_data 

    def load(self):
        """
        Загружает данные из файла TOML, валидирует их с помощью Pydantic 
        и сохраняет в self.state_data.
        """
        try:
            # 1. Читаем файл в dict
            parsed_data = self._parse_toml_file_to_dict(self.config_file)

            # 2. Преобразуем dict в объект StateDataSchema и валидируем данные
            self.state_store_data = StateDataSchema.model_validate(parsed_data)
            return self.state_store_data
            
        except FileNotFoundError:
            raise
        except Exception as e:
            self.logger.critical(f"Критическая ошибка при загрузке или валидации: {e}")
            raise
    
    def save(self):
        """
        Сохраняет текущие данные из self.state_data обратно в файл TOML.
        """
        if self.state_store_data is None:
            self.logger.warning("Нет объекта состояния для сохранения.")
            return
            
        # Преобразуем Pydantic-модель в обычный словарь Python
        updated_data_dict = self.state_store_data.model_dump() 

        # Записываем словарь в файл TOML
        self._write_dict_to_toml_file(self.config_file, updated_data_dict)
        self.logger.debug(f"Состояние успешно сохранено в {self.config_file}.")

    # --- Приватные утилиты для работы с файлами ---

    def _parse_toml_file_to_dict(self, file_path: Path) -> Dict[str, Any]:
        """
        Читает содержимое TOML-файла и парсит его в стандартный словарь Python.
        """
        if not file_path.exists():
            self.logger.critical(f"Файл конфигурации не найден по пути: {file_path}")
            raise FileNotFoundError(f"Файл конфигурации не найден по пути: {file_path}")
            
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
            toml_doc = tomlkit.parse(content)
            # tomlkit.parse возвращает объект Document, который конвертируется в dict
            return dict(toml_doc)
        except Exception as e:
            self.logger.error(f"Ошибка парсинга TOML-файла: {e}")
            raise

    def _write_dict_to_toml_file(self, file_path: Path, data: Dict[str, Any]) -> None:
        """
        Записывает словарь Python в файл в формате TOML.
        """
        try:
            # tomlkit.dumps преобразует Python-словарь в строку TOML
            toml_string = tomlkit.dumps(data)
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(toml_string)
        except Exception as e:
            self.logger.error(f"Ошибка записи TOML-файла: {e}")
            raise