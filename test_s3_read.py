#!/usr/bin/env python3
"""
Minimal S3A read test to isolate the executor failure.
This script will attempt to read users.csv from MinIO and show the first few rows.
"""

from pyspark.sql import SparkSession

def main():
    spark = None
    try:
        print("Creating Spark session...")
        spark = SparkSession.builder.appName("S3ReadTest").getOrCreate()
        
        print("Testing basic Spark functionality...")
        test_df = spark.range(5)
        print(f"Range test count: {test_df.count()}")
        
        print("Reading users.csv from s3a://warehouse/data/...")
        df = spark.read.option("header", "true").csv("s3a://warehouse/data/users.csv")
        
        print(f"Row count: {df.count()}")
        print("Schema:")
        df.printSchema()
        print("First 5 rows:")
        df.show(5)
        
        print("Test completed successfully!")
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        raise
        
    finally:
        if spark:
            spark.stop()

if __name__ == "__main__":
    main()