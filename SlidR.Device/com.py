import serial
import struct
import time
from enum import IntEnum
from typing import Optional, Callable
from dataclasses import dataclass
from PIL import Image
import threading
import getpass

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

class Controller:
    bytes_on_line = 16

    def __init__(self) -> None:
        self.serial = serial.Serial(port="COM4", baudrate=115200, timeout=1)
        time.sleep(2)
        self.line = bytearray()
        threading.Thread(target=self.show, daemon=True).start()
        threading.Thread(target=self.poll, daemon=True).start()
        threading.Thread(target=self.input, daemon=True).start()

    def poll(self) -> None:
        while True:
            time.sleep(0.01)
            
            while self.serial.in_waiting > 0:
                byte = self.serial.read(1)
                if (len(byte) == 0):
                    break

                self.line.extend(byte)

    def show(self) -> None:
        while True:
            time.sleep(0.1)

            if len(self.line) > self.bytes_on_line:
                # Print the complete line before clearing it
                l = list[tuple[str, str]]()
                for i in range(0, self.bytes_on_line):
                    c = self.line[i]
                    l.append((hex(c)[2:].rjust(2, '0'), chr(c) if 32 <= c <= 126 else '.'))
                
                hex_part = ' '.join(f"{x[0]}" for x in l)
                ascii_part = ''.join(x[1] for x in l)
                print(f"\r{hex_part}    |{ascii_part}|")
                
                self.line = self.line[self.bytes_on_line:]

            elif len(self.line) > 0:
                # Show partial line
                l = list[tuple[str, str]]()
                for i in range(0, self.bytes_on_line):
                    if i < len(self.line):
                        c = self.line[i]
                        l.append((hex(c)[2:].rjust(2, '0'), chr(c) if 32 <= c <= 126 else '.'))
                    else:
                        l.append(('    ', ' '))

                hex_part = ' '.join(f"{x[0]}" for x in l)
                ascii_part = ''.join(x[1] for x in l)
                print(f"\r{hex_part}    |{ascii_part}|", end='', flush=True)

    def input(self) -> None:
        while True:
            try:
                hex_input = input("")
                
                if not hex_input.strip():
                    continue
                
                # Remove spaces and validate hex
                hex_clean = hex_input.replace(" ", "").replace("\n", "").strip()
                data = bytes.fromhex(hex_clean)
                self.serial.write(data)
                print(f"Sent: {' '.join(f'{b:02x}' for b in data)}")
            except ValueError as e:
                print(f"Invalid hex input: {e}")
            except Exception as e:
                print(f"Error: {e}")

if __name__ == "__main__":
    controller = Controller()
    while True:
        time.sleep(0.1)