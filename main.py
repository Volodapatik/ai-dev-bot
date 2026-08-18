import os
import asyncio
import requests
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
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

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

def list_github_repositories(limit: int = 50) -> str:
    """Повертає загальну кількість та список репозиторіїв користувача."""
    try:
        user = gh.get_user()
        repos = list(user.get_repos())
        total_count = len(repos)
        
        if total_count == 0:
            return "У вас немає репозиторіїв."

        repo_names = [f"- {r.name} ({r.html_url})" for r in repos[:limit]]
        result = f"Загальна кількість репозиторіїв: {total_count}\n\nОсь список (перші {len(repo_names)}):\n" + "\n".join(repo_names)
        
        if total_count > limit:
            result += f"\n\n...і ще {total_count - limit} репозиторіїв."

        return result
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

def enable_github_pages(repo_name: str, branch: str = "main", path: str = "/") -> str:
    """Вмикає GitHub Pages для репозиторію через GitHub REST API."""
    try:
        user = gh.get_user()
        username = user.login
        
        url = f"https://api.github.com/repos/{username}/{repo_name}/pages"
        headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }
        data = {
            "source": {
                "branch": branch,
                "path": path
            }
        }
        
        response = requests.post(url, headers=headers, json=data)
        
        if response.status_code in [201, 202]:
            return f"🚀 GitHub Pages успішно увімкнено для '{repo_name}'!\nСайт буде доступний за адресою: https://{username}.github.io/{repo_name}/"
        elif response.status_code == 409:
            return f"ℹ️ GitHub Pages вже увімкнено для '{repo_name}'.\nАдреса сайту: https://{username}.github.io/{repo_name}/"
        else:
            return f"❌ Помилка GitHub API ({response.status_code}): {response.json().get('message', response.text)}"
    except Exception as e:
        return f"Помилка увімкнення GitHub Pages: {e}"

def create_or_update_file(repo_name: str, path: str, content: str, commit_message: str = "Update file via AI Assistant") -> str:
    """Створює або оновлює/замінює файл у репозиторії."""
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
    """Прочитати вміст існуючого файлу з репозиторію GitHub."""
    try:
        user = gh.get_user()
        repo = user.get_repo(repo_name)
        file_content = repo.get_contents(path)
        return file_content.decoded_content.decode('utf-8')
    except Exception as e:
        return f"Помилка читання файлу: {e}"

tools_list = [
    create_github_repository, 
    list_github_repositories, 
    delete_github_repository, 
    enable_github_pages,
    create_or_update_file,
    get_file_content
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
    await message.answer("🤖 **AI Dev Assistant готовий!**")

async def process_user_request(message: types.Message, user_text: str):
    msg = await message.answer("🧠 Виконую завдання...")
    
    try:
        response = ai_client.models.generate_content(
            model=GEMINI_MODEL,
            contents=user_text,
            config=genai_types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                tools=tools_list
            )
        )
        
        if response.function_calls:
            results = []
            for call in response.function_calls:
                func_name = call.name
                args = call.args
                
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

        await msg.edit_text(response.text)
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
    print("Бот запущений...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
