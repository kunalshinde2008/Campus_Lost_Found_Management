import os
from dotenv import load_dotenv
import mysql.connector

load_dotenv()

print("Host:", os.getenv("DB_HOST"))
print("User:", os.getenv("DB_USER"))
print("Database:", os.getenv("DB_NAME"))
print("Port:", os.getenv("DB_PORT"))
print("Password found:", bool(os.getenv("DB_PASSWORD")))

try:
    conn = mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
        port=int(os.getenv("DB_PORT", 3306)),
    )
    cursor = conn.cursor()
    cursor.execute("SHOW TABLES")
    print("CONNECTED! Tables:", [row[0] for row in cursor.fetchall()])
    conn.close()
except Exception as e:
    print("ERROR:", e)