#!/usr/bin/env python3
"""Hex2SysEx utility - Python 3 version.

usage:
  python hex2sysex.py \
    [--page_size 64] \
    [--delay 250] \
    [--syx] \
    [--device_id 127] \
    [--output_file path_to/firmware.syx] \
    path_to/firmware.hex
"""

import argparse
import os
import struct
import sys


def nibblize(data):
    """Convert bytes to nibble-encoded bytes for MIDI transmission."""
    result = bytearray()
    for byte in data:
        result.append((byte >> 4) & 0x0F)  # High nibble
        result.append(byte & 0x0F)         # Low nibble
    return bytes(result)


def calculate_checksum(data):
    """Calculate simple checksum (sum of all bytes)."""
    return sum(data) & 0xFF


def load_hex_file(filename):
    """Load Intel HEX file and return data as bytes."""
    data = bytearray()
    max_addr = 0
    
    try:
        with open(filename, 'r') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line or not line.startswith(':'):
                    continue
                    
                try:
                    # Parse Intel HEX line
                    byte_count = int(line[1:3], 16)
                    address = int(line[3:7], 16)
                    record_type = int(line[7:9], 16)
                    
                    if record_type == 0x00:  # Data record
                        # Extract data bytes
                        for i in range(byte_count):
                            byte_pos = 9 + i * 2
                            byte_val = int(line[byte_pos:byte_pos + 2], 16)
                            
                            # Extend data array if needed
                            while len(data) <= address + i:
                                data.append(0xFF)
                            
                            data[address + i] = byte_val
                            max_addr = max(max_addr, address + i)
                            
                    elif record_type == 0x01:  # End of file
                        break
                        
                except ValueError as e:
                    print(f"Error parsing line {line_num}: {e}")
                    return None
                    
    except FileNotFoundError:
        print(f"Error: File '{filename}' not found")
        return None
    except Exception as e:
        print(f"Error reading file: {e}")
        return None
    
    # Trim data to actual size
    return bytes(data[:max_addr + 1])


def create_sysex_message(manufacturer_id, device_id, command, data):
    """Create a complete SysEx message."""
    # Start with SysEx header
    message = bytearray([0xF0])  # SysEx start
    
    # Add manufacturer ID (3 bytes)
    message.extend(manufacturer_id)
    
    # Add device ID (2 bytes, big-endian)
    message.extend(struct.pack('>H', device_id))
    
    # Add command (2 bytes)
    message.extend(command)
    
    # Add nibblized data
    if data:
        nibbled_data = nibblize(data)
        message.extend(nibbled_data)
        
        # Add checksum
        checksum = calculate_checksum(data)
        message.extend(nibblize(bytes([checksum])))
    
    # End SysEx
    message.append(0xF7)
    
    return bytes(message)


def create_sysex_file(input_file, output_file, options):
    """Create SysEx file from Intel HEX file."""
    print(f"Loading HEX file: {input_file}")
    data = load_hex_file(input_file)
    
    if not data:
        print("Failed to load HEX file")
        return False
    
    print(f"Loaded {len(data)} bytes")
    
    # Prepare manufacturer ID
    manufacturer_id = bytes([0x00, 0x21, 0x02])  # Mutable Instruments
    
    # Commands
    update_command = bytes([0x7E, 0x00])  # Flash write command
    reset_command = bytes([0x7F, 0x00])   # Reset command
    
    sysex_data = bytearray()
    page_size = options.page_size
    
    print(f"Creating SysEx with page size: {page_size} bytes")
    
    # Process data in pages
    pages_written = 0
    for i in range(0, len(data), page_size):
        # Get page data
        page_data = data[i:i + page_size]
        
        # Pad page to full size
        if len(page_data) < page_size:
            page_data += bytes([0x00] * (page_size - len(page_data)))
        
        # Create SysEx message for this page
        sysex_msg = create_sysex_message(
            manufacturer_id,
            options.device_id,
            update_command,
            page_data
        )
        
        sysex_data.extend(sysex_msg)
        pages_written += 1
        
        if pages_written % 16 == 0:
            print(f"Processed {pages_written} pages...")
    
    # Add reset command
    reset_msg = create_sysex_message(
        manufacturer_id,
        options.device_id,
        reset_command,
        None  # No data for reset
    )
    sysex_data.extend(reset_msg)
    
    # Write output file
    try:
        with open(output_file, 'wb') as f:
            f.write(sysex_data)
        print(f"Created SysEx file: {output_file}")
        print(f"Total size: {len(sysex_data)} bytes")
        print(f"Pages written: {pages_written}")
        return True
    except Exception as e:
        print(f"Error writing output file: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description='Convert Intel HEX to MIDI SysEx for bootloader'
    )
    
    parser.add_argument(
        'input_file',
        help='Input Intel HEX file'
    )
    
    parser.add_argument(
        '-p', '--page_size',
        type=int,
        default=64,
        help='Flash page size in bytes (default: 64)'
    )
    
    parser.add_argument(
        '-d', '--device_id',
        type=int,
        default=127,
        help='Device ID for SysEx (default: 127)'
    )
    
    parser.add_argument(
        '-o', '--output_file',
        default=None,
        help='Output SysEx file (default: input.syx)'
    )
    
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Verbose output'
    )
    
    args = parser.parse_args()
    
    # Determine output filename
    if args.output_file:
        output_file = args.output_file
    else:
        base_name = os.path.splitext(args.input_file)[0]
        output_file = base_name + '.syx'
    
    # Validate inputs
    if not os.path.exists(args.input_file):
        print(f"Error: Input file '{args.input_file}' not found")
        sys.exit(1)
    
    if args.page_size <= 0 or args.page_size > 256:
        print("Error: Page size must be between 1 and 256")
        sys.exit(1)
    
    if args.device_id < 0 or args.device_id > 16383:
        print("Error: Device ID must be between 0 and 16383")
        sys.exit(1)
    
    # Create SysEx file
    success = create_sysex_file(args.input_file, output_file, args)
    
    if success:
        print("Conversion completed successfully!")
    else:
        print("Conversion failed!")
        sys.exit(1)


if __name__ == '__main__':
    main()