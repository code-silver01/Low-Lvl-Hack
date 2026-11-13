# Tier 2: v1 Compiler

## Requirements
- Python 3.8+ (standard library only; no external dependencies)

## How to Run
The compiler reads a `v1` source file from standard input and outputs whitespace-separated decimal integers (the format `vm` reads) to standard output.

```bash
# On Linux / macOS:
python3 tier2/compile.py < program.v1 > program.txt

# On Windows:
python tier2\compile.py < program.v1 > program.txt
```

## Running the Compiled Program on VM
```bash
# Using the provided VM:
./vm program.txt < input.txt

# Or using tools/vm.exe (on Windows):
tools\vm.exe program.txt < input.txt
```

