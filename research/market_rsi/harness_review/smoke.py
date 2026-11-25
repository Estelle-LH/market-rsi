"""Offline check for the exported harness source and the Review declaration."""
import ast
import json
from pathlib import Path
import sys
from types import ModuleType
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
SOURCE = HERE / 'source'
TRANSITION = 'edgar25_depth_frontier_v5'
MARKER = 'edgar25_independent_q12_public_composition_v1'


def load_function(source, name, namespace):
    tree = ast.parse(source)
    fn = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name)
    exec(compile(ast.Module(body=[fn], type_ignores=[]), '<exported harness source>', 'exec'), namespace)
    return namespace[name]


class ExportTests(unittest.TestCase):
    def test_source_and_record(self):
        for path in SOURCE.glob('*.py'):
            ast.parse(path.read_text(), filename=str(path))
        result = json.loads((HERE / 'evidence.json').read_text())
        base = result['last_complete_training_panel']
        self.assertEqual((base['companies'], base['targets']), (25, 125))
        self.assertEqual((base['candidate_mean'], base['incumbent_mean']), (3.04, 3.18))

    @unittest.skipUnless((HERE / 'review-declaration.patch').exists(), 'current Q12 snapshot only')
    def test_review_uses_the_authenticated_q12_contract(self):
        coevolution = (SOURCE / 'earnings_population_coevolution.py').read_text()
        layered = (SOURCE / 'earnings_population_layered.py').read_text()
        hunk = (HERE / 'review-declaration.patch').read_text().splitlines(keepends=True)[3:]
        before = ''.join(line[1:] for line in hunk if line.startswith((' ', '-')))
        after = ''.join(line[1:] for line in hunk if line.startswith((' ', '+')))
        self.assertEqual(coevolution.count(before), 1)

        hypotheses = [{'hypothesis_id': f'slot-{i}', 'change_axis': 'H'} for i in range(1, 17)]
        frontier = dict(schema=TRANSITION, generation=9, expansions=[
            dict(parent_id='root', children=hypotheses)])
        claim = dict(generation=9, logical_round=29, parent_id='root',
                     frontier='synthetic-frontier', hypothesis_id='slot-12')
        origin = dict(prospective_public_local_composition=MARKER, frontier_expansion='synthetic-claim',
                      root_child_ordinal=12)
        q12 = ModuleType('earnings_population_independent_q12')
        q12.is_origin = lambda value: value.get('prospective_public_local_composition') == MARKER

        def authenticate(value):
            if value != origin:
                raise ValueError('Synthetic origin binding mismatch')
            return dict(frontier=frontier, claim=claim, contract=hypotheses[11])

        q12.context = authenticate
        layer = ModuleType('earnings_population_layered')
        layer_values = dict(TRANSITION_SCHEMA=TRANSITION, BREADTH16_POLICY='synthetic-policy', SCHEMA='generic')
        breadth = load_function(layered, 'child_breadth', layer_values)
        layer.slot_resolution = load_function(layered, 'slot_resolution', layer_values)

        def declaration(source):
            return load_function(source, 'declared_test',
                                 dict(expansion=lambda _: claim, saved=lambda _: frontier))

        broken = declaration(coevolution)
        repaired = declaration(coevolution.replace(before, after))
        with patch.dict(sys.modules, {layer.__name__: layer, q12.__name__: q12}):
            with self.assertRaisesRegex(ValueError, 'requires exact breadth16'):
                broken(origin)
            projection = repaired(origin)
            self.assertEqual((projection['slot_hypothesis_id'], projection['change_axis']), ('slot-12', 'H'))
            with self.assertRaisesRegex(ValueError, 'origin binding mismatch'):
                repaired(dict(origin, root_child_ordinal=11))
            with self.assertRaisesRegex(ValueError, 'requires exact breadth16'):
                breadth(frontier)


if __name__ == '__main__':
    unittest.main(verbosity=2)
