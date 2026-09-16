"""Independent, additive arithmetic audit of the exact completed GLM queries.

Does not replace the controller decision, mutate its profiles, change a query
spec, fit a model or call a provider. Keeps original source and results intact.
"""
import argparse
import importlib.util
import math
from pathlib import Path
import statistics
import sys

import numpy as np

from historical_grid_objective_controller import assess_activity, read_panel
from historical_grid_objectives import targets, profile
from market_rsi import canonical, digest, file_hash, fresh_json, identifier, load_json


def scalar_target(panel,spec,index,lookup):
    current=panel.midpoint[index]
    offsets=range(spec['window_start_ms'],spec['window_end_ms']+1,panel.cadence_ms)
    values=[];weights=[]
    for offset in offsets:
        other=lookup.get((int(panel.entity[index]),int(panel.time_ms[index])+offset))
        if (other is not None and np.isfinite(panel.midpoint[other])
                and panel.quote_age_ms[other]<=spec['label_max_age_ms']):
            values.append(float(panel.midpoint[other])-float(current))
            weights.append(2**((offset-spec['window_end_ms'])/spec['half_life_ms'])
                if spec['family']=='forward_ewma_delta' else 1.)
    required=max(spec['minimum_observations'],math.ceil(len(offsets)*spec['minimum_window_coverage']))
    if not np.isfinite(current) or len(values)<required:return None
    if spec['family']=='forward_median_delta':return statistics.median(values)
    return math.fsum(v*w for v,w in zip(values,weights))/math.fsum(weights)


def run(controller,output):
    identifier(output.name);root=controller/'workspace'
    assessment=load_json(controller/'session/assessment.json')
    if assessment.get('valid') is not True or assessment.get('process_reaped') is not True or not assess_activity(root)['valid']:
        raise ValueError('complete valid original controller required')
    preparation=load_json(controller/'preparation.json');old_path=controller/'source-snapshot/historical_grid_objectives.py'
    if file_hash(old_path)!=preparation['source_hashes']['historical_grid_objectives.py']:
        raise ValueError('exact original engine snapshot required')
    name='historical_objective_original_forensic_snapshot'
    spec=importlib.util.spec_from_file_location(name,old_path);old=importlib.util.module_from_spec(spec)
    sys.modules[name]=old;spec.loader.exec_module(old)
    panel,ids,panel_result=read_panel(root)
    lookup={(int(e),int(t)):i for i,(e,t) in enumerate(zip(panel.entity,panel.time_ms))}
    paths=[controller/'session/assessment.json',root/'workspace.json',root/'objective-activity.jsonl',
        root/'frozen-grid-objective-proposal.json',root/'submitted-grid-objective-decision.json',old_path]
    queries=sorted((root/'queries').glob('*/result.json'))
    paths += [item for q in queries for item in [q,q.with_name('query.json')]]
    before={str(path):file_hash(path) for path in paths}
    output.mkdir(parents=True,exist_ok=False,mode=0o700)
    engine=Path(__file__).with_name('historical_grid_objectives.py')
    claim={'old_engine_sha256':file_hash(old_path),'new_engine_sha256':file_hash(engine),'auditor_sha256':file_hash(__file__),
        'input_hashes':before,'panel_sha256':panel_result['panel_sha256'],
        'change':'centre future values on current quote before aggregation; no epsilon threshold/deadband',
        'same_queries_only':True,'new_model_calls':0,'original_controller_unchanged':True}
    fresh_json(output/'claim.json',claim)
    reports=[]
    for path in queries:
        saved=load_json(path);objective=saved['profile']['spec']
        previous=old.targets(panel,objective)
        if digest(old.profile(panel,objective))!=digest(saved['profile']):raise ValueError('original profile does not exactly reproduce')
        updated=targets(panel,objective);updated_profile=profile(panel,objective)
        np.testing.assert_array_equal(previous['available'],updated['available'])
        np.testing.assert_array_equal(previous['reason'],updated['reason'])
        np.testing.assert_array_equal(previous['label_available_ms'],updated['label_available_ms'])
        np.testing.assert_allclose(previous['delta_probability'],updated['delta_probability'],rtol=1e-12,atol=1e-14,equal_nan=True)
        indices=set(np.linspace(0,len(ids)-1,64,dtype=int).tolist())
        for phase in set(panel.phase):indices.add(int(np.flatnonzero(panel.phase==phase)[0]))
        invented=np.flatnonzero((previous['delta_probability']!=0)&updated['all_observed_future_quotes_equal_current'])
        indices.update(invented[:3].tolist())
        for index in sorted(indices):
            scalar=scalar_target(panel,objective,index,lookup);vector=updated['delta_probability'][index]
            if scalar is None:
                if not np.isnan(vector):raise ValueError('scalar missingness disagrees')
            elif not math.isclose(scalar,float(vector),rel_tol=1e-12,abs_tol=1e-14):raise ValueError('independent scalar target disagrees')
        corrections={'query_id':saved['query_id'],'spec_unchanged':objective,'original_profile_sha256':file_hash(path),
            'original_profile':saved['profile'],'corrected_profile':updated_profile,
            'constant_future_paths_with_original_nonzero_delta':len(invented),
            'constant_path_examples':[{'row_id':str(ids[i]),'current_quote':float(panel.midpoint[i]),
                'old_delta':float(previous['delta_probability'][i]),'corrected_delta':float(updated['delta_probability'][i])} for i in invented[:3]],
            'all_row_coverage_reasons_times_unchanged':True,'old_profile_reproduced_exactly':True,
            'independent_scalar_checks':len(indices),
            'max_absolute_delta_difference':float(np.nanmax(np.abs(previous['delta_probability']-updated['delta_probability'])))}
        corrections['correction_sha256']=digest(corrections)
        fresh_json(output/(saved['query_id']+'.json'),corrections);reports.append(corrections)
    if before!={str(path):file_hash(path) for path in paths} or file_hash(engine)!=claim['new_engine_sha256']:
        raise ValueError('original evidence or repaired engine changed during audit')
    selected=load_json(root/'frozen-grid-objective-proposal.json')
    final={'schema':'historical_objective_numerical_correction_v1','audit_pass':True,'queries':len(reports),
        'proposal_sha256':selected['proposal_sha256'],'selected_primary_query_id':selected['primary_query_id'],
        'corrections':[{k:r[k] for k in ['query_id','correction_sha256','constant_future_paths_with_original_nonzero_delta',
            'all_row_coverage_reasons_times_unchanged','independent_scalar_checks','max_absolute_delta_difference']} for r in reports],
        'original_controller_harness_valid':True,'original_scientific_choice_requires_corrected_feedback_review':True,
        'reporting_corrections':[
            'q-point-5m actually specifies600000ms, which is10minutes; its identifier and narrative are misleading.',
            '30-minute mean did not have the highest coverage among all queries: EWMA with a lower coverage requirement had higher coverage.',
            'Label mean-vs-median comparisons do not use identical objectives; lower MSE or MAE does not prove improved prediction.'],
        'all_source_rows_and_specs_unchanged':True,'new_model_calls':0,'training_admitted':False,
        'no_selected_objective_overwritten':True,'claim_sha256':file_hash(output/'claim.json')}
    final['audit_sha256']=digest(final);fresh_json(output/'audit.json',final)
    return final


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--controller',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();result=run(**vars(args));print(canonical({k:result[k] for k in ['audit_pass','queries','audit_sha256']}))
