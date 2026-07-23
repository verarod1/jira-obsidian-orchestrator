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
@mcp.tool()
def search_issues(jql: str, max_results: int = 40, include_comments: bool = False) -> str:
    """
    Выполняет поиск задач в Jira по JQL запросу.
    Возвращает сводку по задачам. Если include_comments=True, добавляет последние комментарии.
    Используй include_comments=True ТОЛЬКО для подготовки ежедневной сводки (Standup).
    """
    safe_max_results = min(max_results, 40)
    url = f"{JIRA_URL}/rest/api/3/search/jql" 
    
    target_fields = ["summary", "status", "issuetype", "created", "assignee", "labels"]
    if include_comments:
        target_fields.append("comment")
        
    payload = {
        "jql": jql,
        "maxResults": safe_max_results,
        "fields": target_fields
    }
    
    response = requests.post(url, json=payload, headers=HEADERS, auth=AUTH)
    if response.status_code != 200:
        return f"Ошибка Jira API (search_issues): {response.text}"
        
    issues = response.json().get("issues", [])
    result = []
    
    def parse_adf(body):
        if isinstance(body, dict):
            text_parts = []
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
            return "".join(text_parts).strip()
        return str(body).strip()

    for issue in issues:
        key = issue.get('key', 'Без ключа')
        fields = issue.get('fields', {})
        summary = fields.get('summary', 'Без названия')
        status = fields.get('status', {}).get('name', 'Неизвестно')
        issuetype = fields.get('issuetype', {}).get('name', 'Неизвестно')
        created = fields.get('created', 'Неизвестно')
        
        assignee_data = fields.get('assignee')
        assignee = assignee_data.get('displayName', 'Не назначен') if assignee_data else 'Не назначен'
        raw_labels = fields.get('labels', [])
        clean_labels = [lbl for lbl in raw_labels if lbl != "test-seed"]
        labels_str = ", ".join(clean_labels) if clean_labels else "Нет меток"
        
        issue_str = (
            f"[{key}] {summary} | Статус: {status} | Тип: {issuetype} | Метки: {labels_str} | "
            f"Исполнитель: {assignee} | Создано: {created}"
        )
        
        if include_comments:
            comment_bundle = fields.get('comment', {})
            comments_list = comment_bundle.get('comments', [])
            
            recent_comments = comments_list[-2:] if comments_list else []
            comments_str_list = []
            
            for c in recent_comments:
                author = c.get('author', {}).get('displayName', 'Неизвестный автор')
                text = parse_adf(c.get('body', ''))
                comments_str_list.append(f"[{author}]: {text}")
                
            comments_summary = " | ".join(comments_str_list) if comments_str_list else "Нет комментариев"
            issue_str += f" | Последние комментарии: {comments_summary}"
            
        result.append(issue_str)
        
    if not result:
        return "Задачи по данному JQL-запросу не найдены."
        
    return "\n".join(result)


@mcp.tool()
def get_comments(issue_key: str) -> str:
    """
    Получает полный список комментариев для конкретной задачи Jira по её ключу (например, VKNOTIF-42).
    Используй только если контекста из поиска задач оказалось недостаточно.
    """
    url = f"{JIRA_URL}/rest/api/3/issue/{issue_key}/comment"
    
    response = requests.get(url, headers=HEADERS, auth=AUTH)
    if response.status_code != 200:
        return f"Ошибка Jira API (get_comments): {response.text}"
        
    comments_data = response.json().get("comments", [])
    result = []
    
    for comment in comments_data:
        author_info = comment.get("author", {})
        author_name = author_info.get("displayName", "Неизвестный автор")
        body = comment.get("body", "")
        
        if isinstance(body, dict):
            text_parts = []
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