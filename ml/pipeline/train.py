import pandas as pd
import xgboost as xgb
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
import os
import json
from datetime import datetime
from features import FeatureEngineer

def train_model(data_path: str, model_output_path: str):
    print(f"Starting training at {datetime.now()}")
    
    # Load data
    df = pd.read_csv(data_path)
    
    # Feature Engineering
    fe = FeatureEngineer()
    fe.fit(df)
    X = fe.preprocess(df)
    y = df['delay']
    
    # Split
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    # Train
    model = xgb.XGBRegressor(
        n_estimators=100,
        learning_rate=0.1,
        max_depth=5,
        random_state=42
    )
    model.fit(X_train, y_train)
    
    # Evaluate
    predictions = model.predict(X_test)
    metrics = {
        "mae": float(mean_absolute_error(y_test, predictions)),
        "rmse": float(np.sqrt(mean_squared_error(y_test, predictions))),
        "r2": float(r2_score(y_test, predictions)),
        "timestamp": datetime.now().isoformat()
    }
    
    print(f"Metrics: {json.dumps(metrics, indent=2)}")
    
    # Save Model
    os.makedirs(os.path.dirname(model_output_path), exist_ok=True)
    model.get_booster().save_model(model_output_path)
    
    # Save Feature Engineer Medians
    medians_path = os.path.join(os.path.dirname(model_output_path), "medians.json")
    fe.save_medians(medians_path)
        
    # Save Metrics Report
    report_path = model_output_path.replace(".json", "_metrics.json")
    with open(report_path, "w") as f:
        json.dump(metrics, f, indent=2)
        
    print(f"Model saved to {model_output_path}")

if __name__ == "__main__":
    train_model("data/flight_data.csv", "ml/models/v1_model.json")
