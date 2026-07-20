import asyncio
from contextlib import AsyncExitStack
from datetime import datetime, timedelta
import json
import os
import re
from typing import Dict, List, Optional

from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from openai import AsyncOpenAI

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
    return (
        "Ты ИИ-аналитик кросс-функциональной команды. Работаешь в цикле"
        " ReAct.\nТвоя задача — сформировать ежедневную сводку активности"
        " (Ежедневная сводка).\nИспользуй доступные инструменты (Jira) для"
        " поиска задач, которые были обновлены за указанный пользователем"
        " период.\n\nТвой финальный ответ должен быть в формате Markdown и"
        " строго содержать:\n1. Выделенный прогресс по разработчикам (сдвиги"
        ' статусов).\n2. Текущий фокус дня (задачи, находящиеся "В'
        ' работе").\n3. Аномалии: выдели зависшие задачи (без движения в нужном'
        ' статусе дольше 3 дней). Если таких задач нет, скажи "Аномалий'
        " нет\".\nВАЖНО: В JQL-запросах всегда заключай названия статусов,"
        ' содержащие пробелы, в кавычки. Например: status = "In Progress"\nНе'
        " придумывай данные, опирайся только на ответ таск-трекера.\nПосле"
        " формирования отчета сохрани его в файл Obsidian с помощью"
        " инструмента update_note, передав target_heading='☕ Авто-Standup"
        " (AI)'."
    )

  @staticmethod
  def get_epic_status_prompt(epic_context: str) -> str:
    return (
        "Ты ИИ-аналитик кросс-функциональной команды. Работаешь в цикле"
        " ReAct.\nТвоя задача — сформировать отчет по крупным задачам"
        " (Стратегический статус).\nТебе предоставлены целевые приоритеты"
        f" (Эпики) из базы знаний руководителя:\n{epic_context}\n\nИспользуй"
        " инструменты (Jira) для фильтрации потока закрытых и текущих"
        " задач.\nВАЖНО: В JQL-запросах всегда заключай названия статусов,"
        ' содержащие пробелы, в кавычки. Например: status = "In Progress"\nТвой'
        " финальный ответ должен быть в формате Markdown и подсвечивать"
        " прогресс ИСКЛЮЧИТЕЛЬНО по целевым приоритетам, указанным выше."
        " Игнорируй задачи, не относящиеся к этим приоритетам.\nПосле"
        " формирования отчета сохрани его в файл Obsidian с помощью"
        " инструмента update_note, передав target_heading='📊 Стратегический"
        " статус'."
    )

  @staticmethod
  def get_sprint_retro_prompt(sprint_goals: str) -> str:
    return (
        "Ты ИИ-аналитик кросс-функциональной команды. Работаешь в цикле"
        " ReAct.\nТвоя задача — подвести итоги цикла разработки"
        f" (Ретроспектива).\nЦели текущего цикла:\n{sprint_goals}\n\nИспользуй"
        " инструменты (Jira) для агрегации всех завершенных и незавершенных"
        " задач за итерацию.\nТвой финальный ответ должен быть в формате"
        " Markdown и строго включать:\n1. Сравнение фактического результата с"
        " заявленными целями.\n2. Выявление внеплановых задач (задачи,"
        " добавленные после старта цикла).\n3. Формирование списка"
        " задач-кандидатов на перенос в следующий цикл.\nВАЖНО: В JQL-запросах"
        ' всегда заключай названия статусов, содержащие пробелы, в кавычки.'
        ' Например: status = "In Progress"\nПосле формирования отчета сохрани'
        " его в файл Obsidian с помощью инструмента update_note, передав"
        " target_heading='🎯 Ретроспектива'."
    )


class AIAgent:
  """Класс для работы с LLM и выполнения цикла ReAct с несколькими MCP."""

  def __init__(self, api_key: str, base_url: str, model_id: str):
    self.client = AsyncOpenAI(base_url=base_url, api_key=api_key)
    self.model_id = model_id
    env = os.environ.copy()

    self.jira_params = StdioServerParameters(
        command="python", args=["jira_mcp.py"], env=env
    )
    self.obsidian_params = StdioServerParameters(
        command="python", args=["obsidian_mcp.py"], env=env
    )

  @staticmethod
  def _clean_output(text: Optional[str]) -> str:
    if not text:
      return ""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

  def _convert_mcp_to_openai_tool(self, mcp_tool) -> dict:
    return {
        "type": "function",
        "function": {
            "name": mcp_tool.name,
            "description": mcp_tool.description,
            "parameters": mcp_tool.inputSchema,
        },
    }

  async def run_loop(
      self, system_prompt: str, user_prompt: str, max_iterations: int = 7
  ) -> str:
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    print(f"Старт оркестратора. Запрос: '{user_prompt}'\n")
    print("[MCP] Подключение серверов Jira и Obsidian...")

    async with AsyncExitStack() as stack:
      # Инициализируем Jira MCP
      jira_transport = await stack.enter_async_context(
          stdio_client(self.jira_params)
      )
      jira_session = await stack.enter_async_context(
          ClientSession(jira_transport[0], jira_transport[1])
      )
      await jira_session.initialize()

      # Инициализируем Obsidian MCP
      obsidian_transport = await stack.enter_async_context(
          stdio_client(self.obsidian_params)
      )
      obsidian_session = await stack.enter_async_context(
          ClientSession(obsidian_transport[0], obsidian_transport[1])
      )
      await obsidian_session.initialize()

      # Регистрируем все инструменты обоих серверов
      tool_map = {}
      openai_tools = []

      jira_tools_resp = await jira_session.list_tools()
      for tool in jira_tools_resp.tools:
        tool_map[tool.name] = jira_session
        openai_tools.append(self._convert_mcp_to_openai_tool(tool))

      obsidian_tools_resp = await obsidian_session.list_tools()
      for tool in obsidian_tools_resp.tools:
        tool_map[tool.name] = obsidian_session
        openai_tools.append(self._convert_mcp_to_openai_tool(tool))

      print(
          f"[MCP] Инструменты подключены: {', '.join(tool_map.keys())}\n"
      )

      for i in range(max_iterations):
        print(f"--- Итерация {i + 1} ---")

        response = await self.client.chat.completions.create(
            model=self.model_id,
            messages=messages,
            temperature=0.3,
            max_tokens=2000,
            tools=openai_tools,
            tool_choice="auto",
            parallel_tool_calls=False,
        )

        assistant_message = response.choices[0].message
        messages.append(assistant_message)

        if (
            hasattr(assistant_message, "tool_calls")
            and assistant_message.tool_calls
        ):
          print("[LLM] Запрошен вызов инструмента (Action).")

          for tool_call in assistant_message.tool_calls:
            name = tool_call.function.name
            arguments = json.loads(tool_call.function.arguments)
            print(
                f"📡 [MCP] Выполнение '{name}' с параметрами: {arguments}"
            )

            target_session = tool_map.get(name)
            if not target_session:
              result_text = f"Ошибка: Инструмент '{name}' не найден."
            else:
              try:
                mcp_result = await target_session.call_tool(name, arguments)
                result_text = "".join([
                    content.text
                    for content in mcp_result.content
                    if hasattr(content, "text")
                ])
              except Exception as tool_err:
                result_text = f"Ошибка выполнения инструмента MCP: {tool_err}"
                print(f"❌ [MCP] {result_text}")

            print(f"📥 [RESPONSE]: {result_text[:300]}...")

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result_text,
            })
        else:
          final_text = self._clean_output(assistant_message.content)
          print("[LLM] Финальный ответ получен.")
          return final_text

      print("Достигнут лимит итераций.")
      return (
          "Ошибка: Не удалось завершить задачу за отведенное число шагов."
      )


class AnalyticsApp:
  """Главный класс консольного приложения."""

  def __init__(self, agent: AIAgent):
    self.agent = agent
    self.prompts = PromptManager()

  async def _handle_standup(self) -> tuple[str, str]:
    target_date = (datetime.now() - timedelta(days=15)).strftime("%Y-%m-%d")
    system_prompt = self.prompts.get_standup_prompt()
    user_prompt = (
        f"Собери данные из Jira за период с {target_date} и сохрани отчет в"
        " Obsidian через update_note под заголовком '☕ Авто-Standup (AI)'."
    )
    return system_prompt, user_prompt

  async def _handle_epic(self) -> tuple[str, str]:
    system_prompt = self.prompts.get_epic_status_prompt(
        "Целевые эпики: Оптимизация базы данных, Интеграция платежной системы"
    )
    user_prompt = (
        "Проанализируй текущий прогресс по эпикам в Jira и сохрани результат в"
        " Obsidian через update_note под заголовком '📊 Стратегический"
        " статус'."
    )
    return system_prompt, user_prompt

  async def _handle_retro(self) -> tuple[str, str]:
    system_prompt = self.prompts.get_sprint_retro_prompt(
        "Цели спринта: Выпуск релиза v1.2, Покрытие тестами модуля авторизации"
    )
    user_prompt = (
        "Подведи итоги спринта в Jira и сохрани отчет в Obsidian через"
        " update_note под заголовком '🎯 Ретроспектива'."
    )
    return system_prompt, user_prompt

  async def run(self):
    print("Система аналитики задач рада вас приветствовать.")
    print("Выберите режим работы:")
    print("1. Ежедневная сводка (Авто-Standup)")
    print("2. Статус по стратегическим целям (Эпики)")
    print("3. Итоги спринта (Ретроспектива)")

    choice = input("\nВаш выбор (1-3): ").strip()

    if choice == "1":
      system_prompt, user_prompt = await self._handle_standup()
    elif choice == "2":
      system_prompt, user_prompt = await self._handle_epic()
    elif choice == "3":
      system_prompt, user_prompt = await self._handle_retro()
    else:
      print("Ошибка: Неверный выбор режима.")
      return

    print("\n[Система] Оркестратор запущен...")
    final_report = await self.agent.run_loop(system_prompt, user_prompt)
    print("\n--- Финальный ответ ---\n")
    print(final_report)


async def main():
  if not Config.API_KEY:
    print("Ошибка: Переменная OPENROUTER_API_KEY не найдена.")
    return

  agent = AIAgent(
      api_key=Config.API_KEY,
      base_url=Config.BASE_URL,
      model_id=Config.MODEL_ID,
  )
  app = AnalyticsApp(agent)
  await app.run()


if __name__ == "__main__":
  asyncio.run(main())