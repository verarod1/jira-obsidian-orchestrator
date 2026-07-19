import os
import re
import asyncio
from datetime import datetime, timedelta
from dotenv import load_dotenv
from openai import AsyncOpenAI

load_dotenv()

llm_client = AsyncOpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=os.getenv("GROQ_API_KEY"), 
)

MODEL_ID = "qwen/qwen3-32b"

def clean_output(text):
    if not text:
        return ""
    cleaned_text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    return cleaned_text.strip()

async def run_agentic_loop(system_prompt, test_prompt, max_iterations=5, tools=None):
    tools = tools or []
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": test_prompt}
    ]

    print(f"Старт оркестратора. Запрос: '{test_prompt}'\n")

    for i in range(max_iterations):
        print(f"--- Итерация {i + 1} ---")
        
        kwargs = {
            "model": MODEL_ID,
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": 2000,
        }
        if tools:
            kwargs["tools"] = tools
            
        response = await llm_client.chat.completions.create(**kwargs)
        
        assistant_message = response.choices[0].message
        messages.append(assistant_message)
        
        if assistant_message.tool_calls:
            print("LLM запросила вызов инструмента (Action).")
            for tool_call in assistant_message.tool_calls:
                tool_response_content = "[Результат выполнения инструмента.]" 
                
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": tool_response_content
                })
        else:
            final_text = clean_output(assistant_message.content)
            print(f"LLM вернула ответ:\n{final_text}")
            return final_text
            
    print("Достигнут лимит итераций.")
    return "Ошибка: Не удалось завершить задачу за отведенное число шагов."

def get_standup_prompt():
    return ""

def get_epic_status_prompt(context):
    return f"{context}"

def get_sprint_retro_prompt(context):
    return f"{context}"

async def main():
    print("Система аналитики задач запущена.")
    print("Выберите режим работы:")
    print("1. Ежедневная сводка (анализ за 24 часа)")
    print("2. Статус по крупным задачам (анализ приоритетов)")
    print("3. Итоги цикла разработки (подготовка к ретроспективе)")
    context=''
    
    choice = input("\nВаш выбор (1-3): ").strip()
    
    if choice == '1':
        date_input = input("Нажмите Enter для анализа за последние 24 часа (или введите дату ГГГГ-ММ-ДД): ").strip()
        if not date_input:
            target_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        else:
            target_date = date_input
        
        system_prompt = get_standup_prompt()
        user_prompt = f"Собери данные и сформируй отчет за период начиная с {target_date}."

    elif choice == '2':
        print("[Система] Чтение файла приоритетов из локальной базы...")
        #context = await read_obsidian_goals("путь/к/приоритетам.md")
        system_prompt = get_epic_status_prompt(context)
        user_prompt = "Проанализируй статус по переданным крупным задачам."

    elif choice == '3':
        print("[Система] Чтение целей цикла из локальной базы...")
        #context = await read_obsidian_goals("путь/к/целям.md")
        system_prompt = get_sprint_retro_prompt(context)
        user_prompt = "Агрегируй данные и сформируй отчет для ретроспективы."

    else:
        print("Ошибка: Неверный выбор режима.")
        return

    print("\n[Система] Запуск ИИ-оркестратора. Ожидайте...")
    final_report = await run_agentic_loop(system_prompt, user_prompt)
    print("\nРабота успешно завершена.")

if __name__ == "__main__":
    asyncio.run(main())