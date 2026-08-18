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
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
gh = Github(GITHUB_TOKEN)
groq_client = Groq(api_key=GROQ_API_KEY)

# Збереження історії повідомлень (пам'ять бота)
user_history = defaultdict(list)
MAX_HISTORY = 10

# --- ФУНКЦІЇ GITHUB ---

def list_repo_files(repo_name: str, path: str = "") -> str:
    """Виводит список файлів у вказаному репозиторії GitHub."""
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
        return content
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
            "description": list_repo_files.__doc__,
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_name": {"type": "string", "description": "Назва репозиторію"},
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
    "Ти — досвідчений і рішучий Dev Assistant. Твоє завдання — допомагати розробнику з GitHub.\n"
    "1. Завжди аналізуй контекст попередніх повідомлень. Якщо користувач питає 'про що код в цьому файлі', викликай get_file_content, а потім поясни його зміст.\n"
    "2. Якщо просять щось змінити або замінити сайт на 3D модель — не став 10 питань, одразу генеруй код і викликай create_or_update_file.\n"
    "3. Будь стислим, конкретним і відповідай зрозумілою українською мовою."
)

@dp.message()
async def handle(message: types.Message):
    if MY_TELEGRAM_ID and message.from_user.id != MY_TELEGRAM_ID:
        return
    
    user_id = message.from_user.id
    history = user_history[user_id]
    
    # Додаємо нове повідомлення в історію
    history.append({"role": "user", "content": message.text})
    if len(history) > MAX_HISTORY:
        history = history[-MAX_HISTORY:]
        user_history[user_id] = history

    messages_payload = [{"role": "system", "content": SYSTEM_PROMPT}] + history

    msg = await message.answer("🧠 Думаю...")
    try:
        response = groq_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=messages_payload,
            tools=TOOLS_SCHEMA
        )
        
        choice = response.choices[0].message
        tool_calls = choice.tool_calls

        if tool_calls:
            # Модель попросила викликати інструмент
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
                    
                    # Додаємо результат функції в контекст
                    messages_payload.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": str(res)
                    })

            # Повторний запит до Groq, щоб модель дала фінальну відповідь на основі отриманих даних
            second_response = groq_client.chat.completions.create(
                model=GROQ_MODEL,
                messages=messages_payload
            )
            
            final_text = second_response.choices[0].message.content
            history.append({"role": "assistant", "content": final_text})
            await msg.edit_text(final_text)

        else:
            final_text = choice.content or "Отримано порожню відповідь."
            history.append({"role": "assistant", "content": final_text})
            await msg.edit_text(final_text)

    except Exception as e:
        await msg.edit_text(f"❌ Помилка: {e}")

async def main():
    print("🤖 Бот запущений з пам'яттю диалогу...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
