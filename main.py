import os
import json
import asyncio
import requests
import inspect
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from github import Github
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
MY_TELEGRAM_ID = int(os.getenv("MY_TELEGRAM_ID", 0))
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
gh = Github(GITHUB_TOKEN)
groq_client = Groq(api_key=GROQ_API_KEY)

# --- ФУНКЦІЇ GITHUB ---

def list_repo_files(repo_name: str, path: str = "") -> str:
    """Виводить список файлів у репозиторії."""
    try:
        user = gh.get_user()
        repo = user.get_repo(repo_name)
        contents = repo.get_contents(path)
        if isinstance(contents, list):
            return "\n".join([f"- {c.name}" for c in contents])
        return f"Файл: {contents.name}"
    except Exception as e:
        return f"Помилка отримання файлів: {e}"

def list_github_repositories(limit: int = 50) -> str:
    user = gh.get_user()
    repos = list(user.get_repos())
    return "\n".join([f"- {r.name}" for r in repos[:limit]])

def create_or_update_file(repo_name: str, path: str, content: str) -> str:
    user = gh.get_user()
    repo = user.get_repo(repo_name)
    try:
        existing = repo.get_contents(path)
        repo.update_file(path, "Update", content, existing.sha)
        return "Оновлено."
    except:
        repo.create_file(path, "Create", content)
        return "Створено."

def get_file_content(repo_name: str, path: str) -> str:
    user = gh.get_user()
    repo = user.get_repo(repo_name)
    return repo.get_contents(path).decoded_content.decode('utf-8')

# --- БЕЗПЕЧНИЙ ВИКЛИК ---

tools_map = {
    "list_repo_files": list_repo_files,
    "list_github_repositories": list_github_repositories,
    "create_or_update_file": create_or_update_file,
    "get_file_content": get_file_content
}

def safe_call(func, args):
    sig = inspect.signature(func)
    # Залишаємо тільки ті аргументи, які функція реально приймає
    filtered_args = {k: v for k, v in args.items() if k in sig.parameters}
    return func(**filtered_args)

# --- BOT LOGIC ---

@dp.message()
async def handle(message: types.Message):
    if message.from_user.id != MY_TELEGRAM_ID: return
    
    msg = await message.answer("🧠 Думаю...")
    try:
        response = groq_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": message.text}],
            tools=[{"type": "function", "function": {"name": n, "description": f.__doc__, "parameters": {"type": "object", "properties": {}}}} for n, f in tools_map.items()]
        )
        
        tool_calls = response.choices[0].message.tool_calls
        if tool_calls:
            results = []
            for tc in tool_calls:
                fn = tools_map.get(tc.function.name)
                args = json.loads(tc.function.arguments)
                results.append(safe_call(fn, args))
            await msg.edit_text("\n".join(results))
        else:
            await msg.edit_text(response.choices[0].message.content)
    except Exception as e:
        await msg.edit_text(f"❌ Помилка: {e}")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
