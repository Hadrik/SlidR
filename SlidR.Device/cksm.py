input = bytes.fromhex(input().rstrip("\r\n"))
checksum = 0
for byte in input:
    checksum ^= byte
print(f"Checksum: 0x{checksum:02X}")