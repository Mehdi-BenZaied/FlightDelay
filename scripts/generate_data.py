# generate_data.py
import pandas as pd
import random
from datetime import datetime, timedelta

def generate_flight_data(num_rows=100):
    airlines = ["IndiGo", "SpiceJet", "AirAsia", "Vistara", "GoAir", "Air India", "American Airlines", "Delta", "United"]
    airports = ["DEL", "BOM", "BLR", "HYD", "MAA", "CCU", "JFK", "LAX", "ORD", "LHR", "DXB"]
    aircraft_types = ["A320", "A321", "B737", "B777", "B787", "A350"]
    weather_conditions = ["Clear", "Cloudy", "Rain", "Fog", "Thunderstorm", "Sunny"]

    data = []
    start_date = datetime(2025, 2, 22, 6, 0, 0)

    for i in range(num_rows):
        airline = random.choice(airlines)
        origin = random.choice(airports)
        destination = random.choice([a for a in airports if a != origin])
        flight_duration = random.randint(60, 600)
        congestion = random.randint(1, 10)
        aircraft_type = random.choice(aircraft_types)
        
        # Simple logic for delay: more congestion and bad weather = more delay
        weather = random.choice(weather_conditions)
        base_delay = congestion * 2
        if weather in ["Rain", "Fog"]: base_delay += 10
        if weather == "Thunderstorm": base_delay += 20
        delay = max(0, base_delay + random.randint(-5, 10))

        scheduled_time = start_date + timedelta(hours=i*2)
        temperature = random.randint(15, 35)
        humidity = random.randint(40, 90)

        data.append([
            airline, origin, destination, flight_duration, congestion, 
            aircraft_type, delay, weather, scheduled_time.strftime("%Y-%m-%d %H:%M:%S"), 
            temperature, humidity
        ])

    df = pd.DataFrame(data, columns=[
        "airline", "origin", "destination", "flight_duration", "congestion", 
        "aircraft_type", "delay", "weather", "scheduled_time", "temperature", "humidity"
    ])
    
    df.to_csv("data/flight_data.csv", index=False)
    print(f"Generated {num_rows} rows in data/flight_data.csv")

if __name__ == "__main__":
    generate_flight_data(100)
