from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime, timedelta
import os, psycopg2
from psycopg2.extras import RealDictCursor
from typing import Optional, List

app = FastAPI(title="Addis Ababa Bus Garage - Full Enterprise System")

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://neondb_owner:npg_oAtjGa1ZYnK7@ep-rapid-forest-atyx5bhs.c-9.us-east-1.aws.neon.tech/neondb?sslmode=require")

def get_db(): return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

def init_db():
    with get_db() as conn, conn.cursor() as cursor:
        # Users Table (Added status field for Resigned employees)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY, username TEXT UNIQUE NOT NULL, password TEXT NOT NULL,
                full_name TEXT NOT NULL, staff_id TEXT UNIQUE NOT NULL, gender TEXT, rank_level TEXT,
                role TEXT NOT NULL, depo_id INTEGER, group_id INTEGER DEFAULT NULL, 
                is_active INTEGER DEFAULT 1, emp_status TEXT DEFAULT 'Active',
                can_add INTEGER DEFAULT 1, can_edit INTEGER DEFAULT 0, can_delete INTEGER DEFAULT 0
            )
        """)
        # Employee History Table (Tracks transfers and status changes)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS employee_history (
                id SERIAL PRIMARY KEY, username TEXT NOT NULL, action_type TEXT NOT NULL,
                description TEXT NOT NULL, done_by TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Vehicles Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS vehicles (
                id SERIAL PRIMARY KEY, plate_number TEXT UNIQUE NOT NULL, side_number TEXT UNIQUE NOT NULL,
                vehicle_type TEXT NOT NULL, assigned_group INTEGER, depo_id INTEGER, status TEXT DEFAULT 'Active',
                oil_limit_km INTEGER, fuel_filter_limit_km INTEGER, differential_oil_limit_km INTEGER,
                steering_oil_limit_km INTEGER, transmission_oil_limit_km INTEGER
            )
        """)
        # Maintenance Logs Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS maintenance_logs (
                id SERIAL PRIMARY KEY, side_number TEXT NOT NULL, maintenance_type TEXT NOT NULL,
                entered_km INTEGER NOT NULL, work_details TEXT NOT NULL, logged_by_user TEXT NOT NULL,
                depo_id INTEGER, co_workers TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'Pending', inspection_remark TEXT DEFAULT '', inspected_by TEXT DEFAULT ''
            )
        """)
        # Super Admin Init
        cursor.execute("SELECT COUNT(*) FROM users WHERE username = 'admin'")
        if cursor.fetchone()['count'] == 0:
            cursor.execute("""
                INSERT INTO users (username, password, full_name, staff_id, gender, rank_level, role, depo_id, is_active, can_add, can_edit, can_delete)
                VALUES ('admin', 'admin123', 'ዋና ሱፐር አድሚን', 'STAFF-000', 'Male', 'Level 5', 'SUPER_ADMIN', 0, 1, 1, 1, 1)
            """)
        conn.commit()

try: init_db()
except Exception as e: print(f"DB Error: {e}")

# --- Models ---
class UserAdd(BaseModel):
    username: str; password: str; full_name: str; staff_id: str; gender: str; rank_level: str; role: str; depo_id: int; group_id: Optional[int] = None

class VehicleAdd(BaseModel):
    plate_number: str; side_number: str; vehicle_type: str; assigned_group: int; depo_id: int
    oil_limit_km: int; fuel_filter_limit_km: int; differential_oil_limit_km: int; steering_oil_limit_km: int; transmission_oil_limit_km: int

class EmployeeTransfer(BaseModel):
    username: str; new_depo_id: int; new_group_id: Optional[int]; new_role: str; admin_username: str; reason: str

class EmployeeStatusChange(BaseModel):
    username: str; new_status: str; admin_username: str; reason: str

class MaintenanceLogInput(BaseModel):
    side_number: str; maintenance_type: str; entered_km: int; work_details: str; username: str; depo_id: int; co_workers: Optional[str] = ""

class LoginInput(BaseModel):
    username: str; password: str; depo_id: Optional[int] = None; is_admin_login: bool = False

class InspectionInput(BaseModel):
    log_id: int; status: str; remark: Optional[str] = ""; inspector_username: str

# --- Depot Codes Dictionary ---
DEPOT_CODES = {1: "1", 2: "2", 3: "3", 4: "4", 5: "5"}
DEPOT_NAMES = {1: "የካ", 2: "ቃሊቲ", 3: "መካኒሳ", 4: "ሸጎሌ", 5: "ሰሚት"}

# --- Endpoints ---
@app.post("/api/login")
def login(data: LoginInput):
    with get_db() as conn, conn.cursor() as cursor:
        cursor.execute("SELECT * FROM users WHERE username = %s AND password = %s", (data.username.strip().lower(), data.password))
        user = cursor.fetchone()
        if not user: raise HTTPException(401, "የተሳሳተ Username ወይም Password!")
        if user['is_active'] == 0 or user['emp_status'] == 'Resigned': raise HTTPException(403, "ይህ አካውንት ታግዷል ወይም ሰራተኛው ስራ ለቋል!")
        
        if not data.is_admin_login:
            if user['depo_id'] != data.depo_id and user['role'] != 'SUPER_ADMIN':
                raise HTTPException(403, f"እርስዎ የዲፖ {data.depo_id} ባለሙያ አይደሉም!")
        return {"status": "success", **user}

@app.post("/api/admin/add-vehicle")
def add_vehicle(veh: VehicleAdd):
    with get_db() as conn, conn.cursor() as cursor:
        if veh.assigned_group not in [1, 2, 3, 4]: raise HTTPException(400, "መኪና ከ4ቱ አንዱ ግሩፕ ሊሰጠው ይገባል!")
        
        # Check prefix rule
        required_prefix = DEPOT_CODES.get(veh.depo_id)
        if not veh.side_number.startswith(required_prefix):
            depot_name = DEPOT_NAMES.get(veh.depo_id, "ያልታወቀ")
            raise HTTPException(400, f"የ {depot_name} ዲፖ መኪና የጎን ቁጥር በ '{required_prefix}' መጀመር አለበት!")

        try:
            cursor.execute("""
                INSERT INTO vehicles (plate_number, side_number, vehicle_type, assigned_group, depo_id, oil_limit_km, fuel_filter_limit_km, differential_oil_limit_km, steering_oil_limit_km, transmission_oil_limit_km)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (veh.plate_number.upper(), veh.side_number.upper(), veh.vehicle_type, veh.assigned_group, veh.depo_id, veh.oil_limit_km, veh.fuel_filter_limit_km, veh.differential_oil_limit_km, veh.steering_oil_limit_km, veh.transmission_oil_limit_km))
            conn.commit()
            return {"status": "success"}
        except psycopg2.IntegrityError:
            raise HTTPException(400, "ታርጋ ወይም የጎን ቁጥር ቀድሞ ተመዝግቧል!")

@app.post("/api/admin/transfer-employee")
def transfer_employee(data: EmployeeTransfer):
    with get_db() as conn, conn.cursor() as cursor:
        cursor.execute("UPDATE users SET depo_id = %s, group_id = %s, role = %s WHERE username = %s", 
                       (data.new_depo_id, data.new_group_id, data.new_role, data.username.lower()))
        desc = f"ወደ ዲፖ {data.new_depo_id}፣ ግሩፕ {data.new_group_id or 'የለም'}፣ ክፍል {data.new_role} ተዛወረ። ምክንያት: {data.reason}"
        cursor.execute("INSERT INTO employee_history (username, action_type, description, done_by) VALUES (%s, %s, %s, %s)", 
                       (data.username.lower(), 'TRANSFER', desc, data.admin_username))
        conn.commit()
        return {"status": "success", "message": "ሰራተኛው በትክክል ተዛውሯል!"}

@app.post("/api/admin/change-employee-status")
def change_employee_status(data: EmployeeStatusChange):
    with get_db() as conn, conn.cursor() as cursor:
        is_active = 0 if data.new_status == 'Resigned' else 1
        cursor.execute("UPDATE users SET emp_status = %s, is_active = %s WHERE username = %s", 
                       (data.new_status, is_active, data.username.lower()))
        desc = f"የሰራተኛው ሁኔታ ወደ '{data.new_status}' ተቀይሯል። ምክንያት: {data.reason}"
        cursor.execute("INSERT INTO employee_history (username, action_type, description, done_by) VALUES (%s, %s, %s, %s)", 
                       (data.username.lower(), 'STATUS_CHANGE', desc, data.admin_username))
        conn.commit()
        return {"status": "success", "message": "የሰራተኛው ሁኔታ ተቀይሯል!"}

@app.get("/api/profile/employee/{username}")
def get_employee_profile(username: str):
    with get_db() as conn, conn.cursor() as cursor:
        cursor.execute("SELECT username, full_name, role, depo_id, group_id, emp_status FROM users WHERE username = %s", (username.lower(),))
        user_info = cursor.fetchone()
        if not user_info: raise HTTPException(404, "ሰራተኛው አልተገኘም!")
        
        cursor.execute("SELECT * FROM employee_history WHERE username = %s ORDER BY created_at DESC", (username.lower(),))
        history = cursor.fetchall()
        
        cursor.execute("SELECT * FROM maintenance_logs WHERE logged_by_user = %s ORDER BY created_at DESC", (username.lower(),))
        work_logs = cursor.fetchall()
        
        return {"info": user_info, "history": history, "work_logs": work_logs}

@app.get("/api/profile/vehicle/{side_number}")
def get_vehicle_profile(side_number: str):
    with get_db() as conn, conn.cursor() as cursor:
        cursor.execute("SELECT * FROM vehicles WHERE side_number = %s", (side_number.upper(),))
        veh_info = cursor.fetchone()
        if not veh_info: raise HTTPException(404, "መኪናው አልተገኘም!")
        
        cursor.execute("SELECT l.*, u.full_name FROM maintenance_logs l JOIN users u ON l.logged_by_user = u.username WHERE l.side_number = %s ORDER BY l.created_at DESC", (side_number.upper(),))
        work_logs = cursor.fetchall()
        
        return {"info": veh_info, "work_logs": work_logs}

# (ሌሎቹ ከዚህ ቀደም የነበሩት የ maintenance_log፣ inspection፣ get_logs API ዎች እንደነበሩ ይቀጥላሉ...)
