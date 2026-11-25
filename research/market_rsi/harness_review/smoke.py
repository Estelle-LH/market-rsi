import ast
import json
from pathlib import Path

here = Path(__file__).resolve().parent
for file in (here / 'source').glob('*.py'):
    ast.parse(file.read_text(), filename=str(file))
result = json.loads((here / 'evidence.json').read_text())['round17_incumbent']
assert (result['companies'], result['targets']) == (25, 125)
assert result['total_points'] / result['companies'] == result['candidate_mean'] == 3.18
assert result['selected'] == 'candidate'
print('Source parses; verified aggregate arithmetic for 3.18 / 5.')
