"""Run the Agentimo first screens with the standard library server."""

import os

from app import web
from wsgiref.simple_server import WSGIServer, WSGIRequestHandler, make_server
from socketserver import ThreadingMixIn


class ThreadingWSGIServer(ThreadingMixIn, WSGIServer):
    """A WSGI server handling each request in its own thread."""

    daemon_threads = True


def main():
    host = os.environ.get("APP_HOST", "127.0.0.1")
    port = int(os.environ.get("APP_PORT", "8000"))
    if "APP_DB_PATH" in os.environ:
        web.DB_PATH = os.environ["APP_DB_PATH"]
    with make_server(host, port, web.application,
                     server_class=ThreadingWSGIServer,
                     handler_class=WSGIRequestHandler) as server:
        server.serve_forever()


if __name__ == "__main__":
    main()
