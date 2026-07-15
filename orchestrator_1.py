import os
import asyncio
import re
from dotenv import load_dotenv
from openai import AsyncOpenAI
from datetime import datetime, timedelta

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

async def run_agentic_loop(system_prompt, test_prompt, max_iterations = 5):
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": test_prompt}
    ]

    print(f"Старт оркестратора. Запрос: '{test_prompt}'\n")

    for i in range(max_iterations):
        print(f"--- Итерация {i + 1} ---")
        
        response = await llm_client.chat.completions.create(
            model=MODEL_ID,
            messages=messages,
            temperature=0.3,
            max_tokens=2000,
            tools=[]
        )
        
        assistant_message = response.choices[0].message
        messages.append(assistant_message)
        
        if assistant_message.tool_calls:
            print("LLM запросила вызов инструмента (Action).")
            for tool_call in assistant_message.tool_calls:
                tool_response_content = "[Результат выполнения инструмента.]" 
                messages.append([])
        else:
            final_text = clean_output(assistant_message.content)
            print(f"LLM вернула ответ:\n{final_text}")
            return final_text
            
    print("Достигнут лимит итераций.")
    return "Ошибка: Не удалось завершить задачу за отведенное число шагов."


def get_standup_prompt():
    return """Ты ИИ-аналитик кросс-функциональной команды. Работаешь в цикле ReAct.
Твоя задача — сформировать ежедневную сводку активности (Ежедневная сводка).
Используй доступные инструменты (Jira) для поиска задач, которые были обновлены за указанный пользователем период.

Твой финальный ответ должен быть в формате Markdown и строго содержать:
1. Выделенный прогресс по разработчикам (сдвиги статусов).
2. Текущий фокус дня (задачи, находящиеся "В работе").
3. Аномалии: выдели зависшие задачи (без движения в нужном статусе дольше порогового времени).

Не придумывай данные, опирайся только на ответ таск-трекера."""

def get_epic_status_prompt(epic_context):
    return f"""Ты ИИ-аналитик кросс-функциональной команды. Работаешь в цикле ReAct.
Твоя задача — сформировать отчет по крупным задачам (Стратегический статус).
Тебе предоставлены целевые приоритеты (Эпики) из базы знаний руководителя:
{epic_context}

Используй инструменты (Jira) для фильтрации потока закрытых и текущих задач.
Твой финальный ответ должен быть в формате Markdown и подсвечивать прогресс ИСКЛЮЧИТЕЛЬНО по целевым приоритетам, указанным выше. Игнорируй задачи, не относящиеся к этим приоритетам."""

def get_sprint_retro_prompt(sprint_goals):
    return f"""Ты ИИ-аналитик кросс-функциональной команды. Работаешь в цикле ReAct.
Твоя задача — подвести итоги цикла разработки (Ретроспектива).
Цели текущего цикла:
{sprint_goals}

Используй инструменты (Jira) для агрегации всех завершенных и незавершенных задач за итерацию.
Твой финальный ответ должен быть в формате Markdown и строго включать:
1. Сравнение фактического результата с заявленными целями.
2. Выявление внеплановых задач (задачи, добавленные после старта цикла).
3. Формирование списка задач-кандидатов на перенос в следующий цикл."""


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