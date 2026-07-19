import os
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