import json
from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

# UI Label and Badge mapping
VERDICT_LABEL_MAP = {
    "verified": "Verified",
    "partial": "Partly matched",
    "unverified": "Couldn't verify",
    "suspicious": "Warning signs",
}

VERDICT_BADGE_MAP = {
    "verified": "badge-verified",
    "partial": "badge-partial",
    "unverified": "badge-unverified",
    "suspicious": "badge-suspicious",
}


def utc_now():
    """Return current UTC datetime."""
    return datetime.now(timezone.utc)


class User(db.Model):
    """Registered user authenticated via Google OAuth."""

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    google_sub = db.Column(db.String(255), unique=True, nullable=True, index=True)
    name = db.Column(db.String(255), nullable=True)
    picture = db.Column(db.String(1024), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)

    # Relationships
    checks = db.relationship(
        "Check",
        backref="user",
        lazy="dynamic",
        cascade="all, delete-orphan",
        order_by="desc(Check.created_at)",
    )

    def __repr__(self):
        return f"<User {self.email}>"

    def to_dict(self):
        return {
            "id": self.id,
            "email": self.email,
            "name": self.name,
            "picture": self.picture,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Check(db.Model):
    """Verification record storing extracted claim and verification verdict."""

    __tablename__ = "checks"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    input_hash = db.Column(db.String(64), nullable=False, index=True)
    claim_json = db.Column(db.Text, nullable=False)
    verdict_json = db.Column(db.Text, nullable=False)
    verdict = db.Column(db.String(32), nullable=False, index=True)
    confidence = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False, index=True)

    def __repr__(self):
        return f"<Check {self.id} user={self.user_id} verdict={self.verdict} conf={self.confidence}>"

    def get_claim(self) -> dict:
        """Parse stored claim JSON."""
        try:
            return json.loads(self.claim_json) if self.claim_json else {}
        except Exception:
            return {}

    def get_verdict(self) -> dict:
        """Parse stored verdict JSON."""
        try:
            return json.loads(self.verdict_json) if self.verdict_json else {}
        except Exception:
            return {}

    @property
    def ui_verdict_label(self) -> str:
        """Return human-friendly UI label for the verdict."""
        return VERDICT_LABEL_MAP.get(self.verdict, "Couldn't verify")

    @property
    def ui_badge_class(self) -> str:
        """Return CSS class for badge styling."""
        return VERDICT_BADGE_MAP.get(self.verdict, "badge-unverified")

    def to_dict(self, include_details: bool = True) -> dict:
        """Convert check record to dictionary for API responses."""
        claim_data = self.get_claim()
        verdict_data = self.get_verdict()

        data = {
            "id": self.id,
            "user_id": self.user_id,
            "input_hash": self.input_hash,
            "verdict": self.verdict,
            "verdict_label": self.ui_verdict_label,
            "badge_class": self.ui_badge_class,
            "confidence": self.confidence,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "formatted_date": self.created_at.strftime("%b %d, %Y %H:%M UTC") if self.created_at else "",
            "brand_or_company": claim_data.get("brand_or_company", ""),
            "category": claim_data.get("category", "other"),
        }

        if include_details:
            data.update({
                "claim": claim_data,
                "summary": verdict_data.get("summary", ""),
                "official_links": verdict_data.get("official_links", []),
                "red_flags": verdict_data.get("red_flags", []),
                "advice": verdict_data.get("advice", ""),
            })

        return data

