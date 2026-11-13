#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>

#define N 1048576
#define IN_ADDR  (N - 2)
#define OUT_ADDR (N - 1)

static int32_t mem[N];

int main(int argc, char **argv) {
    if (argc < 2) {
        fprintf(stderr, "usage: %s program.txt < input.txt\n", argv[0]);
        return 1;
    }

    FILE *f = fopen(argv[1], "r");
    if (!f) {
        fprintf(stderr, "can't open %s\n", argv[1]);
        return 1;
    }

    int count = 0;
    long long val;
    while (1) {
        int res = fscanf(f, "%lld", &val);
        if (res == 1) {
            if (val < -2147483648LL || val > 2147483647LL) {
                fprintf(stderr, "word %d in program file doesn't fit in 32 bits\n", count);
                fclose(f);
                return 1;
            }
            if (count > N - 3) {
                fprintf(stderr, "program doesn't fit in memory (max %d words)\n", N - 2);
                fclose(f);
                return 1;
            }
            mem[count++] = (int32_t)val;
        } else if (res == EOF) {
            break;
        } else {
            fprintf(stderr, "bad token in program file after %d words\n", count);
            fclose(f);
            return 1;
        }
    }
    fclose(f);

    int32_t pc = 0;
    uint64_t steps = 0;
    uint64_t step_limit = 100000000ULL; /* 10^8 for tier 1 and 2, 10^10 for tier 3 */

    char *env_limit = getenv("VM_LIMIT");
    if (env_limit) {
        step_limit = strtoull(env_limit, NULL, 10);
    }

    while (pc >= 0 && pc <= N - 3) {
        if (steps == step_limit) {
            fprintf(stderr, "timeout after %llu steps (pc = %d)\n", (unsigned long long)steps, pc);
            char *dump = getenv("VM_DUMP_MEM");
            if (dump) {
                FILE *df = fopen(dump, "wb");
                if (df) {
                    fwrite(mem, sizeof(int32_t), N, df);
                    fclose(df);
                }
            }
            return 2;
        }
        steps++;

        int32_t a = mem[pc];
        int32_t b = mem[pc + 1];
        int32_t c = mem[pc + 2];

        if (a < 0 || a >= N || b < 0 || b >= N) {
            fprintf(stderr, "error at %d: operand outside memory (%d %d %d)\n", pc, a, b, c);
            return 1;
        }
        if (a == IN_ADDR) {
            fprintf(stderr, "error at %d: IN used as first operand (%d %d %d)\n", pc, a, b, c);
            return 1;
        }

        int32_t b_val;
        if (b == IN_ADDR) {
            int ch = getchar();
            b_val = (ch == EOF) ? -1 : (int32_t)(unsigned char)ch;
        } else {
            b_val = mem[b];
        }

        int32_t a_val = mem[a];
        int32_t r = (int32_t)((uint32_t)a_val - (uint32_t)b_val);

        if (a == OUT_ADDR) {
            putchar(r & 0xFF);
        } else {
            mem[a] = r;
        }

        if (r < 0) {
            pc = c;
        } else {
            pc = pc + 3;
        }
    }

    char *dump = getenv("VM_DUMP_MEM");
    if (dump) {
        FILE *df = fopen(dump, "wb");
        if (df) {
            fwrite(mem, sizeof(int32_t), N, df);
            fclose(df);
        }
    }

    if (getenv("VM_STATS")) {
        fprintf(stderr, "halted after %llu steps\n", (unsigned long long)steps);
    }
    return 0;
}
