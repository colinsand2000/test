from fastapi.testclient import TestClient
from app.main import app

def test_health_and_mode_separation():
    client=TestClient(app)
    assert client.get('/api/health').json()['real_money'] is False
    real=client.get('/api/matches').json()
    demo=client.get('/api/matches?synthetic=true').json()
    assert all(not m['synthetic'] for m in real)
    assert len(demo)==6 and all(m['synthetic'] for m in demo)
    m=client.get('/api/matches/'+demo[0]['id']).json()
    assert m['snapshot']['synthetic'] is True
    assert m['versions'] and m['cutoff']
    assert client.get('/api/matches/not-a-match').status_code==404
    assert client.get('/api/paper-bets').json()['roi'] is None
    assert client.post('/api/matches').status_code==405
