import os
from flask import Flask, jsonify, request
from flask_restx import Api, Resource, fields
import pyodbc
import logging
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

app = Flask(__name__)

#  API 
api = Api(
    app,
    title="TrailService API",
    version="1.0",
    description="API for managing trails",
 
)


ns_trails = api.namespace("trails", description="Operations related to trails")

# db config
DATABASE_CONFIG = {
    "DRIVER": os.getenv("DB_DRIVER", "ODBC Driver 17 for SQL Server"),
    "SERVER": os.getenv("DB_SERVER", "dist-6-505.uopnet.plymouth.ac.uk."),
    "DATABASE": os.getenv("DB_NAME", "COMP2001_SAlhammad"),
    "UID": os.getenv("DB_USER", "SAlhammad"),
    "PWD": os.getenv("DB_PASSWORD", "AjeQ519+"),
}


# db connection 
def get_db_connection():
    try:
        connection = pyodbc.connect(
            f"DRIVER={DATABASE_CONFIG['DRIVER']};"
            f"SERVER={DATABASE_CONFIG['SERVER']};"
            f"DATABASE={DATABASE_CONFIG['DATABASE']};"
            f"UID={DATABASE_CONFIG['UID']};"
            f"PWD={DATABASE_CONFIG['PWD']};"
        )
        logging.info("Database connection established")
        return connection
    except pyodbc.Error as e:
        logging.error(f"Database connection error: {e}")
        return None


AUTHENTICATOR_API_URL = "https://web.socem.plymouth.ac.uk/COMP2001/auth/api/users"
def authenticate_user(email, password):
    """Authenticate a user using the external Authenticator API."""
    try:
        # Authenticator API
        response = requests.post(
            AUTHENTICATOR_API_URL, json={"email": email, "password": password}
        )
        logging.info(f"Authenticator API response: {response.status_code} {response.text}")

    
        if response.status_code == 200:
            user_data = response.json()
            
            if isinstance(user_data, list) and len(user_data) == 2 and user_data[0] == "Verified" and user_data[1] == "True":
                return {"email": email}  # authenticate 
            logging.error("Authentication failed: Invalid API response structure or verification failed")
        else:
            logging.error(f"Authentication failed: {response.status_code} {response.text}")
    except Exception as e:
        logging.error(f"Error during authentication: {e}")
    return None

# users role from the database
def get_user_role(email):
    """Retrieve a user's role from the database."""
    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor()
            logging.info(f"Fetching role for email: {email}")
            
           
            cursor.execute(
                "SELECT role FROM CW2.[user] WHERE CAST(email AS VARCHAR(MAX)) = ?", email
            )
            result = cursor.fetchone()
            connection.close()
            
            logging.info(f"Role query result: {result}")
            if result:
                return result[0]  # the role
        except Exception as e:
            logging.error(f"Error fetching user role: {e}")
    return None

#  Swagger
trail_model = api.model(
    "Trail",
    {
        "title": fields.String(required=True, description="Title of the trail"),
        "description": fields.String(required=True, description="Description of the trail"),
        "length": fields.Float(required=True, description="Length of the trail"),
        "elevation": fields.Float(required=True, description="Elevation gain"),
        "routeType": fields.String(required=True, description="Type of the trail (e.g., Loop, Out-and-Back)"),
    },
)




@app.route("/")
def home():
    """Home route."""
    logging.info("Home route accessed")
    return jsonify({"message": "TrailService is running!"})

@ns_trails.route("/")
class TrailList(Resource):
    @api.doc(
        description="Fetch all trails. Admins see all details; public users see a limited view.",
        params={"email": "User email (optional)", "password": "User password (optional)"},
    )
    def get(self):
        """Fetch all trails with appropriate access based on user role."""
        email = request.args.get("email")
        password = request.args.get("password")

        # authenticate
        if email and password:
            user = authenticate_user(email, password)
            if not user:
                return {"error": "Authentication failed"}, 

            role = get_user_role(email)  # ftch  role
            if not role:
                return {"error": "User role not found"}, 

            # admins acess details
            if role == "admin":
                connection = get_db_connection()
                if connection:
                    try:
                        cursor = connection.cursor()
                        cursor.execute("SELECT * FROM CW2.trials")
                        trails = [
                            {
                                "trialID": row[0],
                                "title": row[1],
                                "description": row[2],
                                "length": float(row[3]),
                                "elevation": float(row[4]),
                                "routeType": row[5],
                                "userID": row[6],
                            }
                            for row in cursor.fetchall()
                        ]
                        connection.close()
                        return trails, 
                    except Exception as e:
                        logging.error(f"Error fetching trails: {e}")
                        return {"error": "Failed to fetch trails", "details": str(e)}, 
                return {"error": "Database connection failed"}, 

        # Public users see a limited view
        connection = get_db_connection()
        if connection:
            try:
                cursor = connection.cursor()
                cursor.execute("SELECT trialID, title, description, length, elevation, routeType FROM CW2.trials")
                trails = [
                    {
                        "trialID": row[0],
                        "title": row[1],
                        "description": row[2],
                        "length": float(row[3]),
                        "elevation": float(row[4]),
                        "routeType": row[5],
                    }
                    for row in cursor.fetchall()
                ]
                connection.close()
                return trails, 
            except Exception as e:
                logging.error(f"Error fetching trails: {e}")
                return {"error": "Failed to fetch trails", "details": str(e)}, 
        return {"error": "Database connection failed"}, 
@ns_trails.route("/add")
class AddTrail(Resource):
    @api.expect(trail_model)
    @api.doc(
        description="Admins can add a new trail.",
        params={"email": "Admin email", "password": "Admin password"},
    )
    def post(self):
        email = request.args.get("email")
        password = request.args.get("password")

        if not email or not password:
            return {"error": "Email and password are required"}, 

        user = authenticate_user(email, password)
        if not user:
            return {"error": "Authentication failed"}, 

        role = get_user_role(email)
        if role != "admin":
            return {"error": "Forbidden: Only admins can add trails"}, 

        connection = get_db_connection()
        if connection:
            try:
                data = api.payload
                cursor = connection.cursor()
                cursor.execute(
                    "INSERT INTO CW2.trials (title, description, length, elevation, routeType, userID) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    data["title"],
                    data["description"],
                    data["length"],
                    data["elevation"],
                    data["routeType"],
                    user.get("id"), 
                )
                connection.commit()
                connection.close()
                return {"message": "Trail added successfully!"}, 
            except Exception as e:
                logging.error(f"Error adding trail: {e}")
                return {"error": "Failed to add trail", "details": str(e)}, 
        return {"error": "Database connection failed"}, 

@ns_trails.route("/<int:trial_id>")
class UpdateTrail(Resource):
    @api.expect(trail_model)
    @api.doc(
        description="Admins can update a trail.",
        params={"email": "Admin email", "password": "Admin password"},
    )
    def put(self, trial_id):
        """Update a trail (admin only)."""
        email = request.args.get("email")
        password = request.args.get("password")

        if not email or not password:
            return {"error": "Email and password are required"}, 

        user = authenticate_user(email, password)
        if not user:
            return {"error": "Authentication failed"}, 

        role = get_user_role(email)
        if role != "admin":
            return {"error": "Forbidden: Only admins can update trails"}, 

        connection = get_db_connection()
        if connection:
            try:
                data = api.payload or {}
            
                required_fields = ["title", "description", "length", "elevation", "routeType"]
                for field in required_fields:
                    if field not in data:
                        return {"error": f"Missing field: {field}"}, 

                cursor = connection.cursor()

                # Check trail exists
                cursor.execute("SELECT trialID FROM CW2.trials WHERE trialID = ?", trial_id)
                if not cursor.fetchone():
                    return {"error": "Trail not found"}, 

                # Update the trail
                cursor.execute(
                    "UPDATE CW2.trials SET title = ?, description = ?, length = ?, elevation = ?, routeType = ? WHERE trialID = ?",
                    data["title"],
                    data["description"],
                    data["length"],
                    data["elevation"],
                    data["routeType"],
                    trial_id,
                )
                connection.commit()
                connection.close()
                return {"message": "Trail updated successfully!"}, 
            except Exception as e:
                logging.error(f"Error updating trail: {e}")
                return {"error": "Failed to update trail", "details": str(e)}, 
        return {"error": "Database connection failed"}, 


@ns_trails.route("/delete/<int:trial_id>")
class DeleteTrail(Resource):
    @api.doc(
        description="Admins can delete a trail.",
        params={"email": "Admin email", "password": "Admin password"},
    )
    def delete(self, trial_id):
        """Delete a trail (admin only)."""
        email = request.args.get("email")
        password = request.args.get("password")

        if not email or not password:
            return {"error": "Email and password are required"}, 

        user = authenticate_user(email, password)
        if not user:
            return {"error": "Authentication failed"}, 

        role = get_user_role(email)
        if role != "admin":
            return {"error": "Forbidden: Only admins can delete trails"}, 

        connection = get_db_connection()
        if connection:
            try:
                cursor = connection.cursor()

                cursor.execute("SELECT trialID FROM CW2.trials WHERE trialID = ?", trial_id)
                trail = cursor.fetchone()
                if not trail:
                    return {"error": "Trail not found"}, 

                # Delete the trail
                cursor.execute("DELETE FROM CW2.trials WHERE trialID = ?", trial_id)
                connection.commit()
                connection.close()
                return {"message": "Trail deleted successfully!"}, 
            except Exception as e:
                logging.error(f"Error deleting trail: {e}")
                return {"error": "Failed to delete trail", "details": str(e)}, 
        return {"error": "Database connection failed"}, 
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
