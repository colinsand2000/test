"""Deterministic models and point-in-time features. No LLM predictions."""
import hashlib
import json
import math
from datetime import timedelta
import numpy as np
from scipy.stats import poisson
from scipy.optimize import minimize_scalar
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import log_loss

OUTCOMES = ['HOME', 'DRAW', 'AWAY']
FEATURE_VERSION = 'point-in-time-v2'
MODEL_VERSION = 'models-v1.0.0'

def normalize_odds(odds):
    x = np.asarray(odds, dtype=float)
    if x.shape != (3,) or not np.isfinite(x).all() or (x <= 1).any():
        raise ValueError('Three finite decimal odds greater than 1 required')
    implied = 1 / x
    return (implied / implied.sum()).tolist(), float(implied.sum() - 1)

def label(home, away):
    return 0 if home > away else 1 if home == away else 2

def eligible(history, cutoff):
    # Strict inequality also prevents simultaneously starting matches leaking.
    return sorted([r for r in history if r['kickoff'] < cutoff and r['available_at'] < cutoff], key=lambda r: (r['kickoff'], r['id']))

def features(history, home, away, cutoff):
    rows = eligible(history, cutoff)
    ratings = {}
    for r in rows:
        h, a = r['home_id'], r['away_id']
        rh, ra = ratings.get(h, 1500.), ratings.get(a, 1500.)
        expected = 1 / (1 + 10 ** ((ra - rh - 65) / 400))
        actual = 1 if r['home_goals'] > r['away_goals'] else .5 if r['home_goals'] == r['away_goals'] else 0
        ratings[h], ratings[a] = rh + 20 * (actual - expected), ra - 20 * (actual - expected)
    def team(t, venue):
        played = sorted([r for r in rows if t in (r['home_id'], r['away_id'])], key=lambda r: r['kickoff'])
        stats = []
        for r in played:
            ish = r['home_id'] == t
            gf, ga = (r['home_goals'], r['away_goals']) if ish else (r['away_goals'], r['home_goals'])
            stats.append((gf, ga, 3 if gf > ga else 1 if gf == ga else 0, ish))
        result = {'matches': len(stats), 'elo': ratings.get(t, 1500.), 'rest_days': min((cutoff - played[-1]['kickoff']).total_seconds()/86400, 60) if played else None,
                  'congestion_14d': sum(r['kickoff'] > cutoff - timedelta(days=14) for r in played), 'xg': None, 'xga': None, 'shot_quality': None}
        for n in (5, 10, 20):
            last = stats[-n:]
            result[f'form_{n}'] = float(np.mean([x[2] for x in last])) if last else None
        # Shrink sparse goal rates toward explicit priors, never claim these are observations.
        result['goals_for'] = (sum(x[0] for x in stats[-20:]) + 5*1.35)/(min(len(stats),20)+5)
        result['goals_against'] = (sum(x[1] for x in stats[-20:]) + 5*1.35)/(min(len(stats),20)+5)
        venue_rows = [x for x in stats[-20:] if x[3] == venue]
        result['venue_form'] = float(np.mean([x[2] for x in venue_rows])) if venue_rows else None
        weights = np.exp(-.15*np.arange(len(stats[-20:]))[::-1])
        result['ew_form'] = float(np.average([x[2] for x in stats[-20:]], weights=weights)) if stats else None
        opponents=[ratings.get(r['away_id'] if r['home_id']==t else r['home_id'],1500.) for r in played[-20:]]
        result['opponent_strength']=float(np.mean(opponents)) if opponents else None
        result['opponent_adjusted_form']=float(np.mean([s[2]+(o-1500)/400 for s,o in zip(stats[-20:],opponents)])) if stats else None
        result['attack_strength']=result['goals_for']/1.35
        result['defensive_concession_ratio']=result['goals_against']/1.35
        return result
    h, a = team(home, True), team(away, False)
    return {'home': h, 'away': a, 'training_rows': len(rows), 'history_ids': [r['id'] for r in rows], 'prior': {'goal_rate': 1.35, 'pseudo_matches': 5, 'elo': 1500}}

def vector(f):
    keys = ('elo','goals_for','goals_against','form_5','form_10','form_20','ew_form','venue_form','rest_days','congestion_14d','opponent_strength','opponent_adjusted_form','attack_strength','defensive_concession_ratio')
    return [f[t][k] if f[t][k] is not None else np.nan for t in ('home','away') for k in keys]

def poisson_model(f):
    h,a=f['home'],f['away']
    lh = max(.1, min(5., h['goals_for'] * a['goals_against'] / 1.35 * 1.12))
    la = max(.1, min(5., a['goals_for'] * h['goals_against'] / 1.35 / 1.12))
    grid = np.outer(poisson.pmf(np.arange(31),lh), poisson.pmf(np.arange(31),la))
    p=np.array([np.tril(grid,-1).sum(),np.trace(grid),np.triu(grid,1).sum()])
    return (p/p.sum()).tolist()

def elo_model(f):
    win=1/(1+10**((f['away']['elo']-f['home']['elo']-65)/400))
    draw=.28*math.exp(-abs(win-.5))
    return [(1-draw)*win,draw,(1-draw)*(1-win)]

def fit_boosting(history, cutoff, feature_cache=None):
    rows=eligible(history,cutoff)
    if len(rows)<80: return None
    x,y=[],[]
    for r in rows:
        f=feature_cache[r['id']] if feature_cache is not None else features(rows,r['home_id'],r['away_id'],r['kickoff'])
        if min(f['home']['matches'],f['away']['matches'])<3: continue
        x.append(vector(f)); y.append(label(r['home_goals'],r['away_goals']))
    if len(x)<60 or set(y)!={0,1,2}: return None
    model=HistGradientBoostingClassifier(max_iter=50,max_leaf_nodes=7,l2_regularization=5,random_state=7)
    model.fit(x,y)
    return model

def predict(f, boosting=None):
    models={'poisson':poisson_model(f),'elo':elo_model(f)}
    if boosting is not None:
        models['boosting']=boosting.predict_proba([vector(f)])[0].tolist()
    # Ensemble is a candidate only. Never automatically promote on in-sample scores.
    models['ensemble_candidate']=np.mean(list(models.values()),axis=0).tolist()
    return models

def metrics(probabilities, labels):
    if not labels: return {'n':0,'accuracy':None,'brier':None,'log_loss':None,'reliability':[]}
    p=np.asarray(probabilities); y=np.asarray(labels); target=np.eye(3)[y]
    reliability=[]
    for cls in range(3):
        for lo in np.arange(0,1,.1):
            mask=(p[:,cls]>=lo)&(p[:,cls]<(lo+.1) if lo<.9 else p[:,cls]<=1)
            if mask.any(): reliability.append({'outcome':OUTCOMES[cls],'lower':round(float(lo),1),'n':int(mask.sum()),'predicted':float(p[mask,cls].mean()),'observed':float((y[mask]==cls).mean())})
    return {'n':len(y),'accuracy':float((p.argmax(axis=1)==y).mean()),'brier':float(np.mean(np.sum((p-target)**2,axis=1))),'log_loss':float(log_loss(y,p,labels=[0,1,2])),'reliability':reliability}

def walk_forward(history, min_training=40):
    output=[]
    feature_cache={r['id']:features(history,r['home_id'],r['away_id'],r['kickoff']) for r in history}
    available={r['id']:r['available_at'] for r in history}
    for r in sorted(history,key=lambda r:(r['kickoff'],r['id'])):
        past=eligible(history,r['kickoff'])
        if len(past)<min_training: continue
        f=feature_cache[r['id']]
        model=fit_boosting(past,r['kickoff'],feature_cache)
        probabilities=predict(f,model)
        for name in ('poisson','elo','boosting'):
            prior=[v for v in output if name in v['probabilities'] and available[v['match_id']] < r['kickoff']]
            if name in probabilities and len(prior)>=40:
                temperature=fit_temperature([v['probabilities'][name] for v in prior],[v['actual'] for v in prior])
                probabilities[name+'_calibrated']=temperature_scale(probabilities[name],temperature)
        output.append({'match_id':r['id'],'competition':r['competition_id'],'season':r['season'],'kickoff':r['kickoff'].isoformat(), 'actual':label(r['home_goals'],r['away_goals']),'probabilities':probabilities,'training_n':len(past),'confidence':'LOW'})
    return output

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,default=str).encode()).hexdigest()

def settle(outcome,actual,odds,stake=1.):
    return stake*(odds-1) if outcome==actual else -stake


def temperature_scale(probabilities, temperature):
    if not np.isfinite(temperature) or temperature<=0: raise ValueError("Positive temperature required")
    p=np.asarray(probabilities,dtype=float)
    z=np.log(np.clip(p,1e-12,1))/temperature
    z-=np.max(z,axis=-1,keepdims=True)
    scaled=np.exp(z);scaled/=scaled.sum(axis=-1,keepdims=True)
    return scaled.tolist()

def fit_temperature(probabilities, labels):
    if len(labels)<40: raise ValueError("At least 40 prior out-of-sample labels required")
    p=np.asarray(probabilities);y=np.asarray(labels)
    def objective(t):
        q=np.asarray(temperature_scale(p,t))
        return -np.mean(np.log(q[np.arange(len(y)),y]))
    result=minimize_scalar(objective,bounds=(.5,5),method='bounded')
    if not result.success: raise ValueError("Calibration optimization failed")
    return float(result.x)

def fit_reconstructed_boosting(history,cutoff):
    """Train on currently known labels, reconstructing past feature availability.

    Publication times are assumed at +48h for historical training only. Unknown
    labels are filtered with their real recorded availability before this step.
    This is not a certified point-in-time historical evaluation.
    """
    known=eligible(history,cutoff)
    reconstructed=[{**r,'available_at':r['kickoff']+timedelta(days=2)} for r in known]
    return fit_boosting(reconstructed,cutoff)
