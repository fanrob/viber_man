"""Взаимодействие с окном Viber.

Публичный API — функции, необходимые для алгоритма бота (см. main.py):

    Окно:
        activate()                   — развернуть окно на передний план (вызов при старте)

    1. has_new_messages()            — есть ли кружок новых сообщений
       find_unread_chat_positions()  — позиции строк чатов с кружком
    2. get_chat_list()               — чаты, видимые на экране (имя + позиция строки)
       find_chat()                   — найти чат по имени среди видимых
       get_opened_chat_name()        — имя открытого чата
    3. scroll_chats()                — прокрутить список чатов
    4. scroll_messages()             — прокрутить ленту сообщений
       scroll_messages_to_bottom()   — нажать кнопку «вниз до конца»
    5. get_messages()                — сообщения открытого чата (текст + время)
    6. send_message()                — отправить текст
       type_message()                — ввести текст без отправки (для проверки)
       submit_message()              — нажать Enter (отправить)
       get_input_text()              — прочитать набранный текст (проверка)
       is_message_sent()             — проверить, что сообщение дошло (TODO алгоритма)
    7. click_chat() / click_chat_at() — кликнуть по чату (по имени / по позиции)

Низкоуровневые утилиты (снимки экрана, поиск цвета, скролл, клики, ввод, буфер
обмена) — в модуле ocr_screen; координаты, цвета и задержки — в viber_config.
"""

import re
import time
from datetime import date, datetime, timedelta
from typing import List, NamedTuple, Tuple

import pyautogui

import viber_config as cfg
from ocr_screen import ScreenAnalyzer
from viber_config import CHAT_LIST_HOLIDAY_FIELD, CORRECTION_X, CORRECTION_Y, MESSAGES_SCROLL_BUTTON_ZONE, NEW_MESSAGES_ZONE, Point

import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ViberWindowError(RuntimeError):
    """Базовая ошибка взаимодействия с окном Viber."""


class ViberWindowNotFoundError(ViberWindowError):
    """Окно Viber не найдено."""


class ChatEntry(NamedTuple):
    """Чат в списке на экране."""

    name: str        # имя чата (распознано или скопировано)
    position: Point  # левый верхний угол строки чата в координатах окна
    has_new_message: bool  # есть ли кружок новых сообщений у чата


class Message(NamedTuple):
    """Сообщение в ленте открытого чата."""

    text: str                # текст сообщения
    time: datetime | None    # разобранное время (None, если не распознано)
    is_mine: bool = False    # True — моё сообщение, False — сообщение собеседника


class _MessageSegment(NamedTuple):
    """Отрезок-пузырь в ленте (координаты экрана)."""

    top: int        # верх отрезка
    bottom: int     # низ отрезка (не включая)
    scan_x: int     # X вертикальной линии сканирования
    is_mine: bool   # True — моё сообщение, False — сообщение собеседника


class ViberWindow:
    """Высокоуровневые действия с окном Viber."""

    # Направления скролла (дублируются из конфига для удобства вызова)
    SCROLL_UP = cfg.SCROLL_UP
    SCROLL_DOWN = cfg.SCROLL_DOWN

    def __init__(self, title: str = cfg.WINDOW_TITLE) -> None:
        self.title = title

    # ------------------------------------------------------------------
    # Окно
    # ------------------------------------------------------------------

    def activate(self) -> None:
        """Вывести окно Viber на передний план (развернув, если свёрнуто)."""
        window = self._window()
        ScreenAnalyzer.activate_window(window)
        time.sleep(cfg.WINDOW_ACTIVATE_DELAY)

    def _window(self):
        """Найти окно Viber (и развернуть, если свёрнуто)."""
        window = ScreenAnalyzer.find_window(self.title)
        if window is None:
            raise ViberWindowNotFoundError(
                f"Окно '{self.title}' не найдено. Откройте Viber или измените "
                "cfg.WINDOW_TITLE в viber_config.py"
            )
        if window.isMinimized:
            window.restore()
            time.sleep(cfg.WINDOW_ACTIVATE_DELAY)
        return window

    def _window_rect(self) -> Tuple[int, int, int, int]:
        """Прямоугольник окна: (left, top, width, height) в координатах экрана."""
        window = self._window()
        return window.left, window.top, window.width, window.height

    def _absolute_zone(self, zone: Tuple[int, int, int, int]) -> Tuple[int, int, int, int]:
        """Перевести зону из координат окна в координаты экрана."""
        left, top, _, _ = self._window_rect()
        x, y, width, height = zone
        #корректировка в 30 для строки заголовка окна
        return left + CORRECTION_X + x, top + CORRECTION_Y + y, width, height

    def _abs_pnt(self, point: Point) -> Point:
        """Перевести точку из координат окна в координаты экрана."""
        left, top, _, _ = self._window_rect()
        #корректировка в 30 для строки заголовка окна
        return left + CORRECTION_X + point[0], top + CORRECTION_Y + point[1]

    def close_holiday(self):
        #проверяем что есть полоска с днюхой и кликаем по закрытию
        color_matches = ScreenAnalyzer.has_color_in_region(
            *self._absolute_zone(CHAT_LIST_HOLIDAY_FIELD),
            cfg.HOLIDAY_COLOR,
            cfg.HOLIDAY_COLOR_TOLERANCE,
            cfg.HOLIDAY_MIN_PIXELS
        )
        if color_matches:
            print("Полоска с днюхой обнаружена, закрываем...")
            x, y = self._abs_pnt(cfg.BUTTON_CLOSE_HOLIDAY_FIELD)
            ScreenAnalyzer.click_in_place(x, y)
            time.sleep(cfg.CLICK_SETTLE_DELAY)
        
    # ------------------------------------------------------------------
    # 1. Новые сообщения
    # ------------------------------------------------------------------

    def has_new_messages(self) -> bool:
        """Проверить, есть ли новые сообщения (пиксели цвета бейджа в зоне)."""
        x, y, width, height = self._absolute_zone(cfg.FULL_NEW_MESSAGES_ZONE)
        return ScreenAnalyzer.has_color_in_region(
            x,
            y,
            width,
            height,
            cfg.NEW_MESSAGE_COLOR,
            cfg.NEW_MESSAGE_COLOR_TOLERANCE,
            cfg.NEW_MESSAGE_MIN_PIXELS,
        )

    def check_has_new_messages(self, position: Point) -> bool:
        """Проверить, есть ли новые сообщения в указанной зоне. 
            На вход подаётся координата левого верхнего угла строки чата (относительно окна Viber)."""
        x, y, width, height = self._absolute_zone((position[0]+NEW_MESSAGES_ZONE[0], 
                                                   position[1]+NEW_MESSAGES_ZONE[1], 
                                                   NEW_MESSAGES_ZONE[2], 
                                                   NEW_MESSAGES_ZONE[3]))
        return ScreenAnalyzer.has_color_in_region(
            x,
            y,
            width,
            height,
            cfg.NEW_MESSAGE_COLOR,
            cfg.NEW_MESSAGE_COLOR_TOLERANCE,
            cfg.NEW_MESSAGE_MIN_PIXELS,
        )

    def find_unread_chat_positions(self) -> List[Point]:
        """Найти чаты с кружком новых сообщений на текущем экране.

        Returns:
            Центры строк чатов с кружком (координаты окна), сверху вниз.
            Пустой список, если кружков на экране нет.
        """
        return []  # TODO: сканировать CHAT_LIST_ZONE на цвет кружка, группировать по строкам

    # ------------------------------------------------------------------
    # 2. Список чатов
    # ------------------------------------------------------------------

    def get_chat_list(self) -> List[ChatEntry]:
        """Получить список чатов на текущем экране.
        Возвращает список имён чатов (распознанных или скопированных), сверху вниз.
        Массив чатов с полями name и has_new_message (наличие кружка новых сообщений).

        Учесть в списки чатов поле с днюхами, поле с рекламой
        Высота строчки чата - 72 пикс
        вначале списка чатов может быть поле с днюхами(не обязательно), потом список чатов, потом реклама(тоже не обязательно)
        поле с днюхами 40 px, цвет 115, 96, 242

        """
        self.close_holiday()  #закрыть поле с днюхами, если оно есть

        #сдвинуть мышку вправо, чтобы не мешала сканированию списка чатов
        x, y, width, height = self._absolute_zone(cfg.CHAT_LIST_ZONE)
        ScreenAnalyzer.move_mouse_to(x + width + 30, y + height // 2, duration=0.4)

        #теперь список чатов. Высота строки чата - 72 px. Сканируем список чатов сверху вниз, пока не дойдём до конца зоны списка чатов
        cury = 0
        chat_list = []
        while cury < cfg.CHAT_LIST_ZONE[3]:
            # 1. получаем зону с названием чата
            # 2. получаем число новых сообщений в чате (если есть)

            # распознать текст в зоне названия чата (OCR)
            chat_name = ScreenAnalyzer.get_text_in_region(
                *self._absolute_zone((cfg.CHAT_LIST_ZONE[0]+cfg.CHAT_HEADER_COORD[0], 
                                      cfg.CHAT_LIST_ZONE[1] + cury + cfg.CHAT_HEADER_COORD[1], 
                                      cfg.CHAT_HEADER_COORD[2], 
                                      cfg.CHAT_HEADER_COORD[3]))
            )
            has_new_message = self.check_has_new_messages((cfg.CHAT_LIST_ZONE[0], 
                                                           cfg.CHAT_LIST_ZONE[1] + cury))
            chat_list.append(ChatEntry(name=chat_name, 
                                       position=(cfg.CHAT_LIST_ZONE[0]+cfg.CHAT_HEADER_COORD[0], cfg.CHAT_LIST_ZONE[1] + cury + cfg.CHAT_HEADER_COORD[1]),
                                       has_new_message=has_new_message))

            # TODO: если имя чата пустое, то открыть чат, и скопировать имя чата через правое меню и вставить из буфера. 
            #           Обязательно проверить, не прочитали ли случайно новые сообщения!!!
            # TODO: тут позже вставть проверку на рекламу
            cury += cfg.CHAT_RECORD_HEIGHT  # переходим к следующей строке чата
        return chat_list

    def find_chat(self, name: str) -> ChatEntry | None:
        """Найти чат с указанным именем среди видимых на экране.

        Args:
            name: имя чата (точное или частичное совпадение — решить при реализации).

        Returns:
            Найденный чат или None, если на экране его нет (тогда нужно
            прокрутить список и повторить поиск).
        """
        return None  # TODO: перебрать get_chat_list() и сравнить имена

    def get_opened_chat_name(self) -> str:
        """Имя открытого чата (заголовок переписки).

        Используется в обходном пути «открыть каждый чат и проверить имя».

        Returns:
            Имя открытого чата или "", если получить не удалось.
        """
        ScreenAnalyzer.move_mouse_to(*self._abs_pnt(cfg.OPENED_CHAT_NAME_POINT), duration=0.4)
        ScreenAnalyzer.click_in_place(*self._abs_pnt(cfg.OPENED_CHAT_NAME_POINT), button="right")
        time.sleep(cfg.CLICK_SETTLE_DELAY)
        ScreenAnalyzer.click_in_place(*self._abs_pnt((cfg.OPENED_CHAT_NAME_POINT[0]+10,
                                                            cfg.OPENED_CHAT_NAME_POINT[1]+10)))
        time.sleep(cfg.CLICK_SETTLE_DELAY)
        #получаем текст из буфера обмена
        text = ScreenAnalyzer.get_clipboard_text()
        
        return text

    # ------------------------------------------------------------------
    # 3. Скролл списка чатов
    # ------------------------------------------------------------------

    def scroll_chats(self, direction: int, amount: int = cfg.SCROLL_AMOUNT) -> None:
        """Прокрутить список чатов вверх/вниз (колёсико над списком чатов)."""
        self._scroll(cfg.CHATS_SCROLL_POINT, direction, amount)

    def scroll_chats_to_up(self):
        #проверить, что кнопка вверх списка чатов видна (т.е. список не прокручен до верха)
        x, y, width, height = self._absolute_zone(cfg.BUTTON_UP_ZONE)
        if not ScreenAnalyzer.has_color_in_region(
            x, y, width, height,
            cfg.BUTTON_UP_COLOR,
            cfg.NEW_MESSAGE_COLOR_TOLERANCE,
            cfg.BUTTON_UP_MIN_PIXELS,
        ):
            for _ in range(3):  # если кнопки вверх нет, то просто прокрутим вверх немного на всякий случай
                self._scroll(cfg.CHATS_SCROLL_POINT, cfg.SCROLL_UP, cfg.SCROLL_AMOUNT)
        else:
            #нажать мышкой на кнопку вверх списка чатов, чтобы прокрутить наверх
            x, y = self._abs_pnt(cfg.BUTTON_UP)
            ScreenAnalyzer.click_in_place(x, y)

        time.sleep(cfg.SCROLL_SETTLE_DELAY)



    # ------------------------------------------------------------------
    # 4. Скролл ленты сообщений
    # ------------------------------------------------------------------

    def scroll_messages(self, direction: int, amount: int = cfg.SCROLL_AMOUNT) -> None:
        """Прокрутить ленту сообщений вверх/вниз (колёсико над лентой)."""
        self._scroll(cfg.MESSAGES_SCROLL_POINT, direction, amount)

    def scroll_messages_to_bottom(self) -> None:
        """Поставить ленту в самый конец нажатием кнопки «вниз до конца»."""

        x, y, width, height = self._absolute_zone(cfg.MESSAGES_SCROLL_BUTTON_ZONE)
        if ScreenAnalyzer.has_color_in_region(
            x, y, width, height,
            cfg.DEFAULT_VIOL_COLOR,
            0,
            cfg.BUTTON_DOWN_MIN_PIXELS,
        ):
            ScreenAnalyzer.click_in_place(*self._abs_pnt(cfg.MESSAGES_SCROLL_POINT))

    # ------------------------------------------------------------------
    # 5. Текст сообщений
    # ------------------------------------------------------------------

    def get_messages(self, since: datetime | None = None) -> List[Message]:
        """Сообщения открытого чата, от старых к новым.

        Чтение идёт снизу вверх, пока не будет достигнуто уже известное
        сообщение (граница `since`) — чтобы не читать обработанное ранее.

        Args:
            since: если задан — возвращаются только сообщения новее этого
                времени; None — все видимые сообщения.

        Returns:
            Список сообщений (text + time + от кого), от старых к новым.
        """

        '''
        крутим чат вниз до конца
        пока в буффере нет сообщений или флага, что достигнуто собщение с временем старше указанного цикл:
            делаем скан зоны сообщений
            сканируем чат снизу вверх по вертикальной линии, где сообщения собеседника ещё нет, а фон сообщений уже есть
            записываем в массив сегменты, где был фон сообщений
            сканируем чат вверх по вертикальной линии, со стороны моих сообщений, записываем в другой массив аналогичные сегменты
            объединяем 2 массива с сортировкой по координатам снизу вверх, но с признаком, из какого именно массива отрезок
            обрабатываем каждый отрезок, снизу вверх:
            беру нижнюю границу отрезка, прибавляю координаты (разные для разных авторов (от меня или мне)),
                        получаю прямоугольник, где находится время
            распознаю время, если оно не корректно распозналось, то считаю, что оно ещё входит в нужный временной промежуток
            если время уже ранее, чем на входе функции, то прерываю цикл
            копирую правой кнопкой текст сообщения
            записываю известные данные в буффер
            программно нажимаю pageup

        TODO: еще не учтены файлы и изображения. Тоже нужно будет, но позже
        ''' 


        logger.info("get_messages: начало чтения (since=%s)", since)

        # 1. активируем окно, держим фокус в ленте, прокручиваем в самый низ
        self.activate()
        self.scroll_messages_to_bottom()

        found: List[Message] = []   # порядок сбора: снизу вверх (новые -> старые)
        seen: set = set()           # уже прочитанные (защита от дублей после PageUp)
        prev_signature = None

        for page in range(cfg.MESSAGES_MAX_PAGES):
            segments, signature = self._scan_message_segments()

            if signature == prev_signature:
                logger.info("Страница %d не изменилась — дальше лента не прокручивается", page)
                break
            prev_signature = signature

            if not segments:
                logger.info("Страница %d: отрезков сообщений не найдено", page)
                break

            reached_old = False
            for seg in segments:  # снизу вверх: сначала новые сообщения
                msg_time = self._read_message_time(seg)
                # Время не распознано -> считаем, что сообщение ещё в нужном
                # интервале (см. план). Распознано и не новее since -> хватит.
                if since is not None and msg_time is not None and msg_time <= since:
                    logger.info("Достигнута граница since=%s", since)
                    reached_old = True
                    break

                text = self._copy_message_text(seg)
                if not text:
                    continue

                key = (text, msg_time, seg.is_mine)
                if key in seen:
                    continue  # уже прочитано (пересечение страниц после PageUp)
                seen.add(key)
                found.append(Message(text=text, time=msg_time, is_mine=seg.is_mine))

            if reached_old:
                break

            # на страницу назад — читаем более старые сообщения
            ScreenAnalyzer.press_key(cfg.PAGE_UP_KEY)
            time.sleep(cfg.MESSAGES_PAGE_DELAY)

        found.reverse()  # от старых к новым
        logger.info("get_messages: прочитано %d сообщений", len(found))
        return found

    # ------------------------------------------------------------------
    # 5. Внутренности чтения ленты: сканирование, время, копирование
    # ------------------------------------------------------------------

    def _scan_message_segments(self) -> Tuple[List[_MessageSegment], tuple]:
        """Просканировать ленту по двум вертикальным линиям (см. план).

        Returns:
            (отрезки-пузыри, сигнатура страницы). Отрезки отсортированы снизу
            вверх; сигнатура нужна, чтобы понять, изменилась ли лента после
            PageUp (совпадает — дальше прокрутить некуда).
        """
        ax, ay, aw, ah = self._absolute_zone(cfg.MESSAGES_LIST_ZONE)
        segments: List[_MessageSegment] = []
        signature = []

        for offset, is_mine in ((cfg.ANOTH_MESS_SCAN_X, False), (cfg.MY_MESS_SCAN_X, True)):
            if not 0 <= offset < aw:
                logger.warning("Линия сканирования вне зоны: offset=%d, ширина зоны=%d", offset, aw)
                continue
            x = ax + offset
            colors = ScreenAnalyzer.get_pixels_colors_in_region(x, ay, 1, ah)
            signature.append(tuple(colors))
            for top, bottom in self._bubble_runs(colors, is_mine):
                segments.append(
                    _MessageSegment(top=ay + top, bottom=ay + bottom, scan_x=x, is_mine=is_mine)
                )

        segments.sort(key=lambda seg: seg.top, reverse=True)  # снизу вверх
        return segments, tuple(signature)

    @staticmethod
    def _bubble_runs(colors: List[Tuple[int, int, int]], is_mine: bool) -> List[Tuple[int, int]]:
        """Найти в вертикальном срезе отрезки-пузыри.

        Отрезок — непрерывный участок, отличный от фона чата, подходящий по
        высоте и с преобладанием «своего» цвета (свои/чужие пузыри разного
        цвета, белый текст внутри пузыря не должен сбивать с толку).

        Returns:
            Список (верх, низ) в индексах colors.
        """
        tolerance = cfg.MESSAGES_SCAN_TOLERANCE
        own_color = cfg.BACKGROUND_MY_MESS if is_mine else cfg.BACKGROUND_ANOTH_MESS
        foreign_color = cfg.BACKGROUND_ANOTH_MESS if is_mine else cfg.BACKGROUND_MY_MESS

        # 1. отрезки непрерывных пикселей, отличных от фона чата
        runs: List[Tuple[int, int]] = []
        start = None
        for i, pixel in enumerate(colors):
            if not ScreenAnalyzer.color_matches(pixel, cfg.BACKGROUND_CHAT, tolerance):
                if start is None:
                    start = i
            elif start is not None:
                runs.append((start, i))
                start = None
        if start is not None:
            runs.append((start, len(colors)))

        # 2. отбор: высота как у пузыря, внутри преимущественно «свой» цвет
        result: List[Tuple[int, int]] = []
        for top, bottom in runs:
            height = bottom - top
            if not cfg.MESSAGES_MIN_SEGMENT_HEIGHT <= height <= cfg.MESSAGES_MAX_SEGMENT_HEIGHT:
                continue
            segment_colors = colors[top:bottom]
            own = sum(
                1 for p in segment_colors
                if ScreenAnalyzer.color_matches(p, own_color, tolerance)
            )
            foreign = sum(
                1 for p in segment_colors
                if ScreenAnalyzer.color_matches(p, foreign_color, tolerance)
            )
            if own < 10 or foreign > own:
                continue
            result.append((top, bottom))
        return result

    def _read_message_time(self, seg: _MessageSegment) -> datetime | None:
        """Распознать время у нижней границы отрезка (прямоугольник из конфига)."""
        offset = cfg.MY_MESS_TIME_ZONE if seg.is_mine else cfg.ANOTH_MESS_TIME_ZONE
        x = seg.scan_x + offset[0]
        y = seg.bottom + offset[1]
        text = ScreenAnalyzer.get_text_in_region(x, y, offset[2], offset[3])
        parsed = self._parse_message_time(text)
        logger.debug("Время отрезка y=%d..%d: %r -> %s", seg.top, seg.bottom, text, parsed)
        return parsed

    @staticmethod
    def _parse_message_time(text: str) -> datetime | None:
        """Разобрать время из OCR-строки: «14:35», «вчера 14:35», «12.11.2026 14:35».

        Returns:
            datetime или None, если время распознать не удалось.
        """
        if not text:
            return None
        normalized = " ".join(text.lower().split())

        m_time = re.search(r"(\d{1,2}):(\d{2})", normalized)
        if not m_time:
            return None
        hour, minute = int(m_time.group(1)), int(m_time.group(2))
        if hour > 23 or minute > 59:
            return None

        now = datetime.now()
        if "вчера" in normalized:
            day = now.date() - timedelta(days=1)
        else:
            m_date = re.search(r"(\d{1,2})[./](\d{1,2})(?:[./](\d{2,4}))?", normalized)
            if m_date:
                day_num, month = int(m_date.group(1)), int(m_date.group(2))
                year = int(m_date.group(3)) if m_date.group(3) else now.year
                if m_date.group(3) and len(m_date.group(3)) == 2:
                    year += 2000
                try:
                    day = date(year, month, day_num)
                except ValueError:
                    day = now.date()
            else:
                day = now.date()  # только время без даты — считаем сегодня

        return datetime(day.year, day.month, day.day, hour, minute)

    def _find_button_copy():
        chat_image = ScreenAnalyzer()
    

    def _copy_message_text(self, seg: _MessageSegment) -> str:
        """Скопировать текст сообщения: правый клик -> «Копировать» -> буфер.

        Returns:
            Текст сообщения или "", если скопировать не удалось.
        """
        offset = cfg.MY_MESS_COPY_OFFSET if seg.is_mine else cfg.ANOTH_MESS_COPY_OFFSET
        x = seg.scan_x + offset[0]
        # держим точку клика внутри отрезка (ближе к центру)
        y = (seg.top + seg.bottom) // 2 + offset[1]
        y = min(max(y, seg.top + 2), seg.bottom - 2)

        ScreenAnalyzer.set_clipboard_text("")  # чтобы отличить неудачу от старого содержимого
        ScreenAnalyzer.move_mouse_to(x, y, duration=0.2)
        ScreenAnalyzer.click_in_place(x, y, button="right")
        
        # теперь сложное: меню может выскочить в любом месте по оси Y, слева или справа от точки клика, в зависимости 
        # от того, по моим пузырям или чужим.
        # Также кнопка копировать может быть не на том месте, где мы ожидаем (например, если в сообщении есть картинка или файл)
        # Поэтому мы кликаем правой кнопкой по сообщению, получаем картинку всей части окна с диалогом,
        # ищем вдоль оси Y (X правее/левее на 10px чем клик) когда цвет пикселей сменится на цвет фона меню. 
        # Так найдем верхнюю границу меню. Далее ищем вдоль оси Y, когда цвет фона меню обратно сменится на другой цвет 
        # фона чата. Так найдем нижнюю границу меню. Нижняя границе может совпасть с границей окна, предусмотреть
        # затем также вдоль оси X ищем начало и конец меню по фону (Y на 10px ниже точки клика)
        # в полученых координатах распознаем текст. Убираем пустые строки. Получаем точное меню на экране
        # Ищем текст Скопировать сообщение, узнаем номер строки. Множим номер строки на высоту строки (константа будет дана)
        # и получаем Y нужно строки, делаем клик по середине по Y и на 20 px правее (или левее, если меню для моего сообщения)

        menu_x, menu_y = self._find_button_copy()
        





        ScreenAnalyzer.click_in_place(menu_x, menu_y)
        time.sleep(cfg.CLICK_SETTLE_DELAY)
        ScreenAnalyzer.press_key("esc")  # закрыть меню, если пункт не совпал

        text = ScreenAnalyzer.get_clipboard_text().strip()
        if not text:
            logger.warning("Не удалось скопировать сообщение в точке (%d, %d)", x, y)
        return text

    # ------------------------------------------------------------------
    # 6. Отправка сообщения
    # ------------------------------------------------------------------

    def send_message(self, text: str) -> None:
        """Отправить текст в поле ввода открытого чата.

        Клик по полю ввода -> ввод текста (буфер обмена + Ctrl+V) -> Enter.
        """
        if not text:
            return

        self.activate()

        # Клик по полю ввода, чтобы перевести фокус в него
        x, y, width, height = self._absolute_zone(cfg.MESSAGE_INPUT_ZONE)
        ScreenAnalyzer.click_in_place(x + width // 2, y + height // 2)
        time.sleep(cfg.CLICK_SETTLE_DELAY)

        ScreenAnalyzer.type_text_clipboard(text)
        time.sleep(cfg.SEND_KEY_DELAY)

        ScreenAnalyzer.press_key(cfg.SUBMIT_KEY)

    def type_message(self, text: str) -> None:
        """Ввести текст в поле ввода, НЕ отправляя его.

        Нужен для проверки (get_input_text) перед submit_message().

        Заглушка: после реализации send_message() можно собирать из
        type_message() + submit_message(), чтобы не дублировать код.
        """
        pass  # TODO: клик по полю ввода + type_text_clipboard()

    def submit_message(self) -> None:
        """Отправить то, что набрано в поле ввода (Enter)."""
        pass  # TODO: press_key(cfg.SUBMIT_KEY)

    def get_input_text(self) -> str:
        """Прочитать текст, набранный в поле ввода (Ctrl+A -> Ctrl+C -> буфер).

        Внимание: буфер обмена затирается — серверный текст нужно сохранить
        заранее (до type_message).

        Returns:
            Набранный текст или "", если прочитать не удалось.
        """
        return ""  # TODO: выделить всё в поле ввода и скопировать

    def is_message_sent(self, text: str) -> bool:
        """Проверить, что сообщение с таким текстом появилось в ленте.

        TODO из алгоритма: проверка статуса отправленного сообщения.

        Returns:
            True, если последнее сообщение в ленте совпадает с `text`.
        """
        return False  # TODO: прочитать последнее сообщение ленты и сравнить

    # ------------------------------------------------------------------
    # 7. Клик по чату
    # ------------------------------------------------------------------

    def click_chat(self, chat: str) -> bool:
        """Кликнуть по чату с указанным именем, чтобы открыть его.

        Ищет только среди видимых на экране чатов (find_chat); если чата нет
        на экране — вернуть False, а вызывающий код прокрутит список и повторит.

        Returns:
            True, если чат найден и по нему кликнули.
        """
        return False  # TODO: find_chat() + клик по позиции строки

    def click_chat_at(self, position: Point) -> bool:
        """Кликнуть по строке чата в указанной позиции.

        Args:
            position: центр строки чата в координатах окна.

        Returns:
            True, если позиция внутри зоны списка чатов и клик выполнен.
        """
        return False  # TODO: проверить, что позиция внутри CHAT_LIST_ZONE, и кликнуть

    # ------------------------------------------------------------------
    # Приватные помощники
    # ------------------------------------------------------------------

    def _scroll(self, point: Point, direction: int, amount: int) -> None:
        """Прокрутить колёсиком над точкой окна и дать списку перерисоваться."""
        logger.info("Прокрутка списка чатов...")
        x, y = self._abs_pnt(point)
        ScreenAnalyzer.scroll_at(x, y, direction, amount)
        time.sleep(cfg.SCROLL_SETTLE_DELAY)


if __name__ == "__main__":
    pyautogui.FAILSAFE = False
    
    TEST = 0.1

    if TEST == 0:   #тест координат скрина экрана
        viber = ViberWindow()
        viber.activate()
        time.sleep(cfg.SCROLL_SETTLE_DELAY)
        x,y,w,h = viber._absolute_zone((0, 0, 300, 300))
        ScreenAnalyzer.capture_region(x, y, w, h).save(f"test_{time.time()}.png")
        pass

    if TEST == 0.1:   #тест сканирования текста в зоне меню чата
        viber = ViberWindow()
        viber.activate()
        time.sleep(5)   #за это время нужно открыть меню нижнего сообщения собеседника на первой букве
        x,y,w,h = viber._absolute_zone((374,310,178,261))
        text = ScreenAnalyzer.get_text_in_region(x, y, w, h)
        print(f"Текст в зоне: \n{text}")

    if TEST == 1:   #тест сканирования списка чатов и получения их имён
        logger.info("Тестирование ViberWindow...")
        viber = ViberWindow()
        viber.activate()
        print(f"Окно '{viber.title}': {viber._window_rect()}")
        print(f"Есть новые сообщения: {viber.has_new_messages()}")
        print(f"Позиции непрочитанных (заглушка): {viber.find_unread_chat_positions()}")
        print(f"Чаты на экране (заглушка): {viber.get_chat_list()}")
        print(f"Сообщения: {viber.get_messages()}")

        #тестовый цикл сканирования чатов и получения их имён
        while True:
            try:
                viber.activate()
                chat_list = viber.get_chat_list()
                print(f"Чаты на экране: {chat_list}")
                time.sleep(5)
                #прокуртить список чатов вниз
                viber.scroll_chats(ViberWindow.SCROLL_DOWN, 50)
                #сделать скрин списка чатов и сохранить в файл
                x, y, width, height = viber._absolute_zone(cfg.CHAT_LIST_ZONE)
                ScreenAnalyzer.capture_region(x, y, width, height).save(f"chat_list_{time.time()}.png")
            except: 
                pass

    if TEST == 2:   #тест чтения названия открытого чата
        viber = ViberWindow()
        viber.activate()
        cchat_name = viber.get_opened_chat_name()   
        print(f"Имя открытого чата: {cchat_name}")
        viber.scroll_messages_to_bottom()

    if TEST == 3:   #тест чтения сообщений открытого чата
        viber = ViberWindow()
        viber.activate()
        messages = viber.get_messages(since=None)
        for msg in messages:
            print(f"{msg.time} {'(мое)' if msg.is_mine else '(чужое)'}: {msg.text}")

