"""
Spam Checker — Web UI + API

Local web interface and team API for checking email copy against
spam trigger patterns (mirroring Mailmeteor's spam checker).

Usage:
    # Local dev
    python app.py

    # Production (Render)
    gunicorn app:app --bind 0.0.0.0:$PORT

Routes:
    GET  /              — Web UI (check email copy)
    GET  /docs          — API reference (HTML, human-readable)
    GET  /llms.txt      — API reference (markdown, for AI agents)
    GET  /openapi.json  — OpenAPI 3.1 specification
    POST /api/check     — Check email text, returns JSON
    GET  /api/health    — Health check
"""

import os

from pathlib import Path

from flask import Flask, render_template, request, jsonify, Response, url_for
from spam_checker import check_spam, SPAM_PATTERNS, CATEGORY_ICONS

app = Flask(__name__)


# ─── Helpers ─────────────────────────────────────────────────────────

CATEGORIES = ["urgency", "shady", "overpromise", "money", "unnatural"]


def _pattern_counts() -> dict[str, int]:
    counts = {cat: 0 for cat in CATEGORIES}
    for _, _, cat in SPAM_PATTERNS:
        counts[cat] = counts.get(cat, 0) + 1
    return counts


def _base_url() -> str:
    """Return canonical base URL without trailing slash."""
    # Prefer the production URL when deployed; fall back to request host for local dev.
    if "RENDER" in os.environ or "PORT" in os.environ and os.environ.get("PORT") != "5050":
        return "https://spam-checker-gig9.onrender.com"
    return request.url_root.rstrip("/")


# ─── Web UI ──────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template(
        "index.html",
        pattern_counts=_pattern_counts(),
        total=len(SPAM_PATTERNS),
    )


@app.route("/docs")
def docs():
    return render_template(
        "docs.html",
        pattern_counts=_pattern_counts(),
        total=len(SPAM_PATTERNS),
        base_url=_base_url(),
    )


# ─── Machine-readable docs ───────────────────────────────────────────

_LLMS_TXT_PATH = Path(__file__).parent / "static" / "llms.txt"


@app.route("/llms.txt")
def llms_txt():
    """Plain markdown docs optimized for LLM consumption (emerging llms.txt standard)."""
    content = _LLMS_TXT_PATH.read_text(encoding="utf-8")
    return Response(content, mimetype="text/plain; charset=utf-8")


@app.route("/openapi.json")
def openapi_spec():
    """OpenAPI 3.1 specification for programmatic client generation."""
    base = _base_url()
    spec = {
        "openapi": "3.1.0",
        "info": {
            "title": "Spam Checker API",
            "version": "1.0.0",
            "summary": "Score email copy against spam-trigger patterns.",
            "description": (
                "Stateless HTTP API that scores email copy against "
                f"{len(SPAM_PATTERNS)} regex patterns across 5 categories. "
                "Mirrors Mailmeteor's spam-checker scoring algorithm. "
                "No authentication, deterministic, safe for AI-agent consumption."
            ),
            "license": {"name": "MIT"},
            "contact": {"url": "https://github.com/mihajlo-133/spam-checker"},
        },
        "servers": [{"url": base, "description": "Production"}],
        "paths": {
            "/api/check": {
                "post": {
                    "operationId": "checkSpam",
                    "summary": "Check email copy for spam triggers.",
                    "description": (
                        "Submit email text and receive a deterministic spam score, "
                        "rating, and the specific keywords matched per category."
                    ),
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/CheckRequest"},
                                "examples": {
                                    "clean": {
                                        "summary": "Clean B2B cold email",
                                        "value": {
                                            "text": "Hi Sarah, noticed your team is hiring SDRs — quick question about your onboarding process."
                                        },
                                    },
                                    "spammy": {
                                        "summary": "Obvious spam",
                                        "value": {"text": "Act now for a free offer! Click here!"},
                                    },
                                },
                            },
                            "application/x-www-form-urlencoded": {
                                "schema": {"$ref": "#/components/schemas/CheckRequest"}
                            },
                        },
                    },
                    "responses": {
                        "200": {
                            "description": "Scored result.",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/CheckResponse"}
                                }
                            },
                        },
                        "400": {
                            "description": "Missing or empty text field.",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Error"}
                                }
                            },
                        },
                    },
                }
            },
            "/api/health": {
                "get": {
                    "operationId": "getHealth",
                    "summary": "Health check and capability discovery.",
                    "responses": {
                        "200": {
                            "description": "Service is up.",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/HealthResponse"}
                                }
                            },
                        }
                    },
                }
            },
        },
        "components": {
            "schemas": {
                "CheckRequest": {
                    "type": "object",
                    "required": ["text"],
                    "properties": {
                        "text": {
                            "type": "string",
                            "minLength": 1,
                            "description": "Email subject + body as a single string.",
                        }
                    },
                },
                "CheckResponse": {
                    "type": "object",
                    "required": ["score", "rating", "total_hits", "word_count", "categories"],
                    "properties": {
                        "score": {
                            "type": "integer",
                            "description": "Raw numeric score. Higher = spammier. No upper bound.",
                        },
                        "rating": {
                            "type": "string",
                            "enum": ["Great", "Okay", "Poor"],
                            "description": "Derived from score: >20 Poor, >5 Okay, else Great.",
                        },
                        "total_hits": {
                            "type": "integer",
                            "description": "Unique (keyword, category) matches.",
                        },
                        "word_count": {
                            "type": "integer",
                            "description": "Whitespace-split word count of the input text.",
                        },
                        "categories": {
                            "type": "object",
                            "description": "Matched keywords grouped by category.",
                            "additionalProperties": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "example": {
                                "urgency": ["Act", "Now"],
                                "shady": ["Free"],
                            },
                        },
                    },
                },
                "HealthResponse": {
                    "type": "object",
                    "required": ["status", "patterns", "categories"],
                    "properties": {
                        "status": {"type": "string", "enum": ["ok"]},
                        "patterns": {"type": "integer"},
                        "categories": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "enum": CATEGORIES,
                            },
                        },
                    },
                },
                "Error": {
                    "type": "object",
                    "required": ["error"],
                    "properties": {"error": {"type": "string"}},
                },
            }
        },
        "x-scoring-algorithm": {
            "description": "Deterministic score derivation used by POST /api/check.",
            "pseudocode": [
                "score = total_hits",
                "if 'money' in matched_categories or 'shady' in matched_categories: score += 20",
                "if 'urgency' in matched_categories or 'overpromise' in matched_categories: score += 10",
                "rating = 'Poor' if score > 20 else 'Okay' if score > 5 else 'Great'",
            ],
        },
        "x-agent-guidance": {
            "when_to_use": [
                "Check email copy for spam triggers before sending cold email.",
                "Compare copy variants and pick the one with the lowest score.",
                "Filter LLM-generated drafts for deliverability risk.",
            ],
            "when_not_to_use": [
                "General deliverability scoring (DNS/auth/reputation not checked).",
                "Inbox placement prediction (requires seedlist testing).",
                "Content moderation (tuned for marketing spam, not abuse detection).",
            ],
            "rating_action_map": {
                "Great": "Copy is clean. Ship it.",
                "Okay": "Review flagged words; rewrite 1-2 specific terms. Often acceptable for B2B cold email.",
                "Poor": "High risk. Rewrite required. Inspect categories to see which buckets contributed.",
            },
            "calibration_notes": [
                "Engine is aggressive for B2B: words like 'new', 'please', 'open' may trigger 'unnatural'.",
                "Poor ratings driven entirely by 'unnatural' hits are usually false positives for B2B outbound.",
                "Poor ratings with any 'money' or 'shady' hit are almost always true positives.",
            ],
        },
    }
    return jsonify(spec)


# ─── API ─────────────────────────────────────────────────────────────

@app.route("/api/check", methods=["POST"])
def api_check():
    """Check email copy for spam trigger words.

    Accepts:
        JSON: {"text": "email copy here"}
        Form: text=email+copy+here
    """
    if request.is_json:
        data = request.get_json(silent=True) or {}
        text = data.get("text", "")
    else:
        text = request.form.get("text", "")

    if not isinstance(text, str) or not text.strip():
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
        "categories": CATEGORIES,
    })


# ─── Run ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    print(f"Spam Checker running at http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=True)
