import toml
import os
import sys

def create_from_template(new_symbol: str, template_name: str):
    # Путь к директории с конфигами
    config_dir = os.path.join("data", "config")
    template_path = os.path.join(config_dir, template_name)

    # Проверка существования шаблона
    if not os.path.exists(template_path):
        print(f"❌ Ошибка: Шаблон {template_name} не найден в {config_dir}")
        return

    # Формируем имя выходного файла (напр. btc_sell.toml или btc_hedge.toml)
    suffix = template_name.replace("template_", "")
    new_filename = f"{new_symbol.lower()}_{suffix}"
    output_path = os.path.join(config_dir, new_filename)

    # ПРОВЕРКА: Если файл уже есть, не переписываем его
    if os.path.exists(output_path):
        print(f"⚠️ Файл уже существует: {new_filename}. Пропускаю.")
        return

    # 1. Загружаем данные из файла-шаблона как обычный словарь
    try:
        with open(template_path, "r", encoding="utf-8") as f:
            data = toml.load(f)
    except Exception as e:
        print(f"❌ Ошибка при чтении TOML: {e}")
        return

    # 2. Просто заменяем символ (приводим к формату SYMBOLUSDT)
    # Работает для любого шаблона, где есть поле symbol
    data["symbol"] = f"{new_symbol.upper()}USDT"

    # 3. Сохраняем в новый TOML файл без валидации
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            toml.dump(data, f)
        print(f"✅ Файл успешно создан: {output_path}")
    except Exception as e:
        print(f"❌ Ошибка при записи файла: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Использование: python create_config.py <TICKER>")
        sys.exit(1)

    ticker = sys.argv[1]
    
    # Список шаблонов для обработки
    create_from_template(ticker, "template_hedge.toml")   
    create_from_template(ticker, "template_sell.toml")    
    create_from_template(ticker, "template_buy.toml")
    create_from_template(ticker, "template_sell_av.toml")    
    create_from_template(ticker, "template_buy_av.toml")    