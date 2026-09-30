"""Перенос всех данных из SQLite (data/bot.db) в PostgreSQL.

    DATABASE_URL=postgresql://... python deploy/sqlite_to_postgres.py путь/к/bot.db

Целевая база доводится до последней миграции и должна быть пустой — иначе
скрипт ничего не трогает. Всё копируется одной транзакцией: либо все данные,
либо ничего. ID сохраняются, счётчики автоинкремента сдвигаются за максимум.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Запуск как `python deploy/...` кладёт в sys.path папку deploy/, а не корень проекта.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import Integer, func, select, text

from bot.config import DatabaseSettings
from bot.database import create_engine, upgrade_database
from bot.database.models import Base


async def main(sqlite_path: str) -> None:
    if not Path(sqlite_path).is_file():
        sys.exit(f"Файл не найден: {sqlite_path}")
    target_url = DatabaseSettings().database_url
    if not target_url.startswith("postgresql"):
        sys.exit(f"DATABASE_URL должен указывать на PostgreSQL, сейчас: {target_url}")

    src = create_engine(f"sqlite+aiosqlite:///{Path(sqlite_path).as_posix()}")
    dst = create_engine(target_url)
    try:
        await upgrade_database(src)   # старая база тоже должна быть на последней схеме
        await upgrade_database(dst)
        tables = Base.metadata.sorted_tables   # порядок с учётом внешних ключей

        async with dst.begin() as dst_conn:
            for table in tables:
                if await dst_conn.scalar(select(func.count()).select_from(table)):
                    sys.exit(f"Целевая база не пуста (таблица {table.name}) — перенос отменён.")

            async with src.connect() as src_conn:
                for table in tables:
                    rows = [dict(r) for r in (await src_conn.execute(table.select())).mappings()]
                    if rows:
                        await dst_conn.execute(table.insert(), rows)
                    print(f"{table.name:<24} {len(rows):>6} строк")

            # Автоинкремент: следующие ID должны идти после перенесённых.
            for table in tables:
                pk = list(table.primary_key.columns)
                if len(pk) == 1 and isinstance(pk[0].type, Integer) and pk[0].autoincrement is True:
                    await dst_conn.execute(text(
                        f"SELECT setval(pg_get_serial_sequence('{table.name}', '{pk[0].name}'), "
                        f"COALESCE((SELECT MAX({pk[0].name}) FROM {table.name}), 1), "
                        f"(SELECT MAX({pk[0].name}) FROM {table.name}) IS NOT NULL)"
                    ))

        # Сверка количества строк.
        async with src.connect() as s, dst.connect() as d:
            for table in tables:
                a = await s.scalar(select(func.count()).select_from(table))
                b = await d.scalar(select(func.count()).select_from(table))
                if a != b:
                    sys.exit(f"Расхождение в {table.name}: {a} → {b}")
        print("Готово: все таблицы перенесены, количество строк совпадает.")
    finally:
        await src.dispose()
        await dst.dispose()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    asyncio.run(main(sys.argv[1]))
