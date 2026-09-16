"""Pre-result research intent, exact outcomes, and separately labelled reflection.

No hidden chain of thought is requested or inferred: these are concise research
decisions, public rationale, tool evidence and observed results.
"""
from pathlib import Path
from datetime import datetime, timezone
import json

from data_scientist_harness.release import attribution, compare_attribution, identity
from data_scientist_harness.sanity import rules
from market_rsi import digest, file_hash, fresh_json, load_json

TEXT_FIELDS = ("question", "hypothesis", "supports_if", "refutes_if", "next_if_unsupported")
POLICY_FIELDS = ("feature_units", "feature_rules", "normalized_units", "normalized_rules")
FIELDS = set(TEXT_FIELDS + POLICY_FIELDS + ("changed_layer",))


def validate_experiment(value, plan, parent_claim=None):
    if not isinstance(value, dict) or set(value) != FIELDS:
        raise ValueError("complete pre-result experiment question, hypothesis, criteria and sanity policies required")
    for key in TEXT_FIELDS:
        if not isinstance(value[key], str) or not 1 <= len(value[key].strip()) <= 2000:
            raise ValueError("concise nonempty research intent required")
    names = [f['name'] for f in plan['features']]
    for key in ('feature_units','normalized_units'):
        if (not isinstance(value[key], dict) or set(value[key]) != set(names)
                or any(not isinstance(v,str) or not v.strip() for v in value[key].values())):
            raise ValueError("explicit feature and normalized units required")
    for key in ('feature_rules','normalized_rules'): rules(value[key], names)
    if plan['normalizer']=='none' and value['normalized_units']!=value['feature_units']:
        raise ValueError('no normalization cannot change feature units')
    expected = 'baseline'
    if parent_claim:
        old = parent_claim['plan']; previous = parent_claim['experiment']
        changed_features = old['features'] != plan['features']
        expected = 'features' if changed_features else 'trainer'
        fixed = [] if changed_features else ['feature_units','feature_rules']
        if not changed_features and old['normalizer'] == plan['normalizer']:
            fixed += ['normalized_units','normalized_rules']
        if any(previous[k] != value[k] for k in fixed):
            raise ValueError("same-feature sanity policy cannot be loosened after outcome inspection")
    if value['changed_layer'] != expected:
        raise ValueError("declared changed layer differs from the actual parent comparison")
    return value


def trial_attribution(config, plan, experiment):
    return {**attribution(config,plan), 'quality_policies_sha256':digest({k:experiment[k] for k in POLICY_FIELDS})}


def write_intent(store, path, claim):
    events = store.events()
    value = {'schema':'data_science_experiment_intent_v1',
        'recorded_utc':datetime.now(timezone.utc).isoformat(),
        'phase':'before_worker_or_result', 'author':'controller_explicit_research_plan',
        'experiment':claim['experiment'], 'plan':claim['plan'],
        'parent_trial_id':claim['parent_trial_id'],
        'attribution':trial_attribution(store.config,claim['plan'],claim['experiment']),
        'quality_review':store.quality(),
        'raw_profile_refs':[e['record'] for e in events if e['tool']=='profile_raw_series'],
        'feature_review':store.get(claim['feature_review'],'review_feature_set'),
        'trainer_research':store.get(claim['trainer_research'],'record_research'),
        'prior_activity':events, 'claim_scope':'already-open Train diagnostics, not fresh Dev/Test',
        'outcomes_known_at_write':False}
    fresh_json(path/'intent.json',value)
    return file_hash(path/'intent.json')


def outcome(store, trial):
    path = store.root/'trials'/trial
    claim = load_json(path/'claim.json')
    if file_hash(path/'intent.json') != claim['intent_sha256']:
        raise ValueError("pre-result research intent changed")
    if (path/'failure.json').exists():
        failures=[r for r in store.records('train_candidate') if r['status']=='error'
            and r['arguments']['trial_id']==trial and r['result'].get('failure_sha256')==file_hash(path/'failure.json')]
        if len(failures)!=1: raise ValueError('failure needs its unchanged ledger-backed receipt')
        return {'status':'failed', 'outcome_sha256':file_hash(path/'failure.json'),
                'failure':load_json(path/'failure.json'), 'scientific_conclusion':None}
    result = load_json(path/'result.json'); report=result['report']
    if (file_hash(path/'claim.json')!=result['claim_sha256']
            or file_hash(path/'predictions.npz')!=result['predictions_sha256']):
        raise ValueError('observed trial artifact changed')
    expected={f'sanity/{stage}/{name}.json' for stage in ('raw','features','normalized','score')
              for name in ('data_check','time_series_check','quality_gate')}
    if set(result['sanity_reports'])!=expected:
        raise ValueError('complete raw/feature/normalized/score sanity evidence required')
    for relative, sha in result['sanity_reports'].items():
        if file_hash(path/relative)!=sha: raise ValueError('sanity report changed')
        if relative.endswith('quality_gate.json') and load_json(path/relative)['status']!='PASS':
            raise ValueError('successful result cannot have a failed quality gate')
    parent = claim['parent_trial_id']; before = None
    if parent:
        before = load_json(store.root/'trials'/parent/'result.json')
    metrics = report['score']
    delta = None if before is None else {
        'model_mse_probability':metrics['model_mse_probability']-before['report']['score']['model_mse_probability'],
        'mse_skill_vs_persistence':None if metrics['mse_skill_vs_persistence'] is None
            or before['report']['score']['mse_skill_vs_persistence'] is None else
            metrics['mse_skill_vs_persistence']-before['report']['score']['mse_skill_vs_persistence']}
    return {'status':'completed', 'outcome_sha256':file_hash(path/'result.json'),
        'baseline_persistence_mse':metrics['persistence_mse_probability'],
        'parent_metrics':None if before is None else before['report']['score'],
        'candidate_metrics':metrics, 'candidate_minus_parent':delta,
        'by_date':report['by_check_date'],
        'fit_rows':report['fit_rows'], 'check_rows':report['check_population_rows'],
        'fallback_rows':report['check_persistence_fallback_rows'],
        'fit_warnings':report['fit_warnings'], 'elapsed_seconds':report['elapsed_seconds'],
        'sanity_reports':result['sanity_reports'],
        'component_comparison':None if before is None else compare_attribution(before['attribution'],result['attribution']),
        'scientific_performance_proven':False, 'fresh_holdout':False,
        'cost_scope':'CPU fit reports zero provider cost; controller cost is in session/provider ledger, not zero'}


def reflect(store, args):
    path = store.root/'trials'/args['trial_id']
    if (path/'reflection.json').exists():
        raise ValueError("reflection is append-only; cannot rewrite earlier conclusions")
    for key in ('interpretation','next_step'):
        if not isinstance(args[key],str) or not 1 <= len(args[key].strip()) <= 3000:
            raise ValueError("concise interpretation and next step required")
    observed = outcome(store,args['trial_id'])
    if args['outcome_sha256'] != observed['outcome_sha256']:
        raise ValueError("reflection must cite the exact observed result or failure")
    allowed = {'infrastructure_failure','inconclusive'} if observed['status']=='failed' else {
        'supported_on_open_train','not_supported_on_open_train','inconclusive'}
    if args['conclusion'] not in allowed:
        raise ValueError("reflection cannot turn an error or Train result into external success")
    value = {'schema':'data_science_experiment_reflection_v1',
        'recorded_utc':datetime.now(timezone.utc).isoformat(),
        'intent_sha256':file_hash(path/'intent.json'), 'observed':observed,
        'controller_interpretation':args, 'interpretation_is_not_independently_verified':True}
    fresh_json(path/'reflection.json',value)
    return {'trial_id':args['trial_id'], 'reflection_sha256':file_hash(path/'reflection.json'),
            'external_improvement_proven':False}


def completed_trace(store):
    paths = sorted((store.root/'trials').iterdir()) if (store.root/'trials').exists() else []
    trace = []
    for path in paths:
        seen = [r for r in store.records('reflect_candidate')
                if r['status']=='ok' and r['arguments']['trial_id']==path.name]
        if len(seen)!=1 or not (path/'reflection.json').exists():
            raise ValueError("every claimed trial, including failures, needs a recorded reflection")
        reflection = load_json(path/'reflection.json')
        if (seen[0]['result']['reflection_sha256'] != file_hash(path/'reflection.json')
                or reflection['intent_sha256'] != file_hash(path/'intent.json')
                or reflection['observed'] != outcome(store,path.name)):
            raise ValueError("trial evidence or reflection changed")
        trace.append({'trial_id':path.name,'intent':load_json(path/'intent.json'),
                      'reflection':reflection,'reflection_sha256':file_hash(path/'reflection.json')})
    return {'schema':'data_science_round_trace_v1', 'harness':identity(store.config),
        'trials':trace, 'all_trial_count':len(trace), 'no_trial_claimed':not trace,
        'reading_and_failures':store.events(), 'hidden_reasoning_requested':False,
        'claim':'Research decisions and observable evidence; no independent RSI improvement claim.'}


def write_trace(store, value):
    fresh_json(store.root/'research-trace.json',value)
    lines=['# 本轮做了什么', '',
           '这是工具验收记录。输入和模型回复是测试夹具，不是真实研究结果。'
           if store.config['purpose']=='canary' else
           '这是已开放 Train 内的研究记录，不是新的 Dev/Test 成绩。', '',
           f"共 {len(value['trials'])} 次训练尝试；失败也保留。模型费用另见会话账本，CPU 拟合费用不能代替总费用。", '',
           '[完整数据与调用记录](research-trace.json)', '', '## 实际调用顺序', '']
    for event in value['reading_and_failures']:
        relative=Path(event['record']['path']).relative_to(store.root).as_posix()
        lines.append(f"- {event['tool']}：[{relative}]({relative})")
    lines.append('')
    def number(value):
        return '不适用' if value is None else format(value,'.9g')
    for trial in value['trials']:
        intent=trial['intent']; e=intent['experiment']; r=trial['reflection']; observed=r['observed']
        path=f"trials/{trial['trial_id']}"
        lines += [f"## {trial['trial_id']}", '', f"问题：{e['question']}", '',
            f"运行前的想法：{e['hypothesis']}", '',
            f"本次改动：{e['changed_layer']}；比较对象：{intent['parent_trial_id'] or '首个模型 / 价格不变预测'}。", '',
            f"什么结果支持它：{e['supports_if']}", '', f"什么结果不支持它：{e['refutes_if']}", '',
            f"不支持时原定怎么做：{e['next_if_unsupported']}", '',
            f"[完整计划、资料和检查]({path}/intent.json)", '', '### 实际结果', '']
        if observed['status']=='failed':
            lines += ['没有有效分数；不能据此判断方法好坏。', '',
                      f"[错误详情]({path}/failure.json)", '', '```json',
                      json.dumps(observed['failure'],ensure_ascii=False,indent=2), '```', '']
        else:
            baseline=observed['baseline_persistence_mse']
            rows=[('价格不变预测',baseline,0.0 if baseline is not None and baseline>0 else None)]
            if observed['parent_metrics']:
                p=observed['parent_metrics']; rows.append(('上个模型',p['model_mse_probability'],p['mse_skill_vs_persistence']))
            c=observed['candidate_metrics']; rows.append(('本次模型',c['model_mse_probability'],c['mse_skill_vs_persistence']))
            lines += ['| 比较对象 | MSE（概率平方） | RMSE（概率 bp） | 相对价格不变预测的 skill |',
                      '|---|---:|---:|---:|']
            for name,mse,skill in rows:
                # Display conversion only. Neither the target nor the score changes.
                lines.append(f"| {name} | {number(mse)} | {number(None if mse is None else mse**0.5*10000)} | {number(skill)} |")
            lines += ['', 'MSE/RMSE 越低越好，skill 越高越好。概率 bp 是概率差乘 10,000，不是交易收益。', '',
                f"拟合行数：{observed['fit_rows']}；检查行数：{observed['check_rows']}；回退到价格不变预测的行数：{observed['fallback_rows']}。", '',
                f"[逐日分数、警告和耗时]({path}/result.json)；[原始数据检查]({path}/sanity/raw/quality_gate.json)；"
                f"[特征检查]({path}/sanity/features/quality_gate.json)；[归一化检查]({path}/sanity/normalized/quality_gate.json)；"
                f"[评分输入检查]({path}/sanity/score/quality_gate.json)。", '']
        interpretation=r['controller_interpretation']
        lines += ['### 运行后怎么判断', '', f"Controller 的解释：{interpretation['interpretation']}", '',
            f"下一步：{interpretation['next_step']}", '',
            f"这段解释没有被独立验证。[原始判断记录]({path}/reflection.json)。", '']
    with (store.root/'research-trace.md').open('x') as stream: stream.write('\n'.join(lines))
    return {'json_sha256':file_hash(store.root/'research-trace.json'),
            'markdown_sha256':file_hash(store.root/'research-trace.md')}
