import datetime
from pathlib import Path
from mcp.server.fastmcp import FastMCP
from markdown_it import MarkdownIt

mcp = FastMCP("ObsidianManager")

BASE_DIR = Path(__file__).parent.resolve() / "mock_obsidian_vault"
BASE_DIR.mkdir(exist_ok=True)

def validate_path(filename: str) -> Path:
    """Обеспечивает строгую изоляцию внутри BASE_DIR."""
    target_path = (BASE_DIR / filename).resolve()
    try:
        target_path.relative_to(BASE_DIR)
    except ValueError:
        raise PermissionError(f"Ошибка безопасности: доступ к пути '{filename}' запрещен.")
    return target_path

def ensure_daily_template(file_path: Path, date_str: str):
    """Создает шаблон, если файла не существует."""
    if not file_path.exists():
        template = f"""---
date: {date_str}
type: daily-note
---
# Заметка за {date_str}

## Авто-Standup (AI)

## Стратегический статус

## Ретроспектива
"""
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(template)

@mcp.tool()
def read_markdown_file(filename: str = None) -> str:
    """Читает Markdown файл. По умолчанию берет файл за сегодня."""
    try:
        if not filename:
            filename = f"{datetime.datetime.now().strftime('%Y-%m-%d')}.md"
            
        safe_path = validate_path(filename)
        if not safe_path.exists():
            return f"Ошибка: Файл '{filename}' не найден."
            
        with open(safe_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        return f"Ошибка чтения: {str(e)}"
    
@mcp.tool()
def update_note(
    new_content: str, 
    target_heading: str = "Авто-Standup (AI)",
    filename: str = None
) -> str:
    """
    Обновляет секцию H2 в Markdown файле (идемпотентно).
    Сохраняет YAML-фронтмэттер и сторонние записи.
    """
    try:
        if not filename:
            filename = f"{datetime.datetime.now().strftime('%Y-%m-%d')}.md"
            
        safe_path = validate_path(filename)
        ensure_daily_template(safe_path, filename.replace('.md', ''))
        
        with open(safe_path, 'r', encoding='utf-8') as f:
            original_text = f.read()
            
        original_lines = original_text.splitlines(keepends=True)
        
        md = MarkdownIt("commonmark")
        tokens = md.parse(original_text)
        
        start_line = -1
        end_line = -1
        in_target_section = False
        
        for i, token in enumerate(tokens):
            if token.type == 'heading_open':
                level = int(token.tag[1:])
                
                if not in_target_section and level == 2:
                    title_token = tokens[i+1]
                    if title_token.type == 'inline' and title_token.content.strip() == target_heading:
                        in_target_section = True
                        start_line = token.map[1] if token.map else -1
                        continue
                
                elif in_target_section and level <= 2:
                    end_line = token.map[0] if token.map else -1
                    break
                    
        if in_target_section and end_line == -1:
            end_line = len(original_lines)
            
        formatted_content = new_content.strip() + "\n\n"
        
        if start_line != -1:
            new_lines = original_lines[:start_line] + [formatted_content] + original_lines[end_line:]
        else:
            new_lines = original_lines
            if new_lines and not new_lines[-1].endswith("\n"):
                new_lines.append("\n\n")
            elif new_lines and new_lines[-1] != "\n":
                new_lines.append("\n")
            
            new_lines.append(f"## {target_heading}\n\n")
            new_lines.append(formatted_content)
            
        with open(safe_path, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
            
        return f"Успех: Секция '{target_heading}' в файле '{filename}' обновлена."
        
    except Exception as e:
        return f"Ошибка при обновлении файла: {str(e)}"    

if __name__ == "__main__":
    mcp.run()