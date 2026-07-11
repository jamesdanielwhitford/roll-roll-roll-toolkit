"""
Redeem a promo/recovery code you actually have (e.g. handed out at the
hackathon, found in a QR code, given by organizers).

This intentionally does NOT brute-force or guess codes - only submits
codes you explicitly pass in.

Usage:
    python3 redeem.py SOME-CODE-HERE
    python3 redeem.py SOME-CODE-HERE --user-id YOUR-ID
"""

import argparse
from api import redeem, RollAPIError


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("code", help="the redemption code to submit")
    parser.add_argument("--user-id", metavar="ID", default=None, help="your player id (or set ROLL_USER_ID)")
    args = parser.parse_args()

    try:
        status, data = redeem(args.code)
        print(f"Success: {data.get('title')} - {data.get('subtitle')}")
        print(data.get("player"))
    except RollAPIError as e:
        print(f"Failed ({e.status_code}): {e.payload}")


if __name__ == "__main__":
    main()
