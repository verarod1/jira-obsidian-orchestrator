import os
import re
import asyncio  
from dotenv import load_dotenv  
from openai import AsyncOpenAI  

load_dotenv()

SYSTEM_RULES = """
Ты — автономный ИИ-агент, работающий в пошаговом цикле (Agentic Loop).
Твоя задача — решить проблему пользователя, разбивая её на логические шаги.

Для каждого шага ты должен строго соблюдать следующий формат размышления:
1. МЫСЛЬ: Опиши, что ты сейчас делаешь, какую подзадачу решаешь и что тебе нужно для следующего шага.
2. ФИНАЛ: Если ты полностью решил задачу, напиши финальный ответ пользователю после этого слова.

ВАЖНО: Если задача требует нескольких шагов или рассуждений, не давай финальный ответ сразу. Напиши МЫСЛЬ, 
сделай промежуточный вывод, и на следующей итерации цикла продолжи рассуждение.
"""

client = AsyncOpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=os.getenv("GROQ_API_KEY")
)

MODEL_NAME = "qwen/qwen3-32b"

def clean_think_tags(text):
    if not text:
        return ""
    return re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()

class AgentOrchestrator:
    def __init__(self, model = MODEL_NAME, max_steps = 5):
        self.model = model
        self.max_steps = max_steps
        self.messages = [
            {"role": "system", "content": SYSTEM_RULES}
        ]

    async def run(self, initial_prompt: str):
        print(f"\n Запуск автономного цикла для задачи: '{initial_prompt}'\n")
        self.messages.append({"role": "user", "content": initial_prompt})
        
        for step in range(1, self.max_steps + 1):
            print(f"--- [Шаг {step} из {self.max_steps}] Запрос к модели ---")
            
            try:
                response = await client.chat.completions.create(
                    model=self.model,
                    messages=self.messages,
                    temperature=0.3
                )
            except Exception as e:
                print(f" Ошибка API Groq: {e}")
                break

            assistant_message = response.choices[0].message
            
            if hasattr(assistant_message, 'tool_calls') and assistant_message.tool_calls:
                print(" LLM запросила вызов инструмента (Action).")
                self.messages.append({"role": "user", "content": "Инструменты пока не реализованы. Продолжай без них."})
                continue

            raw_response_text = assistant_message.content
            response_text = clean_think_tags(raw_response_text)
            
            print(f"Ответ модели на шаге {step}:\n{response_text}\n")
            
            self.messages.append({"role": "assistant", "content": response_text})

            if "ФИНАЛ" in response_text or "финальный ответ:" in response_text.lower():
                print(" Агент принял решение, что задача выполнена. Выход из цикла.")
                break
            
            self.messages.append({"role": "user", "content": "Продолжай выполнение задачи, опираясь на свои мысли выше."})
                
        else:
            print("Цикл завершен по лимиту шагов (Max Steps). Финальный ответ не гарантирован.")


async def main():
    if not os.getenv("GROQ_API_KEY"):
        print("Ошибка: Не установлена переменная окружения GROQ_API_KEY!")
        return

    user_input = input("Введите вашу задачу: ").strip()
    if user_input:
        orchestrator = AgentOrchestrator(max_steps=5)
        await orchestrator.run(user_input)
    else:
        print("Запрос не введен. Завершение работы.")

if __name__ == "__main__":
    asyncio.run(main())