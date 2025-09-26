# E-commerce Platform Automation Makefile

PYTHON ?= python
K8S_NAMESPACE ?= ecommerce-platform
CLICKSTREAM_BUCKET ?= warehouse
CLICKSTREAM_KEY ?= data/clickstream.json
SEED ?= 42

.PHONY: help data-generate upload-data submit-sample-jobs ray-train flink-run spark-etl ray-portforward minio-portforward

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?##' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS":.*?## "}; {printf "\033[36m%-25s\033[0m %s\n", $$1, $$2}'

DATA_OUT_DIR ?= data

data-generate: ## Generate users, products, and clickstream (stable alias created)
	$(PYTHON) tools/generate_data.py all --seed $(SEED) --output-dir $(DATA_OUT_DIR)

MINIO_ENDPOINT ?= http://localhost:9000
MINIO_ACCESS_KEY ?= minioadmin
MINIO_SECRET_KEY ?= minioadmin

upload-data: ## Upload generated users, products, clickstream using Python uploader
	$(PYTHON) tools/upload-data-to-minio.py \
	  --endpoint $(MINIO_ENDPOINT) \
	  --access-key $(MINIO_ACCESS_KEY) \
	  --secret-key $(MINIO_SECRET_KEY) \
	  --bucket $(CLICKSTREAM_BUCKET) \
	  --data-dir $(DATA_OUT_DIR) \
	  --prefix data \
	  --include users products clickstream

submit-sample-jobs: ## Run the unified job submission script (Spark, Flink, Ray)
	bash k8s/submit-sample-jobs.sh

spark-etl: ## Run only Spark ETL part (requires data uploaded)
	kubectl run spark-job-submitter -n $(K8S_NAMESPACE) --image=bitnami/spark:3.5.0 --rm -i --restart=Never -- \
	  spark-submit \
	  --master spark://spark-master:7077 \
	  --deploy-mode client \
	  --conf spark.sql.catalog.nessie=org.apache.iceberg.spark.SparkCatalog \
	  --conf spark.sql.catalog.nessie.uri=http://nessie:19120/api/v1 \
	  --conf spark.sql.catalog.nessie.ref=main \
	  --conf spark.sql.catalog.nessie.authentication.type=NONE \
	  --conf spark.sql.catalog.nessie.catalog-impl=org.apache.iceberg.nessie.NessieCatalog \
	  --conf spark.sql.catalog.nessie.warehouse=s3a://warehouse \
	  --conf spark.sql.extensions="org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions" \
	  --conf spark.hadoop.fs.s3a.endpoint=http://minio:9000 \
	  --conf spark.hadoop.fs.s3a.access.key=minioadmin \
	  --conf spark.hadoop.fs.s3a.secret.key=minioadmin \
	  --conf spark.hadoop.fs.s3a.path.style.access=true \
	  --conf spark.hadoop.fs.s3a.impl=org.apache.hadoop.fs.s3a.S3AFileSystem \
	  /apps/batch_etl_k8s.py

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
