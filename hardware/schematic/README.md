# KiCad schematic source

`vix_pico_interface.sch` is a portable KiCad legacy-format schematic accompanied by its local `vix_pico_interface-cache.lib` symbol library. KiCad 7/8/9/10 can import/open legacy schematics; save it once in KiCad to convert it to the current `.kicad_sch` format.

The schematic covers the **low-voltage Pico 2 <-> ViX X4 interface** only. It intentionally does not reproduce X1 high-voltage/motor wiring or X2 motor-feedback wiring. Use the Parker manual and the correct Parker motor harness for those connections.

The exported, easy-to-read reference image is [`../../docs/images/x4_interface.svg`](../../docs/images/x4_interface.svg).
