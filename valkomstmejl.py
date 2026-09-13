#!/usr/bin/env python3
"""Välkomstmejl med rabattkod till nya prenumeranter från rabattkodsrutan.

Körs var 5:e minut av GitHub Actions (.github/workflows/valkomstmejl.yml):
  1. hämtar kunder med taggen valkommen10 (sv) eller velkommen10 (nb) som
     saknar taggen valkomstmejl-skickat,
  2. mejlar koden på rätt språk som support@nordlights.se via Simplys SMTP,
  3. sätter taggen valkomstmejl-skickat så att ingen får mejlet två gånger.

Hemligheter i miljön (GitHub-secrets): SHOPIFY_CLIENT_ID, SHOPIFY_CLIENT_SECRET,
SMTP_PASSWORD.

  python3 valkomstmejl.py                      # en körning
  python3 valkomstmejl.py --test <mejl> sv|nb  # provmejl, rör inte Shopify
"""
import json
import os
import urllib.request
import smtplib
import ssl
import subprocess
import sys
from datetime import datetime
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid

STORE = "emhhmp-1k.myshopify.com"
VERSION = "2026-07"

SENDER = "support@nordlights.se"
SENDER_NAME = "NORDLIGHTS"
HOST, PORT = "smtp.simply.com", 587
SENT_TAG = "valkomstmejl-skickat"

LANG = {
    "sv": {
        "tag": "valkommen10",
        "code": "VALKOMMEN10",
        "subject": "Här är din rabattkod – 10 % extra hos NORDLIGHTS",
        "preheader": "Gäller hela beställningen, ovanpå reapriset.",
        "hello": "Välkommen till NORDLIGHTS!",
        "intro": "Tack för att du vill ha våra nyheter. Här är din rabattkod:",
        "body": "Den ger 10 % på hela beställningen och läggs ovanpå reapriserna och "
                "mängdrabatten. Skriv in koden i kassan – den kan användas en gång.",
        "cta": "Handla nu",
        "url": "https://nordlights.se/products/tindra",
        "usp": "Fri frakt och 30 dagars öppet köp på alla beställningar.",
        "footer": "Du får det här mejlet eftersom du anmält dig till nyheter från NORDLIGHTS.",
        "unsub": "Vill du inte ha fler mejl?",
        "unsub_link": "Avregistrera dig här",
        "unsub_subject": "Avregistrera",
    },
    "nb": {
        "tag": "velkommen10",
        "code": "VELKOMMEN10",
        "subject": "Her er rabattkoden din – 10 % ekstra hos NORDLIGHTS",
        "preheader": "Gjelder hele bestillingen, i tillegg til salgsprisen.",
        "hello": "Velkommen til NORDLIGHTS!",
        "intro": "Takk for at du vil ha nyhetene våre. Her er rabattkoden din:",
        "body": "Den gir 10 % på hele bestillingen og kommer i tillegg til salgsprisene og "
                "mengderabatten. Skriv inn koden i kassen – den kan brukes én gang.",
        "cta": "Handle nå",
        "url": "https://nordlights.se/nb-no/products/tindra",
        "usp": "Fri frakt og 30 dagers åpent kjøp på alle bestillinger.",
        "footer": "Du får denne e-posten fordi du har meldt deg på nyheter fra NORDLIGHTS.",
        "unsub": "Vil du ikke ha flere e-poster?",
        "unsub_link": "Meld deg av her",
        "unsub_subject": "Meld av",
    },
}


def log(*a):
    print(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), *a, flush=True)


_token = None


def post(url, payload, headers=None):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json", **(headers or {})})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def token():
    global _token
    if not _token:
        d = post(f"https://{STORE}/admin/oauth/access_token", {
            "grant_type": "client_credentials",
            "client_id": os.environ["SHOPIFY_CLIENT_ID"],
            "client_secret": os.environ["SHOPIFY_CLIENT_SECRET"],
        })
        _token = d["access_token"]
    return _token


def api(query):
    data = post(f"https://{STORE}/admin/api/{VERSION}/graphql.json", {"query": query},
                {"X-Shopify-Access-Token": token()})
    if data.get("errors"):
        raise RuntimeError(data["errors"])
    return data["data"]


def html(t):
    return f"""<div style="display:none;max-height:0;overflow:hidden">{t['preheader']}</div>
<div style="max-width:560px;margin:0 auto;padding:32px 20px;text-align:center;font-family:-apple-system,BlinkMacSystemFont,Arial,sans-serif;color:#202225">
  <p style="margin:0 0 24px;font-size:22px;font-weight:700;letter-spacing:2px">NORDLIGHTS</p>
  <h1 style="margin:0 0 12px;font-size:26px;line-height:1.25">{t['hello']}</h1>
  <p style="margin:0 0 20px;font-size:16px;line-height:1.5">{t['intro']}</p>
  <p style="margin:0 auto 20px;display:inline-block;padding:14px 28px;border:2px dashed #202225;font-size:26px;font-weight:700;letter-spacing:3px">{t['code']}</p>
  <p style="margin:0 0 28px;font-size:15px;line-height:1.55;color:#444">{t['body']}</p>
  <p style="margin:0 0 28px"><a href="{t['url']}" style="background:#202225;color:#fff;text-decoration:none;padding:14px 32px;border-radius:6px;font-weight:600;display:inline-block">{t['cta']}</a></p>
  <p style="margin:0 0 32px;font-size:14px;color:#444">{t['usp']}</p>
  <p style="margin:0;font-size:12px;line-height:1.5;color:#888">{t['footer']}<br>{t['unsub']} <a href="mailto:{SENDER}?subject={t['unsub_subject']}" style="color:#888">{t['unsub_link']}</a>.</p>
</div>"""


def text(t):
    return (f"{t['hello']}\n\n{t['intro']}\n\n{t['code']}\n\n{t['body']}\n\n"
            f"{t['cta']}: {t['url']}\n\n{t['usp']}\n\n{t['footer']}\n"
            f"{t['unsub']} {SENDER}")


def password():
    return os.environ["SMTP_PASSWORD"]


def build(to, lang):
    t = LANG[lang]
    msg = EmailMessage()
    msg["From"] = formataddr((SENDER_NAME, SENDER))
    msg["To"] = to
    msg["Subject"] = t["subject"]
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain="nordlights.se")
    msg["List-Unsubscribe"] = f"<mailto:{SENDER}?subject={t['unsub_subject']}>"
    msg.set_content(text(t))
    msg.add_alternative(html(t), subtype="html")
    return msg


def send(messages):
    with smtplib.SMTP(HOST, PORT, timeout=30) as s:
        s.starttls(context=ssl.create_default_context())
        s.login(SENDER, password())
        for msg in messages:
            yield msg, s.send_message(msg)


def run():
    q = (f'(tag:{LANG["sv"]["tag"]} OR tag:{LANG["nb"]["tag"]}) AND NOT tag:{SENT_TAG}')
    data = api('{ customers(first: 50, query: %s) { nodes { id tags '
               'defaultEmailAddress { emailAddress marketingState } } } }' % json.dumps(q))
    todo = []
    for c in data["customers"]["nodes"]:
        tags = [x.lower() for x in c["tags"]]
        if SENT_TAG in tags:
            continue
        e = c.get("defaultEmailAddress") or {}
        if not e.get("emailAddress") or e.get("marketingState") in ("UNSUBSCRIBED", "REDACTED", "INVALID"):
            continue
        lang = "nb" if LANG["nb"]["tag"] in tags else "sv"
        todo.append((c["id"], e["emailAddress"], lang))
    if not todo:
        return
    by_msg = {}
    msgs = []
    for cid, to, lang in todo:
        m = build(to, lang)
        by_msg[m["Message-ID"]] = (cid, to, lang)
        msgs.append(m)
    for m, refused in send(msgs):
        cid, to, lang = by_msg[m["Message-ID"]]
        if refused:
            log("AVVISAD", to, refused)
            continue
        r = api('mutation { tagsAdd(id: %s, tags: ["%s"]) { userErrors { message } } }' % (json.dumps(cid), SENT_TAG))
        errs = r["tagsAdd"]["userErrors"]
        log("skickat", lang, to, "| TAGGFEL: %s" % errs if errs else "")


def main():
    if len(sys.argv) >= 2 and sys.argv[1] == "--test":
        to, lang = sys.argv[2], sys.argv[3]
        for m, refused in send([build(to, lang)]):
            log("provmejl", lang, to, "| avvisade:", refused or "inga")
        return
    try:
        run()
    except Exception as e:  # syns i Actions-loggen och ger röd körning
        log("FEL", repr(e))
        sys.exit(1)

if __name__ == "__main__":
    main()
