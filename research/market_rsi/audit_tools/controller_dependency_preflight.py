"""Offline SDK/tokenizer readiness receipt; never contacts a model provider.

Supplement the published CPU harness identity with the exact installed SDK
environment. A PASS is setup evidence, not source admission or a paid dispatch.
"""
import argparse
import importlib
import importlib.metadata as metadata
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from market_rsi import digest, file_hash, fresh_json, load_json
from codex_glm_provider import TinkerGLMBackend, CHAT_TEMPLATE_SHA256, TOKENIZER_REVISION
from data_scientist_harness.store import runtime_identity
from data_scientist_harness.release import source_hashes, validate_release

PINS = {'tinker':'0.25.0', 'transformers':'5.5.4', 'python-dotenv':'1.2.2',
        'jinja2':'3.1.6', 'tokenizers':'0.22.2'}
MODULES = {'tinker':'tinker', 'transformers':'transformers', 'python-dotenv':'dotenv',
           'jinja2':'jinja2', 'tokenizers':'tokenizers'}


def inspect(release_path, tokenizer_cache):
    runtime = runtime_identity()
    release = load_json(release_path)
    validate_release(release, source_hashes(), runtime)
    identities = {}
    for package, expected in PINS.items():
        if metadata.version(package) != expected:
            raise ValueError('controller SDK version mismatch: '+package)
        module = importlib.import_module(MODULES[package])
        path = Path(module.__file__).resolve()
        if not path.is_relative_to(Path(sys.prefix).resolve()):
            raise ValueError('controller dependency imported outside isolated environment')
        identities[package] = {'version':expected, 'module_path':str(path), 'module_sha256':file_hash(path)}
    # Constructor loads ONLY the pinned local tokenizer. Sampling is prohibited
    # here; a noncredential ensures this cannot be mistaken for API validation.
    backend = TinkerGLMBackend('offline-noncredential', tokenizer_cache)
    encoded = backend.encode({'messages':[{'role':'user','content':'Offline tool-schema encoding test.'}],
        'tools':[{'type':'function','function':{'name':'inspect_harness','description':'Offline test.',
            'parameters':{'type':'object','properties':{},'required':[]}}}]})
    if not encoded['token_ids'] or backend._sampler is not None:
        raise ValueError('offline tokenizer preflight did not stay offline')
    distributions = sorted((d.metadata['Name'], d.version) for d in metadata.distributions())
    return {'schema':'market_rsi_controller_dependency_preflight_v1','passed':True,
        'script_sha256':file_hash(__file__), 'release_sha256':release['release_sha256'],
        'runtime':runtime,'controller_packages':identities,
        'all_installed_distributions':distributions,'distributions_sha256':digest(distributions),
        'tokenizer_revision':TOKENIZER_REVISION,'chat_template_sha256':CHAT_TEMPLATE_SHA256,
        'synthetic_encoded_tokens':len(encoded['token_ids']),
        'provider_calls':0,'credentials_read':False,'market_data_read':False,
        'source_admitted':False,'new_dev_test_opened':False}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('output','release','tokenizer-cache'):
        parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists(): raise ValueError('fresh preflight receipt required')
    result=inspect(args.release,args.tokenizer_cache)
    result['result_sha256']=digest(result)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    fresh_json(args.output,result)
    print({k:result[k] for k in ('passed','synthetic_encoded_tokens','provider_calls','result_sha256')})
