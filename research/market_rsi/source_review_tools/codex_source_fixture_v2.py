"""Real Codex and v2 broker, scripted model replies only, isolated fixture cost."""
import argparse
from pathlib import Path
import sys

import run_source_review_v2 as runner
from codex_source_fixture import ScriptedBackend
from market_rsi import canonical,digest,file_hash,fresh_json
from paid_budget import PaidBudget


def canary(prepared):
    prep,manifest,_=runner.verify_preparation(prepared)
    if manifest['purpose']!='transport_canary':raise ValueError('fixture-only preparation required')
    if any((prepared/n).exists() for n in ('session','fixture-budget','fixture-only-claim.json')):
        raise ValueError('permanent fixture already used')
    for module in (Path(__file__),Path(runner.__file__)):
        if prep['source_hashes'].get('source_review_tools/'+module.name)!=file_hash(module):raise ValueError('unfrozen actual fixture')
    fresh_json(prepared/'fixture-only-claim.json',{'evidence_mode':'synthetic_transport_fixture',
        'actual_tinker_calls':0,'real_budget_access':False,'credentials_loaded':False,
        'decision_is_model_authored':False,'source_hashes':prep['source_hashes']})
    budget=PaidBudget.create(prepared/'fixture-budget',{'experiment_id':'fixture-'+prepared.name,
        'cap_usd':'10','target_usd':'10','buckets_usd':{'learning':'10'},'authority':'Synthetic counters only, no provider usage.'})
    backend=ScriptedBackend()
    try:
        a=runner.run_session(prepared=prepared,backend=backend,budget=budget,
            prompt='Synthetic transport fixture: execute scripted metadata tools and terminal handshake.',
            evidence_mode='synthetic_transport_fixture')
        if backend.sample_calls!=2 or a['turns']!=2 or a['tool_calls']!=4 or a['model_authorship_proven'] is not False:
            raise ValueError('exact two samples and four tools required')
        runner.verify_preparation(prepared)
    except Exception as e:
        fresh_json(prepared/'fixture-failure.json',{'error_type':type(e).__name__,'message_sha256':digest(str(e)),
            'actual_tinker_calls':0,'automatic_retry':False});raise
    r={'schema':'historical_source_review_v2_codex_fixture_v1','passed':True,'actual_codex_cli':True,
        'actual_tinker_calls':0,'credentials_loaded':False,'source_hashes':prep['source_hashes'],
        'context_sha256':prep['context_sha256'],'followup_sha256':prep['followup_sha256'],
        'preparation_sha256':file_hash(prepared/'preparation.json'),
        'codex_cli_sha256':file_hash(runner.harness.CODEX),'python_sha256':file_hash(Path(sys.executable)),
        'assessment_sha256':file_hash(prepared/'session/assessment.json'),
        'fixture_claim_sha256':file_hash(prepared/'fixture-only-claim.json'),
        'scripted_samples':2,'tool_calls':4,'model_authorship_proven':False,
        'fixture_ledger_is_not_provider_cost':True,'new_downloads':0,'new_fits':0}
    r['result_sha256']=digest(r);fresh_json(prepared/'codex-fixture-canary.json',r);return r


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prepared',type=Path,required=True)
    r=canary(p.parse_args().prepared.resolve());print(canonical({k:v for k,v in r.items() if k!='source_hashes'}))
