# SlidR Serial Protocol

This document describes the binary framing, commands, and payloads used by the SlidR device when communicating over its USB CDC serial link.

## Physical Transport
- Default serial settings: 115200 baud, 8 data bits, no parity, 1 stop bit (8N1)
- Serial timeout on the device is 1000 ms; host implementations should use comparable read timeouts
- Device waits for the USB CDC port to become available before completing boot

## Packet Framing
All traffic (device ↔ host) uses the same packet structure:

```
| Byte | Field          | Notes                               |
|------|----------------|-------------------------------------|
|  0   | 0xAA           | Start byte                          |
|  1   | Command        | See command table                   |
|  2   | Length (LSB)   | Payload length in bytes (little-end)|
|  3   | Length (MSB)   |                                     |
| 4..N | Payload        | Optional; N = 4 + Length            |
| N+1  | Checksum       | XOR of command, length bytes, and payload
```

- Commands and payload bytes are encoded as unsigned 8-bit values unless specified otherwise
- Maximum payload size is `4096 - 4` bytes (device-side `MAX_PACKET_SIZE`)
- Packets with invalid checksums are discarded and answered with `ERROR_CMD` + `CHECKSUM_ERROR`

## Command Summary
| Command                | ID | Direction | Payload                                                                 | Expected Response |
|------------------------|----|-----------|-------------------------------------------------------------------------|-------------------|
| `PING`                 |0x01| D <- H    | None                                                                    | `PONG`            |
| `PONG`                 |0x02| D -> H    | None                                                                    | None              |
| `SET_CONFIG`           |0x03| D <- H    | Device configuration blob (binary, see firmware schema)                 | `ACK` or `ERROR_CMD` |
| `GET_CONFIG`           |0x04| D <- H    | None                                                                    | `CONFIG_DATA`     |
| `CONFIG_DATA`          |0x05| D -> H    | Device configuration blob                                               | None              |
| `DEFAULT_DONFIG`       |0x06| D <- H    | Load default configuration                                              | None              |
| `UPLOAD_IMAGE_START`   |0x07| D <- H    | Segment index (`uint8`), followed by total image bytes (`uint32`)       | `ACK` or `ERROR_CMD` |
| `UPLOAD_IMAGE_DATA`    |0x08| D <- H    | Raw image chunk (≤ 4092 bytes per packet)                               | `ACK` or `ERROR_CMD` |
| `UPLOAD_IMAGE_END`     |0x09| D <- H    | None                                                                    | `ACK`             |
| `DOWNLOAD_IMAGE_START` |0x0A| D <- H    | Segment index (`uint8`)                                                 | `ACK` then `DOWNLOAD_IMAGE_DATA` stream |
| `DOWNLOAD_IMAGE_DATA`  |0x0B| D -> H    | Raw file chunk                                                          | `ACK` (per chunk) |
| `DOWNLOAD_IMAGE_END`   |0x0C| D -> H    | None                                                                    | None              |
| `ACK`                  |0x0D| Both      | None                                                                    | None              |
| `SLIDER_VALUE`         |0x0E| D -> H    | `[segment_index:uint8][value:uint8]`                                    | None              |
| `SET_BACKLIGHT`        |0x0F| D <- H    | `[brightness:uint8]` (0=off, 255=max)                                   | None              |
| `ERROR_CMD`            |0x10| D -> H    | `[error_code:uint8]` (see table below)                                  | None              |
| `GET_STATUS`           |0x11| D <- H    | None                                                                    | `STATUS_DATA`     |
| `STATUS_DATA`          |0x12| D -> H    | `[awake:uint8][backlight:uint8][segment_count:uint8]`                   | None              |
| `LOG_MESSAGE`          |0x13| D -> H    | ASCII text (no terminator)                                              | Optional display  |
| `CHANGE_BAUDRATE`      |0x14| D <- H    | Planned; not yet implemented in firmware                                | `ERROR_CMD` (`INVALID_COMMAND`) |

## Payload Details
- Paths are ASCII strings copied into a 32-byte buffer; only the first 31 bytes are significant, last byte is forced to `\0`
- All multi-byte integers are little-endian and tightly packed
- Configuration payload layout is defined by the firmware's `ConfigLoader` and should be generated/parsed with matching logic
- `SLIDER_VALUE` messages are emitted whenever a segment detects a significant potentiometer change

## Error Codes (`ERROR_CMD` payload)
| Code                | Value | Description                     |
|---------------------|-------|---------------------------------|
| `NONE`              | 0x00  | No error                        |
| `INVALID_COMMAND`   | 0x01  | Command ID not recognized       |
| `CHECKSUM_ERROR`    | 0x02  | Packet checksum mismatch        |
| `FILE_ERROR`        | 0x03  | Filesystem or underlying IO issue|
| `INVALID_CONFIG`    | 0x04  | Config payload failed validation|
| `BUFFER_OVERFLOW`   | 0x05  | Payload length exceeded limits  |
| `TRANSFER_IN_PROGRESS` |0x06| New transfer attempted while another active |
| `TRANSFER_TIMEOUT`  | 0x07  | File transfer watchdog expired  |

## File Transfer Sequences

**Upload (host → device)**
1. Host sends `UPLOAD_IMAGE_START` with target path and total byte count
2. Device responds with `ACK` if it opened the temp file
3. Host streams chunks via `UPLOAD_IMAGE_DATA`; device acknowledges each chunk
4. After final chunk, host sends `UPLOAD_IMAGE_END`
5. Device finalizes the file (renames temp file to requested path), refreshes segment imagery, and responds with `ACK`

Failure at any step causes the device to close the temp file, emit `ERROR_CMD`, and leave the previous file untouched.

**Download (host ← device)**
1. Host sends `DOWNLOAD_IMAGE_START` with path
2. Device replies `ACK` and spawns a sender task
3. Device streams the file using repeated `DOWNLOAD_IMAGE_DATA` packets; host must return `ACK` for each
4. Device ends the transfer with `DOWNLOAD_IMAGE_END`

If the device cannot open the file it returns `ERROR_CMD` (`FILE_ERROR`) after logging a message.

## Connection Health
- Device records the timestamp of the last received packet to manage its sleep watchdog
- `PING` packets should be sent periodically (≤ every 5 s) when automatic sleep is enabled to keep the device awake
- When asleep the device disables backlight and segments; it wakes automatically upon any valid packet

## Logging
`LOG_MESSAGE` packets carry null-terminated strings that may include newline characters. Hosts should treat them as diagnostic output.

