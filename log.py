"""Logs the lowest listed price to data/prices.csv. Runs on a schedule."""
import csv, datetime, json, os, subprocess, sys, time

PAGE = "https://www.eldorado.gg/creatures-of-sonaria-mushrooms/g/280"
API = ("https://www.eldorado.gg/api/predefinedOffers/augmentedGame/offers"
       "?gameId=280&category=Currency&pageSize=150&useNewCurrencyScores=true&pageIndex=")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
CSV_PATH, STATUS_PATH = "data/prices.csv", "data/status.json"
HEADER = ["time", "price", "seller", "min_qty_k", "stock_k", "offers", "currency", "src"]
SAMPLES = int(os.environ.get("SAMPLES", "5"))   # checks per run
EVERY = int(os.environ.get("EVERY", "60"))      # seconds between checks
KEEP_DAYS = 30


def now():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)


def fetch(page):
    out = subprocess.run(
        ["curl", "-sS", "--compressed", "--max-time", "20", "-w", "\n%{http_code}",
         "-A", UA,
         "-H", "Accept: application/json, text/plain, */*",
         "-H", "Accept-Language: en-GB,en;q=0.9",
         "-H", "Referer: " + PAGE,
         "-b", "eldoradogg_currencyPreference=GBP; eldoradogg_locale=en-US",
         API + str(page)],
        capture_output=True, text=True, timeout=40)
    body, _, code = out.stdout.rpartition("\n")
    if code != "200":
        raise RuntimeError("HTTP %s %s" % (code, (out.stderr or body)[:160].replace("\n", " ")))
    return json.loads(body)


def price_of(o):
    d = o["offer"].get("pricePerUnitWithDiscount") or {}
    return float(d.get("amount") or o["offer"]["pricePerUnit"]["amount"])


def best_offer():
    offers, page, total = [], 1, 1
    while page <= total and page <= 5:
        r = fetch(page)
        offers += r.get("results") or []
        total = int(r.get("totalPages") or 1)
        page += 1
    valid = [o for o in offers
             if o["offer"].get("offerState") == "Active"
             and o["offer"].get("pricePerUnit")
             and float(o["offer"]["pricePerUnit"]["amount"]) > 0
             and float(o["offer"]["quantity"]) >= float(o["offer"]["minQuantity"])]
    if not valid:
        raise RuntimeError("no usable offers")
    b = min(valid, key=price_of)
    seller = str(b["user"]["username"])
    for ch in ',\r\n"':
        seller = seller.replace(ch, " ")
    return {"price": ("%.7f" % price_of(b)).rstrip("0").rstrip("."),
            "seller": seller,
            "min": "%d" % float(b["offer"]["minQuantity"]),
            "stock": "%d" % float(b["offer"]["quantity"]),
            "offers": str(len(offers)),
            "cur": str(b["offer"]["pricePerUnit"]["currency"])}


def main():
    os.makedirs("data", exist_ok=True)
    rows = []
    if os.path.exists(CSV_PATH):
        with open(CSV_PATH, newline="", encoding="utf-8") as f:
            rows = [r for r in csv.reader(f) if r][1:]
    last = (rows[-1][1], rows[-1][2]) if rows else None
    ok, err = 0, ""
    for i in range(SAMPLES):
        if i:
            time.sleep(EVERY)
        try:
            b = best_offer()
            ok += 1
            if i == 0 or (b["price"], b["seller"]) != last:
                rows.append([now().strftime("%Y-%m-%dT%H:%M:%SZ"), b["price"], b["seller"],
                             b["min"], b["stock"], b["offers"], b["cur"], "cloud"])
                last = (b["price"], b["seller"])
        except Exception as e:  # keep going, note the problem
            err = str(e)[:200]
            print("check failed:", err, file=sys.stderr)
    cutoff = (now() - datetime.timedelta(days=KEEP_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = [r for r in rows if r[0] >= cutoff]
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(HEADER)
        w.writerows(rows)
    with open(STATUS_PATH, "w", encoding="utf-8") as f:
        json.dump({"time": now().strftime("%Y-%m-%dT%H:%M:%SZ"), "ok": ok,
                   "samples": SAMPLES, "error": err}, f)
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
