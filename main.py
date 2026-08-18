import os
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from github import Github
from google import genai
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

def is_owner(user_id: int) -> bool:
    return user_id == MY_TELEGRAM_ID

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    if not is_owner(message.from_user.id):
        return
    await message.answer("🤖 **AI Dev Assistant готовий до роботи!**\n\nЯ можу створювати репозиторії, генерувати код та керувати GitHub.")

@dp.message(Command("create_repo"))
async def create_repo_cmd(message: types.Message):
    if not is_owner(message.from_user.id):
        return
    
    repo_name = message.text.replace("/create_repo", "").strip()
    if not repo_name:
        await message.answer("Вкажіть назву репозиторію: `/create_repo my-new-project`", parse_mode="Markdown")
        return

    try:
        user = gh.get_user()
        repo = user.create_repo(repo_name, private=False)
        await message.answer(f"✅ Репозиторій успішно створено:\n{repo.html_url}")
    except Exception as e:
        await message.answer(f"❌ Помилка створення репозиторію: {e}")

@dp.message()
async def handle_ai_prompt(message: types.Message):
    if not is_owner(message.from_user.id):
        return
    
    msg = await message.answer("🧠 Генерація відповіді...")
    
    try:
        response = ai_client.models.generate_content(
            model=GEMINI_MODEL,
            contents=message.text
        )
        await msg.edit_text(response.text)
    except Exception as e:
        await msg.edit_text(f"❌ Помилка Gemini API: {e}")

async def main():
    print("Бот запущений...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
