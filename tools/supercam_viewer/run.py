#!/usr/bin/env python3
"""SuperCam cross-platform dual-stream viewer (IR left, VIS right).

Usage:
  python run.py                  # use remembered IP
  python run.py 192.168.2.32     # override IP
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from supercam.gui import run  # noqa: E402


if __name__ == '__main__':
    host = sys.argv[1] if len(sys.argv) > 1 else None
    run(host)