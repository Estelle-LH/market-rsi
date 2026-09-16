"""Allow only a proved additive direction cache, not an arbitrary input mutation."""
from pathlib import Path
import zipfile

import numpy as np

from historical_direction_fields import DOWN, MAKER, QUOTE_VOLUME, UP, direction_contract
from historical_ingest_controller import _signed
from market_rsi import file_hash, load_json


ARRAY_KEYS = {'row_id','entity','decision_ms','date','field_names','values'}
ADDED_FIELDS = ('binance_trades.'+MAKER, 'binance_trades.'+QUOTE_VOLUME,
                'polymarket_ticks_ms.'+UP, 'polymarket_ticks_ms.'+DOWN)


def read_cache(path):
    with zipfile.ZipFile(path) as z:
        if (len(z.namelist())!=len(ARRAY_KEYS) or set(z.namelist())!={k+'.npy' for k in ARRAY_KEYS}
                or sum(i.file_size for i in z.infolist())>300000000):
            raise ValueError('bounded numeric input cache required')
    with np.load(path,allow_pickle=False) as z:return {k:z[k] for k in ARRAY_KEYS}


def verify_addition(old, new):
    """Byte-exact old values, including NaN payloads and signed zero, must survive."""
    if set(old)!=ARRAY_KEYS or set(new)!=ARRAY_KEYS:raise ValueError('exact input archive schema required')
    for key in ('row_id','entity','decision_ms','date'):
        if (old[key].dtype!=new[key].dtype or old[key].shape!=new[key].shape
                or old[key].tobytes()!=new[key].tobytes()):
            raise ValueError('additive cache changed original row identity/order/clock')
    old_names=old['field_names'].tolist();new_names=new['field_names'].tolist()
    if (new_names!=old_names+list(ADDED_FIELDS) or len(set(new_names))!=len(new_names)
            or old['values'].shape!=(len(old['row_id']),len(old_names))
            or new['values'].shape!=(len(old['row_id']),len(new_names))
            or old['values'].dtype!=new['values'].dtype
            or old['values'].tobytes()!=new['values'][:,:len(old_names)].tobytes()
            or np.isinf(new['values']).any()):
        raise ValueError('only declared appended fields allowed; old values/NaNs must be byte-identical')
    for field in ADDED_FIELDS:
        column=new['values'][:,new_names.index(field)];finite=column[np.isfinite(column)]
        if field.endswith(QUOTE_VOLUME):
            if np.any(finite<0):raise ValueError('negative quote-volume field')
        elif np.any((finite!=0)&(finite!=1)):raise ValueError('nonbinary reported direction field')
    up,down=(new['values'][:,new_names.index('polymarket_ticks_ms.'+name)] for name in (UP,DOWN))
    valid=np.isfinite(up)
    if not np.array_equal(valid,np.isfinite(down)) or np.any(up[valid]+down[valid]!=1):
        raise ValueError('publisher token roles must agree as a pair, including missingness')
    return {'original_rows':len(old['row_id']),'original_fields':len(old_names),
        'added_fields':list(ADDED_FIELDS),'all_original_arrays_and_values_byte_identical':True}


def require_compatible_inputs(old_root, new_root):
    old_path=old_root/'current-inputs.npz';new_path=new_root/'current-inputs.npz'
    old_sha,new_sha=file_hash(old_path),file_hash(new_path)
    if old_sha==new_sha:return {'kind':'identical','archive_sha256':old_sha}
    old,new=load_json(old_root/'input-result.json'),load_json(new_root/'input-result.json')
    _signed(old,'result_sha256');_signed(new,'result_sha256')
    if (new.get('schema')!='historical_direction_input_extension_v1'
            or new.get('complete') is not True or new.get('labels_present') is not False
            or new.get('fresh_holdout') is not False or new.get('training_admitted') is not False
            or old['panel_sha256']!=new['panel_sha256'] or old['rows']!=new['rows']
            or old['archive_sha256']!=old_sha or new['archive_sha256']!=new_sha
            or new.get('additive_parent')!={'archive_sha256':old_sha,'result_sha256':old['result_sha256'],
                                          'field_names':old['field_names']}
            or new.get('source_extension',{}).get('direction_contract')!=direction_contract()):
        raise ValueError('only exact declared direction-input extension ancestry is compatible')
    before,after=read_cache(old_path),read_cache(new_path)
    if before['field_names'].tolist()!=old['field_names'] or after['field_names'].tolist()!=new['field_names']:
        raise ValueError('cache field manifest disagrees with arrays')
    proof=verify_addition(before,after)
    if proof!=new.get('compatibility'):raise ValueError('additive compatibility receipt disagrees with actual arrays')
    return {'kind':'additive_reported_direction_only','old_archive_sha256':old_sha,
            'new_archive_sha256':new_sha,'extension_result_sha256':new['result_sha256'],**proof}
