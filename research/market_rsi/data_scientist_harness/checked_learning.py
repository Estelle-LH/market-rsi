"""The unchanged four trainers behind fresh raw/feature/normalized checks.

Legacy historical_grid_learning remains untouched for frozen runs. Only the
new entry point invokes this module; parity tests must compare all predictions.
"""
from dataclasses import replace
from pathlib import Path
import copy
import time
import warnings
import importlib.metadata
import numpy as np
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import ElasticNet, Ridge

from historical_grid_learning import validate_plan, weights
from historical_delta_evaluation import score_delta
from materialize_selected_grid_objective import prior_day_label_mask
from market_rsi import digest
from data_scientist_harness import sanity


def evaluate(inputs, plan, experiment, contract, path):
    started = time.monotonic()
    validate_plan(plan, inputs)
    raw = sanity.raw_panel(inputs, contract)
    identity = {name:[name] for name in inputs["names"]}

    def derive_checked(checked):
        local = {**inputs, "x": {**inputs["x"], "values": checked["values"]}}
        features = sanity.derived_panel(local, plan, experiment, contract)
        return sanity.guard(raw=raw, transformed=features, c=contract,
            lineage_map={f["name"]:sanity.lineage(f) for f in plan["features"]},
            path=path/"features", stage="fit",
            operation=lambda batch: fit_normalizer(local, features, batch))[0]

    def fit_normalizer(local, features, checked):
        x, y = local["x"], local["y"]; matrix = checked["values"]; n = len(x["row_id"])
        check = np.isin(x['date'],plan['check_utc_dates'])
        train = np.isin(x['date'],plan['train_utc_dates'])
        first_check = int(x['decision_ms'][check].min())
        causal = prior_day_label_mask(x['decision_ms'],y['label_available_ms'],y['available'],first_check)
        whole_market = ~np.isin(x['market'],np.unique(x['market'][check]))
        finite = np.all(np.isfinite(matrix),axis=1)
        model_supported = np.ones(n,dtype=bool) if plan['missing_input_action']=='native_nan' else finite
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
        normalized = copy.deepcopy(features)
        normalized.batch['values'] = transformed
        # Limits after scaling are separately declared, never copied as if the
        # raw-unit limits applied to standardized values.
        normalized = replace(normalized, spec=replace(normalized.spec,
            units=experiment['normalized_units'],
            rules=sanity.rules(experiment['normalized_rules'],checked['feature_names'])),
            observed={**normalized.observed, 'units':experiment['normalized_units']})

        def fit_model(batch):
            actual = batch['values']
            method = plan['model']['algorithm']; parameters = plan['model']['parameters']
            if method == 'ridge': estimator = Ridge(**parameters, solver='svd')
            elif method == 'elastic_net': estimator = ElasticNet(**parameters, random_state=23, selection='cyclic')
            elif method == 'random_forest': estimator = RandomForestRegressor(**parameters,random_state=23,n_jobs=1)
            else: estimator = HistGradientBoostingRegressor(**parameters,random_state=23,early_stopping=False)
            with warnings.catch_warnings(record=True) as fit_warnings:
                warnings.simplefilter('always')
                estimator.fit(actual[fit],y['delta_probability'][fit],sample_weight=w)

            def predict_score(scoring):
                prediction = np.full(n,np.nan); prediction[check] = 0.
                model_rows = check & model_supported
                prediction[model_rows] = estimator.predict(scoring['values'][model_rows])
                if plan['output_transform'] == 'clip_to_probability_delta_bounds':
                    mid = x['values'][:,local['names'].index('polymarket_ticks_ms.midpoint_from_reported_bbo')]
                    supported = check & np.isfinite(mid)
                    prediction[supported] = np.clip(prediction[supported],-mid[supported],1-mid[supported])
                def score(mask):
                    return score_delta(y['delta_probability'][mask],prediction[mask],
                        label_available=y['available'][mask],dates=x['date'][mask],groups=x['market'][mask],
                        aggregation=plan['score_aggregation'])
                report = {'schema':'historical_open_train_model_diagnostic_v1',
                    'plan_sha256':digest(plan),'objective_sha256':local['objective']['proposal_sha256'],
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
                    'fit_warnings':[{'category':v.category.__name__,'message':str(v.message)} for v in fit_warnings],
                    'elapsed_seconds':time.monotonic()-started,
                    'runtime_packages':{name:importlib.metadata.version(name) for name in ['numpy','scipy','scikit-learn']},
                    'seed':23,'fresh_holdout':False,'dev_test_opened':False,'profitability_evidence':False,
                    'claim':'one explicit fit/later-check diagnostic within already-open Train; not RSI promotion',
                    'parameters_explicit_in_plan':True,'model_weights_persisted':False}
                return report, {'row_id':x['row_id'],'check':check,'fit':fit,'prediction_delta_probability':prediction,
                    'check_model_prediction':model_rows}
            return sanity.guard(raw=features, transformed=normalized, c=contract,
                lineage_map={feature_name:[feature_name] for feature_name in checked['feature_names']},path=path/'score',stage='score',
                operation=predict_score)[0]
        return sanity.guard(raw=features, transformed=normalized, c=contract,
            lineage_map={feature_name:[feature_name] for feature_name in checked['feature_names']},path=path/'normalized',stage='fit',
            operation=fit_model)[0]
    return sanity.guard(raw=raw, transformed=raw, c=contract,lineage_map=identity,
        path=path/'raw',stage='fit',operation=derive_checked)[0]
