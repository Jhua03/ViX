# PlatformIO / official Pico SDK workflow

The PlatformIO project is only a VS Code task front-end. The firmware itself is
built by the official Raspberry Pi Pico SDK for `PICO_BOARD=pico2`.

## Requirements

```bash
sudo dnf install -y cmake ninja-build arm-none-eabi-gcc-cs \
  arm-none-eabi-gcc-cs-c++ arm-none-eabi-newlib
export PICO_SDK_PATH="$HOME/pico-sdk"
```

Open VS Code from the shell that contains `PICO_SDK_PATH`:

```bash
code /path/to/vix500ae_to_100nm_v4_20/firmware
```

Use:

```text
Project Tasks -> pico2_official_sdk -> Custom -> SDK Build
Project Tasks -> pico2_official_sdk -> Custom -> SDK Upload
```

The resulting file is:

```text
build-pio/vix_base_pico2_controller.uf2
```

For the first upload, hold BOOTSEL while connecting the Pico 2. Later uploads
can use picotool when Fedora udev permissions are installed.
