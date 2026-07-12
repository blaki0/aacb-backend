from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import psycopg2
from psycopg2.extras import RealDictCursor
import os

app = FastAPI()

# የ CORS መቼት (Netlify እና ሌሎች እንዲገናኙ)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_methods=["*"],
    allow_headers=["*"],
)

DATABASE_URL = os.environ.get("DATABASE_URL") # በRender ውስጥ የተዋቀረ

def get_db(): 
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

class LogInput(BaseModel):
    side_number: str
    maintenance_type: str
    entered_km: int
    work_details: str
    username: str
    depo_id: int

@app.post("/api/maintenance/submit-log")
def submit_log(log: LogInput):
    with get_db() as conn, conn.cursor() as cursor:
        # አዲሱ Validation: ኪሎሜትር ማረጋገጫ
        cursor.execute("SELECT entered_km FROM maintenance_logs WHERE side_number = %s ORDER BY created_at DESC LIMIT 1", (log.side_number.upper(),))
        last = cursor.fetchone()
        if last and log.entered_km < last['entered_km']:
            raise HTTPException(400, "ስህተት! የገባው ኪሎሜትር ከቀድሞው ያነሰ ነው።")
        
        # የድሮው የመረጃ ማስገቢያ (Insertion)
        cursor.execute("""
            INSERT INTO maintenance_logs (side_number, maintenance_type, entered_km, work_details, logged_by_user, depo_id, status)
            VALUES (%s, %s, %s, %s, %s, %s, 'Pending')
        """, (log.side_number.upper(), log.maintenance_type, log.entered_km, log.work_details, log.username.lower(), log.depo_id))
        conn.commit()
        return {"status": "success"}

@app.get("/api/dashboard/stats")
def get_stats(depo_id: int):
    # አዲሱ Stats Dashboard
    with get_db() as conn, conn.cursor() as cursor:
        cursor.execute("SELECT status, COUNT(*) FROM maintenance_logs WHERE depo_id = %s GROUP BY status", (depo_id,))
        rows = cursor.fetchall()
        stats = {"Pending": 0, "Approved": 0, "Rejected": 0}
        for r in rows: stats[r['status']] = r['count']
        return stats
