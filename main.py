import uuid
import asyncio
import logging
import os
import aiohttp
import json
from typing import Any, Dict

from aiogram import Bot, Dispatcher, Router, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# Токены из .env файла
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GIGACHAT_API_KEY = os.getenv("GIGACHAT_API_KEY")
GIGACHAT_SCOPE = os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS")

# URL для GigaChat API (placeholder)
GIGACHAT_API_URL = "https://gigachat.devices.sberbank.ru/api/v1"

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Состояния FSM для диалога
class PostStates(StatesGroup):
    waiting_for_topic = State()

# Создаем роутер
router = Router()

async def generate_post_gigachat(prompt: str) -> str:
    """
    Функция для генерации поста через GigaChat API
    """
    auth_url = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
    chat_url = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"

    headers_auth = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
        "RqUID": str(uuid.uuid4()),  # Генерируем уникальный UUID для каждого запроса
        "Authorization": f"Basic {GIGACHAT_API_KEY}"  # Ключ из кабинета, закодирован в Base64
    }
    data_auth = {
        "scope": GIGACHAT_SCOPE  # обычно GIGACHAT_API_PERS
    }

    async with aiohttp.ClientSession() as session:
        # Получаем access token
        async with session.post(auth_url, headers=headers_auth, data=data_auth, ssl=False) as resp:
            if resp.status != 200:
                return f"❌ Ошибка авторизации: {resp.status}"
            res = await resp.json()
            access_token = res.get("access_token")
            if not access_token:
                return "❌ Не удалось получить access token"

        # Готовим промпт и отправляем запрос в GigaChat
        prompt_full = (
            f"Создай привлекательный текстовый пост для социальных сетей на тему: {prompt}\n\n"
            "Требования:\n- Используй эмодзи\n- Добавь заголовок\n- Форматируй текст по абзацам\n"
        )
        headers_chat = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {access_token}",
        }
        data_chat = {
            "model": "GigaChat",
            "messages": [
                {"role": "user", "content": prompt_full}
            ],
            "temperature": 0.7,
            "max_tokens": 1000
        }

        async with session.post(chat_url, headers=headers_chat, json=data_chat, ssl=False) as chat_resp:
            if chat_resp.status != 200:
                return f"❌ Ошибка генерации поста: {chat_resp.status}"
            result = await chat_resp.json()
            if "choices" in result and result["choices"]:
                return result["choices"][0]["message"]["content"]
            return "❌ Не удалось получить ответ от GigaChat"

@router.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    """
    Обработчик команды /start
    """
    welcome_text = f"""
🤖 **Привет, {message.from_user.first_name}!**

Я бот для генерации текстовых постов с помощью GigaChat AI! 

📝 **Доступные команды:**
• /start - показать это сообщение
• /post - создать новый пост

✨ Чтобы создать пост, просто введи команду /post и укажи тему!
    """
    
    await message.answer(welcome_text, parse_mode=ParseMode.MARKDOWN)

@router.message(Command("post"))
async def command_post_handler(message: Message, state: FSMContext) -> None:
    """
    Обработчик команды /post
    """
    await message.answer(
        "📝 **Создание поста**\n\n"
        "Напиши тему для поста, и я создам для тебя интересный контент с эмодзи и структурированным текстом!",
        parse_mode=ParseMode.MARKDOWN
    )
    await state.set_state(PostStates.waiting_for_topic)

@router.message(PostStates.waiting_for_topic)
async def process_post_topic(message: Message, state: FSMContext) -> None:
    """
    Обработка темы поста от пользователя
    """
    topic = message.text
    
    # Показываем, что бот работает
    await message.answer("🤖 Генерирую пост... Это может занять несколько секунд.")
    
    # Генерируем пост через GigaChat
    generated_post = await generate_post_gigachat(topic)
    
    # Отправляем результат
    await message.answer(
        f"✅ **Ваш пост готов:**\n\n{generated_post}",
        parse_mode=ParseMode.MARKDOWN
    )
    
    # Сбрасываем состояние
    await state.clear()

@router.message()
async def echo_handler(message: Message) -> None:
    """
    Обработчик всех остальных сообщений
    """
    await message.answer(
        "🤔 Я не понимаю эту команду.\n\n"
        "Используйте:\n"
        "• /start - для начала работы\n"
        "• /post - для создания поста"
    )

async def main() -> None:
    """
    Основная функция запуска бота
    """
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN не найден в переменных окружения!")
        return
    
    if not GIGACHAT_API_KEY:
        logger.error("GIGACHAT_API_KEY не найден в переменных окружения!")
        return
    
    # Создаем бота
    bot = Bot(
        token=TELEGRAM_BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    
    # Создаем диспетчер
    dp = Dispatcher(storage=MemoryStorage())
    
    # Подключаем роутер
    dp.include_router(router)
    
    logger.info("Бот запускается...")
    
    # Запускаем бота
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
