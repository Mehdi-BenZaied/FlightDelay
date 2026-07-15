# backend/seed.py
from app import create_app, db, bcrypt
from app.models.user import User
from app.models.prediction import Prediction
import random

app = create_app()

def seed():
    with app.app_context():
        # Drop and create
        db.drop_all()
        db.create_all()

        # Seed Admin
        admin = User(
            username="admin",
            password=bcrypt.generate_password_hash("admin123").decode("utf-8"),
            is_admin=True
        )
        db.session.add(admin)

        # Seed some dummy predictions
        airlines = ["American Airlines", "Delta", "United", "IndiGo"]
        airports = ["JFK", "LAX", "ORD", "DEL", "BOM"]
        
        for _ in range(20):
            org = random.choice(airports)
            dest = random.choice([a for a in airports if a != org])
            p = Prediction(
                airline=random.choice(airlines),
                origin=org,
                destination=dest,
                flight_duration=random.randint(60, 600),
                congestion=random.uniform(1, 10),
                aircraft_type="Boeing 737",
                delay=random.uniform(0, 45)
            )
            db.session.add(p)
        
        db.session.commit()
        print("Database seeded successfully!")

if __name__ == "__main__":
    seed()
