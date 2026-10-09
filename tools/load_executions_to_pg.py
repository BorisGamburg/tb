"""
Загрузка executions с Bybit в Postgres.

Положить в tools/ рядом с calc_pnl.py (импорты такие же, как там).

Использование:
    python load_executions_to_pg.py SYMBOL [PERIOD_DAYS] [--dsn DSN] [--table TABLE]

    SYMBOL       - например HUMAUSDT
    PERIOD_DAYS  - сколько дней истории забрать. Если не указан, скрипт
                   докачивает с момента последней сохранённой записи по
                   этому символу (с запасом в 1 день), а если записей нет,
                   берёт 30 дней.

DSN берётся из --dsn или переменной окружения PG_DSN, например:
    export PG_DSN="postgresql://user:password@localhost:5432/trading"

Зависимость:  pip install psycopg2-binary

Таблицу скрипт не создаёт и не меняет: она должна существовать заранее
(имя по умолчанию bybit_executions, другое через --table). Колонки, в которые
он пишет, перечислены в COLUMNS. Для пропуска дублей нужен уникальный ключ
по exec_id: повторный запуск тогда безопасен.
"""
import argparse
import os
import sys
import time
from datetime import datetime, timezone

DEFAULT_TABLE = "bybit_executions"
DEFAULT_DAYS = 30
OVERLAP_DAYS = 1.0

COLUMNS = (
    "exec_id", "symbol", "exec_time", "exec_type", "side",
    "exec_price", "exec_qty", "exec_value", "exec_fee", "fee_rate",
    "fee_currency", "is_maker", "order_id", "order_link_id",
    "order_type", "closed_size", "raw",
)


def _num(value):
    """Bybit отдаёт числа строками, пустую строку превращаем в NULL."""
    if value is None or value == "":
        return None
    return str(value)


def _text(value):
    if value is None or value == "":
        return None
    return str(value)


def _bool(value):
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    return str(value).lower() == "true"


def row_from_execution(rec: dict, json_dumps):
    """Превращает одну запись get_executions в кортеж по COLUMNS."""
    exec_time = datetime.fromtimestamp(
        int(rec["execTime"]) / 1000, tz=timezone.utc
    )
    return (
        rec["execId"],
        rec["symbol"],
        exec_time,
        rec.get("execType") or "",
        _text(rec.get("side")),
        _num(rec.get("execPrice")),
        _num(rec.get("execQty")),
        _num(rec.get("execValue")),
        _num(rec.get("execFee")),
        _num(rec.get("feeRate")),
        _text(rec.get("feeCurrency")),
        _bool(rec.get("isMaker")),
        _text(rec.get("orderId")),
        _text(rec.get("orderLinkId")),
        _text(rec.get("orderType")),
        _num(rec.get("closedSize")),
        json_dumps(rec),
    )


def rows_from_dataframe(df, json_dumps):
    rows = []
    for rec in df.to_dict(orient="records"):
        # NaN от pandas (колонка есть не у всех записей) считаем отсутствием
        rec = {k: v for k, v in rec.items() if not _is_nan(v)}
        if not rec.get("execId"):
            continue
        rows.append(row_from_execution(rec, json_dumps))
    return rows


def _is_nan(value):
    return isinstance(value, float) and value != value


def last_exec_time(conn, table, symbol):
    from psycopg2 import sql

    query = sql.SQL(
        "SELECT max(exec_time) FROM {} WHERE symbol = %s"
    ).format(sql.Identifier(table))
    with conn.cursor() as cur:
        cur.execute(query, (symbol,))
        return cur.fetchone()[0]


def insert_rows(conn, table, rows):
    """Возвращает число реально добавленных строк (дубли пропускаются).

    Таблица должна уже существовать, скрипт её не создаёт и не меняет.
    Для пропуска дублей нужен уникальный ключ или индекс по exec_id.
    """
    if not rows:
        return 0

    from psycopg2 import sql
    from psycopg2.extras import execute_values

    query = sql.SQL(
        "INSERT INTO {} ({}) VALUES %s ON CONFLICT (exec_id) DO NOTHING RETURNING exec_id"
    ).format(
        sql.Identifier(table),
        sql.SQL(", ").join(sql.Identifier(c) for c in COLUMNS),
    )
    with conn.cursor() as cur:
        inserted = execute_values(
            cur, query, rows,
            template="(" + ", ".join(["%s"] * (len(COLUMNS) - 1)) + ", %s::jsonb)",
            page_size=1000,
            fetch=True,
        )
    return len(inserted)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("symbol")
    parser.add_argument("period_days", nargs="?", type=float, default=None)
    parser.add_argument("--dsn", default=os.environ.get("PG_DSN"))
    parser.add_argument("--table", default=DEFAULT_TABLE)
    args = parser.parse_args()

    if not args.dsn:
        sys.exit("Не задан DSN: укажите --dsn или переменную окружения PG_DSN")

    import json
    import psycopg2
    from common.bybit_executions import get_full_history_by_weeks

    json_dumps = lambda obj: json.dumps(obj, ensure_ascii=False, default=str)

    conn = psycopg2.connect(args.dsn)
    try:
        period_days = args.period_days
        if period_days is None:
            last = last_exec_time(conn, args.table, args.symbol)
            if last is None:
                period_days = DEFAULT_DAYS
                print(f"В базе нет записей по {args.symbol}, беру {period_days:g} дн.")
            else:
                age_days = (time.time() - last.timestamp()) / 86400
                period_days = age_days + OVERLAP_DAYS
                print(f"Последняя запись: {last.isoformat()}, докачиваю {period_days:.2f} дн.")

        print(f"\n=== Загрузка executions {args.symbol} за {period_days:.2f} дн. ===")
        history = get_full_history_by_weeks(args.symbol, period_days)

        if history.empty:
            print("Bybit вернул пустую историю, ничего не добавлено.")
            return

        rows = rows_from_dataframe(history, json_dumps)
        added = insert_rows(conn, args.table, rows)
        conn.commit()

        print(f"\nПолучено с биржи: {len(rows)}")
        print(f"Добавлено новых:  {added}")
        print(f"Пропущено дублей: {len(rows) - added}")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()