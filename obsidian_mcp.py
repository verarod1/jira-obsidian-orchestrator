import datetime
import os
from pathlib import Path
from markdown_it import MarkdownIt
from mcp.server.fastmcp import FastMCP

# Шаг 1: Папка хранилища по ТЗ
VAULT_DIR = Path(__file__).parent.resolve() / "mock_obsidian_vault"
VAULT_DIR.mkdir(exist_ok=True)

mcp = FastMCP("ObsidianVaultServer")


def _resolve_safe_path(filepath: str) -> Path:
  """Безопасность: гарантирует, что путь находится строго внутри mock_obsidian_vault."""
  target_path = (VAULT_DIR / filepath).resolve()
  if not str(target_path).startswith(str(VAULT_DIR)):
    raise PermissionError(
        f"Отказано в доступе. Разрешена работа только внутри {VAULT_DIR}"
    )
  return target_path


def create_daily_template(file_path: Path, date_str: str):
  """Создает базовый шаблон дневной заметки."""
  template = f"""# Заметка за {date_str}

## ☕ Авто-Standup (AI)

## 📊 Стратегический статус

## 🎯 Ретроспектива
"""
  with open(file_path, "w", encoding="utf-8") as f:
    f.write(template)


# Шаг 2: Инструмент чтения по ТЗ
@mcp.tool()
def read_markdown_file(filename: str = None) -> str:
  """Читает Markdown-файл из хранилища Obsidian.

  Если filename не указан, читает файл за сегодняшнее число (YYYY-MM-DD.md).
  """
  try:
    if not filename:
      filename = f"{datetime.datetime.now().strftime('%Y-%m-%d')}.md"

    file_path = _resolve_safe_path(filename)
    if not file_path.exists():
      return f"Ошибка: Файл '{filename}' не найден в хранилище."

    with open(file_path, "r", encoding="utf-8") as f:
      return f.read()
  except Exception as e:
    return f"Ошибка чтения файла: {e}"


# Шаг 2: Инструмент записи по ТЗ (с AST-логикой преподавателя)
@mcp.tool()
def update_note(
    report_content: str,
    target_heading: str = "☕ Авто-Standup (AI)",
    date_str: str = None,
) -> str:
  """Создает/обновляет секцию в дневной заметке Obsidian.

  :param report_content: Текст отчета в формате Markdown.
  :param target_heading: Название H2 секции, куда вставить текст ("☕
  Авто-Standup (AI)", "📊 Стратегический статус", "🎯 Ретроспектива").
  :param date_str: Дата в формате YYYY-MM-DD. По умолчанию — сегодня.
  """
  try:
    if not date_str:
      date_str = datetime.datetime.now().strftime("%Y-%m-%d")

    filename = f"{date_str}.md"
    file_path = _resolve_safe_path(filename)

    if not file_path.exists():
      create_daily_template(file_path, date_str)

    with open(file_path, "r", encoding="utf-8") as f:
      full_text = f.read()

    # AST-парсер от преподавателя для точечной замены внутри H2
    md = MarkdownIt("commonmark")
    tokens = md.parse(full_text)

    start_line = -1
    end_line = -1
    in_target = False

    for i, token in enumerate(tokens):
      if token.type == "heading_open" and token.tag == "h2":
        title_token = tokens[i + 1]
        if title_token.content.strip() == target_heading.strip():
          in_target = True
          start_line = token.map[1]
          continue

      if (
          in_target
          and token.type == "heading_open"
          and token.tag in ["h1", "h2"]
      ):
        end_line = token.map[0]
        break

    if start_line == -1:
      return (
          f"Ошибка: В файле {filename} не найдена секция H2 '{target_heading}'."
      )

    lines = full_text.splitlines(keepends=True)
    if end_line == -1:
      end_line = len(lines)

    new_content = report_content.strip() + "\n\n"
    new_lines = lines[:start_line] + [new_content] + lines[end_line:]

    with open(file_path, "w", encoding="utf-8") as f:
      f.writelines(new_lines)

    return (
        f"Успешно: Отчет записан в секцию '{target_heading}' файла {filename}"
    )

  except Exception as e:
    return f"Ошибка записи файла: {e}"


if __name__ == "__main__":
  mcp.run()