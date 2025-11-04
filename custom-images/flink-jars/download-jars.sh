#!/bin/bash

set -e

cd "$(dirname "$0")"
jar_dir="$(pwd)"

# Download the required JAR files
echo "Downloading required JAR files for Flink Iceberg integration..."

if [ ! -f $jar_dir/iceberg-flink-runtime-1.17-1.4.3.jar ]; then
    curl -L -O https://repo1.maven.org/maven2/org/apache/iceberg/iceberg-flink-runtime-1.17/1.4.3/iceberg-flink-runtime-1.17-1.4.3.jar
fi

if [ ! -f $jar_dir/hadoop-common-3.3.4.jar ]; then
    curl -L -O https://repo1.maven.org/maven2/org/apache/hadoop/hadoop-common/3.3.4/hadoop-common-3.3.4.jar
fi

if [ ! -f $jar_dir/hadoop-aws-3.3.4.jar ]; then
    curl -L -O https://repo1.maven.org/maven2/org/apache/hadoop/hadoop-aws/3.3.4/hadoop-aws-3.3.4.jar
fi

if [ ! -f $jar_dir/hadoop-hdfs-client-3.3.4.jar ]; then
    curl -L -O https://repo1.maven.org/maven2/org/apache/hadoop/hadoop-hdfs-client/3.3.4/hadoop-hdfs-client-3.3.4.jar
fi

if [ ! -f aws-java-sdk-bundle-1.12.665.jar ]; then
    curl -L -O https://repo1.maven.org/maven2/com/amazonaws/aws-java-sdk-bundle/1.12.665/aws-java-sdk-bundle-1.12.665.jar
fi

# Rename files to expected names
mv iceberg-flink-runtime-1.17-1.4.3.jar iceberg-flink-runtime-1.4.3.jar

