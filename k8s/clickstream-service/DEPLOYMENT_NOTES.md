# Clickstream Service Deployment Notes

## Image Pull Policy

The clickstream service deployments (both backend and frontend) are configured with `imagePullPolicy: Always` to ensure that the latest image is always pulled from the registry when using the `:latest` tag.

### Why Always?

When using the `:latest` tag, Kubernetes' default `IfNotPresent` policy can cause issues:
- Cached images on nodes may be used even after pushing new versions
- This leads to inconsistent deployments and outdated code running

### Configuration

Both deployment files have been updated:

```yaml
# k8s/clickstream-service/backend-deployment.yaml
# k8s/clickstream-service/frontend-deployment.yaml

spec:
  template:
    spec:
      containers:
        - name: clickstream-backend  # or clickstream-frontend
          image: ghcr.io/your-org/clickstream-backend:latest
          imagePullPolicy: Always  # ← Forces fresh pull on every deployment
```

### Impact

- **Pros:**
  - Always get the latest code when redeploying
  - No stale cache issues
  - Consistent behavior across all cluster nodes
  
- **Cons:**
  - Slightly slower pod startup (image pull required)
  - Increased registry bandwidth usage
  - For production, consider using versioned tags (e.g., `v1.2.3`) with `IfNotPresent` instead

### Best Practices

For different environments:

- **Development/Testing:** Use `:latest` with `imagePullPolicy: Always` (current setup)
- **Production:** Use semantic version tags (e.g., `:v1.2.3`) with `imagePullPolicy: IfNotPresent`

### Deployment Commands

After updating the manifest files, apply changes:

```bash
# Apply individual changes
kubectl apply -f k8s/clickstream-service/backend-deployment.yaml
kubectl apply -f k8s/clickstream-service/frontend-deployment.yaml

# Or use kustomize
kubectl apply -k k8s/clickstream-service/

# Or use the Makefile
make deploy-clickstream
```

### Verification

Check that the policy is applied:

```bash
# Backend
kubectl get deployment clickstream-backend -n ecommerce-platform \
  -o jsonpath='{.spec.template.spec.containers[0].imagePullPolicy}'

# Frontend  
kubectl get deployment clickstream-frontend -n ecommerce-platform \
  -o jsonpath='{.spec.template.spec.containers[0].imagePullPolicy}'
```

Both should return `Always`.

---

**Last Updated:** 2025-11-06  
**Changed By:** Automated deployment update to expose `/api/v1/data/generate` endpoint

