import os
import json
import asyncio
import inspect
from collections import defaultdict
from aiogram import Bot, Dispatcher, types
from github import Github
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
MY_TELEGRAM_ID = int(os.getenv("MY_TELEGRAM_ID", 0))
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "qwen/qwen3.6-27b")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
gh = Github(GITHUB_TOKEN)
groq_client = Groq(api_key=GROQ_API_KEY)

user_history = defaultdict(list)
MAX_HISTORY = 6

# --- ФУНКЦІЇ GITHUB ---

def list_repo_files(repo_name: str, path: str = "") -> str:
    """Виводить список файлів у репозиторії GitHub."""
    try:
        repo_name = repo_name.strip("/").split("/")[-1]
        user = gh.get_user()
        repo = user.get_repo(repo_name)
        contents = repo.get_contents(path)
        if isinstance(contents, list):
            return f"📂 Файли в {repo_name}/{path}:\n" + "\n".join([f"- {c.name}" for c in contents])
        return f"📄 Файл: {contents.name}"
    except Exception as e:
        return f"❌ Помилка отримання файлів: {e}"

def list_github_repositories(limit: int = 30) -> str:
    """Виводить список репозиторіїв користувача."""
    try:
        user = gh.get_user()
        repos = list(user.get_repos())
        return "📦 Репозиторії:\n" + "\n".join([f"- {r.name}" for r in repos[:limit]])
    except Exception as e:
        return f"❌ Помилка списку репозиторіїв: {e}"

def create_or_update_file(repo_name: str, path: str, content: str) -> str:
    """Створює або оновлює файл у репозиторії GitHub."""
    try:
        repo_name = repo_name.strip("/").split("/")[-1]
        user = gh.get_user()
        repo = user.get_repo(repo_name)
        try:
            existing = repo.get_contents(path)
            repo.update_file(path, "Update file via AI Assistant", content, existing.sha)
            return f"✅ Файл '{path}' успішно оновлено в '{repo_name}'."
        except:
            repo.create_file(path, "Create file via AI Assistant", content)
            return f"✅ Файл '{path}' успішно створено в '{repo_name}'."
    except Exception as e:
        return f"❌ Помилка запису файлу: {e}"

def get_file_content(repo_name: str, path: str) -> str:
    """Отримує текстовий вміст файлу з репозиторію."""
    try:
        repo_name = repo_name.strip("/").split("/")[-1]
        user = gh.get_user()
        repo = user.get_repo(repo_name)
        content = repo.get_contents(path).decoded_content.decode('utf-8')
        if len(content) > 3000:
            content = content[:3000] + "\n\n...[вміст обрізано для економії токенів]..."
        return content
    except Exception as e:
        return f"❌ Помилка читання файлу: {e}"

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
            "description": list_repo_files.__doc__,
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_name": {"type": "string", "description": "Назва репозиторію"},
                    "path": {"type": "string", "description": "Шлях до папки"}
                },
                "required": ["repo_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_github_repositories",
            "description": list_github_repositories.__doc__,
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_or_update_file",
            "description": create_or_update_file.__doc__,
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_name": {"type": "string", "description": "Назва репозиторію"},
                    "path": {"type": "string", "description": "Шлях/ім'я файлу (наприклад, index.html)"},
                    "content": {"type": "string", "description": "Повний новий HTML/JS/CSS код"}
                },
                "required": ["repo_name", "path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_file_content",
            "description": get_file_content.__doc__,
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

def safe_call(func, args):
    sig = inspect.signature(func)
    filtered_args = {k: v for k, v in args.items() if k in sig.parameters}
    return func(**filtered_args)

SYSTEM_PROMPT = (
    "Ти — Dev Assistant. Твоє завдання — розробляти веб-сторінки та працювати з GitHub.\n"
    "Якщо користувач просить переробити сайт на 3D модель (наприклад Three.js), одразу генеруй повний HTML-код "
    "з необхідними скриптами (CDN Three.js, OrbitControls), стилями для мобільних пристроїв та 3D об'єктом. "
    "Викликай create_or_update_file для збереження коду в index.html відповідного репозиторію.\n"
    "Відповідай стисло та зрозуміло українською мовою."
)

@dp.message()
async def handle(message: types.Message):
    if MY_TELEGRAM_ID and message.from_user.id != MY_TELEGRAM_ID:
        return
    
    user_id = message.from_user.id
    history = user_history[user_id]
    
    history.append({"role": "user", "content": message.text})
    if len(history) > MAX_HISTORY:
        history = history[-MAX_HISTORY:]
        user_history[user_id] = history

    messages_payload = [{"role": "system", "content": SYSTEM_PROMPT}] + history

    msg = await message.answer("🧠 Працюю над завданням...")
    try:
        response = groq_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=messages_payload,
            tools=TOOLS_SCHEMA,
            max_tokens=4096
        )
        
        choice = response.choices[0].message
        tool_calls = choice.tool_calls

        if tool_calls:
            messages_payload.append(choice)
            
            for tc in tool_calls:
                fn_name = tc.function.name
                if fn_name in tools_map:
                    fn = tools_map[fn_name]
                    try:
                        args = json.loads(tc.function.arguments) if tc.function.arguments else {}
                    except Exception:
                        args = {}
                    
                    res = safe_call(fn, args)
                    
                    messages_payload.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": str(res)
                    })

            second_response = groq_client.chat.completions.create(
                model=GROQ_MODEL,
                messages=messages_payload,
                max_tokens=1000
            )
            
            final_text = second_response.choices[0].message.content or "Зміни успішно внесено до GitHub!"
            history.append({"role": "assistant", "content": final_text})
            await msg.edit_text(final_text)

        else:
            final_text = choice.content
            if not final_text:
                final_text = "Не вдалося згенерувати відповідь. Спробуй повторити запит ще раз."
            history.append({"role": "assistant", "content": final_text})
            await msg.edit_text(final_text)

    except Exception as e:
        await msg.edit_text(f"❌ Помилка: {e}")

async def main():
    print("🤖 Бот запущен з підтримкою Qwen та двокроковим інструментарієм...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
