#!/usr/bin/env python3
"""Email today's UC Davis dining menus.

Env vars: GMAIL_USER, GMAIL_APP_PASSWORD, MAIL_TO (optional, defaults to GMAIL_USER)
Usage:    python menu_email.py            # send email
          python menu_email.py --print    # just print it (for testing)
"""
import os
import re
import smtplib
import ssl
import sys
from datetime import datetime
from email.message import EmailMessage
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

LOCATIONS = {
    "Segundo DC": "https://housing.ucdavis.edu/dining/dining-commons/segundo/",
    "Tercero DC": "https://housing.ucdavis.edu/dining/dining-commons/tercero/",
    "Cuarto DC": "https://housing.ucdavis.edu/dining/dining-commons/cuarto/",
    "Latitude": "https://housing.ucdavis.edu/dining/latitude/",
}

DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
MEALS = ["Breakfast", "Brunch", "Lunch", "Dinner", "Late Night"]

# Staples that are always there; hide them so the email is just the interesting stuff.
# Set to set() to see everything.
SKIP_DISHES = {
    "salad bar", "salad selections", "deli bar", "panini deli bar", "boiled eggs",
    "oatmeal", "oatmeal elevated", "the parfait palette", "plain bagel",
    "locally grown sticky rice", "scrambled egg", "bacon",
}


def parse_menu(html: str, day_name: str) -> dict:
    """Return {meal: [(zone, dish), ...]} for one day.

    The page lists the whole week as headings: Day > Meal > "X Zone" > dish (a link
    to #collapseN). I classify headings by their text rather than tag level so small
    markup changes don't break it.
    """
    soup = BeautifulSoup(html, "html.parser")
    day = meal = zone = None
    menu: dict = {}
    for tag in soup.find_all(["h1", "h2", "h3", "h4", "h5"]):
        text = " ".join(tag.get_text(" ", strip=True).split())
        if text in DAYS:
            day, meal, zone = text, None, None
            continue
        if day != day_name:
            continue
        if text in MEALS:
            meal, zone = text, None
        elif text.endswith(" Zone"):
            zone = text[: -len(" Zone")]
        elif meal and tag.find("a", href=re.compile(r"^#collapse")):
            if text.lower() in SKIP_DISHES:
                continue
            item = (zone or "", text)
            if item not in menu.setdefault(meal, []):
                menu[meal].append(item)
    return menu


def format_location(name: str, menu: dict, url: str) -> str:
    if not menu:
        return f"{name}\n  (nothing parsed - closed today, or the page layout changed)\n  {url}\n"
    # Lunch and dinner are usually identical; merge them.
    meals = dict(menu)
    if "Lunch" in meals and meals.get("Lunch") == meals.get("Dinner"):
        meals["Lunch & Dinner"] = meals.pop("Lunch")
        meals.pop("Dinner")
    lines = [name]
    for meal, items in meals.items():
        lines.append(f"  {meal.upper()}")
        by_zone: dict = {}
        for zone, dish in items:
            by_zone.setdefault(zone, []).append(dish)
        for zone, dishes in by_zone.items():
            label = f"{zone}: " if zone else ""
            lines.append(f"    {label}{', '.join(dishes)}")
    return "\n".join(lines) + "\n"


def build_email() -> str:
    now = datetime.now(ZoneInfo("America/Los_Angeles"))
    day_name = DAYS[(now.weekday() + 1) % 7]  # Python: Monday=0; site starts at Sunday
    parts = [f"UC Davis dining - {now:%A, %B %d}\n"]
    for name, url in LOCATIONS.items():
        try:
            r = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0 (menu-emailer)"})
            r.raise_for_status()
            parts.append(format_location(name, parse_menu(r.text, day_name), url))
        except Exception as e:  # keep going if one site fails
            parts.append(f"{name}\n  (fetch failed: {e})\n")
    return "\n".join(parts)


def send(body: str) -> None:
    user = os.environ["GMAIL_USER"]
    msg = EmailMessage()
    msg["Subject"] = f"Dining menus - {datetime.now(ZoneInfo('America/Los_Angeles')):%a %b %d}"
    msg["From"] = user
    msg["To"] = os.environ.get("MAIL_TO", user)
    msg.set_content(body)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context()) as s:
        s.login(user, os.environ["GMAIL_APP_PASSWORD"])
        s.send_message(msg)


if __name__ == "__main__":
    body = build_email()
    if "--print" in sys.argv:
        print(body)
    else:
        send(body)
