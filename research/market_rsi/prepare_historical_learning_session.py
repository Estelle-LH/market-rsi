"""Prepare/launch one GLM learning diagnostic using existing budget/runtime only."""
import argparse
import fcntl
import os
from pathlib import Path
import subprocess
import time

from historical_grid_learning_controller import BASE_INSTRUCTIONS, prepare_workspace
from market_rsi import canonical, file_hash, fresh_json, identifier, load_json
from paid_budget import PaidBudget, money


def prepare(output, *, controller, input_cache, labels, budget, execute=False, prior_failed_session=None,
            prior_completed_session=None, prior_result_audit=None, prior_pairing_audit=None,
            recorded_index=None, recorded_audit=None, recorded_canary=None, prior_unsubmitted_session=None,
            prior_error_balance_audit=None):
    output=output.absolute();controller=controller.absolute();identifier(output.name)
    previous=load_json(controller/'preparation.json');command=previous['command']
    runtime=Path(command[0]);env=Path(command[command.index('--env-file')+1])
    tokenizer=Path(command[command.index('--tokenizer-cache')+1])
    if (not runtime.is_file() or file_hash(runtime)!=previous['runtime_sha256']
            or not env.is_file() or not tokenizer.is_dir()):raise ValueError('same verified runtime and private credentials required')
    state=PaidBudget(budget).snapshot()
    if any(k.startswith(output.name+'-') for k in state['jobs']):raise ValueError('permanent session ID already claimed')
    if any(v['state']=='dispatched' and '-turn-' in k for k,v in state['jobs'].items()):
        raise ValueError('unresolved prior paid controller turn')
    # This stage executes researcher-selected feature/model trials. It uses the
    # existing learning allocation; no transfer from final/setup/repair buckets.
    if money(state['buckets']['learning']['available_usd'])<money('2'):
        raise ValueError('insufficient existing learning allocation for next bounded model turn')
    root=Path(__file__).resolve().parent
    with (root/'artifacts/historical-ingest-controller.lock').open('a+') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise ValueError('another historical controller/worker owns the shared lock')
        output.mkdir(parents=True,exist_ok=False,mode=0o700)
        prepare_workspace(output/'workspace',controller=controller,input_cache=input_cache,labels=labels,
            session_id=output.name,experiment_id=state['experiment_id'],prior_failed_session=prior_failed_session,
            prior_completed_session=prior_completed_session,prior_result_audit=prior_result_audit,
            prior_pairing_audit=prior_pairing_audit,recorded_index=recorded_index,
            recorded_audit=recorded_audit,recorded_canary=recorded_canary,
            prior_unsubmitted_session=prior_unsubmitted_session,prior_error_balance_audit=prior_error_balance_audit)
        prompt=BASE_INSTRUCTIONS
        if prior_failed_session is not None:
            prompt+=' This is a repaired continuation after documented tool-argument failures, before any fit. '
            prompt+='inspect_learning_contract includes your first unexecuted plan and every successful prior feature profile. '
            prompt+='Those verified profiles count as already profiled; do not recompute them simply to continue. '
            prompt+='The model object has exactly algorithm and parameters keys, with all hyperparameters inside parameters. '
            prompt+='For the FIRST trial set parent_trial_id to exactly the empty string ""; neither "none" nor an unexecuted trial ID is a parent. '
            prompt+='Always include a nonempty plan.rationale. Complete argument schemas are visible in the tools and library. '
            prompt+='Retain or revise your own scientific choices explicitly; old failed calls are not accepted trials or final decisions.'
        if prior_completed_session is not None:
            prompt+=' Continue from the complete audited diagnostic and your own capability deferral in the archive. '
            prompt+='Inspect the exact currently supported contract and decide your next hypothesis; capabilities are not automatically selected. '
            prompt+='The earlier trial and protocol are carried unchanged. Your NEXT trial must name an available completed parent ID, not an empty string. '
            prompt+='Do not rerun that parent: its original prediction artifacts, score and trial slot remain. All dates/metric stay fixed. '
            prompt+='A distinct one-stage comparison on opened Train is allowed research, not an identical-plan score retry; it is still not untouched validation. '
            extension=load_json(output/'workspace/input-result.json').get('schema')=='historical_direction_input_extension_v1'
            if extension:
                prompt+='Four raw reported fields were omitted by the old projection and are now exposed additively, with old columns and NaNs byte-identical. '
                prompt+='They are recorded buyer-maker flag, quote amount, and publisher UP/DOWN token roles. Inspect the archive input_extension, exact field names, availability and source caveats. '
                prompt+='Maker0 can include a publisher default for missing upstream data; historical deployment is unverified. Token roles are not future outcomes. '
                prompt+='These are latest recorded fields, NOT window-aggregated signed order flow. No full depth, new dates, target changes or fresh Dev/Test were added. '
                prompt+='Your earlier two particular models do not prove no learnable content or isolate missingness as the cause. Choose your own next hypothesis without changing the fixed comparison protocol. '
                prompt+='Do not resubmit a semantically identical old plan with a new name/rationale. Reuse existing profiles. '
            else:
                prompt+='No signed flow, depth, new sources or fresh Dev/Test have been added. '
            prompt+='Request only concrete still-missing capabilities or submit a defensible diagnostic decision.'
        if prior_pairing_audit is not None:
            prompt+=' The archive contains a new independent read-only pairing audit on the SAME already-open inputs. '
            prompt+='Inspect its measured symmetries before interpreting your earlier pooled machine-zero correlations as absent information. '
            prompt+='The library now supports bounded explicit composition of causal primitives (sum/difference/product), as requested in your deferral. '
            prompt+='No default formula, role mapping, hypothesis or new model has been selected for you. '
            prompt+='Choose and justify your own next step; keep the fixed target, protocol and all prior evidence. '
            prompt+='Composition of grid records is not window aggregation of every raw trade; do not claim equivalence.'
        if (output/'workspace/recorded-trades').exists():
            prompt+=' Your requested all-recorded-trade window capability is now attached, after independent full-row/raw-byte reconciliation and real-window mechanics canaries. '
            prompt+='This extends earlier text describing unavailable flow; inspect recorded_event_windows in the library and recorded_event_extension in the archive. '
            prompt+='The index contains the SAME six opened receipt dates and no new observations. Choose your own window, statistic, minimum record count, maximum recorded-gap tolerance, composition and hypothesis; no defaults or model are selected for you. '
            prompt+='A gap guard is only a recorded-feed proxy, not proof of full exchange coverage. Empty windows remain unknown; same-ms aggregate receipts all count; reported maker0 may be an upstream default. '
            prompt+='Reuse all prior feature profiles and trial artifacts; old slots count. Correct prior prose from the archived numeric_profile_sign_counts: Pearson and rank signs need not agree on every date. '
            prompt+='Your earlier ret5xrole profile has negative Pearson on5/6dates (Apr05positive) and negative rank on6/6; do not repeat the all-six-both claim. All old conclusions are opened-Train diagnostics only.'
        if prior_completed_session is not None:
            prompt+=' A new read-only inspect_learning_trial tool can explain your existing trials without refitting: inspect actual parent feature additions/removals, which features are unavailable, quiet-row denominators and projection-evidence limits before repeating causal claims. '
            prompt+=' The library also provides diagnose_feature_controls: YOU choose an existing trial feature and controls. It fits earlier-only nuisance projections, not a new prediction model, to distinguish marginal association from redundancy on explicitly matched rows. Inspect its precise semantics and limitations; no control set is prescribed, no fresh validation is implied, and insufficient evidence is a valid outcome. '
            prompt+='This adds diagnosis, not a native-NaN linear learner or any new data. No model, feature subset or follow-up hypothesis is prescribed. Preserve prior decisions and trial limits. Propose a distinct justified comparison only if warranted; otherwise report the concrete capability needed. '
        if prior_unsubmitted_session is not None:
            prompt+=' THIS SESSION IS PROTOCOL CLOSURE ONLY. The previous inspection session exited with prose but never called submit_grid_learning_decision; it is invalid, not a committed decision. '
            prompt+='Its exact narrative, successful inspection results and all paid-turn hashes/costs are preserved in archive.terminal_protocol_recovery. Do not discard that history. '
            prompt+='No new feature profiles or model fits are permitted here. Inspect existing evidence as needed, then call submit_grid_learning_decision with YOUR decision and evidence-grounded reason. '
            prompt+='Do not answer only in prose, infer a choice from the old narrative, fabricate APIs or declare old samples fresh. There is only one such closure continuation, not an automatic retry loop. '
        if prior_error_balance_audit is not None:
            prompt+=' New independent evidence is available in archive.prediction_error_balance for ALL saved model predictions. '
            prompt+='It decomposes original MSE loss using unchanged population and weights, without fitting a rescaling or another model. '
            prompt+='Inspect exact prediction-energy, target-alignment and additive quiet/moving contributions before attributing failure to quietness, missingness or an entire family. '
            prompt+='These diagnostics do not select your model, parameter, control set or hypothesis. The generic conditional diagnostic remains available if useful; it is NOT a native-NaN linear learner. '
            prompt+='Any next experiment must remain a genuinely distinct justified one-stage hypothesis on opened Train, not an identical-plan retry or merely rewriting a conclusion. All existing trial slots and fees remain. '
        (output/'prompt.txt').write_text(prompt,encoding='utf-8')
        command=[str(runtime),str(root/'run_codex_glm_controller.py'),'--session-id',output.name,
            '--output',str(output/'session'),'--workspace',str(output/'workspace'),
            '--prompt',str(output/'prompt.txt'),'--budget',str(budget.absolute()),
            '--budget-bucket','learning','--env-file',str(env),'--tokenizer-cache',str(tokenizer),
            '--tool-mode','canary','--controller-stage','grid_learning']
        sources={p.name:file_hash(p) for p in sorted(root.glob('*.py'))}
        snapshot=output/'source-snapshot';snapshot.mkdir()
        for name,sha in sources.items():
            (snapshot/name).write_bytes((root/name).read_bytes())
            if file_hash(snapshot/name)!=sha:raise ValueError('source changed during snapshot')
        for name,sha in previous['source_hashes'].items():
            if file_hash(controller/'source-snapshot'/name)!=sha:raise ValueError('prior source snapshot changed')
        adaptation={'purpose':'opened-Train signed-delta feature/model library adapter after completed objective selection',
            'prior_controller_id':controller.name,'prior_preparation_sha256':file_hash(controller/'preparation.json'),
            'changed_existing_sources':{n:{'before':sha,'after':sources.get(n)} for n,sha in previous['source_hashes'].items() if sources.get(n)!=sha},
            'added_sources':{n:sha for n,sha in sources.items() if n not in previous['source_hashes']},
            'prior_artifacts_unchanged':True,'scientific_objective_changed':False,
            'execution':'trusted bounded CPU methods, not arbitrary generated code or E2B',
            'budget_bucket':'existing learning allocation; no rebucketing',
            'tool_mode_name_canary_is_transport_routing_only':'grid_learning tools execute real CPU fits and are labelled opened-Train diagnostics'}
        fresh_json(output/'source-adaptation.json',adaptation)
        receipt={'schema':'historical_grid_learning_preparation_v1','command':command,
            'source_hashes':sources,'source_adaptation_sha256':file_hash(output/'source-adaptation.json'),
            'runtime_sha256':file_hash(runtime),'workspace_sha256':file_hash(output/'workspace/workspace.json'),
            'prompt_sha256':file_hash(output/'prompt.txt'),'budget_before':{k:v for k,v in state.items() if k!='jobs'},
            'paid_controller_started':False,'new_budget':False,'new_dev_test':False,'download_started':False}
        fresh_json(output/'preparation.json',receipt)
        if not execute:return receipt
        fresh_json(output/'dispatch-claim.json',{'session_id':output.name,'claimed_unix_ns':time.time_ns(),
            'preparation_sha256':file_hash(output/'preparation.json')})
        if any(file_hash(root/n)!=sha for n,sha in sources.items()):raise ValueError('source changed before dispatch')
        with (output/'runner.log').open('x') as log:
            process=subprocess.Popen(command,cwd=root,stdout=log,stderr=subprocess.STDOUT,
                start_new_session=True,pass_fds=(lock.fileno(),))
        result={'pid':process.pid,'process_group':process.pid,'command':command,
                'lock_inherited':True,'started_unix_ns':time.time_ns()}
        fresh_json(output/'runner-process.json',result)
        return {'pid':process.pid,'session_id':output.name,'paid_controller_started':True,'output':str(output)}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['output','controller','input-cache','labels','budget']:p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--execute',action='store_true');p.add_argument('--prior-failed-session',type=Path)
    p.add_argument('--prior-completed-session',type=Path);p.add_argument('--prior-result-audit',type=Path)
    p.add_argument('--prior-unsubmitted-session',type=Path)
    p.add_argument('--prior-error-balance-audit',type=Path)
    p.add_argument('--prior-pairing-audit',type=Path)
    p.add_argument('--recorded-index',type=Path);p.add_argument('--recorded-audit',type=Path)
    p.add_argument('--recorded-canary',type=Path)
    print(canonical(prepare(**vars(p.parse_args()))))
