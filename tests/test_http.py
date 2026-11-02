from email.message import Message
import io
import unittest
from unittest.mock import MagicMock, patch
import urllib.error
import urllib.request

from frugalbar_linux import http


class HttpTests(unittest.TestCase):
    def test_redirect_handler_never_forwards_credentials(self):
        req = urllib.request.Request('https://api.github.com/rate_limit', headers={'Authorization': 'Bearer fixture'})
        self.assertIsNone(http.NoRedirect().redirect_request(req, None, 302, 'Found', {}, 'https://attacker.invalid/'))

    def test_endpoint_allowlist_rejects_plaintext_and_foreign_hosts(self):
        for url in ('http://api.github.com/rate_limit', 'https://attacker.invalid/', 'https://api.github.com@attacker.invalid/'):
            with self.assertRaises(http.FetchError):
                http.request(url, 'fixture')

    def test_failure_status_precedes_decoding_and_sanitizes_payload(self):
        headers = Message()
        headers['Retry-After'] = '30'
        error = urllib.error.HTTPError('https://api.github.com/', 429, 'private error', headers, io.BytesIO(b'private payload'))
        with patch.object(http.urllib.request, 'build_opener') as builder:
            builder.return_value.open.side_effect = error
            with self.assertRaises(http.FetchError) as caught:
                http.request('https://api.github.com/rate_limit', 'fixture-secret')
        self.assertEqual(caught.exception.status, 429)
        self.assertNotIn('private', str(caught.exception))
        self.assertNotIn('fixture-secret', str(caught.exception))

    def test_response_size_and_json_shape_are_bounded(self):
        for payload in (b'x' * (http.MAX_BYTES + 1), b'[]', b'<html>error</html>'):
            response = MagicMock()
            response.__enter__.return_value.read.return_value = payload
            with patch.object(http.urllib.request, 'build_opener') as builder:
                builder.return_value.open.return_value = response
                with self.assertRaises(http.FetchError):
                    http.request('https://api.github.com/rate_limit', 'fixture')

    def test_retry_after_rejects_infinite_and_caps_delay(self):
        self.assertIsNone(http.retry_after('inf', now=100))
        self.assertIsNone(http.retry_after('0', now=100))
        self.assertIsNone(http.retry_after('999999999999999999999', now=100))
        self.assertEqual(http.retry_after('999999', now=100), 86500)
        self.assertEqual(http.retry_after('30', now=100), 130)


if __name__ == '__main__':
    unittest.main()
