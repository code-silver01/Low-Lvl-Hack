#!/usr/bin/env python3
"""
v1 to SUBLEQ Compiler (Tier 2)

Reads a v1 source program from standard input and prints the compiled
SUBLEQ machine program (whitespace-separated decimal integers) to standard output.
"""

import sys
import os

# Add local directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from compiler_v1 import compile_v1_source

def main():
    source = sys.stdin.read()
    if not source.strip():
        return
    machine_code = compile_v1_source(source)
    sys.stdout.write(machine_code)
    sys.stdout.write('\n')

if __name__ == '__main__':
    main()
