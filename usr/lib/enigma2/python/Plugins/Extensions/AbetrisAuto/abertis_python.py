#!/usr/bin/env python2
import sys
import re

def main():
    pid = sys.argv[1] if len(sys.argv) > 1 else "0"
    data = sys.stdin.buffer.read()
    
    # Extract TS packets from T2-MI stream (188-byte packets with 0x47 sync byte)
    output = bytearray()
    offset = 0
    
    while offset + 188 <= len(data):
        if data[offset] == 0x47:  # TS sync byte
            # Extract 188-byte TS packet
            ts_packet = data[offset:offset+188]
            # Validate packet (basic check: not all zeros, not all 0x47)
            if ts_packet.count(0x47) < 4 and ts_packet.count(0x00) < len(ts_packet):
                output.extend(ts_packet)
        offset += 1
    
    # Output clean TS to stdout
    sys.stdout.buffer.write(bytes(output))
    sys.stdout.buffer.flush()

if __name__ == "__main__":
    main()