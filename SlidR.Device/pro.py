from tkinter import Tk, ttk, Text, Label, Button, OptionMenu, StringVar, Checkbutton, BooleanVar, NORMAL, DISABLED
from tkinter import filedialog as fd
from typing import Callable
from enum import IntEnum
from PIL import Image
import serial
import threading
import time

class Command(IntEnum):
    PING = 0x01
    PONG = 0x02
    SET_CONFIG = 0x03
    GET_CONFIG = 0x04
    CONFIG_DATA = 0x05
    DEFAULT_CONFIG = 0x06
    UPLOAD_IMAGE_START = 0x07
    UPLOAD_IMAGE_DATA = 0x08
    UPLOAD_IMAGE_END = 0x09
    DOWNLOAD_IMAGE_START = 0x0A
    DOWNLOAD_IMAGE_DATA = 0x0B
    DOWNLOAD_IMAGE_END = 0x0C
    ACK = 0x0D
    SLIDER_VALUE = 0x0E
    SET_BACKLIGHT = 0x0F
    ERROR_CMD = 0x10
    GET_STATUS = 0x11
    STATUS_DATA = 0x12
    LOG_MESSAGE = 0x13

class ErrorCode(IntEnum):
    NONE = 0x00
    INVALID_COMMAND = 0x01
    INVALID_DATA = 0x02
    CHECKSUM_ERROR = 0x03
    FILE_ERROR = 0x04
    INVALID_CONFIG = 0x05
    BUFFER_OVERFLOW = 0x06
    TRANSFER_IN_PROGRESS = 0x07
    TRANSFER_TIMEOUT = 0x08

class Packet:
    command: Command
    length: int
    data: bytes
    checksum: bytes

class Serial:
    on_receive: Callable[[bytes], None] | None = None
    keep_alive: bool = False

    _last_send_time: float = 0.0

    def __init__(self, port: str, baudrate: int) -> None:
        self.serial = serial.Serial(port=port, baudrate=baudrate, timeout=1)
        threading.Thread(target=self._read_serial, daemon=True).start()
        threading.Thread(target=self._keep_alive, daemon=True).start()

    def _keep_alive(self) -> None:
        while True:
            time.sleep(1.0)
            if self.keep_alive and (time.time() - self._last_send_time) > 5.0:
                self.send(b'\xaa\x01\x00\x00\x01')

    def _read_serial(self) -> None:
        while True:
            if self.serial.in_waiting > 0:
                data = self.serial.read(1)
                if len(data) > 0 and self.on_receive:
                    self.on_receive(data)
            else:
                time.sleep(0.01)

    def send(self, data: bytes) -> None:
        self._last_send_time = time.time()
        self.serial.write(data)

    @staticmethod
    def checksum(data: bytes) -> bytes:
        cs: int = 0
        for b in data:
            cs ^= b
        return bytes([cs])



class Parser:
    on_packet: Callable[[Packet], None] | None = None
    _data: bytearray = bytearray()
    
    def feed(self, byte: bytes) -> None:
        self._data.extend(byte)
        if self.valid():
            if self.on_packet:
                packet = Packet()
                packet.command = Command(self._data[1])
                packet.length = self._data[2] | (self._data[3] << 8)
                packet.data = self._data[4:-1]
                packet.checksum = bytes([self._data[-1]])
                self.on_packet(packet)
            self._data = bytearray()

    def valid(self) -> bool:
        # [START][CMD][LEN_HIGH][LEN_LOW][?DATA?][CHK]
            
        if self._data[0] != 0xAA:
            self._data = bytearray()
            return False
        
        if len(self._data) < 5:
            return False

        length = self._data[2] | (self._data[3] << 8)
        # Total packet: START(1) + CMD(1) + LEN(2) + DATA(length) + CHK(1) = length + 5
        if len(self._data) < length + 5:
            return False

        my_cs = Serial.checksum(self._data[1:-1])
        msg_cs = self._data[-1]
        return int.from_bytes(my_cs) == msg_cs



class App:
    bytes_on_line = 16
    _ser = Serial(port="COM4", baudrate=115200)
    _parser = Parser()
    _additional_packet_receiver: Callable[[Packet], None] | None = None
    _waiting_for_ack: threading.Event | None = None

    def __init__(self, root):
        self.raw_in_label = Label(root, text="Raw Input")
        self.raw_in = Text(root, width=self.bytes_on_line * 3, state=DISABLED)
        self.char_in_label = Label(root, text="Character Input")
        self.char_in = Text(root, width=self.bytes_on_line, state=DISABLED)
        self.parsed_in_label = Label(root, text="Parsed Input")
        self.parsed_in = Text(root, width=60, state=DISABLED)

        self.cmd_select_label = Label(root, text="Command Select")
        self.selected_cmd = StringVar()
        self.cmd_select = OptionMenu(root, self.selected_cmd, *[f"{cmd.name} (0x{cmd.value:02X})" for cmd in Command])
        self.content_label = Label(root, text="Packet Content")
        self.content = Text(root, width=40, height=10)
        self.preview_btn = Button(root, text="Preview Packet", command=self.preview_packet)
        self.preview_text = Text(root, width=40, height=10)
        self.send_btn = Button(root, text="Send Packet", command=self.send_packet)

        self.keep_alive = BooleanVar()
        self.keep_alive_check = Checkbutton(root, text="Keep Alive", variable=self.keep_alive, command=self._update_keep_alive)
        self.send_cfg = Button(root, text="Send Config", command=self.send_config)
        self.send_img_frame = ttk.Frame(root)
        self.send_img_idx = ttk.Spinbox(self.send_img_frame, from_=0, to=4, width=10)
        self.send_img = Button(self.send_img_frame, text="Send Image", command=self.send_image)
        self.get_img_frame = ttk.Frame(root)
        self.get_img_idx = ttk.Spinbox(self.get_img_frame, from_=0, to=4, width=10)
        self.get_img_start = ttk.Button(self.get_img_frame, text="Get Image", command=self.get_image)

        self.raw_in_label.grid(row=0, column=0)
        self.raw_in.grid(row=1, column=0, rowspan=6, sticky='NS')

        self.char_in_label.grid(row=0, column=1)
        self.char_in.grid(row=1, column=1, rowspan=6, sticky='NS')

        self.parsed_in_label.grid(row=0, column=2)
        self.parsed_in.grid(row=1, column=2, rowspan=6, sticky='NS')

        self.cmd_select_label.grid(row=0, column=3)
        self.cmd_select.grid(row=1, column=3)

        self.content_label.grid(row=2, column=3)
        self.content.grid(row=3, column=3)

        self.preview_btn.grid(row=4, column=3)
        self.preview_text.grid(row=5, column=3)

        self.send_btn.grid(row=6, column=3)

        self.keep_alive_check.grid(row=7, column=0)
        self.send_cfg.grid(row=7, column=1)
        self.send_img_frame.grid(row=7, column=2)
        self.send_img_idx.pack(side='left', fill='x', expand=True)
        self.send_img.pack(side='right')

        self.get_img_frame.grid(row=7, column=3)
        self.get_img_idx.pack(side='left', fill='x', expand=True)
        self.get_img_start.pack(side='right')

        self._ser.on_receive = self._recv
        self._parser.on_packet = self._on_packet

    def _recv(self, data: bytes) -> None:
        self._parser.feed(data)
        if self._additional_packet_receiver:
            return
        
        self.raw_in.configure(state=NORMAL)
        self.char_in.configure(state=NORMAL)

        hex_byte = f"{data[0]:02X}"
        char_byte = chr(data[0]) if 32 <= data[0] <= 126 else ' '
        
        raw_content = self.raw_in.get("1.0", "end-1c")
        if raw_content == "":
            self.raw_in.insert("end", hex_byte)
            self.char_in.insert("end", char_byte)
        else:
            raw_last_line = self.raw_in.get("end-1l linestart", "end-1l lineend")
            bytes_on_last_line = (len(raw_last_line) + 1) // 3 if raw_last_line else 0
            
            if bytes_on_last_line >= self.bytes_on_line:
                self.raw_in.insert("end", "\n" + hex_byte)
                self.char_in.insert("end", "\n" + char_byte)
            else:
                if bytes_on_last_line > 0:
                    self.raw_in.insert("end", " " + hex_byte)
                else:
                    self.raw_in.insert("end", hex_byte)
                self.char_in.insert("end", char_byte)

            self.raw_in.see("end")
            self.char_in.see("end")

        self.raw_in.configure(state=DISABLED)
        self.char_in.configure(state=DISABLED)

    def _on_packet(self, packet: Packet) -> None:
        self.display_packet(packet)
        if self._additional_packet_receiver:
            self._additional_packet_receiver(packet)
        if self._waiting_for_ack:
            if packet.command == Command.ACK:
                self._waiting_for_ack.set()

    def display_packet(self, packet: Packet) -> None:
        self.parsed_in.configure(state=NORMAL)
        out = f"In: {packet.command.name} (0x{packet.command.value:02X})\n"
        if packet.length > 0:
            out += f"  Length: {packet.length}\n"

        if packet.command == Command.CONFIG_DATA:
            out += f"  Received config (V: {int.from_bytes(packet.data[0:4], byteorder='little')}):\n"
            out += f"    SPI Clk: {int.from_bytes(packet.data[4].to_bytes(1), signed=True)}\n"
            out += f"    SPI Dta: {int.from_bytes(packet.data[5].to_bytes(1), signed=True)}\n"
            out += f"    TFT Dc: {packet.data[6]}\n"
            out += f"    TFT Bl: {packet.data[7]}\n"
            out += f"    SPI Freq: {int.from_bytes(packet.data[8:12], byteorder='little')}\n"
            out += f"    Baudrate: {int.from_bytes(packet.data[12:16], byteorder='little')}\n"
            out += f"    Wait for serial: {packet.data[16] != 0}\n"
            out += f"    Do sleep: {packet.data[17] != 0}\n"
            out += f"    Segments: {packet.data[18]}\n"
            pos = 19
            while pos < packet.length - 1:
                tft_cs = packet.data[pos]
                pot = packet.data[pos + 1]
                min_val = int.from_bytes(packet.data[pos + 2:pos + 4], byteorder='little')
                max_val = int.from_bytes(packet.data[pos + 4:pos + 6], byteorder='little')
                out += f"      TFT Cs: {tft_cs}, Pot: {pot}, Min: {min_val}, Max: {max_val}\n"
                pos += 6

        elif packet.command == Command.SLIDER_VALUE:
            out += f"  Slider Change:\n"
            out += f"    Segment [{packet.data[0]}] Value: {int.from_bytes(packet.data[1:3], byteorder='little')}\n"

        elif packet.command == Command.ERROR_CMD:
            error_code = ErrorCode(packet.data[0])
            out += f"  Error Code: {error_code.name} (0x{error_code.value:02X})\n"

        elif packet.command == Command.STATUS_DATA:
            awake = packet.data[0] != 0
            backlight = packet.data[1]
            segs = packet.data[2]
            out += f"  Awake: {awake}\n"
            out += f"  Backlight: {backlight}\n"
            out += f"  Segments: {segs}\n"

        elif packet.command == Command.LOG_MESSAGE:
            message = packet.data.decode('utf-8', errors='ignore')
            out += f"  Log Message: {message}\n"

        self.parsed_in.insert("end", out + "\n")
        self.parsed_in.see("end")
        self.parsed_in.configure(state=DISABLED)

    def _update_keep_alive(self) -> None:
        self._ser.keep_alive = self.keep_alive.get()

    def preview_packet(self) -> None:
        cmd = self.selected_cmd.get().split(' ')[0]
        cmd_value = Command[cmd].value
        content_text = self.content.get("1.0", "end").strip()
        content_bytes = bytes.fromhex(content_text.replace(" ", "").replace("\n", ""))
        length = len(content_bytes)
        length_bytes = length.to_bytes(2, byteorder='little')

        packet = bytearray()
        packet.append(0xAA)
        packet.append(cmd_value)
        packet.extend(length_bytes)
        packet.extend(content_bytes)
        checksum_byte = Serial.checksum(packet[1:])
        packet.extend(checksum_byte)

        preview_hex = ' '.join(f"{b:02X}" for b in packet)
        self.preview_text.delete("1.0", "end")
        self.preview_text.insert("1.0", preview_hex)

    def send_packet(self) -> None:
        packet = bytearray()
        text = self.preview_text.get("1.0", "end").strip()
        for byte_str in text.split():
            packet.append(int(byte_str, 16))

        self._ser.send(bytes(packet))

    def send_config(self) -> None:
        config_file = fd.askopenfilename(title="Select Config File", filetypes=[("Binary files", "*.bin"), ("All Files", "*.*")])
        if not config_file:
            return

        with open(config_file, "rb") as f:
            config_data = f.read()
            length = len(config_data)
            length_bytes = length.to_bytes(2, byteorder='little')
            packet = bytearray()
            packet.append(0xAA)
            packet.append(Command.SET_CONFIG.value)
            packet.extend(length_bytes)
            packet.extend(config_data)
            checksum_byte = Serial.checksum(packet[1:])
            packet.extend(checksum_byte)
            self._ser.send(bytes(packet))

    def get_image(self) -> None:
        index = self.get_img_idx.get()
        if not index:
            print("Please specify an index.")
            return

        threading.Thread(target=self._download_image, args=(index,), daemon=True).start()

    def send_image(self) -> None:
        # Open file dialog to select image
        image_file = fd.askopenfilename(
            title="Select Image File",
            filetypes=[
                ("Image files", "*.png *.jpg *.jpeg *.bmp *.gif"),
                ("All Files", "*.*")
            ]
        )
        if not image_file:
            return

        try:
            # Load and resize image to 128x128
            img_size = 128
            img = Image.open(image_file)
            img = img.resize((img_size, img_size), Image.Resampling.LANCZOS)
            img = img.convert("RGB")
            
            # Convert to RGB565 format
            img_size_b = img_size.to_bytes(2, byteorder='little')
            rgb565_data = bytearray()
            rgb565_data.extend(img_size_b)
            rgb565_data.extend(img_size_b)
            pixels = img.load()
            for y in range(img_size):
                for x in range(img_size):
                    r, g, b = pixels[x, y] # type: ignore
                    # Convert 8-bit RGB to RGB565
                    r5 = (r >> 3) & 0x1F
                    g6 = (g >> 2) & 0x3F
                    b5 = (b >> 3) & 0x1F
                    rgb565 = (r5 << 11) | (g6 << 5) | b5
                    # Store as big-endian (MSB first)
                    rgb565_data.append((rgb565 >> 8) & 0xFF)
                    rgb565_data.append(rgb565 & 0xFF)

            image_index = int(self.send_img_idx.get())
            threading.Thread(target=self._upload_image, args=(rgb565_data,image_index), daemon=True).start()
        except Exception as e:
            print(f"Error uploading image: {e}")

    def _download_image(self, index: int, timeout: float = 2.0) -> None:
        self._waiting_for_ack = threading.Event()
        self._send(Command.DOWNLOAD_IMAGE_START, index.to_bytes(1, byteorder='little'))
        if not self._waiting_for_ack.wait(timeout):
            print("Timeout waiting for ACK after DOWNLOAD_IMAGE_START")
            self._waiting_for_ack = None
            return
        self._waiting_for_ack = None

        last_data_time = time.time()
        end = False
        data = bytearray()
        def on_data_packet(packet: Packet) -> None:
            nonlocal data, last_data_time, end
            if packet.command == Command.DOWNLOAD_IMAGE_DATA:
                data.extend(packet.data)
                last_data_time = time.time()
            elif packet.command == Command.DOWNLOAD_IMAGE_END:
                end = True

        self._additional_packet_receiver = on_data_packet
        while not end:
            if (time.time() - last_data_time) > timeout:
                print("Timeout waiting for image data")
                self._additional_packet_receiver = None
                return
            time.sleep(0.1)
        self._additional_packet_receiver = None

        with open(f"./img{index}.bin", "w+b") as f:
            f.write(data)

    def _upload_image(self, pixels: bytearray, image_index: int, timeout: float = 2.0) -> None:
        total_size = len(pixels)
        # Send UPLOAD_IMAGE_START
        size_bytes = total_size.to_bytes(4, byteorder='little')
        self._send(Command.UPLOAD_IMAGE_START, image_index.to_bytes(1, byteorder='little') + size_bytes)
        self._waiting_for_ack = threading.Event()
        if not self._waiting_for_ack.wait(timeout):
            print("Timeout waiting for ACK after UPLOAD_IMAGE_START")
            self._waiting_for_ack = None
            return
        
        # Send image data in chunks
        chunk_size = 4000
        offset = 0
        while offset < total_size:
            chunk = pixels[offset:offset + chunk_size]
            self._send(Command.UPLOAD_IMAGE_DATA, chunk)
            self._waiting_for_ack = threading.Event()
            offset += len(chunk)
            print(f"Sent {offset}/{total_size} bytes")
            if not self._waiting_for_ack.wait(timeout):
                print("Timeout waiting for ACK after UPLOAD_IMAGE_DATA")
                self._waiting_for_ack = None
                return
            self._waiting_for_ack = None

        # Send UPLOAD_IMAGE_END
        self._send(Command.UPLOAD_IMAGE_END, b'')
        self._waiting_for_ack = threading.Event()
        if not self._waiting_for_ack.wait(timeout):
            print("Timeout waiting for ACK after UPLOAD_IMAGE_END")
            self._waiting_for_ack = None
            return
        self._waiting_for_ack = None

    def _send(self, command: Command, data: bytes) -> None:
        length = len(data)
        length_bytes = length.to_bytes(2, byteorder='little')
        
        packet = bytearray()
        packet.append(0xAA)
        packet.append(command.value)
        packet.extend(length_bytes)
        packet.extend(data)
        checksum_byte = Serial.checksum(packet[1:])
        packet.extend(checksum_byte)
        
        self._ser.send(bytes(packet))

if __name__== "__main__":
    root = Tk()
    app = App(root)
    root.mainloop()