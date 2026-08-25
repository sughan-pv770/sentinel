"""
A tiny toy microservice that SentinelX sits in front of.
It has zero security of its own on purpose -- SentinelX is the security
layer. This just simulates a realistic set of endpoints: auth, a normal
user-facing resource, an admin-only resource, and a payments-ish resource,
so the demo has something meaningful to protect.
"""
from fastapi import FastAPI, Request
from datetime import datetime
import random

app = FastAPI(title="Origin Demo Service")

import os
import random
from datetime import datetime
from contextlib import asynccontextmanager
from typing import List, Optional, Dict

from fastapi import FastAPI, Request, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, String, ForeignKey, MetaData, Table, inspect

# Use PostgreSQL if provided (e.g. Render/Heroku), else default to local SQLite
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./users.db")
# Fix Heroku's postgres:// -> postgresql:// issue
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(
    DATABASE_URL, 
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)
metadata = MetaData()

users_table = Table(
    "users",
    metadata,
    Column("identity_id", String, primary_key=True),
    Column("name", String, nullable=False),
    Column("role", String, nullable=False), # 'admin', 'manager', 'student', 'service'
    Column("supervisor_id", String, ForeignKey("users.identity_id"), nullable=True),
    Column("network_tag", String, nullable=True),
)

def init_db():
    metadata.create_all(engine)
    
    with engine.begin() as conn:
        from sqlalchemy import select
        res = conn.execute(select(users_table)).fetchone()
        if not res:
            default_users = [
                {"identity_id": "u_admin", "name": "Priya Nair", "role": "admin", "supervisor_id": None, "network_tag": "Core"},
                {"identity_id": "u_manager1", "name": "Prof. Smith", "role": "manager", "supervisor_id": "u_admin", "network_tag": "CS-Dept"},
                {"identity_id": "u_alex", "name": "Alex Rao", "role": "student", "supervisor_id": "u_manager1", "network_tag": "CS-Dept-Lab1"},
                {"identity_id": "u_mina", "name": "Mina Okafor", "role": "student", "supervisor_id": "u_manager1", "network_tag": "Library"},
                {"identity_id": "svc_billing", "name": "billing-worker", "role": "service", "supervisor_id": None, "network_tag": "Internal"}
            ]
            conn.execute(users_table.insert(), default_users)

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(title="Origin Demo Service - Unified API", lifespan=lifespan)

# --- Models ---
class UserCreate(BaseModel):
    identity_id: str
    name: str
    role: str
    supervisor_id: Optional[str] = None
    network_tag: Optional[str] = None

class UserResponse(BaseModel):
    identity_id: str
    name: str
    role: str
    supervisor_id: Optional[str]
    network_tag: Optional[str]

# --- Auth Middleware Mock ---
def get_current_user_role(request: Request):
    # In production, parse JWT Bearer token here.
    # For demo via SentinelX, we use the identity header passed by proxy.
    identity_id = request.headers.get("x-identity-id", "unknown")
    with engine.connect() as conn:
        from sqlalchemy import select
        row = conn.execute(select(users_table).where(users_table.c.identity_id == identity_id)).fetchone()
    if not row:
        return {"identity_id": "unknown", "role": "guest"}
    return dict(row._mapping)

# --- Consolidated User Management Routes ---

@app.get("/users", response_model=dict[str, list[UserResponse]])
def get_all_users():
    with engine.connect() as conn:
        from sqlalchemy import select
        rows = conn.execute(select(users_table)).fetchall()
        return {"users": [dict(r._mapping) for r in rows]}

@app.post("/admin/add_user", response_model=UserResponse)
def add_user(user: UserCreate, current_user: dict = Depends(get_current_user_role)):
    if current_user["role"] not in ["admin", "manager"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions to add users")
        
    with engine.begin() as conn:
        from sqlalchemy import insert, select
        # Check exists
        if conn.execute(select(users_table).where(users_table.c.identity_id == user.identity_id)).fetchone():
            raise HTTPException(status_code=400, detail="User already exists")
            
        conn.execute(insert(users_table).values(**user.model_dump()))
    return user

@app.delete("/admin/users/{identity_id}")
def delete_user(identity_id: str, current_user: dict = Depends(get_current_user_role)):
    if current_user["role"] not in ["admin", "manager"]:
        raise HTTPException(status_code=403, detail="Forbidden")
    with engine.begin() as conn:
        from sqlalchemy import delete
        conn.execute(delete(users_table).where(users_table.c.identity_id == identity_id))
    return {"status": "deleted"}

# --- Existing Demo Routes ---

@app.get("/health")
def health():
    return {"status": "ok", "service": "origin-demo-pg", "time": datetime.utcnow().isoformat()}

@app.post("/login")
def login(request: Request):
    identity = request.headers.get("x-identity-id", "unknown")
    return {"identity": identity, "token": f"tok_{identity}_{random.randint(1000,9999)}", "expires_in": 3600}

@app.get("/profile")
def profile(current_user: dict = Depends(get_current_user_role)):
    return {"identity": current_user["identity_id"], **current_user}

@app.get("/orders")
def orders(request: Request):
    return {
        "identity": request.headers.get("x-identity-id", "unknown"),
        "orders": [{"id": f"ord_{i}", "amount": random.randint(200, 5000)} for i in range(1, 4)]
    }

@app.get("/admin/users_legacy")
def admin_users_legacy(request: Request):
    # The old endpoint format expected by the pipeline test
    with engine.connect() as conn:
        from sqlalchemy import select
        rows = conn.execute(select(users_table.c.identity_id)).fetchall()
        return {
            "identity": request.headers.get("x-identity-id", "unknown"),
            "users": [r[0] for r in rows]
        }

@app.post("/payments/transfer")
def transfer(request: Request):
    return {"identity": request.headers.get("x-identity-id", "unknown"), "status": "queued"}
