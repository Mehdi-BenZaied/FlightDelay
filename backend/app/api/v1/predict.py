# backend/app/api/v1/predict.py
from flask import Blueprint, request, jsonify
from flask_login import current_user
from pydantic import BaseModel, Field, field_validator, ValidationError
from ...services.prediction_service import PredictionService
from ... import socketio

predict_bp = Blueprint("predict", __name__)
prediction_service = PredictionService()

class PredictionRequest(BaseModel):
    airline: str = Field(..., min_length=1)
    origin: str = Field(..., min_length=3, max_length=3)
    destination: str = Field(..., min_length=3, max_length=3)
    flight_duration: float = Field(..., gt=0)
    congestion: float = Field(..., ge=1, le=10)
    aircraft_type: str = Field(None)
    
    @field_validator('origin', 'destination')
    @classmethod
    def validate_iata(cls, v: str) -> str:
        if not v.isalpha():
            raise ValueError("IATA airport code must contain only letters")
        return v.upper().strip()

@predict_bp.route("/", methods=["POST"])
def predict_delay():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Missing JSON request body"}), 400
        
    try:
        validated = PredictionRequest(**data)
    except ValidationError as e:
        errors = {err['loc'][0]: err['msg'] for err in e.errors()}
        return jsonify({"error": "Validation failed", "details": errors}), 400
        
    try:
        user_id = current_user.id if current_user.is_authenticated else None
        result = prediction_service.get_prediction(validated.model_dump(), user_id=user_id)
        
        # Emit real-time WebSocket event
        socketio.emit("new_prediction", result)
        
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@predict_bp.route("/history", methods=["GET"])
def get_history():
    limit = request.args.get("limit", 10, type=int)
    # Filter by user if logged in, otherwise return recent predictions
    user_id = current_user.id if current_user.is_authenticated else None
    history = prediction_service.get_history(limit, user_id=user_id)
    return jsonify(history), 200

# Import DB and analytical tools
from ...models.prediction import Prediction
from ...models.base import db
from scipy.stats import ks_2samp
import pandas as pd
import os

@predict_bp.route("/stats", methods=["GET"])
def get_stats():
    try:
        # Total predictions
        total_predictions = db.session.query(db.func.count(Prediction.id)).scalar() or 0
        
        # Average delay
        average_delay = db.session.query(db.func.avg(Prediction.delay)).scalar() or 0.0
        average_delay = round(float(average_delay), 1)
        
        # Most congested airport
        active_airport_res = db.session.query(
            Prediction.origin, 
            db.func.count(Prediction.origin)
        ).group_by(Prediction.origin).order_by(db.func.count(Prediction.origin).desc()).first()
        
        most_congested_airport = active_airport_res[0] if active_airport_res else "N/A"
        
        return jsonify({
            "total_predictions": total_predictions,
            "average_delay": average_delay,
            "most_congested_airport": most_congested_airport
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@predict_bp.route("/drift", methods=["GET"])
def get_drift():
    try:
        # Load training delays
        csv_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../data/flight_data.csv"))
        if not os.path.exists(csv_path):
            return jsonify({"error": "Training data CSV not found"}), 500
            
        df = pd.read_csv(csv_path)
        training_delays = pd.to_numeric(df['delay'], errors='coerce').dropna().values
        
        # Query up to 100 recent predictions
        recent_preds = Prediction.query.order_by(Prediction.created_at.desc()).limit(100).all()
        
        if len(recent_preds) < 10:
            return jsonify({
                "status": "Insufficient Data",
                "message": f"Need at least 10 predictions in DB for drift test (currently have {len(recent_preds)})."
            }), 200
            
        db_delays = [p.delay for p in recent_preds]
        
        # Kolmogorov-Smirnov test comparison
        stat, p_value = ks_2samp(training_delays, db_delays)
        drift_detected = bool(p_value < 0.05)
        
        return jsonify({
            "status": "Success",
            "predictions_analyzed": len(db_delays),
            "ks_statistic": float(stat),
            "p_value": float(p_value),
            "drift_detected": drift_detected,
            "interpretation": "Drift detected (p < 0.05). Consider retraining model." if drift_detected else "No significant drift detected.",
            "metrics": {
                "training_avg_delay": float(training_delays.mean()),
                "production_avg_delay": float(pd.Series(db_delays).mean())
            }
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


