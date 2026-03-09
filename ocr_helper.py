import pytesseract
from PIL import Image
import os
import tempfile

# Если на Windows нужно указать путь к tesseract, раскомментируйте следующую строку и укажите правильный путь:
# pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

async def ocr_from_photo(file_path: str) -> str:
    """
    Распознаёт текст с фото с помощью Tesseract OCR.
    """
    try:
        image = Image.open(file_path)
        text = pytesseract.image_to_string(image, lang='rus')
        return text.strip()
    except Exception as e:
        return f"Ошибка OCR: {e}"

async def download_photo(bot, file_id: str) -> str:
    """
    Скачивает фото от Telegram и возвращает путь к временному файлу.
    """
    file = await bot.get_file(file_id)
    temp_dir = tempfile.gettempdir()
    file_path = os.path.join(temp_dir, f"{file_id}.jpg")
    await bot.download_file(file.file_path, file_path)
    return file_path