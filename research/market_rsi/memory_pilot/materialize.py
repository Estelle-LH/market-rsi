"""One bounded source object -> verified derived cache, never model-visible rows."""
from array import array
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
import struct

from market_rsi import digest, fresh_json
from typed_raw_profile import Profile, canonical_kernel, sample_at, DAY

COLUMNS = ['lag_delta_60s', 'current_mid', 'current_spread', 'past_quote_count',
           'target_delta', 'anonymous_market_index']
ROW = struct.Struct('<6d')


class CacheProfile(Profile):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.spreads = {}

    def consume(self, line, ordinal):
        super().consume(line, ordinal)  # Frozen validation/routing is authoritative.
        r = json.loads(line)
        messages = r['m'] if isinstance(r['m'], list) else [r['m']]
        touched = set()
        for m in messages:
            if r.get('src') == 'rest' or m.get('event_type') != 'price_change':
                continue
            for c in m['price_changes']:
                asset = c['asset_id']; series = self.entities[asset]; touched.add(asset)
                out = self.spreads.setdefault(asset, array('d'))
                # Correspond exactly to this quote's position, including invalids.
                j = len(out)
                valid = series.valid[j]
                spread = float(Decimal(str(c['best_ask'])) - Decimal(str(c['best_bid']))) if valid else 0.
                out.append(spread)
        if any(len(self.spreads[a]) != len(self.entities[a].t) for a in touched):
            raise ValueError('spread routing/count parity failure')


def write_cache(profile, directory, progress=lambda *_: None):
    """All original eligible pairs; no result-dependent filters or downsampling."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    quality = profile.summary(progress)
    markets = {}; n = 0; sha = hashlib.sha256(); paired = hashlib.sha256()
    sx = sy = sxx = sxy = syy = 0.
    minimum = [float('inf')]*5; maximum = [float('-inf')]*5
    with (directory/'rows.f64').open('xb') as stream:
        for number, (asset,s) in enumerate(profile.entities.items()):
            if s.gaps['negative']:
                continue
            market = hashlib.sha256(s.market.encode()).hexdigest()
            if market not in markets: markets[market] = len(markets)
            k = canonical_kernel(s.rows(), profile.contract)
            prefix = [0]
            for v in s.valid: prefix.append(prefix[-1]+v)
            identity = hashlib.sha256(asset.encode()).digest()
            for i in range(1,len(s.t)):
                if s.t[i] == s.t[i-1]: continue
                x,y = sample_at(k,i,profile.contract,prefix,profile.day_start+DAY)
                if not (x['available'] and y['available']): continue
                values = [x['feature'],s.v[i],profile.spreads[asset][i],
                          float(x['window_observations']),y['label'],float(markets[market])]
                if not all(math.isfinite(v) for v in values) or not 0 <= values[2] <= 1:
                    raise ValueError('invalid derived feature; no silent drop')
                if y['label_available_after_ms'] >= profile.day_start+DAY:
                    raise ValueError('label crosses file-day cutoff')
                raw = ROW.pack(*values); stream.write(raw); sha.update(raw); n += 1
                key = identity+struct.pack('>qQII',s.t[i],s.ordinal[i],s.message[i],s.inner[i])
                paired.update(key+struct.pack('>dd',x['feature'],y['label']))
                a,b = x['feature'],y['label']; sx+=a;sy+=b;sxx+=a*a;sxy+=a*b;syy+=b*b
                for j,v in enumerate(values[:5]):
                    minimum[j]=min(minimum[j],v); maximum[j]=max(maximum[j],v)
            if number%250 == 0: progress(number+1,len(profile.entities))
    m = dict(n=n,sum_x=sx,sum_y=sy,sum_xx=sxx,sum_xy=sxy,sum_yy=syy)
    if not n or n != quality['counts']['numerically_available']:
        raise ValueError('empty cache or paired mask differs')
    for k,v in m.items():
        if not math.isclose(v,quality['paired_moments'][k],rel_tol=1e-8,abs_tol=1e-8):
            raise ValueError('frozen moment parity failure')
    header = dict(schema='memory_pilot_cache_v1',columns=COLUMNS,dtype='<f8',shape=[n,6],
        bytes=n*ROW.size,sha256=sha.hexdigest(),paired_rows_sha256=paired.hexdigest(),
        quality=quality,market_hashes=list(markets),feature_minimum=minimum,feature_maximum=maximum,
        old_kernel_mask_unchanged=True,valid_zero_labels_retained=True,features_causal=True,
        hosted_model_row_access=False,source_admitted=False)
    fresh_json(directory/'header.json',header)
    return header
