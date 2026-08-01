#!/usr/bin/env python3
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CC = shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
if CC is None:
    raise SystemExit("No C compiler found for firmware syntax audit")

headers = {
    "hardware/pio.h": r'''
#ifndef STUB_PIO_H
#define STUB_PIO_H
#include <stdbool.h>
#include <stdint.h>
typedef unsigned int uint;
typedef void* PIO;
#define pio0 ((PIO)0x1)
#define pio1 ((PIO)0x2)
typedef struct { int dummy; } pio_program;
static inline bool pio_interrupt_get(PIO p, uint i){return false;}
static inline void pio_interrupt_clear(PIO p, uint i){}
static inline void pio_sm_set_enabled(PIO p, uint sm, bool e){}
static inline void pio_sm_clear_fifos(PIO p, uint sm){}
static inline void pio_sm_restart(PIO p, uint sm){}
static inline void pio_sm_set_clkdiv(PIO p, uint sm, float d){}
static inline void pio_sm_put_blocking(PIO p, uint sm, uint32_t v){}
static inline bool pio_can_add_program_at_offset(PIO p,const pio_program* pr,uint o){return true;}
static inline uint pio_add_program_at_offset(PIO p,const pio_program* pr,uint o){return o;}
static inline uint pio_add_program(PIO p,const pio_program* pr){return 0;}
static inline uint pio_claim_unused_sm(PIO p,bool r){return 0;}
static inline void pio_set_irq0_source_enabled(PIO p,int src,bool e){}
#define pis_interrupt1 1
#endif
''',
    "hardware/gpio.h": r'''
#ifndef STUB_GPIO_H
#define STUB_GPIO_H
#include <stdbool.h>
#include <stdint.h>
typedef unsigned int uint;
#define GPIO_OUT 1
#define GPIO_IN 0
#define GPIO_IRQ_EDGE_RISE 1u
#define GPIO_IRQ_EDGE_FALL 2u
static inline void gpio_put(uint p,bool v){}
static inline int gpio_get(uint p){return 0;}
static inline void gpio_init(uint p){}
static inline void gpio_set_dir(uint p,int d){}
static inline void gpio_pull_up(uint p){}
static inline void gpio_pull_down(uint p){}
static inline void gpio_set_irq_enabled_with_callback(uint p,uint32_t e,bool en,void(*cb)(uint,uint32_t)){}
static inline void gpio_set_irq_enabled(uint p,uint32_t e,bool en){}
#endif
''',
    "hardware/irq.h": r'''
#ifndef STUB_IRQ_H
#define STUB_IRQ_H
#define PIO1_IRQ_0 0
static inline void irq_set_exclusive_handler(int i, void(*h)(void)){}
static inline void irq_set_enabled(int i, int e){}
#endif
''',
    "hardware/clocks.h": r'''
#ifndef STUB_CLOCKS_H
#define STUB_CLOCKS_H
#include <stdint.h>
#define clk_sys 0
static inline uint32_t clock_get_hz(int c){return 150000000u;}
#endif
''',
    "pico/stdlib.h": r'''
#ifndef STUB_STDLIB_H
#define STUB_STDLIB_H
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
typedef unsigned int uint;
typedef int64_t absolute_time_t;
#define PICO_ERROR_TIMEOUT (-1)
static inline void stdio_init_all(void){}
static inline void sleep_ms(uint32_t x){}
static inline void sleep_us(uint64_t x){}
static inline uint64_t time_us_64(void){return 0;}
static inline absolute_time_t make_timeout_time_us(uint64_t x){return 0;}
static inline bool time_reached(absolute_time_t t){return false;}
static inline int getchar_timeout_us(uint32_t x){return PICO_ERROR_TIMEOUT;}
static inline void tight_loop_contents(void){}
static inline void panic(const char* x){}
#endif
''',
    "pico/multicore.h": r'''
#ifndef STUB_MULTICORE_H
#define STUB_MULTICORE_H
static inline void multicore_launch_core1(void(*f)(void)){}
#endif
''',
    "pico/util/queue.h": r'''
#ifndef STUB_QUEUE_H
#define STUB_QUEUE_H
#include <stdbool.h>
#include <stddef.h>
typedef struct {int dummy;} queue_t;
static inline bool queue_init(queue_t*q,size_t a,unsigned int b){return true;}
static inline void queue_remove_blocking(queue_t*q,void*p){}
static inline bool queue_try_add(queue_t*q,const void*p){return true;}
#endif
''',
    "stepgen.pio.h": r'''
#ifndef STUB_STEPGEN_H
#define STUB_STEPGEN_H
#include "hardware/pio.h"
static const pio_program stepgen_program={0};
static inline void stepgen_program_init(PIO p,uint sm,uint off,uint pin){}
#endif
''',
    "quadrature_encoder.pio.h": r'''
#ifndef STUB_QUAD_H
#define STUB_QUAD_H
#include "hardware/pio.h"
static const pio_program quadrature_encoder_program={0};
static inline void quadrature_encoder_program_init(PIO p,uint sm,uint pin,int v){}
static inline int32_t quadrature_encoder_get_count(PIO p,uint sm){return 0;}
#endif
''',
}

with tempfile.TemporaryDirectory() as directory:
    stub_root = Path(directory)
    for relative, text in headers.items():
        path = stub_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    subprocess.run(
        [
            CC,
            "-std=c11",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-Wno-unused-parameter",
            "-Wno-unused-function",
            "-fsyntax-only",
            f"-I{stub_root}",
            f"-I{ROOT / 'firmware/src'}",
            str(ROOT / "firmware/src/main.c"),
        ],
        check=True,
    )

print("firmware C11 syntax audit PASS")
