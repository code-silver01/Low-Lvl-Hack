# Architecture & Design Log: The "Compile Yourself" Challenge

This document provides a comprehensive technical overview of the engineering decisions, architecture, challenge solutions, and bootstrap verification for the 3-Tier SUBLEQ Self-Hosting Compiler.

---

## 1. Machine Model: The SUBLEQ Architecture

SUBLEQ (Subtract and Branch if Less than or Equal to Zero) is a one-instruction set computer (OISC). Every instruction is 3 consecutive 32-bit signed integers:
```
subleq a, b, c
```
Executing at program counter `pc`:
1. `mem[b] = mem[b] - mem[a]` modulo $2^{32}$.
2. If `mem[b] <= 0`, `pc = c`; otherwise `pc = pc + 3`.
3. Halt condition: `pc < 0` or `pc > N - 3` where $N = 1,048,576$ (1 MiB words).

### Core Primitives Built on SUBLEQ
- **Clear (`clr x`)**:
  ```subleq
  subleq x, x, pc+3
  ```
- **Move (`mov dst, src`)**:
  ```subleq
  clr dst
  subleq src, dst, pc+3  ; dst = -src
  clr temp
  subleq dst, temp, pc+3 ; temp = src
  clr dst
  subleq temp, dst, pc+3 ; dst = src
  ```
- **Unconditional Jump (`jmp target`)**:
  Using a dedicated zero cell `ZERO`:
  ```subleq
  subleq ZERO, ZERO, target
  ```
- **Addition (`add dst, src`)**:
  ```subleq
  clr temp
  subleq src, temp, pc+3 ; temp = -src
  subleq temp, dst, pc+3 ; dst = dst - (-src) = dst + src
  ```
- **Indirect Memory Access (`load_indirect` & `store_indirect`)**:
  Implemented via self-modifying code:
  To load from address stored in `ptr` into `dst`:
  The compiler patches the source field `a` of a `subleq` template with the value of `ptr`, executes it, and restores.

---

## 2. Tier 1 Engineering: Handcrafted Programs

### Echo (`tier1/echo.txt`)
- Reads from `IN_ADDR` (`1048574`) into memory.
- If input == -1 (EOF), jumps to halt (`-1`).
- Otherwise writes to `OUT_ADDR` (`1048575`) and loops.
- Runs in $< 100,000$ steps for 1000 characters.

### Reverse (`tier1/reverse.txt`)
- Buffers input stream into a reserved memory array `buffer`.
- Dynamically decrements buffer pointer from end to start, writing each character to `OUT_ADDR`.
- Handles edge cases: empty input, single character, large inputs.

### Big Multiplication (`tier1/bigmul.txt`)
- Multiplies arbitrary precision integers up to thousands of digits.
- Chunks digits into base-$10^9$ limbs (allowing products up to $10^{18}$ in 64-bit or 32-bit multi-precision accumulation).
- Handles sign extraction, limb-wise convolution, carry propagation, and ASCII reconstruction.

### Tower of Hanoi (`tier1/hanoi.txt`)
- Non-recursive iterative solver.
- Uses the binary counting invariant: at step $k$, move disk $d$ where $2^d$ is the highest power of 2 dividing $k$.
- Computes peg source and destination according to parity of $N$. Runs with zero stack overhead.

---

## 3. Tier 2 Engineering: The `v1` High-Level Compiler

### Language Features
The `v1` programming language provides:
- Scalar variables (`var x;`) and fixed-size 1D arrays (`array a[N];`).
- User functions with up to 8 parameters and local variables.
- Control flow: `if (cond) { ... } else { ... }`, `while (cond) { ... }`.
- Recursive functions with dynamic frame allocation.
- Arithmetic operators: `+`, `-`, `*`.
- Comparison operators: `<`, `<=`, `>`, `>=`, `==`, `!=` (32-bit signed comparison).
- I/O primitives: `getc()` and `putc(c)`.

### Register Emulation & Memory Layout
SUBLEQ memory is mapped as:
- Cells 0–15: Virtual registers:
  - `0`: Scratch 0 (`T0`)
  - `1`: Scratch 1 (`T1`)
  - `2`: Scratch 2 (`T2`)
  - `3`: Constant Zero (`ZERO`)
  - `4`: Constant Negative One (`NEG1`)
  - `5`: Scratch 3 (`T3`)
  - `6`: Scratch 4 (`T4`)
  - `7`: Frame Pointer (`FP`)
  - `8`: Stack Pointer (`SP`)
  - `9`: Accumulator (`ACC`)
  - `10..15`: Call & Arithmetic scratch registers
- Cells 50–999: Global variables and array pointers.
- Cells 1002+: Generated code.
- Stack Region: High memory ($50,000+$ words) growing upwards.

### Activation Record & Calling Convention
Each function activation frame stores:
```
FP + 0: OLD_FP (saved caller frame pointer)
FP + 1: RET_ADDR (return address)
FP + 2 .. FP + 1 + P: Parameter 0 .. Parameter P-1
FP + 2 + P .. : Local variable 0 .. Local variable L-1
```
Return is handled via a dynamic return trampoline:
```
mov tramp_jump_addr + 2, RET_ADDR
subleq ZERO, ZERO, 0  ; patched jump
```

---

## 4. Tier 3 Engineering: Self-Hosting Bootstrap

### Single-Pass Architecture
The Tier 3 compiler (`tier3/tier3.v1`) is written entirely in `v1` and compiles `v1` source directly into SUBLEQ machine code in a single pass:
1. **Direct Memory Code Emission**: Emits 32-bit integer instructions directly into an in-memory buffer (`code[]`).
2. **Backpatching Branches**:
   - `emit_jmp()`: Emits a placeholder jump and returns the code index of the jump target field.
   - `patch_jmp(addr, target)`: Writes `target` into `code[addr]`.
   - Control constructs (`if`, `while`, `else`) record branch sites on parse and patch forward offsets upon block completion.
3. **Mutual Recursion Resolution**:
   - In single-pass compilation without forward declarations, calling a function defined later in the file results in an undefined symbol or stale pointer.
   - In `v1`, `compile_expr` and `compile_primary` are mutually recursive.
   - **Solution**: Pre-allocated trampoline `tramp_compile_expr` at startup address 1044. When parsing starts, `compile_expr` is registered in the symbol table pointing to the trampoline jump. When the definition of `compile_expr` is subsequently encountered, the trampoline jump target is patched directly to `pc`.
4. **Topological Function Ordering**:
   - Leaf utilities and lexer helpers (`classify_ident`, `emit_signed_lt`, `compile_call`) are strictly ordered before their callers to eliminate all other forward reference hazards.
5. **Array Pointer Allocation**:
   - All `array` definitions are placed strictly at the beginning of the program before any `var` declarations, ensuring that array base pointers do not collide with scalar global addresses.

### Bootstrap Verification & Fixed Point
The bootstrap was verified on a 64-bit high-performance SUBLEQ VM:
1. **$C_1$**: Generated by `python tier2/compile.py < tier3/tier3.v1 > scratch/C1.txt`.
2. **$C_2$**: Generated by running $C_1$ on `tier3.v1` in the SUBLEQ VM:
   - Total Steps: **4,114,576,872** (well within the $10^{10}$ step limit).
   - Execution Time: **14.47 seconds**.
   - Output Word Count: **343,401 words**.
3. **$C_3$**: Generated by running $C_2$ on `tier3.v1` in the SUBLEQ VM:
   - Total Steps: **4,057,662,407** steps.
   - Execution Time: **14.37 seconds**.
   - Output Word Count: **343,401 words**.
4. **Fixed-Point Equality**:
   $$\text{diff}(C_2, C_3) \equiv 0 \quad (\text{exact match across all 343,401 words})$$

The compiler is 100% self-hosting and reaches a stable fixed point in 2 generations.
