# Народный прогнозист

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)
![aiogram](https://img.shields.io/badge/aiogram-3-2CA5E0?logo=telegram&logoColor=white)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2-D71F00?logo=sqlalchemy&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?logo=postgresql&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-DC382D?logo=redis&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=white)

Телеграм бот для турнира прогнозов на матчи. Делал на заказ, проект обошёлся заказчику в $150.

Как это работает: админ закидывает тур списком матчей, участники ставят П1, Х или П2 до начала первого матча тура. После игр админ вносит результаты, за каждый угаданный исход даётся 1 балл. Кто набрал больше, тот выше в таблице. Когда розыгрыш закончился, турнир уходит в архив и можно начинать новый.

Что умеет:

- регистрация по нику, мат в никах не пропускает (обходы вроде "с у к а" или "п1д0р" тоже ловит)
- прогнозы можно менять, пока не начался первый матч тура
- рейтинг текущего турнира и архив прошлых
- админка прямо в боте: турниры, загрузка тура одним сообщением, результаты, удаление матчей, добавление админов по @username
- админы видят контакты участников, остальные только ники

Стек: aiogram 3, SQLAlchemy 2 + Alembic, PostgreSQL (для локалки SQLite), Redis по желанию, Docker.

## Запуск

Локально:

```
pip install -r requirements.txt
cp .env.example .env
python -m bot
```

В `.env` обязательно `BOT_TOKEN` и `ADMIN_IDS`. База по умолчанию в `data/bot.db`, миграции применяются сами при старте.

На сервере через докер (бот, postgres и redis):

```
docker compose up -d --build
```

Для докера в `.env` нужен ещё `POSTGRES_PASSWORD`. Если без докера, в `deploy/` лежит systemd юнит.

## Как загрузить тур

Админ отправляет боту одним сообщением:

```
Тур 1
01.10 19:00 Реал - Барселона
01.10 21:30 Спартак - Зенит
```

Время московское, год можно не писать. Приём прогнозов закрывается с началом первого матча.
