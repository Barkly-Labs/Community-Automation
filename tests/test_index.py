from app import core, repository_index as ri

def test_incremental_index_and_secret_filter(tmp_path,monkeypatch):
 monkeypatch.setattr(core,'DB',tmp_path/'db.sqlite');core.init()
 repo=tmp_path/'repo';repo.mkdir();(repo/'a.py').write_text('def hello(): return 1')
 (repo/'.env').write_text('SECRET=x');(repo/'node_modules').mkdir();(repo/'node_modules'/'bad.js').write_text('bad')
 first=ri.scan(repo);assert first['indexed']==1 and first['changes']['added']==1
 assert ri.search('hello')[0]['path']=='a.py'
 assert ri.scan(repo)['changes']=={}
 (repo/'a.py').write_text('def hello(): return 2');assert ri.scan(repo)['changes']['modified']==1
 (repo/'a.py').rename(repo/'b.py');assert ri.scan(repo)['changes']=={'added':1,'deleted':1}
 assert ri.preview('a.py') is None
 assert 'hello' in ri.context(['b.py'])
 (repo/'b.py').unlink();assert ri.scan(repo)['indexed']==0
