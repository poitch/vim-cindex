#!/usr/bin/env python
import argparse
import sys
import socket


class Searcher(object):

    def __init__(self, port, debug = False):
        self.port = port
        self.debug = debug

    def _gets(self, socket):
        lines = []
        while True:
            data = socket.recv(4096)
            tmp = data.split("\n")
            del tmp[-1]
            if self.debug:
                for line in tmp:
                    print >>sys.stderr, " <- %s\n" % line
            lines = lines + tmp
            if "DONE" in tmp:
                del lines[-1]
                return lines

    def _command(self, message):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_address = ('localhost', int(self.port))
        if self.debug:
            print >>sys.stderr, "Connecting to %s" % self.port
        try:
            sock.connect(server_address)
            if self.debug:
                print >>sys.stderr, " -> %s" % message
            sock.sendall(message)
            return self._gets(sock)
        except Exception as er:
            if self.debug:
                print >>sys.stderr, "Failed to connect", er
            return None
        finally:
            sock.close()


    def index(self, path):
        message = "INDEX %s\n" % path
        return self._command(message)

    def implementation(self, pattern):
        message = "IMPL %s\n" % pattern
        return self._command(message)

    def declaration(self, pattern):
        message = "DECL %s\n" % pattern
        return self._command(message)

    def calls(self, pattern):
        message = "CALLS %s\n" % pattern
        return self._command(message)

    def complete(self, pattern):
        message = "AUTO %s\n" % pattern
        return self._command(message)

    def quit(self):
        message = "QUIT\n"
        return self._command(message)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port',
                        default=10000,
                        help='Listening port.')

    args, unknown_args = parser.parse_known_args()
    argv = [sys.argv[0]] + unknown_args

    searcher = Searcher(args.port)

    lines = None
    if len(argv) == 3:
        if argv[1] == 'INDEX':
            lines = searcher.index(argv[2])
        elif argv[1] == 'IMPL':
            lines = searcher.implementation(argv[2])
        elif argv[1] == 'DECL':
            lines = searcher.declaration(argv[2])
        elif argv[1] == 'CALLS':
            lines = searcher.calls(argv[2])
        elif argv[1] == 'AUTO':
            lines = searcher.complete(argv[2])

    if lines is None:
        return 1
    else:
        for line in lines:
            print line
        return 0

if __name__ == "__main__":
    sys.exit(main())
