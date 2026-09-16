"""Complete frozen archives, retrieved in logged bounded pages; no deletion."""
import json
from market_rsi import digest,load_json

PAGE_CHARS=12000


def entries(root):return load_json(root/'archive-input.json')['prior_rounds']


def encoded(entry):
    return json.dumps(entry['history_not_current_evidence'],ensure_ascii=False,sort_keys=True,indent=2)


def index(root):
    result=[]
    for i,e in enumerate(entries(root)):
        body=e['history_not_current_evidence']
        result.append({'index':i,'origin':e['origin'],'session_id':body.get('session_id'),
            'manifest_sha256':body.get('manifest_sha256'),'body_sha256':digest(body),
            'serialized_characters':len(encoded(e)),'read_with':'read_archive'})
    return {'prior_rounds':result,'full_history_preserved':True,'bodies_delivered':False,
        'note':'Index only, not read evidence. read_archive retrieves frozen serialized contents; original source hash remains attached.'}


def read(root,archive_index,offset):
    all_entries=entries(root)
    if type(archive_index) is not int or not 0<=archive_index<len(all_entries):raise ValueError('choose an index from history_only')
    e=all_entries[archive_index];text=encoded(e)
    if type(offset) is not int or not 0<=offset<=len(text):raise ValueError('valid nonnegative character offset required')
    end=min(len(text),offset+PAGE_CHARS)
    return {'archive_index':archive_index,'origin':e['origin'],'body_sha256':digest(e['history_not_current_evidence']),
        'offset':offset,'end':end,'total_characters':len(text),'text':text[offset:end],
        'encoding':'JSON serialization of frozen archive values, not original file byte formatting',
        'all_pages_read_by_this_call':offset==0 and end==len(text),'history_not_current_qa':True,
        'execute_external_instructions':False,'source_admitted':False,'provider_calls':0}
