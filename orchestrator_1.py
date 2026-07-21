import os
import re
import asyncio
import json
from datetime import datetime, timedelta
from typing import Optional
from dotenv import load_dotenv

import httpx
import openai
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
        return """ТТы ИИ-аналитик кросс-функциональной команды. Работаешь в цикле ReAct.
Твоя задача — сформировать ежедневную сводку активности (Ежедневная сводка).
Используй доступные инструменты (Jira) для поиска задач, которые были обновлены за указанный пользователем период.

Сформируй отчет в формате Markdown, который строго содержит:
1. Выделенный прогресс по разработчикам (сдвиги статусов).
2. Текущий фокус дня (задачи, находящиеся "В работе").
3. Аномалии: проанализируй комментарии к задачам. Выдели как аномалии те тикеты, где в комментариях упоминаются проблемы, блокировки, баги, задержки или просьбы о помощи (например, "блокер", "ошибка", "застрял", "нужна помощь"). Если таких комментариев нет, скажи "Аномалий нет".

ВАЖНО ДЛЯ ФОРМАТИРОВАНИЯ: Для структуры отчета используй ТОЛЬКО списки, жирный текст и заголовки уровня H3 (###) или ниже. 
Тебе КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО использовать заголовки H1 (#) и H2 (##), а также писать или дублировать главный заголовок отчета. Начинай ответ сразу с сути.

ВАЖНО: В JQL-запросах всегда заключай названия статусов, содержащие пробелы, в кавычки. Например: status = "In Progress"
Не придумывай данные, опирайся только на ответ таск-трекера.

ФИНАЛЬНЫЙ ШАГ: После формирования отчета ты ОБЯЗАН сохранить его в Obsidian, используя инструмент update_note.
В вызове инструмента передай текст отчета в new_content и строго укажи target_heading="## ☕️ Авто-Standup (AI)".
Никогда не передавай параметр filename в update_note — этот инструмент знает его."""

    @staticmethod
    def get_epic_status_prompt() -> str:
        today = datetime.now().strftime("%Y-%m-%d")
        return f"""Ты ИИ-аналитик кросс-функциональной команды. Работаешь в цикле ReAct.
Твоя задача — сформировать отчет по крупным задачам (Стратегический статус).

1. Сначала прочитай файл 'TargetEpics.md', используя инструмент read_markdown_file.
2. Найди прогресс указанных в нем эпиков в Jira через инструменты поиска.
3. Сформируй итоговый отчет и запиши его в ежедневную заметку с именем '{today}.md' в секцию "## 📊 Стратегический статус", используя инструмент update_note.

⚠️ СТРОГИЕ ПРАВИЛА ПОДСЧЕТА (Chain of Thought):
Перед тем как писать отчет, для каждого эпика пересчитай все элементы в возвращенном отчете Jira:
1. Посчитай **абсолютно каждую строку** с задачей ([OT-...]), которую вернул инструмент поиска. Это число является точным `Total`. Не округляй его и не пропускай задачи.
2. Посчитай, у скольких из них статус равен "Done". Это `Completed`.
3. Вычисли процент: (Completed / Total) * 100%, округлив до целого числа.
4. В строке прогресса обязательно пиши формулу вида: `- **Прогресс**: X% (выполнено Completed из Total)`. Если Total расходится с длиной массива задач — пересчитай заново.

ВАЖНЫЕ ПРАВИЛА JQL:
1. Для поиска задач внутри Эпика используй конструкцию: "Epic Link" = "КЛЮЧ-ЭПИКА" или parent = "КЛЮЧ-ЭПИКА".
2. Всегда заключай названия статусов или полей с пробелами в кавычки.
"""

    @staticmethod
    def get_sprint_retro_prompt() -> str:
        today = datetime.now().strftime("%Y-%m-%d")
        return f"""Ты ИИ-аналитик кросс-функциональной команды. Работаешь в цикле ReAct.
Твоя задача — подвести итоги цикла разработки (Ретроспектива).

АЛГОРИТМ РАБОТЫ:
1. Сначала прочитай файл '{today}.md', используя инструмент read_markdown_file, найди в секции "## 🎯 Ретроспектива" заявленные цели спринта.
2. Используй Jira-инструменты поиска для получения всех завершенных и незавершенных задач за итерацию.
3. Сформируй итоговый отчет в формате Markdown и обнови секцию "## 🎯 Ретроспектива" в файле '{today}.md', используя инструмент update_note. Сохрани исходные пользовательские заметки под заголовком, обновив только выводы ИИ.

Твой финальный отчет должен строго включать:
1. Сравнение фактического результата с заявленными целями.
2. Выявление внеплановых задач (задачи, добавленные после старта цикла).
3. Формирование списка задач-кандидатов на перенос в следующий цикл (незавершенные задачи).

ВАЖНО: В JQL-запросах всегда заключай названия статусов, содержащих пробелы, в кавычки. Например: status = "In Progress"
"""


class AIAgent:
    """Класс для работы с LLM и выполнения цикла ReAct с поддержкой MCP."""
    
    def __init__(self, api_key: str, base_url: str, model_id: str):
        self.client = AsyncOpenAI(base_url=base_url, api_key=api_key, timeout=30.0)
        self.model_id = model_id
        # Параметры подключения к Jira MCP
        self.jira_server_params = StdioServerParameters(
            command="python",
            args=["jira_mcp.py"], 
            env=os.environ.copy()
        )
        # Параметры подключения к Obsidian MCP
        self.obsidian_server_params = StdioServerParameters(
            command="python",
            args=["obsidian_mcp.py"], 
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

    async def run_loop(self, system_prompt: str, user_prompt: str, max_iterations: int = 10) -> str:
        """Оркестратор: запускает MCP-серверы и цикл взаимодействия с моделью."""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        print(f"Старт оркестратора. Запрос: '{user_prompt}'\n")
        print("[MCP] Запуск локальных серверов Jira и Obsidian...")

        # Запуск параллельных MCP-сессий через контекстные менеджеры
        async with stdio_client(self.jira_server_params) as (read_jira, write_jira), \
                   stdio_client(self.obsidian_server_params) as (read_obsidian, write_obsidian):
            
            async with ClientSession(read_jira, write_jira) as jira_session, \
                       ClientSession(read_obsidian, write_obsidian) as obsidian_session:
                
                await jira_session.initialize()
                await obsidian_session.initialize()
                
                # Получаем списки инструментов из обоих серверов
                jira_tools_resp = await jira_session.list_tools()
                obsidian_tools_resp = await obsidian_session.list_tools()
                
                jira_tools = jira_tools_resp.tools
                obsidian_tools = obsidian_tools_resp.tools
                
                # Запоминаем имена инструментов Obsidian для маршрутизации
                obsidian_tool_names = {t.name for t in obsidian_tools}
                
                all_mcp_tools = jira_tools + obsidian_tools
                openai_tools = [self._convert_mcp_to_openai_tool(t) for t in all_mcp_tools]
                
                print(f"[MCP] Инструменты подключены: {', '.join([t.name for t in all_mcp_tools])}\n")

                for i in range(max_iterations):
                    print(f"--- Итерация {i + 1} ---")
                    
                    # ✅ Безопасный вызов LLM с перехватом сетевых ошибок
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
                                # Динамическая маршрутизация вызова в нужный MCP сервер
                                if name in obsidian_tool_names:
                                    target_session = obsidian_session
                                    server_label = "Obsidian"
                                else:
                                    target_session = jira_session
                                    server_label = "Jira"

                                mcp_result = await target_session.call_tool(name, arguments)
                                result_text = "".join([content.text for content in mcp_result.content if hasattr(content, 'text')])
                            except Exception as tool_err:
                                result_text = f"Ошибка MCP API: {tool_err}"
                                print(f"❌ [MCP] {result_text}")
                                
                            print(f"📥 [{server_label.upper()} RESPONSE]: {result_text[:300]}...")

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
        target_date = (datetime.now()).strftime("%Y-%m-%d")    #указано минус 15 дней, тк нет актуальных задач сейчас
            
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