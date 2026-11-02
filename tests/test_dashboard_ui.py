from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app

ROOT = Path(__file__).resolve().parents[1]

def test_dashboard_accessible_primary_workflow():
    html = (ROOT / 'app/static/index.html').read_text(encoding='utf-8')
    script = (ROOT / 'app/static/app.js').read_text(encoding='utf-8')
    for item in ('repoForm', 'scanBtn', 'reviewBtn', 'generateBtn', 'reportBtn', 'reportBody', 'indexInfo', 'monitorStart'):
        assert item in html or item in script
    assert 'role="status"' in html
    assert 'aria-live="polite"' in html
    assert 'app.js' in html and '<script src="/extra.js"' not in html
    assert "api('repo','POST',{path:" in script
    assert "api('scan','POST')" in script
    assert "api('reports','POST'" in script
    assert "api('reports/'+id,'PUT'" in script

def test_dashboard_served_with_assets():
    with TestClient(app) as client:
        assert client.get('/').status_code == 200
        assert client.get('/app.css').status_code == 200
        assert client.get('/app.js').status_code == 200
        assert client.get('/api/state').status_code == 200
