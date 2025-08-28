# Xilinx Virtual Cable Server for Raspberry Pi

[Xilinx Virtual Cable](https://github.com/Xilinx/XilinxVirtualCable/) (XVC) is a TCP/IP-based protocol that acts like a JTAG cable and provides a means to access and debug your FPGA or SoC design without using a physical cable.
A full description of Xilinx Virtual Cable in action is provided in the [XAPP1252 application note](https://www.xilinx.com/support/documentation/application_notes/xapp1251-xvc-zynq-petalinux.pdf).

**Xvcpi** implements an XVC server to allow a Xilinx FPGA or SOC to be controlled remotely by Xilinx Vivado using the Xilinx Virtual Cable protocol. **Xvcpi** uses TCP port 2542 by default.

The **xvcpi** server runs on a Raspberry Pi which is connected, using JTAG, to the target device. **Xvcpi** bitbangs the JTAG control signals on the Pi pins. The bitbanging code was originally extracted from [OpenOCD](http://openocd.org).

## Available Implementations

This project provides two implementations of the XVC server:

### 🔧 C Implementation (`xvcpi.c`)
- **High performance** native C implementation
- Uses modern `libgpiod` library for GPIO control
- **Lower resource usage** - ideal for production environments
- **Fast execution** - optimized for speed-critical applications

### 🐍 Python Implementation (`xvcpi.py`)
- **Easy to modify and extend** - written in pure Python
- Uses `gpiozero` library for GPIO control  
- **Better debugging capabilities** - Python debugging tools
- **Cross-platform potential** - easily portable
- **Comprehensive documentation** and testing included

Both implementations provide identical functionality and command-line interfaces, making them interchangeable based on your needs.

## Modern Implementation

Both implementations have been updated for modern Raspberry Pi systems:

### C Version Features
- Uses modern `libgpiod` library instead of legacy `bcm_host`
- Better compatibility with modern Raspberry Pi systems (including Pi 5)
- Improved GPIO handling and error checking
- More flexible pin configuration via command-line arguments
- Better signal handling and cleanup

### Python Version Features
- Uses `gpiozero` library for Python-native GPIO control
- Object-oriented design for easy extension
- Comprehensive logging and debugging support
- Built-in test suite for verification
- Same GPIO pin configurations and protocol compatibility

## Wiring
Note: The Raspberry Pi is a 3.3V device. Ensure that the target device and the Pi are electrically compatible before connecting. 100 Ohm resistors may be placed inline on all of the JTAG signals to provide a degree of electrical isolation.

JTAG uses 4 signals, TMS, TDI, TDO and, TCK.
From the Raspberry Pi perspective, TMS, TDI and TCK are outputs, and TDO is an input.

### Default Pin Configuration
The default pin mappings for the Raspberry Pi header are:
```
TMS=GPIO25, TDI=GPIO10, TCK=GPIO11, TDO=GPIO9
```

### Alternative Pin Configuration
Alternative pin configurations are also supported and can be specified via command-line arguments:
```
TMS=GPIO13, TDI=GPIO19, TCK=GPIO6, TDO=GPIO26
```

In addition a ground connection is required. Pin 20 is a conveniently placed GND.

The same pins are also used by [Blinkinlabs JTAG Hat](https://github.com/blinkinlabs/jtag_hat). This JTAG Hat accommodates target devices with voltage levels between 1.8V and 5V by using buffers.

Note that the XVC protocol does not provide control of either SRST or TRST and **xvcpi** does not support a RST signal.

## Usage

Both implementations support identical command-line interfaces and functionality.

### Quick Start

**C Version:**
```bash
# Build and run
make
sudo ./xvcpi -v

# Or install system-wide
sudo make install
sudo xvcpi -v
```

**Python Version:**
```bash
# Install dependencies and run
pip install gpiozero
sudo python3 xvcpi.py -v

# Make executable for easier use
chmod +x xvcpi.py
sudo ./xvcpi.py -v
```

### Command-Line Options
Both implementations support flexible configuration via command-line arguments:

**Available Options:**
- `-v` : Enable verbose output
- `-d delay` : Set JTAG delay (default: 40)
- `-p port` : Set TCP port (default: 2542)
- `-c pin` : Set TCK GPIO pin (default: 11)
- `-m pin` : Set TMS GPIO pin (default: 25)
- `-i pin` : Set TDI GPIO pin (default: 10)
- `-o pin` : Set TDO GPIO pin (default: 9)

### Usage Examples

**Use default configuration:**
```bash
# C version
sudo ./xvcpi

# Python version  
sudo python3 xvcpi.py
```

**Use alternative pin configuration:**
```bash
# C version
sudo ./xvcpi -c 6 -m 13 -i 19 -o 26

# Python version
sudo python3 xvcpi.py -c 6 -m 13 -i 19 -o 26
```

**Custom port and verbose output:**
```bash
# C version
sudo ./xvcpi -v -p 2543

# Python version
sudo python3 xvcpi.py -v -p 2543
```

**Custom delay for different speed requirements:**
```bash
# C version
sudo ./xvcpi -d 100

# Python version
sudo python3 xvcpi.py -d 100
```

### JTAG Speed Control
The JTAG interface speed can be controlled by specifying an integer delay after the `-d` flag.
The maximum speed is dependent on the speed of the Pi, the quality of the connections and the target device.
Delay values from 200 to 1000 work well. Smaller is faster, larger more reliable!

### Vivado Connection
Vivado connects to **xvcpi** via an intermediate software server called hw_server. To allow Vivado "autodiscovery" of **xvcpi** via hw_server run:

```bash
hw_server -e 'set auto-open-servers xilinx-xvc:<xvcpi-server>:2542'
```

Alternatively, the following tcl commands can be used in the Vivado Tcl console to initiate a connection:

```tcl
open_hw
connect_hw_server
open_hw_target -xvc_url <xvcpi-server>:2542
```

Full instructions can be found in [ProdDoc_XVC_2014_3](ProdDoc_XVC_2014_3.pdf).

## Building and Installation

### C Implementation

**Prerequisites:**
```bash
sudo apt-get install libgpiod-dev
```

**Compilation:**
```bash
make clean
make
```

**Installation (Optional):**
```bash
sudo make install
```
This installs the binary to `/usr/local/bin/` with appropriate permissions.

### Python Implementation

**Prerequisites:**
```bash
# Install gpiozero library
pip install gpiozero

# Or install from requirements.txt
pip install -r requirements.txt
```

**Make executable (Optional):**
```bash
chmod +x xvcpi.py
```

**Testing:**
```bash
# Run the included test suite
python3 test_xvcpi.py
```

## Implementation Comparison

| Feature | C Version | Python Version |
|---------|-----------|----------------|
| **Performance** | Higher (native C) | Good (2-3x slower) |
| **Memory Usage** | Lower (~1-2MB) | Higher (~10-15MB) |
| **Startup Time** | Instant | ~1 second |
| **Dependencies** | libgpiod-dev | gpiozero (pip) |
| **Debugging** | GDB, printf | Built-in Python tools |
| **Modification** | Requires C knowledge | Easy Python editing |
| **Portability** | Linux/ARM specific | Cross-platform potential |
| **Testing** | Manual testing | Automated test suite |

**Choose C version for:**
- Production deployments requiring maximum performance
- Embedded systems with limited resources
- When minimal dependencies are preferred

**Choose Python version for:**
- Development and prototyping
- Custom JTAG sequence development  
- Educational purposes
- When easy modification is important

## Snickerdoodle
The initial purpose of **xvcpi** was to provide a simple means of programming the [Snickerdoodle](http://snickerdoodle.io).

## Additional Documentation

- **[README_PYTHON.md](README_PYTHON.md)** - Detailed documentation for the Python implementation
- **[CONFIGURATION.md](CONFIGURATION.md)** - GPIO configuration and wiring details
- **[XVC.README.md](XVC.README.md)** - XVC protocol specification
- **[ProdDoc_XVC_2014_3.pdf](ProdDoc_XVC_2014_3.pdf)** - Official XVC documentation

## Testing

### Python Implementation Testing
```bash
# Run comprehensive test suite
python3 test_xvcpi.py

# Test specific functionality
python3 -c "
from test_xvcpi import test_xvc_protocol
test_xvc_protocol()
"
```

### Manual Testing (Both Versions)
```bash
# Start server with verbose output
sudo ./xvcpi -v          # C version
sudo python3 xvcpi.py -v # Python version

# Test connection from another terminal
telnet localhost 2542
# Type: getinfo:
# Expected response: xvcServer_v1.0:2048
```

## Troubleshooting

### Common Issues
- **Permission denied**: Run with `sudo` or add user to `gpio` group
- **GPIO already in use**: Check for conflicting processes or use different pins
- **Connection refused**: Verify server is running and port is not blocked
- **JTAG communication errors**: Increase delay value or check wiring

### Performance Tuning
- **C version**: Already optimized for performance
- **Python version**: Consider PyPy for better performance if needed
- **Both versions**: Adjust `-d` delay parameter for speed vs. reliability

## Licensing
Both implementations maintain the same licensing as the original work:

This work, "xvcpi.c" and "xvcpi.py", is a derivative of "xvcServer.c" (https://github.com/Xilinx/XilinxVirtualCable)

"xvcServer.c" is licensed under CC0 1.0 Universal (http://creativecommons.org/publicdomain/zero/1.0/)
by Avnet and is used by Xilinx for XAPP1251.

"xvcServer.c", is a derivative of "xvcd.c" (https://github.com/tmbinc/xvcd)
by tmbinc, used under CC0 1.0 Universal (http://creativecommons.org/publicdomain/zero/1.0/).

Portions of both implementations are derived from OpenOCD (http://openocd.org)

Both "xvcpi.c" and "xvcpi.py" are licensed under CC0 1.0 Universal (http://creativecommons.org/publicdomain/zero/1.0/)
by Derek Mulcahy.

Updated for modern Raspberry Pi systems using libgpiod (C) and gpiozero (Python).
