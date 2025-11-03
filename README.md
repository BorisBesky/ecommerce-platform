# E-commerce Platform - Cloud-Native Data Analytics

A comprehensive e-commerce analytics platform built with modern cloud-native technologies, deployed on Kubernetes. This platform provides real-time fraud detection, batch ETL processing, and machine learning capabilities for recommendation systems.

## Architecture

The platform consists of the following components:

- **MinIO**: S3-compatible object storage for data lake
- **Nessie**: Git-like catalog for Apache Iceberg tables
- **Apache Spark**: Distributed batch processing engine
- **Apache Flink**: Stream processing for real-time analytics
- **Ray**: Distributed machine learning and AI workloads
- **Apache Iceberg**: Open table format for analytics
- **Clickstream Analytics Service**: FastAPI + React service for simulation orchestration, fraud analytics, and Ray job management

## Quick Start

### Prerequisites

Before deploying the platform, ensure you have:

1. **Kubernetes Cluster** (v1.24+)
   - Local: Docker Desktop with Kubernetes, minikube, or kind
   - Cloud: EKS, GKE, AKS, or any managed Kubernetes service
   - Minimum resources: 8 CPU cores, 16GB RAM

2. **kubectl** configured to access your cluster
   ```bash
   kubectl cluster-info
   ```

3. **Helm** (v3.0+) for installing operators
   ```bash
   helm version
   ```

4. **Git** for cloning the repository
   ```bash
   git clone https://github.com/BorisBesky/ecommerce-platform.git
   cd ecommerce-platform
   ```

### Installation

#### Step 0: Check Prerequisites

Verify your environment meets all requirements:

```bash
cd k8s
./check-prerequisites.sh
```

#### Step 1: Deploy the Platform

Run the complete deployment script:

```bash
cd k8s
./deploy-all.sh
```

This script will:
- Create the `ecommerce-platform` namespace
- Deploy MinIO, Nessie, Spark, and Flink clusters
- Install KubeRay operator (if not present)
- Create necessary ConfigMaps for applications
- Deploy Ray cluster for ML workloads

#### Step 2: Validate Deployment

Verify all services are running correctly:

```bash
./validate-deployment.sh
```

#### Step 3: Submit Sample Jobs

Test the platform with sample workloads:

```bash
./submit-sample-jobs.sh
```

### Access Services

After deployment, access the web interfaces using port forwarding:

```bash
# MinIO Console (admin interface)
kubectl port-forward svc/minio 9001:9001 -n ecommerce-platform
# Open http://localhost:9001 (admin/minioadmin)

# MinIO API
kubectl port-forward svc/minio 9000:9000 -n ecommerce-platform

# Nessie API
kubectl port-forward svc/nessie 19120:19120 -n ecommerce-platform

# Spark Master UI
kubectl port-forward svc/spark-master 8080:8080 -n ecommerce-platform
# Open http://localhost:8080

# Flink JobManager UI
kubectl port-forward svc/flink-jobmanager 8081:8081 -n ecommerce-platform
# Open http://localhost:8081
```

## Platform Components

### Data Storage Layer

#### MinIO (Object Storage)
- **Purpose**: S3-compatible storage for data lake
- **Storage**: Raw data files, processed datasets, ML models
- **Access**: REST API and web console
- **Configuration**: 10GB persistent volume

#### Nessie (Data Catalog)
- **Purpose**: Version control for Iceberg tables
- **Features**: Git-like branching, time travel, metadata management
- **Storage**: 5GB persistent volume for metadata

### Processing Layer

#### Apache Spark Cluster
- **Master**: 1 replica, 2 CPU, 8GB RAM
- **Workers**: 2 replicas, 2 CPU each, 6GB RAM each
- **Use Cases**: Batch ETL, data transformations, analytics
- **Applications**: User/product data processing

#### Apache Flink Cluster
- **JobManager**: 1 replica, 1 CPU, 2GB RAM
- **TaskManagers**: 2 replicas, 2 CPU each, 3GB RAM each
- **Use Cases**: Stream processing, real-time analytics
- **Applications**: Fraud detection, real-time recommendations

#### Ray Cluster
- **Head Node**: 1 replica, 2 CPU, 8GB RAM
- **Workers**: 2-3 replicas (auto-scaling), 2 CPU each, 6GB RAM each
- **Use Cases**: Distributed ML training, hyperparameter tuning
- **Applications**: Recommendation model training

#### Clickstream Analytics Service
- **Backend**: Python FastAPI (`services/clickstream/backend`)
- **Frontend**: React + TypeScript dashboard (`services/clickstream/ui`)
- **Use Cases**: Clickstream simulation, fraud metrics, recommendation accuracy insights, Ray orchestration
- **Deployment**: See `k8s/clickstream-service/`

## Development Guide

### Project Structure

```
ecommerce-platform/
├── k8s/                          # Kubernetes manifests and scripts
│   ├── *.yaml                    # Service deployments
│   ├── check-prerequisites.sh   # Prerequisites validation
│   ├── deploy-all.sh            # Main deployment script
│   ├── validate-deployment.sh   # Validation tests
│   ├── submit-sample-jobs.sh    # Sample workload submission
│   ├── cleanup-deployment.sh    # Cleanup script
│   ├── spark-apps/              # Kubernetes-optimized Spark apps
│   ├── flink-apps/              # Kubernetes-optimized Flink apps
│   └── ray-apps/                # Kubernetes-optimized Ray apps
├── spark-apps/                  # Legacy Spark applications (reference)
├── flink-apps/                  # Legacy Flink applications (reference)
├── ray-apps/                    # Legacy Ray applications (reference)
├── legacy/                      # Old Docker Compose deployment files
├── data/                        # Sample data files
├── tools/                       # Utility scripts
└── README.md                    # This file
```

### Adding New Applications

#### Spark Applications

1. Create your Spark application in `k8s/spark-apps/`
2. Update the Spark ConfigMap:
   ```bash
   kubectl create configmap spark-apps --from-file=k8s/spark-apps/ -n ecommerce-platform --dry-run=client -o yaml | kubectl apply -f -
   ```
3. Submit the job:

    ```bash
    # Ensure ConfigMap is (re)applied first if you changed files:
    kubectl create configmap spark-apps --from-file=k8s/spark-apps/ -n ecommerce-platform \
       --dry-run=client -o yaml | kubectl apply -f -

    # Exec into the existing master pod (it already mounts /apps with your scripts):
    MASTER_POD=$(kubectl get pods -l app=spark,component=master -n ecommerce-platform -o jsonpath='{.items[0].metadata.name}')
    kubectl exec -n ecommerce-platform -it "$MASTER_POD" -- \
       spark-submit --master spark://spark-master:7077 /apps/your-app.py
    ```

   If you see `ClassNotFoundException` for Iceberg or Nessie and you didn't yet restart the master after updating `spark.yaml`, delete the master pod so it picks up the `spark.jars.packages` setting:

   ```bash
   kubectl delete pod -l app=spark,component=master -n ecommerce-platform
   ```

   (It will be recreated automatically.)

#### Flink Applications

1. Create your Flink application in `k8s/flink-apps/`
2. Update the Flink ConfigMap:
   ```bash
   kubectl create configmap flink-apps --from-file=k8s/flink-apps/ -n ecommerce-platform --dry-run=client -o yaml | kubectl apply -f -
   ```
3. Submit the job:
   ```bash
   FLINK_POD=$(kubectl get pods -l app=flink,component=jobmanager -n ecommerce-platform -o jsonpath='{.items[0].metadata.name}')
   kubectl exec $FLINK_POD -n ecommerce-platform -- flink run -py /apps/your-app.py
   ```

#### Ray Applications

1. Create your Ray application in `k8s/ray-apps/`
2. Create a RayJob manifest (use `k8s/ray.yaml` as template)
3. Apply the manifest:
   ```bash
   kubectl apply -f your-ray-job.yaml
   ```

### Configuration Management

#### Environment Variables

All applications use environment variables for configuration:

- **MINIO_ENDPOINT**: `http://minio.ecommerce-platform.svc.cluster.local:9000`
- **NESSIE_URI**: `http://nessie.ecommerce-platform.svc.cluster.local:19120/api/v1`
- **WAREHOUSE_PATH**: `s3a://warehouse`
- **MINIO_ACCESS_KEY**: `minioadmin`
- **MINIO_SECRET_KEY**: `minioadmin`

#### Service Discovery

Services use Kubernetes DNS for discovery:

- `minio.ecommerce-platform.svc.cluster.local`
- `nessie.ecommerce-platform.svc.cluster.local`
- `spark-master.ecommerce-platform.svc.cluster.local`
- `flink-jobmanager.ecommerce-platform.svc.cluster.local`

## Testing

### Validation Tests

The platform includes comprehensive validation tests:

```bash
# Run all validation tests
./k8s/validate-deployment.sh

# Check specific service
kubectl get pods -l app=minio -n ecommerce-platform
kubectl get pods -l app=spark -n ecommerce-platform
kubectl get pods -l app=flink -n ecommerce-platform
```

### Sample Data and Jobs

Submit sample jobs to test the platform:

```bash
# Run sample ETL, streaming, and ML jobs
./k8s/submit-sample-jobs.sh

# Check job status
kubectl get pods -n ecommerce-platform
kubectl get rayjob -n ecommerce-platform
```

### Health Checks

All services include health checks:

- **MinIO**: HTTP health endpoint
- **Nessie**: API config endpoint
- **Spark**: Web UI availability
- **Flink**: Web UI and RPC connectivity
- **Ray**: Job deployment status

## 📈 Monitoring and Observability

### Built-in Monitoring

Access service dashboards:

1. **Spark Master UI**: Cluster health, job status, resource usage
2. **Flink JobManager UI**: Job graphs, metrics, checkpoints
3. **MinIO Console**: Storage usage, bucket management
4. **Ray Dashboard**: Task graphs, cluster resources (when port-forwarded)

### Resource Monitoring

```bash
# Check resource usage
kubectl top pods -n ecommerce-platform
kubectl top nodes

# Check events
kubectl get events -n ecommerce-platform --sort-by='.lastTimestamp'

# Check logs
kubectl logs -l app=spark,component=master -n ecommerce-platform
kubectl logs -l app=flink,component=jobmanager -n ecommerce-platform
```

## Troubleshooting

### Common Issues

#### Pod Startup Issues

```bash
# Check pod status
kubectl get pods -n ecommerce-platform

# Check pod logs
kubectl logs <pod-name> -n ecommerce-platform

# Describe pod for events
kubectl describe pod <pod-name> -n ecommerce-platform
```

#### Storage Issues

```bash
# Check persistent volumes
kubectl get pv,pvc -n ecommerce-platform

# Check MinIO connectivity
kubectl exec -it <minio-pod> -n ecommerce-platform -- mc ls local/
```

#### Network Issues

```bash
# Test service connectivity
kubectl run test-pod --image=curlimages/curl -n ecommerce-platform --rm -i --restart=Never -- \
  curl -s http://minio:9000/minio/health/live
```

#### Resource Constraints

```bash
# Check node resources
kubectl describe nodes

# Scale down if needed
kubectl scale deployment spark-worker --replicas=1 -n ecommerce-platform
kubectl scale deployment flink-taskmanager --replicas=1 -n ecommerce-platform
```

### Performance Tuning

#### Spark Configuration

Adjust Spark resources in `k8s/spark.yaml`:

- Increase `spark.executor.memory` for larger datasets
- Adjust `spark.executor.cores` based on node capacity
- Enable `spark.sql.adaptive.enabled` for query optimization

#### Flink Configuration

Modify Flink settings in `k8s/flink.yaml`:

- Adjust `taskmanager.numberOfTaskSlots` for parallelism
- Increase `taskmanager.memory.process.size` for complex jobs
- Tune `execution.checkpointing.interval` for fault tolerance

#### Ray Configuration

Scale Ray workers in `k8s/ray.yaml`:

- Adjust `minReplicas` and `maxReplicas` for auto-scaling
- Increase worker resources for large ML workloads
- Configure `rayStartParams` for specific use cases

## Security Considerations

### Network Security

- All services run within the `ecommerce-platform` namespace
- Communication uses Kubernetes DNS and ClusterIP services
- No external access by default (use port-forwarding)

### Secrets Management

For production deployments:

1. **Replace default credentials**:
   
   ```bash
   kubectl create secret generic minio-credentials \
     --from-literal=username=<your-username> \
     --from-literal=password=<your-password> \
     -n ecommerce-platform
   ```

2. **Use Kubernetes secrets** in deployments
3. **Enable TLS/SSL** for external access
4. **Implement RBAC** for fine-grained access control

### Data Security

- MinIO supports encryption at rest and in transit
- Iceberg tables support column-level encryption
- Use network policies to restrict pod-to-pod communication

## Production Deployment

### Resource Requirements

**Minimum Production Setup**:

- **Nodes**: 3 worker nodes, 4 CPU, 16GB RAM each
- **Storage**: 100GB+ for data, models, and logs
- **Network**: High bandwidth between nodes

**Recommended Production Setup**:

- **Nodes**: 5+ worker nodes, 8 CPU, 32GB RAM each
- **Storage**: 500GB+ NVMe SSD storage
- **Network**: 10Gbps+ inter-node connectivity

### High Availability

For production environments:

1. **Multiple replicas** for all components
2. **Pod anti-affinity** to spread across nodes
3. **Persistent volumes** with replication
4. **Backup strategies** for data and metadata

### Monitoring and Alerting

Integrate with monitoring systems:

1. **Prometheus** for metrics collection
2. **Grafana** for visualization
3. **AlertManager** for alerts
4. **ELK Stack** for log aggregation

### Auto-scaling

Configure auto-scaling:

1. **Horizontal Pod Autoscaler** for workers
2. **Vertical Pod Autoscaler** for resource optimization
3. **Cluster autoscaler** for node scaling

## Cleanup

To remove the entire platform:

```bash
# Clean up all resources
./k8s/cleanup-deployment.sh

# Optional: Remove KubeRay operator
helm uninstall kuberay-operator
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test with the validation scripts
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License. See LICENSE file for details.

## Support

For issues and questions:

1. Check the troubleshooting guide above
2. Review Kubernetes and application logs
3. Open an issue with detailed information:
   - Kubernetes version and distribution
   - Error messages and logs
   - Resource constraints
   - Steps to reproduce

## Roadmap

Future enhancements:

- [ ] **Multi-tenancy** support with namespaces
- [ ] **CI/CD pipelines** for application deployment
