import json
import os
import sys
from pathlib import Path

import redis
import requests
import shap
import xgboost as xgb

# ---------------------------------------------------------
# Resolve the project root for both:
# - Local execution:
#   FlightDelayAI/backend/app/services/prediction_service.py
# - Docker execution:
#   /app/app/services/prediction_service.py
# ---------------------------------------------------------

CURRENT_FILE = Path(__file__).resolve()

POSSIBLE_PROJECT_ROOTS = [
    CURRENT_FILE.parents[2],  # /app in Docker
    CURRENT_FILE.parents[3],  # FlightDelayAI locally
]

for project_root in POSSIBLE_PROJECT_ROOTS:
    if (project_root / "ml").is_dir():
        project_root_string = str(project_root)

        if project_root_string not in sys.path:
            sys.path.insert(0, project_root_string)

        break

from ml.pipeline.features import FeatureEngineer

from ..core.config import settings
from ..models.base import db
from ..models.prediction import Prediction


def resolve_model_path() -> Path:
    """
    Resolve the XGBoost model path.

    Docker uses:
        /app/ml/models/v1_model.json

    Local development normally uses:
        FlightDelayAI/ml/models/v1_model.json
    """

    configured_path = os.getenv("MODEL_PATH")

    if configured_path:
        return Path(configured_path).expanduser().resolve()

    candidates = [
        CURRENT_FILE.parents[2] / "ml" / "models" / "v1_model.json",
        CURRENT_FILE.parents[3] / "ml" / "models" / "v1_model.json",
    ]

    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()

    # Return the Docker-style location for a useful error message.
    return candidates[0].resolve()


class PredictionService:
    def __init__(self):
        self.fe = FeatureEngineer()

        self.model_path = resolve_model_path()
        self.model = None
        self.explainer = None
        self.redis = None

        self._load_model()
        self._initialize_shap()
        self._initialize_redis()

    def _load_model(self):
        print(f"Loading prediction model from: {self.model_path}")
        print(f"Model file exists: {self.model_path.is_file()}")

        if not self.model_path.is_file():
            print(
                "Prediction model file was not found at: "
                f"{self.model_path}"
            )
            return

        try:
            model = xgb.XGBRegressor()
            model.load_model(str(self.model_path))

            self.model = model

            print("Prediction model loaded successfully.")
        except Exception as exc:
            self.model = None

            print(
                "Prediction model load error: "
                f"{type(exc).__name__}: {exc}"
            )

    def _initialize_shap(self):
        if self.model is None:
            return

        try:
            self.explainer = shap.TreeExplainer(self.model)
            print("SHAP explainer initialized successfully.")
        except Exception as exc:
            # A SHAP failure should not disable predictions.
            self.explainer = None

            print(
                "Warning: SHAP explainer initialization failed: "
                f"{type(exc).__name__}: {exc}"
            )

    def _initialize_redis(self):
        try:
            self.redis = redis.Redis(
                host=getattr(settings, "REDIS_HOST", "localhost"),
                port=int(getattr(settings, "REDIS_PORT", 6379)),
                db=int(getattr(settings, "REDIS_DB", 0)),
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )

            self.redis.ping()

            print("Successfully connected to Redis cache.")
        except Exception as exc:
            self.redis = None

            print(
                f"Warning: Redis connection failed ({exc}). "
                "Running without cache."
            )

    def fetch_weather(self, airport_code):
        airport_code = str(airport_code).upper().strip()
        cache_key = f"weather:{airport_code}"

        # -------------------------------------------------
        # Check Redis cache
        # -------------------------------------------------

        if self.redis:
            try:
                cached_weather = self.redis.get(cache_key)

                if cached_weather:
                    print(f"Redis cache hit for {cache_key}")
                    return json.loads(cached_weather)
            except Exception as exc:
                print(f"Redis error while reading weather cache: {exc}")

        # Default values when the weather service is unavailable.
        weather_data = {
            "temp": 25.0,
            "humidity": 50.0,
        }

        weather_api_key = getattr(settings, "WEATHER_API_KEY", "")

        if not weather_api_key:
            print(
                "WEATHER_API_KEY is not configured. "
                "Using default weather values."
            )
            return weather_data

        # -------------------------------------------------
        # Call OpenWeather
        # -------------------------------------------------

        url = "https://api.openweathermap.org/data/2.5/weather"

        params = {
            "q": airport_code,
            "appid": weather_api_key,
            "units": "metric",
        }

        try:
            response = requests.get(
                url,
                params=params,
                timeout=5,
            )

            response.raise_for_status()
            weather_json = response.json()

            main_weather = weather_json.get("main")

            if main_weather:
                weather_data = {
                    "temp": float(main_weather.get("temp", 25)),
                    "humidity": float(
                        main_weather.get("humidity", 50)
                    ),
                }

                if self.redis:
                    try:
                        # Keep weather data for 15 minutes.
                        self.redis.setex(
                            cache_key,
                            900,
                            json.dumps(weather_data),
                        )

                        print(f"Cached weather for {airport_code}")
                    except Exception as exc:
                        print(
                            "Redis error while caching weather: "
                            f"{exc}"
                        )

        except requests.RequestException as exc:
            print(f"Weather API request error: {exc}")
        except (TypeError, ValueError, KeyError) as exc:
            print(f"Weather API response error: {exc}")

        return weather_data

    def get_prediction(self, data, user_id=None):
        if self.model is None:
            raise RuntimeError(
                "Prediction model is unavailable. "
                f"Expected model at: {self.model_path}"
            )

        required_fields = [
            "airline",
            "origin",
            "destination",
            "flight_duration",
            "congestion",
        ]

        missing_fields = [
            field
            for field in required_fields
            if data.get(field) in (None, "")
        ]

        if missing_fields:
            raise ValueError(
                "Missing required fields: "
                + ", ".join(missing_fields)
            )

        try:
            flight_duration = float(data["flight_duration"])
            congestion = float(data["congestion"])
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "flight_duration and congestion must be numbers."
            ) from exc

        origin = str(data["origin"]).upper().strip()
        destination = str(data["destination"]).upper().strip()

        weather = self.fetch_weather(origin)

        inference_data = {
            "flight_duration": flight_duration,
            "congestion": congestion,
            "temperature": float(weather["temp"]),
            "humidity": float(weather["humidity"]),
        }

        features = self.fe.get_inference_features(inference_data)

        prediction_result = self.model.predict(features)
        prediction_value = float(prediction_result[0])

        shap_contributions = {}

        if self.explainer is not None:
            try:
                shap_values = self.explainer.shap_values(features)

                # Handle the usual one-row SHAP response.
                row_values = shap_values[0]

                for column, value in zip(
                    self.fe.feature_cols,
                    row_values,
                ):
                    shap_contributions[column] = float(value)

            except Exception as exc:
                print(
                    "SHAP explanation calculation error: "
                    f"{exc}"
                )

        new_prediction = Prediction(
            airline=str(data["airline"]).strip(),
            origin=origin,
            destination=destination,
            flight_duration=flight_duration,
            congestion=congestion,
            aircraft_type=data.get("aircraft_type"),
            delay=prediction_value,
            confidence_score=0.92,
            user_id=user_id,
        )

        try:
            db.session.add(new_prediction)
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

        created_at = (
            new_prediction.created_at.isoformat()
            if new_prediction.created_at
            else None
        )

        return {
            "id": new_prediction.id,
            "airline": new_prediction.airline,
            "origin": new_prediction.origin,
            "destination": new_prediction.destination,
            "flight_duration": new_prediction.flight_duration,
            "congestion": new_prediction.congestion,
            "aircraft_type": new_prediction.aircraft_type,
            "delay": prediction_value,
            "weather": weather,
            "confidence": new_prediction.confidence_score,
            "created_at": created_at,
            "user_id": new_prediction.user_id,
            "shap_contributions": shap_contributions,
        }

    def get_history(self, limit=20, user_id=None):
        try:
            limit = int(limit)
        except (TypeError, ValueError):
            limit = 20

        # Prevent invalid or excessively large queries.
        limit = max(1, min(limit, 100))

        query = Prediction.query

        if user_id is not None:
            query = query.filter_by(user_id=user_id)

        predictions = (
            query
            .order_by(Prediction.created_at.desc())
            .limit(limit)
            .all()
        )

        return [
            prediction.to_dict()
            for prediction in predictions
        ]