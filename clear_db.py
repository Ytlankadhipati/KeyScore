import sqlite3

# Connect to the SQLite database
conn = sqlite3.connect('users.db')
cursor = conn.cursor()

# Delete all records from each table
cursor.execute("DELETE FROM files")
cursor.execute("DELETE FROM users")

# Optional: Reset auto-increment counters
cursor.execute("DELETE FROM sqlite_sequence WHERE name='files'")
cursor.execute("DELETE FROM sqlite_sequence WHERE name='users'")

# Commit changes and close connection
conn.commit()
conn.close()

print("All data deleted from users.db.")
