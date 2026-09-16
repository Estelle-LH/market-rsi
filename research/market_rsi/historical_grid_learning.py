"""Bounded, explicit-config learning diagnostics on already-open historical Train.

The researcher supplies features, models, parameters, dates and weighting.
This is NOT the prospective Dev runner or evidence of profitable trading.
"""
from pathlib import Path
import importlib.metadata
import time
import warnings
import zipfile

import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import ElasticNet, Ridge
from sklearn.preprocessing import StandardScaler

from historical_delta_evaluation import score_delta
from historical_recorded_features import derive, validate_feature
from historical_trade_windows import RecordedTradeWindows, load_audited_index
from historical_ingest_controller import _signed
from market_rsi import digest, file_hash, identifier, load_json
from materialize_selected_grid_objective import prior_day_label_mask


MODEL_FIELDS = {
    'ridge': {'alpha', 'fit_intercept'},
    'elastic_net': {'alpha', 'l1_ratio', 'fit_intercept', 'max_iter', 'tol'},
    'random_forest': {'n_estimators', 'max_depth', 'min_samples_leaf', 'max_features'},
    'hist_gradient_boosting': {'learning_rate', 'max_iter', 'max_leaf_nodes',
                              'l2_regularization', 'min_samples_leaf'},
}
PLAN_FIELDS = {'features', 'model', 'normalizer', 'train_utc_dates', 'check_utc_dates',
               'train_weighting', 'score_aggregation', 'missing_input_action',
               'output_transform', 'seed', 'rationale'}


def numeric(value, low, high, *, integer=False):
    if type(value) not in ((int,) if integer else (int, float)) or not low <= value <= high:
        raise ValueError('explicit numeric hyperparameter outside bounded supported range')


def validate_model(model):
    if not isinstance(model, dict) or set(model) != {'algorithm', 'parameters'}:
        raise ValueError('plan.model must be an object with EXACT keys algorithm and parameters: '
                         '{"algorithm": "<library algorithm>", "parameters": {"<each required parameter>": "<chosen value>"}}. '
                         'Do not use name/type/params aliases or place parameters at the top level. '
                         'inspect_learning_library returns model_schema and parameter keys for every algorithm.')
    name, p = model['algorithm'], model['parameters']
    if name not in MODEL_FIELDS or not isinstance(p, dict) or set(p) != MODEL_FIELDS[name]:
        required=sorted(MODEL_FIELDS.get(name,set()))
        raise ValueError('Unsupported algorithm or incorrect plan.model.parameters keys. '
                         f'For algorithm {name!r}, required keys are {required}; no silent defaults.')
    if name in {'ridge', 'elastic_net'}:
        numeric(p['alpha'], 0, 1e6)
        if type(p['fit_intercept']) is not bool: raise ValueError('explicit fit_intercept boolean required')
    if name == 'elastic_net':
        numeric(p['l1_ratio'], 0, 1); numeric(p['max_iter'], 1, 10000, integer=True); numeric(p['tol'], 1e-12, 1)
    if name == 'random_forest':
        numeric(p['n_estimators'], 1, 128, integer=True); numeric(p['max_depth'], 1, 12, integer=True)
        numeric(p['min_samples_leaf'], 1, 10000, integer=True); numeric(p['max_features'], 1e-6, 1)
    if name == 'hist_gradient_boosting':
        numeric(p['learning_rate'], 1e-6, 1); numeric(p['max_iter'], 1, 256, integer=True)
        numeric(p['max_leaf_nodes'], 2, 64, integer=True)
        numeric(p['l2_regularization'], 0, 1e6); numeric(p['min_samples_leaf'], 1, 10000, integer=True)
    return model


def bounded_npz(path, expected):
    with zipfile.ZipFile(path) as archive:
        if (len(archive.namelist()) != len(expected) or set(archive.namelist()) != {k+'.npy' for k in expected}
                or sum(item.file_size for item in archive.infolist()) > 300000000):
            raise ValueError('bounded numeric input archive required')
    with np.load(path, allow_pickle=False) as archive:
        return {key: archive[key] for key in expected}


def read_inputs(root):
    source = load_json(root/'input-result.json'); _signed(source, 'result_sha256')
    labels = load_json(root/'label-result.json'); _signed(labels, 'result_sha256')
    panel = load_json(root/'panel-result.json'); _signed(panel, 'result_sha256')
    objective = load_json(root/'objective-proposal.json'); _signed(objective, 'proposal_sha256')
    data = load_json(root/'data-use-proposal.json'); _signed(data, 'proposal_sha256')
    query = labels['primary_query_id']; identifier(query)
    if (source.get('complete') is not True or source.get('labels_present') is not False
            or labels.get('complete') is not True or labels.get('training_admitted') is not False
            or any(value.get('fresh_holdout') is not False for value in [source, labels, panel])
            or source['panel_sha256'] != labels['panel_sha256'] or source['panel_sha256'] != panel['panel_sha256']
            or labels['proposal_sha256'] != objective['proposal_sha256']
            or objective.get('primary_metric') != 'mse_skill_vs_persistence'
            or query != objective['primary_query_id']
            or labels['queries'][query]['spec'] != objective['queries'][query]['spec']
            or file_hash(root/'current-inputs.npz') != source['archive_sha256']
            or file_hash(root/'primary-labels.npz') != labels['queries'][query]['archive_sha256']):
        raise ValueError('exact completed open-Train input/label/objective lineage required')
    x = bounded_npz(root/'current-inputs.npz', {'row_id','entity','decision_ms','date','field_names','values'})
    y = bounded_npz(root/'primary-labels.npz', {'row_id','decision_ms','delta_probability',
        'delta_probability_bps','label_available_ms','available','future_observation_count','reason'})
    n = len(x['row_id']); names = x['field_names'].tolist()
    if (not 0 < n <= 500000 or n != source['rows'] or n != labels['queries'][query]['rows']
            or any(x[k].shape != (n,) for k in ['row_id','entity','decision_ms','date'])
            or any(y[k].shape != (n,) for k in y)
            or not np.issubdtype(x['decision_ms'].dtype,np.signedinteger)
            or y['available'].dtype != np.dtype(bool)
            or x['values'].shape != (n, len(names)) or names != source['field_names']
            or len(set(x['row_id'])) != n or not np.array_equal(x['row_id'], y['row_id'])
            or not np.array_equal(x['decision_ms'], y['decision_ms'])
            or not np.array_equal(y['available'], np.isfinite(y['delta_probability']))
            or not np.array_equal(y['label_available_ms'], x['decision_ms']+labels['queries'][query]['spec']['window_end_ms'])
            or not np.array_equal(y['delta_probability_bps'], y['delta_probability']*10000, equal_nan=True)
            or np.any(np.isinf(x['values']))):
        raise ValueError('exact aligned finite/missing research row schema required')
    if set(x['date']) != set(data['plan']['open_train_utc_dates']):
        raise ValueError('opened Train dates changed')
    if not np.array_equal(x['decision_ms'].astype('datetime64[ms]').astype('datetime64[D]').astype(str),x['date']):
        raise ValueError('dates must derive from actual UTC observation epochs')
    mapping = {v['entity_code']: v['market_slug'] for v in panel['summary']['entity_mapping']}
    if any(int(e) not in mapping for e in x['entity']): raise ValueError('missing whole-market group identity')
    x['market'] = np.array([mapping[int(e)] for e in x['entity']])
    result = {'x': x, 'y': y, 'names': names, 'cadence_ms': data['plan']['cadence_ms'],
              'objective': objective, 'input_result': source, 'label_result': labels}
    if (root/'recorded-trades').exists():
        events, dates, binding = load_audited_index(root/'recorded-trades', root/'recorded-trades/audit/audit.json')
        if dates != sorted(set(x['date'])):
            raise ValueError('recorded-event dates differ from already-open input dates')
        result['recorded_events'] = RecordedTradeWindows(events, dates)
        result['recorded_event_binding'] = binding
    return result


def validate_plan(plan, inputs):
    if not isinstance(plan, dict) or set(plan) != PLAN_FIELDS:
        raise ValueError('complete explicit learning plan required; no hidden parameters')
    features = plan['features']
    if not isinstance(features, list) or not 1 <= len(features) <= 24:
        raise ValueError('one to24 explicit feature specifications required')
    for feature in features: validate_feature(feature, inputs['names'], inputs['cadence_ms'])
    if len({f['name'] for f in features}) != len(features): raise ValueError('feature names must be unique')
    validate_model(plan['model'])
    dates = sorted(set(inputs['x']['date']))
    train, check = plan['train_utc_dates'], plan['check_utc_dates']
    if (not isinstance(train, list) or not isinstance(check, list) or not train or not check
            or train != sorted(set(train)) or check != sorted(set(check))
            or max(train) >= min(check) or sorted(train+check) != dates):
        raise ValueError('explicit earlier Train/later check partition of all opened dates required')
    if not isinstance(plan['rationale'], str) or not plan['rationale'].strip():
        raise ValueError('plan.rationale must be a nonempty explanation of your choices; empty text is invalid')
    if (plan['normalizer'] not in {'none','fit_mean_std'}
            or plan['train_weighting'] not in {'equal_row','equal_day','equal_market'}
            or plan['score_aggregation'] not in {'equal_row','equal_day','equal_group'}
            or plan['missing_input_action'] not in {'persistence','native_nan'}
            or plan['output_transform'] not in {'none','clip_to_probability_delta_bounds'}
            or type(plan['seed']) is not int or plan['seed'] != 23):
        raise ValueError('explicit implemented normalization/weights/missing/output choices and fixed seed23 required')
    if plan['missing_input_action']=='native_nan' and (
            plan['model']['algorithm']!='hist_gradient_boosting' or plan['normalizer']!='none'):
        raise ValueError('native_nan currently requires hist_gradient_boosting and normalizer="none"; '
                         'NaNs go unchanged into the estimator, never imputed')
    return plan


def weights(keys):
    _, inverse, counts = np.unique(keys, return_inverse=True, return_counts=True)
    w = 1/counts[inverse].astype(float)
    return w/w.mean()


def evaluate(inputs, plan):
    started=time.monotonic()
    validate_plan(plan, inputs)
    x, y = inputs['x'], inputs['y']; n = len(x['row_id'])
    matrix = np.column_stack([derive(x['entity'],x['decision_ms'],x['values'],inputs['names'],
        spec=feature,cadence_ms=inputs['cadence_ms'],recorded_events=inputs.get('recorded_events'))['values'] for feature in plan['features']])
    check = np.isin(x['date'],plan['check_utc_dates'])
    train = np.isin(x['date'],plan['train_utc_dates'])
    # Actual UTC day boundary, not first visible quote later that day.
    first_check = int(x['decision_ms'][check].min())
    causal = prior_day_label_mask(x['decision_ms'],y['label_available_ms'],y['available'],first_check)
    whole_market = ~np.isin(x['market'],np.unique(x['market'][check]))
    finite = np.all(np.isfinite(matrix),axis=1)
    native_nan = plan['missing_input_action']=='native_nan'
    model_supported = np.ones(n,dtype=bool) if native_nan else finite
    fit = train & causal & whole_market & model_supported
    if int(fit.sum()) < max(3,matrix.shape[1]+1):
        raise ValueError('insufficient causally available complete Train rows; no fallback fit')
    if not np.any(check & y['available']): raise ValueError('no covered opened-Train check labels')
    w = np.ones(int(fit.sum()))
    if plan['train_weighting'] == 'equal_day': w = weights(x['date'][fit])
    elif plan['train_weighting'] == 'equal_market': w = weights(x['market'][fit])
    transformed = matrix.copy(); normalizer = None
    if plan['normalizer'] == 'fit_mean_std':
        normalizer = StandardScaler().fit(matrix[fit],sample_weight=w)
        transformed[finite] = normalizer.transform(matrix[finite])
    method = plan['model']['algorithm']; parameters = plan['model']['parameters']
    if method == 'ridge': estimator = Ridge(**parameters, solver='svd')
    elif method == 'elastic_net': estimator = ElasticNet(**parameters, random_state=23, selection='cyclic')
    elif method == 'random_forest': estimator = RandomForestRegressor(**parameters,random_state=23,n_jobs=1)
    else: estimator = HistGradientBoostingRegressor(**parameters,random_state=23,early_stopping=False)
    with warnings.catch_warnings(record=True) as fit_warnings:
        warnings.simplefilter('always')
        estimator.fit(transformed[fit],y['delta_probability'][fit],sample_weight=w)
    prediction = np.full(n,np.nan)
    prediction[check] = 0.  # Declared persistence fallback, NOT an imputed source value.
    model_rows = check & model_supported
    prediction[model_rows] = estimator.predict(transformed[model_rows])
    if plan['output_transform'] == 'clip_to_probability_delta_bounds':
        mid = x['values'][:,inputs['names'].index('polymarket_ticks_ms.midpoint_from_reported_bbo')]
        supported = check & np.isfinite(mid)
        prediction[supported] = np.clip(prediction[supported],-mid[supported],1-mid[supported])
    def score(mask):
        return score_delta(y['delta_probability'][mask],prediction[mask],
            label_available=y['available'][mask],dates=x['date'][mask],groups=x['market'][mask],
            aggregation=plan['score_aggregation'])
    report = {'schema':'historical_open_train_model_diagnostic_v1',
        'plan_sha256':digest(plan),'objective_sha256':inputs['objective']['proposal_sha256'],
        'score':score(check),'by_check_date':{d:score(check & (x['date']==d)) for d in plan['check_utc_dates']},
        'fit_rows':int(fit.sum()),'check_population_rows':int(check.sum()),
        'check_model_prediction_rows':int(model_rows.sum()),'check_persistence_fallback_rows':int((check & ~model_supported).sum()),
        'fit_rows_with_missing_inputs':int((fit & ~finite).sum()),
        'check_model_rows_with_missing_inputs':int((model_rows & ~finite).sum()),
        'missing_input_handling':plan['missing_input_action'],'source_values_imputed':False,
        'train_label_or_day_purged_rows':int((train & ~causal).sum()),
        'train_cross_check_market_rows':int((train & ~whole_market).sum()),
        'train_missing_input_rows':int((train & ~finite).sum()),
        'last_fit_label_available_ms':int(y['label_available_ms'][fit].max()),
        'first_check_day_ms':first_check//86400000*86400000,
        'normalizer_fit_only':True,'normalizer_mean':normalizer.mean_.tolist() if normalizer else None,
        'normalizer_scale':normalizer.scale_.tolist() if normalizer else None,
        'learned_coefficients':estimator.coef_.tolist() if hasattr(estimator,'coef_') else None,
        'effective_estimator_parameters':estimator.get_params(deep=False),
        'fit_warnings':[{'category':w.category.__name__,'message':str(w.message)} for w in fit_warnings],
        'elapsed_seconds':time.monotonic()-started,
        'runtime_packages':{name:importlib.metadata.version(name) for name in ['numpy','scipy','scikit-learn']},
        'seed':23,'fresh_holdout':False,'dev_test_opened':False,'profitability_evidence':False,
        'claim':'one explicit fit/later-check diagnostic within already-open Train; not RSI promotion',
        'parameters_explicit_in_plan':True,'model_weights_persisted':False}
    return report, {'row_id':x['row_id'],'check':check,'fit':fit,'prediction_delta_probability':prediction,
                    'check_model_prediction':model_rows}
