import os
import requests
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv

load_dotenv()

JIRA_TOKEN = os.getenv("JIRA_API_TOKEN")
JIRA_EMAIL = os.getenv("JIRA_EMAIL")
JIRA_URL = os.getenv("JIRA_URL")
PROJECT_KEY = os.getenv("PROJECT_KEY")

AUTH = HTTPBasicAuth(JIRA_EMAIL, JIRA_TOKEN)
HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json"
}

def get_test_issues():
    jql = f'project = "{PROJECT_KEY}" AND labels = "test-seed"'
    search_url = f"{JIRA_URL}/rest/api/3/search/jql"

    payload = {
        "jql": jql,
        "maxResults": 100,
        "fields": ["id", "key", "issueKey"]
    }

    response = requests.post(search_url, json=payload, headers=HEADERS, auth=AUTH)

    if response.status_code != 200:
        print(f"❌ Ошибка поиска: {response.text}")
        exit()

    return response.json().get("issues", [])

def delete_issues(issues):
    if not issues:
        print("✅ Тестовых задач не найдено, доска чиста.")
        return

    print(f"Найдено {len(issues)} задач. Удаляем...")

    for issue in issues:
        # Безопасное извлечение
        issue_key = issue.get("key") or issue.get("issueKey") or issue.get("id")
        
        if not issue_key:
            print(f"⚠️ Непонятный формат объекта от Jira (пропускаем): {issue}")
            continue

        delete_url = f"{JIRA_URL}/rest/api/3/issue/{issue_key}"
        del_res = requests.delete(delete_url, headers=HEADERS, auth=AUTH)
        
        if del_res.status_code == 204:
            print(f"   🗑️ Удалена задача {issue_key}")
        else:
            print(f"   ⚠️ Ошибка удаления {issue_key}: {del_res.text}")

    print("✨ Очистка завершена!")


issues = get_test_issues()
delete_issues(issues)

