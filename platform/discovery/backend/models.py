from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime


class DataProductSLA(BaseModel):
    """Service level agreement for a data product"""
    freshness_minutes: int
    availability_percent: float
    completeness_percent: float


class ColumnAccess(BaseModel):
    """Column-level access control"""
    name: str
    classification: str
    masked_for_roles: List[str] = []


class AccessPolicy(BaseModel):
    """Data product access policy"""
    default: str = "deny"
    approval_required: bool = True
    approval_sla_hours: int = 4
    self_approve_roles: List[str] = []
    columns: List[ColumnAccess] = []


class DataProduct(BaseModel):
    """Data product definition"""
    id: str = Field(..., description="Unique product ID")
    name: str
    version: str
    domain: str
    owner: str
    owner_email: str
    description: str
    tables: List[str]
    sla: DataProductSLA
    access_policy: AccessPolicy
    tags: List[str] = []
    use_cases: List[str] = []
    upstream_lineage: List[str] = []
    downstream_lineage: List[str] = []
    retention_years: int


class AccessRequest(BaseModel):
    """Request for data product access"""
    id: Optional[str] = None
    user_id: str
    user_role: str
    data_product_id: str
    action: str
    justification: str
    requested_columns: List[str] = []
    time_limit_days: Optional[int] = None
    requested_at: Optional[datetime] = None
    status: str = "pending"
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None


class DataProductSearchResult(BaseModel):
    """Search result for data products"""
    id: str
    name: str
    domain: str
    owner: str
    description: str
    tags: List[str]
    freshness_minutes: int
