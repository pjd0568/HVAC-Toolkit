from flask import Blueprint, render_template

bp = Blueprint("billing", __name__)


@bp.get("/subscribe")
def subscribe():
    """Pricing / subscribe placeholder — Stripe Checkout later."""
    return render_template("marketing/subscribe.html")
