import clang.cindex
import logging
import os
import platform
import re
import sys
import time


class Indexer(object):

    def __init__(self, index_file=None, logger=None):
        self.index_file = index_file
        self.server_thread = None
        self.includes = []
        self.observer = None
        self._clear()
        self.logger = logger

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

    def _clear(self):
        self.functions = {}
        self.types = {}

    @staticmethod
    def find_source_files(rootdir):
        sources = []
        for root, subdirs, files in os.walk(rootdir):
            for filename in files:
                if os.path.splitext(filename)[1] in ['.c', '.cpp', '.h', '.hpp']:
                    filename = os.path.join(root, filename)
                    sources.append(filename)
        return sources

    def IndexDirectory(self, root):
        sources = self.find_source_files(root)
        self._clear()
        self.Index(sources, root)

    def Index(self, files=[], root=None):
        self.logger.info('Indexing %d file(s)...',  len(files))
        t0 = time.time()
        for filename in files:
            self.logger.debug('Parsing %s', filename)
            try:
                # Get AST from Clang
                tu = self.cindex.parse(filename, self.includes)
                # Make sure to first remove any information that were
                # previously in this file
                for k in self.functions:
                    fn = self.functions[k]
                    decl = fn['FUNCTION_DECL']
                    impl = fn['FUNCTION_IMPL']
                    calls = fn['CALL_EXPR']
                    if (decl and decl['file'] == filename):
                        self.logger.debug(
                            'Removing function %s declaration from %s', k, filename)
                        del self.functions[k]['FUNCTION_DECL']
                    if (impl and impl['file'] == filename):
                        self.logger.debug(
                            'Removing function %s implementation from %s', k, filename)
                        del self.functions[k]['FUNCTION_IMPL']
                    for idx, call in enumerate(calls):
                        if call['file'] == filename:
                            self.logger.debug(
                                'Removing function %s call from %s', k, filename)
                            del self.functions[k]['CALL_EXPR'][idx]
                # Fill internal structure
                self._parse(tu.cursor, filename)
            except clang.cindex.TranslationUnitLoadError:
                self.logger.warning('Failed ot parse %s', filename)
        t1 = time.time()

        self.logger.info('Done indexing %d file(s) %d function(s) %d type(s) in %0.3f ms...', len(
            files), len(self.functions), len(self.types), (t1 - t0) * 1000.0)

        if self.index_file:
            self.logger.info('Saving index into %s', self.index_file)
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
                            sources = self.indexer.find_source_files(
                                event.src_path)
                            self.indexer.index(sources)

                self.logger.info('Watching changes under %s', root)
                if self.observer:
                    self.observer.stop()
                handler = EventHandler(self)
                self.observer = Observer()
                self.observer.schedule(handler, root, recursive=True)
                self.observer.start()
            except ImportError:
                self.logger.warning('File monitor not available')
        # Clean up after ourself
        self.index_thread = None

    def Autocomplete(self, lookup):
        matches = set()
        matches |= set(
            [k for k, v in self.functions.items() if k.startswith(lookup)])
        matches |= set(
            [k for k, v in self.types.items() if k.startswith(lookup)])
        return matches

    def Implementation(self, lookup):
        impl = None
        if lookup in self.functions:
            if 'file' in self.functions[lookup]['FUNCTION_IMPL']:
                impl = self.functions[
                    lookup]['FUNCTION_IMPL']
        return impl

    def Declaration(self, lookup):
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
        return decl

    def Calls(self, lookup):
        calls = None
        if lookup in self.functions:
            if 'file' in self.functions[lookup]['FUNCTION_IMPL']:
                calls = self.functions[lookup]['CALL_EXPR']
        elif lookup in self.types:
            if 'file' in self.types[lookup]['TYPE_DECL']:
                calls = self.types[lookup]['TYPE_REF']
        return calls

    def _init_func(self, func):
        if not func in self.functions:
            self.functions[func] = {'FUNCTION_IMPL': {},
                                    'FUNCTION_DECL': {}, 'CALL_EXPR': []}

    def _init_type(self, tpe):
        if not tpe in self.types:
            self.types[tpe] = {'TYPE_DECL': {}, 'TYPE_REF': []}

    def _location_to_dict(self, location):
            return {
                'file': location.file.name,
                'line': location.line,
                'column': location.column,
            }

    def _add_func(self, node):
        self._init_func(node.spelling)
        if os.path.splitext(node.location.file.name)[1] in ['.c', '.cpp']:
            self.functions[node.spelling][
                'FUNCTION_IMPL'] = self._location_to_dict(node.location)
        else:
            self.functions[node.spelling][
                'FUNCTION_DECL'] = self._location_to_dict(node.location)

    def _add_type(self, node):
        self._init_type(node.spelling)
        self.types[node.spelling][
            'TYPE_DECL'] = self._location_to_dict(node.location)

    def _add_call(self, node):
        # TODO we want the actual line as well
        self._init_func(node.spelling)
        self.functions[node.spelling]['CALL_EXPR'].append(
            self._location_to_dict(node.location))

    def _add_ref(self, node):
        self._init_type(node.spelling)
        self.types[node.spelling]['TYPE_REF'].append(
            self._location_to_dict(node.location))

    def _parse(self, node, filename):
        try:
            self.logger.debug('Node %s %s %d', node.kind,
                              node.spelling, node.location.line)
            if (node.location.file and node.location.file.name == filename):
                if (node.kind == clang.cindex.CursorKind.FUNCTION_DECL):
                    self.logger.debug('FUNCTION_DECL:%s:%s:%d', node.spelling,
                                      node.location.file.name, node.location.line)
                    self._add_func(node)
                elif (node.kind == clang.cindex.CursorKind.TYPEDEF_DECL):
                    self.logger.debug(
                        'TYPE_DECL:%s:%s:%d', node.spelling, node.location.file.name, node.location.line)
                    self._add_type(node)
                elif (node.kind == clang.cindex.CursorKind.CALL_EXPR):
                    self.logger.debug(
                        'CALL:%s:%s: %d', node.spelling, node.location.file.name, node.location.line)
                    self._add_call(node)
                elif (node.kind == clang.cindex.CursorKind.TYPE_REF):
                    self.logger.debug(
                        'TYPE_REF:%s:%s:%d', node.spelling, node.location.file.name, node.location.line)
                    self._add_ref(node)
        except ValueError:
            # Incompatible libclang and pyclang?
            self.logger.warning("Ignoring node %s %s %d", node.spelling,
                                node.location.file.name, node.location.line)

        # Recurse on children
        for c in node.get_children():
            self._parse(c, filename)
