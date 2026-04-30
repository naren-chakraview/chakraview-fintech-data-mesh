from fastapi import FastAPI, HTTPException, Query
from typing import List, Optional
import yaml
import os
from pathlib import Path
from datetime import datetime
from shared.utils import get_logger
from platform.discovery.backend.models import (
    DataProduct,
    AccessRequest,
    DataProductSearchResult,
)


logger = get_logger(__name__)

app = FastAPI(
    title="Data Mesh Discovery Portal",
    description="Self-service discovery and access management for data products",
    version="1.0.0",
)

# In-memory store for demo (replace with database)
data_products: dict = {}
access_requests: dict = {}


def load_data_products():
    """Load data products from YAML files"""
    global data_products
    domains_path = Path("/home/gundu/portfolio/chakraview-fintech-data-mesh/domains")

    for domain_path in domains_path.iterdir():
        if domain_path.is_dir():
            data_products_dir = domain_path / "data-products"
            if data_products_dir.exists():
                for yaml_file in data_products_dir.glob("*.yaml"):
                    try:
                        with open(yaml_file, 'r') as f:
                            product_data = yaml.safe_load(f)
                            product_id = f"{product_data['domain']}.{product_data['name']}"
                            data_products[product_id] = product_data
                            logger.info(
                                "Loaded data product",
                                context={"product_id": product_id},
                            )
                    except Exception as e:
                        logger.error(
                            "Failed to load data product",
                            error=e,
                            context={"file": yaml_file},
                        )


@app.on_event("startup")
async def startup():
    """Load data products on startup"""
    load_data_products()
    logger.info(
        "Discovery portal started",
        context={"products_loaded": len(data_products)},
    )


@app.get("/api/products", response_model=List[DataProductSearchResult])
async def search_products(
    query: Optional[str] = Query(None, description="Search by name, domain, or tags"),
    domain: Optional[str] = Query(None, description="Filter by domain"),
    tag: Optional[str] = Query(None, description="Filter by tag"),
) -> List[DataProductSearchResult]:
    """Search for data products"""
    results = []

    for product_id, product_data in data_products.items():
        # Filter by domain
        if domain and product_data.get("domain") != domain:
            continue

        # Filter by tag
        if tag and tag not in product_data.get("tags", []):
            continue

        # Filter by search query
        if query:
            query_lower = query.lower()
            searchable = (
                product_data.get("name", "").lower()
                + " " + product_data.get("domain", "").lower()
                + " " + " ".join(product_data.get("tags", []))
            )
            if query_lower not in searchable:
                continue

        results.append(
            DataProductSearchResult(
                id=product_id,
                name=product_data.get("name"),
                domain=product_data.get("domain"),
                owner=product_data.get("owner"),
                description=product_data.get("description", ""),
                tags=product_data.get("tags", []),
                freshness_minutes=product_data.get("sla", {}).get("freshness", {}).get("value", 0),
            )
        )

    logger.info(
        "Product search executed",
        context={"query": query, "results": len(results)},
    )
    return results


@app.get("/api/products/{product_id}")
async def get_product(product_id: str) -> dict:
    """Get detailed product information"""
    if product_id not in data_products:
        raise HTTPException(status_code=404, detail="Product not found")

    product = data_products[product_id]
    logger.info(
        "Product details retrieved",
        context={"product_id": product_id},
    )
    return product


@app.post("/api/access-requests")
async def request_access(request: AccessRequest) -> dict:
    """Submit an access request"""
    request_id = f"req_{len(access_requests) + 1}"
    request.id = request_id
    request.requested_at = datetime.utcnow()

    access_requests[request_id] = request.dict()

    logger.info(
        "Access request submitted",
        context={
            "request_id": request_id,
            "product_id": request.data_product_id,
            "user_id": request.user_id,
        },
    )

    return {
        "id": request_id,
        "status": "pending",
        "message": "Access request submitted for review",
    }


@app.get("/api/access-requests/{request_id}")
async def get_access_request(request_id: str) -> dict:
    """Get access request status"""
    if request_id not in access_requests:
        raise HTTPException(status_code=404, detail="Request not found")

    return access_requests[request_id]


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "products_loaded": len(data_products),
        "pending_requests": len([
            r for r in access_requests.values()
            if r.get("status") == "pending"
        ]),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
