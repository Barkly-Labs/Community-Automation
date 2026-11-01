import subprocess
from pathlib import Path
from fastapi.testclient import TestClient
from app import core, main

def test_selection_persistence_index_and_api(tmp_path, monkeypatch):
 monkeypatch.setattr(core,'DB',tmp_path/'state.sqlite3')
 root=tmp_path/'a repo with spaces'
 (root/'nested').mkdir(parents=True)
 (root/'nested'/'hello.py').write_text('print("hello")\n')
 subprocess.run(['git','init',str(root)],check=True,capture_output=True)
 with TestClient(main.app) as client:
  assert client.get('/extra.js').status_code==200
  bad=client.post('/api/repo',json={'path':str(root/'missing')})
  assert bad.status_code==400 and 'does not exist' in bad.json()['detail']
  malformed=client.post('/api/repo',json={'wrong':'field'})
  assert malformed.status_code==422
  result=client.post('/api/repo',json={'path':str(root/'nested')+'/'})
  assert result.status_code==200,result.text
  assert result.json()['repository']==str(root.resolve())
  assert client.get('/api/state').json()['repository']==str(root.resolve())
  scan=client.post('/api/scan')
  assert scan.status_code==200,scan.text
  assert client.get('/api/index/status').json()['files']>=1
  assert client.get('/api/index/file',params={'path':'nested/hello.py'}).status_code==200
  assert client.post('/api/repo',json={'path':str(root)}).status_code==200
  assert client.get('/api/index/status').json()['files']>=1

def test_windows_path_validation_on_non_windows(tmp_path):
 import os,pytest
 if os.name!='nt':
  with pytest.raises(ValueError,match='Windows drive paths'):
   core.validate(r'C:\Users\Someone\my repo')
