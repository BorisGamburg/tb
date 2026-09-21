import tomlkit
from pathlib import Path
from typing import Dict, Any, Optional
import pprint
from prog.managers.state_store_mng import StateStoreSchema, MapElem 
from pydantic import ValidationError 

# Парсит файл toml в dict
def parse_toml_file_to_dict(file_path: Path) -> Dict[str, Any]:
    if not file_path.exists():
        print(f"Ошибка: Файл конфигурации не найден по пути: {file_path}")
        return {}
        
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
        
    toml_doc = tomlkit.parse(content)
    return dict(toml_doc)

# Записывает dict в файл toml
def write_dict_to_toml_file(file_path: Path, data: Dict[str, Any]) -> None:
    toml_string = tomlkit.dumps(data)
    with open(file_path, 'w', encoding='utf-8') as f:
            f.write(toml_string)


# --- Настройки ---
CONFIG_FILE = Path("/home/bg25al$/tob/V17/data/config/bat.toml") 

# Читаем файл в toml-словарь
parsed_data = parse_toml_file_to_dict(CONFIG_FILE)

# Преобразуем toml-словарь в объект BotConfig и валидируем данные
#config_instance: Optional[BotConfig] = None
config_instance = StateStoreSchema.model_validate(parsed_data) 

# Изменяем данные в объекте BotConfig
#config_instance.map["0"].at_rsi = 55

# Преобразуем объект BotConfig обратно в toml-словарь
updated_data_dict = config_instance.model_dump() 

# Записываем toml-словарь в файл
write_dict_to_toml_file(CONFIG_FILE, updated_data_dict)    
