"""SQLite database operations for wallpaper generation history and preferences."""

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class Generation:
    """A wallpaper generation record."""

    id: Optional[int]
    prompt: str
    image_path: str
    category: str
    style: str
    mood: str
    custom_input: Optional[str]
    rating: Optional[int]
    created_at: datetime

    @classmethod
    def from_row(cls, row: tuple) -> "Generation":
        return cls(
            id=row[0],
            prompt=row[1],
            image_path=row[2],
            category=row[3],
            style=row[4],
            mood=row[5],
            custom_input=row[6],
            rating=row[7],
            created_at=datetime.fromisoformat(row[8]),
        )


@dataclass
class Preference:
    """A preference summary record."""

    id: Optional[int]
    summary_text: str
    updated_at: datetime

    @classmethod
    def from_row(cls, row: tuple) -> "Preference":
        return cls(
            id=row[0],
            summary_text=row[1],
            updated_at=datetime.fromisoformat(row[2]),
        )


def get_db_path() -> Path:
    """Get the database path, creating directories if needed."""
    db_dir = Path.home() / ".local" / "share" / "wallpaper-ai"
    db_dir.mkdir(parents=True, exist_ok=True)
    return db_dir / "wallpapers.db"


def get_images_dir() -> Path:
    """Get the images directory, creating it if needed."""
    images_dir = Path.home() / ".local" / "share" / "wallpaper-ai" / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    return images_dir


def get_connection() -> sqlite3.Connection:
    """Get a database connection."""
    return sqlite3.connect(get_db_path())


def init_db() -> None:
    """Initialize the database schema."""
    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS generations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prompt TEXT NOT NULL,
                image_path TEXT NOT NULL,
                category TEXT NOT NULL,
                style TEXT NOT NULL,
                mood TEXT NOT NULL,
                custom_input TEXT,
                rating INTEGER,
                created_at TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS preferences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                summary_text TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_generations_rating
            ON generations(rating)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_generations_created_at
            ON generations(created_at DESC)
        """)

        conn.commit()


def save_generation(
    prompt: str,
    image_path: str,
    category: str,
    style: str,
    mood: str,
    custom_input: Optional[str] = None,
) -> int:
    """Save a new generation to the database. Returns the generation ID."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO generations (prompt, image_path, category, style, mood, custom_input, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (prompt, image_path, category, style, mood, custom_input, datetime.now().isoformat()),
        )
        conn.commit()
        return cursor.lastrowid


def update_rating(generation_id: int, rating: int) -> None:
    """Update the rating for a generation."""
    if not 1 <= rating <= 5:
        raise ValueError("Rating must be between 1 and 5")

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE generations SET rating = ? WHERE id = ?",
            (rating, generation_id),
        )
        conn.commit()


def get_generation(generation_id: int) -> Optional[Generation]:
    """Get a generation by ID."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM generations WHERE id = ?", (generation_id,))
        row = cursor.fetchone()
        return Generation.from_row(row) if row else None


def get_latest_generation() -> Optional[Generation]:
    """Get the most recent generation."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM generations ORDER BY created_at DESC LIMIT 1")
        row = cursor.fetchone()
        return Generation.from_row(row) if row else None


def get_recent_generations(limit: int = 20) -> list[Generation]:
    """Get recent generations."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM generations ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        return [Generation.from_row(row) for row in cursor.fetchall()]


def get_top_rated(limit: int = 5) -> list[Generation]:
    """Get the highest-rated generations."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT * FROM generations
            WHERE rating IS NOT NULL AND rating >= 4
            ORDER BY rating DESC, created_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        return [Generation.from_row(row) for row in cursor.fetchall()]


def get_low_rated(limit: int = 3) -> list[Generation]:
    """Get the lowest-rated generations."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT * FROM generations
            WHERE rating IS NOT NULL AND rating <= 2
            ORDER BY rating ASC, created_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        return [Generation.from_row(row) for row in cursor.fetchall()]


def get_rated_generations() -> list[Generation]:
    """Get all rated generations for preference analysis."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT * FROM generations
            WHERE rating IS NOT NULL
            ORDER BY created_at DESC
            """
        )
        return [Generation.from_row(row) for row in cursor.fetchall()]


def save_preference(summary_text: str) -> int:
    """Save a new preference summary. Returns the preference ID."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO preferences (summary_text, updated_at)
            VALUES (?, ?)
            """,
            (summary_text, datetime.now().isoformat()),
        )
        conn.commit()
        return cursor.lastrowid


def get_latest_preference() -> Optional[Preference]:
    """Get the most recent preference summary."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM preferences ORDER BY updated_at DESC LIMIT 1")
        row = cursor.fetchone()
        return Preference.from_row(row) if row else None


def get_generation_count() -> int:
    """Get total number of generations."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM generations")
        return cursor.fetchone()[0]


def get_rated_count() -> int:
    """Get number of rated generations."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM generations WHERE rating IS NOT NULL")
        return cursor.fetchone()[0]
