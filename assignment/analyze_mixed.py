#!/usr/bin/env python3
"""Explain the mixed-version captures without sending packets or modifying them."""
from pathlib import Path
import re
import tarfile


def captured_frame(archive, name):
    with tarfile.open(archive) as bundle:
        text = bundle.extractfile(f"logs/{name}").read().decode()
    chunks = []
    for line in text.splitlines():
        match = re.match(r"\s*0x[0-9a-f]+:\s+((?:[0-9a-f]{4}\s+|[0-9a-f]{2}\s+)+)", line)
        if match:
            chunks.append(bytes.fromhex(match.group(1)))
    if not chunks:
        raise ValueError(f"No captured frame in {archive}: {name}")
    return b"".join(chunks)


def checksum(data):
    if len(data) % 2:
        data += b"\x00"
    total = sum(int.from_bytes(data[i:i + 2], "big") for i in range(0, len(data), 2))
    while total >> 16:
        total = (total & 0xffff) + (total >> 16)
    return (~total) & 0xffff


def explain(archive):
    sent = captured_frame(archive, "h1cap.txt")
    received = captured_frame(archive, "h2cap.txt")
    print(f"\nArchive: {archive.name}")
    print(f"Captured lengths: h1={len(sent)}, h2={len(received)} bytes")
    print(f"Captured tunnel budgets: h1={sent[18]}, h2={received[18]}")
    print("Changed Ethernet-frame offsets (zero based):")
    for offset, (before, after) in enumerate(zip(sent, received)):
        if before != after:
            print(f"  {offset}: 0x{before:02x} -> 0x{after:02x}")

    # Model s1's chosen decrement, then s2's original fixed-width parser.
    predicted = bytearray(sent)
    predicted[18] -= 1
    old_ipv4 = bytearray(predicted[18:38])
    print(f"Old s2's 20-byte IPv4 view starts at offset 18: {old_ipv4.hex()}")
    print(f"Old view: version={old_ipv4[0] >> 4}, IHL={old_ipv4[0] & 15}")
    print(f"Old checksum field before update: 0x{int.from_bytes(old_ipv4[10:12], 'big'):04x}")
    old_ipv4[10:12] = b"\x00\x00"
    computed = checksum(old_ipv4)
    predicted[28:30] = computed.to_bytes(2, "big")
    print(f"Computed old checksum written at frame offsets 28-29: 0x{computed:04x}")
    print(f"Actual IPv4 protocol at frame offset 28: h1=0x{sent[28]:02x}, h2=0x{received[28]:02x}")
    print(f"Actual IPv4 checksum validation at h2 (0 means valid): 0x{checksum(received[19:39]):04x}")
    print(f"Decrement plus misaligned checksum model matches every captured byte: {predicted == received}")
    if predicted != received:
        raise ValueError("Observed capture does not match the proposed explanation")


if __name__ == "__main__":
    evidence = Path(__file__).resolve().parent / "evidence"
    for name in ("mixed-delivery-logs.tar.gz", "mixed-diagnostic-logs.tar.gz"):
        explain(evidence / name)
