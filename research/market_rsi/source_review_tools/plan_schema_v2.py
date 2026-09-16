"""Explicit source-review proposal shape for the NEXT, separately frozen stage.

No change to an existing broker, run, artifact, semantic validator or authority.
Dataset IDs and revisions are separate fields; public notes are not data files.
"""
import copy
import controller_source_review as original


def exact_object(properties):
    return {'type':'object','properties':properties,'required':list(properties),'additionalProperties':False}


def text_list(maximum=50):
    return {'type':'array','items':copy.deepcopy(original.TEXT),'minItems':1,
            'maxItems':maximum,'uniqueItems':True}


OBJECT_SCHEMA=exact_object({
    'source_id':{'type':'string','description':'Exact source ID from the catalog, WITHOUT @revision.'},
    'revision':{'type':'string','pattern':'^[0-9a-f]{40}$'},
    'path':copy.deepcopy(original.TEXT),
    'sha256':{'type':'string','pattern':'^[0-9a-f]{64}$'},
    'bytes':{'type':'integer','minimum':1},
})
MAPPING_SCHEMA=exact_object({
    'required_field':copy.deepcopy(original.TEXT),'proposed_field':copy.deepcopy(original.TEXT),
    'availability_clock':copy.deepcopy(original.TEXT),
    'status':{'type':'string','enum':['documented','requires_raw_check','unavailable']},
    'evidence':copy.deepcopy(original.TEXT),
})
PLAN_SCHEMA=exact_object({
    'plan_id':{'type':'string','minLength':1,'maxLength':100},
    'context_sha256':{'type':'string','pattern':'^[0-9a-f]{64}$'},
    'review_catalog_sha256':{'type':'string','pattern':'^[0-9a-f]{64}$'},
    'stage':{'type':'string','enum':['source_compatibility_audit','new_data_stage']},
    'source_ids':{**text_list(3),'description':'Exact catalog dataset IDs, never dataset@revision.'},
    'objects':{'type':'array','items':OBJECT_SCHEMA,'maxItems':20,
        'description':'Only independently recorded exact SHA256/byte descriptors. Documentation URLs '
                      'without such descriptors belong in a metadata request, not this array. Empty '
                      'means requirements unresolved; it does not authorize free acquisition.'},
    'requested_window':{'type':'array','items':{'type':'string','pattern':'^\\d{4}-\\d{2}-\\d{2}$'},
                        'minItems':2,'maxItems':2},
    'minimum_complete_sessions':{'type':'integer','minimum':20},
    'question':copy.deepcopy(original.TEXT),'source_contract_changes':text_list(),
    'required_streams':text_list(),
    'field_mapping':{'type':'array','items':MAPPING_SCHEMA,'minItems':1,'maxItems':100},
    'clock_policy':copy.deepcopy(original.TEXT),'gap_policy':copy.deepcopy(original.TEXT),
    'coverage_policy':copy.deepcopy(original.TEXT),'unresolved_questions':text_list(),
    'artifact_use':{'type':'string','const':'opened_data_qa_train_only'},
    'quiet_rows':{'type':'string','const':'preserve_raw_no_future_filter'},
    'validation_claim':{'type':'string','const':'none'},
})


def enriched_tools():
    tools=copy.deepcopy(original.TOOLS)
    item=next(t for t in tools if t['name']=='propose_source_plan')
    item['inputSchema']['properties']['plan']=copy.deepcopy(PLAN_SCHEMA)
    return tools


def context_addendum(visible):
    ids={s['id'] for s in visible['source-review-catalog.json']['sources']}
    ids|={s['source_id'] for s in visible['prior-source-catalog.json']['sources']}
    return {'source_plan_json_schema':copy.deepcopy(PLAN_SCHEMA),
        'known_source_ids':sorted(ids-{'synthetic-market-simulator'}),
        'source_id_format':'dataset ID only; revision belongs in objects[].revision',
        'metadata_document_urls_use':'request_source_metadata, not invented object hashes',
        'semantic_validator_and_authority_unchanged':True,
        'not_yet_wired_into_paid_dispatcher':True}
