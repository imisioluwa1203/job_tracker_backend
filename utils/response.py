from flask import jsonify


def success(data=None, message=None, status=200):
    body = {"success": True, "data": data}
    if message is not None:
        body["message"] = message
    return jsonify(body), status


def error(code, message, status=400):
    body = {
        "success": False,
        "error": {"code": code, "message": message}
    }
    return jsonify(body), status