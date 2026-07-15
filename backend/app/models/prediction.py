# backend/app/models/prediction.py
from datetime import datetime
from .base import db

class Prediction(db.Model):
    __tablename__ = 'predictions'
    id = db.Column(db.Integer, primary_key=True)
    airline = db.Column(db.String(50), nullable=False)
    origin = db.Column(db.String(10), nullable=False, index=True)
    destination = db.Column(db.String(10), nullable=False, index=True)
    flight_duration = db.Column(db.Float, nullable=False)
    congestion = db.Column(db.Float, nullable=False)
    aircraft_type = db.Column(db.String(50))
    delay = db.Column(db.Float, nullable=False)
    confidence_score = db.Column(db.Float, default=1.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "airline": self.airline,
            "origin": self.origin,
            "destination": self.destination,
            "flight_duration": self.flight_duration,
            "congestion": self.congestion,
            "aircraft_type": self.aircraft_type,
            "delay": self.delay,
            "confidence_score": self.confidence_score,
            "created_at": self.created_at.isoformat(),
            "user_id": self.user_id
        }
