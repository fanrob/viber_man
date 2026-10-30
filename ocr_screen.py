"""Скриншот экрана -> OCR -> текстовый файл.

Каждые 5 секунд снимает весь экран, распознавает текст (русский + английский)
и записывает его в output.txt (перезаписывая файл целиком).
"""

import time
from datetime import datetime
from pathlib import Path

import mss
import pytesseract
from PIL import Image

TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
OUTPUT_FILE = Path(__file__).with_name("output.txt")
INTERVAL = 5  # секунд
LANG = "rus+eng"

pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH


def capture_screen() -> Image.Image:
    """Снимок всего экрана (все мониторы складываются в одно изображение)."""
    with mss.mss() as sct:
        monitor = sct.monitors[0]  # 0 = объединённая область всех мониторов
        shot = sct.grab(monitor)
        return Image.frombytes("RGB", shot.size, shot.rgb)


def ocr_image(image: Image.Image) -> str:
    text = pytesseract.image_to_string(image, lang=LANG)
    return text.strip()


def main() -> None:
    print(f"Запуск. Интервал {INTERVAL} с, вывод в {OUTPUT_FILE}")
    while True:
        started = time.monotonic()
        try:
            text = ocr_image(capture_screen())
            OUTPUT_FILE.write_text(text, encoding="utf-8")
            stamp = datetime.now().strftime("%H:%M:%S")
            print(f"[{stamp}] распознано {len(text)} символов")
        except Exception as exc:  # noqa: BLE001 - не роняем цикл из-за сбоя кадра
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ошибка: {exc}")

        elapsed = time.monotonic() - started
        time.sleep(max(0.0, INTERVAL - elapsed))


if __name__ == "__main__":
    main()
