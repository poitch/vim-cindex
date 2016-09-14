#!/usr/bin/env python
import argparse
import logging
import os
import platform
import re
import socket
import sys
import threading
import time

DIR_OF_CURRENT_SCRIPT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(DIR_OF_CURRENT_SCRIPT, ".."))
from cindex.indexer import Indexer


class Server(object):

    def __init__(self, index_file=None, log_file=None):
        # Setup logging
        self.logger = logging.getLogger('vim.cindex')
        self.logger.setLevel(logging.DEBUG)

        if log_file:
            fh = logging.FileHandler(log_file)
            formatter = logging.Formatter(
                '%(asctime)s - %(levelname)s - %(message)s')
            fh.setFormatter(formatter)
            self.logger.addHandler(fh)
        elif log_file is False:
            nh = logging.NullHandler()
            self.logger.addHandler(nh)
        else:
            ch = logging.StreamHandler()
            self.logger.addHandler(ch)

        self.index_thread = None
        self.indexer = Indexer(index_file, self.logger)

    @staticmethod
    def get_unused_local_port():
        sock = socket.socket()
        # This tells the OS to give us any free port in the range [1024 -
        # 65535]
        sock.bind(('', 0))
        port = sock.getsockname()[1]
        sock.close()
        return port

    def StartServer(self, port=None):
        if not port:
            port = Server.get_unused_local_port()
        self.server_thread = threading.Thread(target=self._run, args=(port,))
        self.server_thread.daemon = True
        self.server_thread.start()
        return port

    def StopServer(self):
        if self.server_thread:
            self.server_thread.stop()
            self.server_thread = None

    def _run(self, port=10000):
        """Start TCP server to answer basic grammar:
            DECL <name> returns location of function/type declaration
            IMPL <name> returns locatino of function/type implementation
            CALLS <name> returns list of locations of usage of function/type
            INDEX <path> indexes C/C++ files under given path
            AUTO <prefix> returns list of function/type starting with prefix."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        server_address = ('localhost', int(port))
        self.logger.info('Starting up on port %d', int(port))
        sock.bind(server_address)
        # Listen for incoming connections
        sock.listen(1)
        running = True
        while running:
            # Wait for a connection
            self.logger.debug('Waiting for a connection')
            connection, client_address = sock.accept()
            try:
                self.logger.debug('Connection from %s', client_address)
                # Receive the data in small chunks and retransmit it
                while True:
                    data = connection.recv(2048)
                    self.logger.debug('Received "%s"', data.rstrip())
                    if data:
                        if data.startswith('QUIT'):
                            self.logger.info("Requested to quit")
                            connection.sendall("DONE\n")
                            running = False
                            break
                        elif data.startswith('INDEX'):
                            lookup = data[6:].rstrip()
                            if not self.index_thread:
                                self.index_thread = threading.Thread(
                                    target=self.indexer.IndexDirectory, args=(lookup,))
                                self.index_thread.start()
                                connection.sendall("INDEXING\n")
                            else:
                                connection.sendall("BUSY\n")
                        elif data.startswith('AUTO'):
                            lookup = data[5:].rstrip()
                            matches = self.indexer.Autocomplete(lookup)
                            for match in matches:
                                connection.sendall("%s\n" % match)
                        elif data.startswith('IMPL'):
                            lookup = data[5:].rstrip()
                            impl = self.indexer.Implementation(lookup)
                            if impl:
                                connection.sendall("%s:%d:%d\n" % (
                                    impl['file'], impl['line'], impl['column']))
                        elif data.startswith('DECL'):
                            lookup = data[5:].rstrip()
                            decl = self.indexer.Declaration(lookup)
                            if decl:
                                connection.sendall("%s:%d:%d\n" % (
                                    decl['file'], decl['line'], decl['column']))
                        elif data.startswith('CALLS'):
                            lookup = data[6:].rstrip()
                            calls = self.indexer.Calls(lookup)
                            if (calls and len(calls) > 0):
                                for call in calls:
                                    connection.sendall("%s:%d:%d:%s\n" % (
                                        call['file'], call['line'], call['column'], call['content']))

                        # If we got that far, it means we did not find an
                        # answer
                        connection.sendall("DONE\n")

                    else:
                        self.logger.debug(
                            'No more data from %s', client_address)
                        break
            finally:
                # Clean up the connection
                connection.close()
        self.logger.info('Server exiting')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port',
                        default=10000,
                        help='Listening port.')
    parser.add_argument('--index',
                        help='Index file.')
    parser.add_argument('--no_server',
                        default=False,
                        help='Do not start server.',
                        action='store_true')

    args, unknown_args = parser.parse_known_args()
    argv = [sys.argv[0]] + unknown_args

    server = Server(args.index)
    if len(argv) > 1:
        sources = server.indexer.find_source_files(argv[1])
        server.indexer.Index(sources, argv[1])
    if not args.no_server:
        server._run(args.port)

    return 0

if __name__ == "__main__":
    sys.exit(main())
