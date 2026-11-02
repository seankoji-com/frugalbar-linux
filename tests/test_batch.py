from concurrent.futures import ThreadPoolExecutor
import threading
import unittest
from unittest.mock import Mock
from frugalbar_linux import batch


class SharedReads(unittest.TestCase):
    def test_sibling_rows_share_a_request_and_credentials_never_share_data(self):
        started = threading.Event()
        release = threading.Event()
        def request(*args, **kwargs):
            started.set()
            release.wait(2)
            return {"fixture": True}
        request = Mock(side_effect=request)
        with ThreadPoolExecutor(2) as pool:
            first = pool.submit(batch.read, request, "https://fixture-one.invalid/", "first-token")
            self.assertTrue(started.wait(2))
            second = pool.submit(batch.read, request, "https://fixture-one.invalid/", "first-token")
            release.set()
            self.assertEqual(first.result(), second.result())
        self.assertEqual(request.call_count, 1)
        batch.read(request, "https://fixture-one.invalid/", "second-token")
        self.assertEqual(request.call_count, 2)
