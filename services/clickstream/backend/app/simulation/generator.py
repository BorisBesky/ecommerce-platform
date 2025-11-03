"""Reusable clickstream data generator adapted from tools.generate_data.

This module borrows the sampling heuristics from the CLI-based generator and
wraps them in a class suitable for programmatic use inside the FastAPI service.
"""

from __future__ import annotations

import csv
import json
import random
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from io import StringIO
from typing import Iterable

import numpy as np

from ..models.simulation import SimulationMode, SimulationParameters

try:  # pragma: no cover - runtime import guard for optional dependency reuse
    from tools import generate_data as legacy_generator
except ModuleNotFoundError:  # pragma: no cover - fallback when CLI tools unavailable
    legacy_generator = None


if legacy_generator:
    FIRST_NAMES = legacy_generator.FIRST_NAMES
    LAST_NAMES = legacy_generator.LAST_NAMES
    PRODUCT_NOUNS = legacy_generator.PRODUCT_NOUNS
    PRODUCT_ADJECTIVES = legacy_generator.PRODUCT_ADJECTIVES
    CATEGORIES = legacy_generator.CATEGORIES
    EVENT_TYPES = legacy_generator.EVENT_TYPES
    select_product_by_affinity = legacy_generator.select_product_by_affinity
else:  # pragma: no cover - fallback constants mirroring tools.generate_data
    FIRST_NAMES = [
        "John",
        "Jane",
        "Peter",
        "Mary",
        "Chris",
        "Pat",
        "Alex",
        "Sam",
        "Taylor",
        "Jordan",
    ]
    LAST_NAMES = [
        "Smith",
        "Jones",
        "Williams",
        "Brown",
        "Davis",
        "Miller",
        "Wilson",
        "Moore",
        "Taylor",
        "Anderson",
    ]
    PRODUCT_NOUNS = [
        "Keyboard",
        "Mouse",
        "Monitor",
        "Chair",
        "Desk",
        "Webcam",
        "Headset",
        "Laptop",
        "Dock",
        "Cable",
    ]
    PRODUCT_ADJECTIVES = [
        "Ergonomic",
        "Mechanical",
        "Gaming",
        "Wireless",
        "4K",
        "Curved",
        "Standing",
        "Adjustable",
        "HD",
    ]
    CATEGORIES = ["Electronics", "Office", "Peripherals", "Furniture", "Accessories"]
    EVENT_TYPES = ["view", "view", "view", "view", "add_to_cart", "add_to_cart", "purchase", "payment_failed"]

    def select_product_by_affinity(
        user_id: str,
        user_features: dict[str, np.ndarray],
        product_ids: list[str],
        product_features: dict[str, np.ndarray],
        temperature: float = 2.0,
        context_product_id: str | None = None,
        context_weight: float = 0.7,
    ) -> str:
        user_vec = user_features[user_id]

        if context_product_id is not None and context_product_id in product_features:
            context_vec = product_features[context_product_id]
            affinities = np.array(
                [
                    context_weight * np.dot(context_vec, product_features[pid])
                    + (1 - context_weight) * np.dot(user_vec, product_features[pid])
                    for pid in product_ids
                ]
            )
        else:
            affinities = np.array([np.dot(user_vec, product_features[pid]) for pid in product_ids])

        exp_affinities = np.exp(affinities / temperature)
        probabilities = exp_affinities / np.sum(exp_affinities)
        return np.random.choice(product_ids, p=probabilities)


@dataclass(slots=True)
class SimulationBatch:
    """A batch of simulation events represented as newline-delimited JSON strings."""

    index: int
    records: list[str]

    @property
    def size(self) -> int:
        return len(self.records)


@dataclass(slots=True)
class SimulationArtifacts:
    """Supporting artifacts generated alongside clickstream events."""

    users_csv: bytes | None
    products_csv: bytes | None
    metadata: dict[str, object]


class ClickstreamDataGenerator:
    """Encapsulate clickstream, user, and product data generation."""

    def __init__(
        self,
        params: SimulationParameters,
        *,
        seed: int | None = None,
        existing_users_csv: bytes | None = None,
        existing_products_csv: bytes | None = None,
    ) -> None:
        self.params = params
        self.seed = seed
        self.existing_users_csv = existing_users_csv
        self.existing_products_csv = existing_products_csv

        self._user_ids: list[str] = []
        self._product_ids: list[str] = []
        self._user_features: dict[str, np.ndarray] = {}
        self._product_features: dict[str, np.ndarray] = {}
        self._users_csv_bytes: bytes | None = None
        self._products_csv_bytes: bytes | None = None
        self._fraud_users: list[str] = []
        self._user_metadata: dict[str, dict[str, object]] = {}
        self._product_metadata: dict[str, dict[str, object]] = {}
        self._prepared: bool = False

        if seed is not None:
            random.seed(seed)
            np.random.seed(seed)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def prepare(self) -> SimulationArtifacts:
        """Prepare user/product datasets and return supporting artifacts."""

        if self._prepared:
            return self._artifacts()

        if self.params.mode is SimulationMode.INCREMENTAL and self.existing_users_csv and self.existing_products_csv:
            self._load_users_csv(self.existing_users_csv)
            self._load_products_csv(self.existing_products_csv)
        else:
            self._generate_users(self.params.user_count)
            self._generate_products(self.params.product_count)
            self._users_csv_bytes = self._serialize_users()
            self._products_csv_bytes = self._serialize_products()

        self._fraud_users = self._select_fraud_users()
        self._prepared = True
        return self._artifacts()

    def iter_batches(self) -> Iterable[SimulationBatch]:
        """Yield simulation batches with newline-delimited JSON records."""

        if not self._prepared:
            self.prepare()

        start_time = datetime.utcnow() - timedelta(hours=1)
        user_last_product: dict[str, str] = {}
        global_event_index = 0

        for batch_index in range(self.params.batches):
            records: list[str] = []
            for _ in range(self.params.batch_size):
                event_time = start_time + timedelta(seconds=global_event_index * 5)
                global_event_index += 1

                user_id = random.choice(self._user_ids)
                last_product = user_last_product.get(user_id)

                if last_product is not None and random.random() < 0.8:
                    product_id = select_product_by_affinity(
                        user_id,
                        self._user_features,
                        self._product_ids,
                        self._product_features,
                        context_product_id=last_product,
                        context_weight=0.7,
                    )
                else:
                    product_id = select_product_by_affinity(
                        user_id,
                        self._user_features,
                        self._product_ids,
                        self._product_features,
                    )

                event_type = random.choice(EVENT_TYPES)
                if event_type in {"view", "add_to_cart", "purchase"}:
                    user_last_product[user_id] = product_id

                event_payload = {
                    "event_id": str(uuid.uuid4()),
                    "timestamp": event_time.isoformat(),
                    "user_id": user_id,
                    "product_id": product_id,
                    "event_type": event_type,
                }
                records.append(json.dumps(event_payload, separators=(",", ":")))

            # Inject fraud activity at the end of each batch for observability.
            records.extend(self._generate_fraud_events(start_time, batch_index, global_event_index))

            yield SimulationBatch(index=batch_index, records=records)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------
    @property
    def users_csv_bytes(self) -> bytes | None:
        if not self._prepared:
            self.prepare()
        return self._users_csv_bytes

    @property
    def products_csv_bytes(self) -> bytes | None:
        if not self._prepared:
            self.prepare()
        return self._products_csv_bytes

    @property
    def user_count(self) -> int:
        return len(self._user_ids)

    @property
    def product_count(self) -> int:
        return len(self._product_ids)

    @property
    def fraud_users(self) -> list[str]:
        if not self._prepared:
            self.prepare()
        return self._fraud_users

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _artifacts(self) -> SimulationArtifacts:
        return SimulationArtifacts(
            users_csv=self._users_csv_bytes,
            products_csv=self._products_csv_bytes,
            metadata={"fraud_users": self._fraud_users},
        )

    def _generate_users(self, count: int) -> None:
        for _ in range(count):
            user_id = str(uuid.uuid4())
            name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
            signup_date = (datetime.utcnow() - timedelta(days=random.randint(1, 365))).strftime("%Y-%m-%d")
            features = np.random.randn(20)
            features = features / np.linalg.norm(features)

            self._user_ids.append(user_id)
            self._user_features[user_id] = features
            self._user_metadata[user_id] = {
                "user_id": user_id,
                "name": name,
                "signup_date": signup_date,
                "features": features.tolist(),
            }

    def _generate_products(self, count: int) -> None:
        for _ in range(count):
            product_id = str(uuid.uuid4())
            product_name = f"{random.choice(PRODUCT_ADJECTIVES)} {random.choice(PRODUCT_NOUNS)}"
            category = random.choice(CATEGORIES)
            price = round(random.uniform(10.0, 500.0), 2)
            features = np.random.randn(20)
            features = features / np.linalg.norm(features)

            self._product_ids.append(product_id)
            self._product_features[product_id] = features
            self._product_metadata[product_id] = {
                "product_id": product_id,
                "product_name": product_name,
                "category": category,
                "price": price,
                "features": features.tolist(),
            }

    def _serialize_users(self) -> bytes:
        sio = StringIO()
        writer = csv.writer(sio)
        writer.writerow(["user_id", "name", "signup_date", "features"])
        for uid in self._user_ids:
            metadata = self._user_metadata[uid]
            writer.writerow(
                [metadata["user_id"], metadata["name"], metadata["signup_date"], json.dumps(metadata["features"])]
            )
        return sio.getvalue().encode("utf-8")

    def _serialize_products(self) -> bytes:
        sio = StringIO()
        writer = csv.writer(sio)
        writer.writerow(["product_id", "product_name", "category", "price", "features"])
        for pid in self._product_ids:
            metadata = self._product_metadata[pid]
            writer.writerow(
                [
                    metadata["product_id"],
                    metadata["product_name"],
                    metadata["category"],
                    metadata["price"],
                    json.dumps(metadata["features"]),
                ]
            )
        return sio.getvalue().encode("utf-8")

    def _load_users_csv(self, payload: bytes) -> None:
        sio = StringIO(payload.decode("utf-8"))
        reader = csv.DictReader(sio)
        for row in reader:
            user_id = row["user_id"]
            features = np.array(json.loads(row["features"]))
            self._user_ids.append(user_id)
            self._user_features[user_id] = features
            self._user_metadata[user_id] = {
                "user_id": user_id,
                "name": row.get("name", ""),
                "signup_date": row.get("signup_date", datetime.utcnow().strftime("%Y-%m-%d")),
                "features": features.tolist(),
            }

    def _load_products_csv(self, payload: bytes) -> None:
        sio = StringIO(payload.decode("utf-8"))
        reader = csv.DictReader(sio)
        for row in reader:
            product_id = row["product_id"]
            features = np.array(json.loads(row["features"]))
            self._product_ids.append(product_id)
            self._product_features[product_id] = features
            self._product_metadata[product_id] = {
                "product_id": product_id,
                "product_name": row.get("product_name", ""),
                "category": row.get("category", ""),
                "price": float(row.get("price", 0.0)),
                "features": features.tolist(),
            }

    def _select_fraud_users(self) -> list[str]:
        population = self._user_ids if len(self._user_ids) >= 3 else (self._user_ids or [str(uuid.uuid4())])
        count = min(3, len(population))
        if count == 0:
            return []
        return random.sample(population, count)

    def _generate_fraud_events(
        self,
        start_time: datetime,
        batch_index: int,
        global_event_index: int,
    ) -> list[str]:
        records: list[str] = []
        fraud_offset_seconds = global_event_index * 5 + batch_index * 60

        for user in self._fraud_users:
            fraud_context_product: str | None = None
            for i in range(10):
                event_time = start_time + timedelta(seconds=fraud_offset_seconds + i)
                if fraud_context_product is not None and random.random() < 0.6:
                    product_id = select_product_by_affinity(
                        user,
                        self._user_features,
                        self._product_ids,
                        self._product_features,
                        context_product_id=fraud_context_product,
                        context_weight=0.5,
                    )
                else:
                    product_id = select_product_by_affinity(
                        user,
                        self._user_features,
                        self._product_ids,
                        self._product_features,
                    )
                fraud_context_product = product_id

                event_payload = {
                    "event_id": str(uuid.uuid4()),
                    "timestamp": event_time.isoformat(),
                    "user_id": user,
                    "product_id": product_id,
                    "event_type": "view",
                    "tags": ["fraud_suspected"],
                }
                records.append(json.dumps(event_payload, separators=(",", ":")))

            for i in range(2):
                event_time = start_time + timedelta(seconds=fraud_offset_seconds + 10 + i)
                product_id = random.choice(self._product_ids)
                event_payload = {
                    "event_id": str(uuid.uuid4()),
                    "timestamp": event_time.isoformat(),
                    "user_id": user,
                    "product_id": product_id,
                    "event_type": "payment_failed",
                    "tags": ["fraud_suspected"],
                }
                records.append(json.dumps(event_payload, separators=(",", ":")))

        return records

