from cindex.server import Server
import os

DIR_OF_CURRENT_SCRIPT = os.path.dirname(os.path.abspath(__file__))

def SetupCIndex(debug = 0):
    log_file = False
    if int(debug) == 1:
        log_dir = os.path.join(DIR_OF_CURRENT_SCRIPT, "..", "..", "logs")
        if not os.path.isdir(log_dir):
            os.mkdir(log_dir)
        instance = os.getpid()
        log_file = os.path.join(log_dir, "server-%d.log" % instance)
    return Server(log_file = log_file)
