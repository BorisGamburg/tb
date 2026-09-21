#!/bin/bash

# Берем имя из первого параметра командной строки
SESSION_NAME=$1

# Проверяем, передано ли имя
if [ -z "$SESSION_NAME" ]; then
    echo "Ошибка: Укажите имя сессии. Пример: $0 broc"
    exit 1
fi

# 1. Создаем сессию в фоне с первым окном "hedge"
screen -dmS "$SESSION_NAME" -t hedge

# 2. Добавляем остальные окна в ЭТУ ЖЕ сессию
screen -S "$SESSION_NAME" -X screen -t sell
screen -S "$SESSION_NAME" -X screen -t sell_av
screen -S "$SESSION_NAME" -X screen -t buy
screen -S "$SESSION_NAME" -X screen -t buy_av

# Отправляем команду в окно "hedge"
#screen -S "$SESSION_NAME" -p hedge -X stuff "python3 hedge_start.py --config $SESSION_NAME\n"
# Отправляем команду в окно "main"
#screen -S "$SESSION_NAME" -p main -X stuff "python3 main.py --config $SESSION_NAME\n"


# echo "Сессия '$SESSION_NAME' запущена."
# echo "В окне 'main' запущен: main.py --config $SESSION_NAME"
# echo "В окне 'hedge' запущен: hedge_start.py --config $SESSION_NAME"