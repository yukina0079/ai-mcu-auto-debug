# Hardware Debug Acceptance Guide

Use this guide to verify that a real board can be controlled through the non-vision debug path: reset/halt, core register reads, memory reads, breakpoints, single-step, and evidence capture.

## 1. Prepare Tools

Install at least one debug backend:

- OpenOCD plus `arm-none-eabi-gdb`
- SEGGER J-Link GDB Server plus `arm-none-eabi-gdb`
- pyOCD GDB Server plus `arm-none-eabi-gdb`
- probe-rs GDB-style flow when supported by the target

Useful Windows setup:

```text
winget install xpack-dev-tools.openocd
winget install Arm.GnuArmEmbeddedToolchain
python -m pip install pyocd
```

Check the local machine:

```text
python -m ai_mcu_debug.cli doctor
python -m ai_mcu_debug.cli probe-scan
```

## 2. Build Firmware

For the bundled STM32F103 example:

```text
python -m ai_mcu_debug.cli build --config examples/build.stm32f103.json
python -m ai_mcu_debug.cli smoke-test --config examples/build.stm32f103.json
```

Expected ELF:

```text
build/stm32f103_blinky/firmware.elf
```

## 3. Configure the Debug Target

Start from one of these templates:

```text
examples/debug.target.openocd.json
examples/debug.target.jlink.json
examples/debug.target.pyocd.json
```

Confirm that:

- `executable` points to a real ELF.
- `gdb_path` points to an embedded GDB such as `arm-none-eabi-gdb`.
- `remote` matches the GDB server port.
- `server_command` starts the correct server for the current probe and MCU.
- NRST wiring is recorded accurately when the board does not connect reset.

## 4. Run Single Debug Operations

```text
python -m ai_mcu_debug.cli debug-op --target examples/debug.target.openocd.json reset
python -m ai_mcu_debug.cli debug-op --target examples/debug.target.openocd.json read-register --register pc
python -m ai_mcu_debug.cli debug-op --target examples/debug.target.openocd.json read-memory --address 0x20000000 --length 32
python -m ai_mcu_debug.cli debug-op --target examples/debug.target.openocd.json step
```

## 5. Run a Debug Sequence

```text
python -m ai_mcu_debug.cli debug-sequence --target examples/debug.target.openocd.json --sequence examples/debug_sequence.json
```

The sequence keeps one GDB connection open while it resets, sets breakpoints, runs, waits for stop, steps, reads registers, and reads memory.

## 6. Run Acceptance

```text
python -m ai_mcu_debug.cli accept-first-stage --target examples/debug.target.openocd.json --task examples/debug_task.json
```

The acceptance report should show:

- `read_core_registers=true`
- `read_memory_address=true`
- `reset_and_halt=true`
- `breakpoint_and_stop=true`
- `single_step=true`
- `debug_record=true`

Reports are written under `debug_runs/`. Keep them locally or include a sanitized copy in an `export-handoff` package.
