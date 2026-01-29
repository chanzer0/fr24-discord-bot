import io
import logging
from typing import Callable

import discord
from discord import app_commands


_FIELD_DEFS: dict[str, dict] = {
    "manufacturers": {
        "label": "Manufacturers",
        "kind": "list",
        "ops": ("has", "has_any", "has_all", "contains"),
        "example": "AIRBUS",
        "example_op": "contains",
    },
    "cardCategory": {
        "label": "Rarity Tier",
        "kind": "str",
        "ops": ("=", "!=", "in"),
        "values": (
            "ultra",
            "rare",
            "scarce",
            "uncommon",
            "common",
            "historical",
            "fantasy",
        ),
        "example": "uncommon",
    },
    "rareness": {
        "label": "Rarity",
        "kind": "number",
        "ops": ("=", "!=", "<", "<=", ">", ">=", "between", "in"),
        "example": "3.09",
        "unit_hint": "rareness/100",
        "scale": 100.0,
    },
    "num": {
        "label": "Num Observed",
        "kind": "number",
        "ops": ("=", "!=", "<", "<=", ">", ">=", "between", "in"),
        "example": "193",
    },
    "engNum": {
        "label": "Num Engines",
        "kind": "number",
        "ops": ("=", "!=", "<", "<=", ">", ">=", "between", "in"),
        "example": "4",
    },
    "wingspan": {
        "label": "Wingspan",
        "kind": "number",
        "ops": ("=", "!=", "<", "<=", ">", ">=", "between"),
        "example": "79.8",
        "unit_hint": "meters",
    },
    "seats": {
        "label": "Seats",
        "kind": "number",
        "ops": ("=", "!=", "<", "<=", ">", ">=", "between", "in"),
        "example": "868",
    },
    "maxSpeed": {
        "label": "Speed",
        "kind": "number",
        "ops": ("=", "!=", "<", "<=", ">", ">=", "between"),
        "example": "561",
        "unit_hint": "knots",
    },
    "firstFlight": {
        "label": "First Flight",
        "kind": "number",
        "ops": ("=", "!=", "<", "<=", ">", ">=", "between", "in"),
        "example": "2005",
    },
    "mtow": {
        "label": "Weight",
        "kind": "number",
        "ops": ("=", "!=", "<", "<=", ">", ">=", "between"),
        "example": "575",
        "unit_hint": "tons",
        "scale": 1000.0,
        "example_op": ">=",
    },
    "military": {
        "label": "Military",
        "kind": "bool",
        "ops": ("is",),
        "example": "true",
        "example_op": "is",
    },
}

_FIELD_ALIASES: dict[str, str] = {}
for key, meta in _FIELD_DEFS.items():
    _FIELD_ALIASES[key.lower()] = key
    _FIELD_ALIASES[meta["label"].lower()] = key
    _FIELD_ALIASES[meta["label"].lower().replace(" ", "")] = key

_OP_LABELS = {
    "=": "equals (=)",
    "!=": "not equals (!=)",
    "<": "less than (<)",
    "<=": "less than or equal (<=)",
    ">": "greater than (>)",
    ">=": "greater than or equal (>=)",
    "between": "between (min..max)",
    "in": "in (a,b,c)",
    "has": "has",
    "has_any": "has any",
    "has_all": "has all",
    "contains": "contains",
    "is": "is (true/false)",
}

_MANUFACTURER_AUTOCOMPLETE = (
    "3XTRIM",
    "ACRO SPORT",
    "AERMACCHI",
    "AERO",
    "AERO BOERO",
    "AERO COMMANDER",
    "AERO VODOCHODY",
    "AEROANDINA",
    "AEROCOMP",
    "AERONCA",
    "AEROPRAKT",
    "AEROSPATIALE",
    "AEROSPOOL",
    "AEROSTAR",
    "AESL",
    "AGUSTAWESTLAND",
    "AIR",
    "AIR TRACTOR",
    "AIRBUS",
    "AIRBUS HELICOPTERS",
    "AIRCRAFT SPRUCE",
    "AIRDALE",
    "ALENIA",
    "ALMS",
    "ALPI",
    "AMD",
    "AMERICAN CHAMPION",
    "ANTONOV",
    "ARCTIC",
    "ASSO AEREI",
    "ATEC",
    "ATR",
    "AUSTER",
    "AUTOGYRO",
    "AVIAMILANO",
    "AVIAT",
    "AVRO",
    "AYRES",
    "B & F TECHNIK",
    "BAC",
    "BAYKAR",
    "BEAGLE",
    "BEDE",
    "BEECH",
    "BELL",
    "BELLANCA",
    "BERIEV",
    "BEST OFF",
    "BINDER",
    "BLACKSHAPE",
    "BLACKWING",
    "BOEING",
    "BOLKOW",
    "BOMBARDIER",
    "BRDITSCHKA",
    "BRITISH AEROSPACE",
    "BRITTEN-NORMAN",
    "BRM AERO",
    "BRUMBY",
    "BUCKER",
    "BUSHBY",
    "CAIGA",
    "CANADAIR",
    "CASA",
    "CENTRE EST",
    "CESSNA",
    "CIRRUS",
    "CLASS",
    "COMAC",
    "COMMONWEALTH",
    "COMP AIR",
    "CONAIR",
    "CONVAIR",
    "CORVUS",
    "CSA",
    "CUB CRAFTERS",
    "CURTISS",
    "DAHER",
    "DASSAULT",
    "DE HAVILLAND",
    "DE HAVILLAND CANADA",
    "DG FLUGZEUGBAU",
    "DIAMOND",
    "DORNIER",
    "DOUGLAS",
    "DOVA",
    "DRUINE",
    "DYN'AERO",
    "EKOLOT",
    "ELA AVIACION",
    "ELMWOOD",
    "EMBRAER",
    "ENSTROM",
    "EVEKTOR",
    "EXTRA",
    "FAIRCHILD",
    "FAIRCHILD DORNIER",
    "FIAT",
    "FISHER",
    "FLEET",
    "FLIGHT DESIGN",
    "FLY SYNTHESIS",
    "FLÄMING AIR",
    "FOKKER",
    "FOURNIER",
    "FUJI",
    "GATES LEARJET",
    "GENERAL ATOMICS",
    "GIPPSLAND",
    "GLASER-DIRKS",
    "GROB",
    "GROPPO",
    "GRUMMAN",
    "GRUMMAN AMERICAN",
    "GULFSTREAM AEROSPACE",
    "HALLEY",
    "HARBIN",
    "HAWKER",
    "HILLER",
    "HINDUSTAN",
    "HOWARD",
    "HUGHES",
    "IAI",
    "IAR",
    "ICP",
    "ILYUSHIN",
    "ISAACS",
    "ISSOIRE",
    "JABIRU",
    "JIHLAVAN",
    "JODEL",
    "JONKER",
    "JUNKERS",
    "JUST",
    "KAMAN",
    "KAWASAKI",
    "KITPLANES FOR AFRICA",
    "LAK",
    "LAKE",
    "LAMBERT",
    "LANCAIR",
    "LEARJET",
    "LET",
    "LOCKHEED",
    "LOCKHEED MARTIN",
    "LUSCOMBE",
    "MAGNI",
    "MAULE",
    "MESSERSCHMITT",
    "MIKOYAN",
    "MIL",
    "MILES",
    "MITSUBISHI",
    "MONOCOUPE",
    "MOONEY",
    "MORANE-SAULNIER",
    "MORAVAN",
    "MSW",
    "MUDRY",
    "MURPHY",
    "MXR",
    "NORD",
    "NORTH AMERICAN",
    "NORTHROP",
    "OSPREY",
    "P&M AVIATION",
    "PARTENAVIA",
    "PAZMANY",
    "PERCIVAL",
    "PIAGGIO",
    "PIEL",
    "PIK",
    "PILATUS",
    "PIPER",
    "PIPISTREL",
    "PITTS",
    "POTTIER",
    "PULSAR",
    "PZL-MIELEC",
    "PZL-OKECIE",
    "PZL-SWIDNIK",
    "RAJ HAMSA",
    "RANS",
    "RAYTHEON",
    "REARWIN",
    "REMOS",
    "REPUBLIC",
    "ROBIN",
    "ROBINSON",
    "ROCKWELL",
    "ROTORWAY",
    "RUTAN",
    "RYAN",
    "SAAB",
    "SAI",
    "SCHEIBE",
    "SCHEMPP-HIRTH",
    "SCHLEICHER",
    "SHORT",
    "SIAI-MARCHETTI",
    "SIKORSKY",
    "SLING AIRCRAFT",
    "SOCATA",
    "SOKO",
    "SONEX",
    "STAUDACHER",
    "STEARMAN",
    "STEMME",
    "STINSON",
    "STITS",
    "STODDARD-HAMILTON",
    "STOLP",
    "SUKHOI",
    "SWEARINGEN",
    "TAYLORCRAFT",
    "TEAM TANGO",
    "TECHNOAVIA",
    "TECNAM",
    "THURSTON",
    "TITAN",
    "TL ULTRALIGHT",
    "TRAVEL AIR",
    "TUPOLEV",
    "UL-JIH",
    "UTVA",
    "VAN'S",
    "VELOCITY",
    "WACO",
    "WASSMER",
    "WESTLAND",
    "XIAN",
    "XTREMEAIR",
    "YAKOVLEV",
    "ZENAIR",
    "ZIVKO",
)


def _resolve_field_key(value) -> str | None:
    if isinstance(value, app_commands.Choice):
        return value.value
    if isinstance(value, str):
        key = _FIELD_ALIASES.get(value.strip().lower())
        if key:
            return key
        if value in _FIELD_DEFS:
            return value
    return None


def _resolve_op(value: str | app_commands.Choice[str]) -> str | None:
    if isinstance(value, app_commands.Choice):
        raw = value.value
    else:
        raw = value
    if not isinstance(raw, str):
        return None
    cleaned = raw.strip().lower()
    if cleaned in _OP_LABELS:
        return cleaned
    synonyms = {
        "eq": "=",
        "equals": "=",
        "ne": "!=",
        "not": "!=",
        "lt": "<",
        "lte": "<=",
        "gt": ">",
        "gte": ">=",
        "range": "between",
        "any": "has_any",
        "all": "has_all",
        "bool": "is",
        "true": "is",
        "false": "is",
    }
    if cleaned in synonyms:
        return synonyms[cleaned]
    return None


def _split_csv(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def _parse_number(value: str) -> float | None:
    cleaned = value.strip()
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_range(value: str) -> tuple[float, float] | None:
    cleaned = value.strip().replace(" ", "")
    if ".." in cleaned:
        parts = cleaned.split("..", 1)
    elif "-" in cleaned:
        parts = cleaned.split("-", 1)
    else:
        return None
    if len(parts) != 2:
        return None
    start = _parse_number(parts[0])
    end = _parse_number(parts[1])
    if start is None or end is None:
        return None
    if start > end:
        start, end = end, start
    return start, end


def _parse_bool(value: str) -> bool | None:
    cleaned = value.strip().lower()
    if cleaned in ("true", "t", "yes", "y", "1"):
        return True
    if cleaned in ("false", "f", "no", "n", "0"):
        return False
    return None


def _format_error(field_key: str, op: str | None = None) -> str:
    meta = _FIELD_DEFS[field_key]
    ops = ", ".join(meta["ops"])
    example = meta.get("example")
    unit_hint = meta.get("unit_hint")
    field_label = meta["label"]
    example_bits = []
    example_op = meta.get("example_op") or meta["ops"][0]
    if example:
        example_bits.append(
            f'Example: /filterlist field="{field_label}" op="{example_op}" value="{example}"'
        )
    if unit_hint:
        example_bits.append(f"{field_label} values use {unit_hint}.")
    a380_hint = (
        "A380 (A388) reference values: Rarity Tier=uncommon, Rarity=3.09, "
        "Num Observed=193, Num Engines=4, Wingspan=79.8, Seats=868, Speed=561, "
        "First Flight=2005, Weight=575 (tons)."
    )
    parts = [f"Supported ops for {field_label}: {ops}."]
    if op and op not in meta["ops"]:
        parts.insert(0, f'Operator "{op}" is not valid for {field_label}.')
    if example_bits:
        parts.append(" ".join(example_bits) + ".")
    parts.append(a380_hint)
    return " ".join(parts)


def _build_filter(
    field_key: str, op: str, raw_value: str
) -> tuple[Callable[[dict], bool] | None, str | None]:
    meta = _FIELD_DEFS[field_key]
    if op not in meta["ops"]:
        return None, _format_error(field_key, op)
    kind = meta["kind"]
    scale = float(meta.get("scale", 1.0))

    if kind == "number":
        if op == "between":
            parsed = _parse_range(raw_value)
            if not parsed:
                return None, f"Value must be a range like 10..20. {_format_error(field_key)}"
            low, high = parsed
            low *= scale
            high *= scale

            def _predicate(row: dict) -> bool:
                value = row.get(field_key)
                if not isinstance(value, (int, float)) or isinstance(value, bool):
                    return False
                return low <= float(value) <= high

            return _predicate, None
        if op == "in":
            tokens = _split_csv(raw_value)
            if not tokens:
                return None, f"Value must be a comma-separated list. {_format_error(field_key)}"
            parsed_values = []
            for token in tokens:
                number = _parse_number(token)
                if number is None:
                    return None, f"Invalid number: {token}. {_format_error(field_key)}"
                parsed_values.append(number * scale)
            values_set = {float(val) for val in parsed_values}

            def _predicate(row: dict) -> bool:
                value = row.get(field_key)
                if not isinstance(value, (int, float)) or isinstance(value, bool):
                    return False
                return float(value) in values_set

            return _predicate, None

        number = _parse_number(raw_value)
        if number is None:
            return None, f"Invalid number. {_format_error(field_key)}"
        target = number * scale

        def _predicate(row: dict) -> bool:
            value = row.get(field_key)
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                return False
            value = float(value)
            if op == "=":
                return value == target
            if op == "!=":
                return value != target
            if op == "<":
                return value < target
            if op == "<=":
                return value <= target
            if op == ">":
                return value > target
            if op == ">=":
                return value >= target
            return False

        return _predicate, None

    if kind == "str":
        text = raw_value.strip().lower()
        if not text:
            return None, f"Value is required. {_format_error(field_key)}"
        if op == "in":
            values = {item.lower() for item in _split_csv(raw_value)}
            if not values:
                return None, f"Value must be a comma-separated list. {_format_error(field_key)}"

            def _predicate(row: dict) -> bool:
                value = row.get(field_key)
                if not isinstance(value, str):
                    return False
                return value.strip().lower() in values

            return _predicate, None

        def _predicate(row: dict) -> bool:
            value = row.get(field_key)
            if not isinstance(value, str):
                return False
            current = value.strip().lower()
            if op == "=":
                return current == text
            if op == "!=":
                return current != text
            return False

        return _predicate, None

    if kind == "list":
        if op in ("has", "contains"):
            needle = raw_value.strip().lower()
            if not needle:
                return None, f"Value is required. {_format_error(field_key)}"

            def _predicate(row: dict) -> bool:
                value = row.get(field_key)
                if not isinstance(value, list):
                    return False
                items = [
                    item.strip().lower() for item in value if isinstance(item, str) and item.strip()
                ]
                if not items:
                    return False
                if op == "contains":
                    return any(needle in item for item in items)
                return any(item == needle for item in items)

            return _predicate, None

        values = [item.lower() for item in _split_csv(raw_value)]
        if not values:
            return None, f"Value must be a comma-separated list. {_format_error(field_key)}"
        values_set = set(values)

        if op == "has_any":

            def _predicate(row: dict) -> bool:
                value = row.get(field_key)
                if not isinstance(value, list):
                    return False
                items = {
                    item.strip().lower()
                    for item in value
                    if isinstance(item, str) and item.strip()
                }
                return bool(items.intersection(values_set))

            return _predicate, None

        if op == "has_all":

            def _predicate(row: dict) -> bool:
                value = row.get(field_key)
                if not isinstance(value, list):
                    return False
                items = {
                    item.strip().lower()
                    for item in value
                    if isinstance(item, str) and item.strip()
                }
                return values_set.issubset(items)

            return _predicate, None

    if kind == "bool":
        parsed = _parse_bool(raw_value)
        if parsed is None:
            return None, f"Value must be true/false. {_format_error(field_key)}"

        def _predicate(row: dict) -> bool:
            value = row.get(field_key)
            if isinstance(value, bool):
                current = value
            else:
                current = False
            return current is parsed

        return _predicate, None

    return None, f"Unsupported filter type. {_format_error(field_key)}"


def _chunk_codes(codes: list[str], chunk_size: int = 99) -> list[str]:
    return [
        ",".join(codes[idx : idx + chunk_size])
        for idx in range(0, len(codes), chunk_size)
    ]


def _format_preview(
    codes: list[str], max_len: int = 1800, chunk_size: int = 99
) -> tuple[str, bool]:
    lines = _chunk_codes(codes, chunk_size)
    if not lines:
        return "", False
    preview_lines: list[str] = []
    remaining = max_len
    truncated = False
    for line in lines:
        extra = len(line) + (1 if preview_lines else 0)
        if extra > remaining:
            truncated = True
            break
        preview_lines.append(line)
        remaining -= extra
    text = "\n".join(preview_lines)
    if truncated and text:
        if len(text) + 4 <= max_len:
            text = text + "\n..."
        else:
            text = text[: max_len - 3] + "..."
    return text, truncated


def _log_no_matches(field_key: str, op: str, raw_value: str, rows: list[dict]) -> None:
    log = logging.getLogger(__name__)
    meta = _FIELD_DEFS.get(field_key, {})
    kind = meta.get("kind", "unknown")
    total_rows = len(rows)
    header = (
        f"filterlist no matches field={field_key} op={op} value={raw_value!r} "
        f"rows={total_rows} kind={kind}"
    )
    details: list[str] = []

    if kind == "list":
        tokens = [token.lower() for token in _split_csv(raw_value)]
        list_rows = 0
        non_empty_rows = 0
        eq_match_rows = 0
        contains_match_rows = 0
        samples: list[str] = []
        for row in rows:
            value = row.get(field_key)
            if not isinstance(value, list):
                continue
            list_rows += 1
            items = [
                item.strip()
                for item in value
                if isinstance(item, str) and item.strip()
            ]
            if not items:
                continue
            non_empty_rows += 1
            lowered = [item.lower() for item in items]
            if tokens and any(item in tokens for item in lowered):
                eq_match_rows += 1
            if tokens and any(any(token in item for token in tokens) for item in lowered):
                contains_match_rows += 1
            if len(samples) < 5:
                samples.extend(items[:1])
        details.append(
            "list_rows=%s non_empty_rows=%s eq_match_rows=%s contains_match_rows=%s tokens=%s samples=%s"
            % (list_rows, non_empty_rows, eq_match_rows, contains_match_rows, tokens, samples)
        )

    elif kind == "number":
        values: list[float] = []
        for row in rows:
            value = row.get(field_key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                values.append(float(value))
        if values:
            details.append(
                "numeric_rows=%s min=%s max=%s"
                % (len(values), min(values), max(values))
            )
        else:
            details.append("numeric_rows=0")

    elif kind == "str":
        non_empty = 0
        samples: list[str] = []
        for row in rows:
            value = row.get(field_key)
            if isinstance(value, str) and value.strip():
                non_empty += 1
                if len(samples) < 5:
                    samples.append(value.strip())
        details.append("non_empty_rows=%s samples=%s" % (non_empty, samples))

    elif kind == "bool":
        true_count = 0
        false_count = 0
        missing = 0
        for row in rows:
            value = row.get(field_key)
            if value is True:
                true_count += 1
            elif value is False:
                false_count += 1
            else:
                missing += 1
        details.append(
            "true=%s false=%s missing=%s" % (true_count, false_count, missing)
        )

    log.info("%s %s", header, " | ".join(details) if details else "")


def _all_ops() -> list[str]:
    ops = []
    for meta in _FIELD_DEFS.values():
        for op in meta["ops"]:
            if op not in ops:
                ops.append(op)
    return ops


def register(tree, db, config) -> None:
    async def op_autocomplete(
        interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        namespace = getattr(interaction, "namespace", None)
        field_value = getattr(namespace, "field", None) if namespace else None
        field_key = _resolve_field_key(field_value)
        ops = _FIELD_DEFS[field_key]["ops"] if field_key in _FIELD_DEFS else _all_ops()
        current_lower = (current or "").lower()
        choices = []
        for op in ops:
            label = _OP_LABELS.get(op, op)
            if current_lower and current_lower not in label.lower() and current_lower not in op:
                continue
            choices.append(app_commands.Choice(name=label, value=op))
        return choices[:25]

    async def value_autocomplete(
        interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        namespace = getattr(interaction, "namespace", None)
        field_value = getattr(namespace, "field", None) if namespace else None
        field_key = _resolve_field_key(field_value)
        if field_key == "cardCategory":
            values = _FIELD_DEFS["cardCategory"]["values"]
        elif field_key == "military":
            values = ("true", "false")
        elif field_key == "manufacturers":
            values = _MANUFACTURER_AUTOCOMPLETE
        else:
            return []
        current_lower = (current or "").lower()
        choices = [
            app_commands.Choice(name=value, value=value)
            for value in values
            if not current_lower or current_lower in value.lower()
        ]
        return choices[:25]

    @tree.command(
        name="filterlist",
        description="Generate a comma-separated ICAO list for FR24 aircraft filters.",
    )
    @app_commands.describe(
        field="Filter field (ex: Rarity Tier, Weight, Wingspan)",
        op="Operator (ex: =, between, in, contains)",
        value="Filter value (ex: uncommon, 575, 79.8, 10..20)",
    )
    @app_commands.choices(
        field=[
            app_commands.Choice(name=meta["label"], value=key)
            for key, meta in _FIELD_DEFS.items()
        ]
    )
    @app_commands.autocomplete(op=op_autocomplete, value=value_autocomplete)
    async def filterlist(
        interaction: discord.Interaction,
        field: app_commands.Choice[str],
        op: str,
        value: str,
    ) -> None:
        field_key = _resolve_field_key(field)
        resolved_op = _resolve_op(op)
        if not field_key or field_key not in _FIELD_DEFS:
            await interaction.response.send_message(
                "Unknown field. Use the dropdown to select a field like Rarity Tier or Weight.",
                ephemeral=True,
            )
            return
        if not resolved_op:
            await interaction.response.send_message(
                _format_error(field_key),
                ephemeral=True,
            )
            return

        predicate, error = _build_filter(field_key, resolved_op, value)
        if error or not predicate:
            await interaction.response.send_message(error or _format_error(field_key), ephemeral=True)
            return

        rows = await db.fetch_reference_model_rows()
        if not rows:
            await interaction.response.send_message(
                "No model data found. Ask an owner to run /refresh-reference.",
                ephemeral=True,
            )
            return
        if not any(isinstance(row, dict) and row.get("cardCategory") for row in rows):
            await interaction.response.send_message(
                "Model details are missing. Ask an owner to run /refresh-reference.",
                ephemeral=True,
            )
            return

        matches = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            if predicate(row):
                icao = row.get("id") or row.get("icao")
                if isinstance(icao, str) and icao.strip():
                    matches.append(icao.strip().upper())

        if not matches:
            _log_no_matches(field_key, resolved_op, value, rows)
            await interaction.response.send_message(
                f"No aircraft matched that filter. {_format_error(field_key)}",
                ephemeral=True,
            )
            return

        matches = sorted(set(matches))
        preview, truncated = _format_preview(matches)
        field_label = _FIELD_DEFS[field_key]["label"]
        message = (
            f'Filter: {field_label} {resolved_op} "{value}"\n'
            f"Matched {len(matches)} aircraft ICAO codes."
        )
        needs_file = len(matches) > 99
        if truncated:
            message += " List is truncated below; full list attached."
        elif needs_file:
            message += " Full list attached for easy copy/paste."
        file = None
        if truncated or needs_file:
            payload = "\n".join(_chunk_codes(matches)).encode("utf-8")
            file = discord.File(io.BytesIO(payload), filename="filterlist.txt")
        payload = {
            "content": f"{message}\n```\n{preview}\n```",
            "ephemeral": True,
        }
        if file is not None:
            payload["file"] = file
        await interaction.response.send_message(**payload)
