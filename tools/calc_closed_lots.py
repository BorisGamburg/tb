"""
Расчёт закрытых лотов (closed lots) по исполнениям (executions) из Postgres.

Терминология:
  execution   - одно исполнение на бирже (запись в bybit_executions);
  lot         - открывающее исполнение (или его остаток), ожидающее закрытия;
  closed lot  - часть лота, погашенная закрывающим исполнением
                (одна строка в closed_lots);
  open lot    - лот, который ещё не закрыт полностью (строка в open_lots).

Алгоритм (one-way режим, linear/USDT контракты):
  * исполнения идут по возрастанию времени (exec_time, exec_id);
  * исполнение в сторону текущей позиции (или при пустом буфере) - открытие,
    из него получается лот, он кладётся в буфер;
  * исполнение в противоположную сторону - закрытие. Оно гасит лоты из буфера:
      - шорт-лоты: сначала с самой ВЫСОКОЙ ценой входа;
      - лонг-лоты: сначала с самой НИЗКОЙ ценой входа (зеркально);
    лот закрыт полностью - убираем, частично - уменьшаем остаток,
    если закрытие больше лота - переходим к следующему лоту;
  * если после гашения всех лотов у закрытия остался остаток (разворот
    позиции), выбрасывается PositionReversalError;
  * комиссия делится пропорционально объёму.

Использование:
    python calc_closed_lots.py SYMBOL [--dsn DSN] [--table TABLE] [--csv FILE]
    python calc_closed_lots.py --selftest

Скрипт считает только исполнения грида (фильтр зашит в load_execs).
Результат пишется в таблицы closed_lots и open_lots (создаются заранее).

DSN: --dsn или переменная окружения PG_DSN.
"""
import argparse
import csv
import heapq
import os
import sys
from decimal import Decimal
from itertools import count

DEFAULT_TABLE = "bybit_executions"
CLOSED_TABLE = "closed_lots"
OPEN_TABLE = "open_lots"
TRADE_TYPES = ("Trade", "AdlTrade", "BustTrade")

# Hedge-режим: шорт и лонг - две независимые позиции, считаются раздельно.
#   Short: открытие Sell (closed_size = 0), закрытие Buy (closed_size > 0)
#   Long:  открытие Buy  (closed_size = 0), закрытие Sell (closed_size > 0)
# funding_side - значение side у записей Funding для этой позиции.
DIRECTIONS = {
    "Short": {"open_side": "Sell", "close_side": "Buy", "funding_side": "Sell"},
    "Long": {"open_side": "Buy", "close_side": "Sell", "funding_side": "Buy"},
}


class PositionReversalError(Exception):
    """Исполнение закрытия больше всей открытой противоположной позиции."""


def D(x):
    return Decimal(str(x))


def match_lots(execs):
    """execs: итерируемое dict-ов-исполнений (по возрастанию времени) с ключами
    exec_id, exec_time, side ('Buy'/'Sell'), price, qty, fee (Decimal).

    Возвращает (closed_lots, open_lots):
      closed_lots - список закрытых лотов (dict),
      open_lots   - список открытых лотов в буфере.
    """
    seq = count()
    shorts = []  # куча: (-price, seq, lot)  -> наверху самая высокая цена
    longs = []   # куча: (price, seq, lot)   -> наверху самая низкая цена
    closed_lots = []

    for e in execs:
        qty, price, fee = e["qty"], e["price"], e["fee"]
        if qty <= 0:
            continue
        is_buy = e["side"] == "Buy"
        opposite = shorts if is_buy else longs   # Buy закрывает шорты, Sell - лонги
        remaining = qty
        had_opposite = bool(opposite)

        while remaining > 0 and opposite:
            lot = opposite[0][2]
            m = min(remaining, lot["qty"])

            open_fee = lot["fee"] * m / lot["qty"]
            close_fee = fee * m / qty
            lot["fee"] -= open_fee
            lot["qty"] -= m
            remaining -= m

            if is_buy:   # закрываем шорт-лот
                direction = "Short"
                gross = (lot["price"] - price) * m
            else:        # закрываем лонг-лот
                direction = "Long"
                gross = (price - lot["price"]) * m

            closed_lots.append({
                "direction": direction,
                "open_time": lot["time"],
                "close_time": e["exec_time"],
                "open_exec_id": lot["exec_id"],
                "close_exec_id": e["exec_id"],
                "qty": m,
                "open_price": lot["price"],
                "close_price": price,
                "gross_pnl": gross,
                "fees": -(open_fee + close_fee),   # комиссии - расход, знак минус
                "net_pnl": gross - (open_fee + close_fee),            })

            if lot["qty"] == 0:
                heapq.heappop(opposite)

        if remaining > 0 and had_opposite:
            # закрытие больше всей противоположной позиции - разворот
            raise PositionReversalError(
                f"Исполнение закрытия больше открытой позиции: exec_id={e['exec_id']}, "
                f"время={e['exec_time']:%Y-%m-%d %H:%M:%S}, сторона={e['side']}, "
                f"объём={qty}, лишний остаток={remaining}"
            )

        if remaining > 0:  # нет противоположных лотов - это открытие, создаём лот
            lot = {
                "time": e["exec_time"], "exec_id": e["exec_id"],
                "price": price, "qty": remaining, "open_qty": remaining,
                "fee": fee * remaining / qty,
                "side": "Long" if is_buy else "Short",
            }
            if is_buy:
                heapq.heappush(longs, (price, next(seq), lot))
            else:
                heapq.heappush(shorts, (-price, next(seq), lot))

    open_lots = [x[2] for x in shorts] + [x[2] for x in longs]
    return closed_lots, open_lots


def load_execs(dsn, table, symbol, direction):
    """Загружает исполнения одной позиции (Short или Long) по символу.

    Временный фильтр (пока боты не ставят order_link_id):
      открытие  - сторона open_side с closed_size = 0,
      закрытие  - сторона close_side с closed_size > 0.
    """
    import psycopg2
    from psycopg2 import sql

    cfg = DIRECTIONS[direction]
    query = sql.SQL(
        "SELECT exec_id, exec_time, side, exec_price, exec_qty, exec_fee "
        "FROM {} WHERE symbol = %s AND exec_type IN %s "
        "AND ((side = %s AND coalesce(closed_size, 0) = 0) "
        "  OR (side = %s AND coalesce(closed_size, 0) > 0)) "
        "ORDER BY exec_time, exec_id"
    ).format(sql.Identifier(table))
    params = (symbol, TRADE_TYPES, cfg["open_side"], cfg["close_side"])

    conn = psycopg2.connect(dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
    finally:
        conn.close()

    return [
        {"exec_id": r[0], "exec_time": r[1], "side": r[2],
         "price": D(r[3]), "qty": D(r[4]), "fee": D(r[5] or 0)}
        for r in rows
    ]


def load_funding(dsn, table, symbol, direction):
    """Сумма Funding по позиции (Short -> side Sell, Long -> side Buy).

    Знак: плюс - получили, минус - заплатили (execFee у Funding
    положительный, если заплатили, поэтому знак меняется).
    """
    import psycopg2
    from psycopg2 import sql

    query = sql.SQL(
        "SELECT -COALESCE(SUM(exec_fee), 0) "
        "FROM {} "
        "WHERE symbol = %s "
        "AND exec_type = 'Funding' "
        "AND side = %s"
    ).format(sql.Identifier(table))

    conn = psycopg2.connect(dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(query, (symbol, DIRECTIONS[direction]["funding_side"]))
            row = cur.fetchone()
    finally:
        conn.close()

    return D(row[0])


def print_report(direction, closed_lots, open_lots, funding_pnl):
    side = DIRECTIONS[direction]["funding_side"]
    print(f"\n{'=' * 60}\n{direction.upper()}\n{'=' * 60}")
    print(f"Закрытых лотов: {len(closed_lots)}")
    print(f"Gross PnL: {sum(c['gross_pnl'] for c in closed_lots):.8f}")
    print(f"Комиссии (по закрытым лотам): {sum(c['fees'] for c in closed_lots):.8f}")

    net_pnl = sum(c["net_pnl"] for c in closed_lots)
    print(f"Net PnL закрытых лотов: {net_pnl:.8f}")
    print(f"Funding {side}:{' ' * (15 - len(side))}{funding_pnl:+.8f}"
          f"  (+ получено, - заплачено)")
    print(f"Итого с Funding:         {net_pnl + funding_pnl:.8f}")

    print("\nОткрытые лоты в буфере (текущая позиция):")
    if not open_lots:
        print("  нет (позиция нулевая)")
    for lot in sorted(open_lots, key=lambda x: x["time"]):
        print(f"  {lot['side']:<6}{lot['qty']:>14.4f} @ {lot['price']:.6f}  "
              f"({lot['time']:%Y-%m-%d %H:%M:%S})")
    net = sum(l["qty"] if l["side"] == "Long" else -l["qty"] for l in open_lots)
    print(f"Чистая позиция по буферу: {net:+.4f}  <- сверьте с позицией на Bybit")

    return net_pnl + funding_pnl


def _num(x):
    """Decimal -> float с 12 значащими цифрами (без хвостов от деления)."""
    return float(f"{float(x):.12g}")


def format_stack_yaml(direction, open_lots):
    """Открытые лоты -> блок `stack:` в формате конфига бота.

    fee - полная комиссия входа на initial_qty (бот считает комиссию на монету
    как fee / initial_qty), поэтому остаток комиссии лота пересчитывается на
    open_qty. Порядок: Short - по возрастанию цены, Long - по убыванию.
    """
    lots = sorted(open_lots, key=lambda l: l["price"],
                  reverse=(direction == "Long"))
    lines = ["stack:", "    entries:"]
    for l in lots:
        fee_full = l["fee"] * l["open_qty"] / l["qty"]
        lines += [
            f"    -   price: {_num(l['price'])}",
            f"        qty: {_num(l['qty'])}",
            f"        fee: {_num(fee_full)}",
            f"        initial_qty: {_num(l['open_qty'])}",
        ]
    return "\n".join(lines)


def save_to_db(dsn, symbol, direction, closed_lots, open_lots):
    """Пишет результат расчёта в таблицы closed_lots и open_lots.

    Таблицы должны существовать заранее: скрипт их не создаёт и не меняет.
    Строки этого символа и этого направления (Short/Long) удаляются и
    записываются заново в одной транзакции, строки других символов и
    другого направления не затрагиваются.
    """
    import psycopg2
    import psycopg2.errors
    from psycopg2 import sql
    from psycopg2.extras import execute_values

    closed_rows = [
        (symbol, c["direction"], c["open_exec_id"], c["close_exec_id"],
         c["open_time"], c["close_time"], c["open_price"], c["close_price"],
         c["qty"], c["gross_pnl"], c["fees"], c["net_pnl"])
        for c in closed_lots
    ]
    open_rows = [
        (symbol, l["side"], l["exec_id"], l["time"], l["price"],
         l["open_qty"], l["qty"], -l["fee"])   # остаток комиссии тоже со знаком минус
        for l in open_lots
    ]

    closed_cols = ("symbol, direction, open_exec_id, close_exec_id, open_time, "
                   "close_time, open_price, close_price, qty, gross_pnl, fees, net_pnl")
    open_cols = ("symbol, side, open_exec_id, open_time, open_price, "
                 "open_qty, remaining_qty, remaining_fee")

    conn = psycopg2.connect(dsn)
    try:
        with conn.cursor() as cur:
            for table, cols, rows, dir_col in (
                (CLOSED_TABLE, closed_cols, closed_rows, "direction"),
                (OPEN_TABLE, open_cols, open_rows, "side"),
            ):
                cur.execute(
                    sql.SQL("DELETE FROM {} WHERE symbol = %s AND {} = %s")
                    .format(sql.Identifier(table), sql.Identifier(dir_col)),
                    (symbol, direction))
                if rows:
                    execute_values(
                        cur,
                        sql.SQL("INSERT INTO {} ({}) VALUES %s").format(
                            sql.Identifier(table), sql.SQL(cols)),
                        rows, page_size=1000)
        conn.commit()
    except psycopg2.errors.UndefinedTable as err:
        conn.rollback()
        sys.exit(f"ОШИБКА: таблица не найдена ({err.diag.message_primary}). "
                 f"Создайте {CLOSED_TABLE} и {OPEN_TABLE} заранее.")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    print(f"Записано в базу ({symbol}, {direction}): {CLOSED_TABLE} - {len(closed_rows)} строк, "
          f"{OPEN_TABLE} - {len(open_rows)} строк")


def write_csv(path, closed_lots):
    cols = ["direction", "open_time", "close_time", "open_exec_id", "close_exec_id",
            "qty", "open_price", "close_price", "gross_pnl", "fees", "net_pnl"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(closed_lots)
    print(f"\nCSV записан: {path}")


def selftest():
    from datetime import datetime, timedelta, timezone
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def ex(i, side, price, qty):
        return {"exec_id": str(i), "exec_time": t0 + timedelta(minutes=i),
                "side": side, "price": D(price), "qty": D(qty), "fee": D(0)}

    # шорты: 1@100, 2@110, 1@105; потом Buy 2.5@100
    closed_lots, left = match_lots([
        ex(1, "Sell", 100, 1), ex(2, "Sell", 110, 2), ex(3, "Sell", 105, 1),
        ex(4, "Buy", 100, "2.5"),
    ])
    assert [(c["qty"], c["open_price"]) for c in closed_lots] == [
        (D(2), D(110)), (D("0.5"), D(105))]
    assert sum(c["gross_pnl"] for c in closed_lots) == D(20) + D("2.5")
    assert sorted((l["qty"], l["price"]) for l in left) == [
        (D("0.5"), D(105)), (D(1), D(100))]

    # разворот: лонг-лот 1@100, Sell 3@110 -> исключение
    try:
        match_lots([ex(1, "Buy", 100, 1), ex(2, "Sell", 110, 3)])
    except PositionReversalError:
        pass
    else:
        raise AssertionError("ожидалось PositionReversalError")

    # закрытие ровно в ноль - не разворот
    closed_lots, left = match_lots([ex(1, "Buy", 100, 1), ex(2, "Sell", 110, 1)])
    assert len(closed_lots) == 1 and closed_lots[0]["gross_pnl"] == D(10) and not left
    # блок stack: шорт по возрастанию цены, комиссия пересчитывается на open_qty
    lots = [
        {"price": D("0.0027314"), "qty": D(100), "open_qty": D(200), "fee": D("0.00015023")},
        {"price": D("0.0023983"), "qty": D(400), "open_qty": D(400), "fee": D("0.00052763")},
    ]
    out = format_stack_yaml("Short", lots)
    assert out.index("0.0023983") < out.index("0.0027314")
    assert "fee: 0.00030046" in out and "initial_qty: 200.0" in out
    assert out.index("0.0027314") < out.index("qty: 100.0")
    print("selftest OK")


def main():
    parser = argparse.ArgumentParser(description="Расчёт закрытых лотов")
    parser.add_argument("symbol", nargs="?")
    parser.add_argument("--dsn", default=os.environ.get("PG_DSN"))
    parser.add_argument("--table", default=DEFAULT_TABLE)
    parser.add_argument("--side", choices=("short", "long", "both"), default="both",
                        help="какую позицию считать (по умолчанию обе)")
    parser.add_argument("--csv", default=None, help="сохранить закрытые лоты в CSV")
    parser.add_argument("--stack", action="store_true",
                        help="напечатать открытые лоты как блок stack для конфига бота")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()

    if args.selftest:
        selftest()
        return
    if not args.symbol:
        sys.exit("Укажите SYMBOL")
    if not args.dsn:
        sys.exit("Не задан DSN: укажите --dsn или переменную окружения PG_DSN")

    directions = {"short": ["Short"], "long": ["Long"],
                  "both": ["Short", "Long"]}[args.side]

    all_closed = []
    totals = {}
    stacks = {}
    for direction in directions:
        execs = load_execs(args.dsn, args.table, args.symbol, direction)
        print(f"\nЗагружено исполнений {args.symbol} ({direction}): {len(execs)}")
        if not execs:
            continue

        funding_pnl = load_funding(args.dsn, args.table, args.symbol, direction)

        try:
            closed_lots, open_lots = match_lots(execs)
        except PositionReversalError as err:
            sys.exit(f"ОШИБКА ({direction}): {err}\n"
                     "Возможные причины: пропущены исполнения открытия, история "
                     "начата не с нулевой позиции, либо одно исполнение развернуло "
                     "позицию.")
        totals[direction] = print_report(direction, closed_lots, open_lots,
                                         funding_pnl)
        all_closed.extend(closed_lots)
        stacks[direction] = open_lots
        save_to_db(args.dsn, args.symbol, direction, closed_lots, open_lots)

    if len(totals) > 1:
        print(f"\n{'=' * 60}\nВСЕГО по {args.symbol} (Short + Long, с Funding): "
              f"{sum(totals.values()):.8f}")
    if args.stack:
        for direction, open_lots in stacks.items():
            side = DIRECTIONS[direction]["open_side"]
            print(f"\n# {direction} (side: {side}), вставить в конфиг бота:")
            print(format_stack_yaml(direction, open_lots))
    if args.csv and all_closed:
        write_csv(args.csv, all_closed)


if __name__ == "__main__":
    main()