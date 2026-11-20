"""Calculate BMI from measurements provided for this request only."""

import math


def calculate_bmi(height_cm, weight_kg):
    """Return a BMI estimate without storing measurements or classifying health.

    Height is in centimetres and weight is in kilograms. Reject missing,
    non-finite and implausible measurements rather than returning nonsense.
    """
    try:
        if isinstance(height_cm, bool) or isinstance(weight_kg, bool):
            raise ValueError
        height = float(height_cm)
        weight = float(weight_kg)
        if not math.isfinite(height) or not math.isfinite(weight):
            raise ValueError
        if not 30 <= height <= 300 or not 2 <= weight <= 500:
            raise ValueError
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError('Please provide a valid height in cm and weight in kg.') from exc

    return {
        'height_cm': height,
        'weight_kg': weight,
        'bmi': round(weight / (height / 100) ** 2, 1),
        'note': ('BMI is a rough screening measure, not a diagnosis. It does not '
                 'measure body fat or account for differences such as muscle mass; '
                 'interpretation depends on age and other factors. These measurements '
                 'are used only for this request and are not saved by DayFlow.'),
    }
