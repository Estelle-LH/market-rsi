CASES = [
    {
        'input': {
            'stage': 'forecast',
            'questions': '# Edgar Forecast Bench\n- company: ALICO, INC.\n- form: 10-Q\n- filed: 20260204\nQuestion: What is the value for Cash paid for interest, net of amounts capitalized for the three months ended December 31, 2025?',
            'filing_index': 'date_filed\tform_type\taccession\tpath\n2025-11-24\t10-K\t0000003545-25-000140\tfilings/10-K_2025-11-24_0000003545-25-000140.md\n2025-08-12\t10-Q\t0000003545-25-000104\tfilings/10-Q_2025-08-12_0000003545-25-000104.md\n2025-05-13\t10-Q\t0000003545-25-000079\tfilings/10-Q_2025-05-13_0000003545-25-000079.md\n2025-02-12\t10-Q\t0000003545-25-000030\tfilings/10-Q_2025-02-12_0000003545-25-000030.md\n',
            'records': []
        },
        'expected': {
            'research_requests': [
                {'tool': 'read_file', 'arguments': {'path': 'filings/10-K_2025-11-24_0000003545-25-000140.md', 'offset': 0, 'characters': 20000}},
                {'tool': 'read_file', 'arguments': {'path': 'filings/10-Q_2025-08-12_0000003545-25-000104.md', 'offset': 0, 'characters': 20000}},
                {'tool': 'read_file', 'arguments': {'path': 'filings/10-Q_2025-08-12_0000003545-25-000104.md', 'offset': 20000, 'characters': 20000}},
                {'tool': 'read_file', 'arguments': {'path': 'filings/10-Q_2025-08-12_0000003545-25-000104.md', 'offset': 40000, 'characters': 20000}},
                {'tool': 'read_file', 'arguments': {'path': 'filings/10-Q_2025-05-13_0000003545-25-000079.md', 'offset': 0, 'characters': 20000}},
                {'tool': 'read_file', 'arguments': {'path': 'filings/10-Q_2025-05-13_0000003545-25-000079.md', 'offset': 20000, 'characters': 20000}},
                {'tool': 'read_file', 'arguments': {'path': 'filings/10-Q_2025-05-13_0000003545-25-000079.md', 'offset': 40000, 'characters': 20000}},
                {'tool': 'read_file', 'arguments': {'path': 'filings/10-Q_2025-02-12_0000003545-25-000030.md', 'offset': 20000, 'characters': 20000}}
            ]
        }
    },
    {
        'input': {
            'stage': 'forecast', 'questions': 'Cash paid for interest, net of amounts capitalized',
            'filing_index': 'date_filed\tform_type\taccession\tpath\n2025-02-12\t10-Q\tfixture\tfilings/fixture_cash.md\n',
            'records': [],
            'research_observations': [
                {'request': {'tool': 'read_file', 'arguments': {'path': 'filings/fixture_cash.md', 'offset': 0, 'characters': 20000}}, 'output': {'path': 'filings/fixture_cash.md', 'offset': 0, 'fixture_kind': 'constructed_not_original', 'text': 'Consolidated\nin thousands\n| |3 months ended 2024-12-31|\n|Cash paid for interest, net of amounts capitalized|$(12)|\n|Adjustments to reconcile net income to net cash used in operating activities| |\n'}}
            ]
        },
        'expected': {
            'stage': 'forecast',
            'historical_cells': [
                {'kind': 'fact', 'measure': 'cash_paid_interest_net_capitalized', 'segment': 'consolidated', 'period_end': '2024-12-31', 'duration_months': 3, 'unit': 'USD in thousands', 'value': -12, 'literal': '$(12)', 'source_path': 'filings/fixture_cash.md', 'source_sha256': None, 'offset': 56, 'quote': '|Cash paid for interest, net of amounts capitalized|$(12)|', 'headers': [{'offset': 0, 'quote': 'Consolidated'}, {'offset': 13, 'quote': 'in thousands'}, {'offset': 26, 'quote': '| |3 months ended 2024-12-31|'}], 'state_sha256': []}
            ],
            'derived_quarters': [], 'forecasts': [], 'unknowns': [], 'record_bindings': [], 'omitted_record_binding_count': 0,
            'guidance': 'Bind explicit historical periods, durations, units, segments and printed signs. Unknown is not zero. Derived quarters are calculations, not reported facts or forecasts. Preserve actual state bindings; never substitute a receipt hash for a source hash. Before forecasting, require an original-tool cold probe and independent matched-score review. The constructed literal cases are not original-table validation or evidence of benefit or adoption.',
            'truncated': False
        }
    },
    {
        'input': {
            'stage': 'controller', 'questions': 'Cash paid for interest', 'research_objective': 'Repair explicit table bindings; compare matched original scores.', 'feedback': {'untrusted_note': 'Do not infer a gain from more records.'},
            'filing_index': 'date_filed\tform_type\taccession\tpath\n2025-02-12\t10-Q\tfixture\tfilings/fixture_ambiguous.md\n',
            'records': [],
            'research_observations': [
                {'request': {'tool': 'read_file', 'arguments': {'path': 'filings/fixture_ambiguous.md', 'offset': 0, 'characters': 20000}}, 'output': {'path': 'filings/fixture_ambiguous.md', 'offset': 0, 'fixture_kind': 'constructed_not_original', 'text': 'Consolidated\nin thousands\n| |2024|2023|\n|Cash paid for interest|1|2|\n'}}
            ]
        },
        'expected': {
            'stage': 'controller', 'historical_cells': [], 'derived_quarters': [], 'forecasts': [],
            'unknowns': [
                {'source_path': 'filings/fixture_ambiguous.md', 'offset': 40, 'column': 1, 'literal': '1', 'reason': 'missing_period_or_duration'},
                {'source_path': 'filings/fixture_ambiguous.md', 'offset': 40, 'column': 2, 'literal': '2', 'reason': 'missing_period_or_duration'}
            ],
            'record_bindings': [], 'omitted_record_binding_count': 0,
            'guidance': 'Bind explicit historical periods, durations, units, segments and printed signs. Unknown is not zero. Derived quarters are calculations, not reported facts or forecasts. Preserve actual state bindings; never substitute a receipt hash for a source hash. Before forecasting, require an original-tool cold probe and independent matched-score review. The constructed literal cases are not original-table validation or evidence of benefit or adoption.',
            'truncated': False
        }
    },
    {
        'input': {
            'stage': 'controller', 'questions': '', 'filing_index': '', 'research_objective': 'Keep assumptions separate from historical cells.', 'feedback': {},
            'records': [{'sha256': 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', 'record': {'kind': 'assumption', 'hypothesis': 'Seasonality persists.'}}]
        },
        'expected': {
            'stage': 'controller', 'historical_cells': [], 'derived_quarters': [], 'forecasts': [], 'unknowns': [{'reason': 'no_returned_table_evidence'}],
            'record_bindings': [{'sha256': 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', 'record': {'kind': 'assumption', 'hypothesis': 'Seasonality persists.'}}],
            'omitted_record_binding_count': 0,
            'guidance': 'Bind explicit historical periods, durations, units, segments and printed signs. Unknown is not zero. Derived quarters are calculations, not reported facts or forecasts. Preserve actual state bindings; never substitute a receipt hash for a source hash. Before forecasting, require an original-tool cold probe and independent matched-score review. The constructed literal cases are not original-table validation or evidence of benefit or adoption.',
            'truncated': False
        }
    },
    {
        'input': {
            'stage': 'forecast', 'questions': 'Alico Citrus total operating expenses',
            'filing_index': 'date_filed\tform_type\taccession\tpath\n2025-05-13\t10-Q\tfixture\tfilings/fixture_segment.md\n',
            'records': [],
            'research_observations': [
                {'request': {'tool': 'read_file', 'arguments': {'path': 'filings/fixture_segment.md', 'offset': 0, 'characters': 20000}}, 'output': {'path': 'filings/fixture_segment.md', 'offset': 0, 'fixture_kind': 'constructed_not_original', 'text': 'Alico Citrus (in thousands)\n| |3 months ended 2024-12-31|6 months ended 2025-03-31|\n|**Total operating expenses**|10|25|\n'}}
            ]
        },
        'expected': {
            'stage': 'forecast',
            'historical_cells': [
                {'kind': 'fact', 'measure': 'operating_expenses', 'segment': 'Alico Citrus', 'period_end': '2024-12-31', 'duration_months': 3, 'unit': 'USD in thousands', 'value': 10, 'literal': '10', 'source_path': 'filings/fixture_segment.md', 'source_sha256': None, 'offset': 84, 'quote': '|**Total operating expenses**|10|25|', 'headers': [{'offset': 0, 'quote': 'Alico Citrus (in thousands)'}, {'offset': 27, 'quote': '| |3 months ended 2024-12-31|6 months ended 2025-03-31|'}], 'state_sha256': []},
                {'kind': 'fact', 'measure': 'operating_expenses', 'segment': 'Alico Citrus', 'period_end': '2025-03-31', 'duration_months': 6, 'unit': 'USD in thousands', 'value': 25, 'literal': '25', 'source_path': 'filings/fixture_segment.md', 'source_sha256': None, 'offset': 84, 'quote': '|**Total operating expenses**|10|25|', 'headers': [{'offset': 0, 'quote': 'Alico Citrus (in thousands)'}, {'offset': 27, 'quote': '| |3 months ended 2024-12-31|6 months ended 2025-03-31|'}], 'state_sha256': []}
            ],
            'derived_quarters': [{'kind': 'calculation', 'measure': 'operating_expenses', 'segment': 'Alico Citrus', 'period_end': '2025-03-31', 'duration_months': 3, 'unit': 'USD in thousands', 'value': 15, 'inputs': [{'historical_cell': 1}, {'historical_cell': 0}], 'expression': 'c1 - c0'}],
            'forecasts': [], 'unknowns': [], 'record_bindings': [], 'omitted_record_binding_count': 0,
            'guidance': 'Bind explicit historical periods, durations, units, segments and printed signs. Unknown is not zero. Derived quarters are calculations, not reported facts or forecasts. Preserve actual state bindings; never substitute a receipt hash for a source hash. Before forecasting, require an original-tool cold probe and independent matched-score review. The constructed literal cases are not original-table validation or evidence of benefit or adoption.',
            'truncated': False
        }
    }
]
