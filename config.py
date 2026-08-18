import os
from datetime import time as dtime

import decouple

TOKEN = str(decouple.config("TG_TOKEN"))
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)
DB_NAME = os.path.join(DATA_DIR, "bot_data.db")
CACHE_TTL = 300

KPI_BELLS = [
    (dtime(8, 30), dtime(10, 0), "1-ша пара"),
    (dtime(10, 25), dtime(11, 55), "2-га пара"),
    (dtime(12, 20), dtime(13, 50), "3-тя пара"),
    (dtime(14, 15), dtime(15, 45), "4-та пара"),
    (dtime(16, 10), dtime(17, 40), "5-та пара"),
    (dtime(18, 5), dtime(19, 35), "6-та пара"),
]

DAYS_MAP = {0: "Пн", 1: "Вв", 2: "Ср", 3: "Чт", 4: "Пт", 5: "Сб"}
DAY_NAMES = {"Пн": "Понеділок", "Вв": "Вівторок", "Ср": "Середа", "Чт": "Четвер", "Пт": "Пʼятниця", "Сб": "Субота"}
TYPE_ICONS = {"Лек": "Лек.📖", "Прак": "Прак.🧪", "Лаб": "Лаб.🔬"}