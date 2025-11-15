# Pico Invaders

Pico Invaders is a MicroPython clone of the classic fixed–shooter arcade game.  
It renders a 128×64 monochrome display on an SSD1306 I²C OLED and is controlled with a rotary encoder (with push switch) for smooth left/right movement and firing. The project targets the Raspberry Pi Pico, but it should work on any RP2040 board that exposes the same pins.

## Hardware at a Glance

| Component | Notes |
| --- | --- |
| Raspberry Pi Pico (MicroPython firmware) | Uses I²C bus 1 and rotary inputs on GPIO 20–22 |
| SSD1306 128×64 OLED display (I²C) | `SDA → GP18`, `SCL → GP19`, powered from 3V3 |
| Incremental rotary encoder with switch | `CLK → GP21`, `DT → GP20`, `SW → GP22`, enable internal pull‑ups |

All graphics, game logic, and input handling live in `main.py`.  
`ssd1306.py`, `rotary.py`, and `rotary_irq_rp2.py` provide display and rotary helper classes.

## Development Environment

1. **Install VS Code** (latest) and the official **MicroPython** extension by Microsoft.
2. **Flash MicroPython** on the Pico if needed:
   - Hold the BOOTSEL button, connect USB, and copy the latest MicroPython UF2 (RP2040 build) onto the RPI-RP2 drive.
3. Clone or download this repository to your workstation.

## Running from VS Code (MicroPython Extension)

1. **Open the folder** `pico_invaders` in VS Code.
2. Press `Ctrl/Cmd + Shift + P` and run `MicroPython: Configure Global Options`; select:
   - **Board**: `Raspberry Pi Pico`.
   - **Port**: the serial port that appears when the Pico is connected.
3. Open `main.py` so the extension treats it as the active script.
4. In the MicroPython REPL sidebar (lower left):
   - Use the **File Explorer** panel to upload `main.py`, `ssd1306.py`, `rotary.py`, and `rotary_irq_rp2.py` to the Pico’s filesystem (`/`).
   - Alternatively choose `MicroPython: Upload Project to MicroPython Device` to mirror the entire folder.
5. Once the files transfer, run `MicroPython: Run current file on device` (or click the ▶ icon in the REPL).  
   The OLED should light up with the splash screen and begin the game loop.

### While Iterating

- Use `MicroPython: Reset device` from the command palette to restart the game quickly.
- If you change pin mappings (for different wiring), update the constants near the top of `main.py`.
- Keep an eye on the VS Code terminal for diagnostic prints (I²C detection, game state info).

## Gameplay & Controls

- Rotate the encoder to move the ship horizontally.
- Press the encoder switch to fire projectiles; you can fire again only after the previous shot leaves the screen or hits an enemy.
- You start with three lives (drawn as hearts). Hits trigger a brief pause and explosion animation. Clearing all enemies sets the victory flag.

## Troubleshooting

- **“No I2C Display Found”**: Verify SDA/SCL wiring and that the display uses address `0x3C` (default). You can adjust `PIX_RES_X/Y` or address logic in `main.py`.
- **Laggy encoder**: Increase `ENCODER_INCREMENT` or disable `half_step` in `RotaryIRQ` initialization.
- **Upload errors**: Ensure no other serial monitor is attached and the correct port is selected in the MicroPython extension.

Enjoy defending the Pico from waves of monochrome invaders!

## Notes
Graphics were drafted with https://lopaka.app