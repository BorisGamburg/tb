#!/bin/bash

BOT_PROCESS_NAME="python"

# Цвета
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

SESSIONS=($(screen -ls | grep -oE '[0-9]+\.[a-zA-Z0-9]+' | sort -t. -k2))

{
    echo "№|Имя|Статус|PID"
    COUNTER=1
    for SESSION_INFO in "${SESSIONS[@]}"; do
        PID=$(echo "$SESSION_INFO" | cut -d'.' -f1)
        NAME=$(echo "$SESSION_INFO" | cut -d'.' -f2)

        if pstree -p "$PID" | grep -q "$BOT_PROCESS_NAME"; then
            STATUS="ACTIVE"
        else
            STATUS="DOWN"
        fi

        echo "$COUNTER|$NAME|$STATUS|$PID"
        ((COUNTER++))
    done
} | column -t -s '|' | while IFS= read -r line; do
    line="${line//ACTIVE/${GREEN}ACTIVE${NC}}"
    line="${line//DOWN/${RED}DOWN${NC}}"
    echo -e "$line"
done

echo ""
echo "Проверка завершена."