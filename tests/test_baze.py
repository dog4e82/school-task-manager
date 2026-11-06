import contextlib
import io
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
import main

KEY = 'test-secret-never-print'
MODEL = {'data': [{'id': 'cheap-test', 'type': 'llm', 'pricing': {'input': 0.1}}]}
BALANCE = {'total': {'remaining': 100}}

class Tests(unittest.TestCase):
    def client(self):
        return main.Client('https://example.invalid/v1/gateway', KEY)

    def test_one_post_and_missing_billing(self):
        client = self.client()
        responses = [MODEL, BALANCE, {'choices': [], 'usage': {'total_tokens': 20}},
                     {'total': {'remaining': 99.75}}]
        output = io.StringIO()
        with patch.object(client, 'request', side_effect=responses) as request, contextlib.redirect_stdout(output):
            main.analyze(client, 'cheap-test')
        self.assertEqual(sum(c.args[0] == '/chat/completions/' for c in request.call_args_list), 1)
        self.assertIn('0.25', output.getvalue())
        self.assertIn('추정하지 않습니다', output.getvalue())
        self.assertNotIn(KEY, output.getvalue())

    def test_failed_preflight_never_generates(self):
        for responses in ([main.BazeError('unavailable')], [MODEL, main.BazeError('balance failed')]):
            client = self.client()
            with patch.object(client, 'request', side_effect=responses) as request:
                with self.assertRaises(main.BazeError):
                    main.analyze(client, 'cheap-test')
            self.assertFalse(any(c.args[0] == '/chat/completions/' for c in request.call_args_list))

    def test_timeout_checks_balance_without_retry(self):
        client = self.client()
        with patch.object(client, 'request', side_effect=[MODEL, BALANCE, main.BazeError('timeout'), BALANCE]) as request:
            with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(main.BazeError):
                main.analyze(client, 'cheap-test')
        self.assertEqual(request.call_count, 4)
        self.assertEqual(request.call_args.args[0], '/credits/')

    def test_unknown_model_never_generates(self):
        client = self.client()
        with patch.object(client, 'request', return_value=MODEL) as request:
            with self.assertRaises(main.BazeError):
                main.analyze(client, 'unknown')
        self.assertEqual(request.call_count, 1)

    def test_server_error_does_not_leak_key(self):
        client = self.client()
        with patch.object(client.opener, 'open', side_effect=HTTPError('https://example.invalid', 401, KEY, {}, None)):
            with self.assertRaises(main.BazeError) as error:
                client.request('/models/')
        self.assertNotIn(KEY, str(error.exception))
        self.assertIn('401', str(error.exception))

    def test_redacts_reflected_key(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.client().emit('response', {'value': KEY})
        self.assertNotIn(KEY, output.getvalue())

    def test_insecure_url_rejected(self):
        for url in ('http://example.invalid', 'https://user:password@example.invalid', 'https://example.invalid?key=secret'):
            with self.assertRaises(main.BazeError):
                main.Client(url, KEY)

if __name__ == '__main__':
    unittest.main()
