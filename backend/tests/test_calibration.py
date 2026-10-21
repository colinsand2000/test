import numpy as np
import pytest
from app.research import temperature_scale,fit_temperature

def test_temperature_normalizes_and_changes_sharpness():
    p=temperature_scale([.8,.1,.1],2)
    assert sum(p)==pytest.approx(1)
    assert .33<p[0]<.8
    assert temperature_scale([.8,.1,.1],1)==pytest.approx([.8,.1,.1])

def test_temperature_fits_on_past_predictions_only():
    probs=[[.98,.01,.01]]*60
    labels=[0,1,2]*20
    temp=fit_temperature(probs,labels)
    assert temp>1
    with pytest.raises(ValueError):fit_temperature(probs[:3],labels[:3])
