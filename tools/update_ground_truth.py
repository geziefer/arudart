#!/usr/bin/env python3
"""
Update existing ground truth JSON files with sector information.

Adds expected_ring and expected_number fields based on description.
"""

import json
from pathlib import Path


def parse_sector_from_description(description):
    """
    Parse sector information from description.
    
    Examples:
        "BS_20" or "BS20" -> {"ring": "BS", "number": 20}
        "T_20" or "T20" -> {"ring": "T", "number": 20}
        "SB_right" or "SB-up" -> {"ring": "SB", "number": 25}
        "DB" -> {"ring": "DB", "number": 50}
    
    Returns:
        dict with "ring" and "number", or None if can't parse
    """
    # Handle bulls first (special cases)
    if description.upper().startswith("SB"):
        return {"ring": "SB", "number": 25}
    elif description.upper() == "DB":
        return {"ring": "DB", "number": 50}
    
    # Try to extract ring and number
    # Support both "BS_20" and "BS20" formats
    import re
    match = re.match(r'^([A-Z]+)[-_]?(\d+)', description.upper())
    
    if match:
        ring = match.group(1)
        try:
            number = int(match.group(2))
            if 1 <= number <= 20:
                return {"ring": ring, "number": number}
        except ValueError:
            pass
    
    return None


def update_json_file(json_file):
    """Update a single JSON file with sector information."""
    with open(json_file, 'r') as f:
        data = json.load(f)
    
    # Check if already has sector info
    if "expected_ring" in data and "expected_number" in data:
        return False  # Already updated
    
    # Parse sector from description
    description = data.get("description", "")
    sector_info = parse_sector_from_description(description)
    
    if sector_info:
        data["expected_ring"] = sector_info["ring"]
        data["expected_number"] = sector_info["number"]
        
        # Write back to file
        with open(json_file, 'w') as f:
            json.dump(data, f, indent=2)
        
        return True  # Updated
    
    return False  # Could not parse


def main():
    recordings_dir = Path("data/recordings")
    
    if not recordings_dir.exists():
        print(f"Error: {recordings_dir} does not exist")
        return
    
    json_files = sorted(recordings_dir.glob("*.json"))
    
    if not json_files:
        print("No JSON files found in recordings directory")
        return
    
    print(f"Found {len(json_files)} JSON files")
    print("Updating with sector information...")
    print()
    
    updated_count = 0
    skipped_count = 0
    failed_count = 0
    
    for json_file in json_files:
        result = update_json_file(json_file)
        
        if result is True:
            # Load to show what was added
            with open(json_file, 'r') as f:
                data = json.load(f)
            print(f"✓ {json_file.name} -> [{data['expected_ring']}_{data['expected_number']}]")
            updated_count += 1
        elif result is False:
            # Check if already had sector info
            with open(json_file, 'r') as f:
                data = json.load(f)
            if "expected_ring" in data:
                print(f"- {json_file.name} (already has sector info)")
                skipped_count += 1
            else:
                print(f"✗ {json_file.name} (could not parse sector)")
                failed_count += 1
    
    print()
    print("=" * 60)
    print(f"Updated: {updated_count}")
    print(f"Skipped (already updated): {skipped_count}")
    print(f"Failed (could not parse): {failed_count}")
    print(f"Total: {len(json_files)}")


if __name__ == "__main__":
    main()
