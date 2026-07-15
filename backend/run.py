# backend/run.py
from gevent import monkey

monkey.patch_all()

from app import create_app, db, socketio

app = create_app()

if __name__ == "__main__":
    with app.app_context():
        db.create_all()

    socketio.run(
        app,
        host="0.0.0.0",
        port=5000,
        debug=True,
        use_reloader=False,
    )