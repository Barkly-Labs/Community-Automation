# Barkly Labs Community Automation (MVP)

Windows-friendly local-first starter for Ollama + FastAPI + SQLite.

## Requirements
- Windows 10/11
- Python 3.11+
- Ollama installed and running
- Llama 3.1 8B pulled in Ollama (`ollama pull llama3.1:8b`)

## Start
1. Extract this ZIP.
2. Open the extracted folder.
3. Double-click `start_windows.bat` (or run it in Command Prompt).
4. Open http://127.0.0.1:8000

The first run creates `.venv`, installs dependencies, and initializes SQLite.

## MVP features
- Check Ollama connectivity/model availability
- Register projects
- Configure founder voice text
- Generate post drafts from project context
- Save and list drafts in SQLite

No publishing is enabled yet. Draft-only by design.

## Configuration
Edit `.env`:
- `OLLAMA_BASE_URL=http://127.0.0.1:11434`
- `OLLAMA_MODEL=llama3.1:8b`
- `DATABASE_URL=sqlite:///./barkly.db`

## Notes
- Keep private personal information out of public project context.
- Generated posts are drafts; review before publishing.
