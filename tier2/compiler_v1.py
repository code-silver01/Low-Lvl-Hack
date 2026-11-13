#!/usr/bin/env python3
"""
Tier 2: v1 to SUBLEQ Compiler
Stack-safe code generation.
"""

import sys
import os

scratch = r'C:\Users\adity\.gemini\antigravity\brain\75d3300f-a93b-4b74-8ebf-a6f9967961bd\scratch'
if scratch not in sys.path:
    sys.path.append(scratch)
from assembler import Assembler

# ----------------- Lexer -----------------

class Token:
    def __init__(self, type, val, line):
        self.type = type
        self.val = val
        self.line = line

    def __repr__(self):
        return f"Token({self.type}, {repr(self.val)}, line {self.line})"

KEYWORDS = {'var', 'array', 'func', 'if', 'else', 'while', 'return'}

def tokenize(src):
    tokens = []
    i = 0
    n = len(src)
    line = 1

    while i < n:
        c = src[i]

        if c == '\n':
            line += 1
            i += 1
            continue

        if c in ' \t\r':
            i += 1
            continue

        # Comments
        if c == '/' and i + 1 < n and src[i+1] == '/':
            i += 2
            while i < n and src[i] != '\n':
                i += 1
            continue

        # Two-character operators
        if i + 1 < n:
            two = src[i:i+2]
            if two in ('==', '!=', '<=', '>='):
                tokens.append(Token(two, two, line))
                i += 2
                continue

        # Single-character tokens
        if c in '(){}[];,+-*=<':
            tokens.append(Token(c, c, line))
            i += 1
            continue
        if c == '>':
            tokens.append(Token(c, c, line))
            i += 1
            continue

        # Numbers
        if c.isdigit():
            start = i
            while i < n and src[i].isdigit():
                i += 1
            num = int(src[start:i])
            tokens.append(Token('INT', num, line))
            continue

        # Identifiers and keywords
        if c.isalpha() or c == '_':
            start = i
            while i < n and (src[i].isalnum() or src[i] == '_'):
                i += 1
            ident = src[start:i]
            if ident in KEYWORDS:
                tokens.append(Token(ident, ident, line))
            else:
                tokens.append(Token('ID', ident, line))
            continue

        raise SyntaxError(f"Unexpected character {repr(c)} at line {line}")

    tokens.append(Token('EOF', '', line))
    return tokens

# ----------------- AST Nodes -----------------

class ASTNode: pass

class Program(ASTNode):
    def __init__(self, globals, funcs):
        self.globals = globals # list of (kind, name, size)
        self.funcs = funcs     # list of FuncDef

class FuncDef(ASTNode):
    def __init__(self, name, params, locals, body):
        self.name = name
        self.params = params
        self.locals = locals
        self.body = body

class Block(ASTNode):
    def __init__(self, stmts):
        self.stmts = stmts

class VarDecl(ASTNode):
    def __init__(self, name):
        self.name = name

class Assign(ASTNode):
    def __init__(self, name, index_expr, val_expr):
        self.name = name
        self.index_expr = index_expr # None if simple var
        self.val_expr = val_expr

class CallStmt(ASTNode):
    def __init__(self, call_expr):
        self.call_expr = call_expr

class IfStmt(ASTNode):
    def __init__(self, cond, then_block, else_block):
        self.cond = cond
        self.then_block = then_block
        self.else_block = else_block

class WhileStmt(ASTNode):
    def __init__(self, cond, body):
        self.cond = cond
        self.body = body

class ReturnStmt(ASTNode):
    def __init__(self, expr):
        self.expr = expr

class BinOp(ASTNode):
    def __init__(self, op, left, right):
        self.op = op
        self.left = left
        self.right = right

class UnaryOp(ASTNode):
    def __init__(self, op, expr):
        self.op = op
        self.expr = expr

class CallExpr(ASTNode):
    def __init__(self, name, args):
        self.name = name
        self.args = args

class VarRef(ASTNode):
    def __init__(self, name):
        self.name = name

class ArrayRef(ASTNode):
    def __init__(self, name, index_expr):
        self.name = name
        self.index_expr = index_expr

class IntLit(ASTNode):
    def __init__(self, val):
        self.val = val

# ----------------- Parser -----------------

class Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0

    def cur(self):
        return self.tokens[self.pos]

    def eat(self, type=None):
        tok = self.cur()
        if type and tok.type != type:
            raise SyntaxError(f"Expected {type}, got {tok.type} ({tok.val}) at line {tok.line}")
        self.pos += 1
        return tok

    def match(self, *types):
        return self.cur().type in types

    def parse(self):
        globals_list = []
        funcs = []

        while not self.match('EOF'):
            if self.match('var'):
                self.eat('var')
                name = self.eat('ID').val
                self.eat(';')
                globals_list.append(('var', name, 1))
            elif self.match('array'):
                self.eat('array')
                name = self.eat('ID').val
                self.eat('[')
                sz = self.eat('INT').val
                self.eat(']')
                self.eat(';')
                globals_list.append(('array', name, sz))
            elif self.match('func'):
                self.eat('func')
                name = self.eat('ID').val
                self.eat('(')
                params = []
                if not self.match(')'):
                    params.append(self.eat('ID').val)
                    while self.match(','):
                        self.eat(',')
                        params.append(self.eat('ID').val)
                self.eat(')')

                self.eat('{')
                locals_list = []
                self.cur_func_locals = locals_list
                while self.match('var'):
                    self.eat('var')
                    vname = self.eat('ID').val
                    self.eat(';')
                    locals_list.append(vname)

                stmts = []
                while not self.match('}'):
                    stmts.append(self.parse_stmt())
                self.eat('}')
                funcs.append(FuncDef(name, params, locals_list, Block(stmts)))
            else:
                raise SyntaxError(f"Unexpected token {self.cur()} at top level")

        return Program(globals_list, funcs)

    def parse_stmt(self):
        if self.match('var'):
            self.eat('var')
            vname = self.eat('ID').val
            self.eat(';')
            if self.cur_func_locals is not None and vname not in self.cur_func_locals:
                self.cur_func_locals.append(vname)
            return VarDecl(vname)

        if self.match('if'):
            self.eat('if')
            self.eat('(')
            cond = self.parse_expr()
            self.eat(')')
            self.eat('{')
            then_stmts = []
            while not self.match('}'):
                then_stmts.append(self.parse_stmt())
            self.eat('}')
            else_block = None
            if self.match('else'):
                self.eat('else')
                self.eat('{')
                else_stmts = []
                while not self.match('}'):
                    else_stmts.append(self.parse_stmt())
                self.eat('}')
                else_block = Block(else_stmts)
            return IfStmt(cond, Block(then_stmts), else_block)

        if self.match('while'):
            self.eat('while')
            self.eat('(')
            cond = self.parse_expr()
            self.eat(')')
            self.eat('{')
            body_stmts = []
            while not self.match('}'):
                body_stmts.append(self.parse_stmt())
            self.eat('}')
            return WhileStmt(cond, Block(body_stmts))

        if self.match('return'):
            self.eat('return')
            expr = self.parse_expr()
            self.eat(';')
            return ReturnStmt(expr)

        if self.match('ID'):
            name = self.eat('ID').val
            if self.match('('):
                self.eat('(')
                args = []
                if not self.match(')'):
                    args.append(self.parse_expr())
                    while self.match(','):
                        self.eat(',')
                        args.append(self.parse_expr())
                self.eat(')')
                self.eat(';')
                return CallStmt(CallExpr(name, args))
            elif self.match('['):
                self.eat('[')
                idx = self.parse_expr()
                self.eat(']')
                self.eat('=')
                val = self.parse_expr()
                self.eat(';')
                return Assign(name, idx, val)
            elif self.match('='):
                self.eat('=')
                val = self.parse_expr()
                self.eat(';')
                return Assign(name, None, val)
            else:
                raise SyntaxError(f"Unexpected token after ID {name}: {self.cur()}")

        if self.match('getc', 'putc'):
            fn = self.eat().val
            self.eat('(')
            args = []
            if not self.match(')'):
                args.append(self.parse_expr())
                while self.match(','):
                    self.eat(',')
                    args.append(self.parse_expr())
            self.eat(')')
            self.eat(';')
            return CallStmt(CallExpr(fn, args))

        raise SyntaxError(f"Unexpected statement starting with {self.cur()}")

    def parse_expr(self):
        return self.parse_comparison()

    def parse_comparison(self):
        left = self.parse_additive()
        while self.match('<', '<=', '>', '>=', '==', '!='):
            op = self.eat().type
            right = self.parse_additive()
            left = BinOp(op, left, right)
        return left

    def parse_additive(self):
        left = self.parse_multiplicative()
        while self.match('+', '-'):
            op = self.eat().type
            right = self.parse_multiplicative()
            left = BinOp(op, left, right)
        return left

    def parse_multiplicative(self):
        left = self.parse_unary()
        while self.match('*'):
            op = self.eat().type
            right = self.parse_unary()
            left = BinOp(op, left, right)
        return left

    def parse_unary(self):
        if self.match('-'):
            self.eat('-')
            expr = self.parse_unary()
            return UnaryOp('-', expr)
        return self.parse_primary()

    def parse_primary(self):
        if self.match('INT'):
            return IntLit(self.eat('INT').val)

        if self.match('('):
            self.eat('(')
            e = self.parse_expr()
            self.eat(')')
            return e

        if self.match('ID'):
            name = self.eat('ID').val
            if self.match('('):
                self.eat('(')
                args = []
                if not self.match(')'):
                    args.append(self.parse_expr())
                    while self.match(','):
                        self.eat(',')
                        args.append(self.parse_expr())
                self.eat(')')
                return CallExpr(name, args)
            elif self.match('['):
                self.eat('[')
                idx = self.parse_expr()
                self.eat(']')
                return ArrayRef(name, idx)
            else:
                return VarRef(name)

        if self.match('getc', 'putc'):
            fn = self.eat().val
            self.eat('(')
            args = []
            if not self.match(')'):
                args.append(self.parse_expr())
                while self.match(','):
                    self.eat(',')
                    args.append(self.parse_expr())
            self.eat(')')
            return CallExpr(fn, args)

        raise SyntaxError(f"Unexpected token in expression: {self.cur()}")

# ----------------- Code Generator -----------------

class CodeGen:
    def __init__(self, prog_ast):
        self.ast = prog_ast
        self.a = Assembler()

        self.globals = {} # name -> label_name
        self.global_arrays = {} # name -> (label_name, addr_label)

        self.cur_func = None
        self.params = {}
        self.locals = {}
        self.frame_size = 0

    def generate(self):
        # 1. Globals
        for kind, name, sz in self.ast.globals:
            if kind == 'var':
                lbl = f"GLOBAL_{name}"
                self.a.var(lbl, 0)
                self.globals[name] = lbl
            elif kind == 'array':
                lbl = f"ARRAY_{name}"
                addr_lbl = f"ARRAY_ADDR_{name}"
                self.a.array(lbl, sz)
                self.a.var(addr_lbl, (lbl, 0))
                self.global_arrays[name] = (lbl, addr_lbl)

        # Standard runtime registers
        self.a.var("STACK_START_ADDR", ("STACK_REGION", 0))
        self.a.array("STACK_REGION", 50000)

        self.a.var("FP", 0)
        self.a.var("SP", 0)
        self.a.var("ACC", 0)       # Accumulator for expression results
        self.a.var("OP_LEFT", 0)   # Left operand for binary ops
        self.a.var("RET_VAL", 0)
        self.a.var("RET_ADDR", 0)
        self.a.var("PTR", 0)
        self.a.var("DIFF", 0)

        # 32-bit multiplication
        self.a.var("MUL_X", 0)
        self.a.var("MUL_Y", 0)
        self.a.var("MUL_PROD", 0)

        # Signed comparisons
        self.a.var("CMP_X", 0)
        self.a.var("CMP_Y", 0)
        self.a.var("CMP_RES", 0)

        # Startup code
        self.a.mov("FP", "STACK_START_ADDR")
        self.a.mov("SP", "STACK_START_ADDR")

        # Call main(): frame = [OLD_FP=0, RET_ADDR=halt]
        self.a.mov("PTR", "SP")
        self.a.store_indirect("PTR", "ZERO")
        self.a.add_const("PTR", 1)
        self.a.var("ADDR_HALT", "halt")
        self.a.store_indirect("PTR", "ADDR_HALT")
        main_def = None
        for f in self.ast.funcs:
            if f.name == 'main':
                main_def = f
                break
        main_frame_size = 2 + (len(main_def.locals) if main_def else 0)
        self.a.mov("FP", "SP")
        self.a.add_const("SP", main_frame_size)
        self.a.jmp("func_main")

        self.a.set_label("halt")
        self.a.jmp(-1)

        # Return trampoline
        self.a.set_label("ret_trampoline")
        self.a.mov(("jump_ret_insn", 2), "RET_ADDR")
        self.a.set_label("jump_ret_insn")
        self.a.subleq("NEG1", "ZERO", 0)

        # Compile all functions
        for f in self.ast.funcs:
            self.compile_func(f)

        return self.a

    def compile_func(self, f):
        self.cur_func = f
        self.params = {}
        self.locals = {}

        offset = 2
        for p in f.params:
            self.params[p] = offset
            offset += 1
        for loc in f.locals:
            self.locals[loc] = offset
            offset += 1

        self.frame_size = offset
        self.a.set_label(f"func_{f.name}")

        for st in f.body.stmts:
            self.compile_stmt(st)

        # Default return 0
        self.a.mov_const("RET_VAL", 0)
        self.emit_return_sequence()

    def emit_return_sequence(self):
        self.a.mov("PTR", "FP")
        self.a.add_const("PTR", 1)
        self.a.load_indirect("RET_ADDR", "PTR")
        self.a.load_indirect("FP", "FP")
        self.a.sub_const("SP", self.frame_size)
        self.a.jmp("ret_trampoline")

    def push_acc(self):
        """Push ACC onto stack: mem[SP] = ACC; SP += 1"""
        self.a.mov("PTR", "SP")
        self.a.store_indirect("PTR", "ACC")
        self.a.add_const("SP", 1)

    def pop_to(self, dst):
        """Pop from stack into dst: SP -= 1; dst = mem[SP]"""
        self.a.sub_const("SP", 1)
        self.a.mov("PTR", "SP")
        self.a.load_indirect(dst, "PTR")

    def compile_stmt(self, st):
        if isinstance(st, VarDecl):
            return
        if isinstance(st, ReturnStmt):
            self.compile_expr(st.expr) # result in ACC
            self.a.mov("RET_VAL", "ACC")
            self.emit_return_sequence()
        elif isinstance(st, Assign):
            if st.index_expr is None:
                # x = e;
                self.compile_expr(st.val_expr) # ACC = val
                if st.name in self.locals:
                    off = self.locals[st.name]
                    self.a.mov("PTR", "FP")
                    self.a.add_const("PTR", off)
                    self.a.store_indirect("PTR", "ACC")
                elif st.name in self.params:
                    off = self.params[st.name]
                    self.a.mov("PTR", "FP")
                    self.a.add_const("PTR", off)
                    self.a.store_indirect("PTR", "ACC")
                elif st.name in self.globals:
                    self.a.mov(self.globals[st.name], "ACC")
                else:
                    raise NameError(f"Undefined variable {st.name}")
            else:
                # a[index] = val;
                # Evaluate index first, push it
                self.compile_expr(st.index_expr) # ACC = index
                self.push_acc()
                # Evaluate val
                self.compile_expr(st.val_expr) # ACC = val
                # Pop index into OP_LEFT
                self.pop_to("OP_LEFT")
                if st.name not in self.global_arrays:
                    raise NameError(f"Undefined array {st.name}")
                _, addr_lbl = self.global_arrays[st.name]
                # PTR = array_addr + index
                self.a.mov("PTR", addr_lbl)
                self.a.add("PTR", "OP_LEFT")
                self.a.store_indirect("PTR", "ACC")
        elif isinstance(st, CallStmt):
            self.compile_call(st.call_expr)
        elif isinstance(st, IfStmt):
            self.compile_expr(st.cond) # ACC = cond
            else_lbl = self.a.new_label("else")
            end_lbl = self.a.new_label("endif")

            self.a.jz("ACC", else_lbl if st.else_block else end_lbl)

            for s in st.then_block.stmts:
                self.compile_stmt(s)

            if st.else_block:
                self.a.jmp(end_lbl)
                self.a.set_label(else_lbl)
                for s in st.else_block.stmts:
                    self.compile_stmt(s)

            self.a.set_label(end_lbl)
        elif isinstance(st, WhileStmt):
            loop_lbl = self.a.new_label("while_start")
            end_lbl = self.a.new_label("while_end")

            self.a.set_label(loop_lbl)
            self.compile_expr(st.cond) # ACC = cond
            self.a.jz("ACC", end_lbl)

            for s in st.body.stmts:
                self.compile_stmt(s)

            self.a.jmp(loop_lbl)
            self.a.set_label(end_lbl)

    def compile_expr(self, e):
        """Evaluates e and leaves the result in ACC."""
        if isinstance(e, IntLit):
            self.a.mov_const("ACC", e.val)
            return

        if isinstance(e, VarRef):
            if e.name in self.locals:
                off = self.locals[e.name]
                self.a.mov("PTR", "FP")
                self.a.add_const("PTR", off)
                self.a.load_indirect("ACC", "PTR")
            elif e.name in self.params:
                off = self.params[e.name]
                self.a.mov("PTR", "FP")
                self.a.add_const("PTR", off)
                self.a.load_indirect("ACC", "PTR")
            elif e.name in self.globals:
                self.a.mov("ACC", self.globals[e.name])
            else:
                raise NameError(f"Undefined variable {e.name}")
            return

        if isinstance(e, ArrayRef):
            self.compile_expr(e.index_expr) # ACC = index
            if e.name not in self.global_arrays:
                raise NameError(f"Undefined array {e.name}")
            _, addr_lbl = self.global_arrays[e.name]
            self.a.mov("PTR", addr_lbl)
            self.a.add("PTR", "ACC")
            self.a.load_indirect("ACC", "PTR")
            return

        if isinstance(e, UnaryOp) and e.op == '-':
            self.compile_expr(e.expr) # ACC = val
            self.a.clr("DIFF")
            self.a.sub("DIFF", "ACC")
            self.a.mov("ACC", "DIFF")
            return

        if isinstance(e, CallExpr):
            self.compile_call(e)
            return

        if isinstance(e, BinOp):
            # Left-to-right evaluation
            self.compile_expr(e.left) # ACC = left
            self.push_acc()           # stack: [... left]
            self.compile_expr(e.right)# ACC = right
            self.pop_to("OP_LEFT")    # OP_LEFT = left, ACC = right

            if e.op == '+':
                self.a.add("ACC", "OP_LEFT") # ACC = right + left
            elif e.op == '-':
                # OP_LEFT - ACC
                self.a.mov("DIFF", "OP_LEFT")
                self.a.sub("DIFF", "ACC")
                self.a.mov("ACC", "DIFF")
            elif e.op == '*':
                self.a.mov("MUL_X", "OP_LEFT")
                self.a.mov("MUL_Y", "ACC")
                self.a.mov_const("MUL_PROD", 0)
                for _ in range(32):
                    self.a.add("MUL_PROD", "MUL_PROD")
                    skip = self.a.new_label("skip_mul")
                    self.a.jge("MUL_Y", skip)
                    self.a.add("MUL_PROD", "MUL_X")
                    self.a.set_label(skip)
                    self.a.add("MUL_Y", "MUL_Y")
                self.a.mov("ACC", "MUL_PROD")
            elif e.op in ('<', '<=', '>', '>=', '==', '!='):
                self.compile_comparison(e.op, "OP_LEFT", "ACC")
            return

        raise NotImplementedError(f"Unsupported expr: {type(e)}")

    def compile_comparison(self, op, left_var, right_var):
        """Leaves 1 or 0 in ACC."""
        self.a.mov("CMP_X", left_var)
        self.a.mov("CMP_Y", right_var)

        if op in ('==', '!='):
            self.a.mov("DIFF", "CMP_X")
            self.a.sub("DIFF", "CMP_Y")
            lbl_true = self.a.new_label("cmp_true")
            lbl_done = self.a.new_label("cmp_done")
            self.a.mov_const("ACC", 0)
            if op == '==':
                self.a.jz("DIFF", lbl_true)
            else:
                self.a.jnz("DIFF", lbl_true)
            self.a.jmp(lbl_done)
            self.a.set_label(lbl_true)
            self.a.mov_const("ACC", 1)
            self.a.set_label(lbl_done)
            return

        if op == '<':
            x_var, y_var, invert = "CMP_X", "CMP_Y", False
        elif op == '<=':
            x_var, y_var, invert = "CMP_Y", "CMP_X", True
        elif op == '>':
            x_var, y_var, invert = "CMP_Y", "CMP_X", False
        elif op == '>=':
            x_var, y_var, invert = "CMP_X", "CMP_Y", True

        lbl_true = self.a.new_label("lt_true")
        lbl_false = self.a.new_label("lt_false")
        lbl_done = self.a.new_label("lt_done")

        lbl_x_neg = self.a.new_label("x_neg")
        lbl_x_pos = self.a.new_label("x_pos")

        self.a.jn(x_var, lbl_x_neg)
        self.a.jmp(lbl_x_pos)

        # x < 0
        self.a.set_label(lbl_x_neg)
        self.a.jge(y_var, lbl_true)
        self.a.mov("DIFF", x_var)
        self.a.sub("DIFF", y_var)
        self.a.jn("DIFF", lbl_true)
        self.a.jmp(lbl_false)

        # x >= 0
        self.a.set_label(lbl_x_pos)
        self.a.jn(y_var, lbl_false)
        self.a.mov("DIFF", x_var)
        self.a.sub("DIFF", y_var)
        self.a.jn("DIFF", lbl_true)
        self.a.jmp(lbl_false)

        self.a.set_label(lbl_true)
        self.a.mov_const("ACC", 0 if invert else 1)
        self.a.jmp(lbl_done)

        self.a.set_label(lbl_false)
        self.a.mov_const("ACC", 1 if invert else 0)

        self.a.set_label(lbl_done)

    def compile_call(self, call_e):
        fn_name = call_e.name

        if fn_name == 'getc':
            self.a.getc("ACC")
            return

        if fn_name == 'putc':
            self.compile_expr(call_e.args[0])
            self.a.putc("ACC")
            self.a.mov_const("ACC", 0)
            return

        # User function call
        # Evaluate arguments and push each onto stack
        for arg in call_e.args:
            self.compile_expr(arg) # ACC = arg
            self.push_acc()

        num_args = len(call_e.args)

        # Callee frame layout at CALLEE_FP:
        # CALLEE_FP = SP - num_args
        # Callee parameters are already placed at CALLEE_FP + 2 .. CALLEE_FP + 2 + num_args - 1 !
        # We need space for OLD_FP (offset 0) and RET_ADDR (offset 1).
        # So CALLEE_FP = SP - num_args!
        # But wait! The arguments are at CALLEE_FP .. CALLEE_FP + num_args - 1!
        # If parameters start at offset 2, we should allocate space for OLD_FP and RET_ADDR BEFORE arguments!
        # Let's verify:
        # If caller pushes OLD_FP, then RET_ADDR, then arguments:
        # 1. CALLEE_FP = SP
        # 2. Push OLD_FP (FP)
        # 3. Push RET_ADDR (dummy for now, filled later)
        # 4. For each arg: evaluate arg, push arg!
        # LOOK AT HOW ELEGANT THAT IS!
        # The arguments naturally land at FP + 2, FP + 3, FP + 4... !
        pass

    def compile_call(self, call_e):
        fn_name = call_e.name

        if fn_name == 'getc':
            self.a.getc("ACC")
            return

        if fn_name == 'putc':
            self.compile_expr(call_e.args[0])
            self.a.putc("ACC")
            self.a.mov_const("ACC", 0)
            return

        # User-defined function call
        callee_def = None
        for f in self.ast.funcs:
            if f.name == fn_name:
                callee_def = f
                break
        if callee_def is None:
            raise NameError(f"Call to undefined function {fn_name}")

        # Callee frame base will be at CALLEE_FP = current SP!
        # But wait! If we evaluate arguments AFTER pushing OLD_FP, the arguments might make subcalls!
        # If an argument makes a subcall, it will use stack ABOVE current SP!
        # So evaluating arguments BEFORE or storing them in a temporary frame is standard.
        # Let's do:
        # 1. Evaluate arguments left-to-right, push each to stack:
        #    Stack has: [arg0, arg1, ...]
        for arg in call_e.args:
            self.compile_expr(arg) # ACC = arg
            self.push_acc()

        num_args = len(call_e.args)
        num_locals = len(callee_def.locals)
        total_frame = 2 + len(callee_def.params) + num_locals

        # Now args are at SP - num_args .. SP - 1.
        # We can construct the frame at CALLEE_FP = SP - num_args:
        # Move args from (CALLEE_FP .. CALLEE_FP + num_args - 1) to (CALLEE_FP + 2 .. CALLEE_FP + 2 + num_args - 1)!
        # In reverse order (from last arg down to first):
        # arg[i] moves from CALLEE_FP + i to CALLEE_FP + 2 + i!
        self.a.var("CALLEE_FP", 0)
        self.a.mov("CALLEE_FP", "SP")
        self.a.sub_const("CALLEE_FP", num_args)

        for i in range(num_args - 1, -1, -1):
            # load from CALLEE_FP + i
            self.a.mov("PTR", "CALLEE_FP")
            self.a.add_const("PTR", i)
            self.a.load_indirect("DIFF", "PTR")
            # store to CALLEE_FP + 2 + i
            self.a.mov("PTR", "CALLEE_FP")
            self.a.add_const("PTR", 2 + i)
            self.a.store_indirect("PTR", "DIFF")

        # Now store OLD_FP at CALLEE_FP + 0
        self.a.mov("PTR", "CALLEE_FP")
        self.a.store_indirect("PTR", "FP")

        # Store RET_ADDR at CALLEE_FP + 1
        ret_lbl = self.a.new_label(f"ret_{fn_name}")
        ret_addr_var = f"ADDR_RET_{ret_lbl}"
        self.a.var(ret_addr_var, ret_lbl)
        self.a.add_const("PTR", 1)
        self.a.store_indirect("PTR", ret_addr_var)

        # Set new FP and SP
        self.a.mov("FP", "CALLEE_FP")
        self.a.mov("SP", "CALLEE_FP")
        self.a.add_const("SP", total_frame)
        self.a.jmp(f"func_{fn_name}")

        self.a.set_label(ret_lbl)
        self.a.mov("ACC", "RET_VAL")

def compile_v1_source(source_str):
    tokens = tokenize(source_str)
    parser = Parser(tokens)
    prog_ast = parser.parse()
    codegen = CodeGen(prog_ast)
    asm = codegen.generate()
    return asm.to_string()
