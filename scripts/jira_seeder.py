import requests
import json
from requests.auth import HTTPBasicAuth
import os
from dotenv import load_dotenv
import time

load_dotenv()

JIRA_TOKEN = os.getenv("JIRA_API_TOKEN")
JIRA_EMAIL = os.getenv("JIRA_EMAIL")
JIRA_URL = os.getenv("JIRA_URL")
PROJECT_KEY = os.getenv("PROJECT_KEY")

auth = HTTPBasicAuth(JIRA_EMAIL, JIRA_TOKEN)
headers = {
    "Accept": "application/json",
    "Content-Type": "application/json"
}

STATUS_MAPPING = {
    "done": "готово",
    "in progress": "в работе",
    "in review": "ревью",
    "testing": "тестирование",
    "to do": "к выполнению"
}

def load_mock_data(filepath="mock_sprint.json"):
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)

def create_adf_text(text):
    return {
        "version": 1,
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": text}
                ]
            }
        ]
    }

def create_epic(title, description):
    url = f"{JIRA_URL}/rest/api/3/issue"
    payload = {
        "fields": {
            "project": {"key": PROJECT_KEY},
            "summary": title,
            "description": create_adf_text(description), 
            "issuetype": {"name": "Epic"},
            "labels": ["test-seed"]
        }
    }
    
    response = requests.post(url, json=payload, headers=headers, auth=auth)
    time.sleep(0.5) 
    
    if response.status_code == 201:
        epic_key = response.json().get("key")
        print(f"Эпик создан: {epic_key}")
        return epic_key
    else:
        print(f"Ошибка создания Эпика '{title}': {response.text}")
        return None
    
def create_task(epic_key, task):
    url = f"{JIRA_URL}/rest/api/3/issue"
    
    task_labels = ["test-seed"]
    if task.get("role"):
        task_labels.append(task["role"])
    if "estimated" in task:
        if task["estimated"]:
            task_labels.append("estimated")
        else:
            task_labels.append("unestimated")
            
    title_lower = task["title"].lower()
    if "bug" in title_lower:
        issue_type = "Bug"
    else:
        issue_type = "Task"
            
    payload = {
        "fields": {
            "project": {"key": PROJECT_KEY},
            "summary": task["title"],
            "description": create_adf_text(task["description"]),
            "issuetype": {"name": issue_type},
            "parent": {"key": epic_key},
            "labels": task_labels
        }
    }
    
    if task.get("priority"):
        payload["fields"]["priority"] = {"name": task["priority"]}
    
    response = requests.post(url, json=payload, headers=headers, auth=auth)
    time.sleep(0.5) 
    
    if response.status_code == 201:
        task_key = response.json().get("key")
        print(f"  {issue_type} создана: {task_key} (привязана к {epic_key})")
        return task_key
    else:
        print(f"  Ошибка создания {issue_type} '{task['title']}': {response.text}")
        return None

def add_comment(issue_key, comment_text):
    url = f"{JIRA_URL}/rest/api/3/issue/{issue_key}/comment"
    
    payload = {
        "body": create_adf_text(comment_text) 
    }
    
    response = requests.post(url, json=payload, headers=headers, auth=auth)
    time.sleep(0.5)
    
    if response.status_code == 201:
        print(f"  💬 Добавлен комментарий к {issue_key}")
    else:
        print(f"  ⚠️ Ошибка добавления комментария к {issue_key}: {response.text}")

def transition_issue(issue_key, target_status):
    if not target_status or target_status.lower() == "to do":
        return 
        
    get_url = f"{JIRA_URL}/rest/api/3/issue/{issue_key}/transitions"
    response = requests.get(get_url, headers=headers, auth=auth)
    
    if response.status_code != 200:
        print(f"  ⚠️ Ошибка получения переходов для {issue_key}: {response.text}")
        return

    transitions = response.json().get("transitions", [])
    target_lower = target_status.lower()
    
    mapped_target = STATUS_MAPPING.get(target_lower, target_lower)
    
    transition_id = None
    
    for t in transitions:
        t_name = t.get("name", "").lower()
        if mapped_target in t_name or t_name in mapped_target:
            transition_id = t.get("id")
            break
            
    if not transition_id:
        print(f"  ⚠️ Статус '{target_status}' (маппинг: '{mapped_target}') не доступен для {issue_key}. Доступные: {[t['name'] for t in transitions]}")
        return
        
    post_url = f"{JIRA_URL}/rest/api/3/issue/{issue_key}/transitions"
    payload = {"transition": {"id": transition_id}}
    
    post_response = requests.post(post_url, json=payload, headers=headers, auth=auth)
    time.sleep(0.5) 
    
    if post_response.status_code == 204:
        print(f"  ↪ Статус обновлен: {issue_key} -> {target_status} ({t_name})")
    else:
        print(f"  ⚠️ Ошибка смены статуса {issue_key}: {post_response.text}")


print("Начинаем генерацию песочницы...")
data = load_mock_data()
tasks_count = 0

for epic_data in data.get("epics", []):
    epic_key = create_epic(epic_data["title"], epic_data["description"])
    
    if epic_key:
        for task_data in epic_data.get("tasks", []):
            task_key = create_task(epic_key, task_data)
            
            if task_key:
                tasks_count += 1
                
                if "status" in task_data:
                    transition_issue(task_key, task_data["status"])
                
                if "mock_comment" in task_data:
                    add_comment(task_key, task_data["mock_comment"])
                    
print(f"\nГенерация завершена. Успешно обработано задач: {tasks_count}")

