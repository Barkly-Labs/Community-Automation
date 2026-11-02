# Barkly Labs · Developer Community Automation MVP

A local-first FastAPI dashboard for indexing Git repositories, watching commits, summarizing evidence with Ollama, and preparing **human-reviewed** community drafts. No publishing feature exists.

## Windows installation

1. Install Python 3.10+ and Git, ensuring both are on PATH. Install [Ollama](https://ollama.com) separately.
2. In a terminal, run `ollama pull llama3.1:8b` and make sure Ollama is running locally.
3. Extract the ZIP into a normal writable folder, then double-click **start.bat**. It creates `.venv`, installs `requirements.txt`, and opens `http://127.0.0.1:8765`.
4. Enter the **absolute path** of an existing local Git repository root (for example `C:\Users\you\Documents\my-project`) and select it. Browsers cannot safely reveal arbitrary local folder paths to a local web app; paste the path instead.
5. Click **Scan now**, or **Start monitoring** for periodic scans. Choose a commit, click **Analyze with Ollama**, select a draft format, and generate/edit/approve a draft.

## Configuration

Copy `.env.example` to `.env` to configure `OLLAMA_URL`, `OLLAMA_MODEL`, and `SCAN_INTERVAL` (seconds). The dashboard also saves the model and endpoint in the local SQLite database. Default model: `llama3.1:8b`.

## Privacy boundaries and limitations

- Dashboard binds to **127.0.0.1 only**. Do not reverse-proxy it or expose port 8765. There is no login/authentication; any local process that can access the port may call its APIs.
- Ollama endpoints are restricted to `localhost` or `127.0.0.1` and HTTP; no cloud AI APIs or outbound publishing integrations are used. Ollama prompts include commit messages, safe-filtered filenames and repository metadata, **not source file bodies**. These fields can still contain sensitive text if a developer puts it in a commit message or path; review Git history before processing.
- Indexing traverses file metadata (names, sizes, extensions) only; it does **not** read or semantically embed source contents. Detection is heuristic; framework identification is approximate. It excludes common secret names, symlinks, caches, binary extensions, large files and hidden directories, but exclusion rules cannot guarantee perfect secret detection.
- Git monitoring polls every 60 seconds by default. It indexes up to the most recent 60 commits across branches per scan; merges appear as Git commits, but merge-specific analytics are not provided. Branch labels reflect the current branch at scan time, not necessarily the commit's original branch. Tracked uncommitted changes are reported as a separate **dirty flag**, not analyzed or drafted. Untracked changes are not reported.
- Classification begins with conservative commit-message heuristics and can be updated by Ollama. The AI may still make mistakes: review all statements against actual code before approving or posting. Approval is a local workflow status, never a publication action.
- Data is stored locally in `data/community.sqlite3`; it can contain commit messages, author names, draft text and filenames. Protect this directory. No automatic publishing occurs.
- This is an MVP, not a full semantic code index, AST architecture mapper, or comprehensive Git event journal. Large repositories may take time to scan. Only the 60 most recent reachable commits per scan are considered.

## Troubleshooting

- **Python not found:** install Python 3.10+ with the Python Launcher (`py`) enabled.
- **Git not found:** install Git for Windows and restart the terminal.
- **Ollama offline:** run Ollama, confirm `ollama list`, and check the local endpoint/model in the dashboard.
- **Port in use:** close the other process using 8765 or manually start `python -m uvicorn app.main:app --host 127.0.0.1 --port 8766` from the virtual environment.
- **Repository rejected:** paste its actual root folder; run `git -C "YOUR_PATH" rev-parse --show-toplevel` to verify.
- **Reset local data:** stop the server, back up and delete `data/community.sqlite3` (also remove SQLite WAL/SHM files if present).

## Tests

From the project root: `.venv\Scripts\python.exe -m pytest -q`. The tests use a temporary Git repository and do not require Ollama.

## Repository-wide indexing and Markdown reports

After selecting the Git repository root, choose **Start background index**. Indexing runs in a worker and updates persistent SQLite FTS5 tables. **Refresh index status** displays progress, exclusions, errors, counts, and detected additions/modifications/deletions. Search returns local text excerpts; previews are limited to 12,000 characters. Monitoring rescans periodically according to `SCAN_INTERVAL`; start or stop it on the dashboard. `INDEX_MAX_BYTES`, `INDEX_EXCLUDE` and `INDEX_INCLUDE` configure file filtering. Only UTF-8 text formats are indexed. Files with sensitive names or recognizable credential patterns are excluded; this is a best-effort safeguard, **not a guarantee that every secret is detected**. Review all generated public text.

Use the **Developer Markdown report generator** to select a period or check specific commits, then generate with a locally running Ollama model. The generated report is editable, previewable, and downloadable; approval is a local state only and never publishes anything. Reports contain abbreviated Git references when Ollama follows the instructions. Inference requires the configured local model; no cloud fallback is provided. The dashboard is intended only for a trusted local machine, and is bound to loopback by the Windows startup scripts. File preview and report generation are intended for the local operator; no login system is included.

**Limitations:** Repository indexing uses polling, not native filesystem events. Git history is limited by the existing scanner to its most recent 60 commits; newly indexed files are matched by path and SHA-256, while Git handles committed rename detection. The report preview supports headings, paragraphs and simple bullets rather than full CommonMark. Repository context is retrieved with local SQLite FTS5, not embeddings. Do not expose the service to untrusted users. The index is tied to one selected repository; switch repositories only after clearing the local index/database, or use a fresh installation.

## Repository selection and API diagnostics

Run the server on the **same computer** that contains the Git working tree. Paste the local absolute directory path into **Local Git repository root**, then click **Select repository**. Subdirectories inside a Git working tree are accepted; Git resolves them to the canonical root (`git rev-parse --show-toplevel`). The selected root persists in local SQLite and is restored on dashboard reload. On Windows, drive letters, spaces, and backslashes work when the server is running on Windows. A browser directory chooser cannot grant a server access to arbitrary folders: use the path input.

After selection, choose **Scan now** to scan Git and index source files, or **Start background index** to index files alone. Index progress is shown in the dashboard. The additional dashboard JavaScript is served at `/extra.js`. Invalid requests return an actionable error with endpoint and status; server-side failures are logged locally without dumping request bodies or source code. To diagnose a 400/422, inspect the browser Network tab for the exact request URL, JSON payload and response details; 422 indicates schema mismatch, while 400 indicates a rejected repository path or operation.

## Calm dashboard (current interface)

The dashboard now opens with one project overview and three primary actions: **Scan project**, **Review recent changes**, and **Generate community update**. The project picker is shown only when needed; use **Change project** to reveal it again. Recent commits are presented as a concise list with details hidden until requested. Report generation defaults to seven days, with optional commit selection under a disclosure. Markdown editing, preview, local approval, copying, and download remain available. File search, local AI configuration, monitoring controls, and diagnostics are under **Project tools**. All existing API endpoints remain unchanged. The old `/extra.js` route remains for compatibility, but the redesigned page loads only `/app.js`.

The interface supports keyboard navigation, live status announcements, responsive layouts, and reduced-motion preferences. The local model must be running to generate reports; a report is never automatically published. Use **Project tools → Local AI settings → Check connection** when generation fails.
