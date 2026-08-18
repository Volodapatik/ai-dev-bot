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
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
MY_TELEGRAM_ID = int(os.getenv("MY_TELEGRAM_ID", 0))
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

dp = Dispatcher()

# Авторизація PyGithub
auth = Auth.Token(GITHUB_TOKEN)
gh = Github(auth=auth)

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
        except Exception:
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

GEMINI_TOOLS = [
    {
        "function_declarations": [
            {
                "name": "list_repo_files",
                "description": list_repo_files.__doc__,
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "repo_name": {"type": "STRING"},
                        "path": {"type": "STRING"}
                    },
                    "required": ["repo_name"]
                }
            },
            {
                "name": "create_or_update_file",
                "description": create_or_update_file.__doc__,
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "repo_name": {"type": "STRING"},
                        "path": {"type": "STRING"},
                        "content": {"type": "STRING"}
                    },
                    "required": ["repo_name", "path", "content"]
                }
            },
            {
                "name": "get_file_content",
                "description": get_file_content.__doc__,
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "repo_name": {"type": "STRING"},
                        "path": {"type": "STRING"}
                    },
                    "required": ["repo_name", "path"]
                }
            }
        ]
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

async def call_gemini(contents):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    
    payload = {
        "system_instruction": {
            "parts": [{"text": SYSTEM_PROMPT}]
        },
        "contents": contents,
        "tools": GEMINI_TOOLS
    }

    connector = aiohttp.TCPConnector(family=socket.AF_INET)
    async with aiohttp.ClientSession(connector=connector) as session:
        async with session.post(url, json=payload) as resp:
            data = await resp.json()
            if resp.status != 200:
                raise Exception(f"Gemini API Error {resp.status}: {data}")
            return data

@dp.message()
async def handle(message: types.Message):
    if MY_TELEGRAM_ID and message.from_user.id != MY_TELEGRAM_ID:
        return
    
    user_id = message.from_user.id
    history = user_history[user_id]
    
    history.append({
        "role": "user",
        "parts": [{"text": message.text}]
    })
    
    if len(history) > MAX_HISTORY * 2:
        history = history[-(MAX_HISTORY * 2):]
        user_history[user_id] = history

    msg = await message.answer("⚡ Генерую 3D код та оновлюю GitHub через Gemini...")
    
    try:
        data = await call_gemini(history)
        candidate = data["candidates"][0]["content"]
        parts = candidate.get("parts", [])

        function_call = None
        text_response = ""

        for part in parts:
            if "functionCall" in part:
                function_call = part["functionCall"]
            if "text" in part:
                text_response += part["text"]

        if function_call:
            fn_name = function_call["name"]
            fn_args = function_call.get("args", {})
            
            if fn_name in tools_map:
                fn = tools_map[fn_name]
                res = safe_call(fn, fn_args)
                
                # Додаємо виклик і відповідь інструменту в історію Gemini
                history.append(candidate)
                history.append({
                    "role": "function",
                    "parts": [{
                        "functionResponse": {
                            "name": fn_name,
                            "response": {"output": str(res)}
                        }
                    }]
                })

                second_data = await call_gemini(history)
                second_parts = second_data["candidates"][0]["content"].get("parts", [])
                final_text = "".join([p.get("text", "") for p in second_parts]) or "✅ Операцію успішно виконано!"
                
                history.append({
                    "role": "model",
                    "parts": [{"text": final_text}]
                })
                await msg.edit_text(final_text)
        else:
            final_text = text_response or "Виконано."
            history.append({
                "role": "model",
                "parts": [{"text": final_text}]
            })
            await msg.edit_text(final_text)

    except Exception as e:
        await msg.edit_text(f"❌ Помилка: {e}")

async def main():
    connector = aiohttp.TCPConnector(family=socket.AF_INET)
    session = AiohttpSession(connector_init={"connector": connector})
    bot = Bot(token=BOT_TOKEN, session=session)
    print("🤖 Запущено Telegram-бота з Gemini API та IPv4 фіксом...")
    
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
