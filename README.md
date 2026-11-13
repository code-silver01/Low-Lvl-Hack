# Compile Yourself: 3-Tier SUBLEQ Self-Hosting Compiler

A complete, self-hosting compilation toolchain targeting the **SUBLEQ** (Subtract and Branch if Less than or Equal to Zero) One-Instruction Set Computer (OISC) architecture.

---

## Architecture Overview

### The SUBLEQ Machine
The virtual machine executes a single instruction repeated indefinitely:
```
subleq a, b, c
```
Semantics:
1. `mem[b] = mem[b] - mem[a]` (modulo $2^{32}$, signed 32-bit two's complement)
2. If `mem[b] <= 0`, jump to address `c` (`pc = c`); otherwise advance to `pc + 3`.
3. Halt condition: `pc < 0` or `pc > N - 3`.

- **Memory Size**: $N = 1,048,576$ words ($2^{20}$ 32-bit signed cells).
- **Memory-Mapped I/O**:
  - `IN` = Address $1,048,574$ (`N - 2`): Reading from this cell consumes one character from standard input (returning -1 on EOF).
  - `OUT` = Address $1,048,575$ (`N - 1`): Writing to this cell outputs one character to standard output.

---

## Project Structure

```
├── tier1/
│   ├── echo.txt          # Echoes stdin to stdout until EOF
│   ├── reverse.txt       # Reverses input string
│   ├── bigmul.txt        # High-precision arbitrary length multiplication
│   ├── hanoi.txt         # Iterative Towers of Hanoi solver
│   └── echo_gen.py       # Generator script for Tier 1 programs
├── tier2/
│   ├── compiler_v1.py    # v1 language compiler to SUBLEQ assembly
│   ├── assembler.py      # Two-pass SUBLEQ macro assembler
│   ├── compile.py        # Pipeline compiler (v1 -> machine code)
│   └── BUILD.md          # Tier 2 build and specification doc
├── tier3/
│   └── tier3.v1          # Self-hosting compiler written in v1
├── tools/
│   ├── vm.c              # High-performance C reference VM (~300M steps/sec)
│   ├── vm.exe            # Compiled optimized VM binary
│   └── asm.py            # SUBLEQ assembler utility
├── DESIGN_LOG.md         # Detailed architectural and engineering log
└── README.md             # Project overview
```

---

## Tier Summary

### Tier 1: Handcrafted SUBLEQ Machine Programs
All 4 required SUBLEQ programs running directly on bare metal SUBLEQ within the $10^8$ step limit:
1. `tier1/echo.txt`: Echoes characters from stdin to stdout until EOF (`-1`).
2. `tier1/reverse.txt`: Reads input into a memory buffer and outputs in reverse order.
3. `tier1/bigmul.txt`: Multiplies two arbitrarily large integers (formatted in base $10^9$ digit limbs) with full two's complement sign management and base-10 formatting.
4. `tier1/hanoi.txt`: Iteratively solves Towers of Hanoi for $N$ disks without recursion using binary transitions in $2^N - 1$ steps.

### Tier 2: The `v1` Language Compiler & Assembler
A complete compiler and macro assembler written in Python:
- **Language**: `v1` — procedural language supporting scalar `var`, fixed-size `array`, recursive functions `func` with up to 8 arguments and local variables, control flow (`if`/`else`, `while`), signed comparison operators (`<`, `<=`, `>`, `>=`, `==`, `!=`), arithmetic (`+`, `-`, `*`), and character I/O (`getc()`, `putc(c)`).
- **Stack & Calling Convention**: Emulates frame pointer (`FP`), stack pointer (`SP`), accumulator (`ACC`), return trampoline, and dynamic activation records supporting deep recursion ($>1000$ frames).
- **Verification**: Verified across factorial, fibonacci, square tables, 8-argument functions, and signed comparisons.

### Tier 3: Self-Hosting Bootstrap
The `v1` compiler implemented in `v1` (`tier3/tier3.v1`):
- Single-pass compilation emitting SUBLEQ machine code directly to an internal memory buffer.
- Dynamic forward jump patching for branch targets (`if`, `while`).
- Forward call trampoline mechanism resolving mutual recursion between expression and primary parsers.
- **Bootstrap Fixed Point**:
  - $C_1 = \text{compile.py}(\text{tier3.v1})$
  - $C_2 = \text{VM}(C_1, \text{tier3.v1})$ in $4.11 \times 10^9$ steps (~14.4s).
  - $C_3 = \text{VM}(C_2, \text{tier3.v1})$ in $4.05 \times 10^9$ steps (~14.3s).
  - $C_2 \equiv C_3$ bit-for-bit (343,401 32-bit machine words).

---

## Quickstart

### Building the VM
```bash
gcc -O3 tools/vm.c -o tools/vm.exe
```

### Running Tier 1 Programs
```bash
echo "Hello, SUBLEQ!" | tools/vm.exe tier1/echo.txt
echo "Hello, SUBLEQ!" | tools/vm.exe tier1/reverse.txt
```

### Compiling and Running with Tier 2
```bash
python tier2/compile.py < test.v1 > test_prog.txt
tools/vm.exe test_prog.txt
```

### Running the Tier 3 Bootstrap Verification
```bash
python scratch/run_bootstrap.py
```
