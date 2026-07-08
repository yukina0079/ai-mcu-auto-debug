cmake_minimum_required(VERSION 3.20)

project(stm32f103_blinky C ASM)

set(LINKER_SCRIPT "${CMAKE_CURRENT_SOURCE_DIR}/linker.ld" CACHE FILEPATH "Linker script")

add_executable(firmware.elf
    src/main.c
    src/startup_stm32f103.c
)

target_compile_options(firmware.elf PRIVATE
    -mcpu=cortex-m3
    -mthumb
    -ffunction-sections
    -fdata-sections
    -Wall
    -Wextra
    -Werror
    -O0
    -g3
)

target_link_options(firmware.elf PRIVATE
    -mcpu=cortex-m3
    -mthumb
    -T${LINKER_SCRIPT}
    -nostartfiles
    -Wl,--gc-sections
    -Wl,-Map=${CMAKE_CURRENT_BINARY_DIR}/firmware.map
)

add_custom_command(TARGET firmware.elf POST_BUILD
    COMMAND ${CMAKE_OBJCOPY} -O binary $<TARGET_FILE:firmware.elf> ${CMAKE_CURRENT_BINARY_DIR}/firmware.bin
    COMMAND ${CMAKE_SIZE} $<TARGET_FILE:firmware.elf>
)
