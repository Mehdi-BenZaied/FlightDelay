# backend/analytics.py
from gevent import monkey
monkey.patch_all()

import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)
import os
import sys
import dash
from dash import dcc, html, Input, Output
import dash_bootstrap_components as dbc
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd

# Import Flask app and models
from app import create_app, db
from app.models.prediction import Prediction

flask_app = create_app()

# Load initial historical dataset
flight_data_path = os.getenv(
    "FLIGHT_DATA_PATH",
    "data/flight_data.csv",
)

df_csv = pd.read_csv(flight_data_path)

# Initialize the Dash app with Cyborg dark theme
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.CYBORG])
app.title = "Flight Delay AI | Live Analytics Dashboard"

# Custom Plotly Theme
PLOTLY_TEMPLATE = "plotly_dark"
CHART_COLOR_SEQUENCE = px.colors.qualitative.Pastel

# Layout components
header = html.Div(
    [
        html.H2("Flight Delay AI Analytics Dashboard", className="display-4 text-primary"),
        html.P(
            "Live insights combining training history and real-time inference delays.",
            className="lead text-muted",
        ),
        html.Hr(className="my-4", style={"borderColor": "#4f46e5"}),
    ],
    className="p-4 mb-4",
)

def create_card(title, chart_id):
    return dbc.Card(
        dbc.CardBody([
            html.H4(title, className="card-title text-info mb-3"),
            dcc.Loading(
                dcc.Graph(id=chart_id, config={'displayModeBar': False}),
                type="circle"
            )
        ]),
        className="shadow-lg border-0 bg-dark mb-4",
        style={"borderRadius": "15px", "border": "1px solid rgba(255,255,255,0.1)"}
    )

app.layout = dbc.Container([
    header,
    # Auto-refresh component every 5 seconds
    dcc.Interval(
        id='interval-component',
        interval=5 * 1000,
        n_intervals=0
    ),
    dbc.Row([
        dbc.Col(create_card("Average Delay by Route", "route-delay-chart"), md=6),
        dbc.Col(create_card("Weather Impact on Delays", "weather-chart"), md=6),
    ]),
    dbc.Row([
        dbc.Col(create_card("Airport Congestion vs Delays", "congestion-chart"), md=6),
        dbc.Col(create_card("Historical Delay Trends", "time-series-chart"), md=6),
    ]),
], fluid=True, className="p-4")

@app.callback(
    Output('route-delay-chart', 'figure'),
    Output('weather-chart', 'figure'),
    Output('congestion-chart', 'figure'),
    Output('time-series-chart', 'figure'),
    Input('interval-component', 'n_intervals')
)
def update_charts(n):
    # Fetch real-time predictions from DB
    with flask_app.app_context():
        try:
            db_predictions = Prediction.query.all()
            db_data = []
            for p in db_predictions:
                db_data.append({
                    "airline": p.airline,
                    "origin": p.origin,
                    "destination": p.destination,
                    "flight_duration": p.flight_duration,
                    "congestion": p.congestion,
                    "aircraft_type": p.aircraft_type,
                    "delay": p.delay,
                    "weather": "Clear", # default weather label
                    "scheduled_time": p.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                    "temperature": 25,
                    "humidity": 50
                })
            df_db = pd.DataFrame(db_data)
        except Exception as e:
            print(f"Database Query Error in Dash: {e}")
            df_db = pd.DataFrame()

    # Combine CSV data with DB data
    if not df_db.empty:
        df = pd.concat([df_csv, df_db], ignore_index=True)
    else:
        df = df_csv.copy()

    # Preprocessing
    if 'route' not in df.columns:
        df['route'] = df['origin'].astype(str) + "-" + df['destination'].astype(str)

    df["congestion"] = pd.to_numeric(df["congestion"], errors="coerce")
    df["delay"] = pd.to_numeric(df["delay"], errors="coerce")

    if 'weather' not in df.columns:
        df['weather'] = "Clear"

    # Chart 1: Average Delay by Route
    route_df = df.groupby('route', as_index=False)['delay'].mean().sort_values('delay', ascending=False)
    route_fig = px.bar(
        route_df, x='route', y='delay',
        template=PLOTLY_TEMPLATE,
        color='delay',
        color_continuous_scale='Viridis'
    )
    route_fig.update_layout(margin=dict(l=20, r=20, t=30, b=20), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')

    # Chart 2: Weather Impact
    weather_fig = px.box(
        df, x='weather', y='delay',
        template=PLOTLY_TEMPLATE,
        points="all",
        color='weather',
        color_discrete_sequence=CHART_COLOR_SEQUENCE
    )
    weather_fig.update_layout(margin=dict(l=20, r=20, t=30, b=20), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')

    # Chart 3: Congestion
    congestion_fig = px.scatter(
        df, x='congestion', y='delay',
        template=PLOTLY_TEMPLATE,
        trendline="ols",
        color='delay',
        color_continuous_scale='Magma'
    )
    congestion_fig.update_layout(margin=dict(l=20, r=20, t=30, b=20), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')

    # Chart 4: Time Series
    if 'scheduled_time' in df.columns:
        df['scheduled_time'] = pd.to_datetime(df['scheduled_time'], errors='coerce')
        time_df = df.dropna(subset=['scheduled_time']).sort_values('scheduled_time')
        time_series_fig = px.area(
            time_df, x='scheduled_time', y='delay',
            template=PLOTLY_TEMPLATE
        )
    else:
        time_series_fig = px.line(title="No time data")
    
    time_series_fig.update_layout(margin=dict(l=20, r=20, t=30, b=20), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')

    return route_fig, weather_fig, congestion_fig, time_series_fig

if __name__ == '__main__':
    app.run(host="0.0.0.0", debug=True, port=8050)

