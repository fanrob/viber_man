"""Минимальный мост Viber -> Telegram: пересылает новые сообщения только мне.

Алгоритм (по плану):
    1) постоянно проверяем список чатов Viber на кружки новых сообщений;
    2) если в чате есть новое — открываем его и читаем сообщения снизу вверх,
       пока не встретим текст, уже сохранённый в SQLite;
    3) если чат ещё никогда не читался — новым считаем только 1 последнее
       сообщение;
    4) найденные сообщения отправляем в один фиксированный чат Telegram.

Время сообщений при сравнении не используется — только содержимое (и чат).

Запуск:
    python telegram_bot.py

Заполните TELEGRAM_TOKEN (от @BotFather) и TELEGRAM_CHAT_ID (свой id: напишите
боту /start и зайдите https://api.telegram.org/bot<ТОКЕН>/getUpdates).
"""

import json
import sqlite3
import time
import urllib.request
from pathlib import Path

from ocr_screen import ScreenAnalyzer
from viber_window import ChatEntry, ViberWindow
import viber_config as cfg

from tokens import TELEGRAM_TOKEN,TELEGRAM_CHAT_ID
# ---------------------------------------------------------------------------
# Настройки
# ---------------------------------------------------------------------------


TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

DB_PATH = Path(__file__).with_name("viber_messages.sqlite3")
POLL_INTERVAL = 5            # секунд между проверками списка чатов
MAX_CHAT_PAGES = 3           # сколько страниц списка чатов проходить за проверку
CHAT_SCROLL_AMOUNT = 500     # на сколько прокручивать список чатов к следующей странице
HTTP_TIMEOUT = 10            # таймаут запроса к Telegram, сек


# ---------------------------------------------------------------------------
# SQLite: известные сообщения
# ---------------------------------------------------------------------------

def init_db() -> sqlite3.Connection:
    """Открыть базу и создать таблицу, если её ещё нет."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS seen_messages (
               chat TEXT NOT NULL,
               content TEXT NOT NULL,
               PRIMARY KEY (chat, content)
           )"""
    )
    conn.commit()
    return conn


def is_known(conn: sqlite3.Connection, chat: str, content: str) -> bool:
    """Было ли уже это содержимое в этом чате."""
    return conn.execute(
        "SELECT 1 FROM seen_messages WHERE chat = ? AND content = ?",
        (chat, content),
    ).fetchone() is not None


def is_new_chat(conn: sqlite3.Connection, chat: str) -> bool:
    """Чат ещё никогда не считывался (в базе нет ни одного его сообщения)."""
    return conn.execute(
        "SELECT 1 FROM seen_messages WHERE chat = ? LIMIT 1", (chat,)
    ).fetchone() is None


def remember(conn: sqlite3.Connection, chat: str, content: str) -> None:
    """Запомнить сообщение (повтор не создаст дубль)."""
    conn.execute(
        "INSERT OR IGNORE INTO seen_messages (chat, content) VALUES (?, ?)",
        (chat, content),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------

def send_telegram(text: str) -> None:
    """Отправить текст в один чат (TELEGRAM_CHAT_ID). Без внешних библиотек."""
    payload = json.dumps(
        {"chat_id": TELEGRAM_CHAT_ID, "text": text[:4096]},
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        TELEGRAM_API,
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
        response.read()


# ---------------------------------------------------------------------------
# Viber
# ---------------------------------------------------------------------------

def open_chat(viber: ViberWindow, chat: ChatEntry) -> None:
    """Открыть чат по позиции, полученной из get_chat_list()."""
    # position — левый верхний угол зоны имени чата; кликаем в её центр
    x = chat.position[0] + cfg.CHAT_HEADER_COORD[2] // 2
    y = chat.position[1] + cfg.CHAT_HEADER_COORD[3] // 2
    ScreenAnalyzer.click_in_place(*viber._abs_pnt((x, y)))
    #time.sleep(cfg.CHAT_OPEN_DELAY)


def process_chat(viber: ViberWindow, conn: sqlite3.Connection, chat: ChatEntry) -> None:
    """Прочитать новые сообщения чата и отправить их в Telegram."""
    open_chat(viber, chat)
    # уточняем имя по заголовку открытого чата (OCR из списка может врать)
    name = viber.get_opened_chat_name().strip() or chat.name.strip()
    if not name:
        print("Не удалось узнать имя чата — пропускаем")
        return
    else:
        print('прочитан чат: '+name)

    messages = viber.get_messages(since=None)  # от старых к новым
    if not messages:
        return

    if is_new_chat(conn, name):
        # чат читаем впервые: новое — только последнее сообщение
        fresh = [messages[-1]]
    else:
        # снизу вверх до первого уже известного сообщения
        fresh = []
        for msg in reversed(messages):
            if is_known(conn, name, msg.text):
                break
            fresh.append(msg)
        fresh.reverse()  # отправляем в порядке «старое -> новое»

    for msg in fresh:
        sender = f"{name} (я)" if msg.is_mine else name
        send_telegram(f"{sender}: {msg.text}")
        remember(conn, name, msg.text)
        print(f"Отправлено: {sender}: {msg.text}")


def main() -> None:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        raise RuntimeError("Заполните TELEGRAM_TOKEN и TELEGRAM_CHAT_ID в начале telegram_bot.py")

    conn = init_db()
    viber = ViberWindow()
    print("Мост Viber -> Telegram запущен. Ctrl+C — выход.")

    while True:
        try:
            viber.activate()
            viber.close_holiday()
            viber.scroll_chats_to_up()  # каждый круг начинаем с верха списка

            for _ in range(MAX_CHAT_PAGES):
                unread = [c for c in viber.get_chat_list() if c.has_new_message]
                if not unread:
                    break
                for chat in unread:
                    process_chat(viber, conn, chat)
                viber.scroll_chats(ViberWindow.SCROLL_DOWN, CHAT_SCROLL_AMOUNT)
        except KeyboardInterrupt:
            print("Выход.")
            conn.close()
            return
        except Exception as exc:  # чтобы цикл не упал из-за разовой ошибки
            print(f"Ошибка цикла: {exc}")

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
    
