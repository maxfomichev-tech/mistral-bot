import telebot
from mistralai import Mistral
from mistralai.models import ToolFileChunk
import os
import uuid
import re

# === Загрузка переменных окружения ===
# TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
# MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "").strip()

# === Инициализация клиентов ===
client = Mistral(api_key=MISTRAL_API_KEY)
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

# === Утилита очистки Markdown ===
def clean_markdown(text: str) -> str:
    """Удаляет символы Markdown, чтобы Telegram не выдавал ошибку форматирования"""
    if not text:
        return ""
    text = re.sub(r'[*_`>#~\-]', '', text)  # убираем markdown-символы
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)  # убираем ссылки [текст](ссылка)
    text = re.sub(r'<[^>]+>', '', text)  # убираем HTML-теги
    return text.strip()

# === Главное меню ===
def get_main_menu():
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(telebot.types.KeyboardButton("Создать пост"))
    return markup

# === Команды ===
@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(
        message.chat.id,
        "Привет! 👋\nЯ могу создать пост с текстом и изображением по вашему запросу.\n"
        "Просто отправьте мне тему — и я сделаю магию!",
        reply_markup=get_main_menu()
    )

@bot.message_handler(func=lambda message: message.text == "Создать пост")
def request_prompt(message):
    bot.send_message(message.chat.id, "Введите тему или запрос для генерации поста:")

# === Генерация поста ===
@bot.message_handler(func=lambda message: True)
def generate_post(message):
    user_prompt = message.text
    chat_id = message.chat.id

    bot.send_message(chat_id, "🎯 Генерирую текст и изображение...")

    # === Генерация текста ===
    try:
        text_response = client.chat.complete(
            model="mistral-medium-latest",
            messages=[{
                "role": "user",
                "content": (
                    f"Ты опытный SMM-специалист. Напиши живой, цепляющий пост на тему: {user_prompt}."
                    "Должен присутствовать интересный факт."
                    "До 1024 знаков, с умеренным количеством эмодзи. "
                    "Не используй markdown, списки или заголовки."
                )
            }]
        )
        post_text = text_response.choices[0].message.content
        post_text = clean_markdown(post_text)
    except Exception as e:
        bot.send_message(chat_id, "❌ Ошибка при генерации текста.")
        print("Ошибка текста:", e)
        return

    # === Генерация изображения ===
    try:
        image_agent = client.beta.agents.create(
            model="mistral-medium-2505",
            name="Image Generation Agent",
            description="Agent used to generate images.",
            tools=[{"type": "image_generation"}],
            completion_args={"temperature": 0.3, "top_p": 0.95}
        )

        response = client.beta.conversations.start(
            agent_id=image_agent.id,
            inputs=f"Generate an image for this topic: {user_prompt}"
        )

        for chunk in response.outputs[-1].content:
            if isinstance(chunk, ToolFileChunk):
                file_bytes = client.files.download(file_id=chunk.file_id).read()

                temp_filename = f"{uuid.uuid4()}.png"
                with open(temp_filename, "wb") as f:
                    f.write(file_bytes)

                # === Отправка текста и изображения ===
                MAX_CAPTION_LENGTH = 1024
                if len(post_text) > MAX_CAPTION_LENGTH:
                    short_text = post_text[:MAX_CAPTION_LENGTH - 50].rsplit(" ", 1)[0] + "..."
                    short_text += "\n\n🔗 Далее — см. сообщение ниже 👇"

                    with open(temp_filename, "rb") as photo:
                        bot.send_photo(chat_id, photo, caption=short_text)

                    bot.send_message(chat_id, post_text)
                else:
                    with open(temp_filename, "rb") as photo:
                        bot.send_photo(chat_id, photo, caption=post_text)

                os.remove(temp_filename)
                break
        else:
            bot.send_message(chat_id, "⚠️ Изображение не было сгенерировано.")
    except Exception as e:
        bot.send_message(chat_id, "❌ Ошибка при генерации изображения.")
        print("Ошибка изображения:", e)

# === Запуск ===
if __name__ == "__main__":
    print("Бот запущен...")
    bot.delete_webhook()
    bot.polling(none_stop=True)