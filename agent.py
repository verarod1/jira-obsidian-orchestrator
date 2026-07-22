import os
import re
import json
from typing import Optional
import openai
import httpx
from openai import AsyncOpenAI
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from contextlib import AsyncExitStack

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