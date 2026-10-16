"""Numeric trace/review feedback; never expose scorer labels or raw tool text."""
from copy import deepcopy
import math

from earnings_shadow_measurement import METRICS, SCORE_METRIC, observe, compare
from supervisor_harness import capacity_feedback_engine as engine

REASONS = {'NOT_MEASURED', 'UNKNOWN_EFFECT_SEMANTICS', 'NO_MATCHED_BENEFIT',
           'MECHANICAL_CHECKS_INCOMPLETE_OR_FAILED', 'MATCHED_OPERATIONAL_BENEFIT',
           'MATCHED_PREDICTION_BENEFIT'}
BENEFITS = {'MATCHED_OPERATIONAL_BENEFIT', 'MATCHED_PREDICTION_BENEFIT'}
REVIEW_FIELDS = {'verdict', 'reason', 'metric', 'direction', 'min_delta',
                 'observed_delta', 'score_delta', 'benefit_observed'}


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def validate_diagnostics(value, observation):
    if (type(value) is not dict or set(value) != {'schema', 'execution', 'review'}
            or value['schema'] != 'earnings_research_diagnostics_v1'):
        raise ValueError('Exact label-free diagnostic projection required')
    execution, review = value['execution'], value['review']
    if (type(execution) is not dict or set(execution) != METRICS | {'initial_records', 'score_out_of_5'}
            or any(type(execution[k]) is not int or not 0 <= execution[k] <= 10**12
                   for k in METRICS | {'initial_records'})
            or not 1 <= execution['turns'] <= 24
            or not _number(execution['score_out_of_5']) or not 0 <= execution['score_out_of_5'] <= 5
            or execution['score_out_of_5'] != observation['prediction']['score_out_of_5']
            or observation['execution']['status'] != 'COMPLETED_SCORED'
            or any(execution[k] != observation['execution'].get(k) for k in ('turns', 'tool_calls'))
            or any(execution[k] > execution['tool_calls'] for k in ('repeated_reads', 'rejected_tools'))):
        raise ValueError('Original coherent finite execution diagnostics required')
    if (type(review) is not dict or set(review) != REVIEW_FIELDS
            or type(review['verdict']) is not str or review['verdict'] not in {'continue', 'pending', 'accept', 'reject'}
            or type(review['reason']) is not str or review['reason'] not in REASONS
            or type(review['benefit_observed']) is not bool):
        raise ValueError('Whitelisted review verdict/reason required')
    measured = review['metric'] is not None
    if measured:
        if (type(review['metric']) is not str or review['metric'] not in METRICS | {SCORE_METRIC}
                or type(review['direction']) is not str or review['direction'] not in {'lower', 'higher'}
                or not _number(review['min_delta']) or review['min_delta'] <= 0
                or not _number(review['observed_delta']) or not _number(review['score_delta'])
                or not -5 <= review['score_delta'] <= 5):
            raise ValueError('Exact finite matched effect diagnostics required')
    elif any(review[k] is not None for k in ('direction', 'min_delta', 'observed_delta', 'score_delta')):
        raise ValueError('Unmeasured effect must not invent deltas')
    if (review['benefit_observed'] != (review['reason'] in BENEFITS)
            or (review['benefit_observed'] and (not measured or review['verdict'] != 'accept'))
            or (review['reason'] in {'UNKNOWN_EFFECT_SEMANTICS', 'NOT_MEASURED'} and measured)):
        raise ValueError('Review benefit/measurement scope mismatch')
    reason = review['reason']
    if reason not in {'NOT_MEASURED', *BENEFITS} and review['verdict'] != 'reject':
        raise ValueError('Measured rejection reason cannot describe an accepted or pending candidate')
    if reason in {'NO_MATCHED_BENEFIT', 'MECHANICAL_CHECKS_INCOMPLETE_OR_FAILED'} and not measured:
        raise ValueError('Measured review reason requires actual matched diagnostics')
    if measured:
        if review['metric'] == SCORE_METRIC:
            if (review['direction'] != 'higher' or review['min_delta'] > 5
                    or review['min_delta'] * 2 != int(review['min_delta'] * 2)
                    or review['observed_delta'] != review['score_delta']
                    or reason == 'MATCHED_OPERATIONAL_BENEFIT'):
                raise ValueError('Prediction feedback must use the actual original-score difference')
        elif reason == 'MATCHED_PREDICTION_BENEFIT':
            raise ValueError('Prediction benefit cannot name an operational proxy')
        named = review['observed_delta'] <= -review['min_delta'] if review['direction'] == 'lower' else review['observed_delta'] >= review['min_delta']
        improved = named and review['score_delta'] >= 0
        if ((reason in BENEFITS and not improved)
                or (reason == 'NO_MATCHED_BENEFIT' and improved)):
            raise ValueError('Review reason differs from recomputed metric and score deltas')
    return deepcopy(value)


def project_diagnostics(output, observation):
    execution = observe(output)
    review = dict.fromkeys(REVIEW_FIELDS)
    review.update(verdict=output['capacity_review'], reason='NOT_MEASURED', benefit_observed=False)
    effect = output.get('effect_review')
    if effect is not None:
        engine.driver._artifacts(effect)
        receipt = engine.read(effect['review_receipt'])['review']
        if receipt['decision'] != review['verdict']:
            raise ValueError('Actual review differs from downstream selection')
        review.update(reason=receipt['reason'], benefit_observed=receipt['benefit_observed'])
        if effect['comparison'] is not None:
            measured = engine.read(effect['comparison'])
            recomputed = compare(measured['originals']['parent'], measured['originals']['child'],
                                 declaration=measured['declaration'])
            if any(measured.get(k) != v for k, v in recomputed.items()):
                raise ValueError('Effect feedback differs from retained matched originals')
            criterion = measured['declaration']
            review.update(metric=criterion['metric'], direction=criterion['direction'], min_delta=criterion['min_delta'],
                          observed_delta=measured['delta'][criterion['metric']], score_delta=measured['score_delta'])
    return validate_diagnostics({'schema': 'earnings_research_diagnostics_v1',
                                'execution': execution, 'review': review}, observation)
