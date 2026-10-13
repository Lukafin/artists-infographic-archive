import functools
import http.client
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from preview_server import PreviewHandler


class QuietHandler(PreviewHandler):
    def log_message(self, *args):
        pass


class PreviewRangeTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        self.addCleanup(self.root.cleanup)
        self.content = bytes(range(256)) * 8
        Path(self.root.name, 'episode.m4a').write_bytes(self.content)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(QuietHandler, directory=self.root.name))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.shutdown)

    def shutdown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def request(self, value=None, method='GET'):
        connection = http.client.HTTPConnection(*self.server.server_address)
        connection.request(method, '/episode.m4a', headers={'Range':value} if value else {})
        response = connection.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        connection.close()
        return result

    def test_normal_response_and_media_type(self):
        status, headers, body = self.request()
        self.assertEqual((status, body), (200, self.content))
        self.assertEqual(headers['Content-type'], 'audio/mp4')
        self.assertEqual(headers['Accept-Ranges'], 'bytes')

    def test_closed_open_and_suffix_ranges_return_exact_bytes(self):
        for value, start, end in [('bytes=100-123',100,123), ('bytes=2000-',2000,2047),
                                   ('bytes=-16',2032,2047), ('bytes=2040-9999',2040,2047)]:
            with self.subTest(value=value):
                status, headers, body = self.request(value)
                self.assertEqual(status, 206)
                self.assertEqual(headers['Content-Range'], f'bytes {start}-{end}/2048')
                self.assertEqual(int(headers['Content-Length']), end-start+1)
                self.assertEqual(body, self.content[start:end+1])

    def test_unsatisfiable_range_and_head(self):
        for value in ['bytes=2048-', 'bytes=10-2', 'bytes=-0']:
            status, headers, body = self.request(value)
            self.assertEqual(status, 416)
            self.assertEqual(headers['Content-Range'], 'bytes */2048')
            self.assertEqual(body, b'')
        status, headers, body = self.request('bytes=100-123', 'HEAD')
        self.assertEqual((status, body), (206, b''))
        self.assertEqual(headers['Content-Length'], '24')


if __name__ == '__main__':
    unittest.main()
