# E-commerce Platform Automation Makefile

PYTHON ?= python
K8S_NAMESPACE ?= ecommerce-platform
CLICKSTREAM_BUCKET ?= warehouse
CLICKSTREAM_KEY ?= data/clickstream.json
SEED ?= 42

.PHONY: help build-images push-images-local push-images-ghcr deploy-all data-generate upload-data submit-sample-jobs ray-train flink-run spark-etl ray-portforward minio-portforward

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?##' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS":.*?## "}; {printf "\033[36m%-25s\033[0m %s\n", $$1, $$2}'

DATA_OUT_DIR ?= data

build-images:
	docker build -f custom-images/Dockerfile.spark -t custom-spark .
	docker build -f custom-images/Dockerfile.flink -t custom-flink .

push-images-local:
	docker tag custom-spark localhost:5001/custom-spark:latest
	docker push localhost:5001/custom-spark:latest
	docker tag custom-flink localhost:5001/custom-flink:latest
	docker push localhost:5001/custom-flink:latest

push-images-ghcr:
	docker tag custom-spark ghcr.io/borisbesky/ecommerce-platform/spark:latest
	docker push ghcr.io/borisbesky/ecommerce-platform/spark:latest
	docker tag custom-flink ghcr.io/borisbesky/ecommerce-platform/flink:latest
	docker push ghcr.io/borisbesky/ecommerce-platform/flink:latest


deploy-all: ## Deploy all components using Helm charts
	k8s/deploy-all.sh $(K8S_NAMESPACE) $(CLICKSTREAM_BUCKET)

data-generate: ## Generate users, products, and clickstream (stable alias created)
	$(PYTHON) tools/generate_data.py all --seed $(SEED) --output-dir $(DATA_OUT_DIR)

MINIO_ENDPOINT ?= http://localhost:9000
MINIO_ACCESS_KEY ?= minioadmin
MINIO_SECRET_KEY ?= minioadmin
NESSIE_ENDPOINT ?= http://localhost:19120/api/v1

upload-data: ## Upload generated users, products, clickstream using Python uploader
	$(PYTHON) tools/upload-data-to-minio.py \
	  --endpoint $(MINIO_ENDPOINT) \
	  --access-key $(MINIO_ACCESS_KEY) \
	  --secret-key $(MINIO_SECRET_KEY) \
	  --bucket $(CLICKSTREAM_BUCKET) \
	  --data-dir $(DATA_OUT_DIR) \
	  --prefix data \
	  --include users products clickstream

upload-clickstream: ## Upload generated users, products, clickstream using Python uploader
	$(PYTHON) tools/upload-data-to-minio.py \
	  --endpoint $(MINIO_ENDPOINT) \
	  --access-key $(MINIO_ACCESS_KEY) \
	  --secret-key $(MINIO_SECRET_KEY) \
	  --bucket $(CLICKSTREAM_BUCKET) \
	  --data-dir $(DATA_OUT_DIR) \
	  --prefix data \
	  --include clickstream

submit-sample-jobs: ## Run the unified job submission script (Spark, Flink, Ray)
	bash k8s/submit-sample-jobs.sh

spark-etl: ## Run only Spark ETL part (requires data uploaded)
	SPARK_MASTER_POD=$$(kubectl get pods -l app=spark,component=master -n $(K8S_NAMESPACE) -o jsonpath='{.items[0].metadata.name}'); \
	if [ -n "$$SPARK_MASTER_POD" ]; then \
	  kubectl exec $$SPARK_MASTER_POD -n $(K8S_NAMESPACE) -- spark-submit --master local \
	  --packages org.apache.iceberg:iceberg-spark-runtime-3.5_2.12:1.4.3,org.projectnessie.nessie-integrations:nessie-spark-extensions-3.5_2.12:0.77.1,org.apache.hadoop:hadoop-aws:3.3.4 \
	  --conf spark.sql.catalog.nessie=org.apache.iceberg.spark.SparkCatalog \
	  --conf spark.sql.catalog.nessie.uri=${NESSIE_ENDPOINT} \
	  --conf spark.sql.catalog.nessie.ref=main \
	  --conf spark.sql.catalog.nessie.authentication.type=NONE \
	  --conf spark.sql.catalog.nessie.catalog-impl=org.apache.iceberg.nessie.NessieCatalog \
	  --conf spark.sql.catalog.nessie.warehouse=s3a://warehouse \
	  --conf spark.sql.extensions="org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions" \
	  --conf spark.hadoop.fs.s3a.endpoint=${MINIO_ENDPOINT} \
	  --conf spark.hadoop.fs.s3a.access.key=${MINIO_ACCESS_KEY} \
	  --conf spark.hadoop.fs.s3a.secret.key=${MINIO_SECRET_KEY} \
	  --conf spark.hadoop.fs.s3a.path.style.access=true \
	  --conf spark.hadoop.fs.s3a.impl=org.apache.hadoop.fs.s3a.S3AFileSystem \
	  /apps/batch_etl_k8s.py \
	else \
	  echo "Spark Master pod not found"; exit 1; \
	fi

flink-run: ## Submit Flink streaming job only
	FLINK_JOBMANAGER_POD=$$(kubectl get pods -l app=flink,component=jobmanager -n $(K8S_NAMESPACE) -o jsonpath='{.items[0].metadata.name}'); \
	if [ -n "$$FLINK_JOBMANAGER_POD" ]; then \
	  kubectl exec $$FLINK_JOBMANAGER_POD -n $(K8S_NAMESPACE) -- flink run --detached -py /apps/streaming_fraud_detection_k8s.py; \
	else \
	  echo "Flink JobManager pod not found"; exit 1; \
	fi

ray-train: ## Execute Ray training script on existing cluster head (requires head pod and script)
	RAY_HEAD_POD=$$(kubectl get pods -n $(K8S_NAMESPACE) -l app=ray,component=head -o jsonpath='{.items[0].metadata.name}'); \
	if [ -n "$$RAY_HEAD_POD" ]; then \
	  kubectl exec -n $(K8S_NAMESPACE) $$RAY_HEAD_POD -- bash -lc "python /apps/train_recommendation_model_k8s.py"; \
	else \
	  echo "Ray head pod not found"; exit 1; \
	fi

ray-portforward: ## Port-forward Ray dashboard (default 8265)
	kubectl port-forward svc/rayjob-recommendations-training-head-svc -n $(K8S_NAMESPACE) 8265:8265

minio-portforward: ## Port-forward MinIO console (9001) & API (9000)
	kubectl port-forward svc/minio -n $(K8S_NAMESPACE) 9000:9000 9001:9001

spark-portforward: ## Port-forward Spark master UI (8080) & worker UI (8081)
	kubectl port-forward svc/spark-master -n $(K8S_NAMESPACE) 8080:8080
	kubectl port-forward svc/spark-worker -n $(K8S_NAMESPACE) 8081:8081

flink-portforward: ## Port-forward Flink JobManager UI (8081)
	kubectl port-forward svc/flink-jobmanager -n $(K8S_NAMESPACE) 8082:8081

all-portforward: ## Port-forward all UIs: MinIO (9000,9001), Spark (8080,8081), Flink (8082)
	$(MAKE) minio-portforward & \
	$(MAKE) spark-portforward & \
	$(MAKE) flink-portforward & \
	$(MAKE) ray-portforward & \
	wait

