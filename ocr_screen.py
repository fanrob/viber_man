"""Утилиты экрана: скриншоты, OCR, поиск цвета, мышь и клавиатура.

Класс ScreenAnalyzer содержит переиспользуемые утилиты:
- снимки областей экрана и OCR;
- поиск пикселей нужного цвета;
- анализ рядов пикселей по уже полученному скрину (отрезки и группы
  одного цвета, границы участков в строке);
- клики, скролл колёсиком, ввод текста, нажатие клавиш;
- поиск и активация окна по заголовку.

main() — фоновый цикл: каждые 5 секунд снимает весь экран, распознавает текст
(русский + английский) и записывает его в output.txt (перезаписывая файл целиком).
"""

import time
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Sequence, Tuple

import mss
import pyautogui
import pyperclip
import pytesseract
from PIL import Image

TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
#TESSERACT_PATH = r"C:\Users\56\AppData\Local\Tesseract-OCR\tesseract.exe"
OUTPUT_FILE = Path(__file__).with_name("output.txt")
INTERVAL = 5  # секунд
LANG = "rus+eng"
DEBUG_SAVE_REGION = True  # сохранять снимки распознаваемых областей в region_*.png (отладка OCR)

SCROLL_UP = 1
SCROLL_DOWN = -1


def _ensure_tesseract() -> None:
    """Проверить наличие Tesseract и настроить путь к нему (лениво, при OCR)."""
    if not Path(TESSERACT_PATH).exists():
        raise FileNotFoundError(
            f"Tesseract не найден по пути: {TESSERACT_PATH}\n"
            "Проверьте, что приложение установлено в C:\\Users\\56\\AppData\\Local\\Tesseract-OCR"
        )
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH


class ScreenAnalyzer:
    """Класс для захвата экрана, OCR и анализа пикселей."""

    @staticmethod
    def capture_screen() -> Image.Image:
        """Снимок всего экрана (все мониторы складываются в одно изображение)."""
        with mss.mss() as sct:
            monitor = sct.monitors[0]  # 0 = объединённая область всех мониторов
            shot = sct.grab(monitor)
            return Image.frombytes("RGB", shot.size, shot.rgb)

    @staticmethod
    def capture_region(x: int, y: int, width: int, height: int) -> Image.Image:
        """Снимок прямоугольной области экрана по координатам x, y, width, height."""
        with mss.mss() as sct:
            region = {
                "left": max(0, x),
                "top": max(0, y),
                "width": max(1, width),
                "height": max(1, height),
            }
            shot = sct.grab(region)
            img = Image.frombytes("RGB", shot.size, shot.rgb)
            if DEBUG_SAVE_REGION:
                img.save(f"captregion_{int(time.time() * 1000)}.png")    
            return img

    @staticmethod
    def get_text_in_region(x: int, y: int, width: int, height: int, lang: str = LANG) -> str:
        """Получить текст из области экрана по координатам."""
        #для отладки можно сохранить снимок области в файл:
        
        _ensure_tesseract()
        image = ScreenAnalyzer.capture_region(x, y, width, height)
        text = pytesseract.image_to_string(image, lang=lang)
        if DEBUG_SAVE_REGION:
            image.save(f"gettext____{int(time.time() * 1000)}.png")
        return text.strip()

    @staticmethod
    def get_string_from_region(x: int, y: int, width: int, height: int, lang: str = LANG) -> str:
        _ensure_tesseract()
        image = ScreenAnalyzer.capture_region(x, y, width, height)
        text = pytesseract.image_to_string(
            image, lang=lang, config="--psm 7"
        ).strip()
        return text

    @staticmethod
    def get_pixels_colors_in_region(
        x: int,
        y: int,
        width: int,
        height: int,
        as_2d: bool = False,
    ) -> List[Tuple[int, int, int]] | List[List[Tuple[int, int, int]]]:
        """Получить массив цветов RGB точек в области экрана.

        По умолчанию возвращается плоский список из width * height элементов.
        Если as_2d=True, возвращается двумерный массив по строкам.
        """
        image = ScreenAnalyzer.capture_region(x, y, width, height)
        if DEBUG_SAVE_REGION:
            image.save(f"getpixls____{int(time.time() * 1000)}.png")
        pixels: List[Tuple[int, int, int]] = []

        for row in range(height):
            row_pixels: List[Tuple[int, int, int]] = []
            for col in range(width):
                pixel = image.getpixel((col, row))
                if as_2d:
                    row_pixels.append(pixel)
                else:
                    pixels.append(pixel)
            if as_2d:
                pixels.append(row_pixels)

        return pixels

    @staticmethod
    def color_matches(pixel: Tuple[int, int, int], target_color: Tuple[int, int, int], tolerance: int = 0) -> bool:
        """Проверить, совпадает ли цвет пикселя с target_color с допустимым отклонением."""
        return all(abs(pixel[i] - target_color[i]) <= tolerance for i in range(3))

    @staticmethod
    def count_color_pixels_in_region(
        x: int,
        y: int,
        width: int,
        height: int,
        target_color: Tuple[int, int, int],
        tolerance: int = 0,
    ) -> int:
        """Сколько пикселей области совпадают с target_color (с допуском)."""
        image = ScreenAnalyzer.capture_region(x, y, width, height)
        if DEBUG_SAVE_REGION:
            image.save(f"region_{int(time.time() * 1000)}.png")  # для отладки
        return sum(
            1
            for pixel in image.getdata()
            if ScreenAnalyzer.color_matches(pixel, target_color, tolerance)
        )

    @staticmethod
    def has_color_in_region(
        x: int,
        y: int,
        width: int,
        height: int,
        target_color: Tuple[int, int, int],
        tolerance: int = 0,
        min_pixels: int = 1,
    ) -> bool:
        """Есть ли в области хотя бы min_pixels пикселей нужного цвета."""
        count = ScreenAnalyzer.count_color_pixels_in_region(
            x, y, width, height, target_color, tolerance
        )
        return count >= min_pixels

    @staticmethod
    def get_first_non_color_y_in_region(
        x: int,
        y: int,
        width: int,
        height: int,
        target_color: Tuple[int, int, int],
        tolerance: int = 0,
    ) -> int | None:
        """Вернуть Y координату первого пикселя в прямоугольнике, который отличается от target_color.

        Поиск идёт сверху вниз и слева направо. Если все пиксели совпадают, возвращается None.
        """
        image = ScreenAnalyzer.capture_region(x, y, width, height)

        for row in range(height):
            for col in range(width):
                pixel = image.getpixel((col, row))
                if not ScreenAnalyzer.color_matches(pixel, target_color, tolerance):
                    return y + row

        return None

    # ------------------------------------------------------------------
    # Анализ рядов пикселей (по уже полученному скрину, без нового захвата)
    # ------------------------------------------------------------------

    @staticmethod
    def column_pixels(image: Image.Image, x: int) -> List[Tuple[int, int, int]]:
        """Вертикальный ряд пикселей (столбец x) из уже полученного скрина.

        Индекс элемента списка — это Y внутри изображения (сверху вниз).
        """
        if not 0 <= x < image.width:
            raise ValueError(f"x={x} вне границ изображения (0..{image.width - 1})")
        px = image.load()
        return [px[x, y] for y in range(image.height)]

    @staticmethod
    def row_pixels(image: Image.Image, y: int) -> List[Tuple[int, int, int]]:
        """Горизонтальный ряд пикселей (строка y) из уже полученного скрина.

        Индекс элемента списка — это X внутри изображения (слева направо).
        """
        if not 0 <= y < image.height:
            raise ValueError(f"y={y} вне границ изображения (0..{image.height - 1})")
        px = image.load()
        return [px[x, y] for x in range(image.width)]

    @staticmethod
    def find_runs(
        pixels: Sequence[Tuple[int, int, int]],
        is_match: Callable[[Tuple[int, int, int]], bool],
    ) -> List[Tuple[int, int]]:
        """Найти в ряду пикселей отрезки подряд идущих пикселей, где is_match() истинно.

        Args:
            pixels: ряд пикселей (обычно вертикальный: индекс = Y, сверху вниз).
            is_match: предикат «пиксель того, что ищем» (цвет, фон, меню...).

        Returns:
            Список (start, end), сверху вниз: end — индекс первого пикселя,
            не прошедшего проверку (не включается); если такие пиксели
            отсутствуют до конца ряда — end == len(pixels).
        """
        runs: List[Tuple[int, int]] = []
        start: int | None = None
        for i, pixel in enumerate(pixels):
            if is_match(pixel):
                if start is None:
                    start = i
            elif start is not None:
                runs.append((start, i))
                start = None
        if start is not None:
            runs.append((start, len(pixels)))
        return runs

    @staticmethod
    def find_color_runs(
        pixels: Sequence[Tuple[int, int, int]],
        target_color: Tuple[int, int, int],
        tolerance: int = 0,
    ) -> List[Tuple[int, int]]:
        """Непрерывные отрезки пикселей одного цвета (сверху вниз)."""
        return ScreenAnalyzer.find_runs(
            pixels,
            lambda pixel: ScreenAnalyzer.color_matches(pixel, target_color, tolerance),
        )

    @staticmethod
    def find_foreign_color_runs(
        pixels: Sequence[Tuple[int, int, int]],
        background_color: Tuple[int, int, int],
        tolerance: int = 0,
    ) -> List[Tuple[int, int]]:
        """Отрезки пикселей, отличных от background_color (сверху вниз).

        Участок прерывается на первом фоновом пикселе — даже одиночный шум
        его разрывает. Если промежутки нужно схлопывать, используйте
        find_color_groups с merge_gap.
        """
        return ScreenAnalyzer.find_runs(
            pixels,
            lambda pixel: not ScreenAnalyzer.color_matches(pixel, background_color, tolerance),
        )

    @staticmethod
    def find_color_groups(
        pixels: Sequence[Tuple[int, int, int]],
        target_color: Tuple[int, int, int],
        tolerance: int = 0,
        merge_gap: int = 0,
    ) -> List[Tuple[int, int]]:
        """Группы пикселей одного цвета в вертикальном ряду.

        Две группы, разделённые промежутком «не того» цвета длиной не больше
        merge_gap, объединяются в одну (шум/сглаживание/прочерк между
        участками одного цвета не должны резать группу на части).

        Args:
            pixels: вертикальный ряд пикселей из уже полученного скрина
                (см. column_pixels); индекс = Y, сверху вниз.
            target_color: искомый цвет.
            tolerance: допуск сравнения (см. color_matches).
            merge_gap: сколько пикселей другого цвета допускается между
                группами (0 — группы не объединяются).

        Returns:
            Список (y_start, y_end), отсортированный сверху вниз, где
            y_start — Y первого пикселя группы, y_end — Y первого пикселя
            после группы (не включается, как и в find_runs).
        """
        groups = ScreenAnalyzer.find_color_runs(pixels, target_color, tolerance)
        if merge_gap <= 0:
            return groups

        merged: List[Tuple[int, int]] = []
        for start, end in groups:
            if merged and start - merged[-1][1] <= merge_gap:
                merged[-1] = (merged[-1][0], end)
            else:
                merged.append((start, end))
        return merged

    @staticmethod
    def row_bounds(
        pixels_row: Sequence[Tuple[int, int, int]],
        col: int,
        is_match: Callable[[Tuple[int, int, int]], bool],
        require_center: bool = True,
    ) -> Tuple[int, int] | None:
        """Границы участка одного цвета в горизонтальном ряду, содержащем col.

        Участок ищется в обе стороны от col, пока пиксели проходят is_match.

        Args:
            pixels_row: горизонтальный ряд пикселей (см. row_pixels).
            col: колонка, внутри которой должен находиться участок.
            is_match: предикат «пиксель того, что ищем».
            require_center: True — пиксель col обязан проходить по is_match,
                иначе None; False — цвет самого col не проверяется, зато
                границы всё равно расширяются в обе стороны (нужно, если
                колонка попала на «букву» внутри участка).

        Returns:
            (x0, x1) — не включая x1, либо None, если col вне ряда или
            (при require_center) пиксель col не проходит по is_match.
        """
        if not 0 <= col < len(pixels_row):
            return None
        if require_center and not is_match(pixels_row[col]):
            return None
        x0 = col
        while x0 > 0 and is_match(pixels_row[x0 - 1]):
            x0 -= 1
        x1 = col + 1
        while x1 < len(pixels_row) and is_match(pixels_row[x1]):
            x1 += 1
        return x0, x1

    @staticmethod
    def click_in_place(x: int, y: int, button: str = "left", clicks: int = 1, interval: float = 0.0) -> None:
        """Кликнуть левой/правой кнопкой мыши в указанное место."""
        ScreenAnalyzer.move_mouse_to(x,y,duration=0.2)
        print(f"{int(time.time()*1000)}: click {x}, {y}, {button}")
        pyautogui.click(x=x, y=y, button=button, clicks=clicks, interval=interval)
        return



    @staticmethod
    def move_mouse_to(x: int, y: int, duration: float = 0.0) -> None:
        """Переместить мышь в указанное место за duration секунд."""
        pyautogui.moveTo(x=x, y=y, duration=duration)

    @staticmethod
    def type_text(text: str, interval: float = 0.0) -> None:
        """Имитировать ввод текста с клавиатуры (только ASCII-символы)."""
        if not text:
            return
        pyautogui.typewrite(text, interval=interval)

    @staticmethod
    def type_text_clipboard(text: str) -> None:
        """Ввести текст через буфер обмена (Ctrl+V) — поддерживает кириллицу."""
        if not text:
            return
        pyperclip.copy(text)
        pyautogui.hotkey("ctrl", "v")

    @staticmethod
    def get_clipboard_text() -> str:
        """Прочитать текстовый содержимое буфера обмена ("" если буфер пуст/не текст)."""
        return pyperclip.paste() or ""

    @staticmethod
    def set_clipboard_text(text: str) -> None:
        """Положить текст в буфер обмена (без ввода с клавиатуры)."""
        pyperclip.copy(text)

    @staticmethod
    def press_key(key: str) -> None:
        """Нажать клавишу (например, 'enter') или комбинацию (например, 'ctrl+c')."""
        if "+" in key:
            pyautogui.hotkey(*key.split("+"))
        else:
            pyautogui.press(key)

    @staticmethod
    def scroll_at(x: int, y: int, direction: int, amount: int = 5) -> None:
        """Повернуть колёсико мыши над точкой (x, y).

        direction: 1 — прокрутить вверх, -1 — вниз. amount — щелчки колёсика.
        """
        if direction not in (SCROLL_UP, SCROLL_DOWN):
            raise ValueError(
                f"direction должен быть {SCROLL_UP} (вверх) или {SCROLL_DOWN} (вниз), получено: {direction}"
            )
        pyautogui.moveTo(x, y)
        pyautogui.scroll(direction * amount)

    @staticmethod
    def find_window(title: str):
        """Найти окно по заголовку. Вернуть объект окна или None."""
        windows = pyautogui.getWindowsWithTitle(title)
        return windows[0] if windows else None

    @staticmethod
    def activate_window(window) -> None:
        """Активировать окно: развернуть, если свёрнуто, и вывести на передний план."""
        if window.isMinimized:
            window.restore()
        try:
            window.activate()
        except Exception:  # noqa: BLE001 - Windows может запретить поднятие окна
            # Запасной путь: кликнуть по заголовку окна
            pyautogui.click(window.left + window.width // 2, window.top + 10)

    @staticmethod
    def ocr_image(image: Image.Image) -> str:
        _ensure_tesseract()
        text = pytesseract.image_to_string(image, lang=LANG)
        return text.strip()

    def main(self) -> None:
        print(f"Запуск. Интервал {INTERVAL} с, вывод в {OUTPUT_FILE}")
        while True:
            started = time.monotonic()
            try:
                text = self.ocr_image(self.capture_screen())
                stamp = datetime.now().strftime("%H:%M:%S")
                OUTPUT_FILE.write_text(f"[{stamp}] распознано {len(text)} символов", encoding="utf-8")
                print(f"[{stamp}] распознано {len(text)} символов")
            except Exception as exc:  # noqa: BLE001 - не роняем цикл из-за сбоя кадра
                print(f"[{datetime.now().strftime('%H:%M:%S')}] ошибка: {exc}")

            elapsed = time.monotonic() - started
            time.sleep(max(0.0, INTERVAL - elapsed))


if __name__ == "__main__":
    ScreenAnalyzer().main()


