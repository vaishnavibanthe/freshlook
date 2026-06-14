import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'blog.db')

def run_migration():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # 1. Alter events table if column doesn't exist
    c.execute("PRAGMA table_info(events)")
    columns = [col[1] for col in c.fetchall()]
    if 'card_image' not in columns:
        print("Adding card_image to events table...")
        c.execute("ALTER TABLE events ADD COLUMN card_image TEXT;")
    else:
        print("card_image already exists in events table.")
        
    # 2. Alter webinars table if column doesn't exist
    c.execute("PRAGMA table_info(webinars)")
    columns = [col[1] for col in c.fetchall()]
    if 'card_image' not in columns:
        print("Adding card_image to webinars table...")
        c.execute("ALTER TABLE webinars ADD COLUMN card_image TEXT;")
    else:
        print("card_image already exists in webinars table.")
        
    # 3. Update existing records with default images cycling 1-6
    # Fetch all events and assign event_X.png
    c.execute("SELECT id FROM events ORDER BY id ASC")
    event_ids = [row[0] for row in c.fetchall()]
    for idx, e_id in enumerate(event_ids):
        img_url = f"/static/img/event_{(idx % 6) + 1}.png"
        c.execute("UPDATE events SET card_image = ? WHERE id = ?", (img_url, e_id))
        
    # Do the same for webinars
    c.execute("SELECT id FROM webinars ORDER BY id ASC")
    webinar_ids = [row[0] for row in c.fetchall()]
    for idx, w_id in enumerate(webinar_ids):
        img_url = f"/static/img/event_{(idx % 6) + 1}.png"
        c.execute("UPDATE webinars SET card_image = ? WHERE id = ?", (img_url, w_id))
        
    conn.commit()
    conn.close()
    print("Migration finished successfully.")

if __name__ == '__main__':
    run_migration()
