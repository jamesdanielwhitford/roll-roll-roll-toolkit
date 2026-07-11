"""
Thin wrapper around the Roll Roll Roll REST API.
"""

import requests
from config import BASE_URL, HEADERS


class RollAPIError(Exception):
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self.payload = payload
        super().__init__(f"HTTP {status_code}: {payload}")


def _request(method, path, auth=True, **kwargs):
    headers = dict(kwargs.pop("headers", {}))
    if auth:
        headers = {**HEADERS, **headers}
    else:
        headers = {"Content-Type": "application/json", **headers}

    resp = requests.request(method, f"{BASE_URL}{path}", headers=headers, timeout=15, **kwargs)
    try:
        data = resp.json()
    except ValueError:
        data = resp.text

    if resp.status_code >= 400:
        raise RollAPIError(resp.status_code, data)
    return resp.status_code, data


def init():
    return _request("GET", "/init")


def register(user_name):
    return _request("POST", "/register", auth=False, json={"userName": user_name})


def login(code):
    return _request("POST", "/login", auth=False, json={"code": code})


def roll():
    return _request("POST", "/roll")


def contribute(project_id, amount):
    return _request("POST", "/project/contribute", json={"projectId": project_id, "amount": amount})


def redeem(code):
    return _request("POST", "/redeem", json={"code": code})
