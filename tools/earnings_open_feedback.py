"""Original target-level points only; financial answer fields stay protected."""
import math
import re


def project_target_scores(score, questions):
    """Whitelisted Discovery feedback, not a new scorer or target definition."""
    if type(score) is not dict or type(questions) is not str:
        raise ValueError('Original score object and question text required')
    targets = re.findall(r'^### (T[0-9]+) \|', questions, re.M)
    if (len(targets) != 5 or len(set(targets)) != 5
            or any(type(score.get(k)) is not int or score[k] != 5
                   for k in ('target_count', 'prediction_count'))
            or any(type(score.get(k)) is not list or score[k] != []
                   for k in ('duplicate_prediction_ids', 'unknown_prediction_ids'))):
        raise ValueError('Exact five-question complete score denominator required')
    total = score.get('score_out_of_5')
    rows = score.get('per_target')
    if (type(total) not in (int, float) or not math.isfinite(total) or not 0 <= total <= 5
            or type(rows) is not list or len(rows) != 5):
        raise ValueError('Finite complete original target scores required')
    points = {}
    for row in rows:
        if type(row) is not dict:
            raise ValueError('Original target score row required')
        ident, value = row.get('target_id'), row.get('points_awarded')
        if (type(ident) is not str or ident not in targets or ident in points
                or type(value) not in (int, float) or not math.isfinite(value)
                or value not in (0, 0.5, 1)):
            raise ValueError('Unique original target ID and awarded points required')
        points[ident] = value
    if sum(points.values()) != total:
        raise ValueError('Target points must equal the unchanged original total')
    return [{'target_id':ident, 'points_awarded':points[ident]} for ident in targets]
