from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime, timedelta
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from typing import Optional, List

app = FastAPI(title="Addis Ababa City Bus Garage Management System - Cloud Production Version")

# 🔓 CORS ፍቃድ ለሁሉም ክፍት ማድረጊያ
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 🔗 የNeon.tech ክላውድ ዳታቤዝ ሊንክ
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://neondb_owner:npg_oAtjGa1ZYnK7@ep-rapid-forest-atyx5bhs.c-9.us-east-1.aws.neon.tech/neondb?sslmode=require")

def get_db_connection():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

# --- Database Initialization ---
def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            full_name TEXT NOT NULL,
            staff_id TEXT UNIQUE NOT NULL,
            gender TEXT,
            rank_level TEXT,
            role TEXT NOT NULL,
            group_id INTEGER DEFAULT NULL,
            is_active INTEGER DEFAULT 1
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vehicles (
            id SERIAL PRIMARY KEY,
            plate_number TEXT UNIQUE NOT NULL,
            side_number TEXT UNIQUE NOT NULL,
            vehicle_type TEXT NOT NULL,
            assigned_group INTEGER,
            status TEXT DEFAULT 'Active',
            oil_limit_km INTEGER,
            fuel_filter_limit_km INTEGER,
            differential_oil_limit_km INTEGER,
            steering_oil_limit_km INTEGER,
            transmission_oil_limit_km INTEGER
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS maintenance_logs (
            id SERIAL PRIMARY KEY,
            side_number TEXT NOT NULL,
            maintenance_type TEXT NOT NULL,
            entered_km INTEGER NOT NULL,
            work_details TEXT NOT NULL,
            logged_by_user TEXT NOT NULL,
            co_workers TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # 🦸 ዋናውን ሱፐር አድሚን በራስ-ሰር መፍጠሪያ (ዳታቤዙ ባዶ ከሆነ)
    cursor.execute("SELECT COUNT(*) FROM users WHERE username = 'admin'")
    if cursor.fetchone()['count'] == 0:
        cursor.execute("""
            INSERT INTO users (username, password, full_name, staff_id, gender, rank_level, role, group_id, is_active)
            VALUES ('admin', 'admin123', 'ዋና ሲስተም አድሚን', 'STAFF-001', 'Male', 'Level 5', 'ADMIN', NULL, 1)
        """)
        
    conn.commit()
    cursor.close()
    conn.close()

try:
    init_db()
except Exception as e:
    print(f"Database connection failed: {e}")

# --- Pydantic Data Models ---
class UserAdd(BaseModel):
    username: str
    password: str
    full_name: str
    staff_id: str
    gender: str
    rank_level: str
    role: str
    group_id: Optional[int] = None

class VehicleAdd(BaseModel):
    plate_number: str
    side_number: str
    vehicle_type: str
    assigned_group: int
    oil_limit_km: int
    fuel_filter_limit_km: int
    differential_oil_limit_km: int
    steering_oil_limit_km: int
    transmission_oil_limit_km: int

class MaintenanceLogInput(BaseModel):
    side_number: str
    maintenance_type: str
    entered_km: int
    work_details: str
    username: str
    co_workers: Optional[str] = ""
    created_at: Optional[str] = None

class MaintenanceLogUpdate(BaseModel):
    entered_km: int
    work_details: str
    co_workers: Optional[str] = ""

class LoginInput(BaseModel):
    username: str
    password: str

# --- API Endpoints ---

@app.post("/api/login")
def login(data: LoginInput):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT role, group_id, is_active, full_name, username FROM users WHERE username = %s AND password = %s", (data.username.strip().lower(), data.password))
    user = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if not user:
        raise HTTPException(status_code=401, detail="የተሳሳተ Username ወይም Password!")
    if user['is_active'] == 0:
        raise HTTPException(status_code=403, detail="ይህ አካውንት በAdmin ታግዷል!")
        
    return {
        "status": "success", 
        "role": user['role'], 
        "group_id": user['group_id'], 
        "full_name": user['full_name'],
        "username": user['username']
    }

@app.post("/api/admin/add-user")
def add_user(user: UserAdd):
    conn = get_db_connection()
    cursor = conn.cursor()
    user_role = user.role.strip().upper()
    
    if user_role in ["PM_TECH", "PM"]: user_role = "PM_TECH"
    elif user_role in ["BD_TECH", "BD"]: user_role = "BD_TECH"
    elif user_role in ["MT_TECH", "MT"]: user_role = "MT_TECH"
    elif user_role in ["ADMIN"]: user_role = "ADMIN"
    else: 
        cursor.close()
        conn.close()
        raise HTTPException(status_code=400, detail="የተሳሳተ የባለሙያ ክፍል!")

    if user_role == "PM_TECH" and user.group_id is None:
        cursor.close()
        conn.close()
        raise HTTPException(status_code=400, detail="ለPM ባለሙያ ግሩፕ መመረጥ አለበት!")
        
    try:
        cursor.execute("""
            INSERT INTO users (username, password, full_name, staff_id, gender, rank_level, role, group_id, is_active)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 1)
        """, (user.username.strip().lower(), user.password, user.full_name, user.staff_id, user.gender, user.rank_level, user_role, user.group_id))
        conn.commit()
        return {"status": "success", "message": f"ባለሙያ {user.full_name} በትክክል ተመዝግቧል!"}
    except psycopg2.IntegrityError:
        raise HTTPException(status_code=400, detail="ይህ Username ወይም Staff ID ቀድሞ ተመዝግቧል!")
    finally:
        cursor.close()
        conn.close()

@app.post("/api/admin/add-vehicle")
def add_vehicle(veh: VehicleAdd):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO vehicles (plate_number, side_number, vehicle_type, assigned_group, oil_limit_km, fuel_filter_limit_km, differential_oil_limit_km, steering_oil_limit_km, transmission_oil_limit_km, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'Active')
        """, (veh.plate_number.strip().upper(), veh.side_number.strip().upper(), veh.vehicle_type, veh.assigned_group, veh.oil_limit_km, veh.fuel_filter_limit_km, veh.differential_oil_limit_km, veh.steering_oil_limit_km, veh.transmission_oil_limit_km))
        conn.commit()
        return {"status": "success", "message": f"መኪና ታርጋ {veh.plate_number} በትክክል ተመዝግቧል!"}
    except psycopg2.IntegrityError:
        raise HTTPException(status_code=400, detail="ይህ ታርጋ ወይም የጎን ቁጥር ቀድሞ ተመዝግቧል!")
    finally:
        cursor.close()
        conn.close()

@app.get("/api/admin/users")
def list_users():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT username, full_name, staff_id, role, group_id, is_active FROM users ORDER BY role, username")
    users = cursor.fetchall()
    cursor.close()
    conn.close()
    return users

@app.get("/api/admin/vehicles")
def list_vehicles():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT plate_number, side_number, vehicle_type, assigned_group, status FROM vehicles ORDER BY side_number")
    vehicles = cursor.fetchall()
    cursor.close()
    conn.close()
    return vehicles

@app.put("/api/admin/update-user-status")
def update_user_status(username: str, action: str, new_group: Optional[int] = None):
    conn = get_db_connection()
    cursor = conn.cursor()
    act = action.strip().lower()
    if act == "suspend":
        cursor.execute("UPDATE users SET is_active = 0 WHERE username = %s", (username,))
    elif act == "activate":
        cursor.execute("UPDATE users SET is_active = 1 WHERE username = %s", (username,))
    elif act == "transfer" and new_group:
        cursor.execute("UPDATE users SET group_id = %s WHERE username = %s", (new_group, username))
    conn.commit()
    cursor.close()
    conn.close()
    return {"status": "success", "message": "የባለሙያው መረጃ ተስተካክሏል!"}

@app.put("/api/admin/freeze-vehicle")
def freeze_vehicle(side_number: str, action: str):
    status = "Frozen" if action.strip().lower() == "freeze" else "Active"
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE vehicles SET status = %s WHERE side_number = %s", (status, side_number.strip().upper()))
    conn.commit()
    cursor.close()
    conn.close()
    return {"status": "success", "message": f"የ... ሁኔታ ወደ {status} ተቀይሯል!"}

@app.put("/api/admin/update-log/{log_id}")
def update_log(log_id: int, log_data: MaintenanceLogUpdate):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT created_at FROM maintenance_logs WHERE id = %s", (log_id,))
    log = cursor.fetchone()
    if not log:
        cursor.close()
        conn.close()
        raise HTTPException(status_code=404, detail="መዝገቡ አልተገኘም!")
        
    log_time = log['created_at']
    if isinstance(log_time, str):
        log_time = datetime.strptime(log_time, "%Y-%m-%d %H:%M:%S")
        
    if datetime.now() - log_time > timedelta(days=1):
        cursor.close()
        conn.close()
        raise HTTPException(status_code=403, detail="ከ1 ቀን በላይ የቆየ መረጃ ማስተካከል አይቻልም!")
        
    cursor.execute("""
        UPDATE maintenance_logs 
        SET entered_km = %s, work_details = %s, co_workers = %s
        WHERE id = %s
    """, (log_data.entered_km, log_data.work_details, log_data.co_workers, log_id))
    conn.commit()
    cursor.close()
    conn.close()
    return {"status": "success", "message": "መዝገቡ በትክክል ተስተካክሏል!"}

@app.delete("/api/admin/delete-log/{log_id}")
def delete_log(log_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT created_at FROM maintenance_logs WHERE id = %s", (log_id,))
    log = cursor.fetchone()
    if not log:
        cursor.close()
        conn.close()
        raise HTTPException(status_code=404, detail="መዝገቡ አልተገኘም!")
        
    log_time = log['created_at']
    if isinstance(log_time, str):
        log_time = datetime.strptime(log_time, "%Y-%m-%d %H:%M:%S")
        
    if datetime.now() - log_time > timedelta(days=1):
        cursor.close()
        conn.close()
        raise HTTPException(status_code=403, detail="ከ1 ቀን በላይ የቆየ መረጃ ማጥፋት አይቻልም!")
        
    cursor.execute("DELETE FROM maintenance_logs WHERE id = %s", (log_id,))
    conn.commit()
    cursor.close()
    conn.close()
    return {"status": "success", "message": "መዝገቡ በትክክል ጠፍቷል!"}

@app.post("/api/maintenance/submit-log")
def submit_log(log: MaintenanceLogInput):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT role, group_id, is_active FROM users WHERE username = %s", (log.username.strip().lower(),))
    user = cursor.fetchone()
    if not user or user['is_active'] == 0:
        cursor.close()
        conn.close()
        raise HTTPException(status_code=401, detail="ባለሙያው አልተመዘገበም ወይም ታግዷል!")
        
    user_role, user_group = user['role'], user['group_id']
    
    cursor.execute("""
        SELECT status, assigned_group, oil_limit_km, fuel_filter_limit_km, 
               differential_oil_limit_km, steering_oil_limit_km, transmission_oil_limit_km 
        FROM vehicles WHERE side_number = %s
    """, (log.side_number.strip().upper(),))
    veh = cursor.fetchone()
    if not veh:
        cursor.close()
        conn.close()
        raise HTTPException(status_code=404, detail="መኪናው በሲስተሙ ላይ አልተገኘም!")
        
    veh_status, veh_group = veh['status'], veh['assigned_group']
    m_type = log.maintenance_type.strip().upper()
    
    if veh_status == "Frozen" and m_type == "PM":
        cursor.close()
        conn.close()
        return {"status": "Locked", "message": "ለጊዜው የቆመ መላሽ፡ መኪናው ከአገልግሎት ውጪ በመሆኑ መረጃ መመዝገብ አይቻልም!"}
    
    alert = ""
    
    if m_type == "PM":
        if user_role != "ADMIN" and user_role != "PM_TECH":
            cursor.close()
            conn.close()
            raise HTTPException(status_code=403, detail="የማስገባት ፍቃድ የለዎትም!")
        if user_role == "PM_TECH" and int(user_group) != int(veh_group):
            cursor.close()
            conn.close()
            raise HTTPException(status_code=403, detail="የማስገባት ፍቃድ የለዎትም! መኪናው የእርስዎ ግሩፕ አይደለም።")
            
        limits = {
            "የሞተር ዘይት": veh['oil_limit_km'], "የነዳጅ ፊልትር": veh['fuel_filter_limit_km'], "የዲፍረንሻል ዘይት": veh['differential_oil_limit_km'],
            "የመሪ ዘይት": veh['steering_oil_limit_km'], "የአውቶማቲክ ትራንስሚሽን ዘይት": veh['transmission_oil_limit_km']
        }
        
        overdue_items = []
        for label, limit_km in limits.items():
            if limit_km and log.entered_km >= limit_km:
                overdue_items.append(f"{label} (በ {log.entered_km - limit_km} ኪ.ሜ አልፏል)")
        
        if overdue_items:
            alert = f"ይህ መኪና ስራ ደርሷል! " + ", ".join(overdue_items)
        else:
            alert = "P"
            
    elif m_type == "BD":
        alert = f"የBD ስራ በትክክል ተመዝግቧል!"
    elif m_type == "MT":
        alert = f"የMT ስራ በትክክል ተመዝግቧል!"

    current_time = log.created_at if log.created_at else datetime.now()
    
    cursor.execute("""
        INSERT INTO maintenance_logs (side_number, maintenance_type, entered_km, work_details, logged_by_user, co_workers, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (log.side_number.strip().upper(), m_type, log.entered_km, log.work_details, log.username.strip().lower(), log.co_workers, current_time))
    
    conn.commit()
    cursor.close()
    conn.close()
    return {"status": "success", "alert_message": alert}

@app.get("/api/admin/check-12-days-alert")
def check_12_days_alert():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT side_number, assigned_group FROM vehicles WHERE status = 'Active'")
    vehicles = cursor.fetchall()
    
    alerts = []
    twelve_days_ago = datetime.now() - timedelta(days=12)
    
    for veh in vehicles:
        side_num, group_id = veh['side_number'], veh['assigned_group']
        cursor.execute("""
            SELECT created_at FROM maintenance_logs
            WHERE side_number = %s AND maintenance_type = 'PM'
            ORDER BY created_at DESC LIMIT 1
        """, (side_num,))
        last_log = cursor.fetchone()
        if last_log:
            last_log_time = last_log['created_at']
            if isinstance(last_log_time, str):
                last_log_time = datetime.strptime(last_log_time, "%Y-%m-%d %H:%M:%S")
            if last_log_time < twelve_days_ago:
                alerts.append({"side_number": side_num, "group_id": group_id, "message": "ማስጠንቀቂያ! ይህ መኪና በ12 ቀናት ውስጥ PM አልተደረገለትም!"})
        else:
            alerts.append({"side_number": side_num, "group_id": group_id, "message": "ማስጠንቀቂያ! ይህ መኪና በ12 ቀናት ውስጥ PM አልተደረገለትም!"})
            
    cursor.close()
    conn.close()
    return {"overdue_vehicles": alerts}

@app.get("/api/maintenance/logs")
def get_all_logs():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT l.id, l.side_number, l.maintenance_type, l.entered_km, l.work_details, 
               l.logged_by_user, l.co_workers, l.created_at, u.full_name, v.assigned_group
        FROM maintenance_logs l
        JOIN users u ON l.logged_by_user = u.username
        LEFT JOIN vehicles v ON l.side_number = v.side_number
        ORDER BY l.created_at DESC
    """)
    logs = cursor.fetchall()
    cursor.close()
    conn.close()
    return logs

@app.get("/api/history/by-date")
def get_history_by_date(date_str: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT l.*, u.full_name 
        FROM maintenance_logs l
        JOIN users u ON l.logged_by_user = u.username
        WHERE l.created_at::date = %s::date 
        ORDER BY l.created_at DESC
    """, (date_str,))
    logs = cursor.fetchall()
    cursor.close()
    conn.close()
    return {"logs": logs}
