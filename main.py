import os
import json
import asyncio
import inspect
from aiogram import Bot, Dispatcher, types
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
    """Виводить список файлів у вказаному репозиторії GitHub."""
    try:
        # Прибираємо можливі префікси або повні URL
        repo_name = repo_name.strip("/").split("/")[-1]
        user = gh.get_user()
        repo = user.get_repo(repo_name)
        contents = repo.get_contents(path)
        if isinstance(contents, list):
            return f"📂 Файли в {repo_name}/{path}:\n" + "\n".join([f"- {c.name}" for c in contents])
        return f"📄 Файл: {contents.name}"
    except Exception as e:
        return f"❌ Помилка отримання файлів: {e}"

def list_github_repositories(limit: int = 50) -> str:
    """Виводить список усіх репозиторіїв користувача."""
    try:
        user = gh.get_user()
        repos = list(user.get_repos())
        return "📦 Ваші репозиторії:\n" + "\n".join([f"- {r.name}" for r in repos[:limit]])
    except Exception as e:
        return f"❌ Помилка отримання списку репозиторіїв: {e}"

def create_or_update_file(repo_name: str, path: str, content: str) -> str:
    """Створює або оновлює файл у репозиторії GitHub."""
    try:
        repo_name = repo_name.strip("/").split("/")[-1]
        user = gh.get_user()
        repo = user.get_repo(repo_name)
        try:
            existing = repo.get_contents(path)
            repo.update_file(path, "Update file via AI Assistant", content, existing.sha)
            return f"✅ Файл '{path}' успішно оновлено в репозиторії '{repo_name}'."
        except:
            repo.create_file(path, "Create file via AI Assistant", content)
            return f"✅ Файл '{path}' успішно створено в репозиторії '{repo_name}'."
    except Exception as e:
        return f"❌ Помилка при записі файлу: {e}"

def get_file_content(repo_name: str, path: str) -> str:
    """Отримує текстовий вміст конкретного файлу з репозиторію."""
    try:
        repo_name = repo_name.strip("/").split("/")[-1]
        user = gh.get_user()
        repo = user.get_repo(repo_name)
        content = repo.get_contents(path).decoded_content.decode('utf-8')
        return f"📄 Вміст {path}:\n\n```{content}```"
    except Exception as e:
        return f"❌ Помилка читання файлу: {e}"

# --- КАРТА ІНСТРУМЕНТІВ ---

tools_map = {
    "list_repo_files": list_repo_files,
    "list_github_repositories": list_github_repositories,
    "create_or_update_file": create_or_update_file,
    "get_file_content": get_file_content
}

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "list_repo_files",
            "description": list_repo_files.__doc__ or "Отримати список файлів",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_name": {"type": "string", "description": "Назва репозиторію (наприклад, ai-dev-bot)"},
                    "path": {"type": "string", "description": "Шлях до папки (за замовчуванням порожньо)"}
                },
                "required": ["repo_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_github_repositories",
            "description": list_github_repositories.__doc__ or "Отримати список репозиторіїв",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Максимальна кількість репозиторіїв"}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_or_update_file",
            "description": create_or_update_file.__doc__ or "Створити або оновити файл",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_name": {"type": "string", "description": "Назва репозиторію"},
                    "path": {"type": "string", "description": "Шлях/ім'я файлу (наприклад, index.html)"},
                    "content": {"type": "string", "description": "Повний новий вміст файлу"}
                },
                "required": ["repo_name", "path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_file_content",
            "description": get_file_content.__doc__ or "Прочитати вміст файлу",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_name": {"type": "string", "description": "Назва репозиторію"},
                    "path": {"type": "string", "description": "Шлях до файлу"}
                },
                "required": ["repo_name", "path"]
            }
        }
    }
]

# --- БЕЗПЕЧНИЙ ВИКЛИК ФУНКЦІЙ ---

def safe_call(func, args):
    """Викликає функцію, передаючи лише ті аргументи, які вона приймає."""
    sig = inspect.signature(func)
    filtered_args = {k: v for k, v in args.items() if k in sig.parameters}
    return func(**filtered_args)

# --- ЛОГІКА БОТА ---

SYSTEM_PROMPT = (
    "Ти — розумний Dev Assistant. Твоя мета — допомагати розробнику працювати з його GitHub репозиторіями.\n"
    "Якщо користувач просить внести зміни або замінити код (наприклад, зробити 3D сайт), одразу підготовуй готовий код "
    "і викликай функцію 'create_or_update_file'. Не став забагато уточнюючих питань, дій рішуче."
)

@dp.message()
async def handle(message: types.Message):
    if MY_TELEGRAM_ID and message.from_user.id != MY_TELEGRAM_ID:
        return
    
    msg = await message.answer("🧠 Обробляю запит...")
    try:
        response = groq_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": message.text}
            ],
            tools=TOOLS_SCHEMA
        )
        
        choice = response.choices[0].message
        tool_calls = choice.tool_calls

        if tool_calls:
            results = []
            for tc in tool_calls:
                fn_name = tc.function.name
                if fn_name in tools_map:
                    fn = tools_map[fn_name]
                    try:
                        args = json.loads(tc.function.arguments) if tc.function.arguments else {}
                    except Exception:
                        args = {}
                    res = safe_call(fn, args)
                    results.append(res)
                else:
                    results.append(f"❌ Невідома функція: {fn_name}")
            
            await msg.edit_text("\n\n".join(results), parse_mode="Markdown")
        else:
            await msg.edit_text(choice.content or "Отримано порожню відповідь.")

    except Exception as e:
        await msg.edit_text(f"❌ Помилка виконання: {e}")

async def main():
    print("🤖 Бот запущений...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
