from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime, timedelta
import os, psycopg2
from psycopg2.extras import RealDictCursor
from typing import Optional, List

app = FastAPI(title="Addis Ababa City Bus Garage M.S ")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://neondb_owner:npg_oAtjGa1ZYnK7@ep-rapid-forest-atyx5bhs-pooler.c-9.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require")

def get_db(): 
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

def init_db():
    with get_db() as conn, conn.cursor() as cursor:
        # Users Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY, username TEXT UNIQUE NOT NULL, password TEXT NOT NULL,
                full_name TEXT NOT NULL, staff_id TEXT UNIQUE NOT NULL, gender TEXT, rank_level TEXT,
                role TEXT NOT NULL, depo_id INTEGER NOT NULL, group_id INTEGER DEFAULT NULL, 
                is_active INTEGER DEFAULT 1, emp_status TEXT DEFAULT 'Active',
                can_add INTEGER DEFAULT 1, can_edit INTEGER DEFAULT 0, can_delete INTEGER DEFAULT 0
            )
        """)
        # User History / Audit Log for Evaluation
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_history (
                id SERIAL PRIMARY KEY, username TEXT NOT NULL, action_type TEXT NOT NULL,
                description TEXT NOT NULL, done_by TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Vehicles Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS vehicles (
                id SERIAL PRIMARY KEY, plate_number TEXT UNIQUE NOT NULL, side_number TEXT UNIQUE NOT NULL,
                vehicle_type TEXT NOT NULL, assigned_group INTEGER NOT NULL, depo_id INTEGER NOT NULL, 
                status TEXT DEFAULT 'Active', oil_limit_km INTEGER DEFAULT 0, fuel_filter_limit_km INTEGER DEFAULT 0, 
                differential_oil_limit_km INTEGER DEFAULT 0, steering_oil_limit_km INTEGER DEFAULT 0, 
                transmission_oil_limit_km INTEGER DEFAULT 0
            )
        """)
        # Maintenance Logs Table with Verification Flow
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS maintenance_logs (
                id SERIAL PRIMARY KEY, side_number TEXT NOT NULL, maintenance_type TEXT NOT NULL,
                entered_km INTEGER NOT NULL, work_details TEXT NOT NULL, logged_by_user TEXT NOT NULL,
                depo_id INTEGER NOT NULL, co_workers TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'Pending', inspection_remark TEXT DEFAULT '', inspected_by TEXT DEFAULT ''
            )
        """)
        
        # Insert Default Super Admin if missing
        cursor.execute("SELECT COUNT(*) FROM users WHERE username = 'admin'")
        if cursor.fetchone()['count'] == 0:
            cursor.execute("""
                INSERT INTO users (username, password, full_name, staff_id, gender, rank_level, role, depo_id, is_active, can_add, can_edit, can_delete)
                VALUES ('admin', 'admin123', 'ዋና ሱፐር አድሚን', 'STAFF-000', 'Male', 'Level 5', 'SUPER_ADMIN', 0, 1, 1, 1, 1)
            """)
        conn.commit()

try: 
    init_db()
except Exception as e: 
    print(f"DB Update Error: {e}")

# --- Pydantic Schemes ---
class LoginInput(BaseModel):
    username: str
    password: str
    depo_id: Optional[int] = None
    is_admin_login: bool = False 

class UserAdd(BaseModel):
    username: str
    password: str
    full_name: str
    staff_id: str
    gender: str
    rank_level: str
    role: str
    depo_id: int
    group_id: Optional[int] = None
    can_add: int = 1
    can_edit: int = 0
    can_delete: int = 0

class VehicleAdd(BaseModel):
    plate_number: str
    side_number: str
    vehicle_type: str
    assigned_group: int
    depo_id: int
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
    depo_id: int
    co_workers: Optional[str] = ""

class InspectionProcessInput(BaseModel):
    log_id: int
    status: str
    remark: Optional[str] = ""
    inspector_username: str

class TransferEmployeeInput(BaseModel):
    username: str
    new_depo_id: int
    new_group_id: Optional[int] = None
    new_role: str
    admin_username: str
    reason: str

class ChangeStatusInput(BaseModel):
    username: str
    new_status: str
    admin_username: str
    reason: str

class PasswordChangeInput(BaseModel):
    username: str
    old_password: Optional[str] = None
    new_password: str
    is_reset: bool = False
    admin_username: Optional[str] = None

# --- API Endpoints ---

@app.post("/api/login")
def login(data: LoginInput):
    with get_db() as conn, conn.cursor() as cursor:
        cursor.execute("SELECT * FROM users WHERE username = %s AND password = %s", (data.username.strip().lower(), data.password))
        user = cursor.fetchone()
        if not user: 
            raise HTTPException(401, "የተሳሳተ Username ወይም Password!")
        
        # 🛠️ ክብ ቅንፍ በመጠቀም የተስተካከለ ስህተት (Fixing .get syntax error)
        if user.get('is_active') == 0 or user.get('emp_status') == 'Resigned': 
            raise HTTPException(403, "ይህ አካውንት ተዘግቷል/ከስራ ለቋል!")

        if not data.is_admin_login:
            if user.get('role') not in ['PM_TECH', 'BD_TECH', 'MT_TECH', 'INSPECTION']:
                raise HTTPException(403, "የባለሙያ መግቢያን ይጠቀሙ!")
            if user['depo_id'] != data.depo_id:
                raise HTTPException(403, f"እርስዎ የዲፖ {data.depo_id} ባለሙያ አይደሉም!")
        else:
            if user['role'] not in ['SUPER_ADMIN', 'DEPO_ADMIN']:
                raise HTTPException(403, "የአድሚንነት መብት የለዎትም!")
        return user

@app.post("/api/maintenance/submit-log")
def submit_log(log: MaintenanceLogInput):
    with get_db() as conn, conn.cursor() as cursor:
        cursor.execute("SELECT * FROM users WHERE username = %s", (log.username.lower(),))
        user = cursor.fetchone()
        if not user or user['is_active'] == 0: 
            raise HTTPException(401, "የእርስዎ መለያ አልተገኘም ወይም ታግዷል!")
        if user['can_add'] == 0: 
            raise HTTPException(403, "መረጃ የመመዝገብ መብትዎ በአድሚን ታግዷል!")
        
        cursor.execute("SELECT * FROM vehicles WHERE side_number = %s", (log.side_number.upper(),))
        veh = cursor.fetchone()
        if not veh: 
            raise HTTPException(404, "ይህ የጎን ቁጥር ያለው መኪና በሲስተሙ አልተመዘገበም!")
        
        # Data Validation: Check Mileage (KM Protection Guard)
        cursor.execute("SELECT entered_km FROM maintenance_logs WHERE side_number = %s ORDER BY entered_km DESC LIMIT 1", (log.side_number.upper(),))
        last_log = cursor.fetchone()
        if last_log and log.entered_km < last_log['entered_km']:
            raise HTTPException(400, f"ስህተት፡ የገባው ኪሎሜትር ({log.entered_km}) ከመኪናው የቀድሞ ማይልስ ({last_log['entered_km']}) ሊያንስ አይችልም!")
            
        m_type = log.maintenance_type.upper()
        alert = "ስራው በተሳካ ሁኔታ ተመዝግቧል። የኢንስፔክሽን ማረጋገጫ ይጠብቃል።"

        if m_type == "PM":
            if user['role'] == "PM_TECH" and user['group_id'] != veh['assigned_group']:
                raise HTTPException(403, "ይህ መኪና በእርስዎ ግሩፕ ስር አይደለም! መመዝገብ አይችሉም።")
            if veh['status'] == "Frozen":
                raise HTTPException(403, "መኪናው 'ለጊዜው የቆመ' ስለሆነ የ PM ስራ መመዝገብ አይቻልም! (BD/MT ብቻ)")
                
            limits = {"የሞተር ዘይት": veh['oil_limit_km'], "የነዳጅ ፊልትር": veh['fuel_filter_limit_km']}
            overdue = [f"{lbl} ({log.entered_km - lim} ኪ.ሜ አልፏል)" for lbl, lim in limits.items() if lim > 0 and log.entered_km >= lim]
            if overdue: 
                alert = "ማስጠንቀቂያ! " + ", ".join(overdue)

        cursor.execute("""
            INSERT INTO maintenance_logs (side_number, maintenance_type, entered_km, work_details, logged_by_user, depo_id, co_workers, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'Pending')
        """, (log.side_number.upper(), m_type, log.entered_km, log.work_details, user['username'], log.depo_id, log.co_workers))
        
        # Record task to user's personal log for performance review
        cursor.execute("""
            INSERT INTO user_history (username, action_type, description, done_by)
            VALUES (%s, 'WORK_LOG', %s, %s)
        """, (user['username'], f"መኪና {log.side_number} ላይ የ {m_type} ስራ ሰርቷል:: ኪ.ሜ: {log.entered_km}", user['username']))
        
        conn.commit()
        return {"status": "success", "alert_message": alert}

@app.post("/api/inspection/process")
def process_inspection(data: InspectionProcessInput):
    with get_db() as conn, conn.cursor() as cursor:
        cursor.execute("SELECT role FROM users WHERE username = %s", (data.inspector_username.lower(),))
        inspector = cursor.fetchone()
        if not inspector or inspector['role'] not in ['INSPECTION', 'SUPER_ADMIN', 'DEPO_ADMIN']:
            raise HTTPException(403, "ይህንን ተግባር ለመፈጸም የኢንስፔክሽን ባለሙያ መሆን አለብዎት!")
            
        cursor.execute("UPDATE maintenance_logs SET status = %s, inspection_remark = %s, inspected_by = %s WHERE id = %s",
                       (data.status, data.remark, data.inspector_username, data.log_id))
        conn.commit()
        return {"status": "success", "message": f"የምርመራ ውጤት ({data.status}) ተመዝግቧል!"}

@app.post("/api/admin/transfer-employee")
def transfer_employee(data: TransferEmployeeInput):
    with get_db() as conn, conn.cursor() as cursor:
        cursor.execute("UPDATE users SET depo_id = %s, group_id = %s, role = %s WHERE username = %s",
                       (data.new_depo_id, data.new_group_id, data.new_role, data.username.lower()))
        
        desc = f"ከዲፖ ወደ ዲፖ ተዛወረ:: አዲስ ዲፖ: {data.new_depo_id}፣ አዲስ ግሩፕ: {data.new_group_id}፣ አዲስ የስራ መደብ: {data.new_role}:: ምክንያት: {data.reason}"
        cursor.execute("""
            INSERT INTO user_history (username, action_type, description, done_by)
            VALUES (%s, 'TRANSFER', %s, %s)
        """, (data.username.lower(), desc, data.admin_username))
        conn.commit()
        return {"status": "success", "message": "የሰራተኛ ዝውውር ታሪክ ተመዝግቧል!"}

@app.post("/api/admin/change-employee-status")
def change_employee_status(data: ChangeStatusInput):
    with get_db() as conn, conn.cursor() as cursor:
        cursor.execute("UPDATE users SET emp_status = %s, is_active = %s WHERE username = %s",
                       (data.new_status, 1 if data.new_status == 'Active' else 0, data.username.lower()))
        
        desc = f"የሰራተኛው ሁኔታ ተቀየረ:: አዲስ ሁኔታ: {data.new_status}:: ምክንያት: {data.reason}"
        cursor.execute("""
            INSERT INTO user_history (username, action_type, description, done_by)
            VALUES (%s, 'STATUS_CHANGE', %s, %s)
        """, (data.username.lower(), desc, data.admin_username))
        conn.commit()
        return {"status": "success", "message": "የሰራተኛው የስራ ሁኔታ ተቀይሯል!"}

@app.get("/api/profile/employee/{username}")
def get_employee_profile(username: str):
    with get_db() as conn, conn.cursor() as cursor:
        cursor.execute("SELECT id, username, full_name, staff_id, role, depo_id, group_id, emp_status, rank_level FROM users WHERE username = %s", (username.lower(),))
        info = cursor.fetchone()
        if not info: 
            raise HTTPException(404, "ሰራተኛው አልተገኘም!")
        
        cursor.execute("SELECT * FROM user_history WHERE username = %s ORDER BY created_at DESC", (username.lower(),))
        history = cursor.fetchall()
        return {"info": info, "history": history}

@app.get("/api/profile/vehicle/{side_number}")
def get_vehicle_profile(side_number: str):
    with get_db() as conn, conn.cursor() as cursor:
        cursor.execute("SELECT * FROM vehicles WHERE side_number = %s", (side_number.upper(),))
        info = cursor.fetchone()
        if not info: 
            raise HTTPException(404, "መኪናው አልተገኘም!")
        
        cursor.execute("""
            SELECT l.*, u.full_name FROM maintenance_logs l 
            JOIN users u ON l.logged_by_user = u.username 
            WHERE l.side_number = %s ORDER BY l.created_at DESC
        """, (side_number.upper(),))
        work_logs = cursor.fetchall()
        return {"info": info, "work_logs": work_logs}

@app.post("/api/change-password")
def change_password(data: PasswordChangeInput):
    with get_db() as conn, conn.cursor() as cursor:
        if data.is_reset:
            cursor.execute("SELECT role FROM users WHERE username = %s", (data.admin_username.lower(),))
            adm = cursor.fetchone()
            if not adm or adm['role'] not in ['SUPER_ADMIN', 'DEPO_ADMIN']:
                raise HTTPException(403, "ይህን ለማድረግ የአድሚን ፍቃድ ያስፈልጋል!")
            cursor.execute("UPDATE users SET password = %s WHERE username = %s", (data.new_password, data.username.lower()))
        else:
            cursor.execute("SELECT id FROM users WHERE username = %s AND password = %s", (data.username.lower(), data.old_password))
            if not cursor.fetchone(): 
                raise HTTPException(401, "የድሮው የይለፍ ቃል ተሳስቷል!")
            cursor.execute("UPDATE users SET password = %s WHERE username = %s", (data.new_password, data.username.lower()))
        conn.commit()
        return {"status": "success", "message": "የይለፍ ቃል ተቀይሯል!"}

# 🆕 የ PM ግሩፕ መኪኖችን ዝርዝር ለይቶ ለማውጣት የተጨመረ አዲስ ኤፒአይ
@app.get("/api/vehicles")
def get_vehicles(depo_id: int):
    with get_db() as conn, conn.cursor() as cursor:
        cursor.execute("SELECT * FROM vehicles WHERE depo_id = %s AND status = 'Active'", (depo_id,))
        return cursor.fetchall()

@app.get("/api/logs")
def get_logs(depo_id: int, role: str, side_number: Optional[str] = None, filter_status: Optional[str] = "ALL"):
    with get_db() as conn, conn.cursor() as cursor:
        # 🛠️ u.username ን 'username' በሚል ስያሜ አውጥተነዋል (እንዲሁም l.logged_by_user)
        query = "SELECT l.*, l.logged_by_user AS username, u.full_name FROM maintenance_logs l JOIN users u ON l.logged_by_user = u.username WHERE 1=1"
        params = []
        if role != 'SUPER_ADMIN':
            query += " AND l.depo_id = %s"; params.append(depo_id)
        if side_number:
            query += " AND l.side_number = %s"; params.append(side_number.upper())
        if filter_status == "PM":
            query += " AND l.maintenance_type = 'PM'"
        elif filter_status == "BD":
            query += " AND l.maintenance_type IN ('BD', 'MT')"
            
        query += " ORDER BY l.created_at DESC"
        cursor.execute(query, tuple(params))
        return cursor.fetchall()

@app.delete("/api/logs/{log_id}")
def delete_log(log_id: int, username: str):
    with get_db() as conn, conn.cursor() as cursor:
        cursor.execute("SELECT role, can_delete FROM users WHERE username = %s", (username.lower(),))
        user = cursor.fetchone()
        if not user or (user['role'] not in ['SUPER_ADMIN', 'DEPO_ADMIN'] and user['can_delete'] == 0):
            raise HTTPException(403, "የማጥፋት ፍቃድ የለዎትም!")
            
        cursor.execute("SELECT created_at FROM maintenance_logs WHERE id = %s", (log_id,))
        log = cursor.fetchone()
        if not log: 
            raise HTTPException(404, "መዝገብ አልተገኘም!")
        if datetime.now() - log['created_at'] > timedelta(days=1) and user['role'] != 'SUPER_ADMIN':
            raise HTTPException(403, "ከ1 ቀን በላይ የቆየ መረጃ ማጥፋት የሚችለው ዋና ሱፐር አድሚን ብቻ ነው!")
            
        cursor.execute("DELETE FROM maintenance_logs WHERE id = %s", (log_id,))
        conn.commit()
        return {"status": "success"}

@app.post("/api/admin/add-user")
def add_user(user: UserAdd):
    with get_db() as conn, conn.cursor() as cursor:
        role = user.role.strip().upper()
        if role == "PM_TECH" and (user.group_id is None or user.group_id not in [1, 2, 3, 4]):
            raise HTTPException(400, "PM ባለሙያ ከ4ቱ አንዱ ግሩፕ ሊሰጠው ይገባል!")
        if role in ["BD_TECH", "MT_TECH", "INSPECTION", "DEPO_ADMIN"]: 
            user.group_id = None
        
        try:
            cursor.execute("""
                INSERT INTO users (username, password, full_name, staff_id, gender, rank_level, role, depo_id, group_id, is_active, can_add, can_edit, can_delete)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 1, %s, %s, %s)
            """, (user.username.lower(), user.password, user.full_name, user.staff_id, user.gender, user.rank_level, role, user.depo_id, user.group_id, user.can_add, user.can_edit, user.can_delete))
            conn.commit()
            return {"status": "success", "message": "ሰራተኛው በተሳካ ሁኔታ ተመዝግቧል!"}
        except psycopg2.IntegrityError:
            raise HTTPException(400, "ይህ Username ወይም Staff ID ቀድሞ ተመዝግቧል!")

@app.post("/api/admin/add-vehicle")
def add_vehicle(veh: VehicleAdd):
    with get_db() as conn, conn.cursor() as cursor:
        try:
            cursor.execute("""
                INSERT INTO vehicles (plate_number, side_number, vehicle_type, assigned_group, depo_id, oil_limit_km, fuel_filter_limit_km, differential_oil_limit_km, steering_oil_limit_km, transmission_oil_limit_km, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'Active')
            """, (veh.plate_number.upper(), veh.side_number.upper(), veh.vehicle_type, veh.assigned_group, veh.depo_id, veh.oil_limit_km, veh.fuel_filter_limit_km, veh.differential_oil_limit_km, veh.steering_oil_limit_km, veh.transmission_oil_limit_km))
            conn.commit()
            return {"status": "success"}
        except psycopg2.IntegrityError:
            raise HTTPException(400, "ይህ ታርጋ ወይም የጎን ቁጥር ቀድሞ ተመዝግቧል!")

@app.put("/api/admin/freeze-vehicle")
def freeze_vehicle(side_number: str, action: str):
    with get_db() as conn, conn.cursor() as cursor:
        status = "Frozen" if action == "freeze" else "Active"
        cursor.execute("UPDATE vehicles SET status = %s WHERE side_number = %s", (side_number.upper(),))
        conn.commit()
        return {"status": "success"}

# --- Export Document (DOC Form) for Weekly/Daily Report ---
@app.get("/api/reports/export-doc")
def export_doc(depo_id: int, role: str):
    with get_db() as conn, conn.cursor() as cursor:
        query = """
            SELECT l.*, u.full_name 
            FROM maintenance_logs l 
            JOIN users u ON l.logged_by_user = u.username 
            WHERE 1=1
        """
        params = []
        if role != 'SUPER_ADMIN':
            query += " AND l.depo_id = %s"; params.append(depo_id)
        query += " ORDER BY l.created_at DESC"
        cursor.execute(query, tuple(params))
        records = cursor.fetchall()
        
        # Build MS Word compatible HTML layout
        doc_content = """
        <html xmlns:o='urn:schemas-microsoft-com:office:office' xmlns:w='urn:schemas-microsoft-com:office:word' xmlns='http://www.w3.org/TR/REC-html40'>
        <head><title>Garage Maintenance Report</title>
        <style>
            table { border-collapse: collapse; width: 100%; }
            th, td { border: 1px solid black; padding: 8px; font-family: Arial; font-size: 11pt; }
            th { background-color: #D3D3D3; }
            h2 { font-family: Arial; text-align: center; }
        </style>
        </head>
        <body>
        <h2>የአዲስ አበባ አውቶቡስ ጋራዥ የጥገና ሪፖርት</h2>
        <p>ቀን፡ """ + datetime.now().strftime('%Y-%m-%d %H:%M') + """</p>
        <table>
            <tr>
                <th>ቀን</th><th>ዲፖ</th><th>የጎን ቁጥር</th><th>የስራ አይነት</th><th>ኪ.ሜ</th><th>ዝርዝር ስራ</th><th>ባለሙያ</th><th>አብረው የሰሩ</th><th>ኢንስፔክሽን</th>
            </tr>
        """
        for r in records:
            doc_content += f"""
            <tr>
                <td>{r['created_at'].strftime('%Y-%m-%d')}</td>
                <td>ዲፖ {r['depo_id']}</td>
                <td>{r['side_number']}</td>
                <td>{r['maintenance_type']}</td>
                <td>{r['entered_km']}</td>
                <td>{r['work_details']}</td>
                <td>{r['full_name']}</td>
                <td>{r['co_workers'] or '-'}</td>
                <td>{r['status']} ({r['inspection_remark'] or '-'})</td>
            </tr>
            """
        doc_content += "</table></body></html>"
        
        headers = {"Content-Disposition": f"attachment; filename=Garage_Report_{datetime.now().strftime('%Y%m%d')}.doc"}
        return Response(content=doc_content, media_type="application/msword", headers=headers)
