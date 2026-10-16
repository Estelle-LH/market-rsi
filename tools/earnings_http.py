"""Original retry-free protocol plus successful raw-wire receipts; no secrets."""
import http.client
import json
import os
import re

from edgar_forecast_openai import OpenAIHTTP, ProviderHTTPError


def strict_json(raw):
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON object key")
            result[key] = value
        return result

    def invalid_constant(value):
        raise ValueError("Nonfinite JSON constant")

    return json.loads(raw, object_pairs_hook=unique_object, parse_constant=invalid_constant)


def credential_reflected(raw, key):
    if not key:
        return False
    if key.encode() in raw:
        return True
    # One bounded lexical pass, independent of JSON envelope validity and
    # duplicate-key handling. Escaped backslashes are consumed only once.
    text = raw.decode(json.detect_encoding(raw), errors="replace")
    def unescape(match):
        value = match.group()
        if value[1] == "u":
            code = int(value[2:6], 16)
            if len(value) == 12:
                code = 0x10000 + ((code - 0xD800) << 10) + int(value[8:12], 16) - 0xDC00
            return chr(code)
        return {'"': '"', "\\": "\\", "/": "/", "b": "\b", "f": "\f",
                "n": "\n", "r": "\r", "t": "\t"}[value[1]]
    decoded = re.sub(r'\\u[dD][89aAbB][0-9a-fA-F]{2}\\u[dD][c-fC-F][0-9a-fA-F]{2}|\\(?:u[0-9a-fA-F]{4}|["\\/bfnrt])',
                     unescape, text)
    return key in decoded


def save_bytes(path, data):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


class RawOpenAIHTTP(OpenAIHTTP):
    def __init__(self, key, timeout=60):
        super().__init__(key, timeout)
        self.record_prefix = None

    def post(self, path, payload):
        prefix, self.record_prefix = self.record_prefix, None
        if path not in {"/v1/responses/input_tokens", "/v1/responses"}:
            raise ValueError("Unsupported API endpoint")
        if prefix is None or not prefix.with_suffix(".intent.json").is_file():
            raise ValueError("Durable actual-send intent required")
        connection = http.client.HTTPSConnection("api.openai.com", timeout=self.timeout)
        try:
            connection.request("POST", path, json.dumps(payload),
                               {"Authorization": "Bearer " + self.key, "Content-Type": "application/json"})
            response = connection.getresponse()
            request_id = response.getheader("x-request-id")
            if (not isinstance(request_id, str) or (self.key and self.key in request_id)
                    or not re.fullmatch(r"req_[A-Za-z0-9_-]{1,100}", request_id)):
                request_id = None
            if response.status != 200:
                code = None
                try:
                    code = strict_json(response.read(65536)).get("error", {}).get("code")
                except (ValueError, AttributeError):
                    pass
                # Raw error messages can echo credentials; retain curated error only.
                raise ProviderHTTPError(response.status, request_id, code)
            raw = response.read(16_000_001)
            if credential_reflected(raw, self.key):
                raise ValueError("Credential reflected by provider; raw persistence refused")
            save_bytes(prefix.with_suffix(".raw.bin"), raw)
            if len(raw) > 16_000_000:
                raise ValueError("API response byte limit; retained bounded prefix")
            result = strict_json(raw)
            result["_request_id"] = request_id
            return result
        finally:
            connection.close()
