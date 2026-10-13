#!/usr/bin/env python3
"""Local archive preview with byte ranges for native audio/video seeking."""
import argparse
import functools
import os
import re
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def byte_range(header, size):
    """Return inclusive bounds; ignore unsupported ranges and reject unsatisfiable ones."""
    match = re.fullmatch(r'bytes=(\d*)-(\d*)', header.strip())
    if not match:
        return None
    start, end = match.groups()
    if size == 0 or not (start or end):
        raise ValueError('Unsatisfiable range')
    if not start:
        suffix = int(end)
        if suffix == 0:
            raise ValueError('Unsatisfiable range')
        return max(0, size - suffix), size - 1
    start = int(start)
    end = min(int(end), size - 1) if end else size - 1
    if start >= size or end < start:
        raise ValueError('Unsatisfiable range')
    return start, end


class PreviewHandler(SimpleHTTPRequestHandler):
    extensions_map = dict(SimpleHTTPRequestHandler.extensions_map,
                          **{'.m4a':'audio/mp4', '.mp3':'audio/mpeg', '.ogg':'audio/ogg', '.wav':'audio/wav'})

    def end_headers(self):
        self.send_header('Accept-Ranges', 'bytes')
        # Preview changes should be visible after reload, including server fixes.
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()

    def send_head(self):
        self.requested_range = None
        header = self.headers.get('Range')
        path = self.translate_path(self.path)
        if not header or self.headers.get('If-Range') or not Path(path).is_file():
            return super().send_head()
        try:
            source = open(path, 'rb')
        except OSError:
            self.send_error(404, 'File not found')
            return None
        stat = os.fstat(source.fileno())
        try:
            bounds = byte_range(header, stat.st_size)
        except ValueError:
            source.close()
            self.send_response(416)
            self.send_header('Content-Range', f'bytes */{stat.st_size}')
            self.send_header('Content-Length', '0')
            self.end_headers()
            return None
        if bounds is None:
            source.close()
            return super().send_head()
        start, end = bounds
        self.requested_range = bounds
        source.seek(start)
        self.send_response(206)
        self.send_header('Content-Type', self.guess_type(path))
        self.send_header('Content-Range', f'bytes {start}-{end}/{stat.st_size}')
        self.send_header('Content-Length', str(end - start + 1))
        self.send_header('Last-Modified', self.date_time_string(stat.st_mtime))
        self.end_headers()
        return source

    def copyfile(self, source, outputfile):
        if self.requested_range is None:
            return super().copyfile(source, outputfile)
        start, end = self.requested_range
        remaining = end - start + 1
        while remaining:
            chunk = source.read(min(65536, remaining))
            if not chunk:
                break
            outputfile.write(chunk)
            remaining -= len(chunk)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8768)
    parser.add_argument('--directory', type=Path, default=Path(__file__).resolve().parent/'docs')
    args = parser.parse_args()
    handler = functools.partial(PreviewHandler, directory=str(args.directory.resolve()))
    with ThreadingHTTPServer(('127.0.0.1', args.port), handler) as server:
        print(f'Archive preview: http://127.0.0.1:{args.port}/index.html#archive', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
