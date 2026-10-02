import os
from dotenv import load_dotenv
import mysql.connector

load_dotenv()

conn = mysql.connector.connect(
    host=os.getenv("DB_HOST"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    database=os.getenv("DB_NAME"),
    port=int(os.getenv("DB_PORT", 3306)),
)
cursor = conn.cursor()

print("===== COLUMNS =====")
cursor.execute(
    "SELECT TABLE_NAME, COLUMN_NAME, COLUMN_TYPE, COLUMN_KEY "
    "FROM information_schema.COLUMNS "
    "WHERE TABLE_SCHEMA = %s ORDER BY TABLE_NAME, ORDINAL_POSITION",
    (os.getenv("DB_NAME"),),
)
for row in cursor.fetchall():
    print(row)

print("===== FUNCTION =====")
try:
    cursor.execute("SHOW CREATE FUNCTION CalculateMatchScore")
    print(cursor.fetchone()[2])
except Exception as e:
    print("ERROR:", e)

print("===== VIEW =====")
try:
    cursor.execute("SHOW CREATE VIEW FoundItemsView")
    print(cursor.fetchone()[1])
except Exception as e:
    print("ERROR:", e)

conn.close()