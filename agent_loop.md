```mermaid
flowchart TD
    Start([Запуск системы]) --> Input[/Выбор режима 1, 2 или 3/]
    Input --> Prompts[Генерация System/User Prompts]
    Prompts --> MCP[Инициализация серверов Jira и Obsidian]
    MCP --> LoopStart{Начало цикла до 20 итераций}
    
    LoopStart --> LLM[Запрос к LLM API]
    LLM --> CheckError{Есть ошибки API?}
    CheckError -- Да --> EndError([Завершение с ошибкой])
    CheckError -- Нет --> CheckTool{Запрошен tool_calls?}
    
    CheckTool -- Да --> ParseJSON{Валидный JSON?}
    ParseJSON -- Нет --> JSONError[Возврат ошибки JSON агенту] --> LoopStart
    ParseJSON -- Да --> ExecuteTool[Выполнение инструмента]
    
    ExecuteTool --> IsAskUser{ask_user_clarification?}
    IsAskUser -- Да --> InputUser[/Ввод пользователя в консоли/] --> AppendResult[Добавление ответа в историю]
    IsAskUser -- Нет --> MCPServer[Вызов MCP сервера]
    MCPServer --> CheckNote{Это update_note?}
    CheckNote -- Да --> SetFlag[Флаг update_note_called = True] --> AppendResult
    CheckNote -- Нет --> AppendResult
    
    AppendResult --> LoopStart
    
    CheckTool -- Нет --> CleanText[Очистка тегов <think>]
    CleanText --> CheckFlag{Флаг update_note_called == True?}
    CheckFlag -- Нет --> AutoSave[Принудительное сохранение в Obsidian] --> FinalEnd
    CheckFlag -- Да --> FinalEnd
    
    FinalEnd([Вывод финального отчета])