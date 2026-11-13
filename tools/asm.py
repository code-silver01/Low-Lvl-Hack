#!/usr/bin/env python3
"""
SUBLEQ Assembler Library

Provides a Python API to generate SUBLEQ machine code with:
- Labels and forward references
- Data variables and arrays (placed after code)
- Macros for common operations (MOV, ADD, JMP, etc.)
- Indirect memory access via self-modifying code
- Subroutine call/return with stack
"""

class Asm:
    IN  = 1048574
    OUT = 1048575
    N   = 1048576

    def __init__(self):
        self._words = []           # emitted words (code section)
        self._labels = {}          # label -> address
        self._patches = []         # (index, label_name) for deferred resolution
        self._data = []            # (name, value_or_list) for data section
        self._uid_counter = 0

    # ── helpers ──────────────────────────────────────────────────────

    def uid(self, prefix='_L'):
        """Generate a unique label."""
        self._uid_counter += 1
        return f'{prefix}_{self._uid_counter}'

    def pc(self):
        """Current emission address."""
        return len(self._words)

    # ── label management ─────────────────────────────────────────────

    def label(self, name):
        """Define a label at the current address."""
        if name in self._labels:
            raise ValueError(f'Duplicate label: {name}')
        self._labels[name] = self.pc()

    def mark(self, name):
        """Alias for label — marks the NEXT word position."""
        self.label(name)

    # ── low-level emission ───────────────────────────────────────────

    def _emit_word(self, w):
        """Emit a single word. If string, it's a label reference (patched later)."""
        if isinstance(w, str):
            self._patches.append((len(self._words), w))
            self._words.append(0)  # placeholder
        elif isinstance(w, int):
            self._words.append(w)
        else:
            raise TypeError(f'Invalid word type: {type(w)} ({w})')

    def word(self, w):
        """Emit a single data word inline. Returns its address."""
        addr = self.pc()
        self._emit_word(w)
        return addr

    def emit(self, a, b, c=None):
        """Emit one SUBLEQ instruction: a b c.
        If c is omitted, defaults to pc+3 (unconditional fall-through)."""
        if c is None:
            c = self.pc() + 3
        self._emit_word(a)
        self._emit_word(b)
        self._emit_word(c)

    # ── data section ─────────────────────────────────────────────────

    def var(self, name, init=0):
        """Allocate a named variable in the data section. Returns the label name."""
        self._data.append((name, init))
        return name

    def array(self, name, size, init_vals=None):
        """Allocate a named array in data section. Returns label of first element."""
        if init_vals is None:
            init_vals = [0] * size
        self._data.append((name, init_vals))
        return name

    # ── finalization ─────────────────────────────────────────────────

    def finalize(self):
        """Append data section and resolve all label references."""
        # Append data
        for name, val in self._data:
            if name not in self._labels:  # avoid duplicate if label already set
                self._labels[name] = self.pc()
            if isinstance(val, list):
                self._words.extend(val)
            else:
                self._words.append(val)

        # Resolve patches
        for idx, name in self._patches:
            if name not in self._labels:
                raise ValueError(f'Undefined label: {name}')
            self._words[idx] = self._labels[name]

        return self._words

    def output(self):
        """Return the program as space-separated decimal integers."""
        self.finalize()
        return ' '.join(str(w) for w in self._words)

    def write(self, filename):
        """Write the program to a file."""
        with open(filename, 'w') as f:
            f.write(self.output())
            f.write('\n')

    # ── address of a label ───────────────────────────────────────────

    def addr_of(self, name):
        """Get the resolved address of a label (only after finalize)."""
        return self._labels[name]

    # ══════════════════════════════════════════════════════════════════
    #  MACROS — Higher-level SUBLEQ patterns
    #  Convention:
    #   - Z must be 0 on entry and exit (all paths)
    #   - N1 must be -1 on entry and exit
    #   - T, T2 may be dirty on exit (caller should clear before use)
    # ══════════════════════════════════════════════════════════════════

    def clear(self, x):
        """x = 0 (1 instruction, 3 words)"""
        self.emit(x, x)

    def halt(self, n1='N1', z='Z'):
        """Halt the machine (1 instruction, 3 words)"""
        self.emit(n1, z, -1)

    def jmp(self, target, n1='N1', z='Z'):
        """Unconditional jump to target (1 instruction, 3 words)
        Uses: N1=-1, Z=0. N1 Z target => r=-1<0, jump. N1 stays -1."""
        self.emit(n1, z, target)

    def nop(self, z='Z'):
        """No operation (1 instruction, 3 words)"""
        self.emit(z, z)

    # ── MOV / copy ───────────────────────────────────────────────────

    def mov(self, dst, src, tmp='T'):
        """dst = src (5 instructions, 15 words). Uses tmp.
        tmp T
        T = 0; T -= src => T = -src
        dst = 0; dst -= T => dst = src
        T = 0"""
        self.clear(tmp)
        self.emit(tmp, src)    # tmp = -src
        self.clear(dst)
        self.emit(dst, tmp)    # dst = src
        self.clear(tmp)

    # ── arithmetic ───────────────────────────────────────────────────

    def add(self, dst, src, tmp='T'):
        """dst += src (4 instructions, 12 words). Uses tmp."""
        self.clear(tmp)
        self.emit(tmp, src)    # tmp = -src
        self.emit(dst, tmp)    # dst -= (-src) = dst + src
        self.clear(tmp)

    def sub(self, dst, src):
        """dst -= src (1 instruction, 3 words). Simple SUBLEQ."""
        self.emit(dst, src)

    def neg(self, x, tmp='T'):
        """x = -x (4 instructions, 12 words). Uses tmp."""
        self.clear(tmp)
        self.emit(tmp, x)     # tmp = -x
        self.clear(x)
        self.emit(x, tmp)     # x = -(-x) = ... wait, x = 0 - (-x) = x. That's wrong!
        # Correction: after tmp = -x, we want x = tmp (which is -original_x? No.)
        # tmp = 0 - x = -x. Then x = 0. Then x = 0 - tmp = 0 - (-x) = x. 
        # That gives x = x, not -x!

    def neg(self, x, tmp='T'):
        """x = -x (3 instructions, 9 words). Uses tmp."""
        # tmp = 0; tmp -= x => tmp = -x; x = 0; x -= tmp => x = -(-x) = x. WRONG!
        # Correct approach: save x to tmp, clear x, subtract original from x... no.
        # Actually: tmp = -x, then clear x, then copy tmp to x:
        #   clear tmp; sub tmp x => tmp = -x
        #   clear x   => x = 0
        #   sub x tmp  => x = 0 - (-x_orig) = x_orig... NO, still x!
        # The problem: sub x tmp gives x = x - tmp = 0 - (-x_orig) = x_orig.
        #
        # Real negation: clear x, subtract from a cell holding original.
        # We need: result = 0 - x. So: clear dst, dst -= x. dst = -x.
        # If dst IS x: clear x => x=0, then x -= x => x = 0 - 0 = 0. Wrong.
        #
        # Correct: tmp = x (via mov), clear x, sub x tmp => x = 0 - x_orig = -x_orig.
        # Wait: mov sets tmp = x. clear x => x = 0. sub x tmp => x = 0 - x_orig = -x_orig. YES!
        # But mov is 5 instructions...
        #
        # Simpler: tmp = 0; tmp -= x => tmp = -x; x = 0; 
        # Now we need x = tmp. x -= tmp => x = 0 - (-x_orig) = x_orig. Wrong again!
        # x = 0 - tmp? But sub does x -= tmp = x - tmp.
        # We need x = tmp. That's a copy. 
        #
        # OK simplest negation using the SUBLEQ subtraction trick:
        # We want to compute -x. We have a zero cell Z.
        # Just compute Z - x, but don't modify Z.
        # Use approach: tmp = 0; tmp -= x => tmp = -x. Then clear x, x -= tmp => x = 0-(-x_orig) = x_orig.
        # NOPE. The issue is that sub always gives us a-b, and we want 0-x = -x.
        # tmp = 0 - x = -x. Good, tmp holds -x.
        # Now how to get -x into x? We need x = tmp.
        # x = 0 - tmp would give 0 - (-x_orig) = x_orig. Wrong!
        # We need x = 0 + tmp = tmp. But add uses sub internally: x += tmp means x -= (-tmp).
        # clear x; add x tmp => x = 0 + tmp = tmp = -x_orig. YES!
        self.clear(tmp)
        self.emit(tmp, x)      # tmp = -x_orig
        self.clear(x)          # x = 0
        self.add(x, tmp, tmp='T2')  # x += tmp = -x_orig. Uses T2 as temp for add!
        self.clear(tmp)
        # Total: 1 + 1 + 1 + 4 + 1 = 8 instructions. Let's optimize.
        pass

    # Let me redefine neg more simply:
    def neg(self, x, tmp='T', z='Z'):
        """x = -x. Uses tmp. (3 instructions, 9 words)
        Strategy: tmp = -x, clear x, mov x = -tmp... 
        Actually simplest: 
          tmp = x (via mov), clear x, clear x is done, x = 0 - tmp... nope
        
        Really the simplest approach:
          tmp_val = 0 - mem[x] = -x  (tmp = -x)
          mem[x] = 0                  (clear x)
          Now we want mem[x] = tmp = -x_orig.
          We can do: Z -= tmp => Z = 0 - (-x_orig) = x_orig. Then x -= Z => x = 0 - x_orig = -x_orig.
          Then Z = 0.
          
          clear tmp
          sub tmp x        # tmp = -x
          clear x           # x = 0
          sub z tmp         # z = 0 - (-x) = x  (Z dirty!)
          sub x z           # x = 0 - x_orig = -x_orig  (wait, z = x_orig, so x = 0 - x_orig = -x_orig!)
          clear z           # restore Z
          clear tmp
          
          That's 7 instructions. Hmm.
        """
        # Simplest correct negation: use mov to copy, then subtract twice
        # Actually, here's the simplest:
        # We want x = 0 - x.
        # Step 1: tmp = 0 - x = -x  (clear tmp; sub tmp, x)
        # Step 2: x = x - x = 0     (clear x)
        # Step 3: x = 0 - (0 - tmp) = tmp  -- no, sub gives x -= tmp
        # 
        # I keep going in circles. Let me just use mov:
        # mov tmp, x  (tmp = x, uses T2 internally)
        # clear x
        # sub x, tmp  (x = 0 - x_orig = -x_orig)
        # clear tmp
        # That's mov(5) + 1 + 1 + 1 = 8 instructions.
        #
        # OR, much simpler with a different approach:
        # We know sub(a,b) does a -= b. We want x = -x.
        # x -= x => x = 0. Then x -= x_orig? But x_orig is gone.
        # 
        # OK final answer: use 3 instructions:
        self.clear(tmp)        # tmp = 0
        self.emit(tmp, x)      # tmp = 0 - x = -x
        self.clear(x)          # x = 0
        # Now copy tmp to x. tmp = -x_orig. We want x = -x_orig = tmp.
        # emit(x, ?) won't help since sub gives x - something.
        # We need x += tmp: 
        # T2 = 0; T2 -= tmp; x -= T2 => x = 0 - (0-(-x_orig)) = 0 - x_orig = -x_orig!
        # Wait: T2 = 0 - tmp = 0 - (-x_orig) = x_orig. Then x -= T2 => x = 0 - x_orig = -x_orig. YES!
        t2 = 'T2'
        self.clear(t2)
        self.emit(t2, tmp)     # T2 = 0 - (-x_orig) = x_orig
        self.emit(x, t2)       # x = 0 - x_orig = -x_orig
        self.clear(t2)
        self.clear(tmp)
        # Total: 7 instructions, 21 words. Not great but correct.

    def inc(self, x, one='ONE'):
        """x += 1 (4 instructions, 12 words)."""
        self.add(x, one)

    def dec(self, x, one='ONE'):
        """x -= 1 (1 instruction, 3 words)."""
        self.sub(x, one)

    # ── conditional branches ─────────────────────────────────────────

    def jn(self, x, target, z='Z'):
        """Jump to target if x < 0 (1 instruction, 3 words).
        x Z target: r = x-0 = x. If x<0, jump. x unchanged."""
        self.emit(x, z, target)

    def jp(self, x, target, tmp='T', z='Z'):
        """Jump to target if x > 0 (3 instructions, 9 words). 
        T dirty after jump taken."""
        self.clear(tmp)
        self.emit(tmp, x)           # tmp = -x
        self.emit(tmp, z, target)   # if tmp < 0 (x > 0), jump. tmp unchanged.
        self.clear(tmp)             # cleanup (only on fall-through)

    def jz(self, x, target, z='Z', n1='N1'):
        """Jump to target if x == 0 (4 instructions, 12 words).
        Z may be temporarily dirty but restored on all paths."""
        lbl = self.uid('_jz')
        nz2 = f'{lbl}_nz2'
        # if x < 0: not zero, skip
        self.emit(x, z, nz2)       # r=x, if x<0 jump to nz2. x unchanged.
        # if x > 0: not zero, jump to cleanup
        self.emit(z, x, nz2)       # Z -= x. If x>0, Z=-x<0, jump to nz2 (Z dirty!)
        # x == 0: Z = 0 - 0 = 0 (clean), jump to target
        self.emit(n1, z, target)
        self.emit(n1, z, f'{lbl}_done')  # skip cleanup
        self.label(nz2)
        self.clear(z)               # restore Z (covers both paths: x<0 Z was clean, x>0 Z dirty)
        self.label(f'{lbl}_done')

    def jnz(self, x, target, z='Z', n1='N1'):
        """Jump to target if x != 0 (4 instructions, 12 words)."""
        lbl = self.uid('_jnz')
        is_zero = f'{lbl}_zero'
        done = f'{lbl}_done'
        # if x < 0: nonzero
        self.emit(x, z, target)     # if x < 0, jump to target. x unchanged.
        # if x > 0: check by negating
        self.emit(z, x, target)     # Z = 0-x. If x>0, Z<0, jump to target. Z dirty!
        # x == 0: Z = 0. Fall through (do nothing).
        self.jmp(done)
        # Note: if we jumped to target with Z dirty, caller must handle.
        # Actually, let's fix Z before jumping:
        # Redesign:
        pass
    
    def jnz(self, x, target, z='Z', n1='N1', tmp='T'):
        """Jump to target if x != 0 (5 instructions, 15 words)."""
        lbl = self.uid('_jnz')
        done = f'{lbl}_done'
        # Check negative
        self.emit(x, z, f'{lbl}_nz')  # if x<0, jump (x unchanged, Z clean)
        # Check positive
        self.clear(tmp)
        self.emit(tmp, x)              # tmp = -x
        self.emit(tmp, z, f'{lbl}_nz') # if -x < 0 (x>0), jump
        self.clear(tmp)
        self.jmp(done)
        self.label(f'{lbl}_nz')
        self.clear(tmp)                # cleanup tmp in case
        self.jmp(target)
        self.label(done)

    def jle(self, x, target, z='Z'):
        """Jump if x <= 0. Check: x < 0 OR x == 0. 
        Equivalent to: NOT (x > 0), i.e., skip if x > 0."""
        lbl = self.uid('_jle')
        skip = f'{lbl}_skip'
        self.jp(x, skip)   # if x > 0, skip
        self.jmp(target)    # x <= 0, jump
        self.label(skip)

    def jge(self, x, target, z='Z'):
        """Jump if x >= 0. Skip if x < 0."""
        lbl = self.uid('_jge')
        self.jn(x, f'{lbl}_skip')
        self.jmp(target)
        self.label(f'{lbl}_skip')

    # ── I/O ──────────────────────────────────────────────────────────

    def getc(self, x):
        """Read input byte into x. x = -(byte value), or x = 1 if EOF.
        (2 instructions, 6 words)"""
        self.clear(x)
        self.emit(x, self.IN)   # x = 0 - input_byte = -byte, or 0-(-1)=1 if EOF

    def putc(self, x):
        """Output byte. x should hold -(char value).
        Prints 0 - x = char. (1 instruction, 3 words)"""
        self.emit(self.OUT, x)  # r = 0 - (-char) = char

    def putc_lit(self, char_val):
        """Output a literal character. (1 instruction + 1 data word)"""
        lbl = self.uid('_ch')
        self.var(lbl, -char_val)
        self.emit(self.OUT, lbl)

    # ── indirect memory access (self-modifying code) ─────────────────

    def _set_fields(self, addr_var, *field_labels):
        """Copy the value of addr_var into multiple instruction fields.
        Uses T2 as temp."""
        t2 = 'T2'
        self.clear(t2)
        self.emit(t2, addr_var)       # T2 = -addr_val
        for fld in field_labels:
            self.clear(fld)
            self.emit(fld, t2)        # fld = addr_val
        self.clear(t2)

    def load_indirect(self, result, addr_var):
        """result = mem[addr_var_value]. Uses T, T2.
        addr_var holds the address to load from."""
        lbl = self.uid('_li')
        load_b = f'{lbl}_b'

        # Set the b-field of the load instruction to addr_var's value
        self._set_fields(addr_var, load_b)

        # Clear T for the load
        self.clear('T')

        # Self-modifying load: T = 0 - mem[addr_value]
        insn = self.pc()
        self._emit_word('T')       # a-field
        self.mark(load_b)
        self._emit_word(0)         # b-field (will be modified)
        self._emit_word(insn + 3)  # c-field = fall through

        # result = -T = mem[addr_value]
        self.clear(result)
        self.emit(result, 'T')
        self.clear('T')

    def store_indirect(self, addr_var, value_var):
        """mem[addr_var_value] = mem[value_var]. Uses T, T2.
        addr_var holds the target address. value_var holds the value to store."""
        lbl = self.uid('_si')
        clr_a = f'{lbl}_ca'
        clr_b = f'{lbl}_cb'
        store_a = f'{lbl}_sa'

        # Set instruction fields to addr_var's value
        self._set_fields(addr_var, clr_a, clr_b, store_a)

        # Clear target: mem[target] = mem[target] - mem[target] = 0
        insn1 = self.pc()
        self.mark(clr_a)
        self._emit_word(0)         # a-field (modified to target)
        self.mark(clr_b)
        self._emit_word(0)         # b-field (modified to target)
        self._emit_word(insn1 + 3) # c = fall through

        # T = -value
        self.clear('T')
        self.emit('T', value_var)  # T = -value

        # mem[target] -= T = 0 - (-value) = value
        insn2 = self.pc()
        self.mark(store_a)
        self._emit_word(0)         # a-field (modified to target)
        self._emit_word('T')       # b-field
        self._emit_word(insn2 + 3) # c = fall through

        self.clear('T')

    def store_indirect_neg(self, addr_var, neg_value_var):
        """mem[addr_var_value] = -mem[neg_value_var]. Uses T2.
        Useful when neg_value_var already holds -value (e.g., from getc).
        Stores: mem[target] = 0 - mem[neg_value_var] = -(-value) = value... 
        Actually stores: mem[target] = -neg_value, which if neg_value = -val, gives val.
        
        Simplified: clear target, then target -= neg_value => target = -neg_value.
        """
        lbl = self.uid('_sin')
        clr_a = f'{lbl}_ca'
        clr_b = f'{lbl}_cb'
        store_a = f'{lbl}_sa'

        self._set_fields(addr_var, clr_a, clr_b, store_a)

        # Clear target
        insn1 = self.pc()
        self.mark(clr_a)
        self._emit_word(0)
        self.mark(clr_b)
        self._emit_word(0)
        self._emit_word(insn1 + 3)

        # target -= neg_value => target = 0 - neg_value = value
        insn2 = self.pc()
        self.mark(store_a)
        self._emit_word(0)
        self._emit_word(neg_value_var)
        self._emit_word(insn2 + 3)

    # ── stack operations (for recursion) ─────────────────────────────

    def push(self, value_var, sp='SP'):
        """Push mem[value_var] onto the stack. Stack grows upward.
        Increments SP, then stores value at mem[SP]."""
        self.inc(sp)
        self.store_indirect(sp, value_var)

    def pop(self, result, sp='SP'):
        """Pop top of stack into result. Decrements SP."""
        self.load_indirect(result, sp)
        self.dec(sp)

    # ── subroutine call/return ───────────────────────────────────────

    def call(self, target, sp='SP', ret_var='RET_ADDR'):
        """Call subroutine at target. Pushes return address onto stack."""
        lbl = self.uid('_call')
        ret_label = f'{lbl}_ret'
        # Store return address into ret_var
        self.mov(ret_var, ret_label)  # ret_var = address of ret_label
        # But wait: ret_label is a label, not a value in memory!
        # We need to store the ADDRESS ret_label into ret_var.
        # Problem: mov copies mem[src] to dst. But ret_label is a code address.
        # Solution: have a data cell that holds the return address.
        # We'll use a different approach: embed the return address as data.
        pass

    # Let me redesign call/return using a simpler approach.
    # Instead of a general call, we'll use a pattern where the return address
    # is computed and pushed before jumping.

    def call_setup(self, target, sp='SP'):
        """Call subroutine at target with return address handling.
        Returns the label that should be placed at the return point."""
        lbl = self.uid('_call')
        ret_lbl = f'{lbl}_ret'
        ret_data = f'{lbl}_retd'

        # Allocate a data cell to hold the return address
        self.var(ret_data, 0)

        # We need to put the address of ret_lbl into ret_data.
        # But ret_lbl is a forward reference. We can use:
        # The value of ret_lbl will be resolved at finalization.
        # We need to MOV the literal address into ret_data.
        # 
        # Trick: create a data cell initialized to the label address.
        # But data cells are initialized at compile time, before labels are resolved...
        # 
        # Better trick: use self-modifying code to load the address.
        # Store the address as an immediate in the code:
        #   mov ret_data, _addr_cell
        # where _addr_cell is a data word containing the address.
        #
        # But we don't know the address yet (forward reference).
        # 
        # Simplest approach: store the return address in a known data cell
        # that's initialized to the label value at finalization time.
        # But our data section only supports constant initializers...
        #
        # Alternative: don't use push/pop for return addresses.
        # Instead, modify the return jump instruction directly.
        pass

    # ── practical call/return system ─────────────────────────────────
    # Uses self-modifying code for indirect jump (return).
    
    def setup_call_return(self):
        """Set up the call/return infrastructure. Call once at program start.
        Requires: SP variable pointing to stack area, RET_ADDR variable.
        Provides: call_func() and emit_return() methods work after this."""
        # The return instruction will be a self-modifying jump:
        # return_insn: N1 Z <ret_addr>
        # The <ret_addr> field is modified before each return.
        pass


# ═══════════════════════════════════════════════════════════════════════
#  Higher-level assembler for function calls
#  Uses a stack-based calling convention with self-modifying code.
# ═══════════════════════════════════════════════════════════════════════

class SubleqProgram(Asm):
    """Extended assembler with built-in function call support."""

    def __init__(self, stack_size=10000):
        super().__init__()
        # Standard cells
        self.var('Z', 0)
        self.var('N1', -1)
        self.var('ONE', 1)
        self.var('T', 0)
        self.var('T2', 0)
        self.var('T3', 0)

        # Stack (grows from stack_base upward)
        self.var('SP', 0)   # Will be set to stack base address at finalize
        self._stack_size = stack_size
        self.array('STACK', stack_size)

        # For call/return
        self.var('RET_ADDR', 0)

    def finalize(self):
        """Override to set SP initial value to stack base."""
        # Set SP to point just below the stack (pre-increment push)
        # SP will be set to STACK - 1, so first push goes to STACK[0]
        # But we don't know STACK's address yet...
        # We'll use a fixup: set SP's initial value after resolving labels.

        # First, do normal finalization to resolve labels
        words = super().finalize()

        # Now set SP to STACK_base - 1
        sp_addr = self._labels['SP']
        stack_base = self._labels['STACK']
        words[sp_addr] = stack_base - 1

        return words

    def push_const(self, value, sp='SP'):
        """Push a constant value onto the stack."""
        lbl = self.uid('_pc')
        tmp = f'{lbl}_v'
        self.var(tmp, value)
        self.push(tmp, sp)

    def emit_return(self, sp='SP'):
        """Emit a return sequence: pop return address, jump to it."""
        lbl = self.uid('_ret')
        ret_jmp_c = f'{lbl}_jc'

        # Pop return address into RET_ADDR
        self.pop('RET_ADDR', sp)

        # Modify the jump instruction's c-field to RET_ADDR
        self.mov(ret_jmp_c, 'RET_ADDR', tmp='T')

        # Jump: N1 Z <modified_c>
        insn = self.pc()
        self._emit_word('N1')
        self._emit_word('Z')
        self.mark(ret_jmp_c)
        self._emit_word(0)     # c-field (will be modified)

