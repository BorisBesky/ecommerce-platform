#!/usr/bin/env python3

import subprocess
import time

# Start port-forward
print("Starting port-forward to MinIO...")
proc = subprocess.Popen(
    ["kubectl", "port-forward", "svc/minio", "9000:9000", "-n", "ecommerce-platform"],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL
)

time.sleep(3)

try:
    # Use AWS CLI to upload if available, otherwise skip
    print("Checking if aws cli is available...")
    result = subprocess.run(["which", "aws"], capture_output=True, text=True)
    if result.returncode == 0:
        print("Uploading clickstream.json using aws s3 cp...")
        subprocess.run([
            "aws", "s3", "cp",
            "data/clickstream.json",
            "s3://warehouse/data/clickstream/clickstream.json",
            "--endpoint-url", "http://localhost:9000",
            "--no-sign-request"
        ])
    else:
        print("AWS CLI not available. Please install it or use another method.")
finally:
    print("Stopping port-forward...")
    proc.terminate()
    proc.wait()
