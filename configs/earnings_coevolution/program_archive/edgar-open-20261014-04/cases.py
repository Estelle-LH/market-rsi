CASES = [
    {
        'input': {'tool': 'read_file', 'arguments': {'path': 'filing_index.tsv', 'offset': 0, 'characters': 4}, 'files': {'filing_index.tsv': 'ABCDEFGH'}},
        'expected': {'path': 'filing_index.tsv', 'offset': 0, 'characters': 4, 'text': 'ABCD', 'next_offset': 4, 'eof': False, 'max_characters': 16000}
    },
    {
        'input': {'tool': 'read_file', 'arguments': {'path': 'filing_index.tsv', 'offset': 4, 'characters': 4}, 'files': {'filing_index.tsv': 'ABCDEFGH'}},
        'expected': {'path': 'filing_index.tsv', 'offset': 4, 'characters': 4, 'text': 'EFGH', 'next_offset': None, 'eof': True, 'max_characters': 16000}
    },
    {
        'input': {'tool': 'read_file', 'arguments': {'path': 'report.txt', 'offset': 1, 'characters': 16000}, 'files': {'report.txt': 'AΔ\nZ', 'questions.md': 'Q'}},
        'expected': {'path': 'report.txt', 'offset': 1, 'characters': 3, 'text': 'Δ\nZ', 'next_offset': None, 'eof': True, 'max_characters': 16000}
    },
    {
        'input': {'tool': 'read_file', 'arguments': {'path': 'filing_index.tsv', 'offset': 0, 'characters': 22400}, 'files': {'filing_index.tsv': 'ABCDEFGH'}},
        'expected': {'error': {'code': 'invalid_characters', 'message': 'characters must be an integer from 1 through 16000. Read at most 16000, then continue using next_offset.', 'minimum': 1, 'maximum': 16000}}
    },
    {
        'input': {'tool': 'read_file', 'arguments': {'path': 'filing_index.tsv', 'offset': 8, 'characters': 4}, 'files': {'filing_index.tsv': 'ABCDEFGH'}},
        'expected': {'path': 'filing_index.tsv', 'offset': 8, 'characters': 0, 'text': '', 'next_offset': None, 'eof': True, 'max_characters': 16000}
    },
    {
        'input': {'tool': 'read_file', 'arguments': {'path': '../private.txt', 'offset': 0, 'characters': 4}, 'files': {'report.txt': 'unchanged', 'questions.md': 'Q'}},
        'expected': {'error': {'code': 'file_not_available', 'message': 'path is not present in the supplied files; no other files are accessible.'}}
    },
    {
        'input': {'tool': 'read_file', 'arguments': {'path': 'filing_index.tsv', 'offset': True, 'characters': 4}, 'files': {'filing_index.tsv': 'ABCDEFGH'}},
        'expected': {'error': {'code': 'invalid_offset', 'message': 'offset must be a nonnegative integer character index.'}}
    },
    {
        'input': {'tool': 'not_read_file', 'arguments': {}, 'files': {}},
        'expected': {'error': {'code': 'unsupported_tool', 'message': 'Only the declared read_file tool is handled by this program.'}}
    }
]
