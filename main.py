import os
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import psycopg2
from psycopg2.extras import RealDictCursor
from typing import Optional, List

app = FastAPI(title="AACB Bus Maintenance Enterprise System")

# 🔓 CORS ፍቃድ - ከNetlify እና ከማንኛውም አካባቢ ያለምንም እግድ እንዲገናኝ
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATABASE_URL = os.getenv("DATABASE_URL")

def get_db_connection():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

# 📋 የዳታ መዋቅሮች (Pydantic Models)
class LoginRequest(BaseModel):
    username: str
    password: str

class UserCreate(BaseModel):
    username: str
    password: str
    full_name: str
    role: str
    depot: str

class PasswordChangeRequest(BaseModel):
    username: str
    old_password: str
    new_password: str

class PasswordResetRequest(BaseModel):
    username: str
    new_password: str

class StatusToggleRequest(BaseModel):
    username: str
    is_active: bool

class MaintenanceLog(BaseModel):
    side_number: str
    maintenance_type: str
    entered_km: int
    work_details: str
    username: str
    co_workers: Optional[str] = ""
    created_at: str

# 🚪 1. መግቢያ (Login Endpoint)
@app.post("/api/login")
def login(data: LoginRequest):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT username, password, full_name, role, depot, is_active FROM users WHERE username = %s", (data.username.strip().lower(),))
    user = cursor.fetchone()
    cursor.close()
    conn.close()

    if not user:
        raise HTTPException(status_code=400, detail="የተጠቃሚ ስም አልተገኘም!")
    if user['password'] != data.password:
        raise HTTPException(status_code=400, detail="የተሳሳተ የይለፍ ቃል!")
    if not user['is_active']:
        raise HTTPException(status_code=403, detail="⛔ መለያዎ በሲስተም አድሚኑ ታግዷል!")

    return user

# ➕ 2. አዲስ ሰራተኛ/አድሚን መፍጠሪያ
@app.post("/api/admin/create-user")
def create_user(data: UserCreate):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO users (username, password, full_name, role, depot, is_active) VALUES (%s, %s, %s, %s, %s, TRUE)",
            (data.username.strip().lower(), data.password, data.full_name, data.role, data.depot)
        )
        conn.commit()
        return {"message": "ተጠቃሚው በስኬት ተፈጥሯል!"}
    except Exception:
        conn.rollback()
        raise HTTPException(status_code=400, detail="ይህ የተጠቃሚ ስም ቀድሞ በሲስተሙ ላይ አለ!")
    finally:
        cursor.close()
        conn.close()

# 📋 3. የሰራተኞች ዝርዝር ማሳያ
@app.get("/api/admin/users")
def list_users():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT username, full_name, role, depot, is_active FROM users ORDER BY role, username")
    users = cursor.fetchall()
    cursor.close()
    conn.close()
    return users

# 🛑 4. ሰራተኛ ማገጃ እና መፍቀጃ (Toggle)
@app.post("/api/admin/toggle-status")
def toggle_status(data: StatusToggleRequest):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET is_active = %s WHERE username = %s", (data.is_active, data.username))
    conn.commit()
    cursor.close()
    conn.close()
    return {"message": "የሰራተኛው የፈቃድ ሁኔታ ተቀይሯል!"}

# 🔄 5. የአድሚን የይለፍ ቃል ሪሴት ማድረጊያ
@app.post("/api/admin/reset-password")
def admin_reset_password(data: PasswordResetRequest):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET password = %s WHERE username = %s", (data.new_password, data.username))
    conn.commit()
    cursor.close()
    conn.close()
    return {"message": "የይለፍ ቃል ተቀይሯል!"}

# 🔑 6. የባለሙያ ራሱ የይለፍ ቃል መቀየሪያ
@app.post("/api/user/change-password")
def change_password(data: PasswordChangeRequest):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT password FROM users WHERE username = %s", (data.username,))
    user = cursor.fetchone()
    if not user or user['password'] != data.old_password:
        cursor.close()
        conn.close()
        raise HTTPException(status_code=400, detail="የድሮው የይለፍ ቃል የተሳሳተ ነው!")
    cursor.execute("UPDATE users SET password = %s WHERE username = %s", (data.new_password, data.username))
    conn.commit()
    cursor.close()
    conn.close()
    return {"message": "የይለፍ ቃልዎ ተቀይሯል!"}

# 📝 7. የጥገና ስራ መመዝገቢያ (Submit Log)
@app.post("/api/maintenance/submit-log")
def submit_log(data: MaintenanceLog):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """INSERT INTO maintenance_logs (side_number, maintenance_type, entered_km, work_details, username, co_workers, created_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (data.side_number.strip().upper(), data.maintenance_type, data.entered_km, data.work_details, data.username, data.co_workers, data.created_at)
        )
        conn.commit()
        return {"message": "ስራው ተመዝግቧል!"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()

# 📊 8. የተራቀቀ የጥገና ታሪክ ሪፖርት ማውጫ (ከተለያዩ ማጣሪያዎች ጋር)
@app.get("/api/maintenance/logs")
def get_maintenance_logs(depot: Optional[str] = None, role: Optional[str] = None, side_number: Optional[str] = None):
    conn = get_db_connection()
    cursor = conn.cursor()
    query = """
        SELECT l.*, u.full_name, u.depot 
        FROM maintenance_logs l
        JOIN users u ON l.username = u.username
        WHERE 1=1
    """
    params = []
    if depot and depot != "ALL":
        query += " AND u.depot = %s"
        params.append(depot)
    if role and role not in ["SUPER_ADMIN", "DEPOT_ADMIN"]:
        query += " AND l.maintenance_type = %s"
        params.append(role)
    if side_number:
        query += " AND l.side_number LIKE %s"
        params.append(f"%{side_number.strip().upper()}%")
        
    query += " ORDER BY l.id DESC"
    cursor.execute(query, tuple(params))
    logs = cursor.fetchall()
    cursor.close()
    conn.close()
    return logs

# 📈 9. የዳሽቦርድ ስታቲስቲክስ ማጠቃለያ (KPI Cards)
@app.get("/api/analytics/stats")
def get_dashboard_stats(depot: Optional[str] = None):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    log_query = "SELECT COUNT(*) as total_buses FROM maintenance_logs l JOIN users u ON l.username = u.username"
    user_query = "SELECT COUNT(*) as active_techs FROM users WHERE is_active = TRUE"
    params = []
    
    if depot and depot != "ALL":
        log_query += " WHERE u.depot = %s"
        user_query += " AND depot = %s"
        params.append(depot)
        
    cursor.execute(log_query, tuple(params))
    total_buses = cursor.fetchone()['total_buses']
    
    cursor.execute(user_query, tuple(params))
    active_techs = cursor.fetchone()['active_techs']
    
    cursor.close()
    conn.close()
    return {"total_buses": total_buses, "active_techs": active_techs}
