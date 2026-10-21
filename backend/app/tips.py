"""Explainable informational shortlist. Never a guarantee or stake instruction."""
from datetime import timedelta
import math
from .research import normalize_odds,OUTCOMES
POLICY_VERSION='informational-v1.0.1'

def build_tip(prediction,match,at):
    s=prediction.snapshot;f=s['features'];models=s['models']
    probs=prediction.probabilities
    if len(probs)!=3 or any(not math.isfinite(x) or x<0 for x in probs) or abs(sum(probs)-1)>1e-6:raise ValueError('Invalid model probability vector')
    pick=max(range(3),key=lambda i:probs[i]);second=sorted(probs)[-2]
    votes=sum(max(range(3),key=lambda i:p[i])==pick for name,p in models.items() if name!='ensemble_candidate')
    histories=s['history'];fresh={}
    reasons=[];blocks=[]
    if min(f['home']['matches'],f['away']['matches'])<8:blocks.append('För få tidigare matcher: minst åtta per lag krävs för en kandidat.')
    for side,team in [('home',match.home_id),('away',match.away_id)]:
        played=[r for r in histories if team in (r['home_id'],r['away_id'])]
        from datetime import datetime
        age=(at-max(datetime.fromisoformat(r['kickoff']) for r in played)).total_seconds()/86400 if played else None
        fresh[side]=round(age,1) if age is not None else None
        if age is None or age>35:blocks.append(f"{'Hemmalagets' if side=='home' else 'Bortalagets'} senaste resultat saknas eller är äldre än 35 dagar.")
    if probs[pick]<.52:blocks.append('Inget utfall har minst 52 % modellsannolikhet.')
    if probs[pick]-second<.12:blocks.append('För liten skillnad mellan de två troligaste utfallen.')
    if votes<2:blocks.append('Basmodellerna ger inte tillräckligt samstämmiga förstaval.')
    model_probs=[p[pick] for name,p in models.items() if name!='ensemble_candidate']
    dispersion=max(model_probs)-min(model_probs) if model_probs else 1.
    if dispersion>.25:blocks.append('Modellernas sannolikheter skiljer sig med mer än 25 procentenheter.')
    if s.get('incomplete_recent_results'):blocks.append('Resultat saknas för minst en nyligen schemalagd match för något av lagen. Underlaget kan vara ofullständigt.')
    if match.kickoff<=at:blocks.append('Matchen har redan börjat.')
    if (at-prediction.generated_at)>timedelta(hours=36):blocks.append('Prognosen är äldre än 36 timmar.')
    for title,key in [('Lagstyrka (Elo)','elo'),('Senaste fem matcherna, poäng/match','form_5'),('Målproduktion, priorjusterad','goals_for'),('Insläppta mål, priorjusterade','goals_against'),('Vila inför avspark, dagar','rest_days')]:
        reasons.append({'factor':title,'home':f['home'].get(key),'away':f['away'].get(key)})
    decision='ABSTAIN' if blocks else 'CANDIDATE'
    return {'decision':decision,'outcome':OUTCOMES[pick],'outcome_index':pick,'probability':probs[pick],'probability_gap':probs[pick]-second,'model_votes':votes,'model_dispersion':dispersion,'base_models':len([k for k in models if k!='ensemble_candidate']),'confidence':'LOW','calibration':'Inte oberoende validerad för nya prognoser','data_quality':'LOW','reasons':reasons,'blocks':blocks,'latest_result_age_days':fresh,'missing':s.get('missing',[]),'policy_version':POLICY_VERSION,'note':'Statistisk kandidat för granskning, inte belägg för lönsamhet. Odds och verifierad kalibrering krävs innan en fördel kan bedömas.','home':match.home_id,'away':match.away_id,'competition':match.competition_id,'kickoff':match.kickoff.isoformat()+'Z'}

def odds_comparison(probabilities,odds):
    market,margin=normalize_odds(odds)
    return {'market_probabilities':market,'overround':margin,'break_even_probabilities':[1/x for x in odds],'probability_differences':[p-m for p,m in zip(probabilities,market)],'model_expected_return':[p*x-1 for p,x in zip(probabilities,odds)],'interpretation':'Beräknat modellövertag, inte verifierad förväntad vinst; modellfel och oddsens ålder kan eliminera skillnaden.'}
