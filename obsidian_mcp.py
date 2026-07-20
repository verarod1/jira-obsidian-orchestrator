import os
from pathlib import Path
from mcp.server.fastmcp import FastMCP
from markdown_it import MarkdownIt

mcp = FastMCP("ObsidianManager")

BASE_DIR = Path("mock_obsidian_vault").resolve()
BASE_DIR.mkdir(exist_ok=True)

def validate_path(filename: str) -> Path:
    target_path = (BASE_DIR / filename).resolve()
    try:
        target_path.relative_to(BASE_DIR)
    except ValueError:
        raise ValueError(f"Ошибка безопасности: доступ к пути '{filename}' запрещен.")
    return target_path

@mcp.tool()
def read_markdown_file(filename: str) -> str:
    """
    Читает содержимое Markdown файла из локального хранилища.
    Args:
        filename: Имя файла (например, '2026-07-20.md')
    """
    try:
        safe_path = validate_path(filename)
        if not safe_path.exists():
            return f"Ошибка: Файл '{filename}' не найден."
            
        with open(safe_path, 'r', encoding='utf-8') as f:
            return f.read()
            
    except ValueError as ve:
        return str(ve)
    except Exception as e:
        return f"Непредвиденная ошибка при чтении: {str(e)}"
    
@mcp.tool()
def update_note(filename: str, target_heading: str, new_content: str) -> str:
    """
    Обновляет секцию в Markdown файле под заданным заголовком H2.
    Сохраняет остальной контент и метаданные (YAML-фронтмэттер).
    Обеспечивает идемпотентность: заменяет старый контент секции на новый.
    """
    try:
        safe_path = validate_path(filename)
        
        if safe_path.exists():
            with open(safe_path, 'r', encoding='utf-8') as f:
                original_text = f.read()
        else:
            original_text = ""
            
        original_lines = original_text.splitlines()
        
        md = MarkdownIt()
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
            
        if start_line != -1:
            new_lines = original_lines[:start_line] 
            if new_content:
                new_lines.extend(new_content.strip().splitlines())
            
            if end_line != -1 and end_line < len(original_lines):
                if new_lines and new_lines[-1].strip() != "":
                    new_lines.append("")
                new_lines.extend(original_lines[end_line:])
        else:
            new_lines = original_lines
            if new_lines and new_lines[-1].strip() != "":
                new_lines.append("")
            new_lines.append(f"## {target_heading}")
            if new_content:
                new_lines.extend(new_content.strip().splitlines())
            
        result_text = "\n".join(new_lines) + "\n"
        
        with open(safe_path, 'w', encoding='utf-8') as f:
            f.write(result_text)
            
        return f"Успех: Секция '{target_heading}' в файле '{filename}' обновлена."
        
    except ValueError as ve:
        return str(ve)
    except Exception as e:
        return f"Ошибка при обновлении файла: {str(e)}"    

if __name__ == "__main__":
    print(f"Запуск Obsidian MCP сервера. Рабочая директория: {BASE_DIR}")
    mcp.run()