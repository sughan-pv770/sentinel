import os
import random
import httpx
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, String, Boolean, MetaData, Table, text

# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./orbit.db")
GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8080")
ORBIT_ENV = os.getenv("ORBIT_ENV", "demo")

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
    Column("password_not_set", Boolean, default=False),
    # sync_status: 'pending' | 'synced' | 'failed'
    # Tracks whether this user has been registered with the SentinelX Gateway.
    Column("sync_status", String, default="synced"),
)

def init_db():
    metadata.create_all(engine)
    # Migrate: add sync_status column if it doesn't exist yet (SQLite-safe migration)
    with engine.begin() as conn:
        try:
            conn.execute(text("ALTER TABLE users ADD COLUMN sync_status VARCHAR DEFAULT 'synced'"))
        except Exception:
            pass  # Column already exists
        from sqlalchemy import select
        res = conn.execute(select(users_table)).fetchone()
        if not res:
            default_users = [
                {"identity_id": "u_admin", "name": "Priya Nair", "role": "admin", "sync_status": "synced"},
                {"identity_id": "u_alex", "name": "Alex Rao", "role": "student", "sync_status": "synced"},
            ]
            conn.execute(users_table.insert(), default_users)
            
async def register_users_with_gateway():
    """Register our seeded users with the SentinelX Gateway to ensure baselines carry over."""
    users_to_register = [
        {"identity_id": "u_admin", "name": "Priya Nair", "role": "admin"},
        {"identity_id": "u_alex", "name": "Alex Rao", "role": "student"},
    ]
    async with httpx.AsyncClient(timeout=3.0) as client:
        for u in users_to_register:
            try:
                await client.post(f"{GATEWAY_URL}/sentinelx/users", json=u)
                print(f"Registered {u['identity_id']} with SentinelX")
            except Exception as e:
                print(f"Failed to register {u['identity_id']} with SentinelX: {e}")

def _create_local_user(conn, gw_user: dict):
    from sqlalchemy import select
    res = conn.execute(select(users_table).where(users_table.c.identity_id == gw_user["identity_id"])).fetchone()
    if not res:
        conn.execute(users_table.insert(), {
            "identity_id": gw_user["identity_id"],
            "name": gw_user["name"],
            "role": gw_user.get("role", "student"),
            "password_not_set": True,
            "sync_status": "synced",  # pulled from gateway, so already synced
        })
        return True
    return False

async def sync_users_from_gateway():
    """Pull existing gateway users into Orbit on startup."""
    async with httpx.AsyncClient(timeout=3.0) as client:
        try:
            res = await client.get(f"{GATEWAY_URL}/sentinelx/users")
            if res.status_code == 200:
                gw_users = res.json().get("users", [])
                with engine.begin() as conn:
                    for gu in gw_users:
                        _create_local_user(conn, gu)
        except Exception as e:
            print(f"Failed to sync users from gateway: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    await register_users_with_gateway()
    await sync_users_from_gateway()
    yield

app = FastAPI(title="Orbit SaaS - Protected by SentinelX", lifespan=lifespan)

# --- Pydantic Models ---
class UserCreate(BaseModel):
    identity_id: str
    name: str
    role: str

class UserResponse(BaseModel):
    identity_id: str
    name: str
    role: str
    sync_status: Optional[str] = "synced"


# --- Auth Middleware ---
async def get_current_user_role(request: Request):
    identity_id = request.headers.get("x-identity-id", "unknown")
    with engine.connect() as conn:
        from sqlalchemy import select
        row = conn.execute(select(users_table).where(users_table.c.identity_id == identity_id)).fetchone()
    if not row:
        # JIT Provisioning Fallback: Check Gateway
        async with httpx.AsyncClient(timeout=2.0) as client:
            try:
                res = await client.get(f"{GATEWAY_URL}/sentinelx/users")
                if res.status_code == 200:
                    gw_users = res.json().get("users", [])
                    gw_user = next((u for u in gw_users if u["identity_id"] == identity_id), None)
                    if gw_user:
                        with engine.begin() as wconn:
                            _create_local_user(wconn, gw_user)
                        with engine.connect() as rconn:
                            row = rconn.execute(select(users_table).where(users_table.c.identity_id == identity_id)).fetchone()
            except Exception:
                pass
                
        if not row:
            if identity_id in ("u_admin", "admin") or identity_id.startswith("u_admin"):
                return {"identity_id": identity_id, "role": "admin", "password_not_set": False}
            return {"identity_id": identity_id, "role": "student", "password_not_set": False}
    return dict(row._mapping)


# ════════════════════════════════════════
# 1. CORE & HEALTH
# ════════════════════════════════════════
@app.get("/health")
def health():
    return {"status": "ok", "service": "orbit", "time": datetime.now(timezone.utc).isoformat()}

@app.get("/env")
def get_env():
    return {"env": ORBIT_ENV}

@app.get("/public/users")
def get_public_users():
    with engine.connect() as conn:
        from sqlalchemy import select
        rows = conn.execute(select(users_table)).fetchall()
        return {"users": [{"identity_id": r.identity_id, "name": r.name, "role": r.role} for r in rows]}



# ════════════════════════════════════════
# 2. PROFILE RESOURCE
# ════════════════════════════════════════
@app.get("/profile")
def get_profile(current_user: dict = Depends(get_current_user_role)):
    return {"identity": current_user["identity_id"], **current_user, "message": "Profile retrieved"}

class SetupPasswordRequest(BaseModel):
    password: str

@app.post("/setup_password")
async def setup_password(data: SetupPasswordRequest, current_user: dict = Depends(get_current_user_role)):
    with engine.begin() as conn:
        conn.execute(
            users_table.update().where(users_table.c.identity_id == current_user["identity_id"]).values(password_not_set=False)
        )
    return {"status": "success", "message": "Password set"}

@app.put("/profile")
async def edit_profile(request: Request, current_user: dict = Depends(get_current_user_role)):
    return {"status": "updated", "identity": current_user["identity_id"], "message": "Profile updated"}

@app.patch("/profile")
async def patch_profile(request: Request, current_user: dict = Depends(get_current_user_role)):
    return {"status": "patched", "identity": current_user["identity_id"], "message": "Profile patched"}


# ════════════════════════════════════════
# 3. PAYMENTS / BILLING
# ════════════════════════════════════════
@app.post("/payments/transfer")
async def execute_transfer(request: Request, current_user: dict = Depends(get_current_user_role)):
    return {"identity": current_user["identity_id"], "status": "queued", "tx_id": f"tx_{random.randint(10000, 99999)}"}


# ════════════════════════════════════════
# 4. ADMIN/USERS
# ════════════════════════════════════════
@app.get("/admin/users", response_model=dict[str, list[UserResponse]])
async def get_all_users(current_user: dict = Depends(get_current_user_role)):
    if current_user["role"] not in ["admin"]:
        raise HTTPException(status_code=403, detail="Forbidden: Admins only")
    
    # Background sync before returning
    async with httpx.AsyncClient(timeout=2.0) as client:
        try:
            res = await client.get(f"{GATEWAY_URL}/sentinelx/users")
            if res.status_code == 200:
                gw_users = res.json().get("users", [])
                with engine.begin() as conn:
                    for gu in gw_users:
                        _create_local_user(conn, gu)
        except Exception:
            pass

    with engine.connect() as conn:
        from sqlalchemy import select
        rows = conn.execute(select(users_table)).fetchall()
        return {"users": [dict(r._mapping) for r in rows]}

@app.patch("/admin/users")
async def edit_user_role(request: Request, current_user: dict = Depends(get_current_user_role)):
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Forbidden: Admins only")
    body = await request.json()
    uid = body.get("identity_id")
    role = body.get("role")
    with engine.begin() as conn:
        conn.execute(
            users_table.update().where(users_table.c.identity_id == uid).values(role=role)
        )
    return {"status": "updated", "identity_id": uid, "new_role": role}

@app.delete("/admin/users")
async def remove_user(request: Request, current_user: dict = Depends(get_current_user_role)):
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Forbidden: Admins only")
    body = await request.json()
    uid = body.get("identity_id")
    with engine.begin() as conn:
        conn.execute(
            users_table.delete().where(users_table.c.identity_id == uid)
        )
    return {"status": "deleted", "identity_id": uid}


@app.post("/admin/add_user")
async def add_user(user_data: UserCreate, request: Request, current_user: dict = Depends(get_current_user_role)):
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Forbidden: Admins only")

    # PHASE 1: Always create local Orbit record first (local-first creation).
    # Gateway sync failure must NEVER prevent the user from being created locally.
    sync_status = "pending"
    with engine.begin() as conn:
        from sqlalchemy import select
        existing = conn.execute(
            select(users_table).where(users_table.c.identity_id == user_data.identity_id)
        ).fetchone()
        if not existing:
            conn.execute(users_table.insert(), {**user_data.model_dump(), "sync_status": sync_status})

    # PHASE 1: Immediately attempt gateway sync — use raise_for_status so errors are never silent.
    gateway_error = None
    async with httpx.AsyncClient(timeout=3.0) as client:
        try:
            res = await client.post(f"{GATEWAY_URL}/sentinelx/users", json=user_data.model_dump())
            res.raise_for_status()  # Raises on 4xx/5xx — do NOT suppress
            sync_status = "synced"
            print(f"Gateway: registered {user_data.identity_id} (status {res.status_code})")
        except Exception as e:
            sync_status = "failed"
            gateway_error = str(e)
            print(f"ERROR: Gateway registration failed for {user_data.identity_id}: status={getattr(getattr(e, 'response', None), 'status_code', 'N/A')} body={gateway_error}")

    # PHASE 1: Update sync_status to reflect actual outcome.
    with engine.begin() as conn:
        conn.execute(
            users_table.update()
            .where(users_table.c.identity_id == user_data.identity_id)
            .values(sync_status=sync_status)
        )

    return {
        "status": "created",
        "user": {**user_data.model_dump(), "sync_status": sync_status},
        "gateway_sync": sync_status,
        "gateway_error": gateway_error,
    }


@app.post("/admin/retry_sync")
async def retry_sync(request: Request, current_user: dict = Depends(get_current_user_role)):
    """PHASE 1/2: Retry gateway sync for a user whose sync_status = 'failed'.
    Called from the Retry Sync button on the Admin Users view."""
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Forbidden: Admins only")
    body = await request.json()
    uid = body.get("identity_id")
    if not uid:
        raise HTTPException(status_code=400, detail="identity_id is required")

    with engine.connect() as conn:
        from sqlalchemy import select
        row = conn.execute(select(users_table).where(users_table.c.identity_id == uid)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")

    user = dict(row._mapping)
    gateway_error = None
    async with httpx.AsyncClient(timeout=3.0) as client:
        try:
            res = await client.post(f"{GATEWAY_URL}/sentinelx/users", json={
                "identity_id": user["identity_id"],
                "name": user["name"],
                "role": user["role"],
            })
            res.raise_for_status()
            sync_status = "synced"
            print(f"Retry sync succeeded for {uid}")
        except Exception as e:
            sync_status = "failed"
            gateway_error = str(e)
            print(f"Retry sync still failing for {uid}: {e}")

    with engine.begin() as conn:
        conn.execute(
            users_table.update()
            .where(users_table.c.identity_id == uid)
            .values(sync_status=sync_status)
        )

    return {"identity_id": uid, "sync_status": sync_status, "gateway_error": gateway_error}


# ════════════════════════════════════════
# 5. ORDERS
# ════════════════════════════════════════
_orders_db = [
    {"id": "ORD-001", "item": "Orbit Pro Plan", "amount": 299, "status": "completed"},
    {"id": "ORD-002", "item": "Extra Seats x5",  "amount": 149, "status": "pending"},
]

@app.get("/orders")
def get_orders(current_user: dict = Depends(get_current_user_role)):
    return {"orders": _orders_db, "identity": current_user["identity_id"]}

@app.post("/orders")
async def place_order(request: Request, current_user: dict = Depends(get_current_user_role)):
    body = await request.json()
    order_id = f"ORD-{random.randint(1000, 9999)}"
    _orders_db.append({"id": order_id, "item": body.get("item", "Unknown"), "amount": body.get("amount", 0), "status": "pending"})
    return {"status": "placed", "order_id": order_id}

@app.delete("/orders")
async def cancel_order(request: Request, current_user: dict = Depends(get_current_user_role)):
    body = await request.json()
    order_id = body.get("id")
    for o in _orders_db:
        if o["id"] == order_id:
            o["status"] = "cancelled"
            break
    return {"status": "cancelled", "order_id": order_id}


# ════════════════════════════════════════
# 6. SELF-SERVICE SIGNUP (pre-auth)
# ════════════════════════════════════════
_ip_signup_counts: dict = {}

class SignupRequest(BaseModel):
    name: str
    email: str
    password: str
    role: str = "student"

@app.post("/signup")
async def signup(data: SignupRequest, request: Request):
    # Simple IP-based rate limiting (max 5 signups per IP)
    ip = request.client.host if request.client else "unknown"
    _ip_signup_counts[ip] = _ip_signup_counts.get(ip, 0) + 1
    if _ip_signup_counts[ip] > 5:
        raise HTTPException(status_code=429, detail="Too many signup attempts from this IP")

    uid = f"u_{data.name.lower().replace(' ', '_')}_{random.randint(100, 999)}"

    # PHASE 1: Write to Orbit's own DB first — local-first creation.
    # Signup is never blocked by a gateway failure; sync failure is tracked and visible.
    with engine.begin() as conn:
        conn.execute(users_table.insert(), {
            "identity_id": uid, "name": data.name, "role": data.role,
            "sync_status": "pending",
        })

    # PHASE 1: Attempt gateway registration — use raise_for_status, log actual error on failure.
    sync_status = "pending"
    gateway_error = None
    async with httpx.AsyncClient(timeout=3.0) as client:
        try:
            res = await client.post(f"{GATEWAY_URL}/sentinelx/users", json={
                "identity_id": uid, "name": data.name, "role": data.role,
            })
            res.raise_for_status()  # Raises on 4xx/5xx — errors are never silent
            sync_status = "synced"
            print(f"Signup: registered {uid} with SentinelX (status {res.status_code})")
        except Exception as e:
            sync_status = "failed"
            gateway_error = str(e)
            # Non-fatal for the user's signup — but logged explicitly, not swallowed
            print(f"WARNING: SentinelX registration failed for {uid}: status={getattr(getattr(e, 'response', None), 'status_code', 'N/A')} body={gateway_error}")

    # PHASE 1: Persist accurate sync_status regardless of outcome.
    with engine.begin() as conn:
        conn.execute(
            users_table.update()
            .where(users_table.c.identity_id == uid)
            .values(sync_status=sync_status)
        )

    return {
        "status": "created",
        "identity_id": uid,
        "name": data.name,
        "role": data.role,
        "sync_status": sync_status,
        "gateway_error": gateway_error,
    }


# ════════════════════════════════════════
# 7. RECOVERY / UNLOCK (Tiered Recovery System)
# ════════════════════════════════════════

@app.get("/admin/locked_accounts")
async def get_locked_accounts(current_user: dict = Depends(get_current_user_role)):
    """Proxy: fetch locked (revoked) accounts from SentinelX Gateway."""
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Forbidden: Admins only")
    async with httpx.AsyncClient(timeout=3.0) as client:
        try:
            res = await client.get(f"{GATEWAY_URL}/sentinelx/unlock")
            return res.json()
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Gateway unreachable: {e}")


@app.post("/admin/unlock/request")
async def request_unlock(request: Request, current_user: dict = Depends(get_current_user_role)):
    """Proxy: admin generates an unlock OTP for a revoked identity."""
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Forbidden: Admins only")
    body = await request.json()
    body["admin_id"] = current_user["identity_id"]
    async with httpx.AsyncClient(timeout=3.0) as client:
        try:
            res = await client.post(f"{GATEWAY_URL}/sentinelx/unlock/request", json=body)
            if res.status_code != 200:
                raise HTTPException(status_code=res.status_code, detail=res.json().get("detail", "Error"))
            return res.json()
        except httpx.HTTPError as e:
            raise HTTPException(status_code=502, detail=f"Gateway unreachable: {e}")


@app.post("/admin/unlock/direct")
async def direct_unlock(request: Request, current_user: dict = Depends(get_current_user_role)):
    """Proxy: admin directly unlocks a revoked identity and resets risk score."""
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Forbidden: Admins only")
    body = await request.json()
    body["admin_id"] = current_user["identity_id"]
    async with httpx.AsyncClient(timeout=3.0) as client:
        try:
            res = await client.post(f"{GATEWAY_URL}/sentinelx/unlock/direct", json=body)
            if res.status_code != 200:
                raise HTTPException(status_code=res.status_code, detail=res.json().get("detail", "Error"))
            return res.json()
        except httpx.HTTPError as e:
            raise HTTPException(status_code=502, detail=f"Gateway unreachable: {e}")

class UnlockVerifyRequest(BaseModel):
    identity_id: str
    code: str

@app.post("/unlock/verify")
async def verify_unlock(data: UnlockVerifyRequest):
    """User-facing: locked-out member submits the admin-issued OTP to regain access."""
    async with httpx.AsyncClient(timeout=3.0) as client:
        try:
            res = await client.post(f"{GATEWAY_URL}/sentinelx/unlock/verify", json=data.model_dump())
            return res.json()
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Gateway unreachable: {e}")


@app.post("/admin/unlock/reset_all")
async def reset_all_locks(current_user: dict = Depends(get_current_user_role)):
    """DEV ONLY: Clear all identity-level revocations for fast demo rehearsal."""
    if ORBIT_ENV != "demo":
        raise HTTPException(status_code=403, detail="Not available outside demo mode")
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Forbidden: Admins only")
    async with httpx.AsyncClient(timeout=3.0) as client:
        try:
            res = await client.post(f"{GATEWAY_URL}/sentinelx/unlock/reset_all")
            return res.json()
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Gateway unreachable: {e}")
if ORBIT_ENV == "demo":
    # Stub: exists to let SentinelX score this combination for demo/testing purposes; not a real product action
    @app.post("/profile")
    @app.delete("/profile")
    @app.put("/orders")
    @app.patch("/orders")
    @app.get("/payments/transfer")
    @app.put("/payments/transfer")
    @app.patch("/payments/transfer")
    @app.delete("/payments/transfer")
    @app.post("/admin/users")
    @app.put("/admin/users")
    @app.get("/admin/add_user")
    @app.put("/admin/add_user")
    @app.patch("/admin/add_user")
    @app.delete("/admin/add_user")
    async def demo_stub(request: Request, current_user: dict = Depends(get_current_user_role)):
        return {"status": "demo_stub", "message": "This is a demo stub for SentinelX scoring."}

# Mount Static Files (Frontend UI) — must be LAST
current_dir = os.path.dirname(os.path.abspath(__file__))
app.mount("/", StaticFiles(directory=os.path.join(current_dir, "static"), html=True), name="static")
