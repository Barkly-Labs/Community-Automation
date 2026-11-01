import os, json, sqlite3, subprocess, re, hashlib
from pathlib import Path
from datetime import datetime, timezone
from collections import Counter

ROOT=Path(__file__).resolve().parents[1]
DB=ROOT/'data'/'community.sqlite3'
EXCLUDE={'.git','node_modules','.venv','venv','env','__pycache__','dist','build','.next','.astro','coverage','.pytest_cache','.mypy_cache','.idea','.vscode','target','vendor','out','.tox'}
BLOCK={'.env','.pem','.key','.p12','.pfx','.sqlite','.db','.zip','.tar','.gz','.exe','.dll','.so','.pyc','.png','.jpg','.jpeg','.gif','.webp','.ico','.pdf','.mp4','.mp3','.woff','.woff2','.ttf','.otf','.lock'}
SECRET=re.compile(r'(secret|password|credential|private.key|token|api.key|\.env)',re.I)
LANG={'.py':'Python','.js':'JavaScript','.jsx':'JavaScript','.ts':'TypeScript','.tsx':'TypeScript','.rs':'Rust','.go':'Go','.java':'Java','.rb':'Ruby','.php':'PHP','.cs':'C#','.cpp':'C++','.c':'C','.h':'C/C++','.html':'HTML','.css':'CSS','.astro':'Astro','.vue':'Vue','.svelte':'Svelte','.sh':'Shell','.ps1':'PowerShell','.sql':'SQL','.md':'Markdown','.json':'JSON','.yml':'YAML','.yaml':'YAML'}
FRAME={'package.json':'Node.js','pyproject.toml':'Python packaging','requirements.txt':'Python','Cargo.toml':'Cargo','go.mod':'Go','Gemfile':'Ruby Bundler','manage.py':'Django (possible)','astro.config.mjs':'Astro','next.config.js':'Next.js','vite.config.ts':'Vite','pom.xml':'Maven'}
def now():return datetime.now(timezone.utc).isoformat()
def conn():
 DB.parent.mkdir(parents=True,exist_ok=True)
 c=sqlite3.connect(DB,timeout=10);c.row_factory=sqlite3.Row;c.execute('PRAGMA journal_mode=WAL');return c
def init():
 with conn() as c:
  c.executescript('''CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT);
  CREATE TABLE IF NOT EXISTS changes(id INTEGER PRIMARY KEY,commit_hash TEXT UNIQUE,subject TEXT,author TEXT,committed_at TEXT,branch TEXT,files TEXT,summary TEXT,significance TEXT,announce INTEGER DEFAULT 0,created_at TEXT);
  CREATE TABLE IF NOT EXISTS drafts(id INTEGER PRIMARY KEY,change_id INTEGER,kind TEXT,body TEXT,status TEXT DEFAULT 'pending',created_at TEXT,updated_at TEXT);
  CREATE TABLE IF NOT EXISTS scans(id INTEGER PRIMARY KEY,created_at TEXT,head TEXT,branch TEXT,dirty TEXT,overview TEXT,error TEXT);''')
def get(k,default=''):
 with conn() as c:
  r=c.execute('SELECT value FROM settings WHERE key=?',(k,)).fetchone();return r['value'] if r else default
def setval(k,v):
 with conn() as c:c.execute('INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(k,str(v)))
def git(path,*args,limit=200000):
 x=subprocess.run(['git','-C',str(path),*args],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=25)
 if x.returncode:raise RuntimeError((x.stderr or 'Git failed')[:300])
 return x.stdout[:limit].strip()
def validate(path):
 """Accept any directory inside a working tree and return Git's canonical root."""
 if not isinstance(path,str) or not path.strip():
  raise ValueError('Enter a local repository directory path.')
 raw=path.strip().strip('"').strip("'")
 # Windows drive paths cannot be accessed by a Linux-hosted server; provide actionable error.
 if os.name!='nt' and re.match(r'^[A-Za-z]:[\\/]',raw):
  raise ValueError('Windows drive paths require running the dashboard on the same Windows computer as the repository.')
 try:p=Path(raw).expanduser().resolve(strict=True)
 except (OSError,ValueError) as e:raise ValueError('Repository path does not exist or cannot be accessed: '+raw) from e
 if not p.is_dir():raise ValueError('Repository path must be a directory.')
 try:
  root=git(p,'rev-parse','--show-toplevel')
  inside=git(p,'rev-parse','--is-inside-work-tree')
 except (RuntimeError,OSError) as e:raise ValueError('Git cannot find a working-tree repository at this directory. Choose a cloned Git repository.') from e
 if inside!='true':raise ValueError('Selected directory is not inside a Git working tree.')
 resolved=Path(root).resolve(strict=True)
 if not resolved.is_dir():raise ValueError('Git returned an inaccessible repository root.')
 return resolved

def index(path):
 count=0; sizes=0; languages=Counter();dirs=Counter();important=[];frameworks=set();structure=[]
 for base,sub,files in os.walk(path,followlinks=False):
  sub[:]=[d for d in sub if d not in EXCLUDE and not (Path(base)/d).is_symlink() and not d.startswith('.')]
  relbase=Path(base).relative_to(path)
  if len(relbase.parts)<=2 and len(structure)<120:structure.append(str(relbase) or '.')
  for name in files:
   f=Path(base)/name;ext=f.suffix.lower()
   if f.is_symlink() or name.startswith('.env') or ext in BLOCK or SECRET.search(name) or f.stat().st_size>500000:continue
   count+=1;sizes+=f.stat().st_size;languages[LANG.get(ext,'Other')]+=1
   if len(relbase.parts):dirs[str(relbase.parts[0])]+=1
   if name in FRAME:frameworks.add(FRAME[name])
   if name.lower() in {'readme.md','license','contributing.md','dockerfile','pyproject.toml','package.json'} and len(important)<30:important.append(str(f.relative_to(path)))
 return dict(files=count,bytes=sizes,languages=dict(languages.most_common()),directories=dict(dirs.most_common(25)),frameworks=sorted(frameworks),important=important,structure=structure)
def safe_files(raw):
 return [x for x in raw.splitlines() if x and not any(y in EXCLUDE for y in Path(x).parts) and not SECRET.search(x) and Path(x).suffix.lower() not in BLOCK][:150]
def classify(subject,files):
 s=subject.lower();major=any(t in s for t in ('release','milestone','breaking','launch','architecture','accessibility','integration','feature'))
 minor=any(t in s for t in ('typo','format','chore','lint','docs:'))
 return ('major' if major else 'minor' if minor else 'normal'),major

def scan():
 path=validate(get('repo'))
 overview=index(path)
 try:head=git(path,'rev-parse','HEAD')
 except RuntimeError:head=''  # Valid newly initialized repositories have no HEAD commit yet.
 branch=git(path,'branch','--show-current');dirty=git(path,'status','--porcelain','--untracked-files=no',limit=15000)
 commits=git(path,'log','-60','--format=%H%x1f%s%x1f%an%x1f%aI','--all').splitlines() if head else []
 new=0
 with conn() as c:
  for line in reversed(commits):
   parts=line.split('\x1f');
   if len(parts)!=4:continue
   h,subject,author,date=parts
   if c.execute('SELECT 1 FROM changes WHERE commit_hash=?',(h,)).fetchone():continue
   files=safe_files(git(path,'diff-tree','--no-commit-id','--name-only','-r','--root',h))
   significance,announce=classify(subject,files)
   c.execute('INSERT INTO changes(commit_hash,subject,author,committed_at,branch,files,summary,significance,announce,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)',(h,subject,author,date,branch,json.dumps(files),subject,significance,int(announce),now()));new+=1
  c.execute('INSERT INTO scans(created_at,head,branch,dirty,overview,error) VALUES(?,?,?,?,?,NULL)',(now(),head,branch,dirty,json.dumps(overview)))
 return {'new_commits':new,'head':head,'branch':branch,'dirty':bool(dirty),'overview':overview}

def history():
 with conn() as c:
  s=c.execute('SELECT * FROM scans ORDER BY id DESC LIMIT 1').fetchone()
  changes=[dict(x) for x in c.execute('SELECT * FROM changes ORDER BY committed_at DESC LIMIT 100')]
  drafts=[dict(x) for x in c.execute('SELECT * FROM drafts ORDER BY id DESC LIMIT 100')]
 return {'repository':get('repo'),'monitoring':get('monitoring','false')=='true','last_scan':dict(s) if s else None,'changes':changes,'drafts':drafts}
