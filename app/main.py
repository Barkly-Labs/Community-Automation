import os, json, asyncio, threading
from contextlib import asynccontextmanager
from pathlib import Path
import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from . import core
load_dotenv(core.ROOT/'.env')
lock=threading.Lock()
KINDS={'discord':'Discord announcement','developer':'Developer update','progress':'Progress report','feature':'Feature announcement','release':'Release notes','discussion':'Community discussion prompt'}
class Repo(BaseModel):path:str
class DraftRequest(BaseModel):change_id:int;kind:str='developer'
class Edit(BaseModel):body:str;status:str='pending'
class Config(BaseModel):endpoint:str='http://127.0.0.1:11434';model:str='llama3.1:8b'
def config():return Config(endpoint=core.get('endpoint',os.getenv('OLLAMA_URL','http://127.0.0.1:11434')),model=core.get('model',os.getenv('OLLAMA_MODEL','llama3.1:8b')))
def endpoint():
 url=config().endpoint.rstrip('/')
 if not (url.startswith('http://127.0.0.1:') or url.startswith('http://localhost:') or url=='http://127.0.0.1' or url=='http://localhost'):raise HTTPException(400,'Only local loopback Ollama endpoints are allowed')
 return url
async def ai(prompt):
 async with httpx.AsyncClient(timeout=120,trust_env=False) as client:
  r=await client.post(endpoint()+'/api/generate',json={'model':config().model,'prompt':prompt,'stream':False,'options':{'temperature':0.2,'num_predict':650}})
  r.raise_for_status();return r.json().get('response','').strip()
async def monitor():
 while True:
  await asyncio.sleep(max(10,int(os.getenv('SCAN_INTERVAL','60'))))
  if core.get('monitoring')=='true' and core.get('repo'):
   try:
    if lock.acquire(False):
     try:await asyncio.to_thread(core.scan)
     finally:lock.release()
   except Exception as e:core.setval('monitor_error',str(e)[:300])
@asynccontextmanager
async def lifespan(app):
 core.init();task=asyncio.create_task(monitor())
 try:yield
 finally:task.cancel()
app=FastAPI(title='Barkly Labs Community Automation',lifespan=lifespan,docs_url=None,redoc_url=None)
@app.get('/')
def home():return FileResponse(core.ROOT/'app/static/index.html')
@app.get('/app.css')
def css():return FileResponse(core.ROOT/'app/static/app.css')
@app.get('/app.js')
def js():return FileResponse(core.ROOT/'app/static/app.js')
@app.get('/api/state')
def state():return {**core.history(),'config':config().model_dump(),'monitor_error':core.get('monitor_error')}
@app.post('/api/repo')
def repo(data:Repo):
 try:p=core.validate(data.path)
 except Exception as e:raise HTTPException(400,str(e))
 core.setval('repo',str(p));return {'repository':str(p)}
@app.post('/api/scan')
def scan():
 if not lock.acquire(False):raise HTTPException(409,'Scan already running')
 try:
  try:return core.scan()
  except Exception as e:raise HTTPException(400,str(e))
 finally:lock.release()
@app.post('/api/monitor/{action}')
def monitoring(action:str):
 if action not in ('start','stop'):raise HTTPException(400,'Invalid action')
 core.setval('monitoring',str(action=='start').lower());return {'monitoring':action=='start'}
@app.post('/api/config')
def save_config(data:Config):
 if not (data.endpoint.startswith('http://localhost:') or data.endpoint.startswith('http://127.0.0.1:')):raise HTTPException(400,'Ollama must be on loopback')
 core.setval('endpoint',data.endpoint);core.setval('model',data.model);return {'ok':True}
@app.get('/api/ollama')
async def ollama():
 try:
  async with httpx.AsyncClient(timeout=4,trust_env=False) as c:
   r=await c.get(endpoint()+'/api/tags');r.raise_for_status()
   return {'connected':True,'models':[m.get('name') for m in r.json().get('models',[])],'configured':config().model}
 except Exception as e:return {'connected':False,'error':str(e)[:200],'configured':config().model}
@app.post('/api/analyze/{change_id}')
async def analyze(change_id:int):
 with core.conn() as c:row=c.execute('SELECT * FROM changes WHERE id=?',(change_id,)).fetchone()
 if not row:raise HTTPException(404,'Commit not found')
 path=core.validate(core.get('repo'));files=json.loads(row['files'])
 # Commit metadata and filenames only: no raw source or secrets included in prompts.
 prompt=f'''Analyze only the documented Git evidence below. Do not invent functionality, dates, results, or claims. If evidence is insufficient, explicitly say so. Return concise factual summary and a line 'Significance: minor|normal|major' and 'Announcement: yes|no'.\nCommit subject: {row['subject'][:300]}\nChanged non-sensitive filenames: {json.dumps(files)[:4500]}\nRepository context: {json.dumps(core.index(path))[:3000]}'''
 try:result=await ai(prompt)
 except Exception as e:raise HTTPException(503,'Local Ollama failed: '+str(e)[:200])
 import re
 m=re.search(r'Significance:\s*(minor|normal|major)',result,re.I);a=re.search(r'Announcement:\s*(yes|no)',result,re.I)
 sig=m.group(1).lower() if m else row['significance'];announce=int(a.group(1).lower()=='yes') if a else row['announce']
 with core.conn() as c:c.execute('UPDATE changes SET summary=?,significance=?,announce=? WHERE id=?',(result,sig,announce,change_id))
 return {'summary':result,'significance':sig,'announce':bool(announce)}
@app.post('/api/drafts')
async def draft(data:DraftRequest):
 if data.kind not in KINDS:raise HTTPException(400,'Invalid draft type')
 with core.conn() as c:row=c.execute('SELECT * FROM changes WHERE id=?',(data.change_id,)).fetchone()
 if not row:raise HTTPException(404,'Commit not found')
 prompt=f'''Write an editable {KINDS[data.kind]} for Barkly Labs, a Detroit-rooted accessibility-minded nonprofit technology lab. Warm, direct, curious, honest, technically grounded, community-centered; no corporate hype. Values: technology adapts to people; people are not numbers; accessibility, privacy, local-first tools and community agency matter. Use ONLY evidence below. Do not invent features, statistics, release dates, promises or achievements. No private personal details. If evidence is insufficient, say what is known without speculation. Never imply the draft has been published.\nCommit: {row['subject'][:300]}\nFiles: {row['files'][:4000]}\nVerified summary: {row['summary'][:5000]}'''
 try:body=await ai(prompt)
 except Exception as e:raise HTTPException(503,'Local Ollama failed: '+str(e)[:200])
 with core.conn() as c:
  cur=c.execute('INSERT INTO drafts(change_id,kind,body,status,created_at,updated_at) VALUES(?,?,?,?,?,?)',(data.change_id,data.kind,body,'pending',core.now(),core.now()));return {'id':cur.lastrowid,'body':body}
@app.put('/api/drafts/{draft_id}')
def edit(draft_id:int,data:Edit):
 if data.status not in ('pending','approved','rejected'):raise HTTPException(400,'Invalid status')
 if len(data.body)>30000:raise HTTPException(400,'Draft too long')
 with core.conn() as c:
  cur=c.execute('UPDATE drafts SET body=?,status=?,updated_at=? WHERE id=?',(data.body,data.status,core.now(),draft_id))
  if not cur.rowcount:raise HTTPException(404,'Draft not found')
 return {'ok':True}
