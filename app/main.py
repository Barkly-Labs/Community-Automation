from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from .database import init_db, connect
from .ollama_client import check_ollama, generate
from .personality import FOUNDER_SYSTEM_PROMPT
from .config import OLLAMA_MODEL

app = FastAPI(title="Barkly Labs Community Automation", version="0.1.0")

@app.on_event("startup")
def startup():
    init_db()

class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    public_context: str = ""

class DraftIn(BaseModel):
    project_id: int
    platform: str = "Discord"
    post_type: str = "development_update"
    goal: str = "Share a clear, friendly development update"
    extra_instructions: str = ""

@app.get("/", response_class=HTMLResponse)
def dashboard():
    return HTMLResponse("""
<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Barkly Labs Community Automation</title>
<style>
body{font-family:system-ui,sans-serif;max-width:900px;margin:2rem auto;padding:0 1rem;background:#faf8fb;color:#28232b}
.card{background:white;border:1px solid #e8dfe9;border-radius:14px;padding:1rem;margin:1rem 0}
input,textarea,select,button{font:inherit;padding:.65rem;border:1px solid #cfc5d1;border-radius:8px;width:100%;box-sizing:border-box;margin:.3rem 0}
button{background:#5b2b52;color:white;cursor:pointer}small{color:#645a66}.draft{white-space:pre-wrap;background:#f4eff5;padding:1rem;border-radius:8px}
</style></head><body>
<h1>🐾 Barkly Labs Community Automation</h1>
<p>Local-first • Draft-only • Human approval</p>
<div class="card"><h2>Ollama status</h2><button onclick="status()">Check connection</button><pre id="status"></pre></div>
<div class="card"><h2>Add a project</h2>
<input id="name" placeholder="Project name">
<textarea id="description" placeholder="Short description"></textarea>
<textarea id="context" placeholder="Public-safe context / current status"></textarea>
<button onclick="addProject()">Save project</button><pre id="projectResult"></pre></div>
<div class="card"><h2>Generate a draft</h2>
<select id="project"></select>
<select id="type"><option value="development_update">Development update</option><option value="announcement">Announcement</option><option value="community_question">Community question</option><option value="technical_explanation">Technical explanation</option><option value="call_for_contributors">Call for contributors</option><option value="milestone">Milestone celebration</option></select>
<input id="goal" value="Share a clear, friendly development update" placeholder="Communication goal">
<textarea id="extra" placeholder="Optional instructions"></textarea>
<button onclick="makeDraft()">Generate and save draft</button><pre id="draftResult" class="draft"></pre></div>
<div class="card"><h2>Saved drafts</h2><button onclick="loadDrafts()">Refresh drafts</button><div id="drafts"></div></div>
<script>
async function status(){let r=await fetch('/api/ollama/status');document.getElementById('status').textContent=JSON.stringify(await r.json(),null,2)}
async function projects(){let r=await fetch('/api/projects');let data=await r.json();let s=document.getElementById('project');s.innerHTML='';data.forEach(p=>{let o=document.createElement('option');o.value=p.id;o.textContent=p.name;s.appendChild(o)})}
async function addProject(){let body={name:document.getElementById('name').value,description:document.getElementById('description').value,public_context:document.getElementById('context').value};let r=await fetch('/api/projects',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});document.getElementById('projectResult').textContent=JSON.stringify(await r.json(),null,2);await projects()}
async function makeDraft(){let body={project_id:Number(document.getElementById('project').value),platform:'Discord',post_type:document.getElementById('type').value,goal:document.getElementById('goal').value,extra_instructions:document.getElementById('extra').value};let r=await fetch('/api/drafts/generate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});let data=await r.json();document.getElementById('draftResult').textContent=data.content||JSON.stringify(data,null,2);await loadDrafts()}
async function loadDrafts(){let r=await fetch('/api/drafts');let data=await r.json();document.getElementById('drafts').innerHTML=data.map(d=>`<div class="card"><b>#${d.id} — ${d.post_type}</b><p class="draft"></p><small>${d.created_at} · ${d.status}</small></div>`).join('');let els=document.querySelectorAll('#drafts .draft');data.forEach((d,i)=>els[i].textContent=d.content)}
projects();loadDrafts();
</script></body></html>
""")

@app.get("/api/ollama/status")
def ollama_status():
    return check_ollama()

@app.get("/api/projects")
def list_projects():
    with connect() as conn:
        rows = conn.execute("SELECT * FROM projects ORDER BY id DESC").fetchall()
        return [dict(row) for row in rows]

@app.post("/api/projects")
def create_project(project: ProjectIn):
    with connect() as conn:
        cursor = conn.execute(
            "INSERT INTO projects(name,description,public_context) VALUES(?,?,?)",
            (project.name.strip(), project.description, project.public_context)
        )
        return {"id": cursor.lastrowid, "name": project.name}

@app.post("/api/drafts/generate")
def generate_draft(request: DraftIn):
    with connect() as conn:
        project = conn.execute("SELECT * FROM projects WHERE id=?", (request.project_id,)).fetchone()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if not check_ollama().get("model_available"):
        raise HTTPException(status_code=503, detail="Ollama is unavailable or configured model is not installed.")
    prompt = f"""Draft a {request.post_type} for {request.platform}.
Communication goal: {request.goal}
Project name: {project['name']}
Description: {project['description']}
Public-safe context: {project['public_context']}
Additional instructions: {request.extra_instructions}

Write only the proposed post. Do not add claims unsupported by the context.
"""
    try:
        content = generate(prompt, FOUNDER_SYSTEM_PROMPT)
    if not content:
        raise HTTPException(status_code=502, detail="Model returned an empty draft")
    with connect() as conn:
        cursor = conn.execute(
            "INSERT INTO drafts(project_id,platform,post_type,content,model,status) VALUES(?,?,?,?,?,?)",
            (request.project_id, request.platform, request.post_type, content, OLLAMA_MODEL, "draft")
        )
        return {"id": cursor.lastrowid, "content": content, "status": "draft"}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Generation failed: {exc}")

@app.get("/api/drafts")
def list_drafts():
    with connect() as conn:
        rows = conn.execute("SELECT * FROM drafts ORDER BY id DESC LIMIT 100").fetchall()
        return [dict(row) for row in rows]
