import math

import pytest

from dayflow_profile import calculate_bmi


def test_bmi_from_metric_measurements():
    result = calculate_bmi(170, 60)
    assert result['bmi'] == 20.8
    assert result['height_cm'] == 170 and result['weight_kg'] == 60
    assert 'not a diagnosis' in result['note']
    assert 'not saved' in result['note']


@pytest.mark.parametrize('height, weight', [
    (None, 60), (0, 60), (170, 0), (math.nan, 60),
    (170, math.inf), (True, 60), (170, -1), ('bad', 60),
])
def test_invalid_measurements_rejected(height, weight):
    with pytest.raises(ValueError):
        calculate_bmi(height, weight)
