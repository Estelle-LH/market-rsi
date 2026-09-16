"""Read-only array/reason audit plus independent prior real-canary comparison."""
import argparse
from collections import Counter, defaultdict
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from historical_input_compatibility import ADDED_FIELDS,read_cache,verify_addition
from market_rsi import canonical,digest,file_hash,fresh_json,load_json


def run(original,extension,canary,output):
    before=load_json(original/'result.json');after=load_json(extension/'result.json')
    tested=load_json(canary/'result.json');claim=load_json(extension/'claim.json')
    for obj in (before,after,tested):
        if obj['result_sha256']!=digest({k:v for k,v in obj.items() if k!='result_sha256'}):
            raise ValueError('result digest mismatch')
    for path,expected in [(original/'current-inputs.npz',before['archive_sha256']),
            (extension/'current-inputs.npz',after['archive_sha256']),
            (extension/'direction-field-reasons.npz',after['reason_archive_sha256']),
            (extension/'claim.json',after['claim_sha256']),
            (canary/'observations.json',tested['observations_sha256'])]:
        if file_hash(path)!=expected:raise ValueError('artifact hash mismatch')
    for key in ('input_hashes','code_hashes'):
        for path,sha in claim[key].items():
            if file_hash(Path(path))!=sha:raise ValueError('source changed since extension build')
    for path,sha in after['raw_source_hashes_verified_unchanged'].items():
        if file_hash(Path(path))!=sha:raise ValueError('raw bytes changed since extension build')
    x,y=read_cache(original/'current-inputs.npz'),read_cache(extension/'current-inputs.npz')
    proof=verify_addition(x,y)
    if proof!=after['compatibility']:raise ValueError('compatibility proof mismatch')
    names=y['field_names'].tolist();n=len(y['row_id'])
    with np.load(extension/'direction-field-reasons.npz',allow_pickle=False) as z:
        if set(z.files)!={'row_id','field_names','reason_codes','reason_dictionary'}:
            raise ValueError('reason archive schema changed')
        if not np.array_equal(z['row_id'],y['row_id']) or z['field_names'].tolist()!=list(ADDED_FIELDS):
            raise ValueError('reason and input rows disagree')
        codes=z['reason_codes'];dictionary=z['reason_dictionary'].tolist()
    if codes.shape!=(n,4) or np.any(codes<0) or np.any(codes>=len(dictionary)) or len(set(dictionary))!=len(dictionary):
        raise ValueError('invalid reason dictionary/codes')
    counts=Counter();field_stats={}
    for j,field in enumerate(ADDED_FIELDS):
        values=y['values'][:,names.index(field)];reason=np.array(dictionary)[codes[:,j]]
        if not np.array_equal(np.isfinite(values),reason=='present'):raise ValueError('missing values/reasons disagree')
        counts.update({field+':'+key:int((reason==key).sum()) for key in np.unique(reason)})
        field_stats[field]={'present':int(np.isfinite(values).sum()),'missing':int(np.isnan(values).sum())}
    if dict(counts)!=after['field_reason_counts']:raise ValueError('reason counts disagree')
    for j,name in enumerate(names):
        if int(np.isfinite(y['values'][:,j]).sum())!=after['finite_rows_per_field'][name]:
            raise ValueError('field coverage mismatch')
    # Canary stored independent source-access results before this full builder existed.
    grouped=defaultdict(list)
    for item in load_json(canary/'observations.json'):
        for field,observation in item['field_observations'].items():
            grouped[(item['panel_row_id'],item['stream']+'.'+field)].append(observation['value'])
    index={r:i for i,r in enumerate(y['row_id'])};compared=0
    for (row_id,field),values in grouped.items():
        actual=y['values'][index[row_id],names.index(field)]
        expected=values[0] if all(v is not None for v in values) and len(set(values))==1 else None
        if not (np.isnan(actual) if expected is None else actual==expected):
            raise ValueError('new full field disagrees with earlier independent real-byte canary')
        compared+=1
    report={'schema':'direction_input_extension_audit_v1','passed':True,
        'original_result_sha256':before['result_sha256'],'extension_result_sha256':after['result_sha256'],
        'compatibility':proof,'added_field_counts':field_stats,'all_reason_codes_checked':int(codes.size),
        'earlier_real_canary_field_comparisons':compared,'canary_result_sha256':tested['result_sha256'],
        'raw_files_rehashed':len(after['raw_source_hashes_verified_unchanged']),
        'new_profiles':0,'new_fits':0,'new_model_calls':0,'new_target_reads':0,
        'fresh_holdout':False,'not_direction_truth_or_signal_strength_proof':True}
    report['result_sha256']=digest(report);output.mkdir(parents=True,exist_ok=False)
    fresh_json(output/'audit.json',report);return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('original','extension','canary','output'):p.add_argument('--'+key,type=Path,required=True)
    print(canonical(run(**vars(p.parse_args()))))
