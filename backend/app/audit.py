"""Reproduce a stored forecast from archived code and exact input snapshot."""
import argparse,runpy
from datetime import datetime
from pathlib import Path
import numpy as np
from .db import Session
from .models import Prediction
from .research import digest

def reproduce(ident):
    with Session() as db:
        p=db.get(Prediction,ident)
        if not p:raise ValueError('Prediction not found')
        snapshot=p.snapshot
        if 'code_sha256' not in snapshot:raise ValueError('Legacy forecast has no code archive')
        path=Path('artifacts/code')/snapshot['code_sha256']/'research.py'
        if digest(path.read_text())!=snapshot['code_sha256']:raise ValueError('Archived code checksum mismatch')
        if (path.parent/'requirements.lock').read_text()!=Path('requirements.lock').read_text():raise ValueError('Recreate archived dependency versions first')
        namespace=runpy.run_path(str(path))
        h=[{**r,'kickoff':datetime.fromisoformat(r['kickoff']),'available_at':datetime.fromisoformat(r['available_at'])} for r in snapshot['history']]
        from .models import Match
        m=db.get(Match,p.match_id)
        reference=datetime.fromisoformat(snapshot['feature_reference_time']) if snapshot.get('feature_reference_time') else p.data_cutoff_time
        f=namespace['features'](h,m.home_id,m.away_id,reference)
        assert f==snapshot['features'],'Feature snapshot differs'
        fit=namespace['fit_reconstructed_boosting'] if snapshot.get('boosting_training_protocol')=='retrospective-assumed-48h' else namespace['fit_boosting']
        models=namespace['predict'](f,fit(h,p.data_cutoff_time))
        for name,values in snapshot['models'].items():
            np.testing.assert_allclose(models[name],values,rtol=1e-10,atol=1e-10)
        np.testing.assert_allclose(models['poisson'],p.probabilities,rtol=1e-10,atol=1e-10)
        return {'prediction_id':ident,'verified':True,'models':list(models),'code_sha256':snapshot['code_sha256']}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--prediction-id',type=int,required=True);a=parser.parse_args();print(reproduce(a.prediction_id))
