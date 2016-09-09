#!/usr/bin/env python
import argparse, sys, socket

def gets(socket):
    lines = []
    while True:
        data = socket.recv(4096)
        tmp = data.split("\n")
        del tmp[-1]
        lines = lines + tmp
        if "DONE" in tmp:
            del lines[-1]
            return lines

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port',
            default=10000,
            help='Listening port.')

    args, unknown_args = parser.parse_known_args()
    argv = [sys.argv[0]] + unknown_args

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_address = ('localhost', args.port)
    try:
        sock.connect(server_address)
    except:
        return 1

    try:
        # Filter on allowed commands
        if argv[1] in ['INDEX', 'IMPL', 'DECL', 'CALLS', 'AUTO']:
            message = "%s %s\n" % (argv[1], argv[2])
            sock.sendall(message)
            lines = gets(sock)
            for line in lines:
                print line
            return 0
        else:
            return 1
    finally:
        sock.close()

if __name__ == "__main__":
    sys.exit(main())
