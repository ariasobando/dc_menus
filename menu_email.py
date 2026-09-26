#!/usr/bin/env python3
"""Email today's UC Davis dining menus as a formatted HTML email.

Sends one individual email per recipient (nobody sees anyone else's address).

Env vars: GMAIL_USER, GMAIL_APP_PASSWORD, MAIL_TO (comma-separated; defaults to GMAIL_USER)
Usage:    python menu_email.py            # send emails
          python menu_email.py --print    # print HTML source (for testing)
          python menu_email.py --preview  # write preview.html, viewable locally
"""
import os
import re
import smtplib
import ssl
import sys
from datetime import datetime
from email.message import EmailMessage
from html import escape
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
MEALS = ["Breakfast", "Lunch", "Dinner"]

# Zone hours, entered manually from the site's "Zone Hours" tab (not scraped --
# that tab has a different layout than the menu, and hours rarely change).
# "weekday" = Mon-Fri, "weekend" = Sat-Sun. A zone with no entry just shows no
# hours next to it. Add other locations here the same way once you have them.
ZONE_HOURS = {
    "Segundo DC": {
        "weekday": {
            "Breakfast": {
                "Red": "7-11 AM", "Yellow": "7-10:15 AM", "Purple": "Closed",
                "Blue": "Closed", "Green": "7-11 AM", "Pink": "7-11 AM",
            },
            "Lunch": {
                "Red": "11:30 AM-2, 4-5 PM", "Yellow": "11:30 AM-2 PM", "Purple": "11 AM-5 PM",
                "Blue": "11 AM-3:30 PM", "Green": "11 AM-5 PM", "Pink": "11 AM-5 PM",
            },
            "Dinner": {
                "Red": "5-10 PM", "Yellow": "5-10 PM", "Purple": "5-10 PM",
                "Blue": "5-8 PM", "Green": "5-10 PM", "Pink": "5-10 PM",
            },
        },
        "weekend": {
            "Breakfast": {
                "Red": "9-11 AM", "Yellow": "9-11 AM", "Purple": "Closed",
                "Blue": "Closed", "Green": "9-11 AM", "Pink": "9-11 AM",
            },
            "Lunch": {
                "Red": "11-1:30, 2-5 PM", "Yellow": "11 AM-5 PM", "Purple": "11 AM-5 PM",
                "Blue": "Closed", "Green": "11 AM-5 PM", "Pink": "11 AM-5 PM",
            },
            "Dinner": {
                "Red": "5-8 PM", "Yellow": "5-8 PM", "Purple": "5-8 PM",
                "Blue": "Closed", "Green": "5-8 PM", "Pink": "5-8 PM",
            },
        },
    },
    "Tercero DC": {
        "weekday": {
            "Breakfast": {
                "Red": "Closed", "Yellow": "7-10:30 AM", "Purple": "Closed",
                "Blue": "7-11 AM", "Green": "7-11 AM", "Pink": "7-11 AM",
            },
            "Lunch": {
                "Red": "11 AM-5 PM", "Yellow": "11 AM-2 PM", "Purple": "11 AM-5 PM",
                "Blue": "11:30 AM-4 PM", "Green": "11 AM-5 PM", "Pink": "11 AM-5 PM",
            },
            "Dinner": {
                "Red": "5-10 PM", "Yellow": "5-10 PM", "Purple": "5-10 PM",
                "Blue": "5-10 PM", "Green": "5-10 PM", "Pink": "5-10 PM",
            },
        },
        "weekend": {
            "Breakfast": {"Red": "Closed", "Yellow": "Closed", "Purple": "Closed",
                           "Blue": "Closed", "Green": "Closed", "Pink": "Closed"},
            "Lunch": {"Red": "Closed", "Yellow": "Closed", "Purple": "Closed",
                      "Blue": "Closed", "Green": "Closed", "Pink": "Closed"},
            "Dinner": {"Red": "Closed", "Yellow": "Closed", "Purple": "Closed",
                       "Blue": "Closed", "Green": "Closed", "Pink": "Closed"},
        },
    },
    "Cuarto DC": {
        "weekday": {
            "Breakfast": {
                "Red": "7-11 AM", "Yellow": "7-11 AM", "Purple": "Closed",
                "Blue": "Closed", "Green": "7-11 AM", "Pink": "7-11 AM",
            },
            "Lunch": {
                "Red": "11 AM-5 PM", "Yellow": "11 AM-2 PM", "Purple": "11 AM-5 PM",
                "Blue": "11 AM-5 PM", "Green": "11 AM-5 PM", "Pink": "11 AM-5 PM",
            },
            "Dinner": {
                "Red": "5-10 PM", "Yellow": "5-10 PM", "Purple": "5-10 PM",
                "Blue": "5-10 PM", "Green": "5-10 PM", "Pink": "5-10 PM",
            },
        },
        "weekend": {
            "Breakfast": {"Red": "Closed", "Yellow": "Closed", "Purple": "Closed",
                           "Blue": "Closed", "Green": "Closed", "Pink": "Closed"},
            "Lunch": {"Red": "Closed", "Yellow": "Closed", "Purple": "Closed",
                      "Blue": "Closed", "Green": "Closed", "Pink": "Closed"},
            "Dinner": {"Red": "Closed", "Yellow": "Closed", "Purple": "Closed",
                       "Blue": "Closed", "Green": "Closed", "Pink": "Closed"},
        },
    },
    "Latitude": {
        # Latitude's page calls this tab "Platform Hours" and only has 4 zones
        # (no Purple/Pink).
        "weekday": {
            "Breakfast": {"Red": "8-10:30 AM", "Blue": "8-10:30 AM",
                          "Yellow": "8-10:30 AM", "Green": "8-10:30 AM"},
            "Lunch": {"Red": "10:30 AM-4:30 PM", "Blue": "10:30 AM-3 PM",
                      "Yellow": "10:30 AM-4:30 PM", "Green": "10:30 AM-3 PM"},
            "Dinner": {"Red": "4:30-8 PM", "Blue": "4:30-8 PM",
                       "Yellow": "4:30-8 PM", "Green": "4:30-8 PM"},
        },
        "weekend": {
            "Breakfast": {"Red": "Closed", "Blue": "Closed", "Yellow": "Closed", "Green": "Closed"},
            "Lunch": {"Red": "Closed", "Blue": "Closed", "Yellow": "Closed", "Green": "Closed"},
            "Dinner": {"Red": "Closed", "Blue": "Closed", "Yellow": "Closed", "Green": "Closed"},
        },
    },
}

# Staples that are always there; hide them so the email is just the interesting stuff.
# Set to set() to see everything.
SKIP_DISHES = {
    "too lazy to remove this vibe coded part",
}

# Any dish whose name contains one of these (case-insensitive) gets starred and
# highlighted. Add/remove freely -- partial words are fine, e.g. "pupusa" matches
# "Pork Pupusas" too.
FAVORITES = [
    "pupusa", "cubano", "burger bar", "muffin", "french toast",
    "byo", "build your own", "(byo) burger",
]

DIET_STYLES = {
    # label shown -> (background, text color)
    "Vegan": ("#dff5e1", "#1b6b34"),
    "Vegetarian": ("#e8f3d6", "#4f7a1a"),
    "Halal": ("#e6eefc", "#2a4d8f"),
}

def parse_menu(html: str, day_name: str) -> dict:
    """Return {meal: [(zone, dish, tags), ...]} for one day."""
    soup = BeautifulSoup(html, "html.parser")
    headings = soup.find_all(["h1", "h2", "h3", "h4", "h5"])
    day = meal = zone = None
    menu: dict = {}

    for idx, tag in enumerate(headings):
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
            tags = set()
            for sib in tag.find_all_next():
                if sib in headings[idx + 1:idx + 2]:
                    break
                if sib.name == "img":
                    alt = (sib.get("alt") or "").strip()
                    if alt in DIET_STYLES:
                        tags.add(alt)
                if sib.name in ("h1", "h2", "h3", "h4", "h5"):
                    break
            bucket = menu.setdefault(meal, [])
            if not any(z == (zone or "") and d == text for z, d, _ in bucket):
                bucket.append((zone or "", text, frozenset(tags)))
    return menu


def is_favorite(dish: str) -> bool:
    low = dish.lower()
    return any(f in low for f in FAVORITES)


def render_dish(dish: str) -> str:
    fav = is_favorite(dish)
    style = "font-weight:600;" if fav else ""
    star = "\u2b50 " if fav else ""
    return f'<span style="{style}">{star}{escape(dish)}</span>'


def render_tags(tags: frozenset) -> str:
    order = ["Vegan", "Vegetarian", "Halal"]
    out = []
    for t in order:
        if t in tags:
            bg, fg = DIET_STYLES[t]
            out.append(
                f'<span style="background:{bg};color:{fg};border-radius:10px;'
                f'padding:1px 7px;font-size:11px;font-weight:600;margin-left:6px;'
                f'white-space:nowrap;">{t}</span>'
            )
    return "".join(out)


def render_location(name: str, menu: dict, url: str, day_kind: str) -> str:
    header = (
        f'<h2 style="margin:28px 0 6px;font-size:18px;border-bottom:2px solid #DAAA00;'
        f'padding-bottom:4px;">{escape(name)}</h2>'
    )
    if not menu:
        return header + (
            f'<p style="color:#888;font-size:13px;">Nothing parsed today &mdash; '
            f'closed, or the page layout changed. <a href="{url}">Check the site</a>.</p>'
        )

    loc_hours = ZONE_HOURS.get(name, {}).get(day_kind, {})

    html_parts = [header]
    for meal, items in menu.items():
        html_parts.append(
            f'<div style="margin:14px 0 4px;font-size:13px;font-weight:700;'
            f'text-transform:uppercase;letter-spacing:.04em;color:#555;">{escape(meal)}</div>'
        )
        by_zone: dict = {}
        for zone, dish, tags in items:
            by_zone.setdefault(zone, []).append((dish, tags))
        meal_hours = loc_hours.get(meal, {})
        for zone, dishes in by_zone.items():
            hours = meal_hours.get(zone, "")
            hours_html = (
                f' <span style="color:#999;font-weight:400;">({escape(hours)})</span>'
                if hours else ""
            )
            zone_label = f'<b>{escape(zone)}</b>{hours_html}: ' if zone else ""
            rows = ", ".join(render_dish(d) + render_tags(t) for d, t in dishes)
            html_parts.append(
                f'<div style="margin:2px 0 2px 8px;font-size:14px;line-height:1.5;">'
                f'{zone_label}{rows}</div>'
            )
    return "".join(html_parts)


def build_email_html() -> str:
    now = datetime.now(ZoneInfo("America/Los_Angeles"))
    day_name = DAYS[(now.weekday() + 1) % 7]  # Python: Monday=0; site starts at Sunday
    day_kind = "weekend" if now.weekday() >= 5 else "weekday"  # Sat=5, Sun=6
    body = [
        '<div style="font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;'
        'max-width:600px;margin:0 auto;color:#222;">',
        f'<h1 style="font-size:20px;margin-bottom:0;">UC Davis Dining</h1>',
        f'<div style="color:#666;font-size:13px;margin-bottom:8px;">{now:%A, %B %d}</div>',
        '<div style="font-size:12px;color:#999;margin-bottom:2px;">\u2b50 = favorite</div>',
        '<div style="font-size:12px;color:#999;margin-bottom:2px;">badges = dietary info '
        '(not everything is tagged on the site)</div>',
        '<div style="font-size:12px;color:#999;margin-bottom:8px;">hours in parentheses '
        'are entered manually and assume the schedule hasn\u2019t changed since it was entered</div>',
    ]
    for name, url in LOCATIONS.items():
        try:
            r = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0 (menu-emailer)"})
            r.raise_for_status()
            body.append(render_location(name, parse_menu(r.text, day_name), url, day_kind))
        except Exception as e:  # keep going if one site fails
            body.append(
                f'<h2 style="margin:28px 0 6px;font-size:18px;">{escape(name)}</h2>'
                f'<p style="color:#c00;font-size:13px;">Fetch failed: {escape(str(e))}</p>'
            )
    body.append("</div>")
    return "".join(body)


def send_all(html: str) -> None:
    user = os.environ["GMAIL_USER"]
    password = os.environ["GMAIL_APP_PASSWORD"]
    recipients = [
        e.strip() for e in os.environ.get("MAIL_TO", user).split(",") if e.strip()
    ]
    subject = f"Dining menus - {datetime.now(ZoneInfo('America/Los_Angeles')):%a %b %d}"

    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context()) as s:
        s.login(user, password)
        for to in recipients:
            msg = EmailMessage()
            msg["Subject"] = subject
            msg["From"] = user
            msg["To"] = to  # one recipient per message -- nobody sees the others
            msg.set_content("This email requires HTML support to view.")
            msg.add_alternative(html, subtype="html")
            s.send_message(msg)


if __name__ == "__main__":
    html = build_email_html()
    if "--print" in sys.argv:
        print(html)
    elif "--preview" in sys.argv:
        with open("preview.html", "w") as f:
            f.write(html)
        print("Wrote preview.html")
    else:
        send_all(html)
