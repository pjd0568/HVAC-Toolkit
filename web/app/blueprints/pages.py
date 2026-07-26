"""Public marketing pages: legal, contact, SEO helpers."""

from __future__ import annotations

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user

from app.mail import mail_configured, send_email

bp = Blueprint("pages", __name__)

# Subject prefixes for Gmail / Workspace filters on info@.
CONTACT_SUBJECTS = (
    ("help", "[Help]", "General help"),
    ("bug", "[Bug]", "Bug report"),
    ("feature", "[Feature]", "New feature suggestion"),
    ("info", "[Info]", "General information"),
    ("billing", "[Billing]", "Subscription queries"),
)


def _contact_map() -> dict[str, tuple[str, str]]:
    return {key: (prefix, label) for key, prefix, label in CONTACT_SUBJECTS}


@bp.get("/terms")
def terms():
    return render_template(
        "marketing/terms.html",
        legal_entity=current_app.config["LEGAL_ENTITY"],
        legal_jurisdiction=current_app.config["LEGAL_JURISDICTION"],
        contact_email=current_app.config["CONTACT_EMAIL"],
    )


@bp.get("/privacy")
def privacy():
    return render_template(
        "marketing/privacy.html",
        legal_entity=current_app.config["LEGAL_ENTITY"],
        legal_jurisdiction=current_app.config["LEGAL_JURISDICTION"],
        contact_email=current_app.config["CONTACT_EMAIL"],
    )


@bp.route("/contact", methods=["GET", "POST"])
def contact():
    subjects = CONTACT_SUBJECTS
    if request.method == "GET":
        return render_template(
            "marketing/contact.html",
            subjects=subjects,
            contact_email=current_app.config["CONTACT_EMAIL"],
            form={},
        )

    name = (request.form.get("name") or "").strip()
    email = (request.form.get("email") or "").strip()
    topic = (request.form.get("topic") or "").strip()
    message = (request.form.get("message") or "").strip()
    form = {"name": name, "email": email, "topic": topic, "message": message}

    errors: list[str] = []
    if not name:
        errors.append("Please enter your name.")
    if not email or "@" not in email:
        errors.append("Please enter a valid email address.")
    topic_map = _contact_map()
    if topic not in topic_map:
        errors.append("Please choose a subject.")
    if len(message) < 10:
        errors.append("Please enter a message (at least a short sentence).")
    if len(message) > 8000:
        errors.append("Message is too long.")

    if errors:
        for err in errors:
            flash(err, "error")
        return render_template(
            "marketing/contact.html",
            subjects=subjects,
            contact_email=current_app.config["CONTACT_EMAIL"],
            form=form,
        ), 400

    prefix, label = topic_map[topic]
    subject = f"{prefix} {name} via {current_app.config['BRAND_NAME']}"
    body_lines = [
        f"Topic: {label}",
        f"From: {name} <{email}>",
    ]
    if current_user.is_authenticated:
        body_lines.append(f"Signed-in account: {current_user.email}")
    body_lines.extend(["", message, "", f"— Sent from {request.host_url.rstrip('/')}/contact"])
    body = "\n".join(body_lines)

    to_addr = current_app.config["CONTACT_EMAIL"]
    if mail_configured():
        ok = send_email(to=to_addr, subject=subject, body=body, reply_to=email)
        if ok:
            flash(
                "Thanks — your message has been sent. We’ll reply to the email you provided.",
                "success",
            )
            return redirect(url_for("pages.contact"))
        flash(
            "We couldn’t send your message just now. Please email us directly "
            f"at {to_addr} (use subject starting with {prefix}).",
            "error",
        )
        return render_template(
            "marketing/contact.html",
            subjects=subjects,
            contact_email=to_addr,
            form=form,
        ), 503

    # No SMTP yet: keep the form usable by handing off to the user’s mail client.
    from urllib.parse import quote

    mailto = (
        f"mailto:{to_addr}"
        f"?subject={quote(subject)}"
        f"&body={quote(body)}"
    )
    return render_template(
        "marketing/contact_mailto.html",
        mailto=mailto,
        contact_email=to_addr,
        prefix=prefix,
    )


@bp.get("/robots.txt")
def robots_txt():
    base = current_app.config["PUBLIC_BASE_URL"].rstrip("/")
    lines = [
        "User-agent: *",
        "Allow: /",
        "Disallow: /app",
        "Disallow: /weather",
        "Disallow: /psychrometrics",
        "Disallow: /duct-sizing",
        "Disallow: /pipe-sizing",
        "Disallow: /converter",
        "Disallow: /projects",
        "Disallow: /reference",
        "Disallow: /help",
        "Disallow: /login",
        "Disallow: /register",
        "Disallow: /preferences/",
        "",
        f"Sitemap: {base}/sitemap.xml",
        "",
    ]
    return current_app.response_class("\n".join(lines), mimetype="text/plain")


@bp.get("/sitemap.xml")
def sitemap_xml():
    base = current_app.config["PUBLIC_BASE_URL"].rstrip("/")
    # Public marketing URLs only — calculators require login.
    paths = [
        ("/", "weekly", "1.0"),
        ("/subscribe", "weekly", "0.8"),
        ("/contact", "monthly", "0.6"),
        ("/terms", "yearly", "0.3"),
        ("/privacy", "yearly", "0.3"),
    ]
    urls = []
    for path, freq, priority in paths:
        urls.append(
            "  <url>\n"
            f"    <loc>{base}{path}</loc>\n"
            f"    <changefreq>{freq}</changefreq>\n"
            f"    <priority>{priority}</priority>\n"
            "  </url>"
        )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(urls)
        + "\n</urlset>\n"
    )
    return current_app.response_class(xml, mimetype="application/xml")
