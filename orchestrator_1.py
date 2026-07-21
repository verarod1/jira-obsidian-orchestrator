import os
import re
import asyncio
import json
from datetime import datetime, timedelta
from typing import Optional
from dotenv import load_dotenv
import openai
import httpx
from openai import AsyncOpenAI
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from contextlib import AsyncExitStack

load_dotenv()


class Config:
    """Конфигурация приложения."""
    MODEL_ID: str = "qwen/qwen3-next-80b-a3b-thinking"
    BASE_URL: str = "https://openrouter.ai/api/v1"
    API_KEY: Optional[str] = os.getenv("OPENROUTER_API_KEY")


class PromptManager:
    """Класс для генерации системных промптов."""
    
    @staticmethod
    def get_standup_prompt() -> str:
        return """Ты ИИ-аналитик кросс-функциональной команды. Работаешь в цикле ReAct.
Твоя задача — сформировать ежедневную сводку активности. Используй доступные инструменты для поиска задач (Jira) и записи отчета в файл (Obsidian).

Сформируй отчет в формате Markdown, который строго содержит:
1. Выделенный прогресс по разработчикам (сдвиги статусов).
2. Текущий фокус дня (задачи, находящиеся "В работе").
3. Аномалии: проанализируй комментарии к задачам. Выдели как аномалии те тикеты, где в комментариях упоминаются проблемы, блокировки, баги, задержки или просьбы о помощи, а также затянувшееся ожидание на чьей-либо стороне. Если таких комментариев нет, скажи "Аномалий нет".

ДЛЯ ФОРМАТИРОВАНИЯ: Для структуры отчета используй ТОЛЬКО списки, жирный текст и заголовки уровня H3 (###) или ниже. 
Тебе КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО использовать заголовки H1 (#) и H2 (##)
ВАЖНО: В JQL-запросах всегда заключай названия статусов, содержащие пробелы, в кавычки.
Не придумывай данные, опирайся только на ответ таск-трекера.

ФИНАЛЬНЫЙ ШАГ (КРИТИЧЕСКИ ВАЖНО): Ты не имеешь права завершать работу, пока не сохранишь отчет в Obsidian!
После формирования текста ты ОБЯЗАН вызвать инструмент update_note. 
Тебе СТРОГО ЗАПРЕЩЕНО выдавать отчет как финальный текстовый ответ пользователю. Передай весь сгенерированный текст в параметр new_content инструмента update_note (target_heading="Авто-Standup (AI)").
Никогда не передавай параметр filename"""

    @staticmethod
    def get_epic_status_prompt(epic_filename: str) -> str:
        return f"""Ты ИИ-аналитик кросс-функциональной команды. Работаешь в цикле ReAct.
Твоя задача — сформировать отчет по крупным задачам (Стратегический статус).
Тебе нужно самостоятельно достать целевые приоритеты (Эпики) из базы знаний Obsidian. Для этого вызови инструмент read_markdown_file и СТРОГО передай параметр filename="{epic_filename}". 
Затем отфильтруй Jira-поток и подсвети прогресс только по найденным целевым эпикам.

Сформируй отчет в формате Markdown, который строго содержит для КАЖДОГО целевого эпика:
1. Заголовок эпика (например: `### 📌 **OT-XXX** Заголовок эпика`).
2. Список задач эпика в формате: `- **ОТ-XXX** | Статус: **[Статус]** | Комментарии: [Текст]`. Если комментариев нет, не пиши это поле.
3. Блок `**Прогресс**:` со списком процентов завершения по статусам.

ДЛЯ ФОРМАТИРОВАНИЯ: Для структуры отчета используй ТОЛЬКО списки, жирный текст и заголовки уровня H3 (###) или ниже. 
Тебе КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО использовать заголовки H1 (#) и H2 (##).
ВАЖНО ПО JQL:
- В JQL-запросах всегда заключай названия статусов, содержащие пробелы, в кавычки.
- Для поиска задач внутри эпика тебе КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО использовать устаревшее поле "Epic Link". Всегда используй оператор parent
Не придумывай данные, опирайся только на ответ таск-трекера. Игнорируй задачи, не относящиеся к целевым эпикам.

ФИНАЛЬНЫЙ ШАГ (КРИТИЧЕСКИ ВАЖНО): Ты не имеешь права завершать работу, пока не сохранишь отчет в Obsidian!
После формирования текста ты ОБЯЗАН вызвать инструмент update_note. 
Тебе СТРОГО ЗАПРЕЩЕНО выдавать отчет как финальный текстовый ответ пользователю. Передай весь сгенерированный текст в параметр new_content инструмента update_note (target_heading="Стратегический статус").
Никогда не передавай параметр filename"""

    @staticmethod
    @staticmethod
    def get_sprint_retro_prompt(sprint_filename: str) -> str:
        return f"""Ты ИИ-аналитик кросс-функциональной команды. Работаешь в цикле ReAct.
Твоя задача — подвести итоги цикла разработки (Ретроспектива).
Тебе нужно самостоятельно достать цели текущего цикла из базы знаний Obsidian. Для этого вызови инструмент read_markdown_file и СТРОГО передай параметр filename="{sprint_filename}".
Затем используй инструменты для агрегации всех завершенных и незавершенных задач за итерацию (Jira). 
КРИТИЧЕСКИ ВАЖНО: Ты не имеешь права завершать работу, пока не сохранишь отчет в Obsidian! Тебе СТРОГО ЗАПРЕЩЕНО выдавать отчет как финальный текстовый ответ пользователю. Передай весь сгенерированный текст в параметр new_content инструмента update_note (target_heading="Ретроспектива").
Никогда не передавай параметр filename

Сформируй отчет в формате Markdown, который строго содержит:
1. Сравнение фактического результата с заявленными целями.
2. Выявление внеплановых задач (в названии или комментариях которой явно указано, что она внеплановая). Если таких задач нет — напиши "Внеплановых задач не обнаружено".
3. Формирование списка незавершенных задач-кандидатов на перенос в следующий цикл (если есть задержка). Для каждой задачи кратко укажи причину переноса
ДЛЯ ФОРМАТИРОВАНИЯ: Для структуры отчета используй ТОЛЬКО списки, жирный текст и заголовки уровня H3 (###) или ниже. 
Тебе КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО использовать заголовки H1 (#) и H2 (##), а также писать или дублировать главный заголовок отчета.

ВАЖНО ПО JQL:
- В JQL-запросах всегда заключай названия статусов, содержащие пробелы, в кавычки.
- Чтобы найти нужные задачи, используй гибридный подход:
  1. Если в файле целей есть ключи задач/эпиков, используй их: "issueKey IN () OR parent IN ()".
  2. Если ключей нет, а есть только текст (например, "Оптимизация запросов"), выдели ключевые слова и используй текстовый поиск: summary ~ "Оптимизация" OR text ~ "Оптимизация".
Не придумывай данные, опирайся только на ответ таск-трекера.

После формирования текста ты ОБЯЗАН вызвать инструмент update_note. """

class AIAgent:
    """Класс для работы с LLM и выполнения цикла ReAct с поддержкой MCP."""
    
    def __init__(self, api_key: str, base_url: str, model_id: str):
        self.client = AsyncOpenAI(base_url=base_url, api_key=api_key)
        self.model_id = model_id
        
        self.servers_config = {
            "jira": StdioServerParameters(
                command="python",
                args=["jira_mcp.py"], 
                env=os.environ.copy()
            ),
            "obsidian": StdioServerParameters(
                command="python",
                args=["obsidian_mcp.py"],
                env=os.environ.copy()
            )
        }

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

    async def run_loop(self, system_prompt: str, user_prompt: str, max_iterations: int = 10) -> str:
        """Оркестратор: запускает MCP-серверы и цикл взаимодействия с моделью."""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        print(f"Старт оркестратора. Запрос: '{user_prompt}'\n")
        print("[MCP] Запуск локальных серверов...")

        async with AsyncExitStack() as stack:
            tool_to_session = {} 
            openai_tools = []
            mcp_tools_names = []

            for server_name, server_params in self.servers_config.items():
                try:
                    read_stream, write_stream = await stack.enter_async_context(stdio_client(server_params))
                    session = await stack.enter_async_context(ClientSession(read_stream, write_stream))
                    await session.initialize()
                    
                    mcp_tools_response = await session.list_tools()
                    for tool in mcp_tools_response.tools:
                        tool_to_session[tool.name] = session 
                        mcp_tools_names.append(tool.name)
                        openai_tools.append(self._convert_mcp_to_openai_tool(tool))
                        
                    print(f"[MCP] Сервер '{server_name}' успешно подключен.")
                except Exception as e:
                    print(f"❌ [MCP] Ошибка инициализации сервера {server_name}: {e}")
                    return f"Ошибка запуска среды: {e}"

            print(f"\n[MCP] Доступные инструменты: {', '.join(mcp_tools_names)}\n")

            for i in range(max_iterations):
                print(f"--- Итерация {i + 1} ---")
                
                try:
                    response = await self.client.chat.completions.create(
                        model=self.model_id,
                        messages=messages,
                        temperature=0.3,
                        max_tokens=2000,
                        tools=openai_tools,
                        tool_choice="auto",
                        parallel_tool_calls=False
                    )
                except (openai.APIConnectionError, httpx.ConnectError) as e:
                    print(f"\n⚠️ Ошибка сети при обращении к LLM API: {e}")
                    print("Проверьте VPN / DNS подключение и повторите попытку.")
                    return "Запуск прерван из-за отсутствия сетевого соединения."
                
                assistant_message = response.choices[0].message
                messages.append(assistant_message)
                
                if hasattr(assistant_message, 'tool_calls') and assistant_message.tool_calls:
                    print("[LLM] Запрошен вызов инструмента (Action).")
                    
                    for tool_call in assistant_message.tool_calls:
                        name = tool_call.function.name
                        arguments = json.loads(tool_call.function.arguments)
                        print(f"📡 [MCP] Выполнение '{name}' с параметрами: {arguments}")
                        
                        try:
                            target_session = tool_to_session.get(name)
                            if not target_session:
                                raise ValueError(f"Инструмент '{name}' не найден.")
                                
                            mcp_result = await target_session.call_tool(name, arguments)
                            result_text = "".join([content.text for content in mcp_result.content if hasattr(content, 'text')])
                        except Exception as tool_err:
                            result_text = f"Ошибка выполнения {name}: {tool_err}"
                            print(f"❌ [MCP] {result_text}")
                            
                        print(f"📥 [RESPONSE]: {result_text[:300]}...")

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
        target_date = (datetime.now()-timedelta(days=1)).strftime("%Y-%m-%d")    
            
        system_prompt = self.prompts.get_standup_prompt()
        user_prompt = f"Собери данные и сформируй отчет за период начиная с {target_date}."
        return system_prompt, user_prompt

    async def _handle_epic(self) -> tuple[str, str]:
        print("[Система] Задача передана агенту: ИИ самостоятельно запросит приоритеты...")
        system_prompt = self.prompts.get_epic_status_prompt(epic_filename="priorities.md")
        user_prompt = "Проанализируй статус по крупным задачам."
        return system_prompt, user_prompt

    async def _handle_retro(self) -> tuple[str, str]:
        print("[Система] Задача передана агенту: ИИ самостоятельно запросит цели цикла...")
        system_prompt = self.prompts.get_sprint_retro_prompt(sprint_filename="goals.md")
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