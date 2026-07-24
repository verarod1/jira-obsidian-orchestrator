from datetime import datetime, timedelta
from agent import AIAgent
from prompts import PromptManager

class AnalyticsApp:
    """Главный класс приложения для взаимодействия с пользователем."""
    
    def __init__(self, agent: AIAgent):
        self.agent = agent
        self.prompts = PromptManager()

    async def _handle_standup(self) -> tuple[str, str]:
        target_date = (datetime.now()).strftime("%Y-%m-%d")    
            
        system_prompt = self.prompts.get_standup_prompt()
        user_prompt = f"Собери данные и сформируй ежедневный отчет за период начиная с {target_date}."
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