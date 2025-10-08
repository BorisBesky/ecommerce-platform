#!/usr/bin/env python3
"""
Verification script to check if Ray cluster is properly configured for distributed training.
Run this after deploying the Ray cluster but before starting the training job.
"""

import ray
import sys

def main():
    """Verify Ray cluster setup for distributed training"""
    
    print("=" * 60)
    print("Ray Cluster Verification for Distributed Training")
    print("=" * 60)
    
    try:
        # Try to connect to Ray
        print("\n1. Connecting to Ray cluster...")
        ctx = ray.init(address="auto", ignore_reinit_error=True)
        print(f"   ✓ Connected to Ray cluster")
        print(f"   Dashboard: {ctx.address_info.get('webui_url', 'N/A')}")
        
        # Check cluster resources
        print("\n2. Checking cluster resources...")
        resources = ray.cluster_resources()
        print(f"   Total CPUs: {resources.get('CPU', 0)}")
        print(f"   Total Memory: {resources.get('memory', 0) / (1024**3):.2f} GB")
        print(f"   Total GPUs: {resources.get('GPU', 0)}")
        
        # Check available resources
        available = ray.available_resources()
        print(f"\n3. Available resources:")
        print(f"   Available CPUs: {available.get('CPU', 0)}")
        print(f"   Available Memory: {available.get('memory', 0) / (1024**3):.2f} GB")
        
        # Check nodes
        print("\n4. Checking cluster nodes...")
        nodes = ray.nodes()
        print(f"   Total nodes: {len(nodes)}")
        
        alive_nodes = [n for n in nodes if n['Alive']]
        print(f"   Alive nodes: {len(alive_nodes)}")
        
        for i, node in enumerate(alive_nodes):
            node_type = "Head" if "node:__internal_head__" in node.get('Resources', {}) else "Worker"
            print(f"\n   Node {i+1} ({node_type}):")
            print(f"     - Node ID: {node['NodeID'][:16]}...")
            print(f"     - Address: {node['NodeManagerAddress']}")
            print(f"     - Resources: CPU={node['Resources'].get('CPU', 0)}, Memory={node['Resources'].get('memory', 0) / (1024**3):.2f} GB")
        
        # Estimate workers for training
        total_cpus = resources.get('CPU', 0)
        worker_count = max(1, int(total_cpus) - 1)  # Reserve 1 for head
        
        print("\n5. Training configuration estimate:")
        print(f"   Recommended workers: {worker_count}")
        print(f"   Expected parallelism: {worker_count}x")
        
        # Test remote function execution
        print("\n6. Testing remote function execution...")
        
        @ray.remote
        def test_remote():
            import socket
            return socket.gethostname()
        
        # Launch test tasks
        futures = [test_remote.remote() for _ in range(worker_count)]
        hostnames = ray.get(futures)
        
        unique_hosts = set(hostnames)
        print(f"   ✓ Successfully executed {len(futures)} remote tasks")
        print(f"   Tasks ran on {len(unique_hosts)} unique hosts:")
        for host in unique_hosts:
            count = hostnames.count(host)
            print(f"     - {host}: {count} task(s)")
        
        # Final assessment
        print("\n" + "=" * 60)
        if len(alive_nodes) >= 2:
            print("✓ READY: Cluster has multiple nodes for distributed training")
            if len(unique_hosts) >= 2:
                print("✓ VERIFIED: Tasks are being distributed across nodes")
            else:
                print("⚠ WARNING: All tasks ran on same node")
                print("  This might indicate scheduling issues")
        else:
            print("⚠ WARNING: Only 1 node detected")
            print("  Distributed training will have limited parallelism")
        print("=" * 60)
        
        return 0
        
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    finally:
        if ray.is_initialized():
            ray.shutdown()
            print("\nRay connection closed.")

if __name__ == "__main__":
    sys.exit(main())

