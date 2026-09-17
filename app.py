from flask import Flask
from routes.auth import auth_bp



from db import get_connection
from utils.response import success

app = Flask(__name__)
app.register_blueprint(auth_bp)

@app.route("/")
def home():
    return success({"status": "ok"}, message="Job Tracker API is running")

# @app.route("/test-db")
# def test_db():
#     conn = get_connection()
#     conn.close()
#     return success(message="Database connection successful")



if __name__ == "__main__":
    app.run(debug=True, port=5000)