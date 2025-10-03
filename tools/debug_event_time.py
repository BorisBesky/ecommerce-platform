"""Utility script to inspect parsed event_time values for clickstream events."""

from pyflink.table import StreamTableEnvironment
from pyflink.datastream import StreamExecutionEnvironment

CATALOG_NAME = "nessie"
DATABASE_NAME = "demo"
NESSIE_URI = "http://nessie.ecommerce-platform.svc.cluster.local:19120/api/v1"
WAREHOUSE_PATH = "s3a://warehouse"
MINIO_ENDPOINT = "http://minio.ecommerce-platform.svc.cluster.local:9000"
STAGED_CLICKSTREAM_JSON = "s3a://warehouse/data/clickstream/individual/"


def main() -> None:
    env = StreamExecutionEnvironment.get_execution_environment()
    t_env = StreamTableEnvironment.create(env)

    cfg = t_env.get_config().get_configuration()
    cfg.set_string("fs.s3a.endpoint", MINIO_ENDPOINT)
    cfg.set_string("fs.s3a.access.key", "minioadmin")
    cfg.set_string("fs.s3a.secret.key", "minioadmin")
    cfg.set_string("fs.s3a.path.style.access", "true")
    cfg.set_string("fs.s3a.ssl.enabled", "false")
    cfg.set_string("fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")

    # Create filesystem table in default catalog
    t_env.execute_sql(
        f"""
        CREATE TEMPORARY TABLE IF NOT EXISTS clickstream_events (
            user_id STRING,
            product_id STRING,
            event_type STRING,
            `timestamp` STRING
        ) WITH (
            'connector' = 'filesystem',
            'path' = '{STAGED_CLICKSTREAM_JSON}',
            'format' = 'json',
            'json.ignore-parse-errors' = 'true',
            'source.monitor-interval' = '1000'
        )
        """
    )

    query = (
        "SELECT `timestamp`, "
        "TO_TIMESTAMP(SUBSTRING(REPLACE(`timestamp`, 'T', ' '), 1, 23)) AS parsed_ts "
        "FROM clickstream_events LIMIT 20"
    )

    print("Collecting sample rows...")
    t_env.sql_query(query).execute().print()


if __name__ == "__main__":
    main()