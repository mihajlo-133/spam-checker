"""
Spam Checker — Web UI + API

Local web interface and team API for checking email copy against
772 spam trigger patterns (mirroring Mailmeteor's spam checker).

Usage:
    # Local dev
    python app.py

    # Production (Render)
    gunicorn app:app --bind 0.0.0.0:$PORT

API Endpoints:
    POST /api/check    — Check email text, returns JSON
    GET  /api/health   — Health check
    GET  /             — Web UI
"""

import os

from flask import Flask, render_template, request, jsonify
from spam_checker import check_spam, SPAM_PATTERNS, CATEGORY_ICONS

app = Flask(__name__)


# ─── Web UI ──────────────────────────────────────────────────────────

@app.route("/")
def index():
    pattern_counts = {}
    for _, _, cat in SPAM_PATTERNS:
        pattern_counts[cat] = pattern_counts.get(cat, 0) + 1
    return render_template("index.html", pattern_counts=pattern_counts, total=len(SPAM_PATTERNS))


# ─── API ─────────────────────────────────────────────────────────────

@app.route("/api/check", methods=["POST"])
def api_check():
    """
    Check email copy for spam trigger words.

    Accepts:
        JSON: {"text": "email copy here"}
        Form: text=email+copy+here

    Returns:
        {
            "score": 31,
            "rating": "Poor",
            "total_hits": 13,
            "word_count": 12,
            "categories": {
                "urgency": ["Act", "Click", "Now", ...],
                "shady": ["Free", "Free offer", ...]
            }
        }
    """
    if request.is_json:
        data = request.get_json()
        text = data.get("text", "")
    else:
        text = request.form.get("text", "")

    if not text.strip():
        return jsonify({"error": "No text provided"}), 400

    result = check_spam(text)

    return jsonify({
        "score": result["score"],
        "rating": result["rating"],
        "total_hits": result["total_hits"],
        "word_count": result["word_count"],
        "categories": {
            cat: [item["keyword"] for item in items]
            for cat, items in result["categories"].items()
        },
    })


@app.route("/api/health")
def health():
    return jsonify({
        "status": "ok",
        "patterns": len(SPAM_PATTERNS),
        "categories": ["urgency", "shady", "overpromise", "money", "unnatural"],
    })


# ─── Run ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    print(f"Spam Checker running at http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=True)
