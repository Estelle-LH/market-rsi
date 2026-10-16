"""Optional R-requested original evidence, then the same executable R again.

The request protocol bounds execution, not algorithm choice. Reads use the
existing public FilingTools limits. All code runs in the original container;
the host only verifies requests, original observations and execution receipts.
"""
from copy import deepcopy
from pathlib import Path

from edgar_forecast_tools import FilingTools
from market_rsi import digest


def execution_value(*args):
    # Runtime import avoids a worker/helper import cycle; receipt semantics stay
    # in the original verifier and no candidate code is imported on host.
    from earnings_open_worker import execution_value as original
    return original(*args)


def requests(value):
    if type(value) is not dict or 'research_requests' not in value:return None
    rows=value['research_requests']
    if (set(value)!={'research_requests'} or type(rows) is not list or not 1<=len(rows)<=8
            or any(type(row) is not dict or set(row)!={'tool','arguments'}
                or type(row['tool']) is not str or row['tool'] not in {'read_file','search_files','calculate'}
                or type(row['arguments']) is not dict for row in rows)):
        raise ValueError('One bounded original-public-evidence request phase required')
    return deepcopy(rows)


def run(runner,source,payload,tools):
    first=runner.run(source,payload)
    chosen=requests(execution_value(first,source,payload))
    if chosen is None:return first
    observations=[dict(request=deepcopy(row),output=tools.dispatch(row['tool'],deepcopy(row['arguments'])))
        for row in chosen]
    following=dict(deepcopy(payload),research_observations=observations)
    final=runner.run(source,following)
    if requests(execution_value(final,source,following)) is not None:
        raise ValueError('R requested another evidence phase; preserve failure, no automatic loop')
    return dict(final,request_execution=first,research_observations=observations)


def verify(execution,source,payload,company):
    if 'request_execution' not in execution and 'research_observations' not in execution:
        value=execution_value(execution,source,payload)
        if requests(value) is not None:raise ValueError('Unfulfilled R evidence request cannot become advice')
        return value
    if 'request_execution' not in execution or 'research_observations' not in execution:
        raise ValueError('Incomplete original R evidence execution')
    chosen=requests(execution_value(execution['request_execution'],source,payload))
    if chosen is None:raise ValueError('Evidence was not requested by the actual selected R')
    # Fresh read-only reconstruction never adds calls to the original worker.
    tools=FilingTools(company)
    expected=[dict(request=deepcopy(row),output=tools.dispatch(row['tool'],deepcopy(row['arguments'])))
        for row in chosen]
    if digest(expected)!=digest(execution['research_observations']):
        raise ValueError('R observations differ from exact original allowed public data')
    following=dict(deepcopy(payload),research_observations=expected)
    value=execution_value(execution,source,following)
    if requests(value) is not None:raise ValueError('A second R request is not a completed computation')
    return value


def originals(execution):
    return [execution.get('request_execution'),execution] if 'request_execution' in execution else [execution]


def evidence_rows(execution):
    """Rejoin both original executions before reporting any extra tool cost.

Original-data correctness is also checked by verify(..., company) in the actual
worker. This projection never treats an unfulfilled request as observed work.
"""
    if 'request_execution' not in execution:
        if 'research_observations' in execution:raise ValueError('Unrequested evidence cost')
        return []
    from supervisor_harness import capacity_feedback_engine as engine
    first=execution['request_execution']
    request=engine.read(engine.pin(Path(first['receipt']['path']).parent/'input.json'))
    chosen=requests(execution_value(first,request['source'],request['payload']))
    rows=execution.get('research_observations')
    if (chosen is None or type(rows) is not list or len(rows)!=len(chosen)
            or any(type(row) is not dict or set(row)!={'request','output'}
                or row['request']!=expected for row,expected in zip(rows,chosen))):
        raise ValueError('R evidence costs differ from actual original requests')
    value=execution_value(execution,request['source'],dict(request['payload'],research_observations=rows))
    if requests(value) is not None:raise ValueError('Unfinished R evidence computation')
    return deepcopy(rows)


def public_evidence(execution):
    rows=evidence_rows(execution)
    if not rows:return None
    return {'schema':'earnings_public_researcher_tools_v1','observations':rows,
        'request_execution_sha256':execution['request_execution']['receipt']['sha256'],
        'execution_sha256':execution['receipt']['sha256']}
