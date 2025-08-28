# XVC Server Configuration Guide

The `xvcpi_modern` server now supports configurable GPIO pins and port numbers via command-line arguments.

## Command-Line Options

```bash
./xvcpi_modern [options]
```

### Available Options

| Option | Description | Default | Example |
|--------|-------------|---------|---------|
| `-v` | Enable verbose output | Disabled | `-v` |
| `-d delay` | Set JTAG transition delay | 40 | `-d 20` |
| `-p port` | Set TCP port number | 2542 | `-p 2543` |
| `-c pin` | Set TCK GPIO pin | 6 | `-c 11` |
| `-m pin` | Set TMS GPIO pin | 13 | `-m 25` |
| `-i pin` | Set TDI GPIO pin | 19 | `-i 10` |
| `-o pin` | Set TDO GPIO pin | 26 | `-o 9` |
| `-?` | Show help message | N/A | `-?` |

## Configuration Examples

### 1. Default Configuration
Uses the original working GPIO pins and default port:
```bash
sudo ./xvcpi_modern -v
```
- TCK: GPIO11
- TMS: GPIO25  
- TDI: GPIO10
- TDO: GPIO9
- Port: 2542
- Delay: 40

### 2. Alternative GPIO Pins (previous working set)
Use the GPIO pins from the previous working version:
```bash
sudo ./xvcpi_modern -v -c 6 -m 13 -i 19 -o 26
```
- TCK: GPIO6
- TMS: GPIO13
- TDI: GPIO19
- TDO: GPIO26
- Port: 2542
- Delay: 40

### 3. Custom Port
Change only the port number:
```bash
sudo ./xvcpi_modern -v -p 2543
```
- Port: 2543 (all other settings remain default)

### 4. Custom JTAG Delay
Adjust the JTAG timing:
```bash
sudo ./xvcpi_modern -v -d 20
```
- Delay: 20 (faster transitions, all other settings remain default)

### 5. Full Custom Configuration
Customize everything:
```bash
sudo ./xvcpi_modern -v -c 5 -m 6 -i 13 -o 19 -p 2544 -d 30
```
- TCK: GPIO5
- TMS: GPIO6
- TDI: GPIO13
- TDO: GPIO19
- Port: 2544
- Delay: 30

## GPIO Pin Selection Guidelines

- **TCK (Clock)**: Should be a GPIO pin that can generate clean clock signals
- **TMS (Mode Select)**: Critical for JTAG state transitions
- **TDI (Data In)**: Used for sending data to the target device
- **TDO (Data Out)**: Used for reading data from the target device

### Recommended GPIO Pins
- **GPIO 6, 13, 19, 26**: Tested and working (default)
- **GPIO 11, 25, 10, 9**: Original xvcpi.c configuration
- **Avoid**: Pins used by system functions (I2C, SPI, UART, etc.)

## Port Configuration

- **Default Port 2542**: Standard XVC port
- **Custom Ports**: Useful when running multiple XVC servers or avoiding conflicts
- **Firewall**: Ensure the selected port is accessible from your network

## Troubleshooting

### GPIO Pin Busy Error
If you get "Device or resource busy" errors:
```bash
# Check what's using the GPIO pins
gpioinfo gpiochip0 | grep -E "(pin_number)"

# Kill any existing xvcpi_modern processes
sudo pkill xvcpi_modern

# Wait a moment for GPIO cleanup, then retry
```

### Invalid Pin Numbers
- GPIO pins must be non-negative integers
- Valid range depends on your Raspberry Pi model
- Invalid pins will fall back to defaults

### Port Already in Use
If the port is already in use:
```bash
# Check what's using the port
sudo netstat -tlnp | grep :2542

# Choose a different port
sudo ./xvcpi_modern -v -p 2543
```

## Performance Tuning

### JTAG Delay
- **Lower values (20-30)**: Faster operation, may cause timing issues
- **Default (40)**: Balanced performance and reliability
- **Higher values (50-80)**: Slower but more reliable on marginal connections

### GPIO Pin Selection
- Use dedicated GPIO pins not shared with other functions
- Avoid pins near switching power supplies or high-frequency signals
- Consider using pins with good drive strength for TCK and TMS
