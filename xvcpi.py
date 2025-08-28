#!/usr/bin/env python3
"""
Xilinx Virtual Cable Server for Raspberry Pi (Python Version)

This is a Python implementation of xvcpi that provides XVC (Xilinx Virtual Cable)
server functionality. It implements the XVC 1.0 protocol to allow Xilinx Vivado
to program and debug FPGA/SoC devices over TCP/IP using JTAG.

The XVC protocol consists of three main commands:
- getinfo: Returns server version and capabilities
- settck: Sets JTAG clock period
- shift: Performs JTAG bit shift operations
"""

import argparse
import socket
import struct
import signal
import sys
import time
import logging
from typing import Optional, Tuple
from gpiozero import DigitalOutputDevice, DigitalInputDevice


class XVCServer:
    """Xilinx Virtual Cable Server implementation in Python"""
    
    # Default GPIO pin assignments
    DEFAULT_TCK_PIN = 11
    DEFAULT_TMS_PIN = 25 
    DEFAULT_TDI_PIN = 10
    DEFAULT_TDO_PIN = 9
    
    # Default configuration
    DEFAULT_PORT = 2542
    DEFAULT_DELAY = 40
    
    # XVC Protocol constants
    XVC_VERSION = "xvcServer_v1.0:2048\n"
    MAX_VECTOR_LENGTH = 2048
    
    def __init__(self, 
                 tck_pin: int = DEFAULT_TCK_PIN,
                 tms_pin: int = DEFAULT_TMS_PIN,
                 tdi_pin: int = DEFAULT_TDI_PIN,
                 tdo_pin: int = DEFAULT_TDO_PIN,
                 port: int = DEFAULT_PORT,
                 delay: int = DEFAULT_DELAY,
                 verbose: bool = False):
        """
        Initialize XVC Server
        
        Args:
            tck_pin: GPIO pin for JTAG TCK (clock)
            tms_pin: GPIO pin for JTAG TMS (test mode select)
            tdi_pin: GPIO pin for JTAG TDI (test data in)
            tdo_pin: GPIO pin for JTAG TDO (test data out)
            port: TCP port to listen on
            delay: JTAG timing delay
            verbose: Enable verbose logging
        """
        self.tck_pin = tck_pin
        self.tms_pin = tms_pin
        self.tdi_pin = tdi_pin
        self.tdo_pin = tdo_pin
        self.port = port
        self.jtag_delay = delay
        self.verbose = verbose
        self.running = True
        
        # GPIO device objects
        self.tck: Optional[DigitalOutputDevice] = None
        self.tms: Optional[DigitalOutputDevice] = None
        self.tdi: Optional[DigitalOutputDevice] = None
        self.tdo: Optional[DigitalInputDevice] = None
        
        # Socket for server
        self.server_socket: Optional[socket.socket] = None
        
        # Setup logging
        self.logger = logging.getLogger('xvcpi')
        level = logging.DEBUG if verbose else logging.INFO
        logging.basicConfig(
            level=level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
    
    def init_gpio(self) -> bool:
        """
        Initialize GPIO pins for JTAG operations
        
        Returns:
            True if successful, False otherwise
        """
        try:
            # Initialize TDO as input (data from target device)
            self.tdo = DigitalInputDevice(self.tdo_pin)
            
            # Initialize TDI, TCK, TMS as outputs (data to target device)
            self.tdi = DigitalOutputDevice(self.tdi_pin, initial_value=False)
            self.tck = DigitalOutputDevice(self.tck_pin, initial_value=False)
            self.tms = DigitalOutputDevice(self.tms_pin, initial_value=True)  # TMS starts high
            
            if self.verbose:
                self.logger.info("GPIO pins configured successfully")
                self.logger.info(f"TMS=GPIO{self.tms_pin}, TDI=GPIO{self.tdi_pin}, "
                               f"TCK=GPIO{self.tck_pin}, TDO=GPIO{self.tdo_pin}")
            
            # Initialize JTAG state (TCK=0, TMS=1, TDI=0)
            self.gpio_write(0, 1, 0)
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to initialize GPIO: {e}")
            return False
    
    def cleanup_gpio(self):
        """Clean up GPIO resources"""
        try:
            if self.tck:
                self.tck.close()
            if self.tms:
                self.tms.close()
            if self.tdi:
                self.tdi.close()
            if self.tdo:
                self.tdo.close()
        except Exception as e:
            self.logger.error(f"Error during GPIO cleanup: {e}")
    
    def gpio_read(self) -> int:
        """
        Read TDO pin value
        
        Returns:
            1 or 0 depending on TDO pin state
        """
        try:
            return 1 if self.tdo.value else 0
        except Exception:
            return 0
    
    def gpio_write(self, tck: int, tms: int, tdi: int):
        """
        Write values to JTAG control pins with timing delay
        
        Args:
            tck: TCK (clock) value (0 or 1)
            tms: TMS (test mode select) value (0 or 1) 
            tdi: TDI (test data in) value (0 or 1)
        """
        try:
            self.tck.value = bool(tck)
            self.tms.value = bool(tms)
            self.tdi.value = bool(tdi)
            
            # Add timing delay (equivalent to C version's asm volatile loop)
            for _ in range(self.jtag_delay):
                pass
                
        except Exception as e:
            self.logger.error(f"Error writing GPIO: {e}")
    
    def gpio_transfer(self, num_bits: int, tms_data: int, tdi_data: int) -> int:
        """
        Perform JTAG bit transfer operation
        
        This is the core JTAG operation that shifts bits in/out while
        controlling TMS and TDI, and reading TDO.
        
        Args:
            num_bits: Number of bits to transfer
            tms_data: TMS bit vector
            tdi_data: TDI bit vector
            
        Returns:
            TDO bit vector read from target
        """
        tdo_data = 0
        
        for i in range(num_bits):
            # Extract current bit values
            tms_bit = (tms_data >> i) & 1
            tdi_bit = (tdi_data >> i) & 1
            
            # Clock low phase with data setup
            self.gpio_write(0, tms_bit, tdi_bit)
            
            # Clock high phase (data is clocked in on rising edge)
            self.gpio_write(1, tms_bit, tdi_bit)
            
            # Read TDO during high phase and build result
            tdo_bit = self.gpio_read()
            tdo_data |= (tdo_bit << i)
            
            # Return to low for next cycle
            self.gpio_write(0, tms_bit, tdi_bit)
        
        return tdo_data
    
    def handle_getinfo(self) -> bytes:
        """
        Handle XVC getinfo command
        
        Returns:
            Server version and capabilities string
        """
        if self.verbose:
            self.logger.info("Received command: 'getinfo'")
            self.logger.info(f"Replied with {self.XVC_VERSION.strip()}")
        
        return self.XVC_VERSION.encode('ascii')
    
    def handle_settck(self, period_data: bytes) -> bytes:
        """
        Handle XVC settck command
        
        Args:
            period_data: 4-byte little-endian period value in nanoseconds
            
        Returns:
            Current period setting (echo back the input)
        """
        if self.verbose:
            period = struct.unpack('<I', period_data)[0]
            self.logger.info("Received command: 'settck'")
            self.logger.info(f"Period set to: {period} ns")
        
        # For this implementation, we just echo back the period
        # In a more sophisticated implementation, this could adjust timing
        return period_data
    
    def handle_shift(self, length: int, buffer: bytes) -> bytes:
        """
        Handle XVC shift command - the main JTAG operation
        
        Args:
            length: Number of bits to shift
            buffer: Contains TMS and TDI vectors
            
        Returns:
            TDO vector with result data
        """
        if self.verbose:
            self.logger.info("Received command: 'shift'")
            self.logger.info(f"Number of Bits: {length}")
        
        # Calculate number of bytes needed (round up to nearest byte)
        num_bytes = (length + 7) // 8
        
        if self.verbose:
            self.logger.info(f"Number of Bytes: {num_bytes}")
        
        # Initialize JTAG state before transfer
        self.gpio_write(0, 1, 1)
        
        # Prepare result buffer
        result = bytearray(num_bytes)
        
        # Process data in 32-bit chunks when possible for efficiency
        bytes_left = num_bytes
        bits_left = length
        byte_index = 0
        
        while bytes_left > 0:
            if bytes_left >= 4 and bits_left >= 32:
                # Process 32 bits at a time
                chunk_bits = 32
                chunk_bytes = 4
                
                # Extract TMS and TDI data (little-endian)
                tms = struct.unpack('<I', buffer[byte_index:byte_index + 4])[0]
                tdi = struct.unpack('<I', buffer[byte_index + num_bytes:byte_index + num_bytes + 4])[0]
                
                # Perform JTAG transfer
                tdo = self.gpio_transfer(chunk_bits, tms, tdi)
                
                # Store result (little-endian)
                result[byte_index:byte_index + 4] = struct.pack('<I', tdo)
                
                if self.verbose:
                    self.logger.debug(f"LEN: 0x{chunk_bits:08x}")
                    self.logger.debug(f"TMS: 0x{tms:08x}")
                    self.logger.debug(f"TDI: 0x{tdi:08x}")
                    self.logger.debug(f"TDO: 0x{tdo:08x}")
                
                bytes_left -= chunk_bytes
                bits_left -= chunk_bits
                byte_index += chunk_bytes
                
            else:
                # Process remaining bits
                chunk_bytes = bytes_left
                chunk_bits = bits_left
                
                # Extract TMS and TDI data
                tms_bytes = buffer[byte_index:byte_index + chunk_bytes]
                tdi_bytes = buffer[byte_index + num_bytes:byte_index + num_bytes + chunk_bytes]
                
                # Convert to integers (pad with zeros if needed)
                tms_padded = tms_bytes + b'\x00' * (4 - len(tms_bytes))
                tdi_padded = tdi_bytes + b'\x00' * (4 - len(tdi_bytes))
                
                tms = struct.unpack('<I', tms_padded)[0]
                tdi = struct.unpack('<I', tdi_padded)[0]
                
                # Perform JTAG transfer
                tdo = self.gpio_transfer(chunk_bits, tms, tdi)
                
                # Store result
                tdo_bytes = struct.pack('<I', tdo)[:chunk_bytes]
                result[byte_index:byte_index + chunk_bytes] = tdo_bytes
                
                if self.verbose:
                    self.logger.debug(f"LEN: 0x{chunk_bits:08x}")
                    self.logger.debug(f"TMS: 0x{tms:08x}")
                    self.logger.debug(f"TDI: 0x{tdi:08x}")
                    self.logger.debug(f"TDO: 0x{tdo:08x}")
                
                bytes_left = 0
        
        # Reset JTAG state after transfer
        self.gpio_write(0, 1, 0)
        
        return bytes(result)
    
    def safe_read(self, conn: socket.socket, length: int) -> Optional[bytes]:
        """
        Safely read exact number of bytes from socket
        
        Args:
            conn: Socket connection
            length: Number of bytes to read
            
        Returns:
            Bytes read, or None if connection closed/error
        """
        data = b''
        while len(data) < length:
            if not self.running:
                return None
                
            try:
                chunk = conn.recv(length - len(data))
                if not chunk:
                    # Connection closed by client
                    return None
                data += chunk
            except socket.timeout:
                continue
            except Exception as e:
                self.logger.error(f"Socket read error: {e}")
                return None
        
        return data
    
    def handle_client(self, conn: socket.socket, addr: tuple):
        """
        Handle client connection and XVC protocol
        
        Args:
            conn: Client socket connection
            addr: Client address tuple
        """
        if self.verbose:
            self.logger.info(f"Connection accepted from {addr}")
        
        try:
            # Set socket timeout for non-blocking behavior
            conn.settimeout(1.0)
            
            # Enable TCP_NODELAY for lower latency
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            
            while self.running:
                # Read command prefix (2 bytes)
                cmd_prefix = self.safe_read(conn, 2)
                if not cmd_prefix:
                    break
                
                if cmd_prefix == b'ge':
                    # getinfo command
                    remaining = self.safe_read(conn, 6)  # 'tinfo:'
                    if not remaining:
                        break
                    
                    response = self.handle_getinfo()
                    conn.sendall(response)
                    
                elif cmd_prefix == b'se':
                    # settck command  
                    remaining = self.safe_read(conn, 9)  # 'ttck:' + 4 bytes
                    if not remaining:
                        break
                    
                    period_data = remaining[5:]  # Last 4 bytes
                    response = self.handle_settck(period_data)
                    conn.sendall(response)
                    
                elif cmd_prefix == b'sh':
                    # shift command
                    remaining = self.safe_read(conn, 4)  # 'ift:'
                    if not remaining:
                        break
                    
                    # Read length (4 bytes, little-endian)
                    length_data = self.safe_read(conn, 4)
                    if not length_data:
                        break
                    
                    length = struct.unpack('<I', length_data)[0]
                    
                    # Calculate buffer size needed
                    num_bytes = (length + 7) // 8
                    buffer_size = num_bytes * 2  # TMS + TDI vectors
                    
                    if buffer_size > 4096:  # Sanity check
                        self.logger.error(f"Buffer size too large: {buffer_size}")
                        break
                    
                    # Read TMS and TDI data
                    buffer = self.safe_read(conn, buffer_size)
                    if not buffer:
                        break
                    
                    # Process shift operation
                    response = self.handle_shift(length, buffer)
                    conn.sendall(response)
                    
                else:
                    self.logger.error(f"Invalid command prefix: {cmd_prefix}")
                    break
                    
        except Exception as e:
            self.logger.error(f"Error handling client {addr}: {e}")
        finally:
            try:
                conn.close()
            except:
                pass
            if self.verbose:
                self.logger.info(f"Connection closed: {addr}")
    
    def signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        self.logger.info(f"Received signal {signum}, shutting down...")
        self.running = False
    
    def start_server(self):
        """Start the XVC TCP server"""
        # Initialize GPIO
        if not self.init_gpio():
            self.logger.error("Failed to initialize GPIO")
            return 1
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        
        try:
            # Create server socket
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind(('', self.port))
            self.server_socket.listen(1)
            self.server_socket.settimeout(1.0)  # For non-blocking accept
            
            self.logger.info(f"XVC server listening on port {self.port}")
            if self.verbose:
                self.logger.info("GPIO Configuration:")
                self.logger.info(f"  TCK: GPIO{self.tck_pin}")
                self.logger.info(f"  TMS: GPIO{self.tms_pin}")
                self.logger.info(f"  TDI: GPIO{self.tdi_pin}")
                self.logger.info(f"  TDO: GPIO{self.tdo_pin}")
                self.logger.info(f"  JTAG Delay: {self.jtag_delay}")
                self.logger.info("Use Ctrl+C to stop the server")
            
            # Main server loop
            while self.running:
                try:
                    conn, addr = self.server_socket.accept()
                    self.handle_client(conn, addr)
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.running:
                        self.logger.error(f"Accept error: {e}")
                    break
                    
        except Exception as e:
            self.logger.error(f"Server error: {e}")
            return 1
        finally:
            self.cleanup()
        
        return 0
    
    def cleanup(self):
        """Clean up resources"""
        self.running = False
        
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
        
        self.cleanup_gpio()
        
        if self.verbose:
            self.logger.info("Cleanup completed")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Xilinx Virtual Cable Server for Raspberry Pi (Python Version)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
GPIO Pin Configuration:
  Default: TMS=GPIO25, TDI=GPIO10, TCK=GPIO11, TDO=GPIO9

Examples:
  %(prog)s                          # Use default configuration
  %(prog)s -v                       # Verbose mode
  %(prog)s -p 2543 -d 100           # Custom port and delay
        """
    )
    
    parser.add_argument('-v', '--verbose', action='store_true',
                       help='Enable verbose output')
    parser.add_argument('-d', '--delay', type=int, default=XVCServer.DEFAULT_DELAY,
                       help=f'JTAG delay (default: {XVCServer.DEFAULT_DELAY})')
    parser.add_argument('-p', '--port', type=int, default=XVCServer.DEFAULT_PORT,
                       help=f'TCP port (default: {XVCServer.DEFAULT_PORT})')
    parser.add_argument('-c', '--tck', type=int, default=XVCServer.DEFAULT_TCK_PIN,
                       help=f'TCK GPIO pin (default: {XVCServer.DEFAULT_TCK_PIN})')
    parser.add_argument('-m', '--tms', type=int, default=XVCServer.DEFAULT_TMS_PIN,
                       help=f'TMS GPIO pin (default: {XVCServer.DEFAULT_TMS_PIN})')
    parser.add_argument('-i', '--tdi', type=int, default=XVCServer.DEFAULT_TDI_PIN,
                       help=f'TDI GPIO pin (default: {XVCServer.DEFAULT_TDI_PIN})')
    parser.add_argument('-o', '--tdo', type=int, default=XVCServer.DEFAULT_TDO_PIN,
                       help=f'TDO GPIO pin (default: {XVCServer.DEFAULT_TDO_PIN})')
    
    args = parser.parse_args()
    
    # Validate GPIO pins
    if any(pin < 0 for pin in [args.tck, args.tms, args.tdi, args.tdo]):
        print("Error: Invalid GPIO pin numbers", file=sys.stderr)
        return 1
    
    # Validate port
    if args.port <= 0 or args.port > 65535:
        print("Error: Invalid port number", file=sys.stderr)
        return 1
    
    # Create and start server
    server = XVCServer(
        tck_pin=args.tck,
        tms_pin=args.tms, 
        tdi_pin=args.tdi,
        tdo_pin=args.tdo,
        port=args.port,
        delay=args.delay,
        verbose=args.verbose
    )
    
    return server.start_server()


if __name__ == '__main__':
    sys.exit(main())
