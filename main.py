from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime, timedelta
import os, psycopg2
from psycopg2.extras import RealDictCursor
from typing import Optional, List

app = FastAPI(title="Addis Ababa Bus Garage - Full Enterprise Multi-Depo System")

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://neondb_owner:npg_oAtjGa1ZYnK7@ep-rapid-forest-atyx5bhs.c-9.us-east-1.aws.neon.tech/neondb?sslmode=require")

def get_db(): return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

# --- Database Initialization ---
def init_db():
    with get_db() as conn, conn.cursor() as cursor:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY, username TEXT UNIQUE NOT NULL, password TEXT NOT NULL,
                full_name TEXT NOT NULL, staff_id TEXT UNIQUE NOT NULL, gender TEXT, rank_level TEXT,
                role TEXT NOT NULL, depo_id INTEGER, group_id INTEGER DEFAULT NULL, is_active INTEGER DEFAULT 1
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS vehicles (
                id SERIAL PRIMARY KEY, plate_number TEXT UNIQUE NOT NULL, side_number TEXT UNIQUE NOT NULL,
                vehicle_type TEXT NOT NULL, assigned_group INTEGER, depo_id INTEGER, status TEXT DEFAULT 'Active',
                oil_limit_km INTEGER, fuel_filter_limit_km INTEGER, differential_oil_limit_km INTEGER,
                steering_oil_limit_km INTEGER, transmission_oil_limit_km INTEGER
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS maintenance_logs (
                id SERIAL PRIMARY KEY, side_number TEXT NOT NULL, maintenance_type TEXT NOT NULL,
                entered_km INTEGER NOT NULL, work_details TEXT NOT NULL, logged_by_user TEXT NOT NULL,
                depo_id INTEGER, co_workers TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # ሱፐር አድሚን መፍጠሪያ
        cursor.execute("SELECT COUNT(*) FROM users WHERE username = 'admin'")
        if cursor.fetchone()['count'] == 0:
            cursor.execute("""
                INSERT INTO users (username, password, full_name, staff_id, gender, rank_level, role, depo_id, is_active)
                VALUES ('admin', 'admin123', 'ዋና ሲስተም አድሚን', 'STAFF-001', 'Male', 'Level 5', 'SUPER_ADMIN', 0, 1)
            """)
        conn.commit()

try: init_db()
except Exception as e: print(f"Database connection failed: {e}")

# --- Pydantic Models ---
class UserAdd(BaseModel):
    username: str; password: str; full_name: str; staff_id: str; gender: str; rank_level: str; role: str; depo_id: int; group_id: Optional[int] = None

class VehicleAdd(BaseModel):
    plate_number: str; side_number: str; vehicle_type: str; assigned_group: int; depo_id: int; oil_limit_km: int; fuel_filter_limit_km: int; differential_oil_limit_km: int; steering_oil_limit_km: int; transmission_oil_limit_km: int

class MaintenanceLogInput(BaseModel):
    side_number: str; maintenance_type: str; entered_km: int; work_details: str; username: str; depo_id: int; co_workers: Optional[str] = ""; created_at: Optional[str] = None

class MaintenanceLogUpdate(BaseModel): entered_km: int; work_details: str; co_workers: Optional[str] = ""
class LoginInput(BaseModel): username: str; password: str

# --- API Endpoints ---

@app.post("/api/login")
def login(data: LoginInput):
    with get_db() as conn, conn.cursor() as cursor:
        cursor.execute("SELECT role, group_id, is_active, full_name, username, depo_id FROM users WHERE username = %s AND password = %s", (data.username.strip().lower(), data.password))
        user = cursor.fetchone()
        if not user: raise HTTPException(status_code=401, detail="የተሳሳተ Username ወይም Password!")
        if user['is_active'] == 0: raise HTTPException(status_code=403, detail="ይህ አካውንት ታግዷል!")
        return {"status": "success", **user}

@app.put("/api/admin/reset-password")
def reset_password(admin_username: str, target_username: str, new_password: str):
    with get_db() as conn, conn.cursor() as cursor:
        cursor.execute("SELECT role FROM users WHERE username = %s", (admin_username,))
        admin = cursor.fetchone()
        if not admin or admin['role'] != 'SUPER_ADMIN': raise HTTPException(status_code=403, detail="የሱፐር አድሚን ፍቃድ ያስፈልጋል!")
        cursor.execute("UPDATE users SET password = %s WHERE username = %s", (new_password, target_username))
        conn.commit()
        return {"status": "success", "message": "የይለፍ ቃል ተቀይሯል!"}

@app.post("/api/admin/add-user")
def add_user(user: UserAdd):
    with get_db() as conn, conn.cursor() as cursor:
        user_role = user.role.strip().upper()
        if user_role in ["PM_TECH", "PM"]: user_role = "PM_TECH"
        elif user_role in ["BD_TECH", "BD"]: user_role = "BD_TECH"
        elif user_role in ["MT_TECH", "MT"]: user_role = "MT_TECH"
        elif user_role in ["ADMIN", "SUPER_ADMIN", "DEPO_ADMIN"]: pass
        else: raise HTTPException(status_code=400, detail="የተሳሳተ የባለሙያ ክፍል!")

        if user_role == "PM_TECH" and user.group_id is None:
            raise HTTPException(status_code=400, detail="ለPM ባለሙያ ግሩፕ መመረጥ አለበት!")
            
        try:
            cursor.execute("""
                INSERT INTO users (username, password, full_name, staff_id, gender, rank_level, role, depo_id, group_id, is_active)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 1)
            """, (user.username.strip().lower(), user.password, user.full_name, user.staff_id, user.gender, user.rank_level, user_role, user.depo_id, user.group_id))
            conn.commit()
            return {"status": "success", "message": f"ባለሙያ {user.full_name} ተመዝግቧል!"}
        except psycopg2.IntegrityError:
            raise HTTPException(status_code=400, detail="ይህ Username ወይም Staff ID ቀድሞ ተመዝግቧል!")

@app.post("/api/admin/add-vehicle")
def add_vehicle(veh: VehicleAdd):
    with get_db() as conn, conn.cursor() as cursor:
        try:
            cursor.execute("""
                INSERT INTO vehicles (plate_number, side_number, vehicle_type, assigned_group, depo_id, oil_limit_km, fuel_filter_limit_km, differential_oil_limit_km, steering_oil_limit_km, transmission_oil_limit_km, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'Active')
            """, (veh.plate_number.strip().upper(), veh.side_number.strip().upper(), veh.vehicle_type, veh.assigned_group, veh.depo_id, veh.oil_limit_km, veh.fuel_filter_limit_km, veh.differential_oil_limit_km, veh.steering_oil_limit_km, veh.transmission_oil_limit_km))
            conn.commit()
            return {"status": "success", "message": f"መኪና ታርጋ {veh.plate_number} ተመዝግቧል!"}
        except psycopg2.IntegrityError:
            raise HTTPException(status_code=400, detail="ይህ ታርጋ ወይም የጎን ቁጥር ቀድሞ ተመዝግቧል!")

@app.post("/api/maintenance/submit-log")
def submit_log(log: MaintenanceLogInput):
    with get_db() as conn, conn.cursor() as cursor:
        cursor.execute("SELECT role, group_id, is_active FROM users WHERE username = %s", (log.username.strip().lower(),))
        user = cursor.fetchone()
        if not user or user['is_active'] == 0: raise HTTPException(status_code=401, detail="ባለሙያው አልተመዘገበም ወይም ታግዷል!")
        
        user_role, user_group = user['role'], user['group_id']
        cursor.execute("SELECT * FROM vehicles WHERE side_number = %s AND depo_id = %s", (log.side_number.strip().upper(), log.depo_id))
        veh = cursor.fetchone()
        if not veh: raise HTTPException(status_code=404, detail="መኪናው በዚህ ዲፖ አልተገኘም!")
        
        veh_status, veh_group = veh['status'], veh['assigned_group']
        m_type = log.maintenance_type.strip().upper()
        
        if veh_status == "Frozen" and m_type == "PM":
            return {"status": "Locked", "message": "መኪናው ከአገልግሎት ውጪ በመሆኑ መረጃ መመዝገብ አይቻልም!"}
        
        alert = ""
        if m_type == "PM":
            if user_role not in ["ADMIN", "SUPER_ADMIN", "DEPO_ADMIN", "PM_TECH"]:
                raise HTTPException(status_code=403, detail="የማስገባት ፍቃድ የለዎትም!")
            if user_role == "PM_TECH" and int(user_group) != int(veh_group):
                raise HTTPException(status_code=403, detail="መኪናው የእርስዎ ግሩፕ አይደለም!")
                
            limits = {
                "የሞተር ዘይት": veh['oil_limit_km'], "የነዳጅ ፊልትር": veh['fuel_filter_limit_km'], 
                "የዲፍረንሻል ዘይት": veh['differential_oil_limit_km'], "የመሪ ዘይት": veh['steering_oil_limit_km'], 
                "የአውቶማቲክ ትራንስሚሽን ዘይት": veh['transmission_oil_limit_km']
            }
            overdue_items = [f"{label} (በ {log.entered_km - limit_km} ኪ.ሜ አልፏል)" for label, limit_km in limits.items() if limit_km and log.entered_km >= limit_km]
            alert = f"ይህ መኪና ስራ ደርሷል! " + ", ".join(overdue_items) if overdue_items else "P"
        elif m_type in ["BD", "MT"]: alert = f"የ{m_type} ስራ ተመዝግቧል!"

        current_time = log.created_at if log.created_at else datetime.now()
        cursor.execute("""
            INSERT INTO maintenance_logs (side_number, maintenance_type, entered_km, work_details, logged_by_user, depo_id, co_workers, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (log.side_number.strip().upper(), m_type, log.entered_km, log.work_details, log.username.strip().lower(), log.depo_id, log.co_workers, current_time))
        conn.commit()
        return {"status": "success", "alert_message": alert}

@app.get("/api/admin/check-12-days-alert")
def check_12_days_alert(depo_id: int):
    with get_db() as conn, conn.cursor() as cursor:
        cursor.execute("SELECT side_number, assigned_group FROM vehicles WHERE status = 'Active' AND depo_id = %s", (depo_id,))
        vehicles = cursor.fetchall()
        alerts = []
        twelve_days_ago = datetime.now() - timedelta(days=12)
        
        for veh in vehicles:
            cursor.execute("SELECT created_at FROM maintenance_logs WHERE side_number = %s AND maintenance_type = 'PM' ORDER BY created_at DESC LIMIT 1", (veh['side_number'],))
            last_log = cursor.fetchone()
            if not last_log or (isinstance(last_log['created_at'], str) and datetime.strptime(last_log['created_at'], "%Y-%m-%d %H:%M:%S") < twelve_days_ago) or (not isinstance(last_log['created_at'], str) and last_log['created_at'] < twelve_days_ago):
                alerts.append({"side_number": veh['side_number'], "group_id": veh['assigned_group'], "message": "ማስጠንቀቂያ! ይህ መኪና በ12 ቀናት ውስጥ PM አልተደረገለትም!"})
        return {"overdue_vehicles": alerts}

@app.get("/api/maintenance/logs")
def get_all_logs(depo_id: int, role: str):
    with get_db() as conn, conn.cursor() as cursor:
        query = """
            SELECT l.id, l.side_number, l.maintenance_type, l.entered_km, l.work_details, 
                   l.logged_by_user, l.depo_id, l.co_workers, l.created_at, u.full_name, v.assigned_group
            FROM maintenance_logs l
            JOIN users u ON l.logged_by_user = u.username
            LEFT JOIN vehicles v ON l.side_number = v.side_number
        """
        if role != 'SUPER_ADMIN':
            query += " WHERE l.depo_id = %s ORDER BY l.created_at DESC"
            cursor.execute(query, (depo_id,))
        else:
            query += " ORDER BY l.created_at DESC"
            cursor.execute(query)
        return cursor.fetchall()

# (Update Log, Delete Log, Update Status, Freeze Vehicle Endpoints can be added here using the same `with get_db() as conn, conn.cursor() as cursor:` pattern)
