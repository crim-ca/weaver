#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
# TODO <will genereate description of process>
"""
import argparse
import os
import sys


def make_parser():
    name = os.path.splitext(os.path.split(__file__)[-1])[0]
    ap = argparse.ArgumentParser(prog=name, description=__doc__, add_help=True)
    # TODO
    # ap.add_argument("arg_name", help="...")
    return ap


def run(arg_name):
    return -1


def main():
    ap = make_parser()
    argv = None if sys.argv[1:] else ['--help']  # auto-help message if no args
    args = ap.parse_args(args=argv)
    return run(**vars(args))  # auto-map arguments by name


if __name__ == "__main__":
    main()
