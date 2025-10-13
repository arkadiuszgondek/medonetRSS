import sys
import time
import hashlib
import feedparser
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from dateutil import tz

# ---- KONFIG ----
OUTPUT_FILE = "docs/medonet.xml"
RETENTION_DAYS = 14
FALLBACK_IMAGE = "https://sm-cdn.eu/y37kjgxdy0ufdyjt.jpg"

FEEDS = [
    ("https://www.medonet.pl/.feed", "ogólny"),
    ("https://dziecko.medonet.pl/.feed", "dziecko"),
    ("https://uroda.medonet.pl/.feed", "uroda"),
    ("https://zywienie.medonet.pl/.feed", "żywienie"),
]

USER_AGENT = "medonetRSS/1.0 (+https://github.com/arkadiuszgondek/medonetRSS)"
TIMEZONE_PL = tz.gettz("Europe/Warsaw")

# ---- POMOCNICZE ----
def normalize_guid(entry):
    guid = getattr(entry, "id", None) or entry.get("guid") or entry.get("link")
    if not guid:
        base = f"{entry.get('title','')}-{entry.get('link','')}"
        guid = hashlib.sha1(base.encode("utf-8")).hexdigest()
    return guid

def entry_datetime(entry):
    tm = entry.get("published_parsed") or entry.get("updated_parsed")
    if tm:
        dt = datetime.fromtimestamp(time.mktime(tm), tz=timezone.utc).astimezone(TIMEZONE_PL)
    else:
        dt = datetime.now(TIMEZONE_PL)
    return dt

def fetch_feed(url):
    feedparser.USER_AGENT = USER_AGENT
    return feedparser.parse(url)

def extract_image(entry):
    # Priorytet: enclosure → media_content → media_thumbnail → fallback
    url = None
    if "enclosures" in entry and entry.enclosures:
        url = entry.enclosures[0].get("url")
    elif "media_content" in entry and entry.media_content:
        url = entry.media_content[0].get("url")
    elif "media_thumbnail" in entry and entry.media_thumbnail:
        url = entry.media_thumbnail[0].get("url")

    # czasem puste lub dziwne znaki
    if not url or not url.startswith("http"):
        url = FALLBACK_IMAGE
    return url

# ---- POBIERZ I POŁĄCZ ----
items = []
seen = set()

for url, label in FEEDS:
    parsed = fetch_feed(url)
    if parsed.bozo:
        sys.stderr.write(f"[WARN] Problem z feedem: {url}\n")

    for e in parsed.entries:
        guid = normalize_guid(e)
        if guid in seen:
            continue
        seen.add(guid)

        pub_dt = entry_datetime(e)
        img_url = extract_image(e)

        items.append({
            "guid": guid,
            "title": e.get("title", "").strip(),
            "link": e.get("link", "").strip(),
            "description": e.get("description", e.get("summary", "")).strip(),
            "pubDate": pub_dt,
            "label": label,
            "image": img_url
        })

# ---- FILTR RETENCJI I SORT ----
cutoff = datetime.now(TIMEZONE_PL) - timedelta(days=RETENTION_DAYS)
items = [it for it in items if it["pubDate"] >= cutoff]
items.sort(key=lambda x: x["pubDate"], reverse=True)

# ---- BUDOWA RSS 2.0 ----
rss = ET.Element("rss", attrib={
    "version": "2.0",
    "xmlns:media": "http://search.yahoo.com/mrss/"
})
channel = ET.SubElement(rss, "channel")
ET.SubElement(channel, "title").text = "medonetRSS – agregat (ogólny, dziecko, uroda, żywienie)"
ET.SubElement(channel, "link").text = "https://www.medonet.pl/"
ET.SubElement(channel, "description").text = "Zbiorczy RSS z wybranych sekcji Medonetu. Retencja: 14 dni."
ET.SubElement(channel, "language").text = "pl-PL"
ET.SubElement(channel, "lastBuildDate").text = datetime.now(TIMEZONE_PL).strftime("%a, %d %b %Y %H:%M:%S %z")

for it in items:
    item = ET.SubElement(channel, "item")
    ET.SubElement(item, "title").text = it["title"] or "(bez tytułu)"
    ET.SubElement(item, "link").text = it["link"]

    desc = ET.SubElement(item, "description")
    desc.text = it["description"]

    ET.SubElement(item, "guid").text = it["guid"]
    ET.SubElement(item, "pubDate").text = it["pubDate"].strftime("%a, %d %b %Y %H:%M:%S %z")
    ET.SubElement(item, "category").text = it["label"]

    # Dodaj klasyczny enclosure
    ET.SubElement(item, "enclosure", attrib={
        "url": it["image"],
        "length": "0",
        "type": "image/jpeg"
    })
    # oraz media:content (lepsza zgodność z agregatorami)
    ET.SubElement(item, "{http://search.yahoo.com/mrss/}content", attrib={
        "url": it["image"],
        "medium": "image"
    })

tree = ET.ElementTree(rss)
tree.write(OUTPUT_FILE, encoding="utf-8", xml_declaration=True)
print(f"OK: zapisano {OUTPUT_FILE} (pozycje: {len(items)}) z repo medonetRSS")
