"""
SUBLEQ Assembler and Macro Library
Designed for high efficiency and robustness.

SUBLEQ semantics:
Instruction at pc: a b c
r = mem[a] - mem[b]
if a != OUT: mem[a] = r
else: putchar(r & 0xFF)
if r < 0: pc = c
else: pc = pc + 3
"""

import sys
import subprocess
import os

OUT_ADDR = 1048575
IN_ADDR  = 1048574
N_WORDS  = 1048576

class Assembler:
    def __init__(self):
        self.code = []       # list of words (ints or label names or (label, offset))
        self.labels = {}     # label_name -> address
        self.data_vars = []  # list of (name, initial_value)
        self.anon_counter = 0

    def new_label(self, prefix="L"):
        self.anon_counter += 1
        return f"{prefix}_{self.anon_counter}"

    def set_label(self, name):
        if name in self.labels:
            raise ValueError(f"Duplicate label: {name}")
        self.labels[name] = len(self.code)

    def var(self, name, init=0):
        self.data_vars.append((name, init))
        return name

    def array(self, name, size):
        self.data_vars.append((name, [0] * size))
        return name

    def emit_raw(self, *words):
        for w in words:
            self.code.append(w)

    def subleq(self, a, b, c=None):
        """Emit a b c. If c is None, c = next instruction (pc + 3)."""
        curr = len(self.code)
        if c is None:
            c = curr + 3
        self.code.extend([a, b, c])

    # Basic macros
    def clr(self, a):
        """mem[a] = 0 (1 instruction: a a pc+3)"""
        self.subleq(a, a)

    def jmp(self, target):
        """Unconditional jump to target using ZERO and NEG1 (1 instruction).
        NEG1 - ZERO = -1 < 0 -> jumps to target. NEG1 remains -1."""
        self.subleq("NEG1", "ZERO", target)

    def mov(self, dst, src):
        """mem[dst] = mem[src]
        Uses TEMP.
        TEMP = 0
        TEMP -= src  (TEMP = -src)
        dst = 0
        dst -= TEMP  (dst = src)
        TEMP = 0
        """
        self.clr("TEMP")
        self.subleq("TEMP", src)
        self.clr(dst)
        self.subleq(dst, "TEMP")
        self.clr("TEMP")

    def mov_const(self, dst, val):
        """mem[dst] = val
        If val == 0: clr(dst)
        Otherwise allocates or reuses a constant.
        """
        if val == 0:
            self.clr(dst)
            return
        c_label = f"CONST_{val if val >= 0 else 'M' + str(-val)}"
        if c_label not in [name for name, _ in self.data_vars]:
            self.var(c_label, val)
        self.mov(dst, c_label)

    def add(self, dst, src):
        """mem[dst] += mem[src]
        TEMP = 0
        TEMP -= src  (TEMP = -src)
        dst -= TEMP  (dst += src)
        TEMP = 0
        """
        self.clr("TEMP")
        self.subleq("TEMP", src)
        self.subleq(dst, "TEMP")
        self.clr("TEMP")

    def add_const(self, dst, val):
        if val == 0:
            return
        c_label = f"CONST_{val if val >= 0 else 'M' + str(-val)}"
        if c_label not in [name for name, _ in self.data_vars]:
            self.var(c_label, val)
        self.add(dst, c_label)

    def sub(self, dst, src):
        """mem[dst] -= mem[src] (1 instruction)"""
        self.subleq(dst, src)

    def sub_const(self, dst, val):
        if val == 0:
            return
        c_label = f"CONST_{val if val >= 0 else 'M' + str(-val)}"
        if c_label not in [name for name, _ in self.data_vars]:
            self.var(c_label, val)
        self.sub(dst, c_label)

    def jn(self, a, target):
        """Jump to target if mem[a] < 0.
        Uses ZERO. mem[a] - ZERO = mem[a]. If < 0, jump to target."""
        self.subleq(a, "ZERO", target)

    def jz(self, a, target):
        """Jump to target if mem[a] == 0.
        Logic:
        if a < 0 -> skip
        TEMP = 0 - a
        if TEMP < 0 (i.e. a > 0) -> skip
        jmp target (since neither < 0 nor > 0, so a == 0)
        """
        skip = self.new_label("skip_jz")
        self.subleq(a, "ZERO", skip)      # if a < 0, jump to skip
        self.clr("TEMP")
        self.subleq("TEMP", a)             # TEMP = -a
        self.subleq("TEMP", "ZERO", skip)  # if -a < 0 (a > 0), jump to skip
        self.jmp(target)                   # a == 0!
        self.set_label(skip)
        self.clr("TEMP")

    def jnz(self, a, target):
        """Jump to target if mem[a] != 0.
        if a < 0 -> jump target
        TEMP = 0 - a
        if TEMP < 0 (a > 0) -> jump target
        """
        self.subleq(a, "ZERO", target)
        self.clr("TEMP")
        self.subleq("TEMP", a)
        self.subleq("TEMP", "ZERO", target)
        self.clr("TEMP")

    def jge(self, a, target):
        """Jump if mem[a] >= 0.
        if a < 0 -> skip
        jmp target
        """
        skip = self.new_label("skip_jge")
        self.subleq(a, "ZERO", skip)
        self.jmp(target)
        self.set_label(skip)

    def jgt(self, a, target):
        """Jump if mem[a] > 0.
        TEMP = 0 - a
        if TEMP < 0 (a > 0) -> jump target
        """
        self.clr("TEMP")
        self.subleq("TEMP", a)
        self.subleq("TEMP", "ZERO", target)
        self.clr("TEMP")

    def jle(self, a, target):
        """Jump if mem[a] <= 0.
        TEMP = 0 - a
        if TEMP < 0 (a > 0) -> skip
        jmp target
        """
        skip = self.new_label("skip_jle")
        self.clr("TEMP")
        self.subleq("TEMP", a)
        self.subleq("TEMP", "ZERO", skip)
        self.clr("TEMP")
        self.jmp(target)
        self.set_label(skip)
        self.clr("TEMP")

    def putc(self, char_var):
        """Print ASCII byte stored in char_var.
        OUT address: mem[OUT] reads as 0, r = 0 - mem[char_var].
        Printed byte is (0 - mem[char_var]) & 0xFF.
        Wait! The VM spec says:
        'If a = OUT, the machine prints the low 8 bits of r (here r = 0 - mem[b]) and stores nothing.'
        So if we do: subleq(OUT, b) -> it prints (-mem[b]) & 0xFF!
        Therefore, to print char_var, char_var must be negated FIRST, OR
        we put -char_var in TEMP and subleq(OUT, TEMP)!
        Let's verify:
        If TEMP = -char_var:
        r = 0 - (-char_var) = char_var.
        Prints (char_var & 0xFF)!
        """
        self.clr("TEMP")
        self.subleq("TEMP", char_var)  # TEMP = -char_var
        self.subleq(OUT_ADDR, "TEMP")  # prints 0 - (-char_var) = char_var
        self.clr("TEMP")

    def putc_const(self, ch_val):
        """Print a constant character."""
        # For constant, we can store -ch_val in a data var!
        # Then: subleq(OUT_ADDR, NEG_CH) prints 0 - (-ch_val) = ch_val directly in 1 instruction!
        neg_val = -ch_val
        c_label = f"CONST_NEG_CH_{ch_val}"
        if c_label not in [name for name, _ in self.data_vars]:
            self.var(c_label, neg_val)
        self.subleq(OUT_ADDR, c_label)

    def getc(self, dst):
        """Read 1 byte from IN into dst.
        If EOF, dst = -1.
        VM spec: 'Reading IN as b returns next input byte (0 to 255) or -1 once ended.'
        subleq(TEMP, IN) -> TEMP = 0 - IN_byte = -byte (or +1 if EOF).
        Then dst = -TEMP = IN_byte (or -1 if EOF).
        """
        self.clr("TEMP")
        self.subleq("TEMP", IN_ADDR)   # TEMP = -IN_val
        self.clr(dst)
        self.subleq(dst, "TEMP")       # dst = IN_val
        self.clr("TEMP")

    # Indirect memory operations (self-modifying code)
    def load_indirect(self, dst, ptr):
        """dst = mem[mem[ptr]]
        We modify the 'b' operand of a subleq instruction:
        instr: subleq(TEMP, 0)
        We patch instr+1 with mem[ptr].
        """
        instr_addr_lbl = self.new_label("load_instr")
        # patch instr_addr + 1
        # To patch instr_addr + 1, we do:
        # instr_addr+1 = mem[ptr]
        self.mov((instr_addr_lbl, 1), ptr)
        # Execute patched instruction:
        self.clr("TEMP")
        self.set_label(instr_addr_lbl)
        self.subleq("TEMP", 0)  # TEMP = -mem[mem[ptr]]
        self.clr(dst)
        self.subleq(dst, "TEMP") # dst = mem[mem[ptr]]
        self.clr("TEMP")

    def store_indirect(self, ptr, src):
        """mem[mem[ptr]] = mem[src]
        We modify BOTH 'a' and 'b' of a clr instruction, and 'a' of a subtract instruction:
        clear target: mem[target] = 0
        target -= (-src) -> mem[target] = src
        """
        clr_instr_lbl = self.new_label("store_clr")
        sub_instr_lbl = self.new_label("store_sub")

        # patch clr_instr: both a (offset 0) and b (offset 1)
        self.mov((clr_instr_lbl, 0), ptr)
        self.mov((clr_instr_lbl, 1), ptr)
        # patch sub_instr: a (offset 0)
        self.mov((sub_instr_lbl, 0), ptr)

        # compute TEMP = -src
        self.clr("TEMP")
        self.subleq("TEMP", src)

        # clear target
        self.set_label(clr_instr_lbl)
        self.subleq(0, 0)

        # target -= TEMP (i.e. target += src)
        self.set_label(sub_instr_lbl)
        self.subleq(0, "TEMP")
        self.clr("TEMP")

    def assemble(self):
        """Resolve all labels and return list of integers."""
        # Standard variables
        # Ensure ZERO, NEG1, TEMP, TEMP2 are present
        std_vars = [("ZERO", 0), ("NEG1", -1), ("TEMP", 0), ("TEMP2", 0)]
        existing = {name for name, _ in self.data_vars}
        for name, val in std_vars:
            if name not in existing:
                self.data_vars.insert(0, (name, val))

        # Append data section
        data_start = len(self.code)
        curr_addr = data_start
        for name, val in self.data_vars:
            self.labels[name] = curr_addr
            if isinstance(val, list):
                self.code.extend(val)
                curr_addr += len(val)
            else:
                self.code.append(val)
                curr_addr += 1

        # Resolve all label references
        resolved = []
        for i, word in enumerate(self.code):
            if isinstance(word, int):
                resolved.append(word)
            elif isinstance(word, str):
                if word not in self.labels:
                    raise ValueError(f"Undefined label: {word}")
                resolved.append(self.labels[word])
            elif isinstance(word, tuple):
                # (label_name, offset)
                base_lbl, offset = word
                if base_lbl not in self.labels:
                    raise ValueError(f"Undefined label: {base_lbl}")
                resolved.append(self.labels[base_lbl] + offset)
            else:
                raise TypeError(f"Invalid code element at {i}: {word}")

        return resolved

    def to_string(self):
        words = self.assemble()
        return " ".join(str(w) for w in words)
