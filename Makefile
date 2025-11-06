# E-commerce Platform Automation Makefile

PYTHON ?= python
K8S_NAMESPACE ?= ecommerce-platform
CLICKSTREAM_BUCKET ?= warehouse
CLICKSTREAM_KEY ?= data/clickstream.json
SEED ?= 42

.PHONY: help build-images push-images-local push-images-ghcr deploy-all data-generate upload-data upload-clickstream spark-etl flink-run ray-train ray-portforward minio-portforward spark-portforward flink-portforward all-portforward ray-serve-portforward ray-get-recommendations validate-clickstream test-clickstream test-clickstream-unit test-clickstream-data test-clickstream-data-e2e test-clickstream-data-manual

help: ## Show available targets
	@awk -F':.*?##' '/^[a-zA-Z_-]+:.*?##/ {printf "\033[36m%-25s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

DATA_OUT_DIR ?= data

build-images: ## Build custom Docker images for Spark and Flink with required JARs
	flink-jars/download-jars.sh
	docker build -f custom-images/Dockerfile.spark -t custom-spark .
	docker build -f custom-images/Dockerfile.flink -t custom-flink .

build-clickstream-images: ## Build custom Docker images for Clickstream backend and frontend
	docker build -t clickstream-backend -f services/clickstream/backend/Dockerfile .
	docker build -t clickstream-frontend services/clickstream/ui

push-images-cluster: ## Push custom Docker images to local registry
	docker tag custom-spark localhost:32000/custom-spark:latest
	docker push localhost:32000/custom-spark:latest
	docker tag custom-flink localhost:32000/custom-flink:latest
	docker push localhost:32000/custom-flink:latest
	docker tag clickstream-backend localhost:32000/clickstream-backend:latest
	docker push localhost:32000/clickstream-backend:latest
	docker tag clickstream-frontend localhost:32000/clickstream-frontend:latest
	docker push localhost:32000/clickstream-frontend:latest

push-images-local: ## Push custom Docker images to local registry
	docker tag custom-spark localhost:5000/custom-spark:latest
	docker push localhost:5000/custom-spark:latest
	docker tag custom-flink localhost:5000/custom-flink:latest
	docker push localhost:5000/custom-flink:latest	
	docker tag clickstream-backend localhost:5000/clickstream-backend:latest
	docker push localhost:5000/clickstream-backend:latest
	docker tag clickstream-frontend localhost:5000/clickstream-frontend:latest
	docker push localhost:5000/clickstream-frontend:latest

push-images-ghcr: ## Push custom Docker images to GitHub Container Registry
	docker tag custom-spark ghcr.io/borisbesky/custom-spark:latest
	docker push ghcr.io/borisbesky/custom-spark:latest
	docker tag custom-flink ghcr.io/borisbesky/custom-flink:latest
	docker push ghcr.io/borisbesky/custom-flink:latest
	docker tag clickstream-backend ghcr.io/borisbesky/clickstream-backend:latest
	docker push ghcr.io/borisbesky/clickstream-backend:latest
	docker tag clickstream-frontend ghcr.io/borisbesky/clickstream-frontend:latest
	docker push ghcr.io/borisbesky/clickstream-frontend:latest

deploy-all: ## Deploy all components using Helm charts
	k8s/deploy-all.sh clustervalidate 

data-generate: ## Generate users, products, and clickstream (stable alias created)
	$(PYTHON) tools/generate_data.py all --seed $(SEED) --output-dir $(DATA_OUT_DIR)

MINIO_ENDPOINT ?= http://localhost:9000
MINIO_ACCESS_KEY ?= minioadmin
MINIO_SECRET_KEY ?= minioadmin
NESSIE_ENDPOINT ?= http://localhost:19120/api/v1

upload-data: data-generate ## Upload generated users, products, clickstream using Python uploader
	$(PYTHON) tools/generate_data.py all \
	  --upload \
	  --seed $(SEED) \
	  --output-dir $(DATA_OUT_DIR) \
	  --minio-endpoint $(MINIO_ENDPOINT) \
	  --minio-access-key $(MINIO_ACCESS_KEY) \
	  --minio-secret-key $(MINIO_SECRET_KEY) \
	  --minio-bucket $(CLICKSTREAM_BUCKET)

upload-clickstream: ## Upload generated users, products, clickstream using Python uploader
	$(PYTHON) tools/generate_data.py clickstream \
	  --upload \
	  --seed $(SEED) \
	  --output-dir $(DATA_OUT_DIR) \
	  --minio-endpoint $(MINIO_ENDPOINT) \
	  --minio-access-key $(MINIO_ACCESS_KEY) \
	  --minio-secret-key $(MINIO_SECRET_KEY) \
	  --minio-bucket $(CLICKSTREAM_BUCKET)

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
	RAY_HEAD_POD=$$(kubectl get pods -n $(K8S_NAMESPACE) -l app=ray,component=head -o jsonpath='{.items[0].metadata.name}'); \
	if [ -n "$$RAY_HEAD_POD" ]; then \
	  kubectl port-forward -n $(K8S_NAMESPACE) $$RAY_HEAD_POD 8265:8265 \
	else \
	  echo "Ray head pod not found"; exit 1; \
	fi

minio-portforward: ## Port-forward MinIO console (9001) & API (9000)
	kubectl port-forward svc/minio -n $(K8S_NAMESPACE) 9000:9000 9001:9001

spark-portforward: ## Port-forward Spark master UI (8080) & worker UI (8081)
	kubectl port-forward svc/spark-master -n $(K8S_NAMESPACE) 8080:8080
	kubectl port-forward svc/spark-worker -n $(K8S_NAMESPACE) 8081:8081

flink-portforward: ## Port-forward Flink JobManager UI (8081)
	kubectl port-forward svc/flink-jobmanager -n $(K8S_NAMESPACE) 8082:8081

clickstream-portforward: ## Port-forward Clickstream backend (8000) & frontend (80)
	kubectl port-forward svc/clickstream-backend -n $(K8S_NAMESPACE) 8000:8000 &
	kubectl port-forward svc/clickstream-frontend -n $(K8S_NAMESPACE) 8001:80 &
	wait

all-portforward: ## Port-forward all UIs: MinIO (9000,9001), Spark (8080,8081), Flink (8082)
	$(MAKE) minio-portforward & \
	$(MAKE) spark-portforward & \
	$(MAKE) flink-portforward & \
	$(MAKE) ray-portforward & \
	wait

ray-serve-portforward: ## Port-forward Ray Serve UI (8000)
	kubectl port-forward svc/recommendation-service-serve-svc -n $(K8S_NAMESPACE) 8083:8000

ray-get-recommendations: ## Get recommendations from Ray Serve
	kubectl exec -n $(K8S_NAMESPACE) $(kubectl get pods -n $(K8S_NAMESPACE) -l app=ray,component=serve-head -o jsonpath='{.items[0].metadata.name}') -- bash -lc "curl -X POST http://localhost:8000/recommend -H 'Content-Type: application/json' -d '{\"user_id\": \"1\", \"n\": 5, \"exclude_products\": [\"prod1\", \"prod2\"]}'"

validate-clickstream: ## Validate clickstream service deployment and run e2e tests
	k8s/validate-clickstream.sh

test-clickstream-unit: ## Run clickstream unit tests
	cd services/clickstream/backend && $(PYTHON) -m pytest tests/test_health.py tests/test_api.py -v

test-clickstream: ## Run all clickstream tests (unit + e2e)
	cd services/clickstream/backend && \
	$(PYTHON) -m pytest tests/test_health.py tests/test_api.py tests/test_data_generation.py -v && \
	RUN_E2E_TESTS=true tests/run_e2e_tests.sh

test-clickstream-data: ## Run data generation unit tests (safe, mocked)
	cd services/clickstream/backend && $(PYTHON) -m pytest tests/test_data_generation.py -v

test-clickstream-data-e2e: ## Run data generation e2e tests (validates endpoint, doesn't trigger)
	cd services/clickstream/backend && \
	RUN_E2E_TESTS=true $(PYTHON) -m pytest tests/test_e2e.py::TestDataEndpoints -v

test-clickstream-data-manual: ## Run manual data generation tests (SLOW - actually generates data)
	@echo "⚠️  WARNING: This will actually generate and upload data to MinIO!"
	@echo "This test takes several minutes and should only be run in test/dev environments."
	@printf "Continue? [y/N] "; \
	read REPLY; \
	case "$$REPLY" in \
		[Yy]*) \
			cd services/clickstream/backend && \
			RUN_E2E_TESTS=true RUN_MANUAL_TESTS=true $(PYTHON) -m pytest tests/test_data_generation_manual.py -v; \
			;; \
		*) \
			echo "Cancelled."; \
			;; \
	esac