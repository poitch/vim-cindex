from cindex.server import Indexer
import os

DIR_OF_CURRENT_SCRIPT = os.path.dirname(os.path.abspath(__file__))
DEBUG = False

port = None

def SetupCIndex():
    log_file = False
    if DEBUG:
        log_dir = os.path.join(DIR_OF_CURRENT_SCRIPT, "..", "..", "logs")
        if not os.path.isdir(log_dir):
            os.mkdir(log_dir)
        instance = os.getpid()
        log_file = os.path.join(log_dir, "server-%d.log" % instance)
    return Indexer(log_file = log_file)
