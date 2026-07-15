# backend/app/__init__.py
import os
from flask import Flask
from flask_cors import CORS
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_bcrypt import Bcrypt
from flask_socketio import SocketIO
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError

from .core.config import settings
from .models.base import db
from .models.user import User

bcrypt = Bcrypt()
migrate = Migrate()
login_manager = LoginManager()
socketio = SocketIO()

def create_app():
    app = Flask(__name__)
    app.config.from_object(settings)
    app.config['SECRET_KEY'] = settings.SECRET_KEY
    
    db_uri = settings.SQLALCHEMY_DATABASE_URI
    
    # Dynamic DB checking & SQLite fallback for easy developer onboarding
    if db_uri.startswith("postgresql"):
        try:
            # Run a quick validation
            engine = create_engine(db_uri, connect_args={'connect_timeout': 3})
            conn = engine.connect()
            conn.close()
            print("Successfully connected to PostgreSQL database.")
        except (OperationalError, Exception) as e:
            print(f"Warning: PostgreSQL connection failed ({e}). Falling back to SQLite local database.")
            sqlite_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../flight_delay.db"))
            os.makedirs(os.path.dirname(sqlite_path), exist_ok=True)
            db_uri = f"sqlite:///{sqlite_path}"
            
    app.config['SQLALCHEMY_DATABASE_URI'] = db_uri

    # Initialize Extensions
    db.init_app(app)
    bcrypt.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    
    # Configure CORS with credentials support for local React/Vite development
    CORS(
        app, 
        supports_credentials=True, 
        resources={r"/api/*": {"origins": ["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000", "http://127.0.0.1:3000"]}}
    )
    
    # Initialize Socket.IO
    socketio.init_app(app, cors_allowed_origins="*")

    login_manager.login_view = "auth.login"
    
    @login_manager.unauthorized_handler
    def unauthorized():
        return {"msg": "Unauthorized. Please log in."}, 401

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    # Register Blueprints
    from .api.v1.auth import auth_bp
    from .api.v1.predict import predict_bp
    
    app.register_blueprint(auth_bp, url_prefix=f"{settings.API_V1_STR}/auth")
    app.register_blueprint(predict_bp, url_prefix=f"{settings.API_V1_STR}/predict")

    @app.route("/health")
    def health_check():
        return {
            "status": "healthy", 
            "service": "flight-delay-api",
            "database": "sqlite" if "sqlite" in db_uri else "postgres"
        }, 200

    return app

