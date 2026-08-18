import os
import json
import socket
import asyncio
import inspect
from collections import defaultdict
import aiohttp
from aiogram import Bot, Dispatcher, types
from aiogram.client.session.aiohttp import AiohttpSession
from github import Auth, Github
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
MY_TELEGRAM_ID = int(os.getenv("MY_TELEGRAM_ID", 0))
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")

dp = Dispatcher()

# Авторизація PyGithub
auth = Auth.Token(GITHUB_TOKEN)
gh = Github(auth=auth)

groq_client = Groq(api_key=GROQ_API_KEY)

user_history = defaultdict(list)
MAX_HISTORY = 4

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
        return f"❌ Помилка: {e}"

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
        return f"❌ Помилка запису: {e}"

def get_file_content(repo_name: str, path: str) -> str:
    """Отримує текстовий вміст файлу з репозиторію."""
    try:
        repo_name = repo_name.strip("/").split("/")[-1]
        user = gh.get_user()
        repo = user.get_repo(repo_name)
        content = repo.get_contents(path).decoded_content.decode('utf-8')
        if len(content) > 2500:
            content = content[:2500] + "\n...[обрізано]..."
        return content
    except Exception as e:
        return f"❌ Помилка читання: {e}"

tools_map = {
    "list_repo_files": list_repo_files,
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
                    "repo_name": {"type": "string"},
                    "path": {"type": "string"}
                },
                "required": ["repo_name"]
            }
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
                    "repo_name": {"type": "string"},
                    "path": {"type": "string"},
                    "content": {"type": "string"}
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
                    "repo_name": {"type": "string"},
                    "path": {"type": "string"}
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
    "Ти Dev Assistant. Якщо користувач дає посилання на репозиторій або просить щось змінити/переробити index.html на 3D модель — "
    "одразу генеруй повний HTML код з Three.js та викликай create_or_update_file(repo_name='test-website-repo', path='index.html', content='...')."
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

    msg = await message.answer("⚡ Генерую 3D код та оновлюю GitHub...")
    try:
        response = groq_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=messages_payload,
            tools=TOOLS_SCHEMA,
            max_tokens=3500
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
                messages=messages_payload
            )
            
            final_text = second_response.choices[0].message.content or "✅ 3D тачка успішно загружена в index.html!"
            history.append({"role": "assistant", "content": final_text})
            await msg.edit_text(final_text)

        else:
            final_text = choice.content or "Виконано."
            history.append({"role": "assistant", "content": final_text})
            await msg.edit_text(final_text)

    except Exception as e:
        await msg.edit_text(f"❌ Помилка: {e}")

async def main():
    # Connector та Bot створюються тільки ВСЕРЕДИНІ async функції
    connector = aiohttp.TCPConnector(family=socket.AF_INET)
    async with AiohttpSession(connector=connector) as session:
        bot = Bot(token=BOT_TOKEN, session=session)
        print("🤖 Запущено на llama-3.1-8b-instant з IPv4 фіксом...")
        await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
