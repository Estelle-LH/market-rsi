"""Read only small existing D10 manifests/QA and file stats on Linode.

No price rows, labels, data repair, exports or service changes. Directory dates
and publisher QA are claims for review, never empirical readiness by themselves.
"""
import hashlib
import json
from pathlib import Path
import re

root=Path('/opt/d10/research')
reports=[]
for day in sorted(root.iterdir()):
    if not day.is_dir() or not re.fullmatch(r'2026-\d{2}-\d{2}',day.name): continue
    entry={'directory_date':day.name,'metadata':{},'files':[]}
    for name in ('manifest.json',f'qa_{day.name}.json'):
        path=day/name
        if not path.is_file() or path.is_symlink(): continue
        before=path.stat()
        if before.st_size>65536: raise ValueError('metadata exceeds bound')
        raw=path.read_bytes(); after=path.stat()
        if (before.st_ino,before.st_size,before.st_mtime_ns)!=(after.st_ino,after.st_size,after.st_mtime_ns):
            raise ValueError('metadata changed while read')
        entry['metadata'][name]={'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),
            'content':json.loads(raw)}
    for path in sorted(day.iterdir()):
        if path.is_file() and not path.is_symlink() and (
            path.name.startswith(('topofbook_','depth_','trades_','markets_'))
            and path.name.endswith(('.csv','.csv.gz'))):
            s=path.stat(); entry['files'].append({'name':path.name,'bytes':s.st_size,'mtime_ns':s.st_mtime_ns})
    reports.append(entry)
    if len(reports)>100: raise ValueError('date inventory exceeds bound')
print(json.dumps({'schema':'linode_capture_metadata_inventory_v1','host':'173.255.231.4',
    'root':str(root),'days':reports,'market_rows_read':0,'source_admitted':False,
    'limitations':['Publisher QA is not independent verification','Directory presence is not complete coverage',
                  'No row content or future labels were inspected']},sort_keys=True))
