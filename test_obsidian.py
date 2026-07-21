import asyncio
from obsidian_mcp import update_note

async def run_test():
    test_filename = "2026-07-21.md"
    new_text = "**Прогресс из Jira:**\n- [EPIC-1] В работе (5/11 задач)\n- [EPIC-2] Тестирование"
    
    print("Запуск инжектора...")
    result = update_note(new_content=new_text, target_heading="📊 Стратегический статус", filename=test_filename)
    print(result)

if __name__ == "__main__":
    asyncio.run(run_test())