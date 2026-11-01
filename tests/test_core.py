import subprocess
from pathlib import Path
from app import core

def test_index_and_git_scan(tmp_path,monkeypatch):
 repo=tmp_path/'repo';repo.mkdir();(repo/'main.py').write_text('print(1)');(repo/'.env').write_text('SECRET=x');(repo/'node_modules').mkdir();(repo/'node_modules'/'ignored.js').write_text('x')
 def git(*args):subprocess.run(['git','-C',str(repo),*args],check=True,capture_output=True)
 git('init');git('config','user.email','test@example.invalid');git('config','user.name','Tester');git('add','main.py');git('commit','-m','feat: improve accessibility')
 monkeypatch.setattr(core,'DB',tmp_path/'test.sqlite3');core.init();core.setval('repo',str(repo));a=core.scan();b=core.scan()
 assert a['new_commits']==1 and b['new_commits']==0
 assert a['overview']['languages']=={'Python':1}
 assert core.history()['changes'][0]['significance']=='major'
 assert core.history()['last_scan']['dirty']==''
 (repo/'main.py').write_text('print(2)');assert core.scan()['dirty'] is True

def test_classification():
 assert core.classify('fix typo',[])[0]=='minor'
 assert core.classify('new integration',[])[0]=='major'
 assert core.classify('fix crash',[])[0]=='normal'
