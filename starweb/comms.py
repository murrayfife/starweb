"""Diplomatic Communication System for StarWeb PBM.

Handles:
- Direct player-to-player messages (delivered next turn per rules)
- Alliance proposals and negotiations
- Trade offers and counter-offers
- Ceasefire/war declarations
- Message queuing (messages delivered on turn processing)
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class MessageType(Enum):
    DIPLOMATIC = "diplomatic"        # General diplomacy
    ALLIANCE_OFFER = "alliance_offer"
    ALLIANCE_ACCEPT = "alliance_accept"
    ALLIANCE_REJECT = "alliance_reject"
    TRADE_OFFER = "trade_offer"
    TRADE_ACCEPT = "trade_accept"
    TRADE_REJECT = "trade_reject"
    CEASEFIRE = "ceasefire"
    WAR_DECLARATION = "war_declaration"
    THREAT = "threat"
    INTEL_SHARE = "intel_share"
    LOADER_REQUEST = "loader_request"


class MessageStatus(Enum):
    QUEUED = "queued"        # Submitted, not yet delivered
    DELIVERED = "delivered"  # Delivered on turn processing
    READ = "read"            # Read by recipient
    EXPIRED = "expired"      # Too old, auto-expired


@dataclass
class DiplomaticMessage:
    id: int
    sender: str
    recipient: str
    message_type: MessageType
    subject: str
    body: str
    turn_sent: int
    turn_delivered: Optional[int] = None
    timestamp: float = 0.0
    status: MessageStatus = MessageStatus.QUEUED
    metadata: dict = field(default_factory=dict)  # For trade details, etc.

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "sender": self.sender,
            "recipient": self.recipient,
            "message_type": self.message_type.value,
            "subject": self.subject,
            "body": self.body,
            "turn_sent": self.turn_sent,
            "turn_delivered": self.turn_delivered,
            "timestamp": self.timestamp,
            "status": self.status.value,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DiplomaticMessage":
        return cls(
            id=data["id"],
            sender=data["sender"],
            recipient=data["recipient"],
            message_type=MessageType(data["message_type"]),
            subject=data["subject"],
            body=data["body"],
            turn_sent=data["turn_sent"],
            turn_delivered=data.get("turn_delivered"),
            timestamp=data.get("timestamp", 0.0),
            status=MessageStatus(data.get("status", "queued")),
            metadata=data.get("metadata", {}),
        )


@dataclass
class TradeOffer:
    """Structured trade offer between players."""
    offering_player: str
    receiving_player: str
    offering_metal: int = 0
    offering_ships: int = 0
    offering_world: Optional[int] = None
    offering_fleet: Optional[int] = None
    requesting_metal: int = 0
    requesting_ships: int = 0
    requesting_world: Optional[int] = None
    requesting_loader: bool = False
    requesting_alliance: bool = False
    duration_turns: int = 0  # 0 = permanent


class CommunicationSystem:
    """Manages all diplomatic communications for a game."""

    def __init__(self, game_id: str, storage_dir: Path):
        self.game_id = game_id
        self.storage_dir = storage_dir / game_id / "comms"
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._messages: list[DiplomaticMessage] = []
        self._next_id = 1
        self._load()

    def _load(self):
        filepath = self.storage_dir / "messages.json"
        if filepath.exists():
            data = json.loads(filepath.read_text())
            self._messages = [DiplomaticMessage.from_dict(m) for m in data["messages"]]
            self._next_id = data.get("next_id", len(self._messages) + 1)

    def _save(self):
        filepath = self.storage_dir / "messages.json"
        data = {
            "next_id": self._next_id,
            "messages": [m.to_dict() for m in self._messages],
        }
        filepath.write_text(json.dumps(data, indent=2))

    def send_message(self, sender: str, recipient: str, message_type: MessageType,
                     subject: str, body: str, turn: int,
                     metadata: Optional[dict] = None) -> DiplomaticMessage:
        """Queue a diplomatic message for delivery next turn."""
        msg = DiplomaticMessage(
            id=self._next_id,
            sender=sender,
            recipient=recipient,
            message_type=message_type,
            subject=subject,
            body=body,
            turn_sent=turn,
            timestamp=time.time(),
            status=MessageStatus.QUEUED,
            metadata=metadata or {},
        )
        self._messages.append(msg)
        self._next_id += 1
        self._save()
        return msg

    def deliver_messages(self, current_turn: int) -> list[DiplomaticMessage]:
        """Deliver all queued messages (called during turn processing).
        Messages are delivered the turn AFTER they are sent."""
        delivered = []
        for msg in self._messages:
            if msg.status == MessageStatus.QUEUED and msg.turn_sent < current_turn:
                msg.status = MessageStatus.DELIVERED
                msg.turn_delivered = current_turn
                delivered.append(msg)
        self._save()
        return delivered

    def get_inbox(self, player: str, status: Optional[MessageStatus] = None) -> list[DiplomaticMessage]:
        """Get messages for a player."""
        results = [m for m in self._messages if m.recipient == player]
        if status:
            results = [m for m in results if m.status == status]
        return sorted(results, key=lambda m: -m.timestamp)

    def get_outbox(self, player: str) -> list[DiplomaticMessage]:
        """Get messages sent by a player."""
        return sorted(
            [m for m in self._messages if m.sender == player],
            key=lambda m: -m.timestamp
        )

    def mark_read(self, message_id: int, reader: str) -> bool:
        """Mark a message as read."""
        for m in self._messages:
            if m.id == message_id and m.recipient == reader:
                if m.status == MessageStatus.DELIVERED:
                    m.status = MessageStatus.READ
                    self._save()
                    return True
        return False

    def get_conversation(self, player1: str, player2: str) -> list[DiplomaticMessage]:
        """Get all messages between two players."""
        results = [
            m for m in self._messages
            if (m.sender == player1 and m.recipient == player2) or
               (m.sender == player2 and m.recipient == player1)
        ]
        return sorted(results, key=lambda m: m.timestamp)

    def propose_trade(self, sender: str, recipient: str, turn: int,
                      offer: TradeOffer) -> DiplomaticMessage:
        """Send a structured trade proposal."""
        metadata = {
            "offering_metal": offer.offering_metal,
            "offering_ships": offer.offering_ships,
            "offering_world": offer.offering_world,
            "offering_fleet": offer.offering_fleet,
            "requesting_metal": offer.requesting_metal,
            "requesting_ships": offer.requesting_ships,
            "requesting_world": offer.requesting_world,
            "requesting_loader": offer.requesting_loader,
            "requesting_alliance": offer.requesting_alliance,
            "duration_turns": offer.duration_turns,
        }
        body = self._format_trade_offer(offer)
        return self.send_message(
            sender, recipient, MessageType.TRADE_OFFER,
            f"Trade Proposal from {sender}", body, turn, metadata
        )

    def propose_alliance(self, sender: str, recipient: str, turn: int,
                         terms: str = "") -> DiplomaticMessage:
        """Send an alliance proposal."""
        return self.send_message(
            sender, recipient, MessageType.ALLIANCE_OFFER,
            f"Alliance Proposal from {sender}",
            f"I propose we form an alliance.\n\nTerms: {terms}" if terms
            else "I propose we form an alliance for mutual benefit.",
            turn
        )

    def declare_war(self, sender: str, recipient: str, turn: int,
                    reason: str = "") -> DiplomaticMessage:
        """Send a war declaration."""
        return self.send_message(
            sender, recipient, MessageType.WAR_DECLARATION,
            f"Declaration of War from {sender}",
            f"War has been declared against you.\n\nReason: {reason}" if reason
            else "Consider yourself warned. War is upon you.",
            turn
        )

    def share_intel(self, sender: str, recipient: str, turn: int,
                    intel: dict) -> DiplomaticMessage:
        """Share intelligence about other players or worlds."""
        body = "Intelligence Report:\n"
        for key, value in intel.items():
            body += f"  {key}: {value}\n"
        return self.send_message(
            sender, recipient, MessageType.INTEL_SHARE,
            f"Intel from {sender}", body, turn, metadata=intel
        )

    def get_pending_offers(self, player: str) -> list[DiplomaticMessage]:
        """Get unresolved trade/alliance offers for a player."""
        offer_types = {MessageType.TRADE_OFFER, MessageType.ALLIANCE_OFFER}
        return [
            m for m in self._messages
            if m.recipient == player and m.message_type in offer_types
            and m.status in {MessageStatus.DELIVERED, MessageStatus.READ}
        ]

    def get_stats(self) -> dict:
        """Get communication statistics."""
        return {
            "total_messages": len(self._messages),
            "queued": sum(1 for m in self._messages if m.status == MessageStatus.QUEUED),
            "delivered": sum(1 for m in self._messages if m.status == MessageStatus.DELIVERED),
            "read": sum(1 for m in self._messages if m.status == MessageStatus.READ),
            "by_type": {
                t.value: sum(1 for m in self._messages if m.message_type == t)
                for t in MessageType
            },
        }

    @staticmethod
    def _format_trade_offer(offer: TradeOffer) -> str:
        lines = ["Trade Proposal:", ""]
        lines.append("I offer:")
        if offer.offering_metal:
            lines.append(f"  - {offer.offering_metal} metal")
        if offer.offering_ships:
            lines.append(f"  - {offer.offering_ships} ships")
        if offer.offering_world:
            lines.append(f"  - World {offer.offering_world}")
        if offer.offering_fleet:
            lines.append(f"  - Fleet {offer.offering_fleet}")
        lines.append("")
        lines.append("In exchange for:")
        if offer.requesting_metal:
            lines.append(f"  - {offer.requesting_metal} metal")
        if offer.requesting_ships:
            lines.append(f"  - {offer.requesting_ships} ships")
        if offer.requesting_world:
            lines.append(f"  - World {offer.requesting_world}")
        if offer.requesting_loader:
            lines.append("  - Loader status")
        if offer.requesting_alliance:
            lines.append("  - Alliance declaration")
        if offer.duration_turns:
            lines.append(f"\nDuration: {offer.duration_turns} turns")
        return "\n".join(lines)
