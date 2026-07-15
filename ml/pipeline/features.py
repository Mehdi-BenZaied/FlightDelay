# ml/pipeline/features.py
import pandas as pd
import numpy as np
import json
import os

class FeatureEngineer:
    def __init__(self):
        self.feature_cols = ['flight_duration', 'congestion', 'temperature', 'humidity']
        self.medians = {}
        # Load medians if they exist in models folder
        self.medians_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../models/medians.json"))
        if os.path.exists(self.medians_path):
            try:
                with open(self.medians_path, 'r') as f:
                    self.medians = json.load(f)
            except Exception as e:
                print(f"Error loading medians: {e}")

    def fit(self, data: pd.DataFrame):
        """
        Computes training medians for imputation.
        """
        df = data.copy()
        for col in self.feature_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        calc_medians = df[self.feature_cols].median(numeric_only=True)
        self.medians = {col: float(val) for col, val in calc_medians.items()}
        return self

    def save_medians(self, output_path: str):
        """
        Saves computed medians to a JSON file.
        """
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, 'w') as f:
            json.dump(self.medians, f, indent=2)

    def preprocess(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Implements reproducible preprocessing steps using fitted medians.
        """
        df = data.copy()
        
        # Ensure numeric types
        for col in self.feature_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # Impute using fitted medians, fall back to median of the input if not fitted
        for col in self.feature_cols:
            if col in df.columns:
                fill_val = self.medians.get(col)
                if fill_val is None:
                    # Fallback to local median (e.g. if fitting wasn't run)
                    local_med = df[col].median()
                    fill_val = local_med if not pd.isna(local_med) else 0.0
                df[col] = df[col].fillna(fill_val)
        
        return df[self.feature_cols]

    def get_inference_features(self, data_dict: dict) -> np.ndarray:
        """
        Converts a single request dictionary into the format expected by the model.
        """
        df = pd.DataFrame([data_dict])
        processed = self.preprocess(df)
        return processed.values
