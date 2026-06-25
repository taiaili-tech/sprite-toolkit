import webview
import sys
import os
import base64
import threading
import socket
from http.server import HTTPServer, SimpleHTTPRequestHandler


def get_free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def get_dist_dir():
    if getattr(sys, 'frozen', False):
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, 'dist')


def start_server(dist_dir, port):
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=dist_dir, **kwargs)
        def log_message(self, *args):
            pass

    httpd = HTTPServer(('127.0.0.1', port), Handler)
    httpd.serve_forever()


# JS 注入：拦截 blob 下载，转交给 Python 文件保存对话框
DOWNLOAD_HOOK = """
(function() {
    const _origClick = HTMLAnchorElement.prototype.click;
    HTMLAnchorElement.prototype.click = function() {
        if (this.download && this.href && this.href.startsWith('blob:')) {
            const filename = this.download;
            const href = this.href;
            fetch(href)
                .then(r => r.arrayBuffer())
                .then(buf => {
                    const bytes = new Uint8Array(buf);
                    let bin = '';
                    for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
                    window.pywebview.api.save_file(filename, btoa(bin));
                });
            return;
        }
        return _origClick.call(this);
    };
})();
"""


class Api:
    def save_file(self, filename, data_b64):
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)

        ext = os.path.splitext(filename)[1] or '.*'
        save_path = filedialog.asksaveasfilename(
            parent=root,
            initialfile=filename,
            defaultextension=ext,
            filetypes=[
                ('ZIP 文件', '*.zip'),
                ('GIF 文件', '*.gif'),
                ('PNG 文件', '*.png'),
                ('所有文件', '*.*'),
            ],
        )
        root.destroy()

        if save_path:
            data = base64.b64decode(data_b64)
            with open(save_path, 'wb') as f:
                f.write(data)
            return True
        return False


if __name__ == '__main__':
    dist_dir = get_dist_dir()
    port = get_free_port()

    server_thread = threading.Thread(
        target=start_server, args=(dist_dir, port), daemon=True
    )
    server_thread.start()

    api = Api()
    window = webview.create_window(
        'Sprite Toolkit',
        url=f'http://127.0.0.1:{port}/index.html',
        width=1100,
        height=760,
        min_size=(800, 600),
        js_api=api,
    )

    def on_loaded():
        window.evaluate_js(DOWNLOAD_HOOK)

    window.events.loaded += on_loaded
    webview.start()
