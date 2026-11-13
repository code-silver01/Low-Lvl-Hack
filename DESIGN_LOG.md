# Design Log: The "Compile Yourself" Challenge

This document provides a concise, one-page engineering record of our architecture, the problems we tackled, **what we tried, what failed, and how we solved it**, along with our verification results.

---

## 1. What We Tried, What Failed, and How We Solved It

### Failure 1: The Infinite Loop in C2 Bootstrap (Forward Reference Hazard)
- **What We Tried**:
  We wrote `tier3.v1` as a single-pass compiler. Functions were declared in intuitive logical order: `next_tok()` first, which called identifier classifier `classify_ident()`.
- **What Failed**:
  When $C_1$ compiled `tier3.v1` into $C_2$, running $C_2$ on `tier3.v1` entered an infinite loop at step $10^8$ ($pc = 295440$).
- **Root Cause**:
  In a single-pass compiler with no forward function prototypes, `lookup_fn("classify_ident")` failed to find the function because it was defined *after* `next_tok`. The compiler fell back to the previous entry in `find_fn_entry`, which happened to be `next_tok` itself! Thus, every attempt to classify a keyword called `next_tok` recursively in an endless loop.
- **How We Solved It**:
  1. Topologically reordered the entire compiler so all helper functions (`classify_ident`, `emit_signed_lt`, `compile_call`) precede their callers.
  2. For the single unavoidable mutual recursion (`compile_primary` $\leftrightarrow$ `compile_expr`), we introduced a startup jump trampoline (`tramp_compile_expr`). At initialization, `compile_expr` is pre-registered in the symbol table pointing to the trampoline. When `func compile_expr` is parsed, the trampoline jump target is patched directly to `pc`.

### Failure 2: Array Base Pointer Overwriting Scalar Globals
- **What We Tried**:
  We allocated array pointer cells dynamically into the data segment (`data_p`) as they appeared in source declarations alongside `var`.
- **What Failed**:
  Global scalar variables declared after arrays (`startup_pc`, `tramp_pc`, `p_compile_expr_jump`) were corrupted during execution, leading to invalid jumps into unmapped memory.
- **Root Cause**:
  In `v1`, an array `array a[10]` allocates 10 elements, but the variable `a` itself is stored in a pointer cell. Interleaving scalar `var` and `array` declarations created an off-by-one mismatch between data segment indices and array base references.
- **How We Solved It**:
  Hoisted all 22 array declarations (`src`, `code`, `p10`, `fn_s`, `glob_s`, etc.) to the absolute top of `tier3.v1` before any scalar `var`. This creates a deterministic, non-overlapping memory layout.

### Failure 3: Signed Comparison Arithmetic Overflow
- **What We Tried**:
  Evaluating signed comparisons ($x < y$) naively via SUBLEQ subtraction: compute $d = x - y$ and test if $d \le 0$.
- **What Failed**:
  Whenever $x$ and $y$ had opposite signs and large magnitudes (e.g. $x = 2 \times 10^9$ and $y = -2 \times 10^9$), $x - y$ overflowed 32-bit signed integer limits modulo $2^{32}$, completely inverting the comparison result.
- **How We Solved It**:
  Implemented overflow-safe signed comparison logic:
  - If $\text{sign}(x) \ne \text{sign}(y)$: if $x < 0$ and $y \ge 0$, then $x < y$ is immediately true; if $x \ge 0$ and $y < 0$, false.
  - If $\text{sign}(x) == \text{sign}(y)$: subtraction $x - y$ is guaranteed never to overflow 32-bit signed limits. Tested and verified on all extreme edge cases.

### Failure 4: Recursive Towers of Hanoi Stack Overhead in Tier 1
- **What We Tried**:
  Implementing the classic recursive Towers of Hanoi algorithm in bare SUBLEQ assembly with simulated call frames.
- **What Failed**:
  For $N = 20$ disks, managing call frames, parameter saving, and return addresses on bare metal SUBLEQ consumed millions of instructions and exceeded memory/step budgets.
- **How We Solved It**:
  Replaced recursion with an iterative, non-recursive algorithm based on the binary counting invariant: move disk $d$ at step $k$, where $2^d$ is the highest power of 2 dividing $k$. Solves all $2^N - 1$ moves in $O(1)$ memory with zero call stack overhead.

---

## 2. Core Architecture & Mechanisms

### How Pointer Access Works in SUBLEQ
Because SUBLEQ has no indirect addressing instruction (`[reg]` or `*ptr`), pointer dereferences are implemented using **self-modifying code**:
1. **Load Indirect (`*ptr -> dst`)**:
   We write an instruction template `subleq 0, dst, pc+3`. Before execution, we copy `ptr` into the instruction's first operand field (`a` at `addr + 0`). When executed, the CPU reads directly from `mem[*ptr]`.
2. **Store Indirect (`val -> *ptr`)**:
   We copy `ptr` into the instruction's second operand field (`b` at `addr + 1`). When executed, SUBLEQ writes the computed result directly to `mem[*ptr]`.

### How Function Calls Work
We emulate a standard activation frame on a simulated stack growing upwards:
```
FP + 0: OLD_FP (saved caller frame pointer)
FP + 1: RET_ADDR (return address)
FP + 2 .. FP + 1 + P: Arguments 0 .. P - 1
FP + 2 + P .. : Local variables 0 .. L - 1
```
1. **Call Sequence**: Caller evaluates arguments, pushes them above `SP`, pushes `OLD_FP` and return address, updates `FP = new_frame`, increments `SP`, and jumps to function entry.
2. **Return Sequence**: Function places return value in Accumulator (`ACC`, cell 9), restores caller's `FP` from `FP[0]`, restores `SP`, and jumps to a dedicated dynamic return trampoline which patches its jump target with `RET_ADDR`.

---

## 3. Bootstrap & Verification Summary

| Tier | Component | Status | Step Count | Time |
| :--- | :--- | :--- | :--- | :--- |
| **Tier 1** | `echo.txt` | **VERIFIED** | $< 100,000$ | $< 0.01$s |
| **Tier 1** | `reverse.txt` | **VERIFIED** | $< 2,000,000$ | $< 0.05$s |
| **Tier 1** | `bigmul.txt` | **VERIFIED** | $< 10,000,000$ | $< 0.2$s |
| **Tier 1** | `hanoi.txt` | **VERIFIED** | $< 50,000,000$ | $< 0.5$s |
| **Tier 2** | `compiler_v1.py` & `assembler.py` | **VERIFIED** | $< 10^8$ | $< 0.5$s |
| **Tier 3** | $C_1 \times \text{tier3.v1} \to C_2$ | **VERIFIED** | 4,114,576,872 | 14.47s |
| **Tier 3** | $C_2 \times \text{tier3.v1} \to C_3$ | **VERIFIED** | 4,057,662,407 | 14.37s |
| **Tier 3** | Fixed Point $C_2 \equiv C_3$ | **IDENTICAL** | 343,401 words | Bit-for-bit exact |
