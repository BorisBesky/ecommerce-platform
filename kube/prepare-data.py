#!/usr/bin/env python3

"""
Prepare clickstream data for Ray training job.
This script merges all clickstream JSON files into a single file expected by the training script.
"""

import os
import json
import glob
from pathlib import Path

def prepare_clickstream_data():
    """Merge all clickstream files into a single file for training."""
    
    # Get the project root directory
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    data_dir = project_root / "data"
    
    print(f"📂 Looking for clickstream files in: {data_dir}")
    
    # Find all clickstream files
    clickstream_files = sorted(glob.glob(str(data_dir / "clickstream-*.json")))
    
    if not clickstream_files:
        print("❌ No clickstream files found!")
        return False
    
    print(f"📋 Found {len(clickstream_files)} clickstream files:")
    for file in clickstream_files:
        print(f"   - {os.path.basename(file)}")
    
    # Merge all files into one
    output_file = data_dir / "clickstream.json"
    print(f"🔄 Merging files into: {output_file}")
    
    total_records = 0
    with open(output_file, 'w') as outf:
        for file_path in clickstream_files:
            print(f"   Processing: {os.path.basename(file_path)}")
            file_records = 0
            try:
                with open(file_path, 'r') as inf:
                    for line in inf:
                        line = line.strip()
                        if line:  # Skip empty lines
                            # Validate JSON
                            json.loads(line)
                            outf.write(line + '\n')
                            file_records += 1
                            total_records += 1
                print(f"     ✅ {file_records} records")
            except Exception as e:
                print(f"     ❌ Error processing {file_path}: {e}")
                return False
    
    print(f"✅ Successfully merged {total_records} records into {output_file}")
    
    # Verify the output file
    print("🔍 Verifying merged file...")
    try:
        with open(output_file, 'r') as f:
            first_line = f.readline().strip()
            if first_line:
                sample_record = json.loads(first_line)
                print(f"   Sample record keys: {list(sample_record.keys())}")
                print(f"   Sample user_id: {sample_record.get('user_id')}")
                print(f"   Sample event_type: {sample_record.get('event_type')}")
            else:
                print("   ❌ Output file is empty!")
                return False
    except Exception as e:
        print(f"   ❌ Error verifying output file: {e}")
        return False
    
    print("✅ Data preparation completed successfully!")
    return True

if __name__ == "__main__":
    print("🚀 Preparing clickstream data for Ray training job...")
    success = prepare_clickstream_data()
    if not success:
        exit(1)
