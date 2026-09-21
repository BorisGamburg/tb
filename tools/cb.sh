#!/bin/bash

BOT_PROCESS_NAME="python"

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# Получаем список сессий
SESSIONS=($(screen -ls | grep -E '^\s+[0-9]+\.' | awk '{print $1}'))

if [ ${#SESSIONS[@]} -eq 0 ]; then
    echo -e "${YELLOW}Нет активных screen-сессий${NC}"
    exit 0
fi

for SESSION_INFO in "${SESSIONS[@]}"; do
    PID=$(echo "$SESSION_INFO" | cut -d'.' -f1)
    NAME=$(echo "$SESSION_INFO" | cut -d'.' -f2)
    
    echo -e "${YELLOW}=== Сессия: $NAME (PID: $PID) ===${NC}"
    
    # 1. Получаем строку со всеми окнами через запрос к screen
    # Формат обычно: "0 name1  1 name2*"
    WINDOWS_STR=$(screen -S "$SESSION_INFO" -Q windows 2>/dev/null)
    
    # 2. Получаем дочерние процессы (оболочки окон)
    # pgrep -P выдает PID в порядке их создания/дерева
    CHILD_PIDS=$(pgrep -P "$PID")
    
    if [ -z "$CHILD_PIDS" ]; then
        echo -e "${RED}  Нет активных процессов в сессии${NC}"
        continue
    fi

    # Превращаем строку окон в массив имен, убирая индикаторы (*, -)
    # Используем perl/sed для очистки и разделения
    mapfile -t WINDOW_LIST < <(echo "$WINDOWS_STR" | grep -oP '\d+ \K[^ ]+(?=[ $]*)' | sed 's/[*]$//; s/[-]$//')

    idx=0
    for CHILD_PID in $CHILD_PIDS; do
        # Берем имя из распарсенного списка по индексу
        WINDOW_NAME="${WINDOW_LIST[$idx]}"
        [ -z "$WINDOW_NAME" ] && WINDOW_NAME="unknown"
        
        # Проверяем, запущен ли целевой процесс (python) внутри этого дерева
        if pstree -p "$CHILD_PID" 2>/dev/null | grep -q "$BOT_PROCESS_NAME"; then
            echo -e "  ${CYAN}[$WINDOW_NAME]${NC} (PID: $CHILD_PID): ${GREEN}ACTIVE${NC}"
        else
            echo -e "  ${CYAN}[$WINDOW_NAME]${NC} (PID: $CHILD_PID): ${RED}DOWN${NC}"
        fi
        
        ((idx++))
    done
    echo ""
done

echo "Проверка завершена."