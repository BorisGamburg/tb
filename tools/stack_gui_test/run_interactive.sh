#!/bin/bash

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_ROOT="$HOME/htz/tob/V22/data/config"

read -r -p "Введите инструмент без USDT (например, bat): " symbol

symbol="${symbol^^}"
symbol="${symbol%USDT}"

if [[ ! "$symbol" =~ ^[A-Z0-9]+$ ]]; then
    echo "Ошибка: некорректное название инструмента."
    exit 1
fi

symbol="${symbol}USDT"
config_dir="$CONFIG_ROOT/$symbol"

if [[ ! -d "$config_dir" ]]; then
    echo "Каталог конфигураций не найден: $config_dir"
    exit 1
fi

mapfile -t configs < <(
    find "$config_dir" -maxdepth 1 -type f -name '*.yaml' | sort
)

if [[ ${#configs[@]} -eq 0 ]]; then
    echo "Конфигурации YAML не найдены: $config_dir"
    exit 1
fi

echo
echo "Инструмент: $symbol"
echo "Выберите конфигурацию:"
echo

for i in "${!configs[@]}"; do
    printf "  %d) %s\n" "$((i + 1))" "$(basename "${configs[$i]}")"
done

echo

while true; do
    read -r -p "Номер конфигурации: " choice

    if [[ "$choice" =~ ^[0-9]+$ ]] &&
       (( choice >= 1 && choice <= ${#configs[@]} )); then
        break
    fi

    echo "Некорректный номер. Повторите ввод."
done

selected_config="${configs[$((choice - 1))]}"

echo
echo "Запуск: $(basename "$selected_config")"
exec "$SCRIPT_DIR/run.sh" "$selected_config"
