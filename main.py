import os
import json
import asyncio
import requests
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
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

gh = Github(GITHUB_TOKEN)
groq_client = Groq(api_key=GROQ_API_KEY)

# --- ФУНКЦІЇ ДЛЯ GITHUB (TOOLS) ---

def create_github_repository(name: str, private: bool = False) -> str:
    try:
        user = gh.get_user()
        repo = user.create_repo(name, private=private)
        return f"Успішно створено репозиторій: {repo.html_url}"
    except Exception as e:
        return f"Помилка створення репозиторію: {e}"

def list_github_repositories(limit: int = 50) -> str:
    try:
        user = gh.get_user()
        repos = list(user.get_repos())
        total_count = len(repos)
        if total_count == 0:
            return "У вас немає репозиторіїв."
        repo_names = [f"- {r.name} ({r.html_url})" for r in repos[:limit]]
        result = f"Загальна кількість репозиторіїв: {total_count}\n\nОсь список:\n" + "\n".join(repo_names)
        return result
    except Exception as e:
        return f"Помилка отримання списку: {e}"

def delete_github_repository(name: str) -> str:
    try:
        user = gh.get_user()
        repo = user.get_repo(name)
        repo.delete()
        return f"Репозиторій '{name}' успішно видалено."
    except Exception as e:
        return f"Помилка видалення: {e}"

def enable_github_pages(repo_name: str, branch: str = "main", path: str = "/") -> str:
    try:
        user = gh.get_user()
        username = user.login
        url = f"https://api.github.com/repos/{username}/{repo_name}/pages"
        headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }
        data = {"source": {"branch": branch, "path": path}}
        response = requests.post(url, headers=headers, json=data)
        if response.status_code in [201, 202]:
            return f"🚀 GitHub Pages успішно увімкнено для '{repo_name}'!\nСайт доступний за адресою: https://{username}.github.io/{repo_name}/"
        elif response.status_code == 409:
            return f"ℹ️ GitHub Pages вже увімкнено для '{repo_name}'.\nАдреса: https://{username}.github.io/{repo_name}/"
        else:
            return f"❌ Помилка GitHub API ({response.status_code}): {response.json().get('message', response.text)}"
    except Exception as e:
        return f"Помилка увімкнення GitHub Pages: {e}"

def create_or_update_file(repo_name: str, path: str, content: str, commit_message: str = "Update file via AI Assistant") -> str:
    try:
        user = gh.get_user()
        repo = user.get_repo(repo_name)
        try:
            existing_file = repo.get_contents(path)
            repo.update_file(path, commit_message, content, existing_file.sha)
            return f"Файл '{path}' успішно оновлено у репозиторії '{repo_name}'."
        except Exception:
            repo.create_file(path, commit_message, content)
            return f"Файл '{path}' успішно створено у репозиторії '{repo_name}'."
    except Exception as e:
        return f"Помилка запису файлу: {e}"

def get_file_content(repo_name: str, path: str) -> str:
    try:
        user = gh.get_user()
        repo = user.get_repo(repo_name)
        file_content = repo.get_contents(path)
        return file_content.decoded_content.decode('utf-8')
    except Exception as e:
        return f"Помилка читання файлу: {e}"

# --- ОПИС ІНСТРУМЕНТІВ ДЛЯ GROQ ---

tools_schema = [
    {
        "type": "function",
        "function": {
            "name": "create_github_repository",
            "description": "Створює новий репозиторій на GitHub",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Назва репозиторію"},
                    "private": {"type": "boolean", "description": "Чи приватний репозиторій"}
                },
                "required": ["name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_github_repositories",
            "description": "Повертає список усех репозиторіїв користувача",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_github_repository",
            "description": "Видаляє репозиторій за його назвою",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string", "description": "Назва репозиторію"}},
                "required": ["name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "enable_github_pages",
            "description": "Вмикає GitHub Pages для репозиторію",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_name": {"type": "string"},
                    "branch": {"type": "string"},
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
            "description": "Створює або оновлює файл у репозиторії",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_name": {"type": "string"},
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                    "commit_message": {"type": "string"}
                },
                "required": ["repo_name", "path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_file_content",
            "description": "Прочитати вміст файлу з репозиторію",
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

SYSTEM_INSTRUCTION = (
    "Ти — розширений AI Dev Assistant для Володимира Патика. "
    "Ти маєш ПРЯМИЙ доступ до керування його акаунтом GitHub через вбудовані функції (tools). "
    "Коли тебе просять увімкнути Pages — використовуй enable_github_pages."
)

def is_owner(user_id: int) -> bool:
    return user_id == MY_TELEGRAM_ID

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    if not is_owner(message.from_user.id):
        return
    await message.answer("🤖 **AI Dev Assistant (Groq / Llama 3.3) готовий!**")

async def process_user_request(message: types.Message, user_text: str):
    msg = await message.answer("⚡ Обробка запиту через Groq...")

    try:
        messages = [
            {"role": "system", "content": SYSTEM_INSTRUCTION},
            {"role": "user", "content": user_text}
        ]

        response = groq_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=messages,
            tools=tools_schema,
            tool_choice="auto"
        )

        response_message = response.choices[0].message

        if response_message.tool_calls:
            results = []
            for tool_call in response_message.tool_calls:
                func_name = tool_call.function.name
                args = json.loads(tool_call.function.arguments)

                if func_name == "create_github_repository":
                    res = create_github_repository(**args)
                elif func_name == "list_github_repositories":
                    res = list_github_repositories(**args)
                elif func_name == "delete_github_repository":
                    res = delete_github_repository(**args)
                elif func_name == "enable_github_pages":
                    res = enable_github_pages(**args)
                elif func_name == "create_or_update_file":
                    res = create_or_update_file(**args)
                elif func_name == "get_file_content":
                    res = get_file_content(**args)
                else:
                    res = "Невідома функція."

                results.append(res)

            await msg.edit_text("⚙️ **Результат:**\n\n" + "\n\n".join(results), disable_web_page_preview=True)
            return

        await msg.edit_text(response_message.content)
    except Exception as e:
        await msg.edit_text(f"❌ Помилка: {e}")

@dp.message(lambda m: m.document)
async def handle_document(message: types.Message):
    if not is_owner(message.from_user.id):
        return

    file_name = message.document.file_name
    caption = message.caption or "Закинь цей файл у репозиторій"

    file_info = await bot.get_file(message.document.file_id)
    downloaded_file = await bot.download_file(file_info.file_path)
    file_content = downloaded_file.read().decode('utf-8', errors='ignore')

    prompt = (
        f"Користувач надіслав файл '{file_name}'.\n"
        f"Вміст:\n```\n{file_content}\n```\n"
        f"Інструкція: {caption}"
    )

    await process_user_request(message, prompt)

@dp.message()
async def handle_ai_prompt(message: types.Message):
    if not is_owner(message.from_user.id):
        return
    await process_user_request(message, message.text)

async def main():
    print("Бот запущений на Groq...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
