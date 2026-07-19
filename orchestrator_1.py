import os
import re
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from dotenv import load_dotenv
from openai import AsyncOpenAI

load_dotenv()


class Config:
    """Конфигурация приложения."""
    MODEL_ID: str = "qwen/qwen3-32b"
    BASE_URL: str = "https://api.groq.com/openai/v1"
    API_KEY: Optional[str] = os.getenv("GROQ_API_KEY")


class PromptManager:
    """Класс для генерации системных промптов."""
    
    @staticmethod
    def get_standup_prompt() -> str:
        return """Ты ИИ-аналитик кросс-функциональной команды. Работаешь в цикле ReAct.
Твоя задача — сформировать ежедневную сводку активности (Ежедневная сводка).
Используй доступные инструменты (Jira) для поиска задач, которые были обновлены за указанный пользователем период.

Твой финальный ответ должен быть в формате Markdown и строго содержать:
1. Выделенный прогресс по разработчикам (сдвиги статусов).
2. Текущий фокус дня (задачи, находящиеся "В работе").
3. Аномалии: выдели зависшие задачи (без движения в нужном статусе дольше порогового времени).

Не придумывай данные, опирайся только на ответ таск-трекера."""

    @staticmethod
    def get_epic_status_prompt(epic_context: str) -> str:
        return f"""Ты ИИ-аналитик кросс-функциональной команды. Работаешь в цикле ReAct.
Твоя задача — сформировать отчет по крупным задачам (Стратегический статус).
Тебе предоставлены целевые приоритеты (Эпики) из базы знаний руководителя:
{epic_context}

Используй инструменты (Jira) для фильтрации потока закрытых и текущих задач.
Твой финальный ответ должен быть в формате Markdown и подсвечивать прогресс ИСКЛЮЧИТЕЛЬНО по целевым приоритетам, указанным выше. Игнорируй задачи, не относящиеся к этим приоритетам."""

    @staticmethod
    def get_sprint_retro_prompt(sprint_goals: str) -> str:
        return f"""Ты ИИ-аналитик кросс-функциональной команды. Работаешь в цикле ReAct.
Твоя задача — подвести итоги цикла разработки (Ретроспектива).
Цели текущего цикла:
{sprint_goals}

Используй инструменты (Jira) для агрегации всех завершенных и незавершенных задач за итерацию.
Твой финальный ответ должен быть в формате Markdown и строго включать:
1. Сравнение фактического результата с заявленными целями.
2. Выявление внеплановых задач (задачи, добавленные после старта цикла).
3. Формирование списка задач-кандидатов на перенос в следующий цикл."""


class AIAgent:
    """Класс для работы с LLM и выполнения цикла ReAct."""
    
    def __init__(self, api_key: str, base_url: str, model_id: str):
        self.client = AsyncOpenAI(base_url=base_url, api_key=api_key)
        self.model_id = model_id

    @staticmethod
    def _clean_output(text: Optional[str]) -> str:
        """Очищает текст от тегов рассуждений."""
        if not text:
            return ""
        cleaned_text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
        return cleaned_text.strip()

    async def run_loop(self, system_prompt: str, user_prompt: str, max_iterations: int = 5, tools: Optional[List] = None) -> str:
        """Оркестратор: запускает цикл взаимодействия с моделью."""
        tools = tools or []
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        print(f"Старт оркестратора. Запрос: '{user_prompt}'\n")

        for i in range(max_iterations):
            print(f"--- Итерация {i + 1} ---")
            
            kwargs = {
                "model": self.model_id,
                "messages": messages,
                "temperature": 0.3,
                "max_tokens": 2000,
            }
            if tools:
                kwargs["tools"] = tools
                
            response = await self.client.chat.completions.create(**kwargs)
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
                final_text = self._clean_output(assistant_message.content)
                print(f"LLM вернула ответ:\n{final_text}")
                return final_text
                
        print("Достигнут лимит итераций.")
        return "Ошибка: Не удалось завершить задачу за отведенное число шагов."


class AnalyticsApp:
    """Главный класс приложения для взаимодействия с пользователем."""
    
    def __init__(self, agent: AIAgent):
        self.agent = agent
        self.prompts = PromptManager()

    async def _handle_standup(self) -> tuple[str, str]:
        date_input = input("Нажмите Enter для анализа за последние 24 часа (или введите дату ГГГГ-ММ-ДД): ").strip()
        if not date_input:
            target_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        else:
            target_date = date_input
            
        system_prompt = self.prompts.get_standup_prompt()
        user_prompt = f"Собери данные и сформируй отчет за период начиная с {target_date}."
        return system_prompt, user_prompt

    async def _handle_epic(self) -> tuple[str, str]:
        print("[Система] Чтение файла приоритетов из локальной базы...")
        context = "" # context = await read_obsidian_goals("путь/к/приоритетам.md")
        system_prompt = self.prompts.get_epic_status_prompt(context)
        user_prompt = "Проанализируй статус по переданным крупным задачам."
        return system_prompt, user_prompt

    async def _handle_retro(self) -> tuple[str, str]:
        print("[Система] Чтение целей цикла из локальной базы...")
        context = "" # context = await read_obsidian_goals("путь/к/целям.md")
        system_prompt = self.prompts.get_sprint_retro_prompt(context)
        user_prompt = "Агрегируй данные и сформируй отчет для ретроспективы."
        return system_prompt, user_prompt

    async def run(self):
        """Запуск консольного интерфейса."""
        print("Система аналитики задач запущена.")
        print("Выберите режим работы:")
        print("1. Ежедневная сводка (анализ за 24 часа)")
        print("2. Статус по крупным задачам (анализ приоритетов)")
        print("3. Итоги цикла разработки (подготовка к ретроспективе)")
        
        choice = input("\nВаш выбор (1-3): ").strip()
        
        if choice == '1':
            system_prompt, user_prompt = await self._handle_standup()
        elif choice == '2':
            system_prompt, user_prompt = await self._handle_epic()
        elif choice == '3':
            system_prompt, user_prompt = await self._handle_retro()
        else:
            print("Ошибка: Неверный выбор режима.")
            return

        print("\n[Система] Запуск ИИ-оркестратора. Ожидайте...")
        final_report = await self.agent.run_loop(system_prompt, user_prompt)
        print("\nРабота успешно завершена.")


async def main():
    if not Config.API_KEY:
        print("Ошибка: GROQ_API_KEY не найден в переменных окружения.")
        return

    agent = AIAgent(
        api_key=Config.API_KEY, 
        base_url=Config.BASE_URL, 
        model_id=Config.MODEL_ID
    )
    app = AnalyticsApp(agent)
    
    await app.run()

if __name__ == "__main__":
    asyncio.run(main())