#!/usr/bin/env python
import argparse
import clang.cindex
import os
import platform
import re
import socket
import sys
import threading
import time
import watchdog


class Indexer(object):

    def __init__(self, verbose=False, index_file=None):
        self.verbose = verbose
        self.index_file = index_file
        self.index_thread = None
        self.server_thread = None
        self.includes = []
        self.observer = None
        self.clear()

        # Setup clang
        if platform.platform().startswith('Darwin'):
            lib_path = '/Library/Developer/CommandLineTools/usr/lib/libclang.dylib'
            clang.cindex.Config.set_library_file(lib_path)
        elif platform.platform().startswith('Linux'):
            lib_path = '/usr/lib/youcompleteme/third_party/ycmd/libclang.so'
            clang.cindex.Config.set_library_file(lib_path)
        else:
            from ctypes.util import find_library
            clang.cindex.Config.set_library_file(find_library('clang'))
        self.cindex = clang.cindex.Index.create()

    def clear(self):
        self.functions = {}
        self.types = {}

    def crawl(self, rootdir):
        sources = []
        for root, subdirs, files in os.walk(rootdir):
            for filename in files:
                if os.path.splitext(filename)[1] in ['.c', '.cpp', '.h', '.hpp']:
                    filename = os.path.join(root, filename)
                    sources.append(filename)
        return sources

    def index(self, files=[], root=None):
        if self.verbose:
            print >>sys.stderr, 'Indexing %d file(s)...' % len(files)
        t0 = time.time()
        # Create internal structure
        for filename in files:
            if self.verbose:
                print 'Parsing %s' % filename
            try:
                tu = self.cindex.parse(filename, self.includes)
                # Make sure to first remove any information that were
                # previously in this file
                # TODO // FIXME
                for k in self.functions:
                    fn = self.functions[k]
                    decl = fn['FUNCTION_DECL']
                    impl = fn['FUNCTION_IMPL']
                    calls = fn['CALL_EXPR']
                    if (decl and decl['file'] == filename):
                        if self.verbose:
                            print >>sys.stderr, 'Removing function %s declaration from %s' % (
                                k, filename)
                        del self.functions[k]['FUNCTION_DECL']
                    if (impl and impl['file'] == filename):
                        if self.verbose:
                            print >>sys.stderr, 'Removing function %s implementation from %s' % (
                                k, filename)
                        del self.functions[k]['FUNCTION_IMPL']
                    for idx, call in enumerate(calls):
                        if call['file'] == filename:
                            if self.verbose:
                                print >>sys.stderr, 'Removing function %s call from %s' % (
                                    k, filename)
                            del self.functions[k]['CALL_EXPR'][idx]

                self.parse(tu.cursor, filename)
            except clang.cindex.TranslationUnitLoadError:
                if self.verbose:
                    print 'Failed ot parse %s' % filename
        t1 = time.time()

        if self.verbose:
            print >>sys.stderr, 'Done indexing %d file(s) %d function(s) %d type(s) in %0.3f ms...' % (
                len(files), len(self.functions), len(self.types), (t1 - t0) * 1000.0)

        if self.index_file:
            if self.verbose:
                print >>sys.stderr, 'Saving index into %s' % self.index_file
            with open(self.index_file, 'w') as output:
                for function in self.functions:
                    defined = False
                    if 'file' in self.functions[function]['FUNCTION_DECL']:
                        output.write("DECL %s (%s:%d)\n" % (function, self.functions[function][
                                     'FUNCTION_DECL']['file'], self.functions[function]['FUNCTION_DECL']['line']))
                        defined = True
                    if 'file' in self.functions[function]['FUNCTION_IMPL']:
                        output.write("IMPL %s (%s:%d)\n" % (function, self.functions[function][
                                     'FUNCTION_IMPL']['file'], self.functions[function]['FUNCTION_IMPL']['line']))
                        defined = True
                    if defined:
                        for call in self.functions[function]['CALL_EXPR']:
                            output.write("CALL %s (%s:%d)\n" %
                                         (function, call['file'], call['line']))
                for tpe in self.types:
                    if 'file' in self.types[tpe]['TYPE_DECL']:
                        output.write("TYPE %s (%s:%d)\n" % (function, self.types[tpe][
                                     'TYPE_DECL']['file'], self.types[tpe]['TYPE_DECL']['line']))
                        for call in self.types[tpe]['TYPE_REF']:
                            output.write("REF %s (%s:%d)\n" %
                                         (function, call['file'], call['line']))
        if root:
            # Attempt to watch changes if monitor is available
            try:
                from watchdog.observers import Observer
                from watchdog.events import FileSystemEventHandler

                class EventHandler(FileSystemEventHandler):

                    def __init__(self, indexer):
                        self.indexer = indexer

                    def on_deleted(self, event):
                        # That one is tricky, we technically need to clean up
                        # files deleted from the internal structures
                        return

                    def on_modified(self, event):
                        if not event.is_directory:
                            self.indexer.index([event.src_path])

                    def on_created(self, event):
                        if not event.is_directory:
                            self.indexer.index([event.src_path])
                        else:
                            sources = self.indexer.crawl(event.src_path)
                            self.indexer.index(sources)

                if self.verbose:
                    print >>sys.stderr, 'Watching changes under %s' % root
                if self.observer:
                    self.observer.stop()
                handler = EventHandler(self)
                self.observer = Observer()
                self.observer.schedule(handler, root, recursive=True)
                self.observer.start()
            except ImportError:
                if self.verbose:
                    print >>sys.stderr, 'File monitor not available'

        # Debug output of structure
        if self.verbose:
            for function in self.functions:
                if 'file' in self.functions[function]['FUNCTION_DECL']:
                    print '%s (%s:%d)' % (function, self.functions[function]['FUNCTION_DECL']['file'], self.functions[function]['FUNCTION_DECL']['line'])
                    for call in self.functions[function]['CALL_EXPR']:
                        print '    %s:%d' % (call['file'], call['line'])
                elif 'file' in self.functions[function]['FUNCTION_IMPL']:
                    print '>>>> %s (%s:%d)' % (function, self.functions[function]['FUNCTION_IMPL']['file'], self.functions[function]['FUNCTION_IMPL']['line'])
                    for call in self.functions[function]['CALL_EXPR']:
                        print '    %s:%d' % (call['file'], call['line'])

        self.index_thread = None

    def _get_unused_local_port(self):
        sock = socket.socket()
        # This tells the OS to give us any free port in the range [1024 -
        # 65535]
        sock.bind(('', 0))
        port = sock.getsockname()[1]
        sock.close()
        return port

    def StartServer(self):
        port = self._get_unused_local_port()
        self.server_thread = threading.Thread(target=self.run, args=(port,))
        self.server_thread.daemon = True
        self.server_thread.start()
        return port

    def StopServer(self):
        if self.server_thread:
            self.server_thread.stop()
            self.server_thread = None

    def run(self, port=10000):
        """Start TCP server to answer basic grammar:
            DECL <name> returns location of function/type declaration
            IMPL <name> returns locatino of function/type implementation
            CALLS <name> returns list of locations of usage of function/type
            INDEX <path> indexes C/C++ files under given path
            AUTO <prefix> returns list of function/type starting with prefix."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        server_address = ('localhost', int(port))
        #print >>sys.stderr, 'Starting up on %s port %s' % server_address
        sock.bind(server_address)
        # Listen for incoming connections
        sock.listen(1)
        while True:
            # Wait for a connection
            #print >>sys.stderr, 'Waiting for a connection'
            connection, client_address = sock.accept()
            try:
                #print >>sys.stderr, 'Connection from', client_address
                # Receive the data in small chunks and retransmit it
                while True:
                    data = connection.recv(2048)
                    #print >>sys.stderr, 'Received "%s"' % data.rstrip()
                    if data:
                        if data.startswith('QUIT'):
                            connection.sendall("DONE\n")
                            break
                        elif data.startswith('INDEX'):
                            lookup = data[6:].rstrip()
                            #print >>sys.stderr, "INDEX for '%s'" % lookup
                            if not self.index_thread:
                                sources = self.crawl(lookup)
                                self.clear()
                                self.index_thread = threading.Thread(
                                    target=self.index, args=(sources, lookup,))
                                self.index_thread.start()
                                connection.sendall("INDEXING\n")
                            else:
                                connection.sendall("BUSY\n")
                        elif data.startswith('AUTO'):
                            lookup = data[5:].rstrip()
                            #print >>sys.stderr, "AUTO for '%s'" % lookup
                            matches = set()
                            matches |= set(
                                [k for k, v in self.functions.items() if k.startswith(lookup)])
                            matches |= set(
                                [k for k, v in self.types.items() if k.startswith(lookup)])
                            for match in matches:
                                connection.sendall("%s\n" % match)
                        elif data.startswith('IMPL'):
                            lookup = data[5:].rstrip()
                            #print >>sys.stderr, "IMPL for '%s'" % lookup
                            impl = None
                            if lookup in self.functions:
                                if 'file' in self.functions[lookup]['FUNCTION_IMPL']:
                                    impl = self.functions[
                                        lookup]['FUNCTION_IMPL']
                            if impl:
                                connection.sendall("%s:%d:%d\n" % (
                                    impl['file'], impl['line'], impl['column']))
                        elif data.startswith('DECL'):
                            lookup = data[5:].rstrip()
                            #print >>sys.stderr, "DECL for '%s'" % lookup
                            decl = None
                            if lookup in self.functions:
                                if 'file' in self.functions[lookup]['FUNCTION_DECL']:
                                    decl = self.functions[
                                        lookup]['FUNCTION_DECL']
                                elif 'file' in self.functions[lookup]['FUNCTION_IMPL']:
                                    decl = self.functions[
                                        lookup]['FUNCTION_IMPL']
                            elif lookup in self.types:
                                if 'file' in self.types[lookup]['TYPE_DECL']:
                                    decl = self.types[lookup]['TYPE_DECL']
                            if decl:
                                connection.sendall("%s:%d:%d\n" % (
                                    decl['file'], decl['line'], decl['column']))
                        elif data.startswith('CALLS'):
                            lookup = data[6:].rstrip()
                            #print >>sys.stderr, "CALLS for '%s'" % lookup
                            calls = None
                            if lookup in self.functions:
                                if 'file' in self.functions[lookup]['FUNCTION_IMPL']:
                                    calls = self.functions[lookup]['CALL_EXPR']
                            elif lookup in self.types:
                                if 'file' in self.types[lookup]['TYPE_DECL']:
                                    calls = self.types[lookup]['TYPE_REF']
                            if (calls and len(calls) > 0):
                                for call in calls:
                                    connection.sendall("%s:%d:%d\n" % (
                                        call['file'], call['line'], call['column']))

                        # If we got that far, it means we did not find an
                        # answer
                        connection.sendall("DONE\n")

                    else:
                        #print >>sys.stderr, 'no more data from', client_address
                        break
            finally:
                # Clean up the connection
                connection.close()

    def _init_func(self, func):
        if not func in self.functions:
            self.functions[func] = {'FUNCTION_IMPL': {},
                                    'FUNCTION_DECL': {}, 'CALL_EXPR': []}

    def _init_type(self, tpe):
        if not tpe in self.types:
            self.types[tpe] = {'TYPE_DECL': {}, 'TYPE_REF': []}

    def _location_to_json(self, location):
            return {
                'file': location.file.name,
                'line': location.line,
                'column': location.column,
            }

    def _add_func(self, node):
        self._init_func(node.spelling)
        if os.path.splitext(node.location.file.name)[1] in ['.c', '.cpp']:
            self.functions[node.spelling][
                'FUNCTION_IMPL'] = self._location_to_json(node.location)
        else:
            self.functions[node.spelling][
                'FUNCTION_DECL'] = self._location_to_json(node.location)

    def _add_type(self, node):
        self._init_type(node.spelling)
        self.types[node.spelling][
            'TYPE_DECL'] = self._location_to_json(node.location)

    def _add_call(self, node):
        self._init_func(node.spelling)
        self.functions[node.spelling]['CALL_EXPR'].append(
            self._location_to_json(node.location))

    def _add_ref(self, node):
        self._init_type(node.spelling)
        self.types[node.spelling]['TYPE_REF'].append(
            self._location_to_json(node.location))

    def parse(self, node, filename):
        try:
            if self.verbose:
                print 'Node %s %s %d' % (node.kind, node.spelling, node.location.line)
            if (node.location.file and node.location.file.name == filename):
                if (node.kind == clang.cindex.CursorKind.FUNCTION_DECL):
                    if self.verbose:
                        print 'FUNCTION_DECL:%s:%s:%d' % (node.spelling, node.location.file.name, node.location.line)
                    self._add_func(node)
                elif (node.kind == clang.cindex.CursorKind.TYPEDEF_DECL):
                    if self.verbose:
                        print 'TYPE_DECL:%s:%s:%d' % (node.spelling, node.location.file.name, node.location.line)
                    self._add_type(node)
                elif (node.kind == clang.cindex.CursorKind.CALL_EXPR):
                    if self.verbose:
                        print 'CALL:%s:%s: %d' % (node.spelling, node.location.file.name, node.location.line)
                    self._add_call(node)
                elif (node.kind == clang.cindex.CursorKind.TYPE_REF):
                    if self.verbose:
                        print 'TYPE_REF:%s:%s:%d' % (node.spelling, node.location.file.name, node.location.line)
                    self._add_ref(node)
        except ValueError:
            # Incompatible libclang and pyclang?
            if self.verbose:
                print >>sys.stderr, "Ignoring node %s %s %d" % (
                    node.spelling, node.location.file.name, node.location.line)

        for c in node.get_children():
            self.parse(c, filename)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--verbose',
                        default=False,
                        help='Print out debug information.',
                        action='store_true')
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

    indexer = Indexer(args.verbose, args.index)
    if len(argv) > 1:
        sources = indexer.crawl(argv[1])
        indexer.index(sources, argv[1])
    if not args.no_server:
        indexer.run(args.port)

    return 0

if __name__ == "__main__":
    sys.exit(main())
