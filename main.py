import asyncio
import json
import os
import re
import random
import io
import requests
import traceback
import html as html_module
import xml.etree.ElementTree as ET

from urllib.parse import urlparse, parse_qs
from datetime import datetime, timedelta
from typing import Optional, Tuple
from pathlib import Path

import dotenv
from dotenv import load_dotenv

import aiohttp
from aiohttp import web

import bs4
from bs4 import BeautifulSoup

from PIL import Image, ImageDraw, ImageFont

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

import discord
from discord.ext import commands, tasks
from discord import app_commands, Object


# ---------------- CONFIG ----------------
TEST_GUILD_ID = 1409038531329917044

# Channel IDs
TRANSACTIONS_CHANNEL_ID = 1416462357718241410
TRANSACTIONS_HELP_CHANNEL_ID = 1426624895722197193
MATCH_SCORE_CHANNEL_ID = 1409043896989777982
MATCH_TIMES_CHANNEL_ID = 1409044495743582268
ASSIGNMENTS_CHANNEL_ID = 1454349005202002012
SCRIM_CATEGORY_ID = 1410590393527046275
SEEDING_POINTS_CHANNEL_ID = 1409043839418896425  # <- replace 0 with your seeding-points channel ID


# Force-time review channel (staff-only announcement)
FORCE_TIME_REVIEW_CHANNEL_ID = 1538368507421655091

# Role IDs
HEAD_REF_ROLE_ID = 1521592074485629088
REF_ROLE_ID = 1409044267908993187
HEAD_CASTER_ROLE_ID = 1521592036795482393
CASTER_ROLE_ID = 1409044226418675814

CAPTAIN_ROLE_ID = 1409046071971151982
CO_CAPTAIN_ROLE_ID = 1409044157334290492
TEAM_PLAYER_ROLE_ID = 1409044068482158744
TEAM_EXEC_ROLE_ID = 1521591557747245277

BOARD_OF_DIRECTORS_ROLE_ID = 1409038947413135370  # @Board Of Directors
COMMUNITY_MANAGER_ROLE_ID = 1476793870887948411   # @Community Manager
SUPERVISOR_ROLE_ID        = 1409057069566525471   # @Supervisor
DEVELOPMENT_TEAM_ROLE_ID  = 1465209483872567369   # <-- replace 0 with your Dev Team role ID

MAX_EXECUTIVES = 1
MAX_CAPTAINS = 1
MAX_CO_CAPTAINS = 2

BRACKET_CHANNEL_ID = 1409043839418896425
BRACKET_BASE_IMAGE_PATH = "MMM BRACKET.png"
BRACKET_OUTPUT_IMAGE_PATH = "MMM_BRACKET_FILLED.png"



EXECUTIVE_ROLE_NAME = "Team-Executive"

NON_TEAM_ROLE_NAMES = {
    "@everyone",
    "Executive",
    "Admin",
    "Administrator",
    "Moderator",
    "Mod",
    "Staff",
    "Owner",
    "Captain",
    "Co-Captain",
    "Co Captain",
    "Bot",
    "Bots",
    "Muted",
    "Verified",
}



ROSTER_LOCKED = False
SEEDING_OPEN = False
FORCE_WARN_DAYS = 4
FORCE_WARN_MARKER = "⚠️"

# Default config persisted to config.json (uses the IDs above as defaults)
DEFAULT_CONFIG = {
    "channels": {
        "transactions": TRANSACTIONS_CHANNEL_ID,
        "faq": None,
        "submit_time": MATCH_TIMES_CHANNEL_ID,
        "submit_score": MATCH_SCORE_CHANNEL_ID,
        "scheduling": None,
        "assignments": ASSIGNMENTS_CHANNEL_ID,
        "force_time_review": FORCE_TIME_REVIEW_CHANNEL_ID,
    },
    "roles": {
        "captain": CAPTAIN_ROLE_ID,
        "co_captain": CO_CAPTAIN_ROLE_ID,
        "executive": TEAM_EXEC_ROLE_ID,
        "team_member": TEAM_PLAYER_ROLE_ID,
        "caster": CASTER_ROLE_ID,
        "referee": REF_ROLE_ID,
    },
    "roster_rules": {
        "max_roster": 12,
        "max_co_captains": 2,
        "max_executive": 1,
    },
}

# ---------------- FILES ----------------
data_dir = Path(os.getenv("data_file", "/data"))
data_dir.mkdir(parents=True, exist_ok=True)

TEAMS_FILE = data_dir / "teams.json"
PLAYER_HISTORY_FILE = data_dir / "player_history.json"
INVITES_FILE = data_dir / "invites.json"
ROSTER_LOCK_FILE = data_dir / "roster_lock.json"
CONFIG_FILE = data_dir / "config.json"
YOUTUBE_STATE_FILE = data_dir / "youtube_state.json"
CODES_STATE_FILE = data_dir / "codes_state.json"
HEADSETS_FILE = data_dir / "headsets.json"
GROUPS_FILE = data_dir / "groups.json"

# ---------- STANDINGS WEB CACHE ----------
STANDINGS_CHANNEL_ID = 1453096022292168947
STANDINGS_CACHE_FILE = data_dir / "standings_cache.json"
PERSIST_STANDINGS_CACHE = True

_standings_cache = {
    "html": None,
    "raw": None,
    "ts": None,
    "message_id": None,
    "author": None,
}

_standings_lock = asyncio.Lock()



# X/Y positions are the *centers* of the first‑round boxes.
# Adjust by a few pixels if they are still slightly off in your image.
BRACKET_SLOT_COORDS = {
    # LEFT SIDE (1–12) – ROUND 1 boxes
    1:  (228,  32),
    2:  (228, 122),
    3:  (228, 212),
    4:  (228, 302),
    5:  (228, 392),
    6:  (228, 482),   # offset from your (88, 482)
    7:  (228, 572),
    8:  (228, 662),
    9:  (228, 752),
    10: (228, 842),
    11: (228, 932),
    12: (228, 1022),

    # RIGHT SIDE (13–24) – ROUND 1 boxes
    13: (1396,  31),
    14: (1396, 121),
    15: (1396, 211),
    16: (1396, 301),
    17: (1396, 391),
    18: (1396, 481),  # offset from your (1536, 479)
    19: (1396, 571),
    20: (1396, 661),
    21: (1396, 751),
    22: (1396, 841),
    23: (1396, 931),
    24: (1396, 1021),
}




def format_list_arrow(items: list[str]) -> str:
    if not items:
        return "> • None"
    return "\n".join(f"> • {it}" for it in items)





DEFAULT_HEADSETS = [
    "Meta Quest 2",
    "Meta Quest 3",
    "Meta Quest 3s",
    "HTC Vive",
    "HTC Vive Pro",
    "Valve Index",
]

def load_headsets() -> list[str]:
    if not HEADSETS_FILE.is_file():
        return DEFAULT_HEADSETS.copy()
    try:
        with HEADSETS_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                # ensure all strings
                return [str(x) for x in data]
    except Exception:
        pass
    return DEFAULT_HEADSETS.copy()

def save_headsets(headsets: list[str]):
    try:
        with HEADSETS_FILE.open("w", encoding="utf-8") as f:
            json.dump(headsets, f, indent=2)
    except Exception:
        pass





def load_codes_state() -> dict:
    if not CODES_STATE_FILE.is_file():
        return {}
    try:
        with CODES_STATE_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}

def save_codes_state(data: dict):
    try:
        with CODES_STATE_FILE.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass



def save_config(cfg):
    try:
        with CONFIG_FILE.open("w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass

def load_config():
    if not CONFIG_FILE.is_file():
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()
    try:
        with CONFIG_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return DEFAULT_CONFIG.copy()

CONFIG = load_config()

# Standing / player-history paths

def load_teams() -> list[dict]:
    if not TEAMS_FILE.is_file():
        return []
    try:
        with TEAMS_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
    except Exception:
        pass
    return []



# invites.json structure:
# {
#   "TEAM_ROLE_ID_STR": [USER_ID_INT, ...],
#   ...
# }

def load_invites() -> dict:
    if not INVITES_FILE.is_file():
        return {}
    try:
        with INVITES_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def save_invites(data: dict):
    try:
        with INVITES_FILE.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


def add_pending_invite(team_role_id: int, user_id: int):
    data = load_invites()
    key = str(team_role_id)
    lst = data.get(key, [])
    if user_id not in lst:
        lst.append(user_id)
    data[key] = lst
    save_invites(data)


def remove_pending_invite(team_role_id: int, user_id: int):
    data = load_invites()
    key = str(team_role_id)
    lst = data.get(key)
    if not isinstance(lst, list):
        return
    if user_id in lst:
        lst.remove(user_id)
    if lst:
        data[key] = lst
    else:
        data.pop(key, None)
    save_invites(data)


def load_groups_state() -> dict:
    if not GROUPS_FILE.is_file():
        return {}
    try:
        with GROUPS_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}

def save_groups_state(data: dict):
    try:
        with GROUPS_FILE.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


def find_member_team_role(member: discord.Member) -> discord.Role | None:
    """
    Strictly detect this member's real team role.

    Requirements for a role to be considered a 'team role':
    - Its ID is listed in teams.json
    - Its name is not a separator/fake (e.g. '————————Team Roles————————')
    - At least one non-bot member in the guild has BOTH:
        - this role
        - and a captain / co-captain / executive / team_player role
    """

    guild = member.guild

    # Load teams.json
    try:
        teams = load_teams()
    except Exception:
        teams = []

    team_ids_from_file: set[int] = set()
    for entry in teams:
        rid = entry.get("role_id")
        if not rid:
            continue
        try:
            team_ids_from_file.add(int(rid))
        except (TypeError, ValueError):
            continue

    # Helper to detect obvious separator/fake roles
    def _is_fake_team_role(r: discord.Role) -> bool:
        name = (r.name or "").strip().lower()
        # e.g. "————————Team Roles————————"
        if "team roles" in name:
            return True
        # names that are basically just dashes/lines/underscores/spaces
        if name and all(ch in "-—_ " for ch in name):
            return True
        return False

    # Helper: is this role actually used as a *team* role by at least one staff/player?
    def _is_real_team_role(r: discord.Role) -> bool:
        if r.id not in team_ids_from_file:
            return False
        if _is_fake_team_role(r):
            return False

        for g_member in guild.members:
            if g_member.bot:
                continue
            if r not in g_member.roles:
                continue
            # must have one of the global team staff/player roles
            if any(
                has_role_id(g_member, rid)
                for rid in (
                    CAPTAIN_ROLE_ID,
                    CO_CAPTAIN_ROLE_ID,
                    TEAM_EXEC_ROLE_ID,
                    TEAM_PLAYER_ROLE_ID,
                )
            ):
                return True

        return False

    # Collect member's roles that qualify as "real team roles"
    candidates: list[discord.Role] = []
    for r in member.roles:
        if _is_real_team_role(r):
            candidates.append(r)

    if not candidates:
        return None

    # Return the highest role in the guild hierarchy
    return max(candidates, key=lambda r: r.position)

# ---------- STANDINGS HELPERS ----------

async def _load_standings_cache():
    global _standings_cache

    if not PERSIST_STANDINGS_CACHE:
        return

    try:
        if not STANDINGS_CACHE_FILE.is_file():
            return

        with STANDINGS_CACHE_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, dict):
            _standings_cache.update(data)

    except Exception:
        print("Failed to load standings cache:")
        traceback.print_exc()


async def _save_standings_cache():
    if not PERSIST_STANDINGS_CACHE:
        return

    try:
        tmp = STANDINGS_CACHE_FILE.with_suffix(".json.tmp")

        with tmp.open("w", encoding="utf-8") as f:
            json.dump(_standings_cache, f, ensure_ascii=False, indent=2)

        os.replace(tmp, STANDINGS_CACHE_FILE)

    except Exception:
        print("Failed to save standings cache:")
        traceback.print_exc()


def _discord_message_to_safe_html(msg: discord.Message) -> Tuple[str | None, str]:
    """
    Converts a Discord standings message into safe HTML.

    Includes:
    - message.content
    - embed title
    - embed description
    - embed fields

    Everything is escaped to prevent XSS.
    """

    raw_parts = []
    html_parts = []

    if msg.content:
        raw_parts.append(msg.content)

        escaped_content = html_module.escape(msg.content)
        html_parts.append(f"<pre class='standings-message'>{escaped_content}</pre>")

    for embed in msg.embeds:
        embed_chunks = []

        title = getattr(embed, "title", None)
        description = getattr(embed, "description", None)

        if title:
            raw_parts.append(title)
            embed_chunks.append(
                f"<h3 class='standings-embed-title'>{html_module.escape(title)}</h3>"
            )

        if description:
            raw_parts.append(description)
            escaped_desc = html_module.escape(description).replace("\n", "<br>")
            embed_chunks.append(
                f"<div class='standings-embed-description'>{escaped_desc}</div>"
            )

        try:
            for field in embed.fields:
                field_name = html_module.escape(field.name or "")
                field_value = html_module.escape(field.value or "").replace("\n", "<br>")

                raw_parts.append(f"{field.name}\n{field.value}")

                embed_chunks.append(
                    "<div class='standings-embed-field'>"
                    f"<strong>{field_name}</strong><br>"
                    f"{field_value}"
                    "</div>"
                )
        except Exception:
            pass

        if embed_chunks:
            html_parts.append(
                "<div class='standings-embed'>"
                + "\n".join(embed_chunks)
                + "</div>"
            )

    html = "\n".join(html_parts).strip() if html_parts else None
    raw = "\n\n".join(raw_parts).strip()

    return html, raw


async def _update_standings_from_message(msg: discord.Message):
    """
    Updates the cached standings from a Discord message.
    """

    if msg is None:
        return

    if not msg.channel or getattr(msg.channel, "id", None) != STANDINGS_CHANNEL_ID:
        return

    html, raw = _discord_message_to_safe_html(msg)

    if not html and not raw:
        return

    try:
        author_name = None
        if msg.author:
            author_name = getattr(msg.author, "display_name", None) or getattr(msg.author, "name", None)

        if msg.edited_at:
            ts = msg.edited_at.isoformat()
        elif msg.created_at:
            ts = msg.created_at.isoformat()
        else:
            ts = datetime.utcnow().isoformat()

        async with _standings_lock:
            _standings_cache["html"] = html
            _standings_cache["raw"] = raw
            _standings_cache["ts"] = ts
            _standings_cache["message_id"] = msg.id
            _standings_cache["author"] = author_name

            await _save_standings_cache()

        print(f"Updated standings cache from message {msg.id}")

    except Exception:
        print("Failed to update standings cache:")
        traceback.print_exc()


async def _populate_initial_standings_cache():
    """
    Used on bot startup.
    If cache is empty, tries to load standings from:
    1. pinned message in standings channel
    2. latest message in standings channel
    """

    try:
        await _load_standings_cache()

        async with _standings_lock:
            has_cache = bool(_standings_cache.get("html") or _standings_cache.get("raw"))

        if has_cache:
            return

        guild = bot.get_guild(TEST_GUILD_ID)
        if guild is None:
            print("Could not populate standings cache: guild not found")
            return

        ch = guild.get_channel(STANDINGS_CHANNEL_ID)

        if not isinstance(ch, discord.TextChannel):
            print("Could not populate standings cache: standings channel not found or not a text channel")
            return

        msg = None

        try:
            pinned = await ch.pins()
            if pinned:
                # newest pinned message first
                pinned.sort(key=lambda m: m.created_at, reverse=True)
                msg = pinned[0]
        except Exception as e:
            print("Warning: failed to read pinned standings messages:", repr(e))

        if msg is None:
            try:
                async for m in ch.history(limit=1):
                    msg = m
                    break
            except Exception as e:
                print("Warning: failed to read standings channel history:", repr(e))

        if msg:
            await _update_standings_from_message(msg)

    except Exception:
        print("Failed to populate initial standings cache:")
        traceback.print_exc()



def add_team_to_list(role_id: int, name: str):
    data = load_teams()
    for entry in data:
        if str(entry.get("role_id")) == str(role_id):
            entry["name"] = name
            break
    else:
        data.append({"role_id": role_id, "name": name})
    try:
        with TEAMS_FILE.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        return

    # Trigger an immediate server stats refresh (best-effort)
    try:
        import asyncio
        if "bot" in globals() and hasattr(bot, "get_cog"):
            cog = bot.get_cog("ServerStatsCog")
            if cog and hasattr(cog, "update_now"):
                asyncio.create_task(cog.update_now())
    except Exception:
        pass



def load_player_history() -> dict:
    if not PLAYER_HISTORY_FILE.is_file():
        return {}
    try:
        with PLAYER_HISTORY_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}

INTENTS = discord.Intents.default()
INTENTS.guilds = True
INTENTS.members = True
INTENTS.messages = True
INTENTS.message_content = True
INTENTS.presences = True



# -------- scan-teams command (plain app command) --------
@app_commands.command(name="scan-teams", description="Admin: register existing team roles into teams.json")
@app_commands.default_permissions(administrator=True)
async def scan_teams(interaction: discord.Interaction):
    guild = interaction.guild
    if guild is None:
        await interaction.response.send_message("Use this in a server.", ephemeral=True)
        return

    team_roles = []
    for role in guild.roles:
        if role.is_default() or role.managed:
            continue
        if role.id in {
            HEAD_REF_ROLE_ID, REF_ROLE_ID,
            HEAD_CASTER_ROLE_ID, CASTER_ROLE_ID,
            CAPTAIN_ROLE_ID, CO_CAPTAIN_ROLE_ID,
            TEAM_PLAYER_ROLE_ID, TEAM_EXEC_ROLE_ID,
            BOARD_OF_DIRECTORS_ROLE_ID, COMMUNITY_MANAGER_ROLE_ID,
            SUPERVISOR_ROLE_ID, DEVELOPMENT_TEAM_ROLE_ID,
        }:
            continue
        # simple rule: name contains "team" (adjust as needed)
        if "team" in role.name.lower():
            team_roles.append(role)

    if not team_roles:
        await interaction.response.send_message("No candidate team roles found by scan.", ephemeral=True)
        return

    existing = []
    if TEAMS_FILE.is_file():
        try:
            existing = json.loads(TEAMS_FILE.read_text("utf-8"))
        except Exception:
            existing = []
    if not isinstance(existing, list):
        existing = []

    for r in team_roles:
        if not any(str(e.get("role_id")) == str(r.id) for e in existing):
            existing.append({"role_id": r.id, "name": r.name})

    try:
        TEAMS_FILE.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    except Exception as e:
        await interaction.response.send_message(f"Failed to write teams.json: `{e}`", ephemeral=True)
        return

    await interaction.response.send_message(
        f"Registered {len(team_roles)} team role(s) into teams.json.",
        ephemeral=True,
    )


# ---------------- HELPERS ----------------
def has_role_id(member: discord.Member, role_id: int | None) -> bool:
    return bool(role_id and any(r.id == role_id for r in member.roles))

def is_team_role(guild: discord.Guild, role: discord.Role) -> bool:
    protected = {
        CAPTAIN_ROLE_ID, CO_CAPTAIN_ROLE_ID, TEAM_PLAYER_ROLE_ID, TEAM_EXEC_ROLE_ID,
        HEAD_REF_ROLE_ID, REF_ROLE_ID, HEAD_CASTER_ROLE_ID, CASTER_ROLE_ID,
    }
    if role.is_default() or role.managed or role.id in protected:
        return False

    team_player = guild.get_role(TEAM_PLAYER_ROLE_ID)

    # Prefer roles where members also have TEAM_PLAYER_ROLE, if such members exist
    if team_player is not None:
        has_pair = False
        for m in guild.members:
            if m.bot:
                continue
            if role in m.roles and team_player in m.roles:
                has_pair = True
                break
        if has_pair:
            return True
        # if no members have both, fall through to generic check below

    # Generic fallback: any non‑protected role assigned to at least one non‑bot member
    for m in guild.members:
        if m.bot:
            continue
        if role in m.roles:
            return True

    return False

def get_user_team_role(member: discord.Member) -> discord.Role | None:
    """Return the team role for this member based on teams.json,
    falling back to scanning their roles with is_team_role()."""

    guild = member.guild

    # --- 1) try teams.json (current behavior) ---
    try:
        teams = load_teams()
    except Exception:
        teams = []

    team_roles: list[discord.Role] = []
    for entry in teams:
        rid = entry.get("role_id")
        if not rid:
            continue
        try:
            rid_int = int(rid)
        except (TypeError, ValueError):
            continue
        r = guild.get_role(rid_int)
        if r and r in member.roles:
            team_roles.append(r)

    if len(team_roles) == 1:
        return team_roles[0]

    # --- 2) fallback: infer from member.roles using is_team_role ---
    inferred: list[discord.Role] = []
    for r in member.roles:
        if is_team_role(guild, r):
            inferred.append(r)

    return inferred[0] if len(inferred) == 1 else None






def find_single_team_for_member(guild: discord.Guild, member: discord.Member) -> Optional[discord.Role]:
    # wrapper kept for compatibility
    return get_user_team_role(member)

async def get_team_data(team_role: discord.Role, guild: discord.Guild):
    members = [m for m in guild.members if team_role in m.roles and not m.bot]
    captain = None
    co_captains = []
    executives = []
    players = []

    for m in members:
        if has_role_id(m, CAPTAIN_ROLE_ID):
            if not captain:
                captain = m
                continue
        if has_role_id(m, CO_CAPTAIN_ROLE_ID):
            co_captains.append(m)
            continue
        if has_role_id(m, TEAM_EXEC_ROLE_ID):
            executives.append(m)
            continue
        players.append(m)

    # -------- PENDING INVITES --------
    invites_raw = load_invites()
    team_invites_ids = invites_raw.get(str(team_role.id), []) or []
    pending_mentions: list[str] = []

    for uid in list(team_invites_ids):
        user = guild.get_member(uid) or guild.get_user(uid)
        # auto-clean: if user is already on any team, drop from pending
        if isinstance(user, discord.Member) and get_user_team_role(user) is not None:
            remove_pending_invite(team_role.id, uid)
            continue
        if user:
            pending_mentions.append(user.mention)
        else:
            # user not found -> clean it out
            remove_pending_invite(team_role.id, uid)

    # Keep old 'executive' key for backwards compatibility (first exec or "None set")
    executive_single = executives[0].mention if executives else "None set"

    return {
        "name": team_role.name,
        "executive": executive_single,              # old single field
        "executives": executives,                   # NEW: list[Member]
        "captain": captain.mention if captain else "None",
        "co_captains": [m for m in co_captains],    # list[Member]
        "players": players,
        "pending_invites": pending_mentions,
    }

SELECTED_MEMBER_CACHE: dict[tuple[int, int], int] = {}

# ---------------- Settings summary view ----------------
class MainSettingsView(discord.ui.View):
    def __init__(self, timeout: Optional[float] = 600):
        super().__init__(timeout=timeout)
        options = [
            discord.SelectOption(label="Channels", description="Configure channel IDs via config.json.", value="channels"),
            discord.SelectOption(label="Roles", description="Configure role IDs via config.json.", value="roles"),
            discord.SelectOption(label="Roster Rules", description="View/update roster limits.", value="roster"),
        ]
        self.select = discord.ui.Select(placeholder="Choose settings section", min_values=1, max_values=1, options=options)
        self.select.callback = self._on_main_select
        self.add_item(self.select)

    async def _on_main_select(self, interaction: discord.Interaction):
        choice = interaction.data["values"][0]
        if choice == "channels":
            await self._show_channels(interaction)
        elif choice == "roles":
            await self._show_roles(interaction)
        elif choice == "roster":
            await self._show_roster(interaction)

    def _resolve_channel_id(self, key: str, fallback_name: Optional[str]) -> Optional[int]:
        # CONFIG -> DEFAULT_CONFIG -> module global
        val = None
        try:
            val = CONFIG.get("channels", {}).get(key)
        except Exception:
            val = None
        if val is None:
            val = DEFAULT_CONFIG.get("channels", {}).get(key)
        if val is None and fallback_name:
            val = globals().get(fallback_name)
        try:
            return int(val) if val is not None else None
        except Exception:
            return None

    def _resolve_role_id(self, key: str, fallback_name: Optional[str]) -> Optional[int]:
        val = None
        try:
            val = CONFIG.get("roles", {}).get(key)
        except Exception:
            val = None
        if val is None:
            val = DEFAULT_CONFIG.get("roles", {}).get(key)
        if val is None and fallback_name:
            val = globals().get(fallback_name)
        try:
            return int(val) if val is not None else None
        except Exception:
            return None

    # ---------------- Channels ----------------
    async def _show_channels(self, interaction: discord.Interaction):
        guild = interaction.guild
        def chan_text(key, fallback):
            cid = self._resolve_channel_id(key, fallback)
            return f"<#{cid}>" if cid else "Not set"

        embed = discord.Embed(
            title="📺  Channel Settings",
            description=(
                "Pick a channel from the dropdown below.\n\n"
                "The bot will then ask you to go to that channel and send a message mentioning me (e.g. `@Bot`). "
                "I will read which channel the confirmation came from and save it.\n\n"
                "For Match Category, go to any channel inside the category you want."
            ),
            color=discord.Color.light_grey(),
        )

        embed.add_field(name="Transactions", value=chan_text("transactions", "TRANSACTIONS_CHANNEL_ID"), inline=True)
        embed.add_field(name="FAQ", value=chan_text("faq", None), inline=True)
        embed.add_field(name="Match Score", value=chan_text("submit_score", "MATCH_SCORE_CHANNEL_ID"), inline=True)
        embed.add_field(name="Match Time", value=chan_text("submit_time", "MATCH_TIMES_CHANNEL_ID"), inline=True)
        embed.add_field(name="Scheduling", value=chan_text("scheduling", None), inline=True)
        embed.add_field(name="Assignments", value=chan_text("assignments", "ASSIGNMENTS_CHANNEL_ID"), inline=True)
        embed.add_field(name="Force-time staff only announcement", value=chan_text("force_time_review", "FORCE_TIME_REVIEW_CHANNEL_ID"), inline=True)

        options = [
            discord.SelectOption(label="Transactions", value="transactions"),
            discord.SelectOption(label="FAQ", value="faq"),
            discord.SelectOption(label="Match Score", value="submit_score"),
            discord.SelectOption(label="Match Time", value="submit_time"),
            discord.SelectOption(label="Scheduling", value="scheduling"),
            discord.SelectOption(label="Assignments", value="assignments"),
            discord.SelectOption(label="Force-time staff only announcement", value="force_time_review"),
        ]
        sel = discord.ui.Select(placeholder="Select which channel setting to update", min_values=1, max_values=1, options=options)

        async def sel_cb(sel_int: discord.Interaction):
            key = sel_int.data["values"][0]
            await sel_int.response.send_message(
                f"Go to the channel you want to assign to **{key}** and send a message mentioning me (e.g. `@Bot`). I will read the channel where you post the mention and save it.",
                ephemeral=True,
            )

            def check(m: discord.Message):
                return (
                    m.author.id == sel_int.user.id
                    and m.guild is not None
                    and m.channel.type == discord.ChannelType.text
                    and any(u.id == sel_int.client.user.id for u in m.mentions)
                )

            try:
                msg = await sel_int.client.wait_for("message", timeout=120.0, check=check)
            except asyncio.TimeoutError:
                try:
                    await sel_int.followup.send("Timed out waiting for confirmation message. Try again.", ephemeral=True)
                except Exception:
                    pass
                return

            channel_obj = msg.channel
            CONFIG.setdefault("channels", {})[key] = channel_obj.id
            save_config(CONFIG)
            if key == "force_time_review":
                globals()["FORCE_TIME_REVIEW_CHANNEL_ID"] = channel_obj.id
            try:
                await sel_int.followup.send(f"Saved channel <#{channel_obj.id}> for `{key}`.", ephemeral=True)
            except Exception:
                pass

        sel.callback = sel_cb
        view = discord.ui.View(timeout=120)
        view.add_item(sel)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    # ---------------- Roles ----------------
    async def _show_roles(self, interaction: discord.Interaction):
        guild = interaction.guild
        def role_text(key, fallback):
            rid = self._resolve_role_id(key, fallback)
            return f"<@&{rid}>" if rid else "Not set"

        embed = discord.Embed(
            title="🎭  Role Settings",
            description=(
                "Pick a role from the dropdown below.\n\n"
                "The bot will then ask you to select/mention the role. Mentioning just the bot with no role will clear that setting."
            ),
            color=discord.Color.blue(),
        )

        embed.add_field(name="Captain", value=role_text("captain", "CAPTAIN_ROLE_ID"), inline=True)
        embed.add_field(name="Co-Captain", value=role_text("co_captain", "CO_CAPTAIN_ROLE_ID"), inline=True)
        embed.add_field(name="Executive", value=role_text("executive", "TEAM_EXEC_ROLE_ID"), inline=True)
        embed.add_field(name="Team Member", value=role_text("team_member", "TEAM_PLAYER_ROLE_ID"), inline=True)
        embed.add_field(name="Caster", value=role_text("caster", "CASTER_ROLE_ID"), inline=True)
        embed.add_field(name="Referee", value=role_text("referee", "REF_ROLE_ID"), inline=True)

        options = [
            discord.SelectOption(label="Captain", value="captain"),
            discord.SelectOption(label="Co-Captain", value="co_captain"),
            discord.SelectOption(label="Executive", value="executive"),
            discord.SelectOption(label="Team Member", value="team_member"),
            discord.SelectOption(label="Caster", value="caster"),
            discord.SelectOption(label="Referee", value="referee"),
        ]
        sel = discord.ui.Select(placeholder="Select which role setting to update", min_values=1, max_values=1, options=options)

        async def sel_cb(sel_int: discord.Interaction):
            key = sel_int.data["values"][0]

            class RoleChooseView(discord.ui.View):
                def __init__(self, parent_key: str):
                    super().__init__(timeout=120)
                    self.parent_key = parent_key
                    self.role_select = discord.ui.RoleSelect(placeholder="Pick a role (or cancel to keep current)", min_values=1, max_values=1)
                    self.role_select.callback = self.role_cb
                    self.add_item(self.role_select)

                async def role_cb(self, rs_int: discord.Interaction):
                    try:
                        rid = int(rs_int.data["values"][0])
                        role_obj = rs_int.guild.get_role(rid)
                    except Exception:
                        role_obj = None

                    if role_obj is None:
                        await rs_int.response.send_message("Could not resolve selected role.", ephemeral=True)
                        return

                    CONFIG.setdefault("roles", {})[self.parent_key] = role_obj.id
                    save_config(CONFIG)
                    await rs_int.response.send_message(f"Saved role {role_obj.mention} for `{self.parent_key}`.", ephemeral=True)
                    self.stop()

                @discord.ui.button(label="Clear", style=discord.ButtonStyle.danger)
                async def clear_btn(self, i: discord.Interaction, btn: discord.ui.Button):
                    CONFIG.setdefault("roles", {}).pop(self.parent_key, None)
                    save_config(CONFIG)
                    await i.response.send_message(f"Cleared `{self.parent_key}`.", ephemeral=True)
                    self.stop()

            view = RoleChooseView(parent_key=key)
            await sel_int.response.send_message(f"Select a role for `{key}` (or press Clear to remove it).", view=view, ephemeral=True)

        sel.callback = sel_cb
        v = discord.ui.View(timeout=120)
        v.add_item(sel)
        await interaction.response.send_message(embed=embed, view=v, ephemeral=True)

    # ---------------- Roster Rules ----------------
    async def _show_roster(self, interaction: discord.Interaction):
        rr = CONFIG.get("roster_rules", {}) or DEFAULT_CONFIG.get("roster_rules", {})
        embed = discord.Embed(title="👥  Roster Rules", description="Click a button to update the limit via a short modal.", color=discord.Color.red())
        embed.add_field(name="Max Roster Size", value=str(rr.get("max_roster", 12)), inline=True)
        embed.add_field(name="Max Co-Captains", value=str(rr.get("max_co_captains", 2)), inline=True)
        embed.add_field(name="Max Team Executives", value=str(rr.get("max_executive", 1)), inline=True)

        class NumModal(discord.ui.Modal):
            def __init__(self, title: str, prompt: str, key: str):
                super().__init__(title=title)
                self.prompt_field = discord.ui.TextInput(label=prompt, placeholder="Enter an integer", required=True, max_length=4)
                self.add_item(self.prompt_field)
                self.key = key

            async def on_submit(self, modal_inter: discord.Interaction):
                val_raw = self.prompt_field.value.strip()
                try:
                    val = int(val_raw)
                    if val < 0:
                        raise ValueError
                except Exception:
                    await modal_inter.response.send_message("Invalid integer. Please try again.", ephemeral=True)
                    return
                CONFIG.setdefault("roster_rules", {})[self.key] = val
                save_config(CONFIG)
                await modal_inter.response.send_message(f"Saved `{self.key}` = {val}.", ephemeral=True)

        view = discord.ui.View(timeout=120)

        @discord.ui.button(label="Max Roster Size", style=discord.ButtonStyle.primary)
        async def max_roster_btn(btn, i: discord.Interaction):
            await i.response.send_modal(NumModal(title="Set Max Roster Size", prompt="What is the new max for roster sizes:", key="max_roster"))

        @discord.ui.button(label="Max Co-Captains", style=discord.ButtonStyle.primary)
        async def max_co_btn(btn, i: discord.Interaction):
            await i.response.send_modal(NumModal(title="Set Max Co-Captains", prompt="What is the new Max for Co-captains:", key="max_co_captains"))

        @discord.ui.button(label="Max Team Executives", style=discord.ButtonStyle.primary)
        async def max_exec_btn(btn, i: discord.Interaction):
            await i.response.send_modal(NumModal(title="Set Max Team Executives", prompt="What it the new max for Team Executives:", key="max_executive"))

        view.add_item(max_roster_btn)
        view.add_item(max_co_btn)
        view.add_item(max_exec_btn)

        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)



class DisbandTeamModal(discord.ui.Modal, title="Disband Team"):
    team = discord.ui.TextInput(
        label="Team (mention/name/id)",
        required=True,
        max_length=100,
    )

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return

        # resolve team role (mention, id, or name) using your existing helper
        raw = self.team.value.strip()
        team_role, _, _ = resolve_team_any(guild, raw)
        if not isinstance(team_role, discord.Role):
            await interaction.response.send_message("Could not find that team role.", ephemeral=True)
            return

        # safety: don't ever disband protected roles
        protected = {
            CAPTAIN_ROLE_ID, CO_CAPTAIN_ROLE_ID, TEAM_PLAYER_ROLE_ID, TEAM_EXEC_ROLE_ID,
            HEAD_REF_ROLE_ID, REF_ROLE_ID, HEAD_CASTER_ROLE_ID, CASTER_ROLE_ID,
        }
        if team_role.id in protected or team_role.is_default() or team_role.managed:
            await interaction.response.send_message("That role cannot be disbanded.", ephemeral=True)
            return

        tx_ch = guild.get_channel(TRANSACTIONS_CHANNEL_ID)

        # Remove team role + global team roles from members
        removed_members = 0
        cap_role = guild.get_role(CAPTAIN_ROLE_ID)
        co_role = guild.get_role(CO_CAPTAIN_ROLE_ID)
        exec_role = guild.get_role(TEAM_EXEC_ROLE_ID)
        player_role = guild.get_role(TEAM_PLAYER_ROLE_ID)

        for m in list(guild.members):
            if m.bot:
                continue
            if team_role in m.roles:
                roles_to_remove = [team_role]
                for r in (cap_role, co_role, exec_role, player_role):
                    if r and r in m.roles:
                        roles_to_remove.append(r)
                try:
                    await m.remove_roles(*roles_to_remove, reason=f"Manual disband via /admin-panel by {interaction.user}")
                    removed_members += 1
                except Exception:
                    pass

        # delete the team role
        try:
            await team_role.delete(reason=f"Manual disband via /admin-panel by {interaction.user}")
        except Exception:
            pass

        # log to transactions
        if isinstance(tx_ch, discord.TextChannel):
            try:
                await tx_ch.send(f"# {team_role.name} HAS BEEN DISBANDED\n\n")
            except Exception:
                pass

        await interaction.response.send_message(
            f"Disbanded **{team_role.name}** and removed team/global roles from {removed_members} member(s).",
            ephemeral=True,
        )



# ---------------- Admin Panel Modals ----------------
class CreateTeamModal(discord.ui.Modal, title="Create Team"):
    team_name = discord.ui.TextInput(label="Team Name", required=True)
    captain = discord.ui.TextInput(label="Captain (mention or ID)", required=True)
    color = discord.ui.TextInput(label="Color code (hex, e.g. #ff0000)", required=True)
    pfp_url = discord.ui.TextInput(label="Team PFP URL (optional)", required=False)

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return

        # Defer early (we do role/emoji creation and HTTP)
        try:
            await interaction.response.defer(ephemeral=True, thinking=True)
        except Exception:
            pass

        tx = guild.get_channel(TRANSACTIONS_CHANNEL_ID)

        # Resolve captain
        raw = self.captain.value.strip()
        if raw.startswith("<@") and raw.endswith(">"):
            raw = raw.strip("<@!>")
        try:
            member = await guild.fetch_member(int(raw))
        except Exception:
            member = None
        if member is None:
            await interaction.followup.send("Could not find that captain.", ephemeral=True)
            return

        # Color
        c = self.color.value.strip()
        if not c.startswith("#"):
            c = "#" + c
        try:
            color_int = int(c[1:], 16)
        except Exception:
            await interaction.followup.send("Invalid color code.", ephemeral=True)
            return

        plain_team_name = self.team_name.value

        # Create role with plain name only
        try:
            role = await guild.create_role(
                name=plain_team_name,
                colour=discord.Colour(color_int),
                reason=f"Team created by {interaction.user}",
            )
        except Exception as e:
            print(f"[CreateTeamModal] Failed to create role: {e}")
            await interaction.followup.send("Failed to create role (missing perms?).", ephemeral=True)
            return

        # Move team role under Team Player role
        try:
            team_player_role = guild.get_role(TEAM_PLAYER_ROLE_ID)
            if team_player_role:
                target_pos = max(team_player_role.position - 1, 1)
                await role.edit(position=target_pos)
        except Exception as e:
            print(f"[CreateTeamModal] Failed to move role {role} under Team Player: {e}")

        # Register in teams.json with plain name
        add_team_to_list(role.id, plain_team_name)

        # Assign captain & team_player roles
        roles_to_add = [role]
        cap_role = guild.get_role(CAPTAIN_ROLE_ID)
        if cap_role:
            roles_to_add.append(cap_role)
        if team_player_role and team_player_role not in roles_to_add:
            roles_to_add.append(team_player_role)

        try:
            await member.add_roles(*roles_to_add, reason="New team created by admin")
        except Exception as e:
            print(f"[CreateTeamModal] Failed to assign roles to captain: {e}")
            await interaction.followup.send("Team created but failed to assign roles.", ephemeral=True)
            return

        # optional: process PFP URL -> emoji + role icon, BUT keep role name plain
        pfp = (self.pfp_url.value or "").strip()
        created_emoji = None
        if pfp:
            try:
                import aiohttp
                async with aiohttp.ClientSession() as sess:
                    async with sess.get(pfp, timeout=15) as resp:
                        if resp.status == 200:
                            data = await resp.read()

                            # Try to create a custom emoji
                            try:
                                safe_name = re.sub(r"[^0-9A-Za-z_]", "_", plain_team_name)[:32] or "teamimg"
                                created_emoji = await guild.create_custom_emoji(
                                    name=safe_name,
                                    image=data,
                                    reason="Team pfp uploaded",
                                )
                            except Exception as e:
                                print(f"[CreateTeamModal] Failed to create emoji: {e}")
                                created_emoji = None

                            # Try to set the role icon (if supported)
                            try:
                                await role.edit(reason=f"Set team icon by {interaction.user}", icon=data)
                            except Exception as e:
                                print(f"[CreateTeamModal] Failed to set role icon: {e}")
            except Exception as e:
                print(f"[CreateTeamModal] Failed PFP handling: {e}")
                created_emoji = None

        # Log and notify
        if tx:
            try:
                await tx.send(
                    f"# New Team Created!\n"
                    f"* Team Name: {role.mention}\n"
                    f"* Team Captain: {member.mention}"
                )
            except Exception:
                pass

        msg_parts = [f"Team {role.mention} created and {member.mention} set as captain."]
        if created_emoji:
            msg_parts.append(f"Created emoji: {created_emoji}")

        await interaction.followup.send("\n".join(msg_parts), ephemeral=True)


class AdminPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="roster lock all", style=discord.ButtonStyle.danger)
    async def roster_lock_all(self, interaction, button):
        global ROSTER_LOCKED
        guild = interaction.guild
        tx = guild.get_channel(TRANSACTIONS_CHANNEL_ID) if guild else None
        ROSTER_LOCKED = True
        if tx:
            try:
                await tx.send("# ROSTER LOCK HAS BEEN ENABLED FOR ALL TEAM!")
            except Exception:
                pass
        await interaction.response.send_message("Rosters locked for all teams.", ephemeral=True)

    @discord.ui.button(label="Disband team", style=discord.ButtonStyle.danger)
    async def disband_team_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # admins only
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You do not have permission to use this.", ephemeral=True)
            return

        await interaction.response.send_modal(DisbandTeamModal())


    @discord.ui.button(label="disband all", style=discord.ButtonStyle.danger)
    async def disband_all(self, interaction, button):
        """
        Disband ONLY teams that are registered in teams.json (load_teams).
        Leaves all other server roles alone.
        """
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        # 1) Load known team roles from teams.json
        teams_data = load_teams()
        team_role_ids: set[int] = set()
        for entry in teams_data:
            rid = entry.get("role_id")
            if not rid:
                continue
            try:
                team_role_ids.add(int(rid))
            except (TypeError, ValueError):
                continue

        if not team_role_ids:
            await interaction.followup.send("No teams found in teams.json; nothing to disband.", ephemeral=True)
            return

        # 2) Resolve actual Role objects for those IDs
        team_roles: list[discord.Role] = []
        for rid in team_role_ids:
            r = guild.get_role(rid)
            if r and not r.is_default() and not r.managed:
                team_roles.append(r)

        if not team_roles:
            await interaction.followup.send("No valid team roles found on this server.", ephemeral=True)
            return

        # 3) Prepare global roles to strip only from members who had a team role
        global_role_ids = {
            CAPTAIN_ROLE_ID,
            CO_CAPTAIN_ROLE_ID,
            TEAM_PLAYER_ROLE_ID,
            TEAM_EXEC_ROLE_ID,
        }
        global_roles = {rid: guild.get_role(rid) for rid in global_role_ids if rid}

        # 4) For each member, if they have ANY team role -> remove team + global roles
        for member in guild.members:
            if member.bot:
                continue
            member_team_roles = [r for r in member.roles if r.id in team_role_ids]
            if not member_team_roles:
                continue

            roles_to_remove = list(member_team_roles)
            for r in global_roles.values():
                if r and r in member.roles:
                    roles_to_remove.append(r)

            if roles_to_remove:
                try:
                    await member.remove_roles(
                        *roles_to_remove,
                        reason=f"Disband-all teams by {interaction.user}",
                    )
                except Exception:
                    pass  # best-effort

        # 5) Delete ONLY the team roles, leave all other roles intact
        deleted_count = 0
        for r in team_roles:
            try:
                await r.delete(reason=f"Disband-all teams by {interaction.user}")
                deleted_count += 1
            except Exception:
                pass  # best-effort

        # 6) Optional: clean teams.json (remove teams whose roles no longer exist)
        cleaned: list[dict] = []
        for entry in teams_data:
            rid = entry.get("role_id")
            if not rid:
                continue
            try:
                rid_int = int(rid)
            except (TypeError, ValueError):
                continue
            # keep only teams whose role still exists
            if guild.get_role(rid_int) is not None:
                cleaned.append(entry)
        try:
            with TEAMS_FILE.open("w", encoding="utf-8") as f:
                json.dump(cleaned, f, indent=2)
        except Exception:
            pass

        # 7) Log to transactions and reply
        tx = guild.get_channel(TRANSACTIONS_CHANNEL_ID)
        if isinstance(tx, discord.TextChannel):
            try:
                await tx.send("# ALL REGISTERED TEAMS HAVE BEEN DISBANDED")
            except Exception:
                pass

        await interaction.followup.send(
            f"Disbanded {deleted_count} team roles and stripped their members' team/global roles.",
            ephemeral=True,
        )

    @discord.ui.button(label="add scrim", style=discord.ButtonStyle.primary)
    async def add_scrim(self, interaction, button):
        await interaction.response.send_modal(AddScrimModal())

    @discord.ui.button(label="submit score", style=discord.ButtonStyle.success)
    async def submit_score(self, interaction, button):
        global SEEDING_OPEN
        if SEEDING_OPEN:
            await interaction.response.send_modal(SubmitScoreModalSeeding())
        else:
            await interaction.response.send_modal(SubmitScoreModalNoSeeding())

    @discord.ui.button(label="submit time", style=discord.ButtonStyle.secondary)
    async def submit_time(self, interaction, button):
        await interaction.response.send_modal(SubmitTimeModal())

    @discord.ui.button(label="create team", style=discord.ButtonStyle.primary)
    async def create_team(self, interaction, button):
        await interaction.response.send_modal(CreateTeamModal())

    @discord.ui.button(label="Admin Add", style=discord.ButtonStyle.success)
    async def admin_add(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AdminAddModal())

    @discord.ui.button(label="Admin Kick", style=discord.ButtonStyle.danger)
    async def admin_kick(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AdminKickModal())

    @discord.ui.button(label="unlock roster all", style=discord.ButtonStyle.success)
    async def unlock_roster_all(self, interaction: discord.Interaction, button: discord.ui.Button):
        global ROSTER_LOCKED
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return

        ROSTER_LOCKED = False
        tx = guild.get_channel(TRANSACTIONS_CHANNEL_ID)
        if isinstance(tx, discord.TextChannel):
            try:
                await tx.send("# ALL ROSTERS HAVE BEEN UNLOCKED BY AN ADMIN")
            except Exception:
                pass

        await interaction.response.send_message("All rosters unlocked.", ephemeral=True)


class AdminPanel(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.guilds(Object(id=TEST_GUILD_ID))
    @app_commands.default_permissions(administrator=True)
    @app_commands.command(name="admin-panel", description="Open the admin panel.")
    async def admin_panel(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You do not have permission.", ephemeral=True)
            return
        await interaction.response.send_message("Admin Panel:", view=AdminPanelView(), ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.author.bot:
            return
        if message.channel.id != TRANSACTIONS_CHANNEL_ID:
            return
        content = message.content.strip()
        if not content.lower().startswith("/create-team"):
            return
        guild = message.guild
        if guild is None:
            return
        parts = content.split()
        if len(parts) < 4:
            return
        raw_color = parts[-1]
        raw_capt = parts[-2]
        name = " ".join(parts[1:-2])
        if raw_capt.startswith("<@") and raw_capt.endswith(">"):
            raw_capt = raw_capt.strip("<@!>")
        try:
            capt = await guild.fetch_member(int(raw_capt))
        except Exception:
            capt = None
        if capt is None:
            return
        c = raw_color
        if not c.startswith("#"):
            c = "#" + c
        try:
            color_int = int(c[1:], 16)
        except Exception:
            return
        try:
            role = await guild.create_role(
                name=name,
                colour=discord.Colour(color_int),
                reason="Team created by apply-bot command"
            )
        except Exception as e:
            print(f"[AdminPanel] Failed to create team role via /create-team: {e}")
            return

        # move team role under Team Player role in the role list
        try:
            team_player_role = guild.get_role(TEAM_PLAYER_ROLE_ID)
            if team_player_role:
                target_pos = max(team_player_role.position - 1, 1)
                await role.edit(position=target_pos)
        except Exception as e:
            print(f"[AdminPanel] Failed to move role {role} under Team Player: {e}")

        # register team in teams.json
        add_team_to_list(role.id, role.name)

        roles = [role]
        cap_role = guild.get_role(CAPTAIN_ROLE_ID)
        if cap_role:
            roles.append(cap_role)
        try:
            await capt.add_roles(*roles, reason="New team created via /create-team")
        except Exception as e:
            print(f"[AdminPanel] Failed to assign roles to captain via /create-team: {e}")
        tx = guild.get_channel(TRANSACTIONS_CHANNEL_ID)
        if tx:
            try:
                await tx.send(f"# New Team Created!\n* Team Name: {role.mention}\n* Team Captain: {capt.mention}")
            except Exception:
                pass



class SubmitScoreModalSeeding(discord.ui.Modal, title="Submit Score"):
    winner = discord.ui.TextInput(label="Winner (team name)", required=True)
    loser = discord.ui.TextInput(label="Loser (team name)", required=True)
    score = discord.ui.TextInput(label="Score (e.g. 3-1)", required=True)
    stage = discord.ui.TextInput(
        label="Stage (Regular / Semifinals / Finals)",
        required=False,
        placeholder="Regular",
        max_length=20,
    )
    timecap_winner = discord.ui.TextInput(
        label="Who got timecapped? (team name or 'None')",
        required=False,
        placeholder="None",
        max_length=100,
    )

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        ch = guild.get_channel(MATCH_SCORE_CHANNEL_ID) if guild else None
        if not isinstance(ch, discord.TextChannel):
            await interaction.response.send_message("Match score channel not configured.", ephemeral=True)
            return

        winner = self.winner.value.strip()
        loser = self.loser.value.strip()
        score = self.score.value.strip()

        stage_raw = (self.stage.value or "Regular").strip().lower()
        if "final" in stage_raw:
            header = "# FINALS"
        elif "semi" in stage_raw:
            header = "# SEMIFINALS"
        else:
            header = None

        tc_raw = (self.timecap_winner.value or "").strip()
        if tc_raw and tc_raw.lower() != "none":
            timecap_line = f"> Timecap: {tc_raw}\n"
        else:
            timecap_line = "> Timecap: None\n"

        if header:
            base = f"{header}\n{winner} vs {loser}\n"
        else:
            base = f"{winner} vs {loser}\n"

        msg = (
            f"{base}"
            f"> Winner: {winner}\n"
            f"> Score: {score}\n"
            f"{timecap_line}"
            f"> Loser: {loser}"
        )

        await ch.send(msg)
        await interaction.response.send_message("Score submitted.", ephemeral=True)



class SubmitScoreModalNoSeeding(discord.ui.Modal, title="Submit Score"):
    winner = discord.ui.TextInput(label="Winner (team name)", required=True)
    loser = discord.ui.TextInput(label="Loser (team name)", required=True)
    score = discord.ui.TextInput(label="Score (e.g. 3-1)", required=True)
    stage = discord.ui.TextInput(
        label="Stage (Regular / Semifinals / Finals)",
        required=False,
        placeholder="Regular",
        max_length=20,
    )

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        ch = guild.get_channel(MATCH_SCORE_CHANNEL_ID) if guild else None
        if not isinstance(ch, discord.TextChannel):
            await interaction.response.send_message("Match score channel not configured.", ephemeral=True)
            return

        winner = self.winner.value.strip()
        loser = self.loser.value.strip()
        score = self.score.value.strip()

        stage_raw = (self.stage.value or "Regular").strip().lower()
        if "final" in stage_raw:
            header = "# FINALS"
        elif "semi" in stage_raw:
            header = "# SEMIFINALS"
        else:
            header = None

        if header:
            base = f"{header}\n{winner} vs {loser}\n"
        else:
            base = f"{winner} vs {loser}\n"

        msg = (
            f"{base}"
            f"> Winner: {winner}\n"
            f"> Score: {score}\n"
            f"> Loser: {loser}"
        )

        await ch.send(msg)
        await interaction.response.send_message("Score submitted.", ephemeral=True)



class AddScrimModal(discord.ui.Modal, title="Add Scrim"):
    team1 = discord.ui.TextInput(label="Team 1", required=True)
    team2 = discord.ui.TextInput(label="Team 2", required=True)
    lower_bracket = discord.ui.TextInput(label="Lower bracket? (true/false)", required=True)

    def _resolve_team(self, guild: discord.Guild, raw: str) -> tuple[Optional[discord.Role], str, str]:
        """
        Return (role_obj or None, mention_or_name, display_name)
        Based on mention, ID, or role name.
        """
        text = raw.strip()

        # Mention: <@&123>
        if text.startswith("<@&") and text.endswith(">"):
            try:
                rid = int(text.strip("<@&>"))
                r = guild.get_role(rid)
                if r:
                    return r, r.mention, r.name
            except Exception:
                pass

        # Raw ID
        try:
            rid = int(text)
            r = guild.get_role(rid)
            if r:
                return r, r.mention, r.name
        except Exception:
            pass

        # Name
        r = discord.utils.get(guild.roles, name=text) or discord.utils.find(
            lambda rr: rr.name.lower() == text.lower(), guild.roles
        )
        if r:
            return r, r.mention, r.name

        # Fallback: no role found, just return text
        return None, text, text

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return

        cat = guild.get_channel(SCRIM_CATEGORY_ID)
        if not isinstance(cat, discord.CategoryChannel):
            await interaction.response.send_message("Scrim category is not configured.", ephemeral=True)
            return

        t1_role, t1m, t1n = self._resolve_team(guild, self.team1.value)
        t2_role, t2m, t2n = self._resolve_team(guild, self.team2.value)
        is_lb = self.lower_bracket.value.strip().lower() in ("true", "yes", "y", "1")

        raw_name = f"{t1n} vs {t2n}"
        chan_name = re.sub(r"[^a-zA-Z0-9 _-]", "", raw_name).strip().replace(" ", "-").lower()[:90]
        channel_topic = f"{t1n} Vs {t2n}"

        # Build permission overwrites:
        overwrites: dict[discord.abc.Snowflake, discord.PermissionOverwrite] = {}

        # Hide from everyone
        overwrites[guild.default_role] = discord.PermissionOverwrite(view_channel=False)

        # Allow only both team roles (if they exist)
        if t1_role:
            overwrites[t1_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)
        if t2_role and t2_role != t1_role:
            overwrites[t2_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

        # NOTE: we intentionally do NOT add overwrites for refs/casters here.
        # Admins still see the channel via their Administrator permission.

        ch = await guild.create_text_channel(
            name=chan_name,
            category=cat,
            overwrites=overwrites,
            topic=channel_topic,
            reason=f"Scrim between {t1n} and {t2n}"
        )

        if is_lb:
            msg = (
                f"{t1m} vs {t2m}\n\n"
                f"> # Welcome to Losers Bracket.\n\n"
                f"> Your last chance to make it back to the regular bracket. If you lose you will be disbanded, however if you win you will be put back in the regular bracket!\n\n"
                f"> Reminder you have 3 days to schedule and 4 days to play."
            )
        else:
            msg = (
                f"{t1m} vs {t2m}\n\n"
                f"# Welcome to PGL Bracket\n"
                f"> 🗓️ You guys will have 3 day to schedule\n"
                f"> ⚔️ And 4 days to play\n"
                f"> Ping a staff member when you're ready to schedule or have any questions!\n"
                f"> Do `/forfeit` if you are unable to play your match"
            )

        await ch.send(msg)
        await interaction.response.send_message(f"Scrim channel created: {ch.mention}", ephemeral=True)


class AdminAddModal(discord.ui.Modal, title="Admin Add Player"):
    username = discord.ui.TextInput(label="What username is it? (mention or ID)", required=True)
    team = discord.ui.TextInput(label="What team? (mention/name/id)", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return

        raw_user = self.username.value.strip()
        if raw_user.startswith("<@") and raw_user.endswith(">"):
            raw_user = raw_user.strip("<@!>")
        member = None
        try:
            member = await guild.fetch_member(int(raw_user))
        except Exception:
            pass
        if member is None:
            await interaction.response.send_message("Could not find that user.", ephemeral=True)
            return

        raw_team = self.team.value.strip()
        team_role = None
        if raw_team.startswith("<@&") and raw_team.endswith(">"):
            try:
                rid = int(raw_team.strip("<@&>"))
                team_role = guild.get_role(rid)
            except Exception:
                pass
        if team_role is None:
            try:
                rid = int(raw_team)
                team_role = guild.get_role(rid)
            except Exception:
                pass
        if team_role is None:
            team_role = discord.utils.get(guild.roles, name=raw_team) or discord.utils.find(
                lambda r: r.name.lower() == raw_team.lower(), guild.roles
            )

        if team_role is None:
            await interaction.response.send_message("Could not find that team role.", ephemeral=True)
            return

        team_player_role = guild.get_role(TEAM_PLAYER_ROLE_ID)
        roles_to_add = [team_role]
        if team_player_role:
            roles_to_add.append(team_player_role)

        try:
            await member.add_roles(*roles_to_add, reason=f"Admin add by {interaction.user}")
        except Exception:
            await interaction.response.send_message("Failed to add roles (missing perms?).", ephemeral=True)
            return

        tx = guild.get_channel(TRANSACTIONS_CHANNEL_ID)
        if isinstance(tx, discord.TextChannel):
            await tx.send(f"{member.mention} Has Been added to **{team_role.name}** by an admin")

        await interaction.response.send_message(
            f"{member.mention} added to {team_role.mention}.",
            ephemeral=True,
        )




class AutoCodeCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.state = load_codes_state()  # {str(message_id): {"code": "PGL1234", "time": "..."}}
        self.check_matches.start()

    def cog_unload(self):
        self.check_matches.cancel()

    def _parse_match_message(self, msg: discord.Message):
        """
        Parse a MATCH_TIMES message.

        Regular:
            Team1 vs Team2
            > WEEK: X
            > Time: 6/25/26 at 8PM EST
            > Referee: <@id>
            > Caster: <@id>

        Finals/Semis:
            # FINALS / # SEMIFINALS
            > Teams: Team1 vs Team2
            > Time: 6/25/26 at 8PM EST
            > Referee: <@id>
            > Caster: <@id>
        """
        content = msg.content or ""
        lines = [ln.strip() for ln in content.splitlines() if ln.strip()]
        if not lines:
            return None

        team1_name = None
        team2_name = None
        time_str = None
        caster_mention = None
        ref_mention = None

        header = lines[0].lower()
        special = header.startswith("# finals") or header.startswith("# semifinals")

        if special:
            # FINALS / SEMIFINALS format
            for ln in lines:
                ln_clean = ln.lstrip("> ").strip()
                lower = ln_clean.lower()
                if lower.startswith("teams:"):
                    vs_part = ln_clean.split(":", 1)[1].strip()
                    if " vs " in vs_part:
                        t1, t2 = vs_part.split(" vs ", 1)
                        team1_name = t1.strip()
                        team2_name = t2.strip()
                elif lower.startswith("time:"):
                    time_str = ln_clean.split(":", 1)[1].strip()
                elif lower.startswith("referee:"):
                    ref_mention = ln_clean.split(":", 1)[1].strip()
                elif lower.startswith("caster:"):
                    caster_mention = ln_clean.split(":", 1)[1].strip()
        else:
            # Regular format
            vs_line = lines[0]
            if " vs " in vs_line:
                t1, t2 = vs_line.split(" vs ", 1)
                team1_name = t1.strip()
                team2_name = t2.strip()
            for ln in lines[1:]:
                ln_clean = ln.lstrip("> ").strip()
                lower = ln_clean.lower()
                if lower.startswith("time:"):
                    time_str = ln_clean.split(":", 1)[1].strip()
                elif lower.startswith("referee:"):
                    ref_mention = ln_clean.split(":", 1)[1].strip()
                elif lower.startswith("caster:"):
                    caster_mention = ln_clean.split(":", 1)[1].strip()

        if not (team1_name and team2_name and time_str):
            return None

        return {
            "team1": team1_name,
            "team2": team2_name,
            "time_str": time_str,
            "caster_mention": caster_mention,
            "ref_mention": ref_mention,
        }

    def _parse_time_to_local(self, time_str: str) -> Optional[datetime]:
        """
        Parse strings like:
          '6/25/26 at 8PM EST'
          '6/25 at 8PM EST'
          '6/25/26 at 8:10PM EST'
          '6/25 at 8:10PM EST'
        into a naive datetime in *server local time* (CST),
        assuming the string is written in EST.
        """
        if not time_str:
            return None

        s = time_str.strip()
        if " at " not in s:
            return None

        date_part, time_part = s.split(" at ", 1)
        date_part = date_part.strip()
        time_part = time_part.strip()

        # Strip timezone words
        for tz_word in ("EST", "EDT", "est", "edt"):
            time_part = time_part.replace(tz_word, "")
        time_part = time_part.strip()

        # Handle missing year
        parts = date_part.split("/")
        if len(parts) == 2:
            # m/d -> add current year
            m, d = parts
            try:
                year_now = datetime.now().year
                date_part_full = f"{int(m)}/{int(d)}/{year_now}"
            except Exception:
                return None
        else:
            # assume m/d/yy or m/d/yyyy
            date_part_full = date_part

        # Try formats with and without minutes, and 2‑digit vs 4‑digit year
        fmts = [
            "%m/%d/%y %I%p",      # 6/25/26 8PM
            "%m/%d/%Y %I%p",      # 6/25/2026 8PM
            "%m/%d/%y %I:%M%p",   # 6/25/26 8:10PM
            "%m/%d/%Y %I:%M%p",   # 6/25/2026 8:10PM
        ]

        dt_est = None
        for fmt in fmts:
            try:
                dt_est = datetime.strptime(f"{date_part_full} {time_part}", fmt)
                break
            except Exception:
                continue

        if dt_est is None:
            return None

        # You type EST, but server is CST (UTC‑6). Convert EST->CST by subtracting 1 hour.
        dt_cst = dt_est - timedelta(hours=1)
        return dt_cst



    def _compute_ff_string_from_time_str(self, time_str: str) -> str:
        """
        Take the original 'Time: ...' value (e.g. '6/18/26 at 10:40PM EST')
        and return a display string like '10:55PM EST' (15 minutes later),
        WITHOUT using the server's timezone.

        This only looks at the clock time in the string.
        """
        if not time_str or " at " not in time_str:
            return "Unknown"

        _, time_part = time_str.split(" at ", 1)
        time_part = time_part.strip()

        # Strip timezone words but remember we will display EST
        for tz_word in ("EST", "EDT", "est", "edt"):
            time_part = time_part.replace(tz_word, "")
        time_part = time_part.strip()

        # Try to parse time only as 12‑hour clock, with and without minutes
        fmts = ["%I%p", "%I:%M%p"]
        dt = None
        for fmt in fmts:
            try:
                dt = datetime.strptime(time_part, fmt)
                break
            except Exception:
                continue

        if dt is None:
            return "Unknown"

        # Add 15 minutes for FF time (as per your example)
        dt_ff = dt + timedelta(minutes=15)
        ff_str = dt_ff.strftime("%I:%M%p").lstrip("0")
        return ff_str + " EST"


    def _resolve_member_from_mention(self, guild: discord.Guild, mention: str) -> Optional[discord.Member]:
        if not mention:
            return None
        mention = mention.strip()
        if mention.startswith("<@") and mention.endswith(">"):
            try:
                uid = int(mention.strip("<@!>"))
                return guild.get_member(uid)
            except Exception:
                return None
        return None

    def _find_scheduling_channel(self, guild: discord.Guild, team1_name: str, team2_name: str) -> Optional[discord.TextChannel]:
        """
        Try to find a scheduling channel for these two teams.
        Uses channel name and topic; assumes '-vs-' style channels like 'team1-vs-team2'.
        """
        t1 = (team1_name or "").lower()
        t2 = (team2_name or "").lower()

        def norm(s: str) -> str:
            return re.sub(r"[^a-z0-9]", "", (s or "").lower())

        n_t1 = norm(t1)
        n_t2 = norm(t2)

        for ch in guild.text_channels:
            name = ch.name or ""
            topic = ch.topic or ""
            if "-vs-" not in name.lower():
                continue
            combined = name + " " + topic
            n_combined = norm(combined)
            if n_t1 in n_combined and n_t2 in n_combined:
                return ch
        return None

    @tasks.loop(minutes=1)
    async def check_matches(self):
        await self.bot.wait_until_ready()
        now_local = datetime.now()

        for guild in self.bot.guilds:
            ch = guild.get_channel(MATCH_TIMES_CHANNEL_ID)
            if not isinstance(ch, discord.TextChannel):
                continue

            try:
                async for msg in ch.history(limit=200):
                    mid = str(msg.id)

                    # already coded?
                    if mid in self.state:
                        continue

                    parsed = self._parse_match_message(msg)
                    if not parsed:
                        continue

                    sched_local = self._parse_time_to_local(parsed["time_str"])
                    if not sched_local:
                        continue

                    # send at macth time (within ~1 min around the time )
                    delta_min = (sched_local - now_local).total_seconds() / 60.0
                    if not (0 <= delta_min <= 5):
                        continue


                    # generate code
                    code = f"PGL{random.randint(1000, 9999)}"

                    # resolve teams to mentions
                    t1_role, t1_mention, _ = resolve_team_any(guild, parsed["team1"])
                    t2_role, t2_mention, _ = resolve_team_any(guild, parsed["team2"])

                    # compute FF display string purely from the original time string (EST-based)
                    ff_str = self._compute_ff_string_from_time_str(parsed["time_str"])

                    # post code in the scheduling channel for these teams, or fallback to MATCH_TIMES
                    body = (
                        f"{t1_mention} {t2_mention}\n"
                        f"# The Code Is:\n\n"
                        f"# {code}\n\n"
                        f"> time until FF is {ff_str}"
                    )

                    try:
                        sched_ch = self._find_scheduling_channel(guild, parsed["team1"], parsed["team2"])
                        target_ch = sched_ch if isinstance(sched_ch, discord.TextChannel) else ch
                        await target_ch.send(body)
                    except Exception:
                        pass

                    # DM caster/ref
                    caster = self._resolve_member_from_mention(guild, parsed["caster_mention"])
                    ref = self._resolve_member_from_mention(guild, parsed["ref_mention"])
                    dm_text = (
                        "# The Code Is:\n\n"
                        f"# {code}\n\n"
                        "***DO NOT SHARE THIS TO ANYONE. IF YOU DO, YOU WILL BE DEMOTED.***"
                    )
                    for target in (caster, ref):
                        if target and not target.bot:
                            try:
                                await target.send(dm_text)
                            except Exception:
                                pass

                    # remember we processed this message so we don't send again
                    self.state[mid] = {"code": code, "time": parsed["time_str"]}
                    save_codes_state(self.state)

            except Exception:
                continue

    @check_matches.before_loop
    async def before_check_matches(self):
        await self.bot.wait_until_ready()


from datetime import datetime, timedelta, timezone  # make sure timezone is imported

EST_TZ = timezone(timedelta(hours=-5))

def parse_time_to_unix_est(time_str: str) -> int | None:
    """
    Parse strings like:
      '1/17 at 8PM EST'
      '6/25/26 at 8PM EST'
      '6/25 at 8:10PM EST'
      '6/25/26 at 8:10PM EST'
    into a UNIX timestamp, assuming the time is EST.
    """
    if not time_str or " at " not in time_str:
        return None

    date_part, time_part = time_str.split(" at ", 1)
    date_part = date_part.strip()
    time_part = time_part.strip()

    # Strip timezone words
    for tz_word in ("EST", "EDT", "est", "edt"):
        time_part = time_part.replace(tz_word, "")
    time_part = time_part.strip()

    # Handle missing year -> use current year
    parts = date_part.split("/")
    if len(parts) == 2:
        m, d = parts
        try:
            year_now = datetime.now().year
            date_part_full = f"{int(m)}/{int(d)}/{year_now}"
        except Exception:
            return None
    else:
        date_part_full = date_part

    fmts = [
        "%m/%d/%y %I%p",
        "%m/%d/%Y %I%p",
        "%m/%d/%y %I:%M%p",
        "%m/%d/%Y %I:%M%p",
    ]

    dt_est = None
    for fmt in fmts:
        try:
            dt_est = datetime.strptime(f"{date_part_full} {time_part}", fmt)
            break
        except Exception:
            continue

    if dt_est is None:
        return None

    # Attach EST timezone so .timestamp() is correct
    dt_est = dt_est.replace(tzinfo=EST_TZ)
    return int(dt_est.timestamp())



class LeaveCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.guilds(Object(id=TEST_GUILD_ID))
    @app_commands.command(
        name="leave",
        description="Leave your team (players, co-captains, executives, captains).",
    )
    async def leave(self, interaction: discord.Interaction):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Use this in a server.",
                ephemeral=True,
            )
            return

        # resolve member
        try:
            member = guild.get_member(interaction.user.id) or await guild.fetch_member(interaction.user.id)
        except Exception:
            member = None

        if member is None:
            await interaction.response.send_message(
                "Could not resolve your member object.",
                ephemeral=True,
            )
            return

        # find team role ONLY from teams.json (using helper)
        team_role = find_member_team_role(member)
        if team_role is None:
            await interaction.response.send_message(
                "You are not on a team.",
                ephemeral=True,
            )
            return

        is_captain = has_role_id(member, CAPTAIN_ROLE_ID)
        is_co = has_role_id(member, CO_CAPTAIN_ROLE_ID)
        is_exec = has_role_id(member, TEAM_EXEC_ROLE_ID)
        is_player = has_role_id(member, TEAM_PLAYER_ROLE_ID)

        if not (is_player or is_co or is_exec or is_captain):
            await interaction.response.send_message(
                "Only players, co-captains, executives, or captains may use this command.",
                ephemeral=True,
            )
            return

        # -------- captain case: must transfer captain first --------
        if is_captain:
            candidates: list[discord.Member] = []
            for m in guild.members:
                if m.bot:
                    continue
                if team_role not in m.roles:
                    continue
                if has_role_id(m, CO_CAPTAIN_ROLE_ID) or has_role_id(m, TEAM_EXEC_ROLE_ID):
                    if m.id == member.id:
                        continue
                    candidates.append(m)
                    if len(candidates) >= 25:
                        break

            if not candidates:
                await interaction.response.send_message(
                    "You are the captain and there are no co-captains/executives to transfer to.\n"
                    "Please transfer captain to someone or disband the team before leaving.",
                    ephemeral=True,
                )
                return

            options = [
                discord.SelectOption(
                    label=c.display_name,
                    description=f"{c.name}#{c.discriminator}",
                    value=str(c.id),
                )
                for c in candidates
            ]
            select = discord.ui.Select(
                placeholder="Select a new captain",
                options=options,
                min_values=1,
                max_values=1,
            )

            async def sel_cb(sel_int: discord.Interaction):
                new_id = int(sel_int.data["values"][0])
                new_member = guild.get_member(new_id)
                if new_member is None:
                    await sel_int.response.send_message(
                        "Selected member not found.",
                        ephemeral=True,
                    )
                    return

                cap_role = guild.get_role(CAPTAIN_ROLE_ID)
                if cap_role is None:
                    await sel_int.response.send_message(
                        "Captain role not configured on this server.",
                        ephemeral=True,
                    )
                    return

                # transfer captain
                try:
                    if cap_role in member.roles:
                        await member.remove_roles(
                            cap_role,
                            reason=f"Transferred captain via /leave by {member}",
                        )
                    await new_member.add_roles(
                        cap_role,
                        reason=f"Promoted to captain by {member} via /leave",
                    )
                except Exception:
                    await sel_int.response.send_message(
                        "Failed to transfer captain role (missing Manage Roles?).",
                        ephemeral=True,
                    )
                    return

                # now remove leaver's team + global roles
                roles_to_remove: list[discord.Role] = []
                if team_role in member.roles:
                    roles_to_remove.append(team_role)
                for rid in (CO_CAPTAIN_ROLE_ID, TEAM_EXEC_ROLE_ID, TEAM_PLAYER_ROLE_ID):
                    r = guild.get_role(rid)
                    if r and r in member.roles:
                        roles_to_remove.append(r)

                try:
                    if roles_to_remove:
                        await member.remove_roles(
                            *roles_to_remove,
                            reason=f"Left team via /leave by {member}",
                        )
                except Exception:
                    await sel_int.response.send_message(
                        "Transferred captain but failed to remove some roles from you (missing perms?).",
                        ephemeral=True,
                    )
                    return

                # log
                try:
                    tx = guild.get_channel(TRANSACTIONS_CHANNEL_ID)
                    if isinstance(tx, discord.TextChannel):
                        await tx.send(f"{member.mention} Has left **{team_role.name}**")
                except Exception:
                    pass

                await sel_int.response.send_message(
                    f"Captain transferred to {new_member.mention} and you have left {team_role.name}.",
                    ephemeral=True,
                )

            select.callback = sel_cb
            view = discord.ui.View(timeout=60)
            view.add_item(select)
            await interaction.response.send_message(
                "You are the captain. Select a new captain to transfer to before leaving:",
                view=view,
                ephemeral=True,
            )
            return

        # -------- non-captain: just remove roles --------
        roles_to_remove: list[discord.Role] = []
        if team_role in member.roles:
            roles_to_remove.append(team_role)
        for rid in (CO_CAPTAIN_ROLE_ID, TEAM_EXEC_ROLE_ID, TEAM_PLAYER_ROLE_ID):
            r = guild.get_role(rid)
            if r and r in member.roles:
                roles_to_remove.append(r)

        try:
            if roles_to_remove:
                await member.remove_roles(
                    *roles_to_remove,
                    reason=f"Left team via /leave by {member}",
                )
        except Exception:
            await interaction.response.send_message(
                "Failed to remove roles (missing Manage Roles permission?). Contact staff.",
                ephemeral=True,
            )
            return

        # log
        try:
            tx = guild.get_channel(TRANSACTIONS_CHANNEL_ID)
            if isinstance(tx, discord.TextChannel):
                await tx.send(f"{member.mention} Has left **{team_role.name}**")
        except Exception:
            pass

        await interaction.response.send_message(
            f"You have left {team_role.name}.",
            ephemeral=True,
        )




class AdminKickModal(discord.ui.Modal, title="Admin Kick Player"):
    username = discord.ui.TextInput(label="What username is it? (mention or ID)", required=True)
    team = discord.ui.TextInput(label="What team? (mention/name/id)", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return

        raw_user = self.username.value.strip()
        if raw_user.startswith("<@") and raw_user.endswith(">"):
            raw_user = raw_user.strip("<@!>")
        member = None
        try:
            member = await guild.fetch_member(int(raw_user))
        except Exception:
            pass
        if member is None:
            await interaction.response.send_message("Could not find that user.", ephemeral=True)
            return

        raw_team = self.team.value.strip()
        team_role = None
        if raw_team.startswith("<@&") and raw_team.endswith(">"):
            try:
                rid = int(raw_team.strip("<@&>"))
                team_role = guild.get_role(rid)
            except Exception:
                pass
        if team_role is None:
            try:
                rid = int(raw_team)
                team_role = guild.get_role(rid)
            except Exception:
                pass
        if team_role is None:
            team_role = discord.utils.get(guild.roles, name=raw_team) or discord.utils.find(
                lambda r: r.name.lower() == raw_team.lower(), guild.roles
            )

        if team_role is None:
            await interaction.response.send_message("Could not find that team role.", ephemeral=True)
            return

        roles_to_remove = [r for r in member.roles if r.id in (team_role.id, TEAM_PLAYER_ROLE_ID)]
        if not roles_to_remove:
            await interaction.response.send_message(
                "That user does not appear to be on that team.",
                ephemeral=True,
            )
            return

        try:
            await member.remove_roles(*roles_to_remove, reason=f"Admin kick by {interaction.user}")
        except Exception:
            await interaction.response.send_message("Failed to remove roles (missing perms?).", ephemeral=True)
            return

        tx = guild.get_channel(TRANSACTIONS_CHANNEL_ID)
        if isinstance(tx, discord.TextChannel):
            await tx.send(f"{member.mention} Has Been kicked from **{team_role.name}** by an admin")

        await interaction.response.send_message(
            f"{member.mention} kicked from {team_role.mention}.",
            ephemeral=True,
        )

class SubmitCodeModal(discord.ui.Modal, title="Post Match Code"):
    team1 = discord.ui.TextInput(label="Team 1", required=True)
    team2 = discord.ui.TextInput(label="Team 2", required=True)
    code = discord.ui.TextInput(label="Code", required=True)

    def _resolve_role_and_display(self, guild, raw):
        t = raw.strip()
        if t.startswith("<@&") and t.endswith(">"):
            try:
                rid = int(t.strip("<@&>"))
                r = guild.get_role(rid)
            except Exception:
                r = None
            if r:
                return r, r.mention
        try:
            rid = int(t)
            r = guild.get_role(rid)
            if r:
                return r, r.mention
        except Exception:
            pass
        r = discord.utils.get(guild.roles, name=t) or discord.utils.find(lambda rr: rr.name.lower() == t.lower(), guild.roles)
        if r:
            return r, r.mention
        return None, raw

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return
        code = self.code.value.strip()
        t1_raw = self.team1.value.strip()
        t2_raw = self.team2.value.strip()

        # resolve roles/display names
        def _resolve(guild, raw):
            t = raw.strip()
            if t.startswith("<@&") and t.endswith(">"):
                try:
                    rid = int(t.strip("<@&>"))
                    r = guild.get_role(rid)
                except Exception:
                    r = None
                if r:
                    return r, r.mention
            try:
                rid = int(t)
                r = guild.get_role(rid)
                if r:
                    return r, r.mention
            except Exception:
                pass
            r = discord.utils.get(guild.roles, name=t) or discord.utils.find(lambda rr: rr.name.lower() == t.lower(), guild.roles)
            if r:
                return r, r.mention
            return None, raw

        t1_role, t1_disp = _resolve(guild, t1_raw)
        t2_role, t2_disp = _resolve(guild, t2_raw)

        msg = f"{t1_disp} vs {t2_disp}\n# The Code Is:\n\n# {code}"
        try:
            if interaction.channel:
                await interaction.channel.send(msg)
        except Exception:
            pass

        # search assignments channel for caster/ref; only DM if found
        assign = guild.get_channel(ASSIGNMENTS_CHANNEL_ID)
        caster = None
        ref = None
        if isinstance(assign, discord.TextChannel):
            try:
                async for m in assign.history(limit=200):
                    c = m.content or ""
                    mt1 = (t1_role and t1_role.name in c) or (t1_raw in c)
                    mt2 = (t2_role and t2_role.name in c) or (t2_raw in c)
                    if mt1 and mt2:
                        for line in c.splitlines():
                            ln = line.strip()
                            if ln.lower().startswith("> referee:"):
                                v = ln.split(":", 1)[1].strip()
                                if v.startswith("<@") and v.endswith(">"):
                                    try:
                                        uid = int(v.strip("<@!>"))
                                        ref = guild.get_member(uid)
                                    except Exception:
                                        pass
                            if ln.lower().startswith("> caster:"):
                                v = ln.split(":", 1)[1].strip()
                                if v.startswith("<@") and v.endswith(">"):
                                    try:
                                        uid = int(v.strip("<@!>"))
                                        caster = guild.get_member(uid)
                                    except Exception:
                                        pass
                        if caster or ref:
                            break
            except Exception:
                pass

        # DM only to found caster/ref
        dm_text = "# The Code Is:\n\n# " + code + "\n\n***DO NOT SHARE THIS TO ANYONE. IF YOU DO, YOU WILL BE DEMOTED.***"
        dm_sent = 0
        for m in (caster, ref):
            if m and not m.bot:
                try:
                    await m.send(dm_text)
                    dm_sent += 1
                except Exception:
                    pass

        await interaction.response.send_message(f"Code posted. DMed caster/ref ({dm_sent}).", ephemeral=True)



class AdminPanel(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.guilds(Object(id=TEST_GUILD_ID))
    @app_commands.default_permissions(administrator=True)
    @app_commands.command(name="admin-panel", description="Open the admin panel.")
    async def admin_panel(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You do not have permission.", ephemeral=True)
            return
        await interaction.response.send_message("Admin Panel:", view=AdminPanelView(), ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.author.bot:
            return
        if message.channel.id != TRANSACTIONS_CHANNEL_ID:
            return
        content = message.content.strip()
        if not content.lower().startswith("/create-team"):
            return
        guild = message.guild
        if guild is None:
            return
        parts = content.split()
        if len(parts) < 4:
            return
        raw_color = parts[-1]
        raw_capt = parts[-2]
        name = " ".join(parts[1:-2])
        if raw_capt.startswith("<@") and raw_capt.endswith(">"):
            raw_capt = raw_capt.strip("<@!>")
        try:
            capt = await guild.fetch_member(int(raw_capt))
        except Exception:
            capt = None
        if capt is None:
            return
        c = raw_color
        if not c.startswith("#"):
            c = "#" + c
        try:
            color_int = int(c[1:], 16)
        except Exception:
            return
        try:
            role = await guild.create_role(name=name, colour=discord.Colour(color_int),
                                           reason="Team created by apply-bot command")
        except Exception:
            return
        roles = [role]
        cap_role = guild.get_role(CAPTAIN_ROLE_ID)
        if cap_role:
            roles.append(cap_role)
        try:
            await capt.add_roles(*roles, reason="New team created via /create-team")
        except Exception:
            pass
        tx = guild.get_channel(TRANSACTIONS_CHANNEL_ID)
        if tx:
            try:
                await tx.send(f"# New Team Created!\n* Team Name: {role.mention}\n* Team Captain: {capt.mention}")
            except Exception:
                pass



class InviteUserSelect(discord.ui.UserSelect):
    def __init__(self, parent_view: "ManageTeamView", invoker_id: int):
        super().__init__(
            placeholder="Select a player to invite",
            min_values=1,
            max_values=1,
        )
        self.parent_view = parent_view
        self.invoker_id = invoker_id

    async def callback(self, interaction: discord.Interaction):
        # Only the original opener (unless admin override) can use this
        if (
            self.parent_view.invoker_id
            and not self.parent_view.admin_override
            and interaction.user.id != self.invoker_id
        ):
            await interaction.response.send_message("This panel is not for you.", ephemeral=True)
            return

        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return

        target = self.values[0]  # Member/User from UserSelect
        if not isinstance(target, (discord.Member, discord.User)):
            await interaction.response.send_message("Invalid selection.", ephemeral=True)
            return

        # We only care about real guild members for team checks
        if isinstance(target, discord.Member):
            if target.bot:
                await interaction.response.send_message("You cannot invite a bot.", ephemeral=True)
                return

            # Already on *this* team
            if self.parent_view.team_role in target.roles:
                await interaction.response.send_message(
                    f"{target.mention} is already on this team.",
                    ephemeral=True,
                )
                return

            # ---------- STRICT 'already on a team' check (local, no helper) ----------
            # Load team role IDs from teams.json
            try:
                teams_data = load_teams()
            except Exception:
                teams_data = []

            team_ids_from_file: set[int] = set()
            for entry in teams_data:
                rid = entry.get("role_id")
                if not rid:
                    continue
                try:
                    team_ids_from_file.add(int(rid))
                except (TypeError, ValueError):
                    continue

            def is_fake_team_role(r: discord.Role) -> bool:
                name = (r.name or "").strip().lower()
                if "team roles" in name:
                    return True
                if name and all(ch in "-—_ " for ch in name):
                    return True
                return False

            already_on_team = False
            for r in target.roles:
                if r.id in team_ids_from_file and not is_fake_team_role(r):
                    already_on_team = True
                    break

            if already_on_team:
                await interaction.response.send_message(
                    f"{target.mention} is already on a team.",
                    ephemeral=True,
                )
                return
            # -----------------------------------------------------------------

        team_role = self.parent_view.team_role
        team_name = team_role.name

        # find captain for display
        captain = None
        for m in guild.members:
            if has_role_id(m, CAPTAIN_ROLE_ID) and team_role in m.roles:
                captain = m
                break
        captain_disp = captain.mention if captain else interaction.user.mention

        class InviteAcceptView(discord.ui.View):
            def __init__(self, target_user: discord.abc.User):
                super().__init__(timeout=86400)
                self.target = target_user

            @discord.ui.button(label="Accept", style=discord.ButtonStyle.success)
            async def accept(self, intr: discord.Interaction, btn: discord.ui.Button):
                guild = team_role.guild

                member_obj = guild.get_member(self.target.id)
                if member_obj is None:
                    try:
                        member_obj = await guild.fetch_member(self.target.id)
                    except Exception:
                        member_obj = None

                if member_obj is None:
                    try:
                        await intr.response.send_message(
                            "Could not find you in the server to add roles. Contact staff.",
                            ephemeral=True,
                        )
                    except Exception:
                        pass
                    return

                roles_to_add = [team_role]
                team_player_role = guild.get_role(TEAM_PLAYER_ROLE_ID)
                if team_player_role and team_player_role not in roles_to_add:
                    roles_to_add.append(team_player_role)

                try:
                    await member_obj.add_roles(
                        *roles_to_add,
                        reason=f"Accepted invite to {team_name}",
                    )
                except Exception:
                    pass

                # remove pending invite record
                remove_pending_invite(team_role.id, self.target.id)

                # disable buttons
                for child in self.children:
                    if isinstance(child, discord.ui.Button):
                        child.disabled = True
                try:
                    await intr.message.edit(view=self)
                except Exception:
                    pass

                try:
                    await intr.message.reply(f"You joined {team_name}!")
                except Exception:
                    try:
                        await intr.followup.send(f"You joined {team_name}!")
                    except Exception:
                        pass

                try:
                    tx_ch = guild.get_channel(TRANSACTIONS_CHANNEL_ID)
                    if isinstance(tx_ch, discord.TextChannel):
                        await tx_ch.send(f"{member_obj.mention} Has Joined **{team_name}**")
                except Exception:
                    pass

                self.stop()

            @discord.ui.button(label="Decline", style=discord.ButtonStyle.danger)
            async def decline(self, intr: discord.Interaction, btn: discord.ui.Button):
                for child in self.children:
                    if isinstance(child, discord.ui.Button):
                        child.disabled = True
                try:
                    await intr.message.edit(view=self)
                except Exception:
                    pass

                # remove pending invite record
                remove_pending_invite(team_role.id, self.target.id)

                try:
                    await intr.response.send_message("You declined the invite.", ephemeral=True)
                except Exception:
                    pass
                self.stop()

        invite_accept_view = InviteAcceptView(target)

        embed_color = team_role.colour or discord.Color.blurple()
        embed = discord.Embed(
            title=f"You've been invited to {team_name}",
            description=f"{captain_disp} invited you to join {team_name}. Use the buttons below to respond.",
            color=embed_color,
        )
        if getattr(team_role, "icon", None):
            embed.set_thumbnail(url=team_role.icon.url)

        # record pending invite
        add_pending_invite(team_role.id, target.id)

        try:
            await target.send(embed=embed, view=invite_accept_view)
            await interaction.response.send_message(
                f"Tell {target.mention} to check their DMs with the bot.",
                ephemeral=True,
            )
        except Exception:
            await interaction.response.send_message(
                "Failed to DM that user (they may have DMs off or blocked the bot).",
                ephemeral=True,
            )


class ManageTeamView(discord.ui.View):
    def __init__(
        self,
        team_role: discord.Role,
        can_captain: bool,
        can_co_captain: bool,
        players: list[discord.Member],
        invoker_id: Optional[int],
        roster_locked: bool,
        admin_override: bool = False,
    ):
        super().__init__(timeout=300)
        self.team_role = team_role
        self.invoker_id = invoker_id
        self.admin_override = admin_override
        self.players = players
        self._roster_locked = roster_locked

        if players:
            member_select = discord.ui.Select(
                placeholder="Select member",
                min_values=1,
                max_values=1,
                options=[
                    discord.SelectOption(label=p.display_name, value=str(p.id))
                    for p in players
                ][:25],
                custom_id=f"mt:{team_role.id}:member",
            )

            async def member_cb(sel_inter: discord.Interaction, *, _select=member_select):
                if (
                    self.invoker_id
                    and not self.admin_override
                    and sel_inter.user.id != self.invoker_id
                ):
                    await sel_inter.response.send_message(
                        "This panel is not for you.", ephemeral=True
                    )
                    return

                target_id = int(sel_inter.data["values"][0])
                SELECTED_MEMBER_CACHE[(sel_inter.user.id, self.team_role.id)] = target_id

                # find the selected member object, if possible
                sel_member = None
                if sel_inter.guild:
                    sel_member = sel_inter.guild.get_member(target_id)

                # enable the four action buttons
                self._set_action_buttons_enabled(True)

                # edit the original manage-team message with updated view
                await sel_inter.response.edit_message(view=self)

                # send a small ephemeral note with the selected member's name
                if sel_member is not None:
                    note = (
                        f"Selected **{sel_member.display_name}**. "
                        "You can now use Kick / Promote / Assign Exec / Transfer Captain for them."
                    )
                else:
                    note = (
                        "Member selected. "
                        "You can now use Kick / Promote / Assign Exec / Transfer Captain."
                    )

                try:
                    await sel_inter.followup.send(note, ephemeral=True)
                except Exception:
                    pass

            member_select.callback = member_cb
            self.add_item(member_select)

        # start with the four action buttons disabled
        self._set_action_buttons_enabled(False)

    def _set_action_buttons_enabled(self, enabled: bool):
        """
        Enable/disable ONLY these four buttons:
        - Kick member
        - Promote to co-captain
        - Assign executive
        - Transfer captain

        Invite, Disband, Edit Team Info are never touched here.
        """
        target_labels = {
            "Kick member",
            "Promote to co-captain",
            "Assign executive",
            "Transfer captain",
        }
        for child in self.children:
            if isinstance(child, discord.ui.Button) and child.label in target_labels:
                child.disabled = not enabled

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.invoker_id and not self.admin_override:
            return interaction.user.id == self.invoker_id
        return True

    def _get_selected_member(self, user_id: int) -> Optional[int]:
        return SELECTED_MEMBER_CACHE.get((user_id, self.team_role.id))

    async def _tx(self, guild: discord.Guild, content: str):
        try:
            ch = guild.get_channel(TRANSACTIONS_CHANNEL_ID)
            if isinstance(ch, discord.TextChannel):
                await ch.send(content)
        except Exception:
            pass

    # ----------------- BUTTONS -----------------

    @discord.ui.button(label="Invite", style=discord.ButtonStyle.success, custom_id="mt_invite_button")
    async def invite_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # ALWAYS enabled
        if self.invoker_id and not self.admin_override and interaction.user.id != self.invoker_id:
            await interaction.response.send_message("This panel is not for you.", ephemeral=True)
            return

        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return

        view = discord.ui.View(timeout=60)
        view.add_item(InviteUserSelect(parent_view=self, invoker_id=interaction.user.id))

        await interaction.response.send_message(
            "Select a player to invite:",
            view=view,
            ephemeral=True,
        )

    @discord.ui.button(label="Kick member", style=discord.ButtonStyle.danger, custom_id="mt_kick_button")
    async def kick_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # starts disabled until member selected
        if self.invoker_id and not self.admin_override and interaction.user.id != self.invoker_id:
            await interaction.response.send_message("This panel is not for you.", ephemeral=True)
            return

        sel_id = self._get_selected_member(interaction.user.id)
        if not sel_id:
            await interaction.response.send_message(
                "No member selected. Use the dropdown to select a member first.",
                ephemeral=True,
            )
            return

        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Use in server.", ephemeral=True)
            return

        member = guild.get_member(sel_id)
        if member is None:
            await interaction.response.send_message("Member not found.", ephemeral=True)
            return

        roles_to_remove = []
        if self.team_role in member.roles:
            roles_to_remove.append(self.team_role)
        team_player_role = guild.get_role(TEAM_PLAYER_ROLE_ID)
        if team_player_role and team_player_role in member.roles:
            roles_to_remove.append(team_player_role)

        try:
            if roles_to_remove:
                await member.remove_roles(
                    *roles_to_remove,
                    reason=f"Kicked from {self.team_role.name} by {interaction.user}",
                )
        except Exception:
            await interaction.response.send_message(
                "Failed to remove roles (missing perms?).",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            f"{member.mention} kicked from {self.team_role.mention}.",
            ephemeral=True,
        )
        await self._tx(guild, f"{member.mention} Has Been kicked from **{self.team_role.name}**")

    @discord.ui.button(label="Promote to co-captain", style=discord.ButtonStyle.primary, custom_id="mt_promote_co_button")
    async def promote_co(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.invoker_id and not self.admin_override and interaction.user.id != self.invoker_id:
            await interaction.response.send_message("This panel is not for you.", ephemeral=True)
            return

        sel_id = self._get_selected_member(interaction.user.id)
        if not sel_id:
            await interaction.response.send_message(
                "No member selected. Use the dropdown to select a member first.",
                ephemeral=True,
            )
            return

        guild = interaction.guild
        member = guild.get_member(sel_id) if guild else None
        if member is None:
            await interaction.response.send_message("Member not found.", ephemeral=True)
            return

        co_role = guild.get_role(CO_CAPTAIN_ROLE_ID)
        if co_role is None:
            await interaction.response.send_message("Co-captain role not configured.", ephemeral=True)
            return

        # Count existing co-captains on this team
        current_cos = [
            m for m in guild.members
            if not m.bot and self.team_role in m.roles and has_role_id(m, CO_CAPTAIN_ROLE_ID)
        ]
        if len(current_cos) >= MAX_CO_CAPTAINS and not self.admin_override:
            await interaction.response.send_message(
                f"This team already has {len(current_cos)} co-captains (max {MAX_CO_CAPTAINS}).",
                ephemeral=True,
            )
            return

        try:
            await member.add_roles(co_role, reason=f"Promoted to co-captain by {interaction.user}")
            await interaction.response.send_message(f"{member.mention} promoted to co-captain.", ephemeral=True)
            await self._tx(guild, f"{member.mention} Has Been Promoted to Co-captain")
        except Exception:
            await interaction.response.send_message(
                "Failed to add co-captain role (missing perms?).",
                ephemeral=True,
            )

    @discord.ui.button(label="Assign executive", style=discord.ButtonStyle.primary, custom_id="mt_assign_exec_button")
    async def assign_exec(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.invoker_id and not self.admin_override and interaction.user.id != self.invoker_id:
            await interaction.response.send_message("This panel is not for you.", ephemeral=True)
            return

        sel_id = self._get_selected_member(interaction.user.id)
        if not sel_id:
            await interaction.response.send_message(
                "No member selected. Use the dropdown to select a member first.",
                ephemeral=True,
            )
            return

        guild = interaction.guild
        member = guild.get_member(sel_id) if guild else None
        if member is None:
            await interaction.response.send_message("Member not found.", ephemeral=True)
            return

        exec_role = guild.get_role(TEAM_EXEC_ROLE_ID)
        if exec_role is None:
            await interaction.response.send_message("Team executive role not configured.", ephemeral=True)
            return

        # Count existing executives on this team
        current_execs = [
            m for m in guild.members
            if not m.bot and self.team_role in m.roles and has_role_id(m, TEAM_EXEC_ROLE_ID)
        ]
        if len(current_execs) >= MAX_EXECUTIVES and not self.admin_override:
            await interaction.response.send_message(
                f"This team already has {len(current_execs)} executives (max {MAX_EXECUTIVES}).",
                ephemeral=True,
            )
            return

        try:
            await member.add_roles(exec_role, reason=f"Assigned executive by {interaction.user}")
            await interaction.response.send_message(f"{member.mention} assigned as team executive.", ephemeral=True)
            await self._tx(guild, f"{member.mention} Has Been Promoted to Team executive")
        except Exception:
            await interaction.response.send_message(
                "Failed to add executive role (missing perms?).",
                ephemeral=True,
            )

    @discord.ui.button(label="Transfer captain", style=discord.ButtonStyle.danger, custom_id="mt_transfer_captain_button")
    async def transfer_captain(self, interaction: discord.Interaction, button: discord.ui.Button):
        # starts disabled until member selected
        if self.invoker_id and not self.admin_override and interaction.user.id != self.invoker_id:
            await interaction.response.send_message("This panel is not for you.", ephemeral=True)
            return

        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Use in server.", ephemeral=True)
            return

        candidates = []
        for m in guild.members:
            if m.bot:
                continue
            if self.team_role not in m.roles:
                continue
            if has_role_id(m, CO_CAPTAIN_ROLE_ID) or has_role_id(m, TEAM_EXEC_ROLE_ID):
                candidates.append(discord.SelectOption(label=m.display_name, value=str(m.id)))
                if len(candidates) >= 25:
                    break

        if not candidates:
            await interaction.response.send_message(
                "No co-captain/executive candidates available to transfer to.",
                ephemeral=True,
            )
            return

        sel = discord.ui.Select(
            placeholder="Select new captain",
            options=candidates,
            min_values=1,
            max_values=1,
        )

        async def sel_cb(sel_int: discord.Interaction):
            new_id = int(sel_int.data["values"][0])
            new_member = guild.get_member(new_id)
            if new_member is None:
                await sel_int.response.send_message("Member not found.", ephemeral=True)
                return

            old_capt = None
            for m in guild.members:
                if self.team_role in m.roles and has_role_id(m, CAPTAIN_ROLE_ID):
                    old_capt = m
                    break

            cap_role = guild.get_role(CAPTAIN_ROLE_ID)
            if cap_role is None:
                await sel_int.response.send_message("Captain role not configured.", ephemeral=True)
                return

            try:
                if old_capt and cap_role in old_capt.roles:
                    await old_capt.remove_roles(
                        cap_role,
                        reason=f"Transferred captain to {new_member}",
                    )
                await new_member.add_roles(
                    cap_role,
                    reason=f"Promoted to captain for {self.team_role.name} by {sel_int.user}",
                )
            except Exception:
                await sel_int.response.send_message(
                    "Failed to transfer captain role (missing perms?).",
                    ephemeral=True,
                )
                return

            await sel_int.response.send_message("Captain transferred.", ephemeral=True)
            old_disp = old_capt.mention if old_capt else "None"
            await self._tx(
                guild,
                f"# {self.team_role.name} HAS CHANGED THERE CAPTAIN\n"
                f"***• Old Captain: {old_disp} New Captain: {new_member.mention} ***",
            )

        sel.callback = sel_cb
        v = discord.ui.View(timeout=60)
        v.add_item(sel)
        await interaction.response.send_message(
            "Select new captain:", view=v, ephemeral=True
        )

    @discord.ui.button(label="Disband", style=discord.ButtonStyle.danger, custom_id="mt_disband_button")
    async def disband_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # ALWAYS enabled (subject to invoker/admin check)
        if self.invoker_id and not self.admin_override and interaction.user.id != self.invoker_id:
            await interaction.response.send_message("This panel is not for you.", ephemeral=True)
            return

        confirm_view = discord.ui.View(timeout=60)

        async def yes_cb(i: discord.Interaction):
            guild = i.guild
            if guild is None:
                await i.response.send_message("Guild not found.", ephemeral=True)
                return

            try:
                await self.team_role.delete(reason=f"Disbanded by {i.user}")
            except Exception:
                pass

            team_player_role = guild.get_role(TEAM_PLAYER_ROLE_ID)
            for m in list(guild.members):
                if self.team_role in m.roles:
                    try:
                        to_remove = [self.team_role]
                        if team_player_role and team_player_role in m.roles:
                            to_remove.append(team_player_role)
                        await m.remove_roles(*to_remove, reason="Team disbanded")
                    except Exception:
                        pass

            await i.response.send_message("Team disbanded.", ephemeral=True)
            await self._tx(guild, f"# {self.team_role.name} HAS BEEN DISBANDED\n\n")
            confirm_view.stop()

        async def no_cb(i: discord.Interaction):
            await i.response.send_message("Canceled disband.", ephemeral=True)
            confirm_view.stop()

        yes = discord.ui.Button(label="Yes", style=discord.ButtonStyle.danger)
        no = discord.ui.Button(label="No", style=discord.ButtonStyle.secondary)
        yes.callback = yes_cb
        no.callback = no_cb
        confirm_view.add_item(yes)
        confirm_view.add_item(no)

        await interaction.response.send_message(
            "Are you sure you want to disband your team?",
            view=confirm_view,
            ephemeral=True,
        )

    @discord.ui.button(label="Edit Team Info", style=discord.ButtonStyle.secondary, custom_id="mt_edit_button")
    async def edit_info(self, interaction: discord.Interaction, button: discord.ui.Button):
        # ALWAYS enabled (subject to invoker/admin check)
        if self.invoker_id and not self.admin_override and interaction.user.id != self.invoker_id:
            await interaction.response.send_message("This panel is not for you.", ephemeral=True)
            return

        options = [
            discord.SelectOption(
                label="Team Profile Picture",
                description="Set a profile picture (URL).",
                value="pfp",
            )
        ]
        if self.admin_override:
            options.append(
                discord.SelectOption(
                    label="Change Team Color",
                    description="Update the team's color code in hex.",
                    value="color",
                )
            )
            options.append(
                discord.SelectOption(
                    label="Change Team Name",
                    description="Rename the team and log the rebrand.",
                    value="name",
                )
            )

        sel = discord.ui.Select(
            placeholder="Edit option",
            options=options,
            min_values=1,
            max_values=1,
        )

        async def sel_cb(sel_int: discord.Interaction):
            choice = sel_int.data["values"][0]
            self_view = self

            if choice == "name":
                class NameModal(discord.ui.Modal, title="Change Team Name"):
                    new_name = discord.ui.TextInput(
                        label="What is your new team's name?",
                        required=True,
                        max_length=100,
                    )

                    async def on_submit(self, modal_inter: discord.Interaction):
                        old = self_view.team_role.name
                        try:
                            await self_view.team_role.edit(
                                name=self.new_name.value,
                                reason=f"Team rename by {modal_inter.user}",
                            )
                            await modal_inter.response.send_message(
                                f"Team renamed to {self.new_name.value}.",
                                ephemeral=True,
                            )
                            await self_view._tx(
                                modal_inter.guild,
                                f"# TEAM HAS REBANED\n*** Old Name: {old} New Name: {self.new_name.value} ***",
                            )
                        except Exception:
                            await modal_inter.response.send_message(
                                "Failed to rename team (missing perms?).",
                                ephemeral=True,
                            )

                await sel_int.response.send_modal(NameModal())

            elif choice == "color":
                class ColorModal(discord.ui.Modal, title="Change Team Color"):
                    color = discord.ui.TextInput(
                        label="What is your new team's color code (in hex):",
                        required=True,
                        max_length=7,
                    )

                    async def on_submit(self, modal_inter: discord.Interaction):
                        new_code = self.color.value.strip()
                        if not new_code.startswith("#"):
                            new_code = "#" + new_code
                        try:
                            color_int = int(new_code[1:], 16)
                        except Exception:
                            await modal_inter.response.send_message(
                                "Invalid color code.", ephemeral=True
                            )
                            return
                        old_col = self_view.team_role.colour
                        try:
                            await self_view.team_role.edit(
                                colour=discord.Colour(color_int),
                                reason=f"Team color change by {modal_inter.user}",
                            )
                            await modal_inter.response.send_message(
                                "Team color updated.", ephemeral=True
                            )
                            await self_view._tx(
                                modal_inter.guild,
                                f"# TEAM HAS CHANGE THERE COLOR CODE\n***• Old Color Code: {old_col} New Color Code: {new_code} ***",
                            )
                        except Exception:
                            await modal_inter.response.send_message(
                                "Failed to change color (missing perms?).",
                                ephemeral=True,
                            )

                await sel_int.response.send_modal(ColorModal())

            elif choice == "pfp":
                class PFPModal(discord.ui.Modal, title="Set Team Profile Picture"):
                    url = discord.ui.TextInput(
                        label="What is your new team's pfp? (URL)",
                        required=True,
                    )

                    async def on_submit(self, modal_inter: discord.Interaction):
                        url_val = self.url.value.strip()
                        try:
                            import aiohttp
                            async with aiohttp.ClientSession() as sess:
                                async with sess.get(url_val, timeout=15) as resp:
                                    if resp.status != 200:
                                        await modal_inter.response.send_message(
                                            "Failed to download image from URL.",
                                            ephemeral=True,
                                        )
                                        return
                                    data = await resp.read()
                        except Exception:
                            await modal_inter.response.send_message(
                                "Failed to download image from URL.",
                                ephemeral=True,
                            )
                            return

                        created_emoji = None
                        try:
                            await self_view.team_role.edit(
                                reason=f"Team pfp set by {modal_inter.user}",
                                icon=data,
                            )
                            await modal_inter.response.send_message(
                                "Team PFP set as role icon (if supported).",
                                ephemeral=True,
                            )
                        except Exception:
                            try:
                                import re
                                name_safe = re.sub(
                                    r"[^0-9A-Za-z_]", "_", self_view.team_role.name
                                )[:32] or "teamimg"
                                created_emoji = await modal_inter.guild.create_custom_emoji(
                                    name=name_safe,
                                    image=data,
                                    reason="Team pfp uploaded",
                                )
                            except Exception:
                                created_emoji = None

                            if created_emoji:
                                await modal_inter.response.send_message(
                                    f"Team PFP uploaded as emoji: {created_emoji}",
                                    ephemeral=True,
                                )
                            else:
                                await modal_inter.response.send_message(
                                    "Team PFP updated (or attempt made). "
                                    "If nothing changed, check bot permissions.",
                                    ephemeral=True,
                                )

                await sel_int.response.send_modal(PFPModal())

        sel.callback = sel_cb
        v = discord.ui.View(timeout=60)
        v.add_item(sel)
        await interaction.response.send_message(
            "Choose edit action:",
            view=v,
            ephemeral=True,
        )



# ---------------- Standing Cog ----------------
class StandingCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.guilds(Object(id=TEST_GUILD_ID))
    @app_commands.default_permissions(administrator=True)
    @app_commands.command(
        name="start-seeding",
        description="Enable seeding and allow /standing to be used.",
    )
    async def start_seeding(self, interaction: discord.Interaction):
        global SEEDING_OPEN
        SEEDING_OPEN = True

        guild = interaction.guild
        await interaction.response.send_message(
            "Seeding has started. `/standing` is now available to everyone.",
            ephemeral=True,
        )

        if guild is None:
            return

        # resolve seeding-points channel: CONFIG override -> constant
        ch_cfg = CONFIG.get("channels", {}) or {}
        ch_id = ch_cfg.get("seeding_points") or SEEDING_POINTS_CHANNEL_ID
        seeding_ch = guild.get_channel(ch_id) if ch_id else None
        if not isinstance(seeding_ch, discord.TextChannel):
            return  # nothing configured, just skip

        info_text = (
            "use `/standing` to see the seeding, and here is how points work:\n\n"
            "for winning = **3 PTS**\n"
            "for losing = **1 PTS**\n"
            "for a time cap = **3 extra PTS**"
        )

        # only post once: check recent messages for exact same text from this bot
        already_posted = False
        try:
            async for msg in seeding_ch.history(limit=50):
                if msg.author == self.bot.user and msg.content.strip() == info_text.strip():
                    already_posted = True
                    break
        except Exception:
            pass

        if not already_posted:
            try:
                await seeding_ch.send(info_text)
            except Exception:
                pass

    @app_commands.guilds(Object(id=TEST_GUILD_ID))
    @app_commands.default_permissions(administrator=True)
    @app_commands.command(
        name="end-seeding",
        description="Disable seeding and hide /standing for everyone.",
    )
    async def end_seeding(self, interaction: discord.Interaction):
        global SEEDING_OPEN
        SEEDING_OPEN = False

        guild = interaction.guild
        await interaction.response.send_message(
            "Seeding has ended. `/standing` is now disabled for everyone.",
            ephemeral=True,
        )

        if guild is None:
            return

        # resolve seeding-points channel: CONFIG override -> constant
        ch_cfg = CONFIG.get("channels", {}) or {}
        ch_id = ch_cfg.get("seeding_points") or SEEDING_POINTS_CHANNEL_ID
        seeding_ch = guild.get_channel(ch_id) if ch_id else None
        if not isinstance(seeding_ch, discord.TextChannel):
            return

        info_text = (
            "use `/standing` to see the seeding, and here is how points work:\n\n"
            "for winning = **3 PTS**\n"
            "for losing = **1 PTS**\n"
            "for a time cap = **3 extra PTS**"
        )

        # find and delete the info message posted by this bot
        try:
            async for msg in seeding_ch.history(limit=50):
                if msg.author == self.bot.user and msg.content.strip() == info_text.strip():
                    try:
                        await msg.delete()
                    except Exception:
                        pass
                    break
        except Exception:
            pass

    @app_commands.guilds(Object(id=TEST_GUILD_ID))
    @app_commands.command(
        name="standing",
        description="View league standings for all teams.",
    )
    async def standing(self, interaction: discord.Interaction):
        global SEEDING_OPEN

        # Block if seeding is closed (must answer here, no defer yet)
        if not SEEDING_OPEN:
            await interaction.response.send_message(
                "Seeding is not currently active. Standings are hidden.",
                ephemeral=True,
            )
            return

        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Must be used in a server.",
                ephemeral=True,
            )
            return

        # From here on we can safely defer and use followup
        await interaction.response.defer(ephemeral=True)

        teams_data = load_teams()
        if not teams_data:
            await interaction.followup.send(
                "There are no teams in the system.",
                ephemeral=True,
            )
            return

        stats: dict[str, dict[str, int]] = {}
        for entry in teams_data:
            rid = entry.get("role_id")
            name = entry.get("name", "Unknown Team")
            try:
                role = guild.get_role(int(rid)) if rid else None
            except Exception:
                role = None
            if role is None:
                continue
            stats[name] = {"W": 0, "L": 0, "TC": 0, "PT": 0}

        if not stats:
            await interaction.followup.send(
                "There are no valid teams in the system.",
                ephemeral=True,
            )
            return

        score_ch = guild.get_channel(MATCH_SCORE_CHANNEL_ID)
        if score_ch is None or not isinstance(score_ch, discord.TextChannel):
            await interaction.followup.send(
                "Match scores channel is not configured correctly.",
                ephemeral=True,
            )
            return

        async for msg in score_ch.history(limit=500):
            content = msg.content
            lines = [ln.strip() for ln in content.splitlines() if ln.strip()]
            if not lines:
                continue
            try:
                winner_name = None
                loser_name = None
                timecap_val = "no"
                for ln in lines:
                    ln_clean = ln.lstrip("> ").strip()
                    lower = ln_clean.lower()
                    if lower.startswith("winner:"):
                        winner_name = ln_clean.split(":", 1)[1].strip()
                    elif lower.startswith("loser:"):
                        loser_name = ln_clean.split(":", 1)[1].strip()
                    elif lower.startswith("timecap:"):
                        timecap_val = ln_clean.split(":", 1)[1].strip()
                if not winner_name or not loser_name:
                    continue
                if winner_name not in stats or loser_name not in stats:
                    continue
                stats[winner_name]["W"] += 1
                stats[loser_name]["L"] += 1
                if timecap_val.lower() != "no":
                    stats[winner_name]["TC"] += 1
            except Exception:
                continue

        for name, s in stats.items():
            s["PT"] = 3 * s["W"] + 1 * s["L"] + 3 * s["TC"]

        ordered = sorted(
            stats.items(),
            key=lambda kv: (-kv[1]["PT"], kv[0].lower()),
        )
        if not ordered:
            await interaction.followup.send(
                "There are no results for any teams yet.",
                ephemeral=True,
            )
            return

        lines_out = ["Monke Monke Monke League SEEDING"]
        rank = 1
        for name, s in ordered:
            lines_out.append(
                f"> {rank}. {name} {s['W']} W - {s['L']} L - {s['PT']} PT"
            )
            rank += 1

        await interaction.followup.send("\n".join(lines_out), ephemeral=True)







class AssignmentClaimView(discord.ui.View):
    def __init__(self, week: str, time: str, team1_name: str, team2_name: str):
        super().__init__(timeout=None)
        self.week = week
        self.time = time
        self.team1_name = team1_name
        self.team2_name = team2_name
        self.caster: Optional[discord.Member] = None
        self.referee: Optional[discord.Member] = None

    async def _find_message_to_edit(self, channel: discord.TextChannel) -> Optional[discord.Message]:
        if channel is None:
            return None

        stage_l = (self.week or "").lower()
        if "final" in stage_l:
            header = "# FINALS"
            special = True
        elif "semi" in stage_l:
            header = "# SEMIFINALS"
            special = True
        else:
            header = ""
            special = False

        teams_line_regular = f"{self.team1_name} vs {self.team2_name}"
        teams_line_special = f"> Teams: {self.team1_name} vs {self.team2_name}"
        q_week = f"> WEEK: {self.week}"
        q_time = f"> Time: {self.time}"

        try:
            async for msg in channel.history(limit=200):
                c = msg.content or ""
                if special:
                    if header in c and teams_line_special in c:
                        return msg
                else:
                    if teams_line_regular in c and q_week in c and q_time in c:
                        return msg
        except Exception:
            return None
        return None

    async def _update_messages(self, interaction: discord.Interaction):
        guild = interaction.guild
        if guild is None:
            return

        match_times = guild.get_channel(MATCH_TIMES_CHANNEL_ID)
        assignments = guild.get_channel(ASSIGNMENTS_CHANNEL_ID)

        caster_text = self.caster.mention if self.caster else ""
        ref_text = self.referee.mention if self.referee else ""

        stage_l = (self.week or "").lower()
        if "final" in stage_l:
            header = "# FINALS"
            special = True
        elif "semi" in stage_l:
            header = "# SEMIFINALS"
            special = True
        else:
            header = None
            special = False

        # Build Discord timestamp from the stored time string
        unix_ts = parse_time_to_unix_est(self.time)
        ts_str = f" (<t:{unix_ts}:F>)" if unix_ts is not None else ""

        # --------- MATCH_TIMES message content ---------
        if special:
            mt_content = (
                f"{header}\n"
                f"> Teams: {self.team1_name} vs {self.team2_name}\n"
                f"> Time: {self.time}{ts_str}\n"
                f"> Referee: {ref_text}\n"
                f"> Caster: {caster_text}"
            )
        else:
            mt_content = (
                f"{self.team1_name} vs {self.team2_name}\n"
                f"> WEEK: {self.week}\n"
                f"> Time: {self.time}{ts_str}\n"
                f"> Referee: {ref_text}\n"
                f"> Caster: {caster_text}"
            )

        if isinstance(match_times, discord.TextChannel):
            mt_msg = await self._find_message_to_edit(match_times)
            try:
                if mt_msg:
                    await mt_msg.edit(content=mt_content)
            except Exception:
                pass

        # --------- ASSIGNMENTS message content ---------
        staff_mentions = []
        for rid in (HEAD_REF_ROLE_ID, REF_ROLE_ID, HEAD_CASTER_ROLE_ID, CASTER_ROLE_ID):
            r = guild.get_role(rid)
            if r:
                staff_mentions.append(r.mention)
        staff_header = " ".join(staff_mentions)

        if special:
            as_content = (
                f"{staff_header}\n"
                f"{header}\n"
                f"> Teams: {self.team1_name} vs {self.team2_name}\n"
                f"> Time: {self.time}{ts_str}\n"
                f"> Referee: {ref_text}\n"
                f"> Caster: {caster_text}"
            )
        else:
            as_content = (
                f"{staff_header}\n"
                f"{self.team1_name} vs {self.team2_name}\n"
                f"> WEEK: {self.week}\n"
                f"> Time: {self.time}{ts_str}\n"
                f"> Referee: {ref_text}\n"
                f"> Caster: {caster_text}"
            )

        if isinstance(assignments, discord.TextChannel):
            as_msg = await self._find_message_to_edit(assignments)
            try:
                if as_msg:
                    await as_msg.edit(content=as_content, view=self)
            except Exception:
                pass

    @discord.ui.button(label="Claim Caster", style=discord.ButtonStyle.primary)
    async def claim_caster(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return

        is_finals = "final" in (self.week or "").lower()
        is_admin = user.guild_permissions.administrator

        # Normal matches: any caster or head caster can claim.
        # Finals: ONLY head caster (plus admins) can claim.
        has_caster = has_role_id(user, CASTER_ROLE_ID) or has_role_id(user, HEAD_CASTER_ROLE_ID)
        has_head_caster = has_role_id(user, HEAD_CASTER_ROLE_ID)

        if is_finals:
            if not (has_head_caster or is_admin):
                await interaction.response.send_message(
                    "Only Head Casters (or admins) may claim Caster for Finals.",
                    ephemeral=True,
                )
                return
        else:
            if not has_caster:
                await interaction.response.send_message(
                    "Only casters may claim this slot.",
                    ephemeral=True,
                )
                return

        prev = self.caster
        self.caster = user

        # disable only this button for this view
        button.disabled = True
        await interaction.response.send_message("You claimed Caster.", ephemeral=True)

        if prev and prev != user:
            try:
                await prev.send(
                    f"You were unclaimed as Caster for {self.team1_name} vs {self.team2_name}."
                )
            except Exception:
                pass

        await self._update_messages(interaction)

    @discord.ui.button(label="Claim Referee", style=discord.ButtonStyle.primary)
    async def claim_ref(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return

        is_finals = "final" in (self.week or "").lower()
        is_admin = user.guild_permissions.administrator

        # Normal matches: any ref or head ref can claim.
        # Finals: ONLY head ref (or admins) can claim.
        has_ref = has_role_id(user, REF_ROLE_ID) or has_role_id(user, HEAD_REF_ROLE_ID)
        has_head_ref = has_role_id(user, HEAD_REF_ROLE_ID)

        if is_finals:
            if not (has_head_ref or is_admin):
                await interaction.response.send_message(
                    "Only Head Referees (or admins) may claim Referee for Finals.",
                    ephemeral=True,
                )
                return
        else:
            if not has_ref:
                await interaction.response.send_message(
                    "Only referees may claim this slot.",
                    ephemeral=True,
                )
                return

        prev = self.referee
        self.referee = user

        button.disabled = True
        await interaction.response.send_message("You claimed Referee.", ephemeral=True)

        if prev and prev != user:
            try:
                await prev.send(
                    f"You were unclaimed as Referee for {self.team1_name} vs {self.team2_name}."
                )
            except Exception:
                pass

        await self._update_messages(interaction)

    @discord.ui.button(label="Unclaim", style=discord.ButtonStyle.danger)
    async def unclaim(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Clear both claims; Unclaim button stays enabled
        self.caster = None
        self.referee = None
        # Re-enable claim buttons on this view instance (they will be re-rendered enabled)
        for child in self.children:
            if isinstance(child, discord.ui.Button) and child.label in ("Claim Caster", "Claim Referee"):
                child.disabled = False
        await interaction.response.send_message("Claims cleared.", ephemeral=True)
        await self._update_messages(interaction)


class TimeAcceptView(discord.ui.View):
    def __init__(
        self,
        guild: discord.Guild,
        team1_role: Optional[discord.Role],
        team2_role: Optional[discord.Role],
        team1_name: str,
        team2_name: str,
        week: str,
        time: str,
    ):
        super().__init__(timeout=None)
        self.guild = guild
        self.team1_role = team1_role
        self.team2_role = team2_role
        self.team1_name = team1_name
        self.team2_name = team2_name
        self.week = week
        self.time = time

        # runtime state
        self.team1_accepted: bool = False
        self.team2_accepted: bool = False
        self.origin_message: Optional[discord.Message] = None

        # for origin message display
        self.team1_mention = team1_role.mention if isinstance(team1_role, discord.Role) else team1_name
        self.team2_mention = team2_role.mention if isinstance(team2_role, discord.Role) else team2_name

    def _is_team_lead(self, member: discord.Member, team_role: Optional[discord.Role]) -> bool:
        if team_role is None:
            return False
        if team_role not in member.roles:
            return False
        return any(has_role_id(member, rid) for rid in (CAPTAIN_ROLE_ID, CO_CAPTAIN_ROLE_ID, TEAM_EXEC_ROLE_ID))

    async def _finalize_if_ready(self, interaction: discord.Interaction):
        if not (self.team1_accepted and self.team2_accepted):
            return

        guild = self.guild
        match_times = guild.get_channel(MATCH_TIMES_CHANNEL_ID)
        assignments = guild.get_channel(ASSIGNMENTS_CHANNEL_ID)

        stage_l = (self.week or "").lower()
        if "final" in stage_l:
            header = "# FINALS"
            special = True
        elif "semi" in stage_l:
            header = "# SEMIFINALS"
            special = True
        else:
            header = None
            special = False

        # build discord timestamp
        unix_ts = parse_time_to_unix_est(self.time)
        ts_str = f"<t:{unix_ts}:F>" if unix_ts is not None else self.time

        if special:
            mt_content = (
                f"{header}\n"
                f"> Teams: {self.team1_name} vs {self.team2_name}\n"
                f"> Time: {ts_str}\n"
                f"> Referee: \n"
                f"> Caster: "
            )
        else:
            mt_content = (
                f"{self.team1_name} vs {self.team2_name}\n"
                f"> WEEK: {self.week}\n"
                f"> Time: {ts_str}\n"
                f"> Referee: \n"
                f"> Caster: "
            )


        if isinstance(match_times, discord.TextChannel):
            try:
                await match_times.send(mt_content)
            except Exception:
                pass

        # ASSIGNMENTS message
        staff_mentions = []
        for rid in (HEAD_REF_ROLE_ID, REF_ROLE_ID, HEAD_CASTER_ROLE_ID, CASTER_ROLE_ID):
            r = guild.get_role(rid)
            if r:
                staff_mentions.append(r.mention)
        staff_header = " ".join(staff_mentions)

        if special:
            as_content = (
                f"{staff_header}\n"
                f"{header}\n"
                f"> Teams: {self.team1_name} vs {self.team2_name}\n"
                f"> Time: {self.time}{ts_str}\n"
                f"> Referee: \n"
                f"> Caster: "
            )
        else:
            as_content = (
                f"{staff_header}\n"
                f"{self.team1_name} vs {self.team2_name}\n"
                f"> WEEK: {self.week}\n"
                f"> Time: {self.time}{ts_str}\n"
                f"> Referee: \n"
                f"> Caster: "
            )

        if isinstance(assignments, discord.TextChannel):
            try:
                view = AssignmentClaimView(self.week, self.time, self.team1_name, self.team2_name)
                await assignments.send(as_content, view=view)
            except Exception:
                pass

    async def _edit_origin(self):
        if not self.origin_message:
            return
        t1_line = f"{self.team1_mention}"
        t2_line = f"{self.team2_mention}"
        if self.team1_accepted:
            t1_line += " ✅"
        if self.team2_accepted:
            t2_line += " ✅"
        content = (
            f"{t1_line} vs {t2_line}\n"
            f"Team staff must accept this match.\n"
            f"> WEEK: {self.week}\n"
            f"> Time: {self.time}\n"
            f"> Team 1: {'Accepted ✅' if self.team1_accepted else ''}\n"
            f"> Team 2: {'Accepted ✅' if self.team2_accepted else ''}\n"
        )
        try:
            await self.origin_message.edit(content=content, view=self)
        except Exception:
            pass

    @discord.ui.button(label="Accept for Team 1", style=discord.ButtonStyle.success)
    async def accept_team1(self, interaction: discord.Interaction, button: discord.ui.Button):
        member = interaction.user
        if not self._is_team_lead(member, self.team1_role):
            await interaction.response.send_message("Only staff from Team 1 (captain/co-cap/exec) can accept.", ephemeral=True)
            return
        if self.team1_accepted:
            await interaction.response.send_message("Team 1 already accepted.", ephemeral=True)
            return

        self.team1_accepted = True
        # disable only Team 1 button
        for child in self.children:
            if isinstance(child, discord.ui.Button) and child.label == "Accept for Team 1":
                child.disabled = True

        await self._edit_origin()
        await interaction.response.send_message("Team 1 accepted.", ephemeral=True)
        await self._finalize_if_ready(interaction)

    @discord.ui.button(label="Accept for Team 2", style=discord.ButtonStyle.success)
    async def accept_team2(self, interaction: discord.Interaction, button: discord.ui.Button):
        member = interaction.user
        if not self._is_team_lead(member, self.team2_role):
            await interaction.response.send_message("Only staff from Team 2 (captain/co-cap/exec) can accept.", ephemeral=True)
            return
        if self.team2_accepted:
            await interaction.response.send_message("Team 2 already accepted.", ephemeral=True)
            return

        self.team2_accepted = True
        # disable only Team 2 button
        for child in self.children:
            if isinstance(child, discord.ui.Button) and child.label == "Accept for Team 2":
                child.disabled = True

        await self._edit_origin()
        await interaction.response.send_message("Team 2 accepted.", ephemeral=True)
        await self._finalize_if_ready(interaction)




class ForceTimeView(discord.ui.View):
    def __init__(
        self,
        team1_role: Optional[discord.Role],
        team2_role: Optional[discord.Role],
        team1_mention: str,
        team2_mention: str,
        team1_name: str,
        team2_name: str,
        time_str: str,
    ):
        super().__init__(timeout=None)
        self.team1_role = team1_role
        self.team2_role = team2_role
        self.team1_mention = team1_mention
        self.team2_mention = team2_mention
        self.team1_name = team1_name
        self.team2_name = team2_name
        self.time_str = time_str

    def _build_forced_message(self) -> str:
        # Only the "real time" line, for after /force-time is accepted
        return f"{self.team1_mention} {self.team2_mention} Your day to play is: {self.time_str}"


    def _build_staff_message(self, guild: discord.Guild) -> str:
        staff_mentions = []
        for rid in (
            BOARD_OF_DIRECTORS_ROLE_ID,
            COMMUNITY_MANAGER_ROLE_ID,
            SUPERVISOR_ROLE_ID,
            DEVELOPMENT_TEAM_ROLE_ID,  # <- added
        ):

            r = guild.get_role(rid)
            if r:
                staff_mentions.append(r.mention)
        staff_header = " ".join(staff_mentions) or ""

        return (
            f"{staff_header}\n"
            f"I have picked this time for {self.team1_mention} and {self.team2_mention}: **{self.time_str}**\n\n"
            f"If you want me to post the message click on the **Accept** button,\n"
            f"but if you want me to find a new time click the **Deny** button."
        )

    def _find_scheduling_channel(self, guild: discord.Guild) -> Optional[discord.TextChannel]:
        """
        Try to find a scheduling channel for these two teams.
        Uses channel name and topic; assumes '-vs-' style channels like 'team1-vs-team2'.
        """
        t1 = self.team1_name.lower()
        t2 = self.team2_name.lower()

        def norm(s: str) -> str:
            import re
            return re.sub(r"[^a-z0-9]", "", s.lower())

        n_t1 = norm(t1)
        n_t2 = norm(t2)

        for ch in guild.text_channels:
            name = ch.name or ""
            topic = ch.topic or ""
            if "-vs-" not in name.lower():
                continue
            combined = name + " " + topic
            n_combined = norm(combined)
            if n_t1 in n_combined and n_t2 in n_combined:
                return ch
        return None

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return

        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Only admins can accept.", ephemeral=True)
            return

        # 1) Find the scheduling channel based on team names and post forced-time message
        sched_ch = self._find_scheduling_channel(guild)
        if not isinstance(sched_ch, discord.TextChannel):
            await interaction.response.send_message(
                "Could not find a scheduling channel for these teams.",
                ephemeral=True,
            )
            return

        forced_msg = self._build_forced_message()
        try:
            await sched_ch.send(forced_msg)
        except Exception:
            await interaction.response.send_message("Failed to send forced time message.", ephemeral=True)
            return

        # 2) Auto "submit time" into MATCH_TIMES and ASSIGNMENTS

        # Treat this as WEEK: Forced
        week = "Forced"
        time_str = self.time_str

        unix_ts = parse_time_to_unix_est(time_str)
        ts_str = f"<t:{unix_ts}:F>" if unix_ts is not None else time_str


        # MATCH_TIMES entry (like a finalized time)
        match_times = guild.get_channel(MATCH_TIMES_CHANNEL_ID)
        if isinstance(match_times, discord.TextChannel):
            mt_content = (
                f"{self.team1_name} vs {self.team2_name}\n"
                f"> WEEK: {week}\n"
                f"> Time: {ts_str}\n"
                f"> Referee: \n"
                f"> Caster: "
            )

            try:
                await match_times.send(mt_content)
            except Exception:
                pass

        # ASSIGNMENTS entry with AssignmentClaimView so staff can claim
        assignments = guild.get_channel(ASSIGNMENTS_CHANNEL_ID)
        if isinstance(assignments, discord.TextChannel):
            staff_mentions = []
            for rid in (HEAD_REF_ROLE_ID, REF_ROLE_ID, HEAD_CASTER_ROLE_ID, CASTER_ROLE_ID):
                r = guild.get_role(rid)
                if r:
                    staff_mentions.append(r.mention)
            staff_header = " ".join(staff_mentions)

            as_content = (
                f"{staff_header}\n"
                f"{self.team1_name} vs {self.team2_name}\n"
                f"> WEEK: {week}\n"
                f"> Time: {time_str}{ts_str}\n"
                f"> Referee: \n"
                f"> Caster: "
            )
            try:
                view = AssignmentClaimView(week=week, time=time_str,
                                           team1_name=self.team1_name,
                                           team2_name=self.team2_name)
                await assignments.send(as_content, view=view)
            except Exception:
                pass

        # 3) Finish up the interaction
        await interaction.response.send_message(
            f"Forced time posted in {sched_ch.mention} and scheduling records updated.",
            ephemeral=True,
        )
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
        try:
            await interaction.message.edit(view=self)
        except Exception:
            pass
        self.stop()

    @discord.ui.button(label="Deny", style=discord.ButtonStyle.danger)
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return

        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Only admins can deny.", ephemeral=True)
            return

        # pick a new time
        self.time_str = generate_forced_time_string()

        # update staff message with new time
        new_content = self._build_staff_message(guild)
        try:
            await interaction.message.edit(content=new_content, view=self)
        except Exception:
            pass

        await interaction.response.send_message("Picked a new time.", ephemeral=True)


class SubmitTimeModal(discord.ui.Modal, title="Submit Match Time"):
    week = discord.ui.TextInput(label="WEEK", required=True)
    time = discord.ui.TextInput(label="Time", required=True)
    team1 = discord.ui.TextInput(label="Team 1 (mention/name/id)", required=True)
    team2 = discord.ui.TextInput(label="Team 2 (mention/name/id)", required=True)

    def _resolve_team(self, guild: discord.Guild, raw: str) -> tuple[Optional[discord.Role], str, str]:
        text = raw.strip()

        # 1) Mention: <@&123>
        if text.startswith("<@&") and text.endswith(">"):
            try:
                rid = int(text.strip("<@&>"))
                r = guild.get_role(rid)
                if r:
                    return r, r.mention, r.name
            except Exception:
                pass

        # 2) Raw ID: 1234567890
        try:
            rid = int(text)
            r = guild.get_role(rid)
            if r:
                return r, r.mention, r.name
        except Exception:
            pass

        # 3) Direct role name match (case-insensitive)
        r = (
            discord.utils.get(guild.roles, name=text)
            or discord.utils.find(lambda rr: rr.name.lower() == text.lower(), guild.roles)
        )
        if r:
            return r, r.mention, r.name

        # 4) Fallback: look in teams.json by team "name" field
        try:
            teams = load_teams()  # uses your existing helper
        except Exception:
            teams = []

        text_lower = text.lower()
        matched_role = None

        for entry in teams:
            t_name = str(entry.get("name", "")).strip()
            rid = entry.get("role_id")
            if not t_name or not rid:
                continue
            if t_name.lower() != text_lower:   # exact case-insensitive match on team name
                continue
            try:
                rid_int = int(rid)
            except Exception:
                continue
            r = guild.get_role(rid_int)
            if r:
                matched_role = r
                break

        if matched_role:
            return matched_role, matched_role.mention, matched_role.name

        # 5) Nothing matched: return the raw text as display + name, no ping
        return None, text, text

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return
        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message("This modal must be used in a text channel.", ephemeral=True)
            return

        team1_role, team1_mention, team1_name = self._resolve_team(guild, self.team1.value)
        team2_role, team2_mention, team2_name = self._resolve_team(guild, self.team2.value)

        stage_raw = self.week.value.strip()
        stage_l = stage_raw.lower()
        if "final" in stage_l:
            header = "# FINALS"
            special = True
        elif "semi" in stage_l:
            header = "# SEMIFINALS"
            special = True
        else:
            header = None
            special = False

        if special:
            content = (
                f"{header}\n"
                f"> Teams: {team1_mention} vs {team2_mention}\n"
                f"> Time: {self.time.value}\n"
                f"> Referee: \n"
                f"> Caster: "
            )
        else:
            content = (
                f"{team1_mention} vs {team2_mention}\n"
                f"Team staff must accept this match.\n"
                f"> WEEK: {self.week.value}\n"
                f"> Time: {self.time.value}\n"
                f"> Team 1: \n"
                f"> Team 2: "
            )

        view = TimeAcceptView(
            guild=guild,
            team1_role=team1_role,
            team2_role=team2_role,
            team1_name=team1_name,
            team2_name=team2_name,
            week=self.week.value,
            time=self.time.value,
        )

        try:
            sent = await channel.send(content, view=view)
            view.origin_message = sent
            await interaction.response.send_message("Match time request posted.", ephemeral=True)
        except Exception:
            await interaction.response.send_message("Failed to post match time (missing perms?).", ephemeral=True)


def resolve_team_any(guild: discord.Guild, raw: str) -> tuple[Optional[discord.Role], str, str]:
    text = raw.strip()

    if text.startswith("<@&") and text.endswith(">"):
        try:
            rid = int(text.strip("<@&>"))
            r = guild.get_role(rid)
            if r:
                return r, r.mention, r.name
        except Exception:
            pass

    try:
        rid = int(text)
        r = guild.get_role(rid)
        if r:
            return r, r.mention, r.name
    except Exception:
        pass

    r = (
        discord.utils.get(guild.roles, name=text)
        or discord.utils.find(lambda rr: rr.name.lower() == text.lower(), guild.roles)
    )
    if r:
        return r, r.mention, r.name

    try:
        teams = load_teams()
    except Exception:
        teams = []

    text_lower = text.lower()
    for entry in teams:
        t_name = str(entry.get("name", "")).strip()
        rid = entry.get("role_id")
        if not t_name or not rid:
            continue
        if t_name.lower() != text_lower:
            continue
        try:
            rid_int = int(rid)
        except Exception:
            continue
        r = guild.get_role(rid_int)
        if r:
            return r, r.mention, r.name

    return None, text, text


def generate_forced_time_string() -> str:
    """
    Generate a time string like '6/25/26 at 8PM EST'.
    """
    base = datetime.utcnow()
    delta_days = random.randint(1, 5)
    target = base + timedelta(days=delta_days)

    # format mm/dd/yy, strip leading zeros from month/day
    date_part = target.strftime("%m/%d/%y").lstrip("0").replace("/0", "/")
    return f"{date_part} at 8PM EST"





#---------------- say something command ----------------
class SaySomethingCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # ignore bots and DMs
        if message.author.bot or not message.guild:
            return

        content = message.content
        # support both prefixes
        prefixes = [".!saysmth", "!saysmth"]
        used = None
        for p in prefixes:
            if content.startswith(p):
                used = p
                break

        if used is None:
            return

        # glued form (e.g. .!saysmthhi / !saysmthhi) -> delete + DM error
        if len(content) > len(used) and content[len(used)] not in (" ", "\n"):
            if not message.author.guild_permissions.administrator:
                return
            try:
                await message.delete()
            except Exception:
                pass
            try:
                await message.author.send("Could not send the message.")
            except Exception:
                pass
            return

        # admin check
        if not message.author.guild_permissions.administrator:
            return

        # strip off the used command
        body = content[len(used):].lstrip()
        if not body:
            try:
                await message.author.send("You must provide a message after the command.")
            except Exception:
                pass
            return

        guild = message.guild

        # Optional (channel_id) at the end: .!saysmth hi (123456789012345678) or !saysmth hi (...)
        chan = message.channel
        import re as _re
        m = _re.search(r"\((\d{5,})\)\s*$", body)
        if m:
            chan_id = int(m.group(1))
            target = guild.get_channel(chan_id)
            if isinstance(target, (discord.TextChannel, discord.Thread)):
                chan = target
            body = body[:m.start()].rstrip()

        if not body:
            try:
                await message.author.send("You must provide a message to send.")
            except Exception:
                pass
            return

        # normalize @ everyone / @ here -> @everyone / @here
        body = _re.sub(r"@ ?everyone", "@everyone", body, flags=_re.IGNORECASE)
        body = _re.sub(r"@ ?here", "@here", body, flags=_re.IGNORECASE)

        # map textual role pings to real role mentions
        def replace_role_pings(text: str) -> str:
            # (pattern, role_id)
            patterns = [
                (r"@ ?head ?caster", HEAD_CASTER_ROLE_ID),
                (r"@ ?head ?ref(?:eree)?", HEAD_REF_ROLE_ID),
                (r"@ ?ref(?:eree)?", REF_ROLE_ID),
                (r"@ ?caster", CASTER_ROLE_ID),
            ]

            def _make_replacer(role_id: int):
                role = guild.get_role(role_id)
                # capture mention or keep original if role missing
                mention = role.mention if role else None

                def _repl(mo: _re.Match) -> str:
                    return mention or mo.group(0)
                return _repl

            for pat, rid in patterns:
                body_local = _re.sub(pat, _make_replacer(rid), text, flags=_re.IGNORECASE)
                text = body_local
            return text

        body = replace_role_pings(body)

        # send the message (pings work as normal)
        try:
            await chan.send(body, allowed_mentions=discord.AllowedMentions.all())
        except Exception:
            try:
                await message.author.send("Failed to send message (check bot permissions / channel ID).")
            except Exception:
                pass
            return

        # delete the original command message
        try:
            await message.delete()
        except Exception:
            pass

        # DM confirmation
        try:
            if chan.id != message.channel.id:
                await message.author.send(f"✅Message sent to {chan.mention}")
            else:
                await message.author.send("✅Message sent!")
        except Exception:
            pass



# ---------------- ForceTimeAutoWarnCog ----------------
class ForceTimeAutoWarnCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.check_channels.start()

    def cog_unload(self):
        self.check_channels.cancel()

    @tasks.loop(hours=1)
    async def check_channels(self):
        """
        Every hour:
        - Look for scheduling channels (name contains '-vs-').
        - If channel is older than FORCE_WARN_DAYS and not yet warned:
          * Send a warning message.
          * Mark topic with FORCE_WARN_MARKER (⚠️ by default).
          * Prefix the channel name with ⚠️ so it’s visually clear the bot is forcing/scheduling.
        """
        now = datetime.utcnow()

        for guild in self.bot.guilds:
            for ch in guild.text_channels:
                name = ch.name or ""
                topic = ch.topic or ""

                # Only consider scheduling-style channels: name contains "-vs-"
                if "-vs-" not in name.lower():
                    continue

                # Skip if already warned (marker in topic)
                if FORCE_WARN_MARKER in (topic or ""):
                    continue

                # Check age (UTC)
                created_utc = ch.created_at.replace(tzinfo=None)
                age_days = (now - created_utc).days
                if age_days < FORCE_WARN_DAYS:
                    continue

                # Try to get team names from topic: "Team1 Vs Team2"
                t1_name = None
                t2_name = None

                if topic and " Vs " in topic:
                    parts = topic.split(" Vs ", 1)
                    if len(parts) == 2:
                        t1_name = parts[0].strip()
                        t2_name = parts[1].strip()

                # If topic failed, fallback: parse from channel name "team1-vs-team2"
                if not t1_name or not t2_name:
                    lower_name = name.lower()
                    if "-vs-" in lower_name:
                        p1, p2 = lower_name.split("-vs-", 1)
                        t1_name = p1.replace("-", " ").strip()
                        t2_name = p2.replace("-", " ").strip()

                if not t1_name or not t2_name:
                    # Can't parse team names; skip this channel
                    continue

                # Resolve to roles or keep plain text
                t1_role, t1_mention, _ = resolve_team_any(guild, t1_name)
                t2_role, t2_mention, _ = resolve_team_any(guild, t2_name)

                # Build and send the warning message
                warn_msg = (
                    f"{t1_mention} {t2_mention} "
                    "You Have Ran Out Of Time To Schedule. A Time Has Been Forced, "
                    "Meaning If One Player From One Team Joins Before The 15 Minute Late Time, That Team Will Win."
                )
                try:
                    await ch.send(warn_msg)
                except Exception:
                    # If we can't send a message, don't try to edit name/topic either
                    continue

                # Mark as warned by updating topic
                new_topic = (topic or "").strip()
                if FORCE_WARN_MARKER not in new_topic:
                    new_topic = (new_topic + " " + FORCE_WARN_MARKER).strip()

                try:
                    await ch.edit(topic=new_topic, reason="Force-time auto warning sent")
                except Exception:
                    # Topic edit failed; continue with name attempt anyway
                    pass

                # Also prefix the channel name with the warning emoji so users know
                # that the bot had to step in and schedule/force this match.
                try:
                    old_name = ch.name or ""
                    if not old_name.startswith(FORCE_WARN_MARKER):
                        new_name = f"{FORCE_WARN_MARKER}{old_name}"
                        # Discord hard limit is 100 chars; trim if needed
                        if len(new_name) > 100:
                            new_name = new_name[:100]
                        await ch.edit(name=new_name, reason="Mark channel as force-time scheduled")
                except Exception:
                    # Best-effort; do not crash the loop
                    pass

    @check_channels.before_loop
    async def before_check_channels(self):
        await self.bot.wait_until_ready()




# ---------------- ForceTimeCog ----------------
class ForceTimeCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.guilds(Object(id=TEST_GUILD_ID))
    @app_commands.default_permissions(administrator=True)
    @app_commands.command(
        name="force-time",
        description="Force a match time between two teams (admins only).",
    )
    @app_commands.describe(
        team1="Team 1 (mention / name / id)",
        team2="Team 2 (mention / name / id)",
    )
    async def force_time(self, interaction: discord.Interaction, team1: str, team2: str):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return

        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You do not have permission to use this.", ephemeral=True)
            return

        # resolve teams
        t1_role, t1_mention, t1_name = resolve_team_any(guild, team1)
        t2_role, t2_mention, t2_name = resolve_team_any(guild, team2)

        if not t1_mention or not t2_mention:
            await interaction.response.send_message("Could not resolve one or both teams.", ephemeral=True)
            return

        # pick an initial forced time
        time_str = generate_forced_time_string()

        # staff review channel (fixed)
        review_ch = guild.get_channel(FORCE_TIME_REVIEW_CHANNEL_ID)
        if not isinstance(review_ch, discord.TextChannel):
            await interaction.response.send_message("Review channel is not configured correctly.", ephemeral=True)
            return

        view = ForceTimeView(
            team1_role=t1_role,
            team2_role=t2_role,
            team1_mention=t1_mention,
            team2_mention=t2_mention,
            team1_name=t1_name,
            team2_name=t2_name,
            time_str=time_str,
        )

        staff_message = view._build_staff_message(guild)

        try:
            await review_ch.send(staff_message, view=view)
        except Exception:
            await interaction.response.send_message("Failed to post review message.", ephemeral=True)
            return

        await interaction.response.send_message(
            f"Proposed forced time created for {t1_mention} vs {t2_mention} and sent to {review_ch.mention}.",
            ephemeral=True,
        )



# ---------------- Settings / Manage / Done / Roster / Info / AdminManage / FAQ+Bracket ----------------
class SettingsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.guilds(Object(id=TEST_GUILD_ID))
    @app_commands.default_permissions(administrator=True)
    @app_commands.command(name="settings", description="Open server settings panel (admins only)")
    async def settings(self, interaction: discord.Interaction):
        ch = CONFIG.get("channels", {})
        rl = CONFIG.get("roles", {})
        rr = CONFIG.get("roster_rules", {})

        def ch_display(key):
            v = ch.get(key)
            return f"<#{v}>" if v else "Not set"

        def role_display(key):
            v = rl.get(key)
            return f"<@&{v}>" if v else "Not set"

        embed = discord.Embed(title="League Settings", color=discord.Color.green())
        embed.description = "Use the buttons to open the settings sections."
        channels_value = (
            f"Transactions: {ch_display('transactions')}\n"
            f"FAQ: {ch_display('faq')}\n"
            f"Match Score: {ch_display('submit_score')}\n"
            f"Match Time: {ch_display('submit_time')}\n"
            f"Scheduling: {ch_display('scheduling')}\n"
            f"Assignments: {ch_display('assignments')}"
        )
        roles_value = (
            f"Captain: {role_display('captain')}\n"
            f"Co-Captain: {role_display('co_captain')}\n"
            f"Executive: {role_display('executive')}\n"
            f"Team Member: {role_display('team_member')}\n"
            f"Caster: {role_display('caster')}\n"
            f"Referee: {role_display('referee')}"
        )
        roster_value = (
            f"Max Roster Size: {rr.get('max_roster', 12)}\n"
            f"Max Co-Captains: {rr.get('max_co_captains', 2)}\n"
            f"Max Executive: {rr.get('max_executive', 1)}"
        )
        embed.add_field(name="📡 Channels", value=channels_value, inline=False)
        embed.add_field(name="🎭 Roles", value=roles_value, inline=False)
        embed.add_field(name="👩🏻‍👦🏽 Roster Rules", value=roster_value, inline=False)
        view = MainSettingsView()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class ManageTeam(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.guilds(Object(id=TEST_GUILD_ID))
    @app_commands.command(name="manage-team", description="View and manage your team roster.")
    async def manage_team(self, interaction: discord.Interaction):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return

        member = interaction.user

        # Use the new, more robust helper
        team_role = find_member_team_role(member)
        if team_role is None:
            await interaction.response.send_message("You are not on a team.", ephemeral=True)
            return

        data = await get_team_data(team_role, guild)

        max_roster = CONFIG.get("roster_rules", {}).get("max_roster", 12)
        embed_color = team_role.colour if getattr(team_role, "colour", None) else discord.Color.blurple()
        embed = discord.Embed(
            title=f"Roster for {data['name']}",
            description="Team roster",
            color=embed_color,
        )

        embed.add_field(
            name="Team Executive",
            value=format_list_arrow([data["executive"]]),
            inline=False,
        )
        embed.add_field(
            name="Captain",
            value=format_list_arrow([data["captain"]]),
            inline=False,
        )
        embed.add_field(
            name="Co-Captains",
            value=format_list_arrow([m.mention for m in data.get("co_captains", [])]),
            inline=False,
        )

        players = data.get("players", [])
        player_mentions = [p.mention for p in players[:max_roster]]
        embed.add_field(
            name="Players",
            value=format_list_arrow(player_mentions),
            inline=False,
        )
        embed.add_field(
            name="\u200b",
            value=f"{len(players)}/{max_roster}",
            inline=False,
        )

        pending = data.get("pending_invites", [])
        pending_text = ", ".join(str(x) for x in pending) if pending else "None"
        embed.add_field(
            name="Pending invites",
            value=pending_text,
            inline=False,
        )

        embed.set_footer(text=team_role.name)

        can_captain = has_role_id(member, CAPTAIN_ROLE_ID)
        can_co_captain = has_role_id(member, CO_CAPTAIN_ROLE_ID)

        view = None
        if can_captain or can_co_captain:
            view = ManageTeamView(
                team_role=team_role,
                can_captain=can_captain,
                can_co_captain=can_co_captain,
                players=players,
                invoker_id=member.id,
                roster_locked=ROSTER_LOCKED,
                admin_override=False,
            )
            # start with action buttons disabled until a member is selected
            if not (ROSTER_LOCKED and not view.admin_override):
                view._set_action_buttons_enabled(False)

        if view is not None:
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)


class DoneCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _extract_teams_from_channel(self, ch: discord.TextChannel) -> tuple[Optional[str], Optional[str]]:
        """
        Try to get 'Team1' and 'Team2' from channel name/topic like 'team1-vs-team2'
        or topic 'Team1 Vs Team2'.
        """
        name = ch.name or ""
        topic = ch.topic or ""

        # Try topic "Team1 Vs Team2"
        if topic and " Vs " in topic:
            parts = topic.split(" Vs ", 1)
            if len(parts) == 2:
                return parts[0].strip(), parts[1].strip()

        # Fallback: channel name "team1-vs-team2"
        lower_name = name.lower()
        if "-vs-" in lower_name:
            p1, p2 = lower_name.split("-vs-", 1)
            t1 = p1.replace("-", " ").strip()
            t2 = p2.replace("-", " ").strip()
            return t1 or None, t2 or None

        return None, None

    @app_commands.guilds(Object(id=TEST_GUILD_ID))
    @app_commands.default_permissions(administrator=True)
    @app_commands.command(name="done", description="Mark match done and lock channel")
    @app_commands.describe(winner="Winner (team name or any text)")
    async def done(self, interaction: discord.Interaction, winner: str):
        ch = interaction.channel
        guild = interaction.guild
        if not isinstance(ch, discord.TextChannel) or guild is None:
            await interaction.response.send_message("Use this in a server text channel.", ephemeral=True)
            return

        # 1) Post the winner message
        try:
            await ch.send(f"# {winner} Won")
        except Exception:
            pass

        # 2) Figure out team roles from channel
        t1_name, t2_name = self._extract_teams_from_channel(ch)
        t1_role = t2_role = None
        if t1_name or t2_name:
            try:
                if t1_name:
                    t1_role, _, _ = resolve_team_any(guild, t1_name)
                if t2_name:
                    t2_role, _, _ = resolve_team_any(guild, t2_name)
            except Exception:
                t1_role = t2_role = None

        # 3) Build / enforce private permissions
        # @everyone: no view, no send
        try:
            await ch.set_permissions(
                guild.default_role,
                view_channel=False,
                send_messages=False,
                reason="Match finished (/done) - keep channel private",
            )
        except Exception:
            pass

        # allow staff roles to view (read-only)
        for rid in (HEAD_REF_ROLE_ID, REF_ROLE_ID, HEAD_CASTER_ROLE_ID, CASTER_ROLE_ID):
            r = guild.get_role(rid)
            if r:
                try:
                    await ch.set_permissions(r, view_channel=True, send_messages=None)
                except Exception:
                    pass

        # ensure both team roles can still see, but cannot send
        for team_role in (t1_role, t2_role):
            if isinstance(team_role, discord.Role):
                try:
                    await ch.set_permissions(team_role, view_channel=True, send_messages=False, reason="Match finished (/done)")
                except Exception:
                    pass

        # 4) Rename the channel to add ✅ in front (e.g. '✅team1-vs-team2')
        try:
            old_name = ch.name or ""
            base_name = old_name

            # If it already starts with ✅, don't duplicate
            if base_name.startswith("✅"):
                base_name = base_name.lstrip("✅").lstrip("-")

            new_name = f"✅{base_name}"
            await ch.edit(name=new_name, reason=f"Match finished via /done by {interaction.user}")
        except Exception:
            pass

        await interaction.response.send_message("Result posted, channel locked, and kept private.", ephemeral=True)


class RosterCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.guilds(Object(id=TEST_GUILD_ID))
    @app_commands.command(name="roster", description="Show a team's roster.")
    async def roster(self, interaction: discord.Interaction):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        # build list of candidate team roles from teams.json
        roles: list[discord.Role] = []
        teams_data = load_teams()
        for entry in teams_data:
            rid = entry.get("role_id")
            if not rid:
                continue
            try:
                rid_int = int(rid)
            except Exception:
                continue
            r = guild.get_role(rid_int)
            if r and not r.is_default() and not r.managed and is_team_role(guild, r):
                roles.append(r)

        if not roles:
            await interaction.followup.send("No teams found.", ephemeral=True)
            return

        max_roster = CONFIG.get("roster_rules", {}).get("max_roster", 12)

        async def build_embed_for_role(role: discord.Role) -> discord.Embed:
            data = await get_team_data(role, guild)
            embed_color = role.colour if getattr(role, "colour", None) else discord.Color.dark_green()
            embed = discord.Embed(
                title=f"Roster for {data['name']}",
                description="Team roster",
                color=embed_color,
            )

            embed.add_field(
                name="Team Executive",
                value=format_list_arrow([data["executive"]]),
                inline=False,
            )
            embed.add_field(
                name="Captain",
                value=format_list_arrow([data["captain"]]),
                inline=False,
            )
            embed.add_field(
                name="Co-Captains",
                value=format_list_arrow([m.mention for m in data.get("co_captains", [])]),
                inline=False,
            )

            players = data.get("players", [])
            player_mentions = [p.mention for p in players[:max_roster]]
            embed.add_field(
                name="Players",
                value=format_list_arrow(player_mentions),
                inline=False,
            )
            embed.add_field(
                name="\u200b",
                value=f"{len(players)}/{max_roster}",
                inline=False,
            )

            pending = data.get("pending_invites", [])
            pending_text = ", ".join(str(x) for x in pending) if pending else "None"
            embed.add_field(
                name="Pending invites",
                value=pending_text,
                inline=False,
            )

            embed.set_footer(text=role.name)
            return embed

        options = [discord.SelectOption(label=r.name, value=str(r.id)) for r in roles][:25]
        select = discord.ui.Select(
            placeholder="Select a team to view its roster",
            options=options,
            min_values=1,
            max_values=1,
        )
        view = discord.ui.View(timeout=120)
        view.add_item(select)

        async def sel_cb(sel_int: discord.Interaction):
            try:
                sel_role_id = int(sel_int.data["values"][0])
            except Exception:
                await sel_int.response.send_message("Invalid selection.", ephemeral=True)
                return

            sel_role = guild.get_role(sel_role_id)
            if not sel_role:
                await sel_int.response.send_message("Role not found.", ephemeral=True)
                return

            embed = await build_embed_for_role(sel_role)

            try:
                await sel_int.response.edit_message(embed=embed, view=view)
            except Exception:
                await sel_int.response.send_message(embed=embed, ephemeral=True)

        select.callback = sel_cb

        # if the requester is on a team, put their team first in dropdown
        requester = guild.get_member(interaction.user.id)
        requester_team = get_user_team_role(requester) if requester else None
        if requester_team:
            options_sorted = sorted(
                options,
                key=lambda o: (0 if o.value == str(requester_team.id) else 1, o.label.lower()),
            )
            select.options = options_sorted

        prompt_embed = discord.Embed(
            title="Pick a team",
            description="Select a team from the dropdown to view its roster.",
            color=discord.Color.dark_green(),
        )

        await interaction.followup.send(embed=prompt_embed, view=view, ephemeral=True)


from discord import app_commands

class AdminManage(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _list_team_roles(self, guild: discord.Guild) -> list[discord.Role]:
        """Return only team roles that are in teams.json and still exist."""
        roles: list[discord.Role] = []
        teams_data = load_teams()
        for entry in teams_data:
            rid = entry.get("role_id")
            if not rid:
                continue
            try:
                rid_int = int(rid)
            except ValueError:
                continue
            r = guild.get_role(rid_int)
            if r and not r.is_default() and not r.managed:
                roles.append(r)
        roles.sort(key=lambda r: (-r.position, r.name.lower()))
        return roles

    async def _autocomplete_team(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        guild = interaction.guild
        if guild is None:
            return []

        roles = self._list_team_roles(guild)
        current_l = (current or "").lower()
        choices: list[app_commands.Choice[str]] = []

        for r in roles:
            name = r.name
            if not current_l or current_l in name.lower():
                choices.append(app_commands.Choice(name=name, value=name))
                if len(choices) >= 25:
                    break

        return choices

    @app_commands.guilds(Object(id=TEST_GUILD_ID))
    @app_commands.default_permissions(administrator=True)
    @app_commands.command(name="admin-manage", description="Admin: view/manage a team by name")
    @app_commands.describe(team_name="Team name")
    @app_commands.autocomplete(team_name=_autocomplete_team)
    async def admin_manage(self, interaction: discord.Interaction, team_name: str):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You do not have permission to use this.", ephemeral=True)
            return

        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return

        role = discord.utils.get(guild.roles, name=team_name) or discord.utils.find(lambda r: r.name.lower() == team_name.lower(), guild.roles)
        if role is None:
            teams = load_teams()
            for entry in teams:
                if entry.get("name", "").lower() == team_name.lower():
                    rid = entry.get("role_id")
                    try:
                        role = guild.get_role(int(rid)) if rid else None
                    except Exception:
                        role = None
                    if role:
                        break
        if role is None:
            await interaction.response.send_message("Team not found. Try selecting from the autocomplete options.", ephemeral=True)
            return

        data = await get_team_data(role, guild)

        embed_color = role.colour if getattr(role, "colour", None) else discord.Color.blurple()
        embed = discord.Embed(title=f"Roster for {data['name']}", description="Team roster (admin view)", color=embed_color)

        embed.add_field(name="Team Executive", value=format_list_arrow([data["executive"]]), inline=False)
        embed.add_field(name="Captain", value=format_list_arrow([data["captain"]]), inline=False)
        embed.add_field(name="Co-Captains", value=format_list_arrow(data.get("co_captains", [])), inline=False)

        players = data.get("players", [])
        player_mentions = [p.mention for p in players[:12]]
        embed.add_field(name="Players", value=format_list_arrow(player_mentions), inline=False)

        pending = data.get("pending_invites", [])
        pending_text = ", ".join(str(x) for x in pending) if pending else "None"
        embed.add_field(name="Pending invites", value=pending_text, inline=False)
        embed.add_field(name="\u200b", value=f"{len(players)}/12", inline=False)

        view = ManageTeamView(
            team_role=role,
            can_captain=True,
            can_co_captain=True,
            players=players,
            invoker_id=None,
            roster_locked=ROSTER_LOCKED,
            admin_override=True,
        )

        # start with action buttons disabled until selection (admin can still use them once enabled)
        view._set_action_buttons_enabled(False)

        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)




class InfoCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.guilds(Object(id=TEST_GUILD_ID))
    @app_commands.command(name="info", description="General commands available to users")
    async def info(self, interaction: discord.Interaction):
        embed = discord.Embed(title="Public Commands", color=discord.Color.blurple())
        embed.add_field(name="/manage-team", value="View/manage your team (players, co-captains, captains, executives)", inline=False)
        embed.add_field(name="/standing", value="View standings (everyone) (only when seeding is enabled)", inline=False)
        embed.add_field(name="/roster", value="Show a team's roster (everyone)", inline=False)
        embed.add_field(name="/list-teams", value="List all teams (everyone)", inline=False)
        embed.add_field(name="/player-info", value="View current and past teams (everyone)", inline=False)
        embed.add_field(name="/info", value="Shows this info (everyone)", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.guilds(Object(id=TEST_GUILD_ID))
    @app_commands.default_permissions(administrator=True)
    @app_commands.command(name="admin-info", description="Admin-only command list")
    async def admin_info(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You do not have permission to use this.", ephemeral=True)
            return
        embed = discord.Embed(title="Admin Commands", color=discord.Color.green())
        embed.add_field(name="/admin-panel", value="Open the admin panel with buttons for team/scrim tools.", inline=False)
        embed.add_field(name="/settings", value="Open server settings (channels, roles, roster rules).(Comming soon)", inline=False)
        embed.add_field(name="/done", value="Mark a match done, lock the channel, and rename it.", inline=False)
        embed.add_field(name="/admin-manage", value="Admin manage teams", inline=False)
        embed.add_field(name="/start-seeding", value="Enable /standing", inline=False)
        embed.add_field(name="/end-seeding", value="Disable /standing", inline=False)
        embed.add_field(name="/delete-scheduling", value="Delete all scheduling channels (name contains -vs-)", inline=False)
        embed.add_field(name="/force-time", value="Propose a forced match time between two teams.", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.guilds(Object(id=TEST_GUILD_ID))
    @app_commands.command(name="list-teams", description="List all teams (everyone).")
    async def list_teams(self, interaction: discord.Interaction):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Must be used in a server.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        data = load_teams()
        if not data:
            await interaction.followup.send("No teams found.", ephemeral=True)
            return

        seen_roles: set[int] = set()
        lines = ["Below is a list of teams:\n"]

        for entry in data:
            rid = entry.get("role_id")
            name = entry.get("name", "Unknown Team")
            if not rid:
                continue
            try:
                rid_int = int(rid)
            except ValueError:
                continue
            if rid_int in seen_roles:
                continue
            seen_roles.add(rid_int)

            role = guild.get_role(rid_int)
            if role:
                if not is_team_role(guild, role):
                    continue
                lines.append(f"> {role.mention} ({role.name})")
            else:
                lines.append(f"> {name} (role not found)")

        if len(lines) == 1:
            await interaction.followup.send("No valid teams found.", ephemeral=True)
            return

        await interaction.followup.send("\n".join(lines), ephemeral=True)

    @app_commands.guilds(Object(id=TEST_GUILD_ID))
    @app_commands.command(
        name="player-info",
        description="View a player's league information (current and past teams).",
    )
    @app_commands.describe(member="The player to look up (leave empty to view yourself)")
    async def player_info(self, interaction: discord.Interaction, member: discord.Member | None = None):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Must be used in a server.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        if member is None:
            member = guild.get_member(interaction.user.id)

        current_team_role = find_single_team_for_member(guild, member)
        current_team_mention = current_team_role.mention if current_team_role else "None"

        history = load_player_history()
        entry = history.get(str(member.id), {})
        past = entry.get("past_teams", [])

        if current_team_role is None and not past:
            await interaction.followup.send(
                f"{member.mention} does not have any league information!",
                ephemeral=True,
            )
            return

        lines = [
            f"# League Information for {member.mention}:\n",
            f"Current Team: {current_team_mention}",
            "Past Teams:",
        ]
        if past:
            for name in past:
                lines.append(f"> {name}")
        else:
            lines.append("> None")

        await interaction.followup.send("\n".join(lines), ephemeral=True)


class BracketAdmin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.guilds(Object(id=TEST_GUILD_ID))
    @app_commands.default_permissions(administrator=True)
    @app_commands.command(
        name="upload-bracket",
        description="Upload the base bracket image to be used by /bracket (admin only)."
    )
    @app_commands.describe(image="PNG/JPG base bracket image")
    async def upload_bracket(self, interaction: discord.Interaction, image: discord.Attachment):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You do not have permission.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        if image is None:
            await interaction.followup.send("No attachment provided.", ephemeral=True)
            return

        fname = image.filename or "bracket.png"
        if not any(fname.lower().endswith(ext) for ext in (".png", ".jpg", ".jpeg")):
            await interaction.followup.send("Please upload a PNG or JPG image.", ephemeral=True)
            return

        try:
            data = await image.read()
            with open(BRACKET_BASE_IMAGE_PATH, "wb") as f:
                f.write(data)
        except Exception as e:
            await interaction.followup.send(f"Failed to save image: {e}", ephemeral=True)
            return

        # Resolve bracket channel
        bracket_ch = None
        if BRACKET_CHANNEL_ID and interaction.guild:
            bracket_ch = interaction.guild.get_channel(BRACKET_CHANNEL_ID)

        if not isinstance(bracket_ch, discord.TextChannel):
            await interaction.followup.send(f"Saved `{BRACKET_BASE_IMAGE_PATH}` but bracket channel not found or invalid.", ephemeral=True)
            return

        basename = os.path.basename(BRACKET_BASE_IMAGE_PATH)
        basename_lower = basename.lower()

        # normalization helper: remove spaces/underscores/dashes and lowercase
        def _norm(s: str) -> str:
            return re.sub(r"[\s_-]+", "", (s or "").lower())

        norm_basename = _norm(basename)

        # get bot member and perms
        try:
            bot_member = interaction.guild.me or await interaction.guild.fetch_member(self.bot.user.id)
        except Exception:
            bot_member = interaction.guild.me
        perms = bracket_ch.permissions_for(bot_member) if bot_member else discord.Permissions.none()
        can_read = bool(perms.read_message_history)
        can_manage = bool(perms.manage_messages)

        found_filenames = []
        deleted_count = 0
        failed_deletes = []

        if can_read:
            try:
                async for msg in bracket_ch.history(limit=1000):
                    if not msg or not msg.attachments:
                        continue
                    if not msg.author or msg.author.id != self.bot.user.id:
                        continue
                    for att in msg.attachments:
                        fn = (att.filename or "").strip()
                        if not fn:
                            continue
                        found_filenames.append(fn)
                        norm_fn = _norm(fn)
                        # match if normalized names overlap (handles spaces/underscores/dashes and suffixes)
                        if norm_basename in norm_fn or norm_fn in norm_basename:
                            if can_manage:
                                try:
                                    await msg.delete()
                                    deleted_count += 1
                                except Exception as ex:
                                    failed_deletes.append((msg.id, str(ex)))
                            else:
                                failed_deletes.append((msg.id, "missing manage_messages"))
                            break
            except Exception as ex:
                failed_deletes.append(("history_scan", str(ex)))

        # post new file
        posted = False
        post_error = None
        try:
            with open(BRACKET_BASE_IMAGE_PATH, "rb") as f:
                file = discord.File(f, filename=basename)
                await bracket_ch.send(file=file)
            posted = True
        except Exception as ex:
            post_error = str(ex)

        # send detailed debug (including filenames found)
        summary = [
            f"Saved `{BRACKET_BASE_IMAGE_PATH}`.",
            f"Bracket channel: #{bracket_ch.name} (id: {bracket_ch.id})",
            f"Permissions: read_history={can_read} manage_messages={can_manage}",
            f"Found bot attachments checked: {len(found_filenames)}",
            f"Deleted messages: {deleted_count}",
            f"Failed deletes: {len(failed_deletes)}",
        ]
        if found_filenames:
            sample = found_filenames[:50]
            summary.append(f"Filenames found (sample up to 50): {sample}")
        if failed_deletes:
            sample_f = failed_deletes[:10]
            summary.append(f"Delete failures (sample up to 10): {sample_f}")
        if not posted:
            summary.append(f"Failed to post new file: {post_error}")

        await interaction.followup.send("\n".join(summary), ephemeral=True)

# ------------------------------ Auto-disband losing teams in single elimination -----------------------
SINGLE_ELIM = False  # set True for this season

class AutoDisbandScrim(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.channel.id != MATCH_SCORE_CHANNEL_ID:
            return
        if not globals().get("SINGLE_ELIM", False):
            return

        content = (message.content or "").strip()
        if not content:
            return

        lines = [ln.strip() for ln in content.splitlines() if ln.strip()]
        winner_name = None
        loser_name = None
        for ln in lines:
            ln_clean = ln.lstrip("> ").strip()
            lower = ln_clean.lower()
            if lower.startswith("winner:"):
                winner_name = ln_clean.split(":", 1)[1].strip()
            elif lower.startswith("loser:"):
                loser_name = ln_clean.split(":", 1)[1].strip()

        if not loser_name:
            return

        guild = message.guild
        if guild is None:
            return

        # Resolve loser to a role
        loser_role = None
        raw = loser_name
        if raw.startswith("<@&") and raw.endswith(">"):
            try:
                rid = int(raw.strip("<@&>"))
                loser_role = guild.get_role(rid)
            except Exception:
                loser_role = None

        if loser_role is None:
            try:
                rid = int(raw)
                loser_role = guild.get_role(rid)
            except Exception:
                loser_role = None

        if loser_role is None:
            r = discord.utils.get(guild.roles, name=raw) or discord.utils.find(lambda rr: rr.name.lower() == raw.lower(), guild.roles)
            if r:
                loser_role = r

        if loser_role is None:
            teams = load_teams()
            for entry in teams:
                if entry.get("name", "").lower() == raw.lower():
                    rid = entry.get("role_id")
                    try:
                        rid_int = int(rid)
                        r = guild.get_role(rid_int)
                        if r:
                            loser_role = r
                            break
                    except Exception:
                        continue

        if loser_role is None:
            return

        # Safety: don't disband protected roles
        protected = {
            CAPTAIN_ROLE_ID, CO_CAPTAIN_ROLE_ID, TEAM_PLAYER_ROLE_ID, TEAM_EXEC_ROLE_ID,
            HEAD_REF_ROLE_ID, REF_ROLE_ID, HEAD_CASTER_ROLE_ID, CASTER_ROLE_ID,
        }
        if loser_role.id in protected or loser_role.is_default() or loser_role.managed:
            return

        tx_ch = guild.get_channel(TRANSACTIONS_CHANNEL_ID)

        try:
            removed_members = 0
            # Prepare global role objects once
            cap_role = guild.get_role(CAPTAIN_ROLE_ID)
            co_role = guild.get_role(CO_CAPTAIN_ROLE_ID)
            exec_role = guild.get_role(TEAM_EXEC_ROLE_ID)
            player_role = guild.get_role(TEAM_PLAYER_ROLE_ID)

            for m in list(guild.members):
                if m.bot:
                    continue
                if loser_role in m.roles:
                    roles_to_remove = [loser_role]
                    # remove global roles if present on this member
                    for r in (cap_role, co_role, exec_role, player_role):
                        if r and r in m.roles:
                            roles_to_remove.append(r)
                    try:
                        await m.remove_roles(*roles_to_remove, reason="Auto-disband (single elimination)")
                        removed_members += 1
                    except Exception:
                        pass

            # delete the role itself
            try:
                await loser_role.delete(reason="Auto-disband (single elimination)")
            except Exception:
                pass

            # send transaction message
            if isinstance(tx_ch, discord.TextChannel):
                try:
                    await tx_ch.send(f"# {loser_role.name} HAS BEEN DISBANDED\n\n")
                except Exception:
                    pass

        except Exception:
            return





class ServerStatsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # cache: guild_id -> (category_id, member_ch_id, team_ch_id, online_ch_id)
        self._cache: dict[int, tuple[int, int, int, int]] = {}
        self.update_stats_task.start()

    def cog_unload(self):
        self.update_stats_task.cancel()

    async def _ensure_structure(self, guild: discord.Guild):
        """
        Create (if missing) the stats category and the three channels:
        - 👥 | MEMBERS: N
        - 🛡️ | TEAMS: N
        - 🟢 | ONLINE: N
        Then cache their IDs.
        """
        cat_name = "📊 SERVER STATS 📊"
        member_prefix = "👥 | MEMBERS"
        team_prefix = "🛡️ | TEAMS"
        online_prefix = "🟢 | ONLINE"

        category = discord.utils.get(guild.categories, name=cat_name)
        if category is None:
            category = await guild.create_category_channel(
                cat_name,
                reason="Create server stats category",
            )

        # best-effort: put category at top
        try:
            await category.edit(position=0)
        except Exception:
            pass

        # STRONG read-only overwrites
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(
                view_channel=False,
                send_messages=False,
                send_messages_in_threads=False,
                create_public_threads=False,
                create_private_threads=False,
                add_reactions=False,
                connect=False,
                speak=False,
            )
        }

        # member stats channel
        member_ch = discord.utils.find(
            lambda c: isinstance(c, discord.TextChannel) and c.name.startswith(member_prefix),
            category.channels,
        )
        if member_ch is None:
            member_ch = await guild.create_text_channel(
                f"{member_prefix}: 0",
                category=category,
                overwrites=overwrites,
                reason="Create member stats channel",
            )

        # team stats channel
        team_ch = discord.utils.find(
            lambda c: isinstance(c, discord.TextChannel) and c.name.startswith(team_prefix),
            category.channels,
        )
        if team_ch is None:
            team_ch = await guild.create_text_channel(
                f"{team_prefix}: 0",
                category=category,
                overwrites=overwrites,
                reason="Create team stats channel",
            )

        # online members channel
        online_ch = discord.utils.find(
            lambda c: isinstance(c, discord.TextChannel) and c.name.startswith(online_prefix),
            category.channels,
        )
        if online_ch is None:
            online_ch = await guild.create_text_channel(
                f"{online_prefix}: 0",
                category=category,
                overwrites=overwrites,
                reason="Create online members stats channel",
            )

        # enforce overwrites best-effort
        for ch in (member_ch, team_ch, online_ch):
            try:
                await ch.edit(overwrites=overwrites, category=category)
            except Exception:
                pass

        self._cache[guild.id] = (category.id, member_ch.id, team_ch.id, online_ch.id)

    async def _compute_team_count_from_transactions(self, guild: discord.Guild) -> int:
        """
        Count unique team roles by reading the transactions channel and
        looking for 'New Team Created!' logs with role mentions.
        """
        ch = guild.get_channel(TRANSACTIONS_CHANNEL_ID)
        if not isinstance(ch, discord.TextChannel):
            return 0

        seen_role_ids: set[int] = set()

        try:
            async for msg in ch.history(limit=500):
                if msg.author != self.bot.user:
                    continue
                if "New Team Created!" not in (msg.content or ""):
                    continue

                for role in msg.role_mentions:
                    if role and not role.is_default() and not role.managed:
                        seen_role_ids.add(role.id)
        except Exception:
            pass

        valid_count = 0
        for rid in seen_role_ids:
            if guild.get_role(rid) is not None:
                valid_count += 1

        return valid_count

    def _compute_online_count(self, guild: discord.Guild) -> int:
        """
        Count online members (including bots) using presence.
        Requires INTENTS.presences = True and presence intent enabled.
        """
        online_statuses = {
            discord.Status.online,
            discord.Status.idle,
            discord.Status.dnd,
        }
        count = 0
        for m in guild.members:
            if getattr(m, "status", discord.Status.offline) in online_statuses:
                count += 1
        return count

    async def _update_names(self, guild: discord.Guild):
        """Only renames the three channels. Does NOT create anything."""
        ids = self._cache.get(guild.id)
        if not ids:
            return
        _, member_id, team_id, online_id = ids

        member_ch = guild.get_channel(member_id)
        team_ch = guild.get_channel(team_id)
        online_ch = guild.get_channel(online_id)

        if not isinstance(member_ch, discord.TextChannel):
            return
        if not isinstance(team_ch, discord.TextChannel):
            return
        if not isinstance(online_ch, discord.TextChannel):
            return

        # member count
        member_count = guild.member_count or 0
        cache_count = len(guild.members)
        if cache_count > member_count:
            member_count = cache_count

        # team count from transactions channel
        valid_team_count = await self._compute_team_count_from_transactions(guild)

        # online (non-bot) members
        online_count = self._compute_online_count(guild)

        desired_member_name = f"👥 | MEMBERS: {member_count}"
        desired_team_name = f"🛡️ | TEAMS: {valid_team_count}"
        desired_online_name = f"🟢 | ONLINE: {online_count}"

        me = guild.me
        if not me or not me.guild_permissions.manage_channels:
            return

        try:
            if member_ch.name != desired_member_name:
                await member_ch.edit(name=desired_member_name)
        except Exception:
            pass

        try:
            if team_ch.name != desired_team_name:
                await team_ch.edit(name=desired_team_name)
        except Exception:
            pass

        try:
            if online_ch.name != desired_online_name:
                await online_ch.edit(name=desired_online_name)
        except Exception:
            pass

    @tasks.loop(minutes=1)
    async def update_stats_task(self):
        await self.bot.wait_until_ready()
        for g in self.bot.guilds:
            if g.id not in self._cache:
                try:
                    await self._ensure_structure(g)
                except Exception:
                    continue
            try:
                await self._update_names(g)
            except Exception:
                continue

    @update_stats_task.before_loop
    async def before_update_stats(self):
        await self.bot.wait_until_ready()
        for g in self.bot.guilds:
            try:
                await self._ensure_structure(g)
            except Exception:
                continue

    async def update_now(self):
        """Immediately update stats for all guilds (can be called after team changes)."""
        await self.bot.wait_until_ready()
        for g in self.bot.guilds:
            if g.id not in self._cache:
                try:
                    await self._ensure_structure(g)
                except Exception:
                    continue
            try:
                await self._update_names(g)
            except Exception:
                continue




# --------------------  CommandGuideCog ----------------------
class CommandGuideCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._posted_once = False  # avoid running twice per process

    @commands.Cog.listener()
    async def on_ready(self):
        # run only once per bot process
        if self._posted_once:
            return
        self._posted_once = True

        for guild in self.bot.guilds:
            ch = guild.get_channel(TRANSACTIONS_HELP_CHANNEL_ID)
            if not isinstance(ch, discord.TextChannel):
                continue

            # Check if the guide is already there
            already = False
            try:
                async for msg in ch.history(limit=200):
                    if msg.author.id != self.bot.user.id:
                        continue
                    if not msg.embeds:
                        continue
                    emb = msg.embeds[0]
                    if (emb.title or "").strip().lower() == "mmm command guide":
                        already = True
                        break
            except Exception:
                continue

            if already:
                continue

            # Build the guide embed (blue)
            embed = discord.Embed(
                title="PGL Command Guide",
                description="What every command does and who can use it:",
                color=discord.Color.blue(),
            )

            # 👤 Everyone
            everyone_value = (
                "/info - Shows this list and basic info.\n"
                "/roster - Shows your team’s roster (or a default team).\n"
                "/manage-team - View your team roster; captains/co-caps can manage it.\n"
                "/standing - View league standings (only when seeding is enabled).\n"
                "/list-teams - Lists all registered teams.\n"
                "/player-info - Shows a player's current team and past teams.\n"
            )
            embed.add_field(name="👤 Everyone", value=everyone_value, inline=False)

            # 👑 Captains & Co-Captains
            cc_value = (
                "/manage-team - Use the buttons to:\n"
                "• Invite players to your team.\n"
                "• Kick players from your team.\n"
                "• Promote players to Co-Captain.\n"
                "• Assign a Team Executive.\n"
                "• Transfer Captain to another staff member.\n"
                "• Disband your team.\n"
            )
            embed.add_field(name="👑 Captains & Co-Captains", value=cc_value, inline=False)

            # 🔧 Administrators
            admin_value = (
                "/admin-panel - Open the admin panel with buttons for team/scrim tools.\n"
                "/settings - View league settings (channels, roles, roster rules).(Comming soon)\n"
                "/admin-manage - Admin view/manage any team roster.\n"
                "/done - Mark a match done, lock the channel, and rename it.\n"
                "/start-seeding - Enable standings and seeding logic.\n"
                "/end-seeding - Disable standings and end seeding.\n"
                "/delete-scheduling - Delete all scheduling channels (-vs-).\n"
                "/force-time - Propose a forced match time between two teams.\n"
            )
            embed.add_field(name="🔧 Administrators", value=admin_value, inline=False)

            # 🧰 Staff / Utility (message-based)
            staff_value = (
                ".!saysmth / !saysmth - Admin-only utility to send a message (with pings) "
                "to any channel by ID.\n"
            )
            embed.add_field(name="🧰 Staff Utility", value=staff_value, inline=False)

            embed.set_footer(text="PGL Season Management System")

            try:
                await ch.send(embed=embed)
            except Exception:
                continue


class TeamRoleAutoOrderCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._task.start()

    def cog_unload(self):
        self._task.cancel()

    def _get_team_roles(self, guild: discord.Guild) -> list[discord.Role]:
        """
        Return all team roles that should be auto‑ordered, based on teams.json.

        For each entry:
        - Try to resolve by role_id.
        - If that fails, fall back to resolving by name (case‑insensitive).
        """
        roles: list[discord.Role] = []
        seen_ids: set[int] = set()

        try:
            teams = load_teams()
        except Exception:
            teams = []

        for entry in teams:
            rid = entry.get("role_id")
            name = (entry.get("name") or "").strip()
            role: discord.Role | None = None

            # 1) Try by ID
            if rid is not None:
                try:
                    rid_int = int(rid)
                except (TypeError, ValueError):
                    print(f"[TeamRoleAutoOrder] Invalid role_id in teams.json: {rid!r}")
                    rid_int = None

                if rid_int is not None:
                    r = guild.get_role(rid_int)
                    if r is None:
                        print(f"[TeamRoleAutoOrder] Role id {rid_int} not found in guild {guild.id}")
                    else:
                        role = r

            # 2) If not found by ID, try by name
            if role is None and name:
                r = (
                    discord.utils.get(guild.roles, name=name)
                    or discord.utils.find(lambda rr: rr.name.lower() == name.lower(), guild.roles)
                )
                if r:
                    print(f"[TeamRoleAutoOrder] Matched team '{name}' by name to role id {r.id}")
                    role = r

            if role is None:
                continue
            if role.is_default() or role.managed:
                print(f"[TeamRoleAutoOrder] Skipping managed/default role {role} ({role.id})")
                continue
            if role.id in seen_ids:
                continue

            seen_ids.add(role.id)
            roles.append(role)

        # Sort team roles by name so they appear in a clean, stable order
        roles.sort(key=lambda r: r.name.lower())
        return roles

    async def _fix_roles_for_guild(self, guild: discord.Guild):
        team_player_role = guild.get_role(TEAM_PLAYER_ROLE_ID)
        if team_player_role is None:
            return

        me = guild.me
        if not me or not me.guild_permissions.manage_roles:
            return

        team_roles = self._get_team_roles(guild)
        if not team_roles:
            return

        # DEBUG: see which roles are being moved
        debug_names = ", ".join(f"{r.name}({r.id})" for r in team_roles)
        print(f"[TeamRoleAutoOrder] Guild {guild.id} team roles (ordered): {debug_names}")

        # Put first team role just under Team Player, others stacked directly under it
        # This guarantees a contiguous block: TEAM PLAYER, TEST1, TEST2, ... with no non‑team roles in between.
        top_position = team_player_role.position - 1
        if top_position < 1:
            top_position = 1

        role_positions: dict[discord.Role, int] = {}
        current_pos = top_position
        for r in team_roles:
            role_positions[r] = current_pos
            current_pos -= 1
            if current_pos < 1:
                current_pos = 1

        try:
            await guild.edit_role_positions(positions=role_positions)
        except Exception as e:
            print(f"[TeamRoleAutoOrder] edit_role_positions failed in guild {guild.id}: {e}")

    @tasks.loop(minutes=2)
    async def _task(self):
        await self.bot.wait_until_ready()
        for g in self.bot.guilds:
            try:
                await self._fix_roles_for_guild(g)
            except Exception as e:
                print(f"[TeamRoleAutoOrder] _fix_roles_for_guild error in {g.id}: {e}")
                continue

    @_task.before_loop
    async def _before(self):
        await self.bot.wait_until_ready()

    # -------- /debug-teams (admin) --------
    @app_commands.guilds(Object(id=TEST_GUILD_ID))
    @app_commands.default_permissions(administrator=True)
    @app_commands.command(
        name="debug-teams",
        description="Show which roles the bot thinks are team roles (for ordering).",
    )
    async def debug_teams(self, interaction: discord.Interaction):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return

        team_roles = self._get_team_roles(guild)
        if not team_roles:
            await interaction.response.send_message("No team roles detected.", ephemeral=True)
            return

        lines = ["Detected team roles (from teams.json):"]
        for r in team_roles:
            lines.append(f"- {r.name} ({r.id}) position={r.position}")

        await interaction.response.send_message("\n".join(lines), ephemeral=True)


class RoleOrderFixCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.guilds(Object(id=TEST_GUILD_ID))
    @app_commands.default_permissions(administrator=True)
    @app_commands.command(
        name="fix-team-order",
        description="Force one role directly under another (admins only).",
    )
    @app_commands.describe(
        above="Role that should be ABOVE",
        below="Role that should be directly BELOW the above role",
    )
    async def fix_team_order(
        self,
        interaction: discord.Interaction,
        above: discord.Role,
        below: discord.Role,
    ):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Use this in a server.",
                ephemeral=True,
            )
            return

        me = guild.me
        if not me or not me.guild_permissions.manage_roles:
            await interaction.response.send_message(
                "I don't have Manage Roles permission.",
                ephemeral=True,
            )
            return

        # Bot cannot move roles at or above its highest role
        top_bot_role = max(me.roles, key=lambda r: r.position, default=None)
        if top_bot_role and (above.position >= top_bot_role.position or below.position >= top_bot_role.position):
            await interaction.response.send_message(
                "I can't move these roles because they are at or above my highest role.",
                ephemeral=True,
            )
            return

        # We want BELOW to end up exactly one step under ABOVE
        target_pos = above.position - 1
        if target_pos < 1:
            target_pos = 1

        positions = {below: target_pos}

        try:
            await guild.edit_role_positions(positions=positions)
        except Exception as e:
            await interaction.response.send_message(
                f"Failed to move roles: {e}",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            f"Moved {below.mention} directly under {above.mention}.",
            ephemeral=True,
        )




class RescrimCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.guilds(Object(id=TEST_GUILD_ID))
    @app_commands.default_permissions(administrator=True)
    @app_commands.command(
        name="rescrim",
        description="Create a rematch announcement between two teams (admins only).",
    )
    @app_commands.describe(
        team1="Team 1 (mention / role / id / name)",
        team2="Team 2 (mention / role / id / name)",
    )
    async def rescrim(
        self,
        interaction: discord.Interaction,
        team1: str,
        team2: str,
    ):
        guild = interaction.guild
        channel = interaction.channel

        if guild is None or not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(
                "Use this in a server text channel.",
                ephemeral=True,
            )
            return

        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "You do not have permission to use this.",
                ephemeral=True,
            )
            return

        # resolve teams
        t1_role, _t1_mention_raw, t1_name = resolve_team_any(guild, team1)
        t2_role, _t2_mention_raw, t2_name = resolve_team_any(guild, team2)

        if not t1_name or not t2_name:
            await interaction.response.send_message(
                "Could not resolve one or both teams.",
                ephemeral=True,
            )
            return

        # Only @ if role exists; otherwise just use the name
        t1_display = t1_role.mention if isinstance(t1_role, discord.Role) else t1_name
        t2_display = t2_role.mention if isinstance(t2_role, discord.Role) else t2_name

        msg = (
            f"{t1_display} and {t2_display}\n"
            "# This Will Be A Rematch\n"
            "Our staff have decided to do a rematch and here are the stuff you’ll need:\n\n"
            "- Team Abbreviations (**Referee can give warnings**)\n"
            "- Discord Display Name (**Referee can give warnings**)\n"
            "- A Clean Mind\n"
            "- Sound Soul\n"
            "- And Stout Heart In Defeat."
        )

        # Post the rematch message (channel remains private)
        await channel.send(msg)

        # Remove leading ✅ from channel name if present
        try:
            old_name = channel.name or ""
            if old_name.startswith("✅"):
                new_name = old_name.lstrip("✅").lstrip("-").lstrip()
                if not new_name:
                    new_name = old_name
                await channel.edit(name=new_name, reason=f"Rescrim via /rescrim by {interaction.user}")
        except Exception:
            pass

        # Explicitly remove access for ref/caster roles for the whole time
        try:
            overwrites = channel.overwrites

            for rid in (HEAD_REF_ROLE_ID, REF_ROLE_ID, HEAD_CASTER_ROLE_ID, CASTER_ROLE_ID):
                role = guild.get_role(rid)
                if not role:
                    continue
                ow = overwrites.get(role, discord.PermissionOverwrite())
                ow.view_channel = False
                ow.send_messages = False
                overwrites[role] = ow

            await channel.edit(overwrites=overwrites, reason=f"/rescrim (lock refs/casters) by {interaction.user}")
        except Exception:
            # best-effort; don't fail the command on perms error
            pass

        await interaction.response.send_message(
            "Rematch message posted, channel kept private, ✅ removed, and refs/casters locked out.",
            ephemeral=True,
        )





@app_commands.command(name="scan-teams", description="Admin: register existing team roles into teams.json")
@app_commands.default_permissions(administrator=True)
async def scan_teams(interaction: discord.Interaction):
    guild = interaction.guild
    if guild is None:
        await interaction.response.send_message("Use this in a server.", ephemeral=True)
        return

    team_roles = []
    for role in guild.roles:
        if role.is_default() or role.managed:
            continue
        # skip obvious non-team roles
        if role.id in {
            HEAD_REF_ROLE_ID, REF_ROLE_ID,
            HEAD_CASTER_ROLE_ID, CASTER_ROLE_ID,
            CAPTAIN_ROLE_ID, CO_CAPTAIN_ROLE_ID,
            TEAM_PLAYER_ROLE_ID, TEAM_EXEC_ROLE_ID,
            BOARD_OF_DIRECTORS_ROLE_ID, COMMUNITY_MANAGER_ROLE_ID,
            SUPERVISOR_ROLE_ID, DEVELOPMENT_TEAM_ROLE_ID,
        }:
            continue
        # Example rule: require "team" in name; adjust if needed
        if "team" in role.name.lower():
            team_roles.append(role)

    if not team_roles:
        await interaction.response.send_message("No candidate team roles found by scan.", ephemeral=True)
        return

    existing = []
    if TEAMS_FILE.is_file():
        try:
            existing = json.loads(TEAMS_FILE.read_text("utf-8"))
        except Exception:
            existing = []
    if not isinstance(existing, list):
        existing = []

    for r in team_roles:
        if not any(str(e.get("role_id")) == str(r.id) for e in existing):
            existing.append({"role_id": r.id, "name": r.name})

    try:
        TEAMS_FILE.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    except Exception as e:
        await interaction.response.send_message(f"Failed to write teams.json: `{e}`", ephemeral=True)
        return

    await interaction.response.send_message(
        f"Registered {len(team_roles)} team role(s) into teams.json.",
        ephemeral=True,
    )





# ---------------- Admin command: delete scheduling channels ----------------
class SchedulingAdmin(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.guilds(Object(id=TEST_GUILD_ID))
    @app_commands.default_permissions(administrator=True)
    @app_commands.command(name="delete-scheduling", description="Delete all scheduling channels (name contains -vs-).")
    async def delete_scheduling(self, interaction: discord.Interaction):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return

        try:
            await interaction.response.defer(ephemeral=True, thinking=True)
        except Exception:
            pass

        deleted = 0
        for ch in list(guild.text_channels):
            try:
                if "-vs-" in (ch.name or "").lower():
                    await ch.delete(reason=f"/delete-scheduling by {interaction.user}")
                    deleted += 1
            except Exception:
                pass

        msg = f"Deleted {deleted} scheduling channels."
        try:
            await interaction.followup.send(msg, ephemeral=True)
            return
        except Exception:
            pass

        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(msg, ephemeral=True)
                return
        except Exception:
            pass

        try:
            if interaction.channel and isinstance(interaction.channel, discord.abc.Messageable):
                await interaction.channel.send(msg)
        except Exception:
            pass

# ---------------- BOT SETUP ----------------
class MainBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=INTENTS)
        self._web_runner: web.AppRunner | None = None

    async def setup_hook(self):
        guild_obj = Object(id=TEST_GUILD_ID)

        cog_names = [
            "SettingsCog",
            "AdminPanel",
            "ManageTeam",
            "DoneCommand",
            "RosterCog",
            "InfoCommands",
            "AdminManage",
            "FAQBracketCog",
            "StandingCog",
            "SchedulingAdmin",
            "BracketAdmin",
            "LeaveCog",
            "AutoDisbandScrim",
            "SaySomethingCog",
            "ForceTimeCog",
            "CommandGuideCog",
            "AutoCodeCog",
            "HeadsetInfoCog",
            "ServerStatsCog",
            "TeamRoleAutoOrderCog",
            "RescrimCog",
            "RoleOrderFixCog",
        ]
        for name in cog_names:
            cls = globals().get(name)
            if cls is None:
                print(f"Skipping cog {name}: not defined")
                continue
            try:
                await self.add_cog(cls(self))
                print(f"Added cog: {name}")
            except Exception:
                import traceback
                traceback.print_exc()
                print(f"Failed to add cog: {name}")


bot = MainBot()

web_api_started = False

@bot.event
async def on_ready():
    global web_api_started

    print(f"Logged in as {bot.user} (ID: {bot.user.id})")

    # Do slow Discord stuff AFTER the API starts
    print("Loading guild members once...")
    try:
        for guild in bot.guilds:
            await guild.chunk(cache=True)
        print("Finished loading guild members.")
    except Exception as e:
        print("Failed to load guild members:", repr(e))

@bot.listen("on_message")
async def standings_on_message(message: discord.Message):
    if message.author and message.author.bot:
        return

    if message.channel and getattr(message.channel, "id", None) == STANDINGS_CHANNEL_ID:
        await _update_standings_from_message(message)


@bot.listen("on_message_edit")
async def standings_on_message_edit(before: discord.Message, after: discord.Message):
    if after.channel and getattr(after.channel, "id", None) == STANDINGS_CHANNEL_ID:
        await _update_standings_from_message(after)


@bot.listen("on_guild_channel_pins_update")
async def standings_on_guild_channel_pins_update(channel: discord.abc.GuildChannel, last_pin):
    if getattr(channel, "id", None) != STANDINGS_CHANNEL_ID:
        return

    if not isinstance(channel, discord.TextChannel):
        return

    msg = None

    try:
        pinned = await channel.pins()
        if pinned:
            pinned.sort(key=lambda m: m.created_at, reverse=True)
            msg = pinned[0]
    except Exception as e:
        print("Warning: failed to read standings pins:", repr(e))

    if msg is None:
        try:
            async for m in channel.history(limit=1):
                msg = m
                break
        except Exception as e:
            print("Warning: failed to read latest standings message:", repr(e))

    if msg:
        await _update_standings_from_message(msg)


if __name__ == "__main__":
    bot.run(os.getenv("BOT_TOKEN"))
