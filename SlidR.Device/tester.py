#!/usr/bin/env python3
"""
PC-side controller for ESP32 Volume Control Device
Handles configuration, image uploads, and volume monitoring
"""

import serial
import struct
import time
from enum import IntEnum
from typing import Optional, Callable
from dataclasses import dataclass
from PIL import Image
import threading

class Command(IntEnum):
    PING = 0x01
    PONG = 0x02
    SET_CONFIG = 0x03
    GET_CONFIG = 0x04
    CONFIG_DATA = 0x05
    UPLOAD_IMAGE_START = 0x06
    UPLOAD_IMAGE_DATA = 0x07
    UPLOAD_IMAGE_END = 0x08
    IMAGE_ACK = 0x09
    SLIDER_VALUE = 0x0A
    SET_BACKLIGHT = 0x0B
    ERROR_CMD = 0x0C
    GET_STATUS = 0x0D
    STATUS_DATA = 0x0E
    LOG_MESSAGE = 0x0F

class ErrorCode(IntEnum):
    NONE = 0x00
    INVALID_COMMAND = 0x01
    CHECKSUM_ERROR = 0x02
    FILE_ERROR = 0x03
    INVALID_CONFIG = 0x04
    BUFFER_OVERFLOW = 0x05

@dataclass
class SegmentConfig:
    tft_cs_pin: int
    pot_pin: int
    pot_min_value: int
    pot_max_value: int
    image_path: str
    
@dataclass
class DeviceConfig:
    spi_clk_pin: int  # -1 for HW SPI
    spi_data_pin: int  # -1 for HW SPI
    tft_dc_pin: int
    tft_backlight_pin: int
    segments: list[SegmentConfig]

class VolumeControllerPC:
    START_BYTE = 0xAA
    MAX_DATA_CHUNK = 1024
    
    def __init__(self, port: str, baudrate: int = 115200):
        self.serial = serial.Serial(port, baudrate, timeout=1)
        self.running = False
        self.on_slider_change: Optional[Callable[[int, int], None]] = None
        self.on_error: Optional[Callable[[ErrorCode], None]] = None
        self._ping_thread = None
        
    def start(self):
        """Start the controller and ping thread"""
        self.running = True
        self._ping_thread = threading.Thread(target=self._ping_loop, daemon=True)
        self._ping_thread.start()
        
        # Start receive thread
        self._rx_thread = threading.Thread(target=self._receive_loop, daemon=True)
        self._rx_thread.start()
        
    def stop(self):
        """Stop the controller"""
        self.running = False
        if self._ping_thread:
            self._ping_thread.join(timeout=2)
        self.serial.close()
        
    def _calculate_checksum(self, data: bytes) -> int:
        """Calculate XOR checksum"""
        checksum = 0
        for byte in data:
            checksum ^= byte
        return checksum
        
    def _send_packet(self, command: Command, payload: bytes = b''):
        """Send a packet to the device"""
        length = len(payload)
        packet = bytearray()
        packet.append(self.START_BYTE)
        packet.append(command)
        packet.append((length >> 8) & 0xFF)
        packet.append(length & 0xFF)
        packet.extend(payload)
        
        # Calculate checksum (exclude START_BYTE)
        checksum = self._calculate_checksum(packet[1:])
        packet.append(checksum)
        
        self.serial.write(packet)
        self.serial.flush()
        
    def _receive_packet(self, timeout: float = 2.0) -> Optional[tuple[Command, bytes]]:
        """Receive a packet from the device"""
        start_time = time.time()
        
        # Wait for start byte
        while time.time() - start_time < timeout:
            if self.serial.in_waiting > 0:
                data = self.serial.read(1)
                if len(data) == 0:
                    continue
                byte = data[0]
                if byte == self.START_BYTE:
                    break
        else:
            return None
            
        # Read command and length
        header = self.serial.read(3)
        if len(header) < 3:
            return None
        
        try:
            command = Command(header[0])
        except ValueError:
            # Invalid command byte, probably garbage
            return None
            
        length = (header[1] << 8) | header[2]
        
        # Read payload and checksum
        data = self.serial.read(length + 1)
        if len(data) < length + 1:
            return None
            
        payload = data[:length]
        received_checksum = data[length]
        
        # Verify checksum
        check_data = header + payload
        calculated_checksum = self._calculate_checksum(check_data)
        
        if received_checksum != calculated_checksum:
            print(f"Checksum error: expected {calculated_checksum}, got {received_checksum}")
            return None
            
        return command, payload
        
    def _ping_loop(self):
        """Send periodic pings to keep device awake"""
        while self.running:
            self.ping()
            time.sleep(5)  # Ping every 5 seconds
            
    def _receive_loop(self):
        """Continuously receive packets"""
        while self.running:
            result = self._receive_packet(timeout=0.1)
            if result:
                command, payload = result
                self._handle_received_packet(command, payload)
                
    def _handle_received_packet(self, command: Command, payload: bytes):
        """Handle received packets"""
        if command == Command.LOG_MESSAGE:
            # Log message from ESP32
            try:
                log_msg = payload.decode('utf-8', errors='replace')
                print(f"[ESP32] {log_msg}")
            except:
                print(f"[ESP32] <binary data: {len(payload)} bytes>")
        elif command == Command.SLIDER_VALUE and len(payload) >= 2:
            segment_id = payload[0]
            volume = payload[1]
            if self.on_slider_change:
                self.on_slider_change(segment_id, volume)
        elif command == Command.ERROR_CMD and len(payload) >= 1:
            error = ErrorCode(payload[0])
            if self.on_error:
                self.on_error(error)
            print(f"Device error: {error.name}")
            
    def ping(self) -> bool:
        """Send ping and wait for pong"""
        self._send_packet(Command.PING)
        result = self._receive_packet(timeout=1.0)
        return result is not None and result[0] == Command.PONG
        
    def set_config(self, config: DeviceConfig) -> bool:
        """Upload configuration to device"""
        payload = bytearray()
        
        # Add global config
        payload.append(config.spi_clk_pin & 0xFF)
        payload.append(config.spi_data_pin & 0xFF)
        payload.append(config.tft_dc_pin)
        payload.append(config.tft_backlight_pin)
        payload.append(len(config.segments))
        
        # Add segment configs
        for seg in config.segments:
            payload.append(seg.tft_cs_pin)
            payload.append(seg.pot_pin)
            payload.append((seg.pot_min_value >> 8) & 0xFF)
            payload.append(seg.pot_min_value & 0xFF)
            payload.append((seg.pot_max_value >> 8) & 0xFF)
            payload.append(seg.pot_max_value & 0xFF)
            
            # Image path (32 bytes, null-padded)
            path_bytes = seg.image_path.encode('utf-8')[:31]
            path_bytes += b'\x00' * (32 - len(path_bytes))
            payload.extend(path_bytes)
        
        self._send_packet(Command.SET_CONFIG, bytes(payload))
        
        # Wait for ACK (longer timeout as this reinitializes hardware)
        result = self._receive_packet(timeout=5.0)
        return result is not None and result[0] == Command.IMAGE_ACK
        
    def get_config(self) -> Optional[DeviceConfig]:
        """Request configuration from device"""
        self._send_packet(Command.GET_CONFIG)
        result = self._receive_packet(timeout=2.0)
        
        if not result or result[0] != Command.CONFIG_DATA:
            return None
            
        data = result[1]
        offset = 0
        
        spi_clk = struct.unpack('b', data[offset:offset+1])[0]; offset += 1
        spi_data = struct.unpack('b', data[offset:offset+1])[0]; offset += 1
        tft_dc = data[offset]; offset += 1
        tft_backlight = data[offset]; offset += 1
        num_segments = data[offset]; offset += 1
        
        segments = []
        for _ in range(num_segments):
            cs_pin = data[offset]; offset += 1
            pot_pin = data[offset]; offset += 1
            pot_min = (data[offset] << 8) | data[offset+1]; offset += 2
            pot_max = (data[offset] << 8) | data[offset+1]; offset += 2
            img_path = data[offset:offset+32].split(b'\x00')[0].decode('utf-8'); offset += 32
            
            segments.append(SegmentConfig(cs_pin, pot_pin, pot_min, pot_max, img_path))
        
        return DeviceConfig(spi_clk, spi_data, tft_dc, tft_backlight, segments)
        
    def upload_image(self, image_path: str, device_path: str, 
                     max_size: tuple[int, int] = (128, 128)) -> bool:
        """Upload an image to the device
        
        Args:
            image_path: Path to image file on PC
            device_path: Path where image will be stored on device
            max_size: Maximum dimensions (width, height)
        
        Returns:
            True if upload successful
        """
        # Load and process image
        img = Image.open(image_path)
        img = img.resize(max_size, Image.Resampling.LANCZOS)
        img = img.convert('RGB')
        
        width, height = img.size
        
        # Convert to RGB565 format
        pixels = []
        for y in range(height):
            for x in range(width):
                r, g, b = img.getpixel((x, y))
                # Convert to RGB565
                r5 = (r >> 3) & 0x1F
                g6 = (g >> 2) & 0x3F
                b5 = (b >> 3) & 0x1F
                rgb565 = (r5 << 11) | (g6 << 5) | b5
                pixels.append(rgb565)
        
        # Create image data with header
        image_data = bytearray()
        image_data.extend(struct.pack('<HH', width, height))  # Width and height
        for pixel in pixels:
            image_data.extend(struct.pack('<H', pixel))
        
        # Send UPLOAD_IMAGE_START
        start_payload = bytearray()
        path_bytes = device_path.encode('utf-8')[:31]
        path_bytes += b'\x00' * (32 - len(path_bytes))
        start_payload.extend(path_bytes)
        start_payload.extend(struct.pack('<I', len(image_data)))
        
        self._send_packet(Command.UPLOAD_IMAGE_START, bytes(start_payload))
        result = self._receive_packet(timeout=2.0)
        if not result or result[0] != Command.IMAGE_ACK:
            print("Failed to start image upload")
            return False
        
        # Send image data in chunks
        offset = 0
        while offset < len(image_data):
            chunk_size = min(self.MAX_DATA_CHUNK, len(image_data) - offset)
            chunk = image_data[offset:offset + chunk_size]
            
            self._send_packet(Command.UPLOAD_IMAGE_DATA, bytes(chunk))
            result = self._receive_packet(timeout=2.0)
            if not result or result[0] != Command.IMAGE_ACK:
                print(f"Failed to upload chunk at offset {offset}")
                return False
            
            offset += chunk_size
            progress = (offset / len(image_data)) * 100
            print(f"Upload progress: {progress:.1f}%", end='\r')
        
        print()  # New line after progress
        
        # Send UPLOAD_IMAGE_END
        self._send_packet(Command.UPLOAD_IMAGE_END)
        result = self._receive_packet(timeout=2.0)
        if not result or result[0] != Command.IMAGE_ACK:
            print("Failed to finalize image upload")
            return False
        
        print(f"Successfully uploaded {device_path}")
        return True
        
    def set_backlight(self, brightness: int):
        """Set backlight brightness (0-255)"""
        brightness = max(0, min(255, brightness))
        self._send_packet(Command.SET_BACKLIGHT, bytes([brightness]))
        
    def get_status(self) -> Optional[dict]:
        """Get device status"""
        self._send_packet(Command.GET_STATUS)
        result = self._receive_packet(timeout=2.0)
        
        if not result or result[0] != Command.STATUS_DATA:
            return None
            
        data = result[1]
        return {
            'awake': bool(data[0]),
            'backlight': data[1],
            'num_segments': data[2]
        }


# Example usage
if __name__ == '__main__':
    # Initialize controller
    controller = VolumeControllerPC('COM4')  # Adjust port as needed
    
    # Set up slider change callback
    def on_slider_change(segment_id: int, volume: int):
        print(f"Segment {segment_id} volume changed to {volume}%")
        # Here you would integrate with your volume control library
        # e.g., pycaw for Windows, pulsectl for Linux
    
    controller.on_slider_change = on_slider_change
    
    # Start controller
    controller.start()
    
    # Test ping
    if controller.ping():
        print("Device connected!")
    else:
        print("Failed to connect to device")
        exit(1)
    
    # Create and upload configuration
    config = DeviceConfig(
        spi_clk_pin=-1,  # Use HW SPI
        spi_data_pin=-1,
        tft_dc_pin=5,
        tft_backlight_pin=39,
        segments=[
            SegmentConfig(
                tft_cs_pin=8,
                pot_pin=34,
                pot_min_value=0,
                pot_max_value=4095,
                image_path='/img0.bin'
            ),
            SegmentConfig(
                tft_cs_pin=6,
                pot_pin=35,
                pot_min_value=0,
                pot_max_value=4095,
                image_path='/img1.bin'
            ),
            SegmentConfig(
                tft_cs_pin=4,
                pot_pin=36,
                pot_min_value=0,
                pot_max_value=4095,
                image_path='/img2.bin'
            ),
            SegmentConfig(
                tft_cs_pin=2,
                pot_pin=37,
                pot_min_value=0,
                pot_max_value=4095,
                image_path='/img3.bin'
            ),
            SegmentConfig(
                tft_cs_pin=1,
                pot_pin=38,
                pot_min_value=0,
                pot_max_value=4095,
                image_path='/img4.bin'
            ),
        ]
    )
    
    print("Uploading configuration...")
    if controller.set_config(config):
        print("Configuration uploaded successfully!")
    else:
        print("Failed to upload configuration")
    
    # Upload images for each segment
    print("\nUploading images...")
    controller.upload_image('0.png', '/img0.bin', (128, 128))
    controller.upload_image('1.jpg', '/img1.bin', (128, 128))
    controller.upload_image('2.jpg', '/img2.bin', (128, 128))
    controller.upload_image('3.jpg', '/img3.bin', (128, 128))
    controller.upload_image('4.jpg', '/img4.bin', (128, 128))

    # Set backlight
    controller.set_backlight(200)
    
    # Get status
    status = controller.get_status()
    print(f"\nDevice status: {status}")
    
    # Keep running
    try:
        print("\nMonitoring sliders... Press Ctrl+C to exit")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping...")
        controller.stop()