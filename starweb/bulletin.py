"""Bulletin Board System for StarWeb PBM.

Provides persistent bulletin boards for:
- Game-wide announcements (GM only)
- Public player messages (visible to all)
- Alliance/faction boards (visible to declared allies)
- Trading post (merchant offers)
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class BoardType(Enum):
    ANNOUNCEMENTS = "announcements"  # GM only
    PUBLIC = "public"                # All players can post/read
    ALLIANCE = "alliance"           # Only allies can read
    TRADING = "trading"             # Trade offers
    PRIVATE = "private"             # DMs between players


@dataclass
class Post:
    id: int
    board: BoardType
    author: str
    subject: str
    body: str
    timestamp: float
    turn: int
    reply_to: Optional[int] = None
    visible_to: list[str] = field(default_factory=list)  # empty = all
    pinned: bool = False
    reactions: dict[str, list[str]] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "board": self.board.value,
            "author": self.author,
            "subject": self.subject,
            "body": self.body,
            "timestamp": self.timestamp,
            "turn": self.turn,
            "reply_to": self.reply_to,
            "visible_to": self.visible_to,
            "pinned": self.pinned,
            "reactions": self.reactions,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Post":
        return cls(
            id=data["id"],
            board=BoardType(data["board"]),
            author=data["author"],
            subject=data["subject"],
            body=data["body"],
            timestamp=data["timestamp"],
            turn=data["turn"],
            reply_to=data.get("reply_to"),
            visible_to=data.get("visible_to", []),
            pinned=data.get("pinned", False),
            reactions=data.get("reactions", {}),
        )


class BulletinBoard:
    """Manages all bulletin boards for a game."""

    def __init__(self, game_id: str, storage_dir: Path):
        self.game_id = game_id
        self.storage_dir = storage_dir / game_id / "boards"
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._posts: list[Post] = []
        self._next_id = 1
        self._load()

    def _load(self):
        filepath = self.storage_dir / "posts.json"
        if filepath.exists():
            data = json.loads(filepath.read_text())
            self._posts = [Post.from_dict(p) for p in data["posts"]]
            self._next_id = data.get("next_id", len(self._posts) + 1)

    def _save(self):
        filepath = self.storage_dir / "posts.json"
        data = {
            "next_id": self._next_id,
            "posts": [p.to_dict() for p in self._posts],
        }
        filepath.write_text(json.dumps(data, indent=2))

    def post(self, board: BoardType, author: str, subject: str, body: str,
             turn: int, reply_to: Optional[int] = None,
             visible_to: Optional[list[str]] = None) -> Post:
        """Create a new post on a board."""
        post = Post(
            id=self._next_id,
            board=board,
            author=author,
            subject=subject,
            body=body,
            timestamp=time.time(),
            turn=turn,
            reply_to=reply_to,
            visible_to=visible_to or [],
        )
        self._posts.append(post)
        self._next_id += 1
        self._save()
        return post

    def get_board(self, board: BoardType, reader: str,
                  allies: Optional[set[str]] = None) -> list[Post]:
        """Get all posts visible to a reader on a board."""
        allies = allies or set()
        results = []
        for p in self._posts:
            if p.board != board:
                continue
            # Visibility check
            if p.visible_to and reader not in p.visible_to and p.author != reader:
                continue
            if board == BoardType.ALLIANCE:
                if p.author != reader and p.author not in allies:
                    continue
            results.append(p)
        return sorted(results, key=lambda p: (-p.pinned, -p.timestamp))

    def get_thread(self, post_id: int) -> list[Post]:
        """Get a post and all its replies."""
        thread = [p for p in self._posts if p.id == post_id or p.reply_to == post_id]
        return sorted(thread, key=lambda p: p.timestamp)

    def get_unread(self, reader: str, since_turn: int,
                   allies: Optional[set[str]] = None) -> list[Post]:
        """Get all posts since a given turn that are visible to reader."""
        allies = allies or set()
        results = []
        for p in self._posts:
            if p.turn < since_turn:
                continue
            if p.visible_to and reader not in p.visible_to and p.author != reader:
                continue
            if p.board == BoardType.ALLIANCE and p.author not in allies and p.author != reader:
                continue
            results.append(p)
        return sorted(results, key=lambda p: p.timestamp)

    def pin_post(self, post_id: int, author: str) -> bool:
        """Pin a post (only author or GM can pin)."""
        for p in self._posts:
            if p.id == post_id and (p.author == author or author == "GM"):
                p.pinned = True
                self._save()
                return True
        return False

    def react(self, post_id: int, reactor: str, emoji: str) -> bool:
        """Add a reaction to a post."""
        for p in self._posts:
            if p.id == post_id:
                if emoji not in p.reactions:
                    p.reactions[emoji] = []
                if reactor not in p.reactions[emoji]:
                    p.reactions[emoji].append(reactor)
                self._save()
                return True
        return False

    def delete_post(self, post_id: int, requester: str) -> bool:
        """Delete a post (only author or GM)."""
        for i, p in enumerate(self._posts):
            if p.id == post_id and (p.author == requester or requester == "GM"):
                self._posts.pop(i)
                self._save()
                return True
        return False

    def search(self, query: str, reader: str,
               allies: Optional[set[str]] = None) -> list[Post]:
        """Search posts by keyword."""
        allies = allies or set()
        query_lower = query.lower()
        results = []
        for p in self._posts:
            if p.visible_to and reader not in p.visible_to:
                continue
            if p.board == BoardType.ALLIANCE and p.author not in allies and p.author != reader:
                continue
            if query_lower in p.subject.lower() or query_lower in p.body.lower():
                results.append(p)
        return results

    def get_stats(self) -> dict:
        """Get board statistics."""
        stats = {}
        for board in BoardType:
            posts = [p for p in self._posts if p.board == board]
            stats[board.value] = {
                "total_posts": len(posts),
                "authors": len(set(p.author for p in posts)),
                "latest_turn": max((p.turn for p in posts), default=0),
            }
        return stats
