import os
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from github import Github
from google import genai
from google.genai import types as genai_types
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
MY_TELEGRAM_ID = int(os.getenv("MY_TELEGRAM_ID", 0))
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

gh = Github(GITHUB_TOKEN)
ai_client = genai.Client(api_key=GEMINI_API_KEY)

# --- ФУНКЦІЇ ДЛЯ GITHUB (TOOLS) ---

def create_github_repository(name: str, private: bool = False) -> str:
    """Створює новий репозиторій на GitHub."""
    try:
        user = gh.get_user()
        repo = user.create_repo(name, private=private)
        return f"Успішно створено репозиторій: {repo.html_url}"
    except Exception as e:
        return f"Помилка створення репозиторію: {e}"

def list_github_repositories() -> str:
    """Повертає список останніх репозиторіїв користувача."""
    try:
        user = gh.get_user()
        repos = user.get_repos()
        repo_names = [f"- {r.name} ({r.html_url})" for r in repos[:15]]
        if not repo_names:
            return "У вас немає репозиторіїв."
        return "Ваші репозиторії:\n" + "\n".join(repo_names)
    except Exception as e:
        return f"Помилка отримання списку: {e}"

def delete_github_repository(name: str) -> str:
    """Видаляє репозиторій за його назвою."""
    try:
        user = gh.get_user()
        repo = user.get_repo(name)
        repo.delete()
        return f"Репозиторій '{name}' успішно видалено."
    except Exception as e:
        return f"Помилка видалення: {e}"

# Списковий масив інструментів для Gemini
tools_list = [create_github_repository, list_github_repositories, delete_github_repository]

SYSTEM_INSTRUCTION = (
    "Ти — розширений AI Dev Assistant для Володимира Патика. "
    "Ти маєш ПРЯМИЙ доступ до керування його акаунтом GitHub через вбудовані функції (tools). "
    "Коли користувач просить створити, показати або видалити репозиторій — обов'язково викликай відповідні функції."
)

def is_owner(user_id: int) -> bool:
    return user_id == MY_TELEGRAM_ID

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    if not is_owner(message.from_user.id):
        return
    await message.answer(
        "🤖 **AI Dev Assistant готовий!**\n\n"
        "Тепер ти можеш писати мені звичайними словами:\n"
        "• *«Створи репозиторій my-test-bot»*\n"
        "• *«Покажи мої репозиторії»*\n"
        "• *«Видали репозиторій test»*"
    )

@dp.message()
async def handle_ai_prompt(message: types.Message):
    if not is_owner(message.from_user.id):
        return
    
    msg = await message.answer("🧠 Обробка запиту...")
    
    try:
        # Передаємо функції у параметр tools
        response = ai_client.models.generate_content(
            model=GEMINI_MODEL,
            contents=message.text,
            config=genai_types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                tools=tools_list
            )
        )
        
        # Перевірка чи ШІ викликав функцію
        if response.function_calls:
            for call in response.function_calls:
                func_name = call.name
                args = call.args
                
                # Виконуємо відповідну функцію
                if func_name == "create_github_repository":
                    result = create_github_repository(**args)
                elif func_name == "list_github_repositories":
                    result = list_github_repositories()
                elif func_name == "delete_github_repository":
                    result = delete_github_repository(**args)
                else:
                    result = "Невідома функція."
                
                await msg.edit_text(f"⚙️ **Виконано діяю:**\n{result}")
                return

        await msg.edit_text(response.text)
    except Exception as e:
        await msg.edit_text(f"❌ Помилка: {e}")

async def main():
    print("Бот запущений...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
