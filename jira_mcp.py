import os
import requests
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from requests.auth import HTTPBasicAuth

load_dotenv()

JIRA_URL = os.getenv("JIRA_URL")
JIRA_EMAIL = os.getenv("JIRA_EMAIL")
JIRA_TOKEN = os.getenv("JIRA_API_TOKEN")
AUTH = HTTPBasicAuth(JIRA_EMAIL, JIRA_TOKEN)
HEADERS = {"Accept": "application/json", "Content-Type": "application/json"}

mcp = FastMCP("JiraTeamReviewServer")

@mcp.tool()
def search_issues(jql: str, max_results: int = 100) -> str:
    """
    Выполняет поиск задач в Jira по JQL запросу.
    Используй это, чтобы найти нужные эпики или таски за спринт.
    """
    url = f"{JIRA_URL}/rest/api/3/search" 
    payload = {
        "jql": jql,
        "maxResults": max_results,
        "fields": ["summary", "status", "issuetype", "created"]
    }
    
    response = requests.post(url, json=payload, headers=HEADERS, auth=AUTH)
    if response.status_code != 200:
        return f"Ошибка Jira API (search_issues): {response.text}"
        
    issues = response.json().get("issues", [])
    result = []
    for issue in issues:
        key = issue.get('key', 'Без ключа')
        fields = issue.get('fields', {})
        summary = fields.get('summary', 'Без названия')
        status = fields.get('status', {}).get('name', 'Неизвестно')
        issuetype = fields.get('issuetype', {}).get('name', 'Неизвестно')
        created = fields.get('created', 'Неизвестно')
        
        issue_str = f"[{key}] {summary} | Статус: {status} | Тип: {issuetype} | Создано: {created}"
        result.append(issue_str)
        
    if not result:
        return "Задачи по данному JQL-запросу не найдены."
        
    return "\n".join(result)


@mcp.tool()
def get_comments(issue_key: str) -> str:
    """
    Получает список комментариев для конкретной задачи Jira по её ключу (например, VKNOTIF-42).
    Помогает узнать обсуждения команды и контекст по зависшим или спорным задачам.
    """
    url = f"{JIRA_URL}/rest/api/3/issue/{issue_key}/comment"
    
    response = requests.get(url, headers=HEADERS, auth=AUTH)
    if response.status_code != 200:
        return f"Ошибка Jira API (get_comments): {response.text}"
        
    comments_data = response.json().get("comments", [])
    result = []
    
    for comment in comments_data:
        # Получаем имя автора комментария (с поддержкой разных форматов Jira API)
        author_info = comment.get("author", {})
        author_name = author_info.get("displayName", "Неизвестный автор")
        
        # Получаем тело комментария. В Jira Cloud API v3 текст часто приходит в формате ADF (JSON).
        # Для простоты извлечем плоский текст или зачитаем строковое поле body, если оно есть.
        body = comment.get("body", "")
        
        # Если body содержит ADF-документ (словарь), вытащим из него только текстовые куски:
        if isinstance(body, dict):
            text_parts = []
            # Простейший парсинг ADF структуры
            def extract_text(node):
                if isinstance(node, dict):
                    if node.get("type") == "text":
                        text_parts.append(node.get("text", ""))
                    for value in node.values():
                        extract_text(value)
                elif isinstance(node, list):
                    for item in node:
                        extract_text(item)
            extract_text(body)
            comment_text = "".join(text_parts).strip()
        else:
            comment_text = str(body).strip()
            
        created = comment.get("created", "Неизвестно")
        
        result.append(f"Автор: {author_name} ({created})\nКомментарий: {comment_text}\n---")
        
    if not result:
        return f"У задачи {issue_key} нет комментариев."
        
    return "\n".join(result)


if __name__ == "__main__":
    mcp.run()