"""Coalesce identical account metadata reads across sibling provider rows."""
from collections import OrderedDict
from concurrent.futures import Future
import hashlib
import json
import threading
import time

_entries = OrderedDict()
_lock = threading.Lock()


def read(request, url, token, **kwargs):
    key = (url, hashlib.sha256(token.encode()).digest(), json.dumps(kwargs, sort_keys=True))
    now = time.monotonic()
    with _lock:
        entry = _entries.get(key)
        if entry and (not entry[1].done() or now - entry[0] < 5):
            future = entry[1]
            owner = False
        else:
            future = Future()
            _entries[key] = (now, future)
            owner = True
            while len(_entries) > 64:
                _entries.popitem(last=False)
    if owner:
        try:
            future.set_result(request(url, token, **kwargs))
        except Exception as error:
            future.set_exception(error)
    return future.result()
