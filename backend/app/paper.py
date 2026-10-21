"""Explicit research simulation, fixed one virtual unit. No real-money execution."""
from datetime import datetime,timezone
from .db import Session
from .models import Prediction,OddsSnapshot,Match,PaperBet
from .research import normalize_odds

def record(prediction_id, odds_snapshot_id, outcome):
    if outcome not in (0,1,2): raise ValueError('Unknown outcome')
    with Session.begin() as db:
        p=db.get(Prediction,prediction_id);o=db.get(OddsSnapshot,odds_snapshot_id)
        if not p or not o or p.match_id!=o.match_id: raise ValueError('Matching prediction and odds required')
        m=db.get(Match,p.match_id)
        current=datetime.now(timezone.utc).replace(tzinfo=None)
        if current>=m.kickoff or p.generated_at>current:raise ValueError('Paper observation must be registered before kickoff using an existing forecast')
        if o.available_at>p.data_cutoff_time or o.fetched_at>p.generated_at or p.generated_at>=m.kickoff: raise ValueError('Odds unavailable at prediction time')
        probs,_=normalize_odds(o.odds)
        db.add(PaperBet(prediction_id=p.id,odds_snapshot_id=o.id,created_at=datetime.now(timezone.utc).replace(tzinfo=None),outcome=outcome,probability=p.probabilities[outcome],market_probability=probs[outcome],odds=o.odds[outcome],stake=1.))
