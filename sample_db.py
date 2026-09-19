import os
from db_adapter import get_db

def seed_database():
    print("🌱 Initializing and seeding IntraBot database...")
    db = get_db("sqlite")
    db.init_db()
    db.seed_data()
    employees = db.list_employees()
    print(f"✅ Successfully seeded {len(employees)} employees across Engineering, HR, IT, Marketing, Finance, Design, Sales, and Product!")
    print("✅ Policies seeded: Leave, WFH, Medical, Travel, Parental Leave, Learning & Development, Equipment.")
    print("✅ Ready to demonstrate IntraBot!")

if __name__ == "__main__":
    seed_database()
