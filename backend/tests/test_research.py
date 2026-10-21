from datetime import datetime,timedelta
import pytest
from app.research import features,normalize_odds,predict,metrics,walk_forward,settle,fit_boosting
from app.ingest import MatchRow
T=datetime(2024,1,1)
def row(i=0,**kwargs):
    return {**dict(id=str(i),competition_id='PL',season='2024',home_id='A',away_id='B',kickoff=T+timedelta(days=i),available_at=T+timedelta(days=i,hours=3),home_goals=2,away_goals=1),**kwargs}
@pytest.mark.parametrize('odds',[[2,3,4],[1.01,20,50],[2.5,3.1,3.2]])
def test_overround(odds):
    p,margin=normalize_odds(odds)
    assert sum(p)==pytest.approx(1)
    assert margin==pytest.approx(sum(1/x for x in odds)-1)
    assert p[0]/p[1]==pytest.approx(odds[1]/odds[0])
@pytest.mark.parametrize('odds',[[0,2,3],[1,2,3],[float('nan'),2,3],[2,3],[float('inf'),2,3]])
def test_bad_odds(odds):
    with pytest.raises(ValueError):normalize_odds(odds)
def test_strict_point_in_time():
    history=[row(0),row(1,available_at=T+timedelta(days=10)),row(3),row(2,available_at=T+timedelta(days=2))]
    f=features(history,'A','B',T+timedelta(days=2))
    assert f['history_ids']==['0'] and f['home']['matches']==1
    assert f['home']['form_5']==3 and f['away']['form_5']==0
    assert f['home']['rest_days']==2 and f['home']['xg'] is None
def test_future_mutations_cannot_change_prediction():
    h=[row(i) for i in range(10)]; f=features(h,'A','B',T+timedelta(days=5))
    h[7]['home_goals']=45;h.append(row(100))
    assert features(h,'A','B',T+timedelta(days=5))==f
def test_probabilities_and_cold_start():
    f=features([],'A','B',T)
    assert f['home']['form_5'] is None
    for p in predict(f).values():
        assert sum(p)==pytest.approx(1) and all(0<v<1 for v in p)
    assert fit_boosting([],T) is None
def test_metrics_and_reliability():
    s=metrics([[1,0,0],[0,1,0],[0,0,1]],[0,1,2])
    assert s['n']==3 and s['brier']==0 and s['accuracy']==1
    wrong=metrics([[.1,.1,.8]],[0]);assert wrong['accuracy']==0 and wrong['log_loss']>2
    assert sum(x['n'] for x in s['reliability'])==9
    assert metrics([],[])['brier'] is None
def test_walk_forward_matches_independent_forecast():
    h=[row(i) for i in range(12)];out=walk_forward(h,min_training=5)
    assert len(out)==7
    for r in out:
        original=next(x for x in h if x['id']==r['match_id'])
        assert r['probabilities']==predict(features(h,'A','B',original['kickoff']))
        assert r['training_n']==int(original['id'])
def test_pnl_counts_losses():
    assert settle(0,0,2.5)==1.5 and settle(0,1,2.5)==-1
def test_import_validation():
    b=dict(id='1',competition_id='PL',season='2024',home_id='A',away_id='B',kickoff='2024-01-01T15:00:00Z',available_at='2023-12-20T00:00:00Z',result_available_at='2024-01-01T18:00:00Z',home_goals=1,away_goals=0)
    assert MatchRow(**b).home_goals==1
    for changed in ({'kickoff':'2024-01-01T15:00:00'},{'result_available_at':'2023-01-01T00:00:00Z'},{'home_id':'B'},{'home_goals':-1}):
        with pytest.raises(ValueError): MatchRow(**{**b,**changed})
