"""
Origin Demo Service - Fully Upgraded REST API

Provides a realistic set of endpoints: full CRUD (GET, POST, PUT, DELETE) 
on profiles, orders, payments, and admin resources.
"""
import os
import random
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Request, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, String, ForeignKey, MetaData, Table

# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./users.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(
    DATABASE_URL, 
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)
metadata = MetaData()

# Define tables
users_table = Table(
    "users", metadata,
    Column("identity_id", String, primary_key=True),
    Column("name", String, nullable=False),
    Column("role", String, nullable=False),
    Column("supervisor_id", String, ForeignKey("users.identity_id"), nullable=True),
    Column("network_tag", String, nullable=True),
)

orders_table = Table(
    "orders", metadata,
    Column("id", String, primary_key=True),
    Column("identity_id", String, ForeignKey("users.identity_id"), nullable=False),
    Column("amount", String, nullable=False),
    Column("status", String, nullable=False)
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
            
            # Seed 3 orders for alex
            default_orders = [
                {"id": "ord_1", "identity_id": "u_alex", "amount": "250", "status": "shipped"},
                {"id": "ord_2", "identity_id": "u_alex", "amount": "500", "status": "processing"},
            ]
            conn.execute(orders_table.insert(), default_orders)

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(title="Origin Demo Service - Fully Upgraded REST API", lifespan=lifespan)

# --- Pydantic Models ---
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

# --- Auth Middleware ---
def get_current_user_role(request: Request):
    identity_id = request.headers.get("x-identity-id", "unknown")
    with engine.connect() as conn:
        from sqlalchemy import select
        row = conn.execute(select(users_table).where(users_table.c.identity_id == identity_id)).fetchone()
    if not row:
        if identity_id in ("u_admin", "admin") or identity_id.startswith("u_admin"):
            return {"identity_id": identity_id, "role": "admin"}
        return {"identity_id": identity_id, "role": "student"}  # Fallback for simulator
    return dict(row._mapping)


# ════════════════════════════════════════
# 1. CORE & HEALTH
# ════════════════════════════════════════
@app.get("/health")
def health():
    return {"status": "ok", "service": "origin-upgraded", "time": datetime.now(timezone.utc).isoformat()}


# ════════════════════════════════════════
# 2. PROFILE RESOURCE (FULL CRUD)
# ════════════════════════════════════════
@app.get("/profile")
def get_profile(current_user: dict = Depends(get_current_user_role)):
    return {"identity": current_user["identity_id"], **current_user, "message": "Profile retrieved"}

@app.post("/profile")
async def create_profile(request: Request, current_user: dict = Depends(get_current_user_role)):
    return {"status": "generated", "identity": current_user["identity_id"], "message": "Profile created successfully"}

@app.put("/profile")
async def edit_profile(request: Request, current_user: dict = Depends(get_current_user_role)):
    return {"status": "updated", "identity": current_user["identity_id"], "message": "Profile updated entirely"}

@app.patch("/profile")
async def patch_profile(request: Request, current_user: dict = Depends(get_current_user_role)):
    return {"status": "patched", "identity": current_user["identity_id"], "message": "Profile modified"}

@app.delete("/profile")
async def wipe_profile(request: Request, current_user: dict = Depends(get_current_user_role)):
    return {"status": "deleted", "identity": current_user["identity_id"], "message": "Profile removed"}


# ════════════════════════════════════════
# 3. ORDERS RESOURCE (FULL CRUD)
# ════════════════════════════════════════
@app.get("/orders")
def get_orders(current_user: dict = Depends(get_current_user_role)):
    with engine.connect() as conn:
        from sqlalchemy import select
        rows = conn.execute(select(orders_table).where(orders_table.c.identity_id == current_user["identity_id"])).fetchall()
        return {"identity": current_user["identity_id"], "orders": [dict(r._mapping) for r in rows]}

@app.post("/orders")
async def post_order(request: Request, current_user: dict = Depends(get_current_user_role)):
    order_id = f"ord_{random.randint(1000, 9999)}"
    return {"status": "processing", "order_id": order_id, "identity": current_user["identity_id"]}

@app.put("/orders/{order_id}")
async def put_order(order_id: str, request: Request, current_user: dict = Depends(get_current_user_role)):
    return {"status": "shipped", "order_id": order_id, "identity": current_user["identity_id"]}

@app.delete("/orders/{order_id}")
async def del_order(order_id: str, request: Request, current_user: dict = Depends(get_current_user_role)):
    return {"status": "cancelled", "order_id": order_id, "identity": current_user["identity_id"]}


# ════════════════════════════════════════
# 4. PAYMENTS RESOURCE (FULL REST)
# ════════════════════════════════════════
@app.get("/payments/transfer")
def list_transfers(current_user: dict = Depends(get_current_user_role)):
    return {"identity": current_user["identity_id"], "history": []}

@app.post("/payments/transfer")
async def execute_transfer(request: Request, current_user: dict = Depends(get_current_user_role)):
    if current_user["role"] not in ["student", "manager", "admin"]:
        raise HTTPException(status_code=403, detail="Not authorized for payments")
    return {"identity": current_user["identity_id"], "status": "queued", "tx_id": f"tx_{random.randint(10000, 99999)}"}

@app.delete("/payments/transfer/{tx_id}")
async def void_transfer(tx_id: str, request: Request, current_user: dict = Depends(get_current_user_role)):
    return {"status": "voided", "tx_id": tx_id, "identity": current_user["identity_id"]}


# ════════════════════════════════════════
# 5. ADMIN/USERS (EXISTING INTEGRATION)
# ════════════════════════════════════════
@app.get("/users", response_model=dict[str, list[UserResponse]])
def get_all_users():
    with engine.connect() as conn:
        from sqlalchemy import select
        rows = conn.execute(select(users_table)).fetchall()
        return {"users": [dict(r._mapping) for r in rows]}

@app.post("/admin/add_user", response_model=UserResponse)
def add_user(user: UserCreate, current_user: dict = Depends(get_current_user_role)):
    if current_user["role"] not in ["admin", "manager"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    with engine.begin() as conn:
        from sqlalchemy import insert, select
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

@app.get("/admin/users_legacy")
def admin_users_legacy(request: Request):
    # Pipeline backward logic
    with engine.connect() as conn:
        from sqlalchemy import select
        rows = conn.execute(select(users_table.c.identity_id)).fetchall()
        return {"identity": request.headers.get("x-identity-id", "unknown"), "users": [r[0] for r in rows]}
