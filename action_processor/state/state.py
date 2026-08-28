import logging
import yaml  
from pathlib import Path
from typing import Optional, Dict, Any  
from action_processor.state.stack_mng import StackMng 

class State:
    def __init__(self, 
        config_file: Path, 
        logger: logging.Logger,
        config_data: Any,
    ):
        self.logger = logger
        self.config_file = config_file

        # 1. Загружаем и валидируем данные 
        self.data = config_data

        # 2. Инициализируем StackManager только для стратегий со stack
        stack = getattr(self.data, "stack", None)
        if self.data.stack is not None:
            self.stack_mng = StackMng(self.data.stack, self.logger) 
            self.stack_mng.sort_stack(self.data.side)
        else:
            self.stack_mng = None

        self.map_mng = None

    def get_cur_map_elem(self):
        return self.map_mng.get_cur_map_elem()        
    
    def get_last_entry_price(self) -> Optional[float]:
        top = self.stack_mng.peek()
        return float(top.price) if top else None    
    
    def save(self):
        """
        Сохраняет данные в YAML. mode='json' обеспечивает запись процентов как "0.5%".
        """
        # Превращаем модель в чистый словарь без объектов Pydantic/Toml
        updated_data_dict = self.data.model_dump(mode='json') 

        self._write_dict_to_yaml_file(self.config_file, updated_data_dict)
        self.logger.debug(f"Состояние успешно сохранено в {self.config_file}.")

    def _write_dict_to_yaml_file(self, file_path: Path, data: Dict[str, Any]) -> None:
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                yaml.dump(
                    data, 
                    f, 
                    allow_unicode=True, 
                    sort_keys=False,     # Сохраняем порядок полей
                    indent=4,            # Красивый отступ
                    default_flow_style=False # Развернутая структура (не в одну строку)
                )
        except Exception as e:
            self.logger.error(f"Ошибка записи YAML: {e}")
            raise

