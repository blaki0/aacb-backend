import os
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import psycopg2
from psycopg2.extras import RealDictCursor
from typing import Optional

app = FastAPI(title="AACB Bus Maintenance System API")

# 🔓 CORS ሙሉ በሙሉ ክፍት በማድረግ ከNetlify ጋር እንዲገናኝ ማድረግ
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # ሁሉንም እንዲቀበል ተደርጓል
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATABASE_URL = os.getenv("DATABASE_URL")

def get_db_connection():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

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

@app.post("/api/login")
def login(data: LoginRequest):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT username, password, full_name, role, depot, is_active FROM users WHERE username = %s", (data.username,))
    user = cursor.fetchone()
    cursor.close()
    conn.close()

    if not user:
        raise HTTPException(status_code=400, detail="የተጠቃሚ ስም አልተገኘም!")
    if user['password'] != data.password:
        raise HTTPException(status_code=400, detail="የተሳሳተ የይለፍ ቃል!")
    if not user['is_active']:
        raise HTTPException(status_code=403, detail="⛔ መለያዎ ታግዷል!")

    return user

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
        return {"message": "ተጠቃሚው ተፈጥሯል!"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail="ስህተት፡ ተጠቃሚው ቀድሞ ሳይኖር አልቀረም!")
    finally:
        cursor.close()
        conn.close()

@app.get("/api/admin/users")
def list_users():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT username, full_name, role, depot, is_active FROM users ORDER BY role")
    users = cursor.fetchall()
    cursor.close()
    conn.close()
    return users

@app.post("/api/admin/toggle-status")
def toggle_status(data: StatusToggleRequest):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET is_active = %s WHERE username = %s", (data.is_active, data.username))
    conn.commit()
    cursor.close()
    conn.close()
    return {"message": "የተጠቃሚው ሁኔታ ተቀይሯል!"}

@app.post("/api/admin/reset-password")
def admin_reset_password(data: PasswordResetRequest):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET password = %s WHERE username = %s", (data.new_password, data.username))
    conn.commit()
    cursor.close()
    conn.close()
    return {"message": "ይለፍ ቃል ተቀይሯል!"}

@app.post("/api/user/change-password")
def change_password(data: PasswordChangeRequest):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT password FROM users WHERE username = %s", (data.username,))
    user = cursor.fetchone()
    if not user or user['password'] != data.old_password:
        cursor.close()
        conn.close()
        raise HTTPException(status_code=400, detail="የቆየው ይለፍ ቃል የተሳሳተ ነው!")
    cursor.execute("UPDATE users SET password = %s WHERE username = %s", (data.new_password, data.username))
    conn.commit()
    cursor.close()
    conn.close()
    return {"message": "ይለፍ ቃልዎ ተቀይሯል!"}

@app.post("/api/maintenance/submit-log")
def submit_log(data: MaintenanceLog):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO maintenance_logs (side_number, maintenance_type, entered_km, work_details, username, co_workers, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (data.side_number, data.maintenance_type, data.entered_km, data.work_details, data.username, data.co_workers, data.created_at)
        )
        conn.commit()
        return {"message": "ስኬት"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()
