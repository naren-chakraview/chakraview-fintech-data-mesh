from pydantic import BaseModel
from typing import List, Optional


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


class AccessRequest(BaseModel):
    """Request for data product access.

    The requester is the verified token subject and the workload is the verified SPIFFE ID.
    Neither is read from this body. The endpoint rejects bodies that carry user_id or user_role.
    """
    data_product_id: str
    action: str = "read"
    justification: str
    purpose: Optional[str] = None
    requested_columns: List[str] = []
    time_limit_days: Optional[int] = None


class DataProductSearchResult(BaseModel):
    """Search result for data products"""
    id: str
    name: str
    domain: str
    owner: str
    description: str
    tags: List[str]
    freshness_minutes: int
