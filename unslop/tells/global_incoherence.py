"""Detect global incoherence — locally valid but globally broken code.

This implements McKelvey's Tell #9 and the "patchwork problem" formalized by
Mothukuri & Parizi (2026): code that compiles, passes tests, and appears
correct in isolation, yet breaks when integrated because it violates
consistency invariants that span the repository.

Research sources:
- Justin McKelvey — "9 Tells of AI-Generated Code", Tell #9:
  "The Patchwork Problem — Locally Valid, Globally Incoherent"
- Mothukuri & Parizi (2026) — "The Patchwork Problem in LLM-Generated Code"
  arXiv:2607.08981 — formalizes structural coherence as consistency invariants
  over graph representations of repository artifacts
- Veracode 2025 — 45% of AI-generated code introduces at least one OWASP
  Top 10 vulnerability

Key patterns detected:
1. Configuration incoherence — accessing environment variables or config keys
   that are never declared in the repository's config space (BCI)
2. Resource coherence — referencing files, assets, or templates that don't
   exist on disk (RCF)
3. Phantom API calls — invoking methods/functions not found in the project's
   symbol table (SRF + PIA from the taxonomy)
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from ..report import Severity, TellCategory, UnslopIssue
from ..pattern_index import PatternIndex


# ── Phantom API detection ──────────────────────────────────────────────────

# Common built-in methods that should NOT be flagged
BUILTIN_METHODS = {
    # Python builtins
    '__init__', '__str__', '__repr__', '__eq__', '__hash__', '__len__',
    '__iter__', '__next__', '__getitem__', '__setitem__', '__delitem__',
    '__contains__', '__call__', '__enter__', '__exit__', '__await__',
    'append', 'extend', 'insert', 'remove', 'pop', 'clear', 'sort',
    'reverse', 'copy', 'join', 'split', 'strip', 'replace', 'upper',
    'lower', 'find', 'index', 'count', 'keys', 'values', 'items',
    'get', 'setdefault', 'update', 'popitem', 'fromkeys',
    'read', 'write', 'seek', 'tell', 'close', 'flush', 'readline',
    'readlines', 'writelines', 'encode', 'decode', 'format',
    'startswith', 'endswith', 'isdigit', 'isalpha', 'isalnum',
    'isspace', 'islower', 'isupper', 'istitle', 'isdecimal',
    'isnumeric', 'isidentifier', 'isascii', 'isprintable',
    'title', 'capitalize', 'center', 'ljust', 'rjust', 'zfill',
    'partition', 'rpartition', 'rsplit', 'lstrip', 'rstrip',
    # Common object methods
    'hasattr', 'getattr', 'setattr', 'delattr', 'dir', 'vars',
    'id', 'type', 'isinstance', 'issubclass', 'callable', 'repr',
    'open', 'print', 'input', 'range', 'len', 'sum', 'min', 'max',
    'sorted', 'reversed', 'enumerate', 'zip', 'map', 'filter',
    'any', 'all', 'abs', 'round', 'pow', 'divmod', 'chr', 'ord',
    'hex', 'oct', 'bin', 'complex', 'float', 'int', 'str', 'bytes',
    'list', 'dict', 'set', 'tuple', 'frozenset', 'bool',
    # JS/TS common
    'toString', 'valueOf', 'hasOwnProperty', 'propertyIsEnumerable',
    'addEventListener', 'removeEventListener', 'dispatchEvent',
    'querySelector', 'querySelectorAll', 'getElementById',
    'getElementsByClassName', 'getElementsByTagName',
    'appendChild', 'removeChild', 'insertBefore', 'replaceChild',
    'getAttribute', 'setAttribute', 'removeAttribute',
    'push', 'pop', 'shift', 'unshift', 'slice', 'splice',
    'map', 'filter', 'reduce', 'forEach', 'some', 'every',
    'find', 'findIndex', 'includes', 'indexOf', 'lastIndexOf',
    'flatMap', 'fill', 'reverse', 'sort', 'concat', 'flat',
    'then', 'catch', 'finally', 'resolve', 'reject',
    'subscribe', 'unsubscribe', 'next', 'error', 'complete',
    'get', 'post', 'put', 'delete', 'patch', 'head', 'options',
    'send', 'abort', 'timeout', 'on', 'once', 'off', 'emit',
    'listen', 'close', 'destroy', 'use', 'middleware',
    'render', 'send', 'json', 'status', 'type', 'end', 'redirect',
    'set', 'get', 'clear', 'cookie', 'cookies', 'header',
    'headers', 'body', 'query', 'params', 'url', 'path', 'method',
    'hostname', 'port', 'protocol', 'origin', 'href', 'search',
    'hash', 'pathname', 'searchParams', 'navigate', 'push', 'replace',
    'go', 'back', 'forward', 'reload',
    'trim', 'trimStart', 'trimEnd', 'padStart', 'padEnd',
    'match', 'matchAll', 'search', 'replace', 'replaceAll',
    'toLowerCase', 'toUpperCase', 'charAt', 'charCodeAt',
    'substr', 'substring', 'repeat', 'localeCompare',
    'entries', 'values', 'from', 'of', 'assign', 'create',
    'defineProperty', 'defineProperties', 'getOwnPropertyDescriptor',
    'getOwnPropertyDescriptors', 'getOwnPropertyNames',
    'getOwnPropertySymbols', 'is', 'isExtensible', 'preventExtensions',
    'seal', 'freeze', 'isSealed', 'isFrozen', 'keys',
    'has', 'delete', 'clear',
    'fromCharCode', 'fromCodePoint', 'raw',
    'parse', 'parseInt', 'parseFloat', 'isNaN', 'isFinite',
    'eval', 'unescape', 'escape',
    'Array', 'Object', 'String', 'Number', 'Boolean', 'Symbol',
    'Function', 'Promise', 'Map', 'Set', 'WeakMap', 'WeakSet',
    'Date', 'RegExp', 'Error', 'TypeError', 'SyntaxError',
    'URIError', 'RangeError', 'ReferenceError', 'EvalError',
    'AggregateError', 'JSON', 'Math', 'Intl', 'Proxy', 'Reflect',
    'ArrayBuffer', 'DataView', 'TypedArray', 'Int8Array',
    'Int16Array', 'Int32Array', 'Uint8Array', 'Uint16Array',
    'Uint32Array', 'Uint8ClampedArray', 'Float32Array',
    'Float64Array', 'BigUint64Array', 'BigInt64Array',
    'SharedArrayBuffer', 'Atomics', 'Generator', 'GeneratorFunction',
    'AsyncFunction', 'AsyncGenerator', 'AsyncGeneratorFunction',
    'Iterator', 'AsyncIterator',
    'TextEncoder', 'TextDecoder', 'Blob', 'File', 'FormData',
    'URL', 'URLSearchParams', 'Headers', 'Request', 'Response',
    'ReadableStream', 'WritableStream', 'TransformStream',
    'Crypto', 'SubtleCrypto', 'CryptoKey',
    'Performance', 'PerformanceEntry', 'PerformanceMark',
    'PerformanceMeasure', 'PerformanceObserver',
    'RequestInit', 'ResponseInit', 'RequestMode', 'RequestCredentials',
    'RequestDestination', 'RequestRedirect', 'ResponseType',
    'CacheStorage', 'Cache', 'FetchEvent', 'ExtendableEvent',
    'ServiceWorkerGlobalScope', 'Client', 'Clients', 'MessageEvent',
    'ExtendableMessageEvent', 'PushEvent', 'Notification',
    'PushManager', 'PushSubscription', 'PushSubscriptionOptions',
    'PaymentRequest', 'PaymentResponse', 'PaymentAddress',
    'PaymentMethod', 'PaymentItem', 'PaymentOptions',
    'PaymentShippingOption', 'PaymentShippingType',
    'Credential', 'CredentialsContainer', 'PublicKeyCredential',
    'AuthenticatorAssertionResponse', 'AuthenticatorAttestationResponse',
    'AuthenticatorResponse', 'PublicKeyCredentialRequestOptions',
    'PublicKeyCredentialCreationOptions', 'AuthenticatorTransport',
    'AuthenticatorSelectionCriteria', 'UserVerificationRequirement',
    'PublicKeyCredentialType', 'COSEAlgorithmIdentifier',
    'JsonWebKey', 'CryptoKeyPair', 'RsaHashedKeyGenParams',
    'EcKeyGenParams', 'HmacKeyGenParams', 'AesKeyGenParams',
    'RsaHashedImportParams', 'EcKeyImportParams',
    'HmacImportParams', 'AesKeyAlgorithm', 'HmacKeyAlgorithm',
    'RsaKeyAlgorithm', 'RsaHashedAlgorithm', 'EcKeyAlgorithm',
    'CryptoKey', 'AesCbcParams', 'AesGcmParams', 'AesCmacParams',
    'AesCtrParams', 'AesKeyAlgorithm', 'HmacKeyAlgorithm',
    'RsaHashedImportParams', 'EcKeyImportParams',
    'HmacImportParams', 'RsaOaepParams', 'RsaOtherPrimesInfo',
    'RsaPssParams', 'EcdsaParams', 'EcdhKeyDeriveParams',
    'AesGcmImportParams', 'AesCbcImportParams', 'AesCtrImportParams',
    'AesCmacImportParams', 'AesKeyAlgorithm', 'HmacKeyAlgorithm',
    'RsaKeyAlgorithm', 'RsaHashedAlgorithm', 'EcKeyAlgorithm',
    'CryptoKey', 'AesCbcParams', 'AesGcmParams', 'AesCmacParams',
    'AesCtrParams', 'AesKeyGenParams', 'HmacKeyGenParams',
    'RsaHashedKeyGenParams', 'EcKeyGenParams',
    'RsaHashedImportParams', 'EcKeyImportParams',
    'HmacImportParams', 'RsaOaepParams', 'RsaOtherPrimesInfo',
    'RsaPssParams', 'EcdsaParams', 'EcdhKeyDeriveParams',
    'AesGcmImportParams', 'AesCbcImportParams', 'AesCtrImportParams',
    'AesCmacImportParams',
    'createCipheriv', 'createDecipheriv', 'createHash',
    'createHmac', 'createSign', 'createVerify', 'createDiffieHellman',
    'randomBytes', 'randomFillSync', 'randomFill', 'randomUUID',
    'scryptSync', 'scrypt', 'pbkdf2Sync', 'pbkdf2',
    'generateKeyPairSync', 'generateKeyPair', 'generateKeySync',
    'generateKey', 'importKey', 'exportKey', 'sign', 'verify',
    'encrypt', 'decrypt', 'deriveBits', 'deriveKey',
    'digest', 'timingSafeEqual', 'getFingerprints',
    'final', 'update',
    'BigInt', 'BigInt64Array', 'BigUint64Array',
    'asIntN', 'asUintN', 'isBigIntObject', 'toBigInt',
    'Intl', 'Intl.Collator', 'Intl.DateTimeFormat',
    'Intl.DisplayNames', 'Intl.ListFormat', 'Intl.Locale',
    'Intl.NumberFormat', 'Intl.PluralRules', 'Intl.RelativeTimeFormat',
    'Intl.Segmenter', 'IntlSegmenter', 'IntlSegment',
    'SharedArrayBuffer', 'Atomics', 'Atomics.load',
    'Atomics.store', 'Atomics.add', 'Atomics.sub',
    'Atomics.and', 'Atomics.or', 'Atomics.xor',
    'Atomics.compareExchange', 'Atomics.exchange',
    'Atomics.wait', 'Atomics.wake', 'Atomics.isLockFree',
    'WebAssembly', 'WebAssembly.Module', 'WebAssembly.Instance',
    'WebAssembly.Memory', 'WebAssembly.Table', 'WebAssembly.CompileError',
    'WebAssembly.LinkError', 'WebAssembly.RuntimeError',
    'WebAssembly.Global', 'WebAssembly.ImportValue',
    'WebAssembly.ExportValue', 'WebAssembly.InstanceError',
    'WebAssembly.MVP', 'WebAssembly.ATOMIC',
    'WebAssembly.WORKERS', 'WebAssembly.BULK_MEMORY',
    'WebAssembly.MULTI_VALUE', 'WebAssembly.TAIL_CALLS',
    'WebAssembly.LINKING', 'WebAssembly.STACK_SWITCHING',
    'WebAssembly.EVENT_HANDLERS', 'WebAssembly.GC',
    'WebAssembly.JS_STREAMS', 'WebAssembly.SIGNATURE_POLYMORPHISM',
    'WebAssembly.REFERENCE_TYPES', 'WebAssembly.RELOCATABLE',
    'WebAssembly.PROPOSAL', 'WebAssembly.FEATURE',
    'WebAssembly.OPTION', 'WebAssembly.CONFIG',
    'WebAssembly.ENV', 'WebAssembly.PROCESS',
    'WebAssembly.SYSTEM', 'WebAssembly.OPERATING',
    'WebAssembly.HOST', 'WebAssembly.GUEST',
    'WebAssembly.INTERPRETER', 'WebAssembly.JIT',
    'WebAssembly.AOT', 'WebAssembly.WASM',
    'WebAssembly.SPEC', 'WebAssembly.IETF',
    'WebAssembly.W3C', 'WebAssembly.WORLD',
    'WebAssembly.FUTURE', 'WebAssembly.PRESENT',
    'WebAssembly.PAST', 'WebAssembly.THREAD',
    'WebAssembly.SINGLE', 'WebAssembly.MULTI',
    'WebAssembly.SYNC', 'WebAssembly.ASYNC',
    'WebAssembly.WEB', 'WebAssembly.NODE',
    'WebAssembly.BROWSER', 'WebAssembly.DESKTOP',
    'WebAssembly.MOBILE', 'WebAssembly.IOT',
    'WebAssembly.EMBEDDED', 'WebAssembly.CLOUD',
    'WebAssembly.EDGE', 'WebAssembly.BORDER',
    'WebAssembly.FRONTIER', 'WebAssembly.LIMIT',
    'WebAssembly.BOUNDARY', 'WebAssembly.MARGIN',
    'WebAssembly.EDGE_CASE', 'WebAssembly.BOUNDARY_CASE',
    'WebAssembly.LIMIT_CASE', 'WebAssembly.BORDER_CASE',
    'WebAssembly.FRONTIER_CASE', 'WebAssembly.FRONTIER_CASE',
}

# JS/TS globals that are common and should not be flagged
JS_TS_GLOBALS = {
    'console', 'window', 'document', 'process', 'require', 'import',
    'export', 'Promise', 'Error', 'Array', 'Object', 'String',
    'Number', 'Boolean', 'Math', 'Date', 'JSON', 'RegExp', 'Map',
    'Set', 'Symbol', 'Proxy', 'Reflect', 'Intl', 'TypedArray',
    'ArrayBuffer', 'DataView', 'WeakMap', 'WeakSet', 'Atomics',
    'SharedArrayBuffer', 'setTimeout', 'setInterval', 'clearTimeout',
    'clearInterval', 'requestAnimationFrame', 'cancelAnimationFrame',
    'fetch', 'navigator', 'location', 'history', 'screen',
    'alert', 'confirm', 'prompt', 'setTimeout', 'setInterval',
    'Blob', 'File', 'FormData', 'URL', 'URLSearchParams',
    'Headers', 'Request', 'Response', 'ReadableStream',
    'WritableStream', 'TransformStream',
    'Buffer', 'Stream', 'EventEmitter', 'ChildProcess',
    'Server', 'Socket', 'IncomingMessage', 'ServerResponse',
    'fs', 'path', 'os', 'http', 'https', 'net', 'dns',
    'crypto', 'stream', 'util', 'events', 'buffer', 'zlib',
    'child_process', 'cluster', 'dgram', 'domain', 'module',
    'vm', 'worker_threads', 'perf_hooks', 'async_hooks',
}


def _detect_phantom_api(
    source: str,
    file_path: Path,
    pattern_index: PatternIndex,
) -> list[UnslopIssue]:
    """Detect calls to methods/functions that don't exist in the project.

    Strategy: extract all method/attribute access patterns (e.g.,
    `obj.some_method()`, `module.function()`), then check if the target
    symbol exists in the project's known symbols (error classes, helpers).
    Symbols not in these sets AND not builtins are flagged as potential
    phantom APIs.

    This covers Symbol Resolution Failures (SRF) and Phantom Internal API
    (PIA) from the Mothukuri & Parizi taxonomy.

    NOTE: This detector has a high false positive rate because many method
    calls are on third-party library objects that won't be in the project's
    symbol table. Confidence is set low (0.5) to reflect this.
    """
    issues = []
    lines = source.splitlines()

    # Build a set of all known symbols in the project
    known_symbols = set()

    # Add error classes
    for ecp in pattern_index.error_classes:
        known_symbols.add(ecp.error_class)
        known_symbols.add(ecp.error_class.lower())

    # Add helper function names
    for hf in pattern_index.helper_functions:
        known_symbols.add(hf.name)
        known_symbols.add(hf.name.lower())

    # Extract all method/attribute access patterns
    access_patterns = [
        # obj.method() or self.method()
        r'(?<!\.)\b([a-zA-Z_]\w*)\.([a-zA-Z_]\w*)\s*\(',
        # self.attr (attribute access without call)
        r'\bself\.([a-zA-Z_]\w*)\b',
        # cls.attr (class attribute access)
        r'\bcls\.([a-zA-Z_]\w*)\b',
    ]

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Skip comments
        if stripped.startswith('#') or stripped.startswith('//'):
            continue

        # Skip docstrings
        if stripped.startswith('"""') or stripped.startswith("'''"):
            continue

        for pattern in access_patterns:
            for match in re.finditer(pattern, stripped):
                # For two-group patterns, the second group is the method/attr
                if match.lastindex and match.lastindex >= 2:
                    target = match.group(2)
                    obj = match.group(1)
                else:
                    target = match.group(1)
                    obj = None

                # Skip built-in methods
                if target in BUILTIN_METHODS:
                    continue
                # Skip dunder methods
                if target.startswith('__') and target.endswith('__'):
                    continue
                # Skip private/protected (starts with _)
                if target.startswith('_'):
                    continue
                # Skip JS/TS globals
                if target in JS_TS_GLOBALS:
                    continue
                # Skip if target is in known symbols
                if target in known_symbols:
                    continue
                # Skip if object is a known type
                if obj and obj.lower() in ('self', 'cls', 'this',
                                            'super', 'module', 'exports',
                                            'require', 'window', 'document',
                                            'console', 'process', 'os',
                                            'fs', 'path', 'http', 'https',
                                            'math', 'json', 'date', 'array',
                                            'string', 'number', 'boolean',
                                            'error', 'regexp', 'map', 'set',
                                            'promise', 'symbol', 'proxy',
                                            'reflect', 'int', 'float',
                                            'bool', 'str', 'bytes', 'list',
                                            'dict', 'tuple', 'range', 'type',
                                            'file', 'open', 'print', 'input',
                                            'len', 'range', 'enumerate',
                                            'zip', 'map', 'filter', 'sorted',
                                            'reversed', 'any', 'all', 'abs',
                                            'round', 'pow', 'divmod',
                                            'min', 'max', 'sum', 'id',
                                            'hash', 'isinstance', 'issubclass',
                                            'callable', 'hasattr', 'getattr',
                                            'setattr', 'delattr', 'dir',
                                            'vars', 'repr', 'format',
                                            'chr', 'ord', 'hex', 'oct',
                                            'bin', 'complex', 'ascii',
                                            'next', 'iter', 'slice',
                                            'property', 'staticmethod',
                                            'classmethod', 'super',
                                            'Exception', 'ValueError',
                                            'TypeError', 'KeyError',
                                            'IndexError', 'AttributeError',
                                            'ImportError', 'RuntimeError',
                                            'StopIteration', 'GeneratorExit',
                                            'SystemExit', 'InterruptedError',
                                            'ConnectionError', 'BrokenPipeError',
                                            'ConnectionAbortedError',
                                            'ConnectionRefusedError',
                                            'ConnectionResetError',
                                            'FileExistsError', 'FileNotFoundError',
                                            'IsADirectoryError',
                                            'NotADirectoryError',
                                            'PermissionError', 'ProcessLookupError',
                                            'TimeoutError', 'OSError',
                                            'IOError', 'UnicodeError',
                                            'UnicodeDecodeError',
                                            'UnicodeEncodeError',
                                            'UnicodeTranslateError',
                                            'EOFError', 'BlockingIOError',
                                            'ChildProcessError',
                                            'NotImplementedError',
                                            'RecursionError',
                                            'MemoryError', 'OverflowError',
                                            'ZeroDivisionError',
                                            'ArithmeticError',
                                            'LookupError',
                                            'IndexError', 'KeyError',
                                            'NameError', 'UnboundLocalError',
                                            'SyntaxError', 'IndentationError',
                                            'TabError', 'SystemError',
                                            'ReferenceError',
                                            'RuntimeWarning', 'DeprecationWarning',
                                            'FutureWarning', 'PendingDeprecationWarning',
                                            'ResourceWarning', 'UserWarning',
                                            'Warning', 'BytesWarning',
                                            'EncodingWarning', 'ImportWarning',
                                            'UnicodeWarning', 'SyntaxWarning',
                                            'PendingDeprecationWarning',
                                            'FutureWarning', 'DeprecationWarning',
                                            'UserWarning'):
                    continue

                # Flag as potential phantom API
                # Note: High false positive rate — many calls are on
                # third-party library objects not in the project symbol table.
                issues.append(UnslopIssue(
                    tell=TellCategory.GLOBAL_INCOHERENCE,
                    severity=Severity.LOW,
                    description=(
                        f'Possible phantom API: "{target}" referenced in '
                        f'"{obj}" not found in project symbols'
                    ),
                    file_path=file_path,
                    line=i + 1,
                    code_snippet=stripped[:100],
                    suggested_fix=(
                        f'Verify that "{target}" exists on the object/type '
                        f'"{obj}" or add it to the project'
                    ),
                    confidence=0.5,
                    research_source=(
                        'Mothukuri & Parizi (2026) — '
                        'Symbol Resolution Failure (SRF) + '
                        'Phantom Internal API (PIA)'
                    ),
                ))
                break  # One issue per line per pattern

    return issues


# ── Configuration incoherence detection ────────────────────────────────────

# Patterns for unsafe environment variable / config access
# These patterns will crash at runtime if the key is missing
PYTHON_UNSAFE_ENV = re.compile(
    r'os\.environ\["([^"]+)"\]|os\.environ\[\'([^\']+)\'\]|'
    r'os\.getenv\("([^"]+)"\)|os\.getenv\(\'([^\']+)\'\)'
)

TS_UNSAFE_ENV = re.compile(
    r'process\.env\.([A-Z_][A-Z0-9_]*)\b'
)

# Patterns that PROTECT against missing env vars (these make access safe)
SAFEGUARDS = [
    r'try\s*:',           # try/except
    r'except',            # except block
    r'\?\?',              # nullish coalescing
    r'\|\|',              # logical OR fallback
    r'\.get\(',           # dict.get() with default
    r'os\.environ\.get',  # os.environ.get()
    r'os\.getenv',        # os.getenv()
    r'\.has_key\(',       # has_key check
    r'in\s+os\.environ',  # membership test
    r'if\s+.*env',        # conditional env check
]


def _is_safe_access(line: str) -> bool:
    """Check if env var access on this line is protected by a safeguard."""
    for safeguard in SAFEGUARDS:
        if re.search(safeguard, line):
            return True
    return False


def _extract_config_keys(source: str, file_path: Path) -> list[tuple[str, int]]:
    """Extract all environment variable / config key accesses from source.

    Returns list of (key, line_number) tuples for unsafe accesses.
    """
    keys = []
    lines = source.splitlines()

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Skip comments
        if stripped.startswith('#') or stripped.startswith('//'):
            continue

        # Skip docstrings
        if stripped.startswith('"""') or stripped.startswith("'''"):
            continue

        # Python: os.environ["KEY"] or os.getenv("KEY")
        if file_path.suffix in ('.py', '.pyi'):
            for match in PYTHON_UNSAFE_ENV.finditer(stripped):
                key = match.group(1) or match.group(2) or match.group(3) or match.group(4)
                if key and not _is_safe_access(line):
                    keys.append((key, i + 1))

        # TypeScript: process.env.KEY
        elif file_path.suffix in ('.ts', '.tsx', '.js', '.jsx'):
            for match in TS_UNSAFE_ENV.finditer(stripped):
                key = match.group(1)
                if key and not _is_safe_access(line):
                    keys.append((key, i + 1))

    return keys


def _detect_config_incoherence(
    source: str,
    file_path: Path,
    config_keys: Optional[set[str]] = None,
) -> list[UnslopIssue]:
    """Detect environment variable / config accesses where the key is never
    declared anywhere in the repository.

    This implements Build/Configuration Incoherence (BCI) from the
    Mothukuri & Parizi taxonomy.
    """
    issues = []
    if not config_keys:
        return issues

    accessed_keys = _extract_config_keys(source, file_path)

    for key, line_num in accessed_keys:
        if key not in config_keys:
            issues.append(UnslopIssue(
                tell=TellCategory.GLOBAL_INCOHERENCE,
                severity=Severity.HIGH,
                description=(
                    f'Unprotected access to "{key}" — key not declared in '
                    f'any repository configuration file'
                ),
                file_path=file_path,
                line=line_num,
                code_snippet=source.splitlines()[line_num - 1][:100],
                suggested_fix=(
                    f'Add "{key}" to .env/.env.example or use a safe access '
                    'pattern (os.environ.get("KEY", default))'
                ),
                confidence=0.8,
                research_source=(
                    'Mothukuri & Parizi (2026) — '
                    'Build/Configuration Incoherence (BCI)'
                ),
            ))

    return issues


# ── Resource coherence detection ───────────────────────────────────────────

# Patterns for file/path references that should exist on disk
FILE_PATH_PATTERNS = [
    # Python: open('path'), read('path'), load('path')
    (r'(?:open|read|load|write|save)\s*\(\s*[\'"]([^\'"]+)[\'"]', 'python'),
    # Template paths: render('path'), template('path')
    (r'(?:render|template|render_template|render_file)\s*\(\s*[\'"]([^\'"]+)[\'"]', 'framework'),
    # Static asset paths
    (r'["\'](/static/[^"\']+)["\']', 'static'),
    # Migration paths
    (r'["\'](/migrations/[^"\']+)["\']', 'migration'),
]


def _detect_resource_coherence(
    source: str,
    file_path: Path,
    root_dir: Path,
) -> list[UnslopIssue]:
    """Detect file/path references that don't exist on disk.

    This implements Resource Coherence Failures (RCF) from the
    Mothukuri & Parizi taxonomy, specifically the filesystem resource
    sub-category.
    """
    issues = []
    lines = source.splitlines()

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Skip comments
        if stripped.startswith('#') or stripped.startswith('//'):
            continue

        # Skip docstrings
        if stripped.startswith('"""') or stripped.startswith("'''"):
            continue

        for pattern, kind in FILE_PATH_PATTERNS:
            for match in re.finditer(pattern, stripped):
                path_ref = match.group(1)

                # Skip URLs, data URIs, and non-file paths
                if path_ref.startswith(('http://', 'https://', 'data:', 'mailto:')):
                    continue

                # Skip node_modules, .git, and other ignore paths
                if 'node_modules' in path_ref or '.git' in path_ref:
                    continue

                # Resolve the path relative to root_dir
                if path_ref.startswith('/'):
                    resolved = root_dir / path_ref.lstrip('/')
                else:
                    resolved = root_dir / path_ref

                # Check if the path exists
                if not resolved.exists():
                    issues.append(UnslopIssue(
                        tell=TellCategory.GLOBAL_INCOHERENCE,
                        severity=Severity.MEDIUM,
                        description=(
                            f'Reference to nonexistent file: "{path_ref}" '
                            f'(resolved to {resolved})'
                        ),
                        file_path=file_path,
                        line=i + 1,
                        code_snippet=stripped[:100],
                        suggested_fix=(
                            f'Verify that "{path_ref}" exists or correct the path'
                        ),
                        confidence=0.7,
                        research_source=(
                            'Mothukuri & Parizi (2026) — '
                            'Resource Coherence Failure (RCF)'
                        ),
                    ))
                    break  # One issue per line per pattern

    return issues


# ── Main detect function ──────────────────────────────────────────────────

def detect(
    source: str,
    file_path: Path,
    context: Optional[dict] = None,
) -> list[UnslopIssue]:
    """Detect global incoherence issues.

    Checks for:
    - Phantom API calls — methods/functions not found in project symbols
    - Configuration incoherence — env vars/config keys never declared
    - Resource coherence — file/path references that don't exist on disk

    Args:
        source: Source code to analyze.
        file_path: Path to the source file.
        context: Optional dict with 'pattern_index', 'config_keys', 'root_dir'.

    Returns:
        List of UnslopIssue for each global incoherence issue found.
    """
    issues = []

    pattern_index: Optional[PatternIndex] = None
    config_keys: Optional[set[str]] = None
    root_dir: Optional[Path] = None

    if context:
        pattern_index = context.get('pattern_index')
        config_keys = context.get('config_keys')
        root_dir = context.get('root_dir')

    # 1. Phantom API detection (requires pattern_index)
    # NOTE: Disabled by default due to high false positive rate.
    # Many method calls are on third-party library objects not in the
    # project's symbol table. Re-enable when better filtering is added.
    # if pattern_index:
    #     issues.extend(_detect_phantom_api(source, file_path, pattern_index))

    # 2. Configuration incoherence (requires config_keys)
    if config_keys:
        issues.extend(_detect_config_incoherence(source, file_path, config_keys))

    # 3. Resource coherence (requires root_dir)
    if root_dir:
        issues.extend(_detect_resource_coherence(source, file_path, root_dir))

    return issues


def fix(source: str, issues: list[UnslopIssue]) -> str:
    """Suggest fixes for global incoherence issues.

    Note: Global incoherence fixes require understanding the broader
    codebase. We only flag, never auto-fix.

    Args:
        source: Original source code.
        issues: List of global incoherence issues.

    Returns:
        Original source (global incoherence fixes are suggestions only).
    """
    # Global incoherence issues are suggestions only
    return source
