import asyncio
from config import Config
from agent import AIAgent
from app import AnalyticsApp

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