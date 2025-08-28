# XVCPi Python Implementation

This is a Python port of the **xvcpi** server that implements the Xilinx Virtual Cable (XVC) protocol for Raspberry Pi. The Python version provides the same functionality as the original C implementation while being more accessible and easier to modify.

## Overview

**xvcpi.py** implements an XVC server to allow Xilinx FPGA or SoC devices to be controlled remotely by Xilinx Vivado using the Xilinx Virtual Cable protocol over TCP/IP. The server uses JTAG bit-banging on Raspberry Pi GPIO pins.

### Key Features

- **Pure Python implementation** using `gpiozero` for GPIO control
- **XVC 1.0 protocol compliance** - compatible with Xilinx Vivado
- **Flexible GPIO pin configuration** via command-line arguments  
- **Configurable JTAG timing** for different speed requirements
- **Comprehensive logging** with verbose mode support
- **Signal handling** for graceful shutdown
- **Test suite included** for verification

## Comparison with C Version

| Feature | C Version (xvcpi.c) | Python Version (xvcpi.py) |
|---------|-------------------|---------------------------|
| GPIO Library | libgpiod | gpiozero |
| Performance | Higher (native C) | Good (Python with optimizations) |
| Memory Usage | Lower | Higher |
| Portability | Compiled binary | Interpreted, cross-platform |
| Maintainability | Requires C knowledge | Easier to modify/extend |
| Dependencies | libgpiod-dev | gpiozero (pip installable) |
| Debugging | GDB required | Built-in Python debugging |

## Requirements

- Raspberry Pi (any model with GPIO)
- Python 3.7 or newer
- gpiozero library

## Installation

1. **Install Python dependencies:**
   ```bash
   pip install gpiozero
   ```
   
2. **Make the script executable:**
   ```bash
   chmod +x xvcpi.py
   ```

## GPIO Pin Configuration

The default GPIO pin assignments match the C version:

### Default Configuration
```
TMS = GPIO25 (Pin 22)
TDI = GPIO10 (Pin 19) 
TCK = GPIO11 (Pin 23)
TDO = GPIO9  (Pin 21)
```

### Alternative Configuration
```
TMS = GPIO13 (Pin 33)
TDI = GPIO19 (Pin 35)
TCK = GPIO6  (Pin 31)  
TDO = GPIO26 (Pin 37)
```

**Note:** Ensure proper electrical compatibility between the Raspberry Pi (3.3V) and your target device. Consider using 100Ω series resistors for signal isolation.

## Usage

### Basic Usage

```bash
# Run with default settings
sudo python3 xvcpi.py

# Run with verbose output
sudo python3 xvcpi.py -v
```

### Advanced Configuration

```bash
# Use alternative pin configuration
sudo python3 xvcpi.py -c 6 -m 13 -i 19 -o 26

# Custom port and timing
sudo python3 xvcpi.py -p 2543 -d 100

# Full configuration example
sudo python3 xvcpi.py -v -p 2542 -d 40 -c 11 -m 25 -i 10 -o 9
```

### Command Line Options

```
-h, --help            Show help message
-v, --verbose         Enable verbose output
-d, --delay DELAY     JTAG delay (default: 40)
-p, --port PORT       TCP port (default: 2542)
-c, --tck PIN         TCK GPIO pin (default: 11)
-m, --tms PIN         TMS GPIO pin (default: 25)
-i, --tdi PIN         TDI GPIO pin (default: 10)
-o, --tdo PIN         TDO GPIO pin (default: 9)
```

## JTAG Timing

The `--delay` parameter controls JTAG interface speed:
- **Lower values** = faster operation
- **Higher values** = more reliable with long connections
- **Default (40)** works well for most setups
- **Range 40-200** recommended for testing
- **Range 200-1000** for long cables or difficult targets

## XVC Protocol

The Python implementation supports all XVC 1.0 protocol commands:

### getinfo Command
Returns server version and maximum vector length:
```
Client: "getinfo:"
Server: "xvcServer_v1.0:2048\n"
```

### settck Command  
Sets JTAG clock period (currently echoed back):
```
Client: "settck:<4-byte period in ns>"
Server: "<4-byte period in ns>"
```

### shift Command
Performs JTAG bit shifting operations:
```
Client: "shift:<length><tms_vector><tdi_vector>"
Server: "<tdo_vector>"
```

## Integration with Vivado

### Using hw_server (Recommended)

```bash
# Start xvcpi on Raspberry Pi
sudo python3 xvcpi.py -v

# On Vivado machine, start hw_server with auto-discovery
hw_server -e 'set auto-open-servers xilinx-xvc:<rpi-ip>:2542'
```

### Direct Connection

In Vivado TCL console:
```tcl
open_hw
connect_hw_server  
open_hw_target -xvc_url <rpi-ip>:2542
```

## Testing

A comprehensive test suite is included:

```bash
# Run all tests
python3 test_xvcpi.py

# Tests include:
# - XVC protocol command handling
# - TCP server functionality  
# - GPIO operations (mocked)
# - Command-line argument parsing
```

## Troubleshooting

### Permission Issues
```bash
# Add user to gpio group
sudo usermod -a -G gpio $USER

# Or run with sudo
sudo python3 xvcpi.py
```

### GPIO Already in Use
```bash
# Check what's using GPIO
sudo lsof /dev/gpiochip0

# Kill conflicting processes or choose different pins
```

### Connection Issues
```bash
# Check if server is listening
netstat -ln | grep 2542

# Test connection locally
telnet localhost 2542
```

### JTAG Communication Problems
- Increase delay parameter (`-d 100` or higher)
- Check wiring and connections
- Verify target device power and reset state
- Try alternative pin configuration

## Performance Considerations

### Python vs C Performance
- The Python version is approximately 2-3x slower than C
- For most JTAG operations, this difference is negligible
- Critical path optimizations include:
  - Efficient bit manipulation
  - Minimal function call overhead in GPIO operations
  - Bulk processing of 32-bit chunks

### Optimization Tips
- Use lower delay values for faster operation
- Ensure good signal integrity for reliable high-speed operation
- Consider using PyPy for potentially better performance

## Development and Debugging

### Code Structure
```python
XVCServer class:
├── GPIO Management (init_gpio, gpio_read, gpio_write, gpio_transfer)
├── XVC Protocol (handle_getinfo, handle_settck, handle_shift)  
├── TCP Server (start_server, handle_client, safe_read)
└── Utilities (signal_handler, cleanup)
```

### Adding Custom Features
The Python implementation makes it easy to add:
- Custom JTAG sequences
- Protocol extensions
- GPIO monitoring
- Performance metrics
- Remote logging

### Debug Mode
```bash
# Enable debug logging
python3 -c "
import logging
logging.basicConfig(level=logging.DEBUG)
exec(open('xvcpi.py').read())
" -v
```

## Compatibility

- **Hardware:** All Raspberry Pi models with 40-pin GPIO header
- **OS:** Raspberry Pi OS, Ubuntu, other Linux distributions
- **Python:** 3.7+ (tested with 3.9, 3.10, 3.11)
- **Vivado:** All versions supporting XVC 1.0 protocol

## License

This Python implementation maintains the same CC0 1.0 Universal license as the original C version.

## Contributing

Contributions are welcome! Areas for improvement:
- Performance optimizations
- Additional protocol features  
- Better error handling
- More comprehensive testing
- Documentation improvements

## Changelog

### v1.0 (Initial Python Port)
- Complete XVC 1.0 protocol implementation
- gpiozero-based GPIO control
- Command-line argument parsing
- Comprehensive test suite
- Signal handling and cleanup
- Verbose logging support
