import os
import math
import pickle
from typing import Dict, Tuple, Optional, List
import warnings

import numpy as np
import pandas as pd
import ray
import boto3
from botocore.config import Config

# --- Configuration ---
RAY_ADDRESS = os.environ.get("RAY_ADDRESS")
MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "http://minio.ecommerce-platform.svc.cluster.local:9000")
MINIO_ACCESS_KEY = os.environ.get("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.environ.get("MINIO_SECRET_KEY", "minioadmin")
S3_BUCKET = os.environ.get("CLICKSTREAM_S3_BUCKET", "warehouse")
OUTPUT_MODEL_KEY = os.environ.get("MODEL_OUTPUT_KEY", "models/prio_aware_recommendation_model.pkl")
CLICKSTREAM_S3_KEY = os.environ.get("CLICKSTREAM_S3_KEY", "data/clickstream.json")
NEW_CLICKSTREAM_S3_KEY = os.environ.get("NEW_CLICKSTREAM_S3_KEY", "data/clickstream_new.json")
INCREMENTAL_MODE = os.environ.get("INCREMENTAL_MODE", "false").lower() == "true"

# Sequence model hyperparameters
SEQUENCE_LENGTH = int(os.environ.get("SEQUENCE_LENGTH", "10"))  # Last K click events
TOP_N = int(os.environ.get("TOP_N", "10"))  # Number of recommendations to return
INCREMENTAL_EPOCHS = int(os.environ.get("INCREMENTAL_EPOCHS", "3"))  # Epochs for incremental training
INCREMENTAL_LR_DECAY = float(os.environ.get("INCREMENTAL_LR_DECAY", "0.5"))  # Learning rate decay for incremental

# ------------------------
# Ray Remote Function for Distributed Training
# ------------------------
@ray.remote
def train_sequence_chunk_remote(
    user_seqs: List[List[str]], 
    targets: List[str],
    user_embeddings: np.ndarray,
    item_embeddings: np.ndarray,
    sequence_weights: np.ndarray,
    user_map: Dict,
    item_map: Dict,
    lr: float, 
    reg: float, 
    chunk_id: int
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, float, int]:
    """
    Train on a chunk of sequences and return gradient updates.
    
    Args:
        user_seqs: List of click sequences (each sequence is list of product IDs)
        targets: Target products for each sequence
        user_embeddings: Current user embedding matrix
        item_embeddings: Current item embedding matrix
        sequence_weights: Weights for combining sequence items
        user_map: User ID to index mapping
        item_map: Item ID to index mapping
        lr: Learning rate
        reg: Regularization parameter
        chunk_id: Identifier for this chunk
        
    Returns:
        Tuple of (user_emb_updates, item_emb_updates, seq_weight_updates, loss, num_samples)
    """
    import socket
    node_name = socket.gethostname()
    print(f"[Worker {chunk_id} on {node_name}] Processing {len(user_seqs)} sequences...")
    
    local_user_emb = user_embeddings.copy()
    local_item_emb = item_embeddings.copy()
    local_seq_weights = sequence_weights.copy()
    
    total_loss = 0.0
    n_factors = user_embeddings.shape[1]
    
    for idx in range(len(user_seqs)):
        seq = user_seqs[idx]
        target = targets[idx]
        
        # Skip if target not in item map
        if target not in item_map:
            continue
            
        target_idx = item_map[target]
        
        # Encode sequence: weighted sum of item embeddings
        seq_embedding = np.zeros(n_factors)
        valid_items = 0
        
        for pos, item_id in enumerate(seq):
            if item_id in item_map:
                item_idx = item_map[item_id]
                # Apply position-based weighting (more recent = higher weight)
                weight = local_seq_weights[min(pos, len(local_seq_weights) - 1)]
                seq_embedding += weight * local_item_emb[item_idx]
                valid_items += 1
        
        if valid_items > 0:
            seq_embedding /= valid_items
        
        # Compute prediction and error
        target_emb = local_item_emb[target_idx]
        pred = float(np.dot(seq_embedding, target_emb))
        
        # Binary cross-entropy-like loss (sigmoid + BCE)
        pred = 1.0 / (1.0 + np.exp(-np.clip(pred, -10, 10)))
        err = 1.0 - pred  # Target is 1 (positive sample)
        total_loss += -np.log(max(pred, 1e-10))
        
        # Gradient updates
        grad = err * pred * (1 - pred)  # Derivative of sigmoid
        
        # Update target item embedding
        local_item_emb[target_idx] += lr * (grad * seq_embedding - reg * target_emb)
        
        # Update sequence item embeddings and weights
        for pos, item_id in enumerate(seq):
            if item_id in item_map:
                item_idx = item_map[item_id]
                weight = local_seq_weights[min(pos, len(local_seq_weights) - 1)]
                weight_idx = min(pos, len(local_seq_weights) - 1)
                
                # Update item embedding
                item_grad = (grad * weight * target_emb) / max(valid_items, 1)
                local_item_emb[item_idx] += lr * (item_grad - reg * local_item_emb[item_idx])
                
                # Update position weight
                weight_grad = grad * np.dot(local_item_emb[item_idx], target_emb) / max(valid_items, 1)
                local_seq_weights[weight_idx] += lr * (weight_grad - reg * local_seq_weights[weight_idx])
        
        # Clamp values
        local_item_emb[target_idx] = np.clip(local_item_emb[target_idx], -10, 10)
        local_seq_weights = np.clip(local_seq_weights, 0.01, 10)
    
    print(f"[Worker {chunk_id} on {node_name}] Completed. Loss: {total_loss:.4f}")
    return local_user_emb, local_item_emb, local_seq_weights, total_loss, len(user_seqs)


# ------------------------
# Prio-Clicks-Aware Sequence Recommender
# ------------------------
class PrioClicksAwareSequenceRecommender:
    """
    Recommendation model that uses sequence of last K clicks to predict top N items.
    Uses embeddings for users and items, with attention-like weights for sequence positions.
    """
    
    def __init__(self, n_factors=32, n_epochs=15, lr=0.01, reg=0.05, 
                 sequence_length=10, random_state=42, early_stopping=True, 
                 patience=3, min_delta=0.001):
        self.n_factors = n_factors
        self.n_epochs = n_epochs
        self.lr = lr
        self.reg = reg
        self.sequence_length = sequence_length
        self.random_state = random_state
        self.early_stopping = early_stopping
        self.patience = patience
        self.min_delta = min_delta
        
        self.user_embeddings = None
        self.item_embeddings = None
        self.sequence_weights = None  # Position-based weights for sequence
        self.user_map = {}
        self.item_map = {}
        self.user_inv = {}
        self.item_inv = {}
        self.training_history = []
    
    def _create_sequences(self, df: pd.DataFrame) -> Tuple[List[List[str]], List[str], List[str]]:
        """
        Create sequences of clicks for each user.
        
        Returns:
            Tuple of (sequences, targets, user_ids)
            - sequences: List of click sequences (each is list of product IDs)
            - targets: Next product in sequence
            - user_ids: User ID for each sequence
        """
        sequences = []
        targets = []
        user_ids = []
        
        # Sort by user and timestamp
        df_sorted = df.sort_values(['user_id', 'timestamp']).reset_index(drop=True)
        
        # Group by user
        for user_id, group in df_sorted.groupby('user_id'):
            products = group['product_id'].tolist()
            
            # Create sliding windows
            for i in range(len(products) - 1):
                # Get last K items before position i+1
                start_idx = max(0, i - self.sequence_length + 1)
                seq = products[start_idx:i+1]
                
                # Pad sequence if needed
                if len(seq) < self.sequence_length:
                    seq = ['<PAD>'] * (self.sequence_length - len(seq)) + seq
                
                target = products[i + 1]
                
                sequences.append(seq)
                targets.append(target)
                user_ids.append(user_id)
        
        return sequences, targets, user_ids
    
    def fit(self, df: pd.DataFrame) -> None:
        """Train the model on clickstream data."""
        print("Creating sequences from clickstream data...")
        sequences, targets, seq_user_ids = self._create_sequences(df)
        
        print(f"Created {len(sequences)} training sequences")
        
        # Build mappings
        users = df['user_id'].unique().tolist()
        items = df['product_id'].unique().tolist()
        items.append('<PAD>')  # Add padding token
        
        self.user_map = {u: i for i, u in enumerate(users)}
        self.item_map = {m: i for i, m in enumerate(items)}
        self.user_inv = {i: u for u, i in self.user_map.items()}
        self.item_inv = {i: m for m, i in self.item_map.items()}
        
        n_users = len(users)
        n_items = len(items)
        
        # Initialize embeddings
        rng = np.random.default_rng(self.random_state)
        self.user_embeddings = 0.1 * rng.standard_normal((n_users, self.n_factors))
        self.item_embeddings = 0.1 * rng.standard_normal((n_items, self.n_factors))
        
        # Initialize sequence position weights (decaying for older items)
        self.sequence_weights = np.array([1.0 / (i + 1) for i in range(self.sequence_length)])
        self.sequence_weights = self.sequence_weights / self.sequence_weights.sum()
        
        print(f"Initialized embeddings: {n_users} users, {n_items} items, {self.n_factors} factors")
        
        best_loss = float('inf')
        patience_counter = 0
        
        for epoch in range(self.n_epochs):
            # Shuffle sequences
            indices = rng.permutation(len(sequences))
            total_loss = 0.0
            
            for idx in indices:
                seq = sequences[idx]
                target = targets[idx]
                
                if target not in self.item_map:
                    continue
                
                target_idx = self.item_map[target]
                
                # Encode sequence
                seq_embedding = np.zeros(self.n_factors)
                valid_items = 0
                
                for pos, item_id in enumerate(seq):
                    if item_id in self.item_map:
                        item_idx = self.item_map[item_id]
                        weight = self.sequence_weights[pos]
                        seq_embedding += weight * self.item_embeddings[item_idx]
                        valid_items += 1
                
                if valid_items > 0:
                    seq_embedding /= valid_items
                
                # Compute prediction
                target_emb = self.item_embeddings[target_idx]
                pred = float(np.dot(seq_embedding, target_emb))
                pred = 1.0 / (1.0 + np.exp(-np.clip(pred, -10, 10)))
                
                loss = -np.log(max(pred, 1e-10))
                total_loss += loss
                
                # Gradient updates
                err = 1.0 - pred
                grad = err * pred * (1 - pred)
                
                # Update target item
                self.item_embeddings[target_idx] += self.lr * (grad * seq_embedding - self.reg * target_emb)
                self.item_embeddings[target_idx] = np.clip(self.item_embeddings[target_idx], -10, 10)
                
                # Update sequence items and weights
                for pos, item_id in enumerate(seq):
                    if item_id in self.item_map:
                        item_idx = self.item_map[item_id]
                        weight = self.sequence_weights[pos]
                        
                        item_grad = (grad * weight * target_emb) / max(valid_items, 1)
                        self.item_embeddings[item_idx] += self.lr * (item_grad - self.reg * self.item_embeddings[item_idx])
                        self.item_embeddings[item_idx] = np.clip(self.item_embeddings[item_idx], -10, 10)
                        
                        weight_grad = grad * np.dot(self.item_embeddings[item_idx], target_emb) / max(valid_items, 1)
                        self.sequence_weights[pos] += self.lr * (weight_grad - self.reg * self.sequence_weights[pos])
                
                self.sequence_weights = np.clip(self.sequence_weights, 0.01, 10)
            
            avg_loss = total_loss / max(len(sequences), 1)
            self.training_history.append(avg_loss)
            print(f"Epoch {epoch + 1}/{self.n_epochs} - Loss: {avg_loss:.4f}")
            
            # Early stopping
            if self.early_stopping:
                if avg_loss < best_loss - self.min_delta:
                    best_loss = avg_loss
                    patience_counter = 0
                else:
                    patience_counter += 1
                    if patience_counter >= self.patience:
                        print(f"Early stopping at epoch {epoch + 1}. Best loss: {best_loss:.4f}")
                        break
    
    def fit_distributed(self, df: pd.DataFrame, num_workers: int = 2) -> None:
        """Train the model using distributed Ray workers."""
        print("Creating sequences from clickstream data...")
        sequences, targets, seq_user_ids = self._create_sequences(df)
        
        print(f"Created {len(sequences)} training sequences")
        
        # Build mappings
        users = df['user_id'].unique().tolist()
        items = df['product_id'].unique().tolist()
        items.append('<PAD>')
        
        self.user_map = {u: i for i, u in enumerate(users)}
        self.item_map = {m: i for i, m in enumerate(items)}
        self.user_inv = {i: u for u, i in self.user_map.items()}
        self.item_inv = {i: m for m, i in self.item_map.items()}
        
        n_users = len(users)
        n_items = len(items)
        
        # Initialize embeddings
        rng = np.random.default_rng(self.random_state)
        self.user_embeddings = 0.1 * rng.standard_normal((n_users, self.n_factors))
        self.item_embeddings = 0.1 * rng.standard_normal((n_items, self.n_factors))
        self.sequence_weights = np.array([1.0 / (i + 1) for i in range(self.sequence_length)])
        self.sequence_weights = self.sequence_weights / self.sequence_weights.sum()
        
        print(f"Starting distributed training with {num_workers} workers...")
        
        best_loss = float('inf')
        patience_counter = 0
        
        for epoch in range(self.n_epochs):
            # Shuffle and split into chunks
            indices = rng.permutation(len(sequences))
            chunk_size = len(indices) // num_workers
            
            futures = []
            for w in range(num_workers):
                start_idx = w * chunk_size
                end_idx = start_idx + chunk_size if w < num_workers - 1 else len(indices)
                chunk_indices = indices[start_idx:end_idx]
                
                chunk_seqs = [sequences[i] for i in chunk_indices]
                chunk_targets = [targets[i] for i in chunk_indices]
                
                future = train_sequence_chunk_remote.remote(
                    chunk_seqs, chunk_targets,
                    self.user_embeddings.copy(),
                    self.item_embeddings.copy(),
                    self.sequence_weights.copy(),
                    self.user_map, self.item_map,
                    self.lr, self.reg, w
                )
                futures.append(future)
            
            # Aggregate results
            results = ray.get(futures)
            
            total_loss = 0.0
            agg_user_emb = np.zeros_like(self.user_embeddings)
            agg_item_emb = np.zeros_like(self.item_embeddings)
            agg_seq_weights = np.zeros_like(self.sequence_weights)
            
            for user_emb, item_emb, seq_weights, loss, n_samples in results:
                agg_user_emb += user_emb
                agg_item_emb += item_emb
                agg_seq_weights += seq_weights
                total_loss += loss
            
            self.user_embeddings = agg_user_emb / num_workers
            self.item_embeddings = agg_item_emb / num_workers
            self.sequence_weights = agg_seq_weights / num_workers
            
            avg_loss = total_loss / max(len(sequences), 1)
            self.training_history.append(avg_loss)
            print(f"Epoch {epoch + 1}/{self.n_epochs} - Loss: {avg_loss:.4f} (distributed)")
            
            # Early stopping
            if self.early_stopping:
                if avg_loss < best_loss - self.min_delta:
                    best_loss = avg_loss
                    patience_counter = 0
                else:
                    patience_counter += 1
                    if patience_counter >= self.patience:
                        print(f"Early stopping at epoch {epoch + 1}. Best loss: {best_loss:.4f}")
                        break
    
    def recommend_top_n(self, user_id: str, click_sequence: List[str], n: int = 10, 
                        exclude_items: Optional[set] = None) -> List[Tuple[str, float]]:
        """
        Generate top-N recommendations based on user ID and recent click sequence.
        
        Args:
            user_id: User identifier
            click_sequence: List of last K product IDs (recent clicks)
            n: Number of recommendations to return
            exclude_items: Set of items to exclude from recommendations
            
        Returns:
            List of (product_id, score) tuples sorted by score descending
        """
        if self.item_embeddings is None:
            raise RuntimeError("Model not fitted")
        
        exclude_items = exclude_items or set()
        
        # Pad/truncate sequence to expected length
        seq = click_sequence[-self.sequence_length:] if len(click_sequence) > self.sequence_length else click_sequence
        if len(seq) < self.sequence_length:
            seq = ['<PAD>'] * (self.sequence_length - len(seq)) + seq
        
        # Encode sequence
        seq_embedding = np.zeros(self.n_factors)
        valid_items = 0
        
        for pos, item_id in enumerate(seq):
            if item_id in self.item_map:
                item_idx = self.item_map[item_id]
                weight = self.sequence_weights[pos]
                seq_embedding += weight * self.item_embeddings[item_idx]
                valid_items += 1
        
        if valid_items > 0:
            seq_embedding /= valid_items
        
        # Score all items
        scores = []
        for item_id, item_idx in self.item_map.items():
            if item_id not in exclude_items and item_id != '<PAD>':
                score = float(np.dot(seq_embedding, self.item_embeddings[item_idx]))
                scores.append((item_id, score))
        
        # Sort and return top-N
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:n]
    
    def update_incremental(self, df: pd.DataFrame, n_epochs: int = 3, lr_decay: float = 0.5) -> None:
        """
        Incrementally update the model with new clickstream data.
        
        Args:
            df: New clickstream data (pandas DataFrame with user_id, product_id, timestamp)
            n_epochs: Number of epochs for incremental training (typically fewer than initial)
            lr_decay: Learning rate decay factor (e.g., 0.5 means use half the original learning rate)
        """
        if self.item_embeddings is None:
            raise RuntimeError("Model must be fitted before incremental updates. Call fit() or fit_distributed() first.")
        
        print(f"\n=== Incremental Model Update ===")
        print(f"Current model: {len(self.user_map)} users, {len(self.item_map)} items")
        
        # Create sequences from new data
        sequences, targets, seq_user_ids = self._create_sequences(df)
        print(f"Created {len(sequences)} new training sequences")
        
        # Identify new users and items
        new_users = set(df['user_id'].unique()) - set(self.user_map.keys())
        new_items = set(df['product_id'].unique()) - set(self.item_map.keys())
        
        print(f"Detected {len(new_users)} new users and {len(new_items)} new items")
        
        # Expand embeddings for new users and items
        if new_users:
            rng = np.random.default_rng(self.random_state)
            new_user_idx_start = len(self.user_map)
            
            for idx, user_id in enumerate(new_users):
                new_idx = new_user_idx_start + idx
                self.user_map[user_id] = new_idx
                self.user_inv[new_idx] = user_id
            
            # Expand user embeddings
            new_user_emb = 0.1 * rng.standard_normal((len(new_users), self.n_factors))
            self.user_embeddings = np.vstack([self.user_embeddings, new_user_emb])
            print(f"Expanded user embeddings: {self.user_embeddings.shape}")
        
        if new_items:
            rng = np.random.default_rng(self.random_state)
            new_item_idx_start = len(self.item_map)
            
            for idx, item_id in enumerate(new_items):
                new_idx = new_item_idx_start + idx
                self.item_map[item_id] = new_idx
                self.item_inv[new_idx] = item_id
            
            # Expand item embeddings
            new_item_emb = 0.1 * rng.standard_normal((len(new_items), self.n_factors))
            self.item_embeddings = np.vstack([self.item_embeddings, new_item_emb])
            print(f"Expanded item embeddings: {self.item_embeddings.shape}")
        
        # Use decayed learning rate for fine-tuning
        incremental_lr = self.lr * lr_decay
        print(f"Using learning rate: {incremental_lr} (original: {self.lr}, decay: {lr_decay})")
        
        # Incremental training
        rng = np.random.default_rng(self.random_state)
        for epoch in range(n_epochs):
            indices = rng.permutation(len(sequences))
            total_loss = 0.0
            
            for idx in indices:
                seq = sequences[idx]
                target = targets[idx]
                
                if target not in self.item_map:
                    continue
                
                target_idx = self.item_map[target]
                
                # Encode sequence
                seq_embedding = np.zeros(self.n_factors)
                valid_items = 0
                
                for pos, item_id in enumerate(seq):
                    if item_id in self.item_map:
                        item_idx = self.item_map[item_id]
                        weight = self.sequence_weights[pos]
                        seq_embedding += weight * self.item_embeddings[item_idx]
                        valid_items += 1
                
                if valid_items > 0:
                    seq_embedding /= valid_items
                
                # Compute prediction
                target_emb = self.item_embeddings[target_idx]
                pred = float(np.dot(seq_embedding, target_emb))
                pred = 1.0 / (1.0 + np.exp(-np.clip(pred, -10, 10)))
                
                loss = -np.log(max(pred, 1e-10))
                total_loss += loss
                
                # Gradient updates
                err = 1.0 - pred
                grad = err * pred * (1 - pred)
                
                # Update target item
                self.item_embeddings[target_idx] += incremental_lr * (grad * seq_embedding - self.reg * target_emb)
                self.item_embeddings[target_idx] = np.clip(self.item_embeddings[target_idx], -10, 10)
                
                # Update sequence items and weights
                for pos, item_id in enumerate(seq):
                    if item_id in self.item_map:
                        item_idx = self.item_map[item_id]
                        weight = self.sequence_weights[pos]
                        
                        item_grad = (grad * weight * target_emb) / max(valid_items, 1)
                        self.item_embeddings[item_idx] += incremental_lr * (item_grad - self.reg * self.item_embeddings[item_idx])
                        self.item_embeddings[item_idx] = np.clip(self.item_embeddings[item_idx], -10, 10)
                        
                        weight_grad = grad * np.dot(self.item_embeddings[item_idx], target_emb) / max(valid_items, 1)
                        self.sequence_weights[pos] += incremental_lr * (weight_grad - self.reg * self.sequence_weights[pos])
                
                self.sequence_weights = np.clip(self.sequence_weights, 0.01, 10)
            
            avg_loss = total_loss / max(len(sequences), 1)
            self.training_history.append(avg_loss)
            print(f"Incremental Epoch {epoch + 1}/{n_epochs} - Loss: {avg_loss:.4f}")
        
        print(f"Incremental update complete. Model now has {len(self.user_map)} users and {len(self.item_map)} items")
    
    def update_incremental_distributed(self, df: pd.DataFrame, num_workers: int = 2, 
                                       n_epochs: int = 3, lr_decay: float = 0.5) -> None:
        """
        Incrementally update the model with new data using distributed workers.
        
        Args:
            df: New clickstream data
            num_workers: Number of Ray workers for distributed training
            n_epochs: Number of epochs for incremental training
            lr_decay: Learning rate decay factor
        """
        if self.item_embeddings is None:
            raise RuntimeError("Model must be fitted before incremental updates.")
        
        print(f"\n=== Distributed Incremental Model Update ===")
        print(f"Current model: {len(self.user_map)} users, {len(self.item_map)} items")
        
        # Create sequences from new data
        sequences, targets, seq_user_ids = self._create_sequences(df)
        print(f"Created {len(sequences)} new training sequences")
        
        # Identify and add new users/items (same as non-distributed version)
        new_users = set(df['user_id'].unique()) - set(self.user_map.keys())
        new_items = set(df['product_id'].unique()) - set(self.item_map.keys())
        
        print(f"Detected {len(new_users)} new users and {len(new_items)} new items")
        
        if new_users:
            rng = np.random.default_rng(self.random_state)
            new_user_idx_start = len(self.user_map)
            
            for idx, user_id in enumerate(new_users):
                new_idx = new_user_idx_start + idx
                self.user_map[user_id] = new_idx
                self.user_inv[new_idx] = user_id
            
            new_user_emb = 0.1 * rng.standard_normal((len(new_users), self.n_factors))
            self.user_embeddings = np.vstack([self.user_embeddings, new_user_emb])
            print(f"Expanded user embeddings: {self.user_embeddings.shape}")
        
        if new_items:
            rng = np.random.default_rng(self.random_state)
            new_item_idx_start = len(self.item_map)
            
            for idx, item_id in enumerate(new_items):
                new_idx = new_item_idx_start + idx
                self.item_map[item_id] = new_idx
                self.item_inv[new_idx] = item_id
            
            new_item_emb = 0.1 * rng.standard_normal((len(new_items), self.n_factors))
            self.item_embeddings = np.vstack([self.item_embeddings, new_item_emb])
            print(f"Expanded item embeddings: {self.item_embeddings.shape}")
        
        # Distributed incremental training
        incremental_lr = self.lr * lr_decay
        print(f"Using learning rate: {incremental_lr} with {num_workers} workers")
        
        rng = np.random.default_rng(self.random_state)
        
        for epoch in range(n_epochs):
            # Shuffle and split into chunks
            indices = rng.permutation(len(sequences))
            chunk_size = len(indices) // num_workers
            
            futures = []
            for w in range(num_workers):
                start_idx = w * chunk_size
                end_idx = start_idx + chunk_size if w < num_workers - 1 else len(indices)
                chunk_indices = indices[start_idx:end_idx]
                
                chunk_seqs = [sequences[i] for i in chunk_indices]
                chunk_targets = [targets[i] for i in chunk_indices]
                
                future = train_sequence_chunk_remote.remote(
                    chunk_seqs, chunk_targets,
                    self.user_embeddings.copy(),
                    self.item_embeddings.copy(),
                    self.sequence_weights.copy(),
                    self.user_map, self.item_map,
                    incremental_lr, self.reg, w
                )
                futures.append(future)
            
            # Aggregate results
            results = ray.get(futures)
            
            total_loss = 0.0
            agg_user_emb = np.zeros_like(self.user_embeddings)
            agg_item_emb = np.zeros_like(self.item_embeddings)
            agg_seq_weights = np.zeros_like(self.sequence_weights)
            
            for user_emb, item_emb, seq_weights, loss, n_samples in results:
                agg_user_emb += user_emb
                agg_item_emb += item_emb
                agg_seq_weights += seq_weights
                total_loss += loss
            
            self.user_embeddings = agg_user_emb / num_workers
            self.item_embeddings = agg_item_emb / num_workers
            self.sequence_weights = agg_seq_weights / num_workers
            
            avg_loss = total_loss / max(len(sequences), 1)
            self.training_history.append(avg_loss)
            print(f"Incremental Epoch {epoch + 1}/{n_epochs} - Loss: {avg_loss:.4f} (distributed)")
        
        print(f"Incremental update complete. Model now has {len(self.user_map)} users and {len(self.item_map)} items")


def _BotoCfg(**kwargs):
    """Helper to create boto3 Config object"""
    return Config(**kwargs)


def load_existing_model(s3_client, bucket: str, key: str) -> Optional[Dict]:
    """
    Load an existing model from S3 if it exists.
    
    Args:
        s3_client: Boto3 S3 client
        bucket: S3 bucket name
        key: S3 object key for the model
        
    Returns:
        Model package dict if exists, None otherwise
    """
    try:
        print(f"Checking for existing model at s3://{bucket}/{key}...")
        response = s3_client.get_object(Bucket=bucket, Key=key)
        model_bytes = response['Body'].read()
        model_package = pickle.loads(model_bytes)
        print(f"✓ Found existing model: {model_package.get('metadata', {}).get('model_type', 'unknown')}")
        return model_package
    except s3_client.exceptions.NoSuchKey:
        print("✗ No existing model found. Will train from scratch.")
        return None
    except Exception as e:
        print(f"⚠ Error loading existing model: {e}. Will train from scratch.")
        return None


def check_for_new_data(s3_client, bucket: str, key: str) -> bool:
    """
    Check if new clickstream data exists in S3.
    
    Args:
        s3_client: Boto3 S3 client
        bucket: S3 bucket name
        key: S3 object key for new data
        
    Returns:
        True if new data exists, False otherwise
    """
    try:
        s3_client.head_object(Bucket=bucket, Key=key)
        print(f"✓ New data found at s3://{bucket}/{key}")
        return True
    except s3_client.exceptions.ClientError:
        print(f"✗ No new data at s3://{bucket}/{key}")
        return False


def main():
    """
    Main Ray application to train a prio-clicks-aware sequence recommendation model.
    """
    try:
        # 1. Initialize Ray
        if RAY_ADDRESS:
            attempts = [RAY_ADDRESS]
        else:
            attempts = ["auto", "ray-head:6379", "ray://ray-head:10001"]

        connected = False
        for addr in attempts:
            try:
                print(f"Connecting to Ray with address='{addr}'...")
                ctx = ray.init(
                    address=addr,
                    ignore_reinit_error=True,
                    _memory=2_000_000_000,
                    _system_config={
                        "object_spilling_config": '{"type":"filesystem","params":{"directory_path":"/tmp/ray_spill"}}'
                    }
                )
                print(f"Ray initialized. Dashboard: {ctx.address_info.get('webui_url')}")
                connected = True
                break
            except Exception as conn_err:
                print(f"Ray init failed for address '{addr}': {conn_err}")
        
        if not connected:
            warnings.warn("Ray connection failed; proceeding without Ray.")
        else:
            print("Ray initialized successfully.")

        # 2. Load clickstream data
        print("Loading clickstream data...")
        s3_path = f"s3://{S3_BUCKET}/{CLICKSTREAM_S3_KEY}"
        
        import pyarrow.fs as pafs
        endpoint_no_protocol = MINIO_ENDPOINT.replace("http://", "").replace("https://", "")
        s3_fs = pafs.S3FileSystem(
            access_key=MINIO_ACCESS_KEY,
            secret_key=MINIO_SECRET_KEY,
            endpoint_override=endpoint_no_protocol,
            scheme="http"
        )
        
        ctx_data = ray.data.DataContext.get_current()
        ctx_data.execution_options.resource_limits.object_store_memory = 500_000_000
        
        clickstream_dataset = ray.data.read_json(s3_path, filesystem=s3_fs)
        print(f"Loaded {clickstream_dataset.count()} clickstream records")
        
        # Convert to pandas for sequence creation
        clickstream_df = clickstream_dataset.to_pandas()
        
        # Ensure timestamp column exists
        if 'timestamp' not in clickstream_df.columns:
            # Create synthetic timestamps based on row order
            clickstream_df['timestamp'] = range(len(clickstream_df))
        
        print(f"Clickstream data shape: {clickstream_df.shape}")
        print(f"Columns: {clickstream_df.columns.tolist()}")

        # 3. Check for incremental mode or train from scratch
        s3_client = boto3.client(
            's3',
            endpoint_url=MINIO_ENDPOINT,
            aws_access_key_id=MINIO_ACCESS_KEY,
            aws_secret_access_key=MINIO_SECRET_KEY,
            config=_BotoCfg(signature_version='s3v4'),
        )
        
        existing_model_package = None
        model = None
        incremental_mode = INCREMENTAL_MODE  # Local copy to avoid UnboundLocalError
        
        if incremental_mode:
            print("\n=== INCREMENTAL MODE ENABLED ===")
            existing_model_package = load_existing_model(s3_client, S3_BUCKET, OUTPUT_MODEL_KEY)
            
            if existing_model_package:
                # Load existing model
                model = existing_model_package['model']
                print(f"Loaded existing model with {len(model.user_map)} users and {len(model.item_map)} items")
                
                # Check for new data
                has_new_data = check_for_new_data(s3_client, S3_BUCKET, NEW_CLICKSTREAM_S3_KEY)
                
                if has_new_data:
                    print(f"Loading new clickstream data from s3://{S3_BUCKET}/{NEW_CLICKSTREAM_S3_KEY}...")
                    new_s3_path = f"s3://{S3_BUCKET}/{NEW_CLICKSTREAM_S3_KEY}"
                    new_clickstream_dataset = ray.data.read_json(new_s3_path, filesystem=s3_fs)
                    new_clickstream_df = new_clickstream_dataset.to_pandas()
                    
                    # Ensure timestamp column exists
                    if 'timestamp' not in new_clickstream_df.columns:
                        new_clickstream_df['timestamp'] = range(len(new_clickstream_df))
                    
                    print(f"New clickstream data shape: {new_clickstream_df.shape}")
                    
                    # Determine number of workers
                    num_workers = 2
                    if ray.is_initialized():
                        resources = ray.cluster_resources()
                        available_cpus = resources.get('CPU', 0)
                        num_workers = min(int(available_cpus) - 2, 4)
                        num_workers = max(1, num_workers)
                    
                    # Perform incremental update
                    print(f"\n=== Performing Incremental Update ===")
                    model.update_incremental_distributed(
                        new_clickstream_df, 
                        num_workers=num_workers,
                        n_epochs=INCREMENTAL_EPOCHS,
                        lr_decay=INCREMENTAL_LR_DECAY
                    )
                    
                    # Merge new data into main dataset for metadata
                    clickstream_df = pd.concat([clickstream_df, new_clickstream_df], ignore_index=True)
                    print(f"Combined dataset size: {len(clickstream_df)} records")
                else:
                    print("No new data available. Using existing model without updates.")
            else:
                print("No existing model found. Switching to full training mode...")
                incremental_mode = False  # Switch to full training

        if not incremental_mode or model is None:
            # 3. Train the model from scratch
            print("\n=== FULL TRAINING MODE ===")
            print("Training Prio-Clicks-Aware Sequence Recommender...")
            model = PrioClicksAwareSequenceRecommender(
                n_factors=32,
                n_epochs=15,
                lr=0.01,
                reg=0.05,
                sequence_length=SEQUENCE_LENGTH,
                random_state=42,
                early_stopping=True,
                patience=3,
                min_delta=0.0001
            )
            
            # Determine number of workers
            num_workers = 2
            if ray.is_initialized():
                resources = ray.cluster_resources()
                available_cpus = resources.get('CPU', 0)
                num_workers = min(int(available_cpus) - 2, 4)
                num_workers = max(1, num_workers)
                print(f"Using {num_workers} workers for training")
            
            model.fit_distributed(clickstream_df, num_workers=num_workers)
        
        print("\n--- Training Complete ---")
        print(f"Model covers {len(model.user_map)} users and {len(model.item_map)} items")
        print(f"Sequence length: {model.sequence_length}")
        print(f"Embedding dimensions: {model.n_factors}")
        print(f"Epochs completed: {len(model.training_history)}")
        print(f"Final loss: {model.training_history[-1]:.4f}")
        
        # 4. Sample recommendations
        print("\n--- Sample Recommendations ---")
        sample_users = list(model.user_map.keys())[:3]
        for user_id in sample_users:
            user_clicks = clickstream_df[clickstream_df['user_id'] == user_id]['product_id'].tolist()
            if user_clicks:
                recent_clicks = user_clicks[-SEQUENCE_LENGTH:]
                recs = model.recommend_top_n(user_id, recent_clicks, n=5)
                print(f"User {user_id} (last clicks: {recent_clicks[-3:]}): {[f'{p}({s:.2f})' for p, s in recs]}")

        # 5. Save model
        print(f"\nSaving model to S3: {S3_BUCKET}/{OUTPUT_MODEL_KEY}")
        
        import datetime
        training_mode = "incremental" if (incremental_mode and existing_model_package) else "full"
        
        model_package = {
            'model': model,
            'metadata': {
                'n_users': len(model.user_map),
                'n_items': len(model.item_map),
                'n_factors': model.n_factors,
                'sequence_length': model.sequence_length,
                'epochs_completed': len(model.training_history),
                'final_loss': float(model.training_history[-1]) if model.training_history else 0.0,
                'model_type': 'prio_clicks_aware_sequence',
                'training_mode': training_mode,
                'last_updated': datetime.datetime.utcnow().isoformat(),
                'total_training_samples': len(clickstream_df)
            }
        }
        
        model_bytes = pickle.dumps(model_package)
        
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=OUTPUT_MODEL_KEY,
            Body=model_bytes,
        )
        
        print(f"✓ Model saved successfully!")
        print(f"  Training mode: {training_mode}")
        print(f"  Total samples: {len(clickstream_df)}")
        print(f"  Model size: {len(model_bytes) / 1024:.2f} KB")
        
        # Archive new data if incremental update was performed
        if incremental_mode and existing_model_package and has_new_data:
            archive_key = f"data/clickstream_archive_{datetime.datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
            print(f"\nArchiving new data to s3://{S3_BUCKET}/{archive_key}...")
            try:
                s3_client.copy_object(
                    Bucket=S3_BUCKET,
                    CopySource={'Bucket': S3_BUCKET, 'Key': NEW_CLICKSTREAM_S3_KEY},
                    Key=archive_key
                )
                s3_client.delete_object(Bucket=S3_BUCKET, Key=NEW_CLICKSTREAM_S3_KEY)
                print("✓ New data archived and removed from staging location")
            except Exception as archive_err:
                print(f"⚠ Warning: Could not archive new data: {archive_err}")
        
        print("\n🎉 Prio-Clicks-Aware Sequence Recommendation model training completed successfully!")

    except Exception as e:
        print(f"An error occurred: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if ray.is_initialized():
            print("Shutting down Ray connection.")
            ray.shutdown()


if __name__ == "__main__":
    main()