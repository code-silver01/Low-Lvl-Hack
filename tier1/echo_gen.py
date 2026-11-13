#!/usr/bin/env python3
"""Generate echo.txt - SUBLEQ program that copies input to output."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tools'))
from asm import Asm

a = Asm()

# Data cells
a.var('Z', 0)
a.var('N1', -1)
a.var('T', 0)

# Code
a.label('loop')
a.clear('T')                    # T = 0
a.emit('T', a.IN)              # T = 0 - input = -byte (or 1 if EOF)

# Check EOF: if T > 0 (T == 1 for EOF), halt
# Z - T: if T > 0, result = -T < 0, jump to halt. Z = -T (dirty).
a.emit('Z', 'T', 'halt')      # if T > 0 (EOF), jump to halt. Z gets dirty!
a.clear('Z')                    # restore Z (only reached if T <= 0)

# Output byte
a.emit(a.OUT, 'T')            # print 0 - (-byte) = byte

# Loop
a.jmp('loop')

# Halt - Z might be dirty here, so restore it first!
a.label('halt')
a.clear('Z')                    # restore Z = 0
a.halt()                        # N1 Z -1: r = -1 - 0 = -1 < 0, jump to -1

# Write output
out_path = os.path.join(os.path.dirname(__file__), 'echo.txt')
a.write(out_path)
print(f"Generated {out_path} ({len(a._words)} words)")
