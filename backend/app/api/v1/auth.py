# backend/app/api/v1/auth.py
from flask import Blueprint, request, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from ...models.user import User
from ...models.base import db
from ... import bcrypt

auth_bp = Blueprint("auth", __name__)

@auth_bp.route("/register", methods=["POST"])
def register():
    data = request.get_json()
    if not data or not data.get("username") or not data.get("password"):
        return jsonify({"msg": "Missing credentials"}), 400
        
    existing_user = User.query.filter_by(username=data["username"]).first()
    if existing_user:
        return jsonify({"msg": "Username already exists"}), 400
        
    hashed_password = bcrypt.generate_password_hash(data["password"]).decode("utf-8")
    new_user = User(
        username=data["username"],
        password=hashed_password
    )
    db.session.add(new_user)
    db.session.commit()
    
    login_user(new_user)
    return jsonify({
        "msg": "Registration successful",
        "user": {"username": new_user.username, "is_admin": new_user.is_admin}
    }), 201

@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    if not data or not data.get("username") or not data.get("password"):
        return jsonify({"msg": "Missing credentials"}), 400
    
    user = User.query.filter_by(username=data["username"]).first()
    if user and bcrypt.check_password_hash(user.password, data["password"]):
        login_user(user)
        return jsonify({
            "msg": "Login successful",
            "user": {"username": user.username, "is_admin": user.is_admin}
        }), 200
    
    return jsonify({"msg": "Invalid username or password"}), 401

@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    return jsonify({"msg": "Logged out"}), 200

@auth_bp.route("/me", methods=["GET"])
@login_required
def get_me():
    return jsonify({
        "username": current_user.username,
        "is_admin": current_user.is_admin
    }), 200
