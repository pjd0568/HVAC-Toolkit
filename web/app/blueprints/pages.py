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

from app.contact_guard import client_ip, release, reserve
from app.mail import mail_configured, send_email
from app.turnstile import turnstile_configured, turnstile_site_key, verify_turnstile_response

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


@bp.get("/tools/")
def tools_index():
    from app.seo_tools import list_landings

    return render_template(
        "marketing/tools_index.html",
        landings=list_landings(),
    )


@bp.route("/tools/<slug>", methods=["GET", "POST"])
def tool_landing(slug: str):
    from flask import abort, g

    from app.seo_tools import get_landing

    landing = get_landing(slug)
    if landing is None:
        abort(404)
    if landing.free_view:
        # Same server-side calculation as the signed-in tool. No second formula path.
        g.public_embed = True
        g.public_landing = landing
        view = current_app.view_functions.get(landing.free_view)
        if view is None:
            abort(404)
        return view()
    related = [get_landing(s) for s in landing.related_slugs]
    related = [r for r in related if r is not None]
    return render_template(
        "marketing/tool_landing.html",
        landing=landing,
        related=related,
    )


@bp.get("/about")
def about():
    return render_template("marketing/about.html")


@bp.get("/methods")
def methods():
    return render_template("marketing/methods.html")


@bp.get("/privacy")
def privacy():
    return render_template(
        "marketing/privacy.html",
        legal_entity=current_app.config["LEGAL_ENTITY"],
        legal_jurisdiction=current_app.config["LEGAL_JURISDICTION"],
        contact_email=current_app.config["CONTACT_EMAIL"],
    )


def _render_contact(subjects, form, errors, status: int = 200):
    rendered = render_template(
        "marketing/contact.html",
        subjects=subjects,
        contact_email=current_app.config["CONTACT_EMAIL"],
        form=form,
        errors=errors,
        turnstile_site_key=turnstile_site_key() if turnstile_configured() else "",
    )
    if status == 200:
        return rendered
    return rendered, status


@bp.route("/contact", methods=["GET", "POST"])
def contact():
    subjects = CONTACT_SUBJECTS
    if request.method == "GET":
        return _render_contact(subjects, {}, [])

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
        errors.append("Please choose a subject from the list.")
    if len(message) < 5:
        errors.append("Please enter a longer message (at least 5 characters).")
    if len(message) > 8000:
        errors.append("Message is too long.")
    if turnstile_configured() and not verify_turnstile_response(
        request.form.get("cf-turnstile-response")
    ):
        errors.append("Please complete the human check and try again.")

    if errors:
        return _render_contact(subjects, form, errors, 400)

    to_addr = current_app.config["CONTACT_EMAIL"]
    ip = client_ip()
    reason, stamp = reserve(ip, message)
    if reason == "rate":
        current_app.logger.info("contact rate-limited ip=%s", ip)
        return _render_contact(
            subjects,
            form,
            [
                "Too many messages from this connection. Please wait an hour, "
                f"or email us directly at {to_addr}."
            ],
            429,
        )
    if reason == "duplicate":
        current_app.logger.info("contact duplicate dropped ip=%s", ip)
        return _render_contact(
            subjects,
            form,
            [
                "We already received this message recently. If you need to add "
                f"something, change the wording or email us directly at {to_addr}."
            ],
            400,
        )

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

    if mail_configured():
        ok = send_email(to=to_addr, subject=subject, body=body, reply_to=email)
        if ok:
            flash(
                "Thanks — your message has been sent. We’ll reply to the email you provided.",
                "success",
            )
            return redirect(url_for("pages.contact"))
        if stamp is not None:
            release(ip, message, stamp)
        return _render_contact(
            subjects,
            form,
            [
                f"We couldn’t send your message just now. Please email us directly "
                f"at {to_addr} (use subject starting with {prefix})."
            ],
            503,
        )

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
        "Allow: /tools/",
        "Allow: /methods",
        "Allow: /about",
        "Allow: /reference",
        "Allow: /methodology",
        "Disallow: /app",
        "Disallow: /v2/",
        "Disallow: /weather",
        "Disallow: /psychrometrics",
        "Disallow: /duct-sizing",
        "Disallow: /pipe-sizing",
        "Disallow: /refrigeration",
        "Disallow: /converter",
        "Disallow: /projects",
        "Disallow: /help",
        "Disallow: /login",
        "Disallow: /register",
        "Disallow: /preferences/",
        "Disallow: /create-checkout-session",
        "Disallow: /admin/",
        "",
        f"Sitemap: {base}/sitemap.xml",
        "",
    ]
    return current_app.response_class("\n".join(lines), mimetype="text/plain")


@bp.get("/BingSiteAuth.xml")
def bing_site_auth():
    """Bing Webmaster Tools XML verification file (site root)."""
    from flask import send_from_directory

    static_dir = current_app.static_folder or ""
    return send_from_directory(
        static_dir,
        "BingSiteAuth.xml",
        mimetype="application/xml",
    )


@bp.get("/sitemap.xml")
def sitemap_xml():
    from app.seo_tools import list_landings

    base = current_app.config["PUBLIC_BASE_URL"].rstrip("/")
    # Public marketing URLs only — logged-in calculators stay out of the sitemap.
    paths = [
        ("/", "weekly", "1.0"),
        ("/tools/", "weekly", "0.9"),
        ("/methods", "monthly", "0.7"),
        ("/about", "monthly", "0.5"),
        ("/reference/", "monthly", "0.6"),
        ("/subscribe", "weekly", "0.8"),
        ("/contact", "monthly", "0.6"),
        ("/terms", "yearly", "0.3"),
        ("/privacy", "yearly", "0.3"),
    ]
    for landing in list_landings():
        paths.append((f"/tools/{landing.slug}", "monthly", "0.85"))
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
