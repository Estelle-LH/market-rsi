"""A bounded, single-file read interface over explicitly supplied text only."""

PROGRAM = {
    'axis': 'H',
    'tools': [{
        'name': 'read_file',
        'description': 'Read an unchanged character chunk from one explicitly supplied logical filing, questions.md, or filing_index.tsv. Offsets are zero-based character offsets. Request 1 through 16000 characters per call (hard maximum 16000). The result contains text, the actual characters returned, next_offset, and eof. To continue the same file, pass next_offset as offset in a new call; stop when eof is true and next_offset is null. This tool never automatically reads another chunk or accesses other files.',
        'parameters': {
            'type': 'object',
            'properties': {
                'path': {'type': 'string', 'description': 'Exact supplied logical filename; no path resolution or host filesystem access.'},
                'offset': {'type': 'integer', 'minimum': 0, 'description': 'Zero-based character offset; use the previous next_offset for continuation.'},
                'characters': {'type': 'integer', 'minimum': 1, 'maximum': 16000, 'description': 'Requested characters, from 1 through 16000 inclusive; fewer may be returned at EOF.'}
            },
            'required': ['path', 'offset', 'characters'],
            'additionalProperties': False
        }
    }]
}

MAX_CHARACTERS = 16000


def _error(code, message, **details):
    error = {'code': code, 'message': message}
    error.update(details)
    return {'error': error}


def run(payload):
    # No filesystem, network, broker, state, scorer, or model operations.
    # Each call returns only one bounded slice, with no automatic continuation.
    if not isinstance(payload, dict):
        return _error('invalid_payload', 'Expected an object containing tool, arguments, and files.')
    if payload.get('tool') != 'read_file':
        return _error('unsupported_tool', 'Only the declared read_file tool is handled by this program.')
    arguments = payload.get('arguments')
    if not isinstance(arguments, dict) or set(arguments) != {'path', 'offset', 'characters'}:
        return _error('invalid_arguments', 'read_file requires exactly path, offset, and characters.')
    path = arguments['path']
    offset = arguments['offset']
    characters = arguments['characters']
    if not isinstance(path, str) or not path:
        return _error('invalid_path', 'path must be a nonempty exact supplied logical filename.')
    if type(offset) is not int or offset < 0:
        return _error('invalid_offset', 'offset must be a nonnegative integer character index.')
    if type(characters) is not int or not 1 <= characters <= MAX_CHARACTERS:
        return _error('invalid_characters', 'characters must be an integer from 1 through 16000. Read at most 16000, then continue using next_offset.', minimum=1, maximum=MAX_CHARACTERS)
    files = payload.get('files')
    if not isinstance(files, dict):
        return _error('invalid_files', 'files must map supplied logical filenames to their text.')
    # Exact-key lookup only: no normalization, aliases, fallback files, or discovery.
    if path not in files:
        return _error('file_not_available', 'path is not present in the supplied files; no other files are accessible.')
    content = files[path]
    if not isinstance(content, str):
        return _error('invalid_file_text', 'The requested supplied file must contain text.')
    text = content[offset:offset + characters]
    end_offset = offset + len(text)
    eof = end_offset >= len(content)
    return {
        'path': path,
        'offset': offset,
        'characters': len(text),
        'text': text,
        'next_offset': None if eof else end_offset,
        'eof': eof,
        'max_characters': MAX_CHARACTERS
    }
