import os
import asyncio
import re
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

async def run_agentic_loop(test_prompt, max_iterations = 5):
    system_prompt = """
    Ты ...
    Твоя задача: 
    Твои основные правила работы:
    """
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
            temperature=0.6,
            max_tokens=2000
        )
        
        assistant_message = response.choices[0].message
        messages.append(assistant_message)
        
        if assistant_message.tool_calls:
            print("LLM запросила вызов инструмента (Action).")
        else:
            #print(f"LLM вернула ответ: {assistant_message.content}")
            print(f"LLM вернула ответ: {clean_output(assistant_message.content)}")
            #print("\nЦикл успешно завершен.")
            #break
            next_action = input("\nВведи следующий запрос (или 'exit' для выхода): ")
            if next_action.lower() in ['exit', 'quit', 'выход']:
                print("Завершение цикла по команде пользователя.")
                break

            messages.append({"role": "user", "content": next_action})
            
    return messages

if __name__ == "__main__":
    test_prompt = "..."
    asyncio.run(run_agentic_loop(test_prompt))