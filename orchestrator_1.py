import os
import re
import asyncio
import json
from datetime import datetime, timedelta
from typing import Optional
from dotenv import load_dotenv
from openai import AsyncOpenAI
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

load_dotenv()


class Config:
    """Конфигурация приложения."""
    MODEL_ID: str = "qwen/qwen3-32b"
    BASE_URL: str = "https://openrouter.ai/api/v1"
    API_KEY: Optional[str] = os.getenv("OPENROUTER_API_KEY")


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
3. Аномалии: выдели зависшие задачи (без движения в нужном статусе дольше 3 дней). Если таких задач нет, скажи "Аномалий нет".
ВАЖНО: В JQL-запросах всегда заключай названия статусов, содержащие пробелы, в кавычки. Например: status = "In Progress"
Не придумывай данные, опирайся только на ответ таск-трекера."""

    @staticmethod
    def get_epic_status_prompt() -> str:
        return f"""Ты ИИ-аналитик кросс-функциональной команды. Работаешь в цикле ReAct.
Твоя задача — сформировать отчет по крупным задачам (Стратегический статус).
Тебе нужно самостоятельно достать целевые приоритеты (Эпики) из базы знаний Obsidian, используя доступный тебе инструмент, и затем проанализировать их прогресс в Jira.

Используй инструменты (Obsidian и Jira) для получения вводных данных и фильтрации потока задач.
ВАЖНО: В JQL-запросах всегда заключай названия статусов, содержащие пробелы, в кавычки. Например: status = "In Progress"
Твой финальный ответ должен быть в формате Markdown и подсвечивать прогресс ИСКЛЮЧИТЕЛЬНО по целевым приоритетам, указанным выше. Игнорируй задачи, не относящиеся к этим приоритетам."""

    @staticmethod
    def get_sprint_retro_prompt() -> str:
        return f"""Ты ИИ-аналитик кросс-функциональной команды. Работаешь в цикле ReAct.
Твоя задача — подвести итоги цикла разработки (Ретроспектива).
Цели текущего цикла нужно самостоятельно достать из базы знаний Obsidian с помощью доступного инструмента.

Используй инструменты для получения целей (Obsidian) и агрегации всех завершенных и незавершенных задач за итерацию (Jira).
Твой финальный ответ должен быть в формате Markdown и строго включать:
1. Сравнение фактического результата с заявленными целями.
2. Выявление внеплановых задач (задачи, добавленные после старта цикла).
3. Формирование списка задач-кандидатов на перенос в следующий цикл.
ВАЖНО: В JQL-запросах всегда заключай названия статусов, содержащие пробелы, в кавычки. Например: status = "In Progress"
"""

class AIAgent:
    """Класс для работы с LLM и выполнения цикла ReAct с поддержкой MCP."""
    
    def __init__(self, api_key: str, base_url: str, model_id: str):
        self.client = AsyncOpenAI(base_url=base_url, api_key=api_key)
        self.model_id = model_id
        self.server_params = StdioServerParameters(
            command="python",
            args=["jira_mcp.py"], 
            env=os.environ.copy()
        )

    @staticmethod
    def _clean_output(text: Optional[str]) -> str:
        """Очищает текст от тегов рассуждений."""
        if not text:
            return ""
        return re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()

    def _convert_mcp_to_openai_tool(self, mcp_tool) -> dict:
        """Конвертирует схему инструмента MCP в формат OpenAI API."""
        return {
            "type": "function",
            "function": {
                "name": mcp_tool.name,
                "description": mcp_tool.description,
                "parameters": mcp_tool.inputSchema
            }
        }

    async def run_loop(self, system_prompt: str, user_prompt: str, max_iterations: int = 5) -> str:
        """Оркестратор: запускает MCP-сервер и цикл взаимодействия с моделью."""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        print(f"Старт оркестратора. Запрос: '{user_prompt}'\n")
        print("[MCP] Запуск локального сервера Jira...")

        async with stdio_client(self.server_params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                
                mcp_tools_response = await session.list_tools()
                mcp_tools = mcp_tools_response.tools
                openai_tools = [self._convert_mcp_to_openai_tool(t) for t in mcp_tools]
                print(f"[MCP] Инструменты подключены: {', '.join([t.name for t in mcp_tools])}\n")

                for i in range(max_iterations):
                    print(f"--- Итерация {i + 1} ---")
                    
                    response = await self.client.chat.completions.create(
                        model=self.model_id,
                        messages=messages,
                        temperature=0.3,
                        max_tokens=2000,
                        tools=openai_tools,
                        tool_choice="auto",
                        parallel_tool_calls=False
                    )
                    
                    assistant_message = response.choices[0].message
                    messages.append(assistant_message)
                    
                    if hasattr(assistant_message, 'tool_calls') and assistant_message.tool_calls:
                        print("[LLM] Запрошен вызов инструмента (Action).")
                        
                        for tool_call in assistant_message.tool_calls:
                            name = tool_call.function.name
                            arguments = json.loads(tool_call.function.arguments)
                            print(f"📡 [MCP] Выполнение '{name}' с параметрами: {arguments}")
                            
                            try:
                                mcp_result = await session.call_tool(name, arguments)
                                result_text = "".join([content.text for content in mcp_result.content if hasattr(content, 'text')])
                            except Exception as tool_err:
                                result_text = f"Ошибка Jira API: {tool_err}"
                                print(f"❌ [MCP] {result_text}")
                                
                            print(f"📥 [JIRA RESPONSE]: {result_text[:300]}...")

                            messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": result_text
                            })
                                
                    else:
                        final_text = self._clean_output(assistant_message.content)
                        print(f"[LLM] Финальный ответ получен.")
                        return final_text
                        
                print("Достигнут лимит итераций.")
                return "Ошибка: Не удалось завершить задачу за отведенное число шагов."

class AnalyticsApp:
    """Главный класс приложения для взаимодействия с пользователем."""
    
    def __init__(self, agent: AIAgent):
        self.agent = agent
        self.prompts = PromptManager()

    async def _handle_standup(self) -> tuple[str, str]:
        target_date = (datetime.now() - timedelta(days=15)).strftime("%Y-%m-%d")    #указано минус 15 дней, тк нет актуальных задач сейчас
            
        system_prompt = self.prompts.get_standup_prompt()
        user_prompt = f"Собери данные и сформируй отчет за период начиная с {target_date}."
        return system_prompt, user_prompt

    async def _handle_epic(self) -> tuple[str, str]:
        print("[Система] Задача передана агенту: ИИ самостоятельно запросит приоритеты...")
        system_prompt = self.prompts.get_epic_status_prompt()
        user_prompt = "Проанализируй статус по крупным задачам."
        return system_prompt, user_prompt

    async def _handle_retro(self) -> tuple[str, str]:
        print("[Система] Задача передана агенту: ИИ самостоятельно запросит цели цикла...")
        system_prompt = self.prompts.get_sprint_retro_prompt()
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
        print("\n--- Финальный отчет ---\n")
        print(final_report)
        print("\nРабота успешно завершена.")


async def main():
    if not Config.API_KEY:
        print("Ошибка: OPENROUTER_API_KEY не найден в переменных окружения.")
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