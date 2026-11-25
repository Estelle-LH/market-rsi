CASES = [
    {
        'input': {
            'stage': 'forecast',
            'questions': '# Recover original table context for this grounded numeric note.',
            'filing_index': 'path\tform\nfilings/10-Q_2025-08-12_0000003545-25-000104.md\t10-Q\n',
            'records': [{'sha256': '1111111111111111111111111111111111111111111111111111111111111111', 'record': {'kind': 'fact', 'period_end': '2025-06-30', 'unit': 'USD_thousands', 'value': -139008, 'source_path': 'filings/10-Q_2025-08-12_0000003545-25-000104.md', 'source_sha256': None, 'offset': 10000, 'quote': '| &nbsp;&nbsp;&nbsp;Net (loss) income | $(139008) | $24514 |', 'literal': '$(139008)'}}]
        },
        'expected': {'research_requests': [{'tool': 'read_file', 'arguments': {'path': 'filings/10-Q_2025-08-12_0000003545-25-000104.md', 'offset': 2000, 'characters': 20000}}]}
    },
    {
        'input': {
            'stage': 'forecast',
            'questions': '# Find cash interest and segment operating inputs; there are no state records.',
            'filing_index': 'path\tform\nfilings/10-Q_2025-08-12_0000003545-25-000104.md\t10-Q\n',
            'records': []
        },
        'expected': {'research_requests': [
            {'tool': 'search_files', 'arguments': {'query': 'Cash paid for interest', 'path_prefix': 'filings/10-Q_2025-08-12_0000003545-25-000104.md', 'max_hits': 5}},
            {'tool': 'search_files', 'arguments': {'query': 'Land and Other Leasing', 'path_prefix': 'filings/10-Q_2025-08-12_0000003545-25-000104.md', 'max_hits': 5}},
            {'tool': 'search_files', 'arguments': {'query': 'Total operating expenses', 'path_prefix': 'filings/10-Q_2025-08-12_0000003545-25-000104.md', 'max_hits': 5}},
            {'tool': 'search_files', 'arguments': {'query': 'Net cash', 'path_prefix': 'filings/10-Q_2025-08-12_0000003545-25-000104.md', 'max_hits': 5}}
        ]}
    },
    {
        'input': {
            'stage': 'forecast',
            'questions': '# Verbatim pre-cutoff cash-flow excerpt inspected in the August filing. This isolated fixture rebases the excerpt to offset zero; it does not assert the excerpt starts at zero in the full filing. No full-source hash was returned.',
            'filing_index': 'path\tform\nfilings/10-Q_2025-08-12_0000003545-25-000104.md\t10-Q\n',
            'records': [],
            'research_observations': [{
                'request': {'tool': 'read_file', 'arguments': {'path': 'filings/10-Q_2025-08-12_0000003545-25-000104.md', 'offset': 0, 'characters': 20000}},
                'output': {'path': 'filings/10-Q_2025-08-12_0000003545-25-000104.md', 'offset': 0, 'text': '**ALICO, INC.**\n\n**CONDENSED CONSOLIDATED STATEMENTS OF CASH FLOWS (UNAUDITED)** \n\n**(in thousands)**\n\n---\n\n|  |  |  |\n|---|---|---|\n|  | **Nine Months Ended June 30,** ||\n|  | **2025** | **2024** |\n| **Net cash provided by (used in) operating activities** |  |  |\n| &nbsp;&nbsp;&nbsp;Net (loss) income | $(139008) | $24514 |\n'}
            }]
        },
        'expected': {
            'stage': 'forecast',
            'historical_cells': [
                {'kind': 'fact', 'measure': 'net_income', 'segment': 'Consolidated', 'basis': 'accrual', 'period_end': '2025-06-30', 'duration_months': 9, 'unit': 'USD_thousands', 'value': -139008, 'literal': '$(139008)', 'column': 1, 'source_path': 'filings/10-Q_2025-08-12_0000003545-25-000104.md', 'source_sha256': None, 'offset': 265, 'quote': '| &nbsp;&nbsp;&nbsp;Net (loss) income | $(139008) | $24514 |', 'context': [
                    {'offset': 17, 'quote': '**CONDENSED CONSOLIDATED STATEMENTS OF CASH FLOWS (UNAUDITED)** '},
                    {'offset': 83, 'quote': '**(in thousands)**'},
                    {'offset': 133, 'quote': '|  | **Nine Months Ended June 30,** ||'},
                    {'offset': 172, 'quote': '|  | **2025** | **2024** |'}
                ], 'state_refs': []},
                {'kind': 'fact', 'measure': 'net_income', 'segment': 'Consolidated', 'basis': 'accrual', 'period_end': '2024-06-30', 'duration_months': 9, 'unit': 'USD_thousands', 'value': 24514, 'literal': '$24514', 'column': 2, 'source_path': 'filings/10-Q_2025-08-12_0000003545-25-000104.md', 'source_sha256': None, 'offset': 265, 'quote': '| &nbsp;&nbsp;&nbsp;Net (loss) income | $(139008) | $24514 |', 'context': [
                    {'offset': 17, 'quote': '**CONDENSED CONSOLIDATED STATEMENTS OF CASH FLOWS (UNAUDITED)** '},
                    {'offset': 83, 'quote': '**(in thousands)**'},
                    {'offset': 133, 'quote': '|  | **Nine Months Ended June 30,** ||'},
                    {'offset': 172, 'quote': '|  | **2025** | **2024** |'}
                ], 'state_refs': []}
            ],
            'derived_quarters': [], 'unknowns': [], 'state_bindings': [], 'leads': [],
            'guidance': 'Use explicitly bound historical cells; blanks and dashes are unknown. Cumulative differences are calculations, not reported quarters. Forecast separately. Missing source hashes remain unknown; existing state bindings are not new records.'
        }
    },
    {
        'input': {
            'stage': 'forecast',
            'questions': '# Synthetic alignment hypothesis: preserve bold negative expense totals, explicit duration groups and the exact supplied state binding. Do not treat blanks as zero.',
            'filing_index': 'path\nfilings/scope.md\n',
            'records': [{'sha256': '1111111111111111111111111111111111111111111111111111111111111111', 'record': {'kind': 'fact', 'period_end': '2025-06-30', 'unit': 'USD_thousands', 'value': -120, 'source_path': 'filings/scope.md', 'source_sha256': 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', 'offset': 128, 'quote': '| **Total operating expenses** | $**(120)** | — | $80 | |', 'literal': '$**(120)**'}}],
            'research_observations': [{
                'request': {'tool': 'read_file', 'arguments': {'path': 'filings/scope.md', 'offset': 0, 'characters': 20000}},
                'output': {'path': 'filings/scope.md', 'offset': 0, 'source_sha256': 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', 'text': '**Alico Citrus**\n(in thousands)\n| | Nine Months Ended June 30, || Six Months Ended March 31, ||\n| | 2025 | 2024 | 2025 | 2024 |\n| **Total operating expenses** | $**(120)** | — | $80 | |\n'}
            }]
        },
        'expected': {
            'stage': 'forecast',
            'historical_cells': [
                {'kind': 'fact', 'measure': 'citrus_expenses', 'segment': 'Alico Citrus', 'basis': 'accrual', 'period_end': '2025-06-30', 'duration_months': 9, 'unit': 'USD_thousands', 'value': -120, 'literal': '$**(120)**', 'column': 1, 'source_path': 'filings/scope.md', 'source_sha256': 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', 'offset': 128, 'quote': '| **Total operating expenses** | $**(120)** | — | $80 | |', 'context': [
                    {'offset': 0, 'quote': '**Alico Citrus**'},
                    {'offset': 17, 'quote': '(in thousands)'},
                    {'offset': 32, 'quote': '| | Nine Months Ended June 30, || Six Months Ended March 31, ||'},
                    {'offset': 96, 'quote': '| | 2025 | 2024 | 2025 | 2024 |'}
                ], 'state_refs': [0]},
                {'kind': 'fact', 'measure': 'citrus_expenses', 'segment': 'Alico Citrus', 'basis': 'accrual', 'period_end': '2025-03-31', 'duration_months': 6, 'unit': 'USD_thousands', 'value': 80, 'literal': '$80', 'column': 3, 'source_path': 'filings/scope.md', 'source_sha256': 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', 'offset': 128, 'quote': '| **Total operating expenses** | $**(120)** | — | $80 | |', 'context': [
                    {'offset': 0, 'quote': '**Alico Citrus**'},
                    {'offset': 17, 'quote': '(in thousands)'},
                    {'offset': 32, 'quote': '| | Nine Months Ended June 30, || Six Months Ended March 31, ||'},
                    {'offset': 96, 'quote': '| | 2025 | 2024 | 2025 | 2024 |'}
                ], 'state_refs': []}
            ],
            'derived_quarters': [{'kind': 'calculation', 'measure': 'citrus_expenses', 'segment': 'Alico Citrus', 'basis': 'accrual', 'period_end': '2025-06-30', 'duration_months': 3, 'unit': 'USD_thousands', 'value': -200, 'inputs': [0, 1], 'expression': 'inputs[0] - inputs[1]'}],
            'unknowns': [
                {'source_path': 'filings/scope.md', 'offset': 128, 'column': 2, 'literal': '—', 'reason': 'missing_or_ambiguous_value'},
                {'source_path': 'filings/scope.md', 'offset': 128, 'column': 4, 'literal': '', 'reason': 'missing_or_ambiguous_value'}
            ],
            'state_bindings': [{'sha256': '1111111111111111111111111111111111111111111111111111111111111111', 'record': {'kind': 'fact', 'period_end': '2025-06-30', 'unit': 'USD_thousands', 'value': -120, 'source_path': 'filings/scope.md', 'source_sha256': 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', 'offset': 128, 'quote': '| **Total operating expenses** | $**(120)** | — | $80 | |', 'literal': '$**(120)**'}}],
            'leads': [],
            'guidance': 'Use explicitly bound historical cells; blanks and dashes are unknown. Cumulative differences are calculations, not reported quarters. Forecast separately. Missing source hashes remain unknown; existing state bindings are not new records.'
        }
    },
    {
        'input': {
            'stage': 'controller',
            'questions': '# A year without a month/day and duration does not identify a quarter.',
            'research_objective': 'Evaluate table binding against matched original-score benefit, not extracted-cell count.',
            'feedback': {'ordinary_score_out_of_5': 1},
            'filing_index': 'path\nfilings/ambiguous.md\n',
            'records': [],
            'research_observations': [{
                'request': {'tool': 'read_file', 'arguments': {'path': 'filings/ambiguous.md', 'offset': 0, 'characters': 20000}},
                'output': {'path': 'filings/ambiguous.md', 'offset': 0, 'text': '**Consolidated**\n(in thousands)\n| | 2025 |\n| Cash paid for interest, net of amounts capitalized | $7 |\n'}
            }]
        },
        'expected': {
            'stage': 'controller', 'historical_cells': [], 'derived_quarters': [],
            'unknowns': [{'source_path': 'filings/ambiguous.md', 'offset': 43, 'column': 1, 'literal': '$7', 'reason': 'ambiguous_period'}],
            'state_bindings': [], 'leads': [],
            'guidance': 'Use explicitly bound historical cells; blanks and dashes are unknown. Cumulative differences are calculations, not reported quarters. Forecast separately. Missing source hashes remain unknown; existing state bindings are not new records. Judge matched original-score benefit and nonregression, not record count. This advice makes no adoption or score-gain claim.'
        }
    },
    {
        'input': {
            'stage': 'forecast',
            'questions': '# A failed read and a row-only search hit are not a successful table observation.',
            'filing_index': 'path\nfilings/10-Q_2025-08-12_0000003545-25-000104.md\n',
            'records': [],
            'research_observations': [
                {'request': {'tool': 'read_file', 'arguments': {'path': 'filings/10-Q_2025-08-12_0000003545-25-000104.md', 'offset': 20000, 'characters': 20000}}, 'output': {'ok': False, 'error': 'read unavailable'}},
                {'request': {'tool': 'search_files', 'arguments': {'query': 'Cash paid for interest', 'path_prefix': 'filings/10-Q_2025-08-12_0000003545-25-000104.md', 'max_hits': 5}}, 'output': {'hits': [{'line': 460, 'path': 'filings/10-Q_2025-08-12_0000003545-25-000104.md', 'text': '| &nbsp;&nbsp;&nbsp;Cash paid for interest, net of amounts capitalized | $2844 | $3337 |'}], 'total_matching_lines': 1}}
            ]
        },
        'expected': {
            'stage': 'forecast', 'historical_cells': [], 'derived_quarters': [],
            'unknowns': [
                {'request_index': 0, 'reason': 'failed_or_incomplete_observation'},
                {'reason': 'table_context_not_returned', 'detail': 'Search hits are leads only; original header, units and segment evidence are still needed through the ordinary evidence workflow.'}
            ],
            'state_bindings': [],
            'leads': [{'source_path': 'filings/10-Q_2025-08-12_0000003545-25-000104.md', 'line': 460, 'text': '| &nbsp;&nbsp;&nbsp;Cash paid for interest, net of amounts capitalized | $2844 | $3337 |'}],
            'guidance': 'Use explicitly bound historical cells; blanks and dashes are unknown. Cumulative differences are calculations, not reported quarters. Forecast separately. Missing source hashes remain unknown; existing state bindings are not new records.'
        }
    },
    {
        'input': {
            'stage': 'forecast',
            'questions': '# Eight overlapping successful-read fixtures with verbatim pre-cutoff rows and irrelevant financial rows. Excerpt offsets are rebased to zero. This volume/deduplication hypothesis is not a 120000-character benchmark or independent correctness proof.',
            'filing_index': 'path\tform\nfilings/10-Q_2025-08-12_0000003545-25-000104.md\t10-Q\n',
            'records': [],
            'research_observations': [
                {'request': {'tool': 'read_file', 'arguments': {'path': 'filings/10-Q_2025-08-12_0000003545-25-000104.md', 'offset': 0, 'characters': 20000}}, 'output': {'ok': True, 'value': {'path': 'filings/10-Q_2025-08-12_0000003545-25-000104.md', 'offset': 0, 'text': '**ALICO, INC.**\n\n**CONDENSED CONSOLIDATED STATEMENTS OF CASH FLOWS (UNAUDITED)** \n\n**(in thousands)**\n\n---\n\n|  |  |  |\n|---|---|---|\n|  | **Nine Months Ended June 30,** ||\n|  | **2025** | **2024** |\n| **Net cash provided by (used in) operating activities** |  |  |\n| &nbsp;&nbsp;&nbsp;Net (loss) income | $(139008) | $24514 |\n| &nbsp;&nbsp;&nbsp;Adjustments to reconcile net (loss) income to net cash provided by (used in) operating activities: |  |  |\n| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Depreciation, depletion and amortization | 170800 | 11317 |\n| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Amortization of debt issue costs | 127 | 176 |\n| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Gain on sale of property and equipment | (21400) | (81520) |\n| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Impairment of long-lived assets | 24966 |  |\n'}}},
                {'request': {'tool': 'read_file', 'arguments': {'path': 'filings/10-Q_2025-08-12_0000003545-25-000104.md', 'offset': 0, 'characters': 20000}}, 'output': {'path': 'filings/10-Q_2025-08-12_0000003545-25-000104.md', 'offset': 0, 'text': '**ALICO, INC.**\n\n**CONDENSED CONSOLIDATED STATEMENTS OF CASH FLOWS (UNAUDITED)** \n\n**(in thousands)**\n\n---\n\n|  |  |  |\n|---|---|---|\n|  | **Nine Months Ended June 30,** ||\n|  | **2025** | **2024** |\n| **Net cash provided by (used in) operating activities** |  |  |\n| &nbsp;&nbsp;&nbsp;Net (loss) income | $(139008) | $24514 |\n| &nbsp;&nbsp;&nbsp;Adjustments to reconcile net (loss) income to net cash provided by (used in) operating activities: |  |  |\n| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Depreciation, depletion and amortization | 170800 | 11317 |\n| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Amortization of debt issue costs | 127 | 176 |\n| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Gain on sale of property and equipment | (21400) | (81520) |\n| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Impairment of long-lived assets | 24966 |  |\n'}},
                {'request': {'tool': 'read_file', 'arguments': {'path': 'filings/10-Q_2025-08-12_0000003545-25-000104.md', 'offset': 0, 'characters': 20000}}, 'output': {'path': 'filings/10-Q_2025-08-12_0000003545-25-000104.md', 'offset': 0, 'text': '**ALICO, INC.**\n\n**CONDENSED CONSOLIDATED STATEMENTS OF CASH FLOWS (UNAUDITED)** \n\n**(in thousands)**\n\n---\n\n|  |  |  |\n|---|---|---|\n|  | **Nine Months Ended June 30,** ||\n|  | **2025** | **2024** |\n| **Net cash provided by (used in) operating activities** |  |  |\n| &nbsp;&nbsp;&nbsp;Net (loss) income | $(139008) | $24514 |\n| &nbsp;&nbsp;&nbsp;Adjustments to reconcile net (loss) income to net cash provided by (used in) operating activities: |  |  |\n| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Depreciation, depletion and amortization | 170800 | 11317 |\n| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Amortization of debt issue costs | 127 | 176 |\n| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Gain on sale of property and equipment | (21400) | (81520) |\n| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Impairment of long-lived assets | 24966 |  |\n'}},
                {'request': {'tool': 'read_file', 'arguments': {'path': 'filings/10-Q_2025-08-12_0000003545-25-000104.md', 'offset': 0, 'characters': 20000}}, 'output': {'path': 'filings/10-Q_2025-08-12_0000003545-25-000104.md', 'offset': 0, 'text': '**ALICO, INC.**\n\n**CONDENSED CONSOLIDATED STATEMENTS OF CASH FLOWS (UNAUDITED)** \n\n**(in thousands)**\n\n---\n\n|  |  |  |\n|---|---|---|\n|  | **Nine Months Ended June 30,** ||\n|  | **2025** | **2024** |\n| **Net cash provided by (used in) operating activities** |  |  |\n| &nbsp;&nbsp;&nbsp;Net (loss) income | $(139008) | $24514 |\n| &nbsp;&nbsp;&nbsp;Adjustments to reconcile net (loss) income to net cash provided by (used in) operating activities: |  |  |\n| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Depreciation, depletion and amortization | 170800 | 11317 |\n| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Amortization of debt issue costs | 127 | 176 |\n| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Gain on sale of property and equipment | (21400) | (81520) |\n| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Impairment of long-lived assets | 24966 |  |\n'}},
                {'request': {'tool': 'read_file', 'arguments': {'path': 'filings/10-Q_2025-08-12_0000003545-25-000104.md', 'offset': 0, 'characters': 20000}}, 'output': {'path': 'filings/10-Q_2025-08-12_0000003545-25-000104.md', 'offset': 0, 'text': '**ALICO, INC.**\n\n**CONDENSED CONSOLIDATED STATEMENTS OF CASH FLOWS (UNAUDITED)** \n\n**(in thousands)**\n\n---\n\n|  |  |  |\n|---|---|---|\n|  | **Nine Months Ended June 30,** ||\n|  | **2025** | **2024** |\n| **Net cash provided by (used in) operating activities** |  |  |\n| &nbsp;&nbsp;&nbsp;Net (loss) income | $(139008) | $24514 |\n| &nbsp;&nbsp;&nbsp;Adjustments to reconcile net (loss) income to net cash provided by (used in) operating activities: |  |  |\n| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Depreciation, depletion and amortization | 170800 | 11317 |\n| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Amortization of debt issue costs | 127 | 176 |\n| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Gain on sale of property and equipment | (21400) | (81520) |\n| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Impairment of long-lived assets | 24966 |  |\n'}},
                {'request': {'tool': 'read_file', 'arguments': {'path': 'filings/10-Q_2025-08-12_0000003545-25-000104.md', 'offset': 0, 'characters': 20000}}, 'output': {'path': 'filings/10-Q_2025-08-12_0000003545-25-000104.md', 'offset': 0, 'text': '**ALICO, INC.**\n\n**CONDENSED CONSOLIDATED STATEMENTS OF CASH FLOWS (UNAUDITED)** \n\n**(in thousands)**\n\n---\n\n|  |  |  |\n|---|---|---|\n|  | **Nine Months Ended June 30,** ||\n|  | **2025** | **2024** |\n| **Net cash provided by (used in) operating activities** |  |  |\n| &nbsp;&nbsp;&nbsp;Net (loss) income | $(139008) | $24514 |\n| &nbsp;&nbsp;&nbsp;Adjustments to reconcile net (loss) income to net cash provided by (used in) operating activities: |  |  |\n| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Depreciation, depletion and amortization | 170800 | 11317 |\n| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Amortization of debt issue costs | 127 | 176 |\n| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Gain on sale of property and equipment | (21400) | (81520) |\n| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Impairment of long-lived assets | 24966 |  |\n'}},
                {'request': {'tool': 'read_file', 'arguments': {'path': 'filings/10-Q_2025-08-12_0000003545-25-000104.md', 'offset': 0, 'characters': 20000}}, 'output': {'path': 'filings/10-Q_2025-08-12_0000003545-25-000104.md', 'offset': 0, 'text': '**ALICO, INC.**\n\n**CONDENSED CONSOLIDATED STATEMENTS OF CASH FLOWS (UNAUDITED)** \n\n**(in thousands)**\n\n---\n\n|  |  |  |\n|---|---|---|\n|  | **Nine Months Ended June 30,** ||\n|  | **2025** | **2024** |\n| **Net cash provided by (used in) operating activities** |  |  |\n| &nbsp;&nbsp;&nbsp;Net (loss) income | $(139008) | $24514 |\n| &nbsp;&nbsp;&nbsp;Adjustments to reconcile net (loss) income to net cash provided by (used in) operating activities: |  |  |\n| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Depreciation, depletion and amortization | 170800 | 11317 |\n| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Amortization of debt issue costs | 127 | 176 |\n| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Gain on sale of property and equipment | (21400) | (81520) |\n| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Impairment of long-lived assets | 24966 |  |\n'}},
                {'request': {'tool': 'read_file', 'arguments': {'path': 'filings/10-Q_2025-08-12_0000003545-25-000104.md', 'offset': 0, 'characters': 20000}}, 'output': {'path': 'filings/10-Q_2025-08-12_0000003545-25-000104.md', 'offset': 0, 'text': '**ALICO, INC.**\n\n**CONDENSED CONSOLIDATED STATEMENTS OF CASH FLOWS (UNAUDITED)** \n\n**(in thousands)**\n\n---\n\n|  |  |  |\n|---|---|---|\n|  | **Nine Months Ended June 30,** ||\n|  | **2025** | **2024** |\n| **Net cash provided by (used in) operating activities** |  |  |\n| &nbsp;&nbsp;&nbsp;Net (loss) income | $(139008) | $24514 |\n| &nbsp;&nbsp;&nbsp;Adjustments to reconcile net (loss) income to net cash provided by (used in) operating activities: |  |  |\n| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Depreciation, depletion and amortization | 170800 | 11317 |\n| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Amortization of debt issue costs | 127 | 176 |\n| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Gain on sale of property and equipment | (21400) | (81520) |\n| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Impairment of long-lived assets | 24966 |  |\n'}}
            ]
        },
        'expected': {
            'stage': 'forecast',
            'historical_cells': [
                {'kind': 'fact', 'measure': 'net_income', 'segment': 'Consolidated', 'basis': 'accrual', 'period_end': '2025-06-30', 'duration_months': 9, 'unit': 'USD_thousands', 'value': -139008, 'literal': '$(139008)', 'column': 1, 'source_path': 'filings/10-Q_2025-08-12_0000003545-25-000104.md', 'source_sha256': None, 'offset': 265, 'quote': '| &nbsp;&nbsp;&nbsp;Net (loss) income | $(139008) | $24514 |', 'context': [
                    {'offset': 17, 'quote': '**CONDENSED CONSOLIDATED STATEMENTS OF CASH FLOWS (UNAUDITED)** '},
                    {'offset': 83, 'quote': '**(in thousands)**'},
                    {'offset': 133, 'quote': '|  | **Nine Months Ended June 30,** ||'},
                    {'offset': 172, 'quote': '|  | **2025** | **2024** |'}
                ], 'state_refs': []},
                {'kind': 'fact', 'measure': 'net_income', 'segment': 'Consolidated', 'basis': 'accrual', 'period_end': '2024-06-30', 'duration_months': 9, 'unit': 'USD_thousands', 'value': 24514, 'literal': '$24514', 'column': 2, 'source_path': 'filings/10-Q_2025-08-12_0000003545-25-000104.md', 'source_sha256': None, 'offset': 265, 'quote': '| &nbsp;&nbsp;&nbsp;Net (loss) income | $(139008) | $24514 |', 'context': [
                    {'offset': 17, 'quote': '**CONDENSED CONSOLIDATED STATEMENTS OF CASH FLOWS (UNAUDITED)** '},
                    {'offset': 83, 'quote': '**(in thousands)**'},
                    {'offset': 133, 'quote': '|  | **Nine Months Ended June 30,** ||'},
                    {'offset': 172, 'quote': '|  | **2025** | **2024** |'}
                ], 'state_refs': []}
            ],
            'derived_quarters': [], 'unknowns': [], 'state_bindings': [], 'leads': [],
            'guidance': 'Use explicitly bound historical cells; blanks and dashes are unknown. Cumulative differences are calculations, not reported quarters. Forecast separately. Missing source hashes remain unknown; existing state bindings are not new records.'
        }
    }
]
