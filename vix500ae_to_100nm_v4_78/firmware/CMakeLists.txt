cmake_minimum_required(VERSION 3.13)

if(NOT DEFINED PICO_BOARD)
    set(PICO_BOARD pico2 CACHE STRING "Pico board")
endif()

include($ENV{PICO_SDK_PATH}/external/pico_sdk_import.cmake)

project(vix_base_pico2_controller C CXX ASM)
set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)

# The wrapper builds a host pioasm from this exact Pico SDK revision before
# configuring the firmware. Defining the imported target here prevents SDK
# 2.3.x Findpioasm.cmake from creating its BUILD_ALWAYS ExternalProject.
if(NOT DEFINED PIOASM_EXECUTABLE OR NOT EXISTS "${PIOASM_EXECUTABLE}")
    message(FATAL_ERROR
        "PIOASM_EXECUTABLE must name the verified host pioasm built by "
        "firmware/extra_scripts/pico_sdk_tasks.py")
endif()
if(NOT TARGET pioasm)
    add_executable(pioasm IMPORTED GLOBAL)
    set_property(TARGET pioasm PROPERTY IMPORTED_LOCATION "${PIOASM_EXECUTABLE}")
endif()

# Keep picotool out of CMake's dependency graph. The wrapper converts the
# completed ELF to UF2 after Ninja has reached a true no-op state.
set(PICO_NO_PICOTOOL 1 CACHE BOOL
    "Disable SDK picotool integration; wrapper creates UF2 after build" FORCE)

pico_sdk_init()

add_executable(vix_base_pico2_controller
    src/main.c
)

pico_generate_pio_header(vix_base_pico2_controller
    ${CMAKE_CURRENT_LIST_DIR}/src/stepgen.pio
)

pico_generate_pio_header(vix_base_pico2_controller
    ${CMAKE_CURRENT_LIST_DIR}/src/quadrature_encoder.pio
)

target_include_directories(vix_base_pico2_controller PRIVATE
    ${CMAKE_CURRENT_LIST_DIR}/src
)

target_link_libraries(vix_base_pico2_controller
    pico_stdlib
    pico_multicore
    hardware_clocks
    hardware_pio
    hardware_irq
)

pico_enable_stdio_usb(vix_base_pico2_controller 1)
pico_enable_stdio_uart(vix_base_pico2_controller 0)
pico_add_extra_outputs(vix_base_pico2_controller)
