#!/usr/bin/env python3
"""Read-only domain research with Namecheap availability/pricing, RDAP, and DNS."""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

DEFAULT_API_URL = "https://api.namecheap.com/xml.response"
DEFAULT_TIMEOUT = 20.0
MAX_DOMAINS_PER_CHECK = 50
USER_AGENT = "openclaw-domain-research-skill/1.0"
DNS_TYPES = {"A": 1, "NS": 2, "CNAME": 5, "MX": 15, "TXT": 16, "AAAA": 28}
DOMAIN_RE = re.compile(r"^[a-z0-9-]+$")


class DomainResearchError(RuntimeError):
    """Expected, user-facing error."""


class NamecheapError(DomainResearchError):
    """Namecheap returned an API error."""


@dataclass(frozen=True)
class NamecheapConfig:
    api_user: str
    api_key: str
    username: str
    client_ip: str
    api_url: str = DEFAULT_API_URL
    timeout: float = DEFAULT_TIMEOUT


class NamecheapClient:
    def __init__(self, config: NamecheapConfig):
        self.config = config

    def call(self, command: str, **parameters: str) -> ET.Element:
        payload = {
            "ApiUser": self.config.api_user,
            "ApiKey": self.config.api_key,
            "UserName": self.config.username,
            "Command": command,
            "ClientIp": self.config.client_ip,
            **parameters,
        }
        # Namecheap accepts form-encoded POST requests. Keeping the API key out of
        # the URL prevents it from appearing in shell history and common URL logs.
        request = urllib.request.Request(
            self.config.api_url,
            data=urllib.parse.urlencode(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": USER_AGENT,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout) as response:
                body = response.read()
        except urllib.error.HTTPError as exc:
            raise NamecheapError(f"Namecheap HTTP error {exc.code}") from None
        except urllib.error.URLError as exc:
            reason = getattr(exc, "reason", "network error")
            raise NamecheapError(f"Namecheap request failed: {reason}") from None
        except TimeoutError:
            raise NamecheapError("Namecheap request timed out") from None

        return parse_namecheap_response(body)

    def check(self, domains: list[str]) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        for start in range(0, len(domains), MAX_DOMAINS_PER_CHECK):
            batch = domains[start : start + MAX_DOMAINS_PER_CHECK]
            root = self.call("namecheap.domains.check", DomainList=",".join(batch))
            seen: set[str] = set()
            for element in root.iter():
                if local_name(element.tag) != "DomainCheckResult":
                    continue
                attrs = element.attrib
                domain = attrs.get("Domain", "").lower()
                seen.add(domain)
                output.append(
                    {
                        "domain": domain,
                        "available": parse_bool(attrs.get("Available")),
                        "premium": parse_bool(attrs.get("IsPremiumName")),
                        "premium_registration_price": money_or_none(
                            attrs.get("PremiumRegistrationPrice")
                        ),
                        "premium_renewal_price": money_or_none(
                            attrs.get("PremiumRenewalPrice")
                        ),
                        "premium_transfer_price": money_or_none(
                            attrs.get("PremiumTransferPrice")
                        ),
                        "icann_fee": money_or_none(attrs.get("IcannFee")),
                        "eap_fee": money_or_none(attrs.get("EapFee")),
                        "error_number": none_if_zero(attrs.get("ErrorNo")),
                        "description": attrs.get("Description") or None,
                    }
                )
            for domain in batch:
                if domain not in seen:
                    output.append(
                        {
                            "domain": domain,
                            "available": None,
                            "premium": None,
                            "error_number": None,
                            "description": "No result returned by Namecheap",
                        }
                    )
        order = {domain: index for index, domain in enumerate(domains)}
        output.sort(key=lambda row: order.get(row["domain"], len(order)))
        return output

    def pricing(self, tld: str, action: str, years: int = 1) -> dict[str, Any]:
        root = self.call(
            "namecheap.users.getPricing",
            ProductType="DOMAIN",
            ProductName=tld,
            ActionName=action.upper(),
        )
        matched_product = False
        prices: list[dict[str, Any]] = []
        for product in root.iter():
            if local_name(product.tag) != "Product":
                continue
            if product.attrib.get("Name", "").lower() != tld.lower():
                continue
            matched_product = True
            for element in product.iter():
                if local_name(element.tag) != "Price":
                    continue
                attrs = element.attrib
                duration = int(attrs.get("Duration", "0") or 0)
                if duration != years or attrs.get("DurationType", "").upper() != "YEAR":
                    continue
                base_price = decimal_or_none(attrs.get("Price"))
                additional_cost = decimal_or_none(attrs.get("AdditionalCost"))
                prices.append(
                    {
                        "years": duration,
                        "currency": attrs.get("Currency"),
                        "price": decimal_string(base_price),
                        "additional_cost": decimal_string(additional_cost),
                        "total": decimal_string(add_decimal(base_price, additional_cost)),
                        "regular_price": money_or_none(attrs.get("RegularPrice")),
                        "your_price": money_or_none(attrs.get("YourPrice")),
                        "promotion_price": money_or_none(attrs.get("PromotionPrice")),
                        "pricing_type": attrs.get("PricingType"),
                    }
                )
        if not matched_product or not prices:
            raise NamecheapError(
                f"No {years}-year {action.lower()} price returned for .{tld}"
            )
        return {"tld": tld, "action": action.lower(), **prices[0]}


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_namecheap_response(body: bytes | str) -> ET.Element:
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        raise NamecheapError("Namecheap returned invalid XML") from None

    errors = []
    for element in root.iter():
        if local_name(element.tag) != "Error":
            continue
        code = element.attrib.get("Number")
        text = (element.text or "").strip()
        errors.append(
            f"{code}: {text}" if code and text else text or code or "Unknown error"
        )
    if errors or root.attrib.get("Status", "").upper() == "ERROR":
        raise NamecheapError("; ".join(errors) or "Namecheap returned an error")
    return root


def parse_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    return None


def decimal_or_none(value: str | None) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def decimal_string(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value, "f")


def money_or_none(value: str | None) -> str | None:
    parsed = decimal_or_none(value)
    if parsed is None or parsed == 0:
        return None
    return decimal_string(parsed)


def add_decimal(left: Decimal | None, right: Decimal | None) -> Decimal | None:
    if left is None:
        return None
    return left + (right or Decimal(0))


def none_if_zero(value: str | None) -> str | None:
    return None if value in (None, "", "0") else value


def normalize_domain(value: str) -> str:
    raw = value.strip()
    if not raw:
        raise DomainResearchError("Domain cannot be empty")
    if "://" in raw:
        parsed = urllib.parse.urlsplit(raw)
        raw = parsed.hostname or ""
    else:
        raw = raw.split("/", 1)[0]
        if raw.count(":") == 1:
            host, port = raw.rsplit(":", 1)
            if port.isdigit():
                raw = host
    raw = raw.strip().rstrip(".").lower()
    try:
        ascii_domain = raw.encode("idna").decode("ascii")
    except UnicodeError:
        raise DomainResearchError(f"Invalid internationalized domain: {value}") from None
    if len(ascii_domain) > 253 or "." not in ascii_domain:
        raise DomainResearchError(f"Invalid domain: {value}")
    for label in ascii_domain.split("."):
        if (
            not label
            or len(label) > 63
            or not DOMAIN_RE.fullmatch(label)
            or label.startswith("-")
            or label.endswith("-")
        ):
            raise DomainResearchError(f"Invalid domain: {value}")
    return ascii_domain


def normalize_domains(values: Iterable[str]) -> list[str]:
    domains: list[str] = []
    seen: set[str] = set()
    for value in values:
        for candidate in value.split(","):
            domain = normalize_domain(candidate)
            if domain not in seen:
                domains.append(domain)
                seen.add(domain)
    if not domains:
        raise DomainResearchError("At least one domain is required")
    return domains


def normalize_tld(value: str) -> str:
    tld = value.strip().lower().lstrip(".")
    try:
        tld = tld.encode("idna").decode("ascii")
    except UnicodeError:
        raise DomainResearchError(f"Invalid TLD: {value}") from None
    if not tld or "." in tld or not DOMAIN_RE.fullmatch(tld):
        raise DomainResearchError(f"Invalid TLD: {value}")
    return tld


def detect_public_ip(timeout: float) -> str:
    request = urllib.request.Request(
        "https://api.ipify.org", headers={"User-Agent": USER_AGENT}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            value = response.read().decode("ascii").strip()
    except (urllib.error.URLError, TimeoutError, UnicodeError):
        raise DomainResearchError(
            "Could not detect public IPv4 address; set NAMECHEAP_CLIENT_IP"
        ) from None
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        raise DomainResearchError(
            "Public IP service returned an invalid address; set NAMECHEAP_CLIENT_IP"
        ) from None
    if address.version != 4:
        raise DomainResearchError("Namecheap requires an IPv4 NAMECHEAP_CLIENT_IP")
    return value


def build_namecheap_client(args: argparse.Namespace) -> NamecheapClient:
    api_user = os.environ.get("NAMECHEAP_API_USER", "").strip()
    api_key = os.environ.get("NAMECHEAP_API_KEY", "").strip()
    username = os.environ.get("NAMECHEAP_USERNAME", api_user).strip()
    missing = [
        name
        for name, value in (
            ("NAMECHEAP_API_USER", api_user),
            ("NAMECHEAP_API_KEY", api_key),
            ("NAMECHEAP_USERNAME", username),
        )
        if not value
    ]
    if missing:
        raise DomainResearchError("Missing environment variable(s): " + ", ".join(missing))
    client_ip = (
        getattr(args, "client_ip", None)
        or os.environ.get("NAMECHEAP_CLIENT_IP", "").strip()
        or detect_public_ip(args.timeout)
    )
    try:
        address = ipaddress.ip_address(client_ip)
    except ValueError:
        raise DomainResearchError("NAMECHEAP_CLIENT_IP must be a valid IPv4 address") from None
    if address.version != 4:
        raise DomainResearchError("NAMECHEAP_CLIENT_IP must be an IPv4 address")
    api_url = (
        getattr(args, "api_url", None)
        or os.environ.get("NAMECHEAP_API_URL", "").strip()
        or DEFAULT_API_URL
    )
    if not api_url.lower().startswith("https://"):
        raise DomainResearchError("NAMECHEAP_API_URL must use HTTPS")
    return NamecheapClient(
        NamecheapConfig(
            api_user=api_user,
            api_key=api_key,
            username=username,
            client_ip=client_ip,
            api_url=api_url,
            timeout=args.timeout,
        )
    )


def fetch_json(url: str, timeout: float, accept: str = "application/json") -> Any:
    request = urllib.request.Request(
        url, headers={"Accept": accept, "User-Agent": USER_AGENT}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except urllib.error.HTTPError:
        raise
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", "network error")
        raise DomainResearchError(f"Public lookup failed: {reason}") from None
    except (TimeoutError, json.JSONDecodeError):
        raise DomainResearchError("Public lookup timed out or returned invalid JSON") from None


def rdap_lookup(domain: str, timeout: float) -> dict[str, Any]:
    url = "https://rdap.org/domain/" + urllib.parse.quote(domain, safe="")
    try:
        data = fetch_json(url, timeout, "application/rdap+json, application/json")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return {"domain": domain, "registered": False}
        raise DomainResearchError(f"RDAP lookup failed with HTTP {exc.code}") from None

    registrar = None
    for entity in data.get("entities", []):
        if "registrar" not in entity.get("roles", []):
            continue
        for item in entity.get("vcardArray", [None, []])[1] or []:
            if item and item[0] == "fn" and len(item) > 3:
                registrar = item[3]
                break
        if registrar:
            break

    events = {
        event.get("eventAction"): event.get("eventDate")
        for event in data.get("events", [])
        if event.get("eventAction") and event.get("eventDate")
    }
    nameservers = sorted(
        {
            server.get("ldhName", "").lower()
            for server in data.get("nameservers", [])
            if server.get("ldhName")
        }
    )
    return {
        "domain": domain,
        "registered": True,
        "handle": data.get("handle"),
        "status": data.get("status", []),
        "registrar": registrar,
        "events": events,
        "nameservers": nameservers,
    }


def dns_lookup(domain: str, record_types: list[str], timeout: float) -> dict[str, Any]:
    records: dict[str, Any] = {}
    for record_type in record_types:
        query = urllib.parse.urlencode({"name": domain, "type": record_type})
        url = "https://cloudflare-dns.com/dns-query?" + query
        try:
            data = fetch_json(url, timeout, "application/dns-json")
            answers = []
            for answer in data.get("Answer", []) or []:
                answers.append(
                    {
                        "name": answer.get("name", "").rstrip("."),
                        "type": answer.get("type"),
                        "ttl": answer.get("TTL"),
                        "data": answer.get("data"),
                    }
                )
            records[record_type] = {
                "status": data.get("Status"),
                "answers": answers,
            }
        except (DomainResearchError, urllib.error.HTTPError) as exc:
            code = exc.code if isinstance(exc, urllib.error.HTTPError) else None
            records[record_type] = {
                "status": None,
                "answers": [],
                "error": f"HTTP {code}" if code else str(exc),
            }
    return {"domain": domain, "records": records}


def extension_for(domain: str) -> str:
    # Namecheap's pricing API accepts product names such as com or co.uk. Try the
    # longest suffix first in research mode; fall back to the final label if the
    # registry's product name is different.
    labels = domain.split(".")
    return ".".join(labels[-2:]) if len(labels) > 2 and len(labels[-1]) == 2 else labels[-1]


def research_domains(
    domains: list[str], args: argparse.Namespace, client: NamecheapClient
) -> list[dict[str, Any]]:
    availability = client.check(domains)
    registration_prices: dict[str, dict[str, Any] | str] = {}
    renewal_prices: dict[str, dict[str, Any] | str] = {}

    if not args.no_pricing:
        for tld in sorted({extension_for(domain) for domain in domains}):
            try:
                registration_prices[tld] = client.pricing(tld, "REGISTER", 1)
            except NamecheapError as exc:
                if "." in tld:
                    fallback = tld.rsplit(".", 1)[-1]
                    try:
                        registration_prices[tld] = client.pricing(fallback, "REGISTER", 1)
                    except NamecheapError:
                        registration_prices[tld] = str(exc)
                else:
                    registration_prices[tld] = str(exc)
            try:
                renewal_prices[tld] = client.pricing(tld, "RENEW", 1)
            except NamecheapError as exc:
                if "." in tld:
                    fallback = tld.rsplit(".", 1)[-1]
                    try:
                        renewal_prices[tld] = client.pricing(fallback, "RENEW", 1)
                    except NamecheapError:
                        renewal_prices[tld] = str(exc)
                else:
                    renewal_prices[tld] = str(exc)

    output = []
    for row in availability:
        domain = row["domain"]
        result: dict[str, Any] = {"availability": row}
        tld = extension_for(domain)
        if not args.no_pricing:
            result["registration_price"] = registration_prices.get(tld)
            result["renewal_price"] = renewal_prices.get(tld)
        if row.get("available") is False:
            if not args.no_rdap:
                try:
                    result["rdap"] = rdap_lookup(domain, args.timeout)
                except DomainResearchError as exc:
                    result["rdap"] = {"domain": domain, "error": str(exc)}
            if not args.no_dns:
                result["dns"] = dns_lookup(domain, args.dns_types, args.timeout)
        output.append(result)
    return output


def print_check_table(rows: list[dict[str, Any]]) -> None:
    print(f"{'DOMAIN':<45} {'AVAILABLE':<10} {'PREMIUM':<8} PRICE")
    for row in rows:
        available = yes_no_unknown(row.get("available"))
        premium = yes_no_unknown(row.get("premium"))
        price = row.get("premium_registration_price") or "-"
        if row.get("description"):
            price = row["description"]
        print(f"{row['domain']:<45} {available:<10} {premium:<8} {price}")


def print_price(row: dict[str, Any]) -> None:
    currency = row.get("currency") or ""
    print(f"TLD: .{row['tld']}")
    print(f"Action: {row['action']}")
    print(f"Duration: {row['years']} year(s)")
    print(f"Price: {row.get('price')} {currency}")
    print(f"Additional cost: {row.get('additional_cost')} {currency}")
    print(f"Total: {row.get('total')} {currency}")


def print_research(rows: list[dict[str, Any]]) -> None:
    for index, result in enumerate(rows):
        if index:
            print()
        availability = result["availability"]
        domain = availability["domain"]
        print(domain)
        print(f"  Available: {yes_no_unknown(availability.get('available'))}")
        print(f"  Premium: {yes_no_unknown(availability.get('premium'))}")
        if result.get("registration_price"):
            price = result["registration_price"]
            if isinstance(price, dict):
                print(
                    f"  Registration: {price.get('total')} {price.get('currency')} "
                    f"({price.get('years')} year)"
                )
            else:
                print(f"  Registration: unavailable ({price})")
        if result.get("renewal_price"):
            price = result["renewal_price"]
            if isinstance(price, dict):
                print(
                    f"  Renewal: {price.get('total')} {price.get('currency')} "
                    f"({price.get('years')} year)"
                )
            else:
                print(f"  Renewal: unavailable ({price})")
        rdap = result.get("rdap")
        if rdap:
            print(f"  Registrar: {rdap.get('registrar') or 'unknown'}")
            expiration = rdap.get("events", {}).get("expiration")
            if expiration:
                print(f"  Expiration: {expiration}")
        dns = result.get("dns", {}).get("records", {})
        if dns:
            active = [key for key, value in dns.items() if value.get("answers")]
            print(f"  DNS records found: {', '.join(active) if active else 'none'}")


def yes_no_unknown(value: bool | None) -> str:
    return "yes" if value is True else "no" if value is False else "unknown"


def emit(data: Any, as_json: bool, printer: Any | None = None) -> None:
    if as_json:
        print(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False))
    elif printer:
        printer(data)
    else:
        print(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False))


def add_common_network_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--timeout", type=float, default=DEFAULT_TIMEOUT, help="Network timeout in seconds"
    )


def add_namecheap_options(parser: argparse.ArgumentParser) -> None:
    add_common_network_options(parser)
    parser.add_argument("--client-ip", help="Override NAMECHEAP_CLIENT_IP")
    parser.add_argument("--api-url", help="Override NAMECHEAP_API_URL")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only domain research using Namecheap, RDAP, and DNS"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    check = subparsers.add_parser("check", help="Check one or more domains at Namecheap")
    check.add_argument("domains", nargs="+", help="Domains, space- or comma-separated")
    check.add_argument("--json", action="store_true")
    add_namecheap_options(check)

    price = subparsers.add_parser("price", help="Get Namecheap TLD pricing")
    price.add_argument("tld", help="TLD, with or without a leading dot")
    price.add_argument(
        "--action",
        choices=["register", "renew", "transfer", "reactivate"],
        default="register",
    )
    price.add_argument("--years", type=int, default=1)
    price.add_argument("--json", action="store_true")
    add_namecheap_options(price)

    rdap = subparsers.add_parser("rdap", help="Get public RDAP registration metadata")
    rdap.add_argument("domain")
    rdap.add_argument("--json", action="store_true")
    add_common_network_options(rdap)

    dns = subparsers.add_parser("dns", help="Get public DNS records via DNS over HTTPS")
    dns.add_argument("domain")
    dns.add_argument(
        "--types",
        nargs="+",
        choices=sorted(DNS_TYPES),
        default=["A", "AAAA", "MX", "NS"],
    )
    dns.add_argument("--json", action="store_true")
    add_common_network_options(dns)

    research = subparsers.add_parser(
        "research", help="Combine availability, pricing, RDAP, and DNS"
    )
    research.add_argument("domains", nargs="+", help="Domains, space- or comma-separated")
    research.add_argument("--json", action="store_true")
    research.add_argument("--no-pricing", action="store_true")
    research.add_argument("--no-rdap", action="store_true")
    research.add_argument("--no-dns", action="store_true")
    research.add_argument(
        "--dns-types",
        nargs="+",
        choices=sorted(DNS_TYPES),
        default=["A", "AAAA", "MX", "NS"],
    )
    add_namecheap_options(research)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.timeout <= 0:
        parser.error("--timeout must be greater than zero")

    try:
        if args.command == "check":
            domains = normalize_domains(args.domains)
            rows = build_namecheap_client(args).check(domains)
            emit(rows, args.json, print_check_table)
        elif args.command == "price":
            if args.years < 1 or args.years > 10:
                raise DomainResearchError("--years must be between 1 and 10")
            row = build_namecheap_client(args).pricing(
                normalize_tld(args.tld), args.action, args.years
            )
            emit(row, args.json, print_price)
        elif args.command == "rdap":
            row = rdap_lookup(normalize_domain(args.domain), args.timeout)
            emit(row, args.json)
        elif args.command == "dns":
            row = dns_lookup(normalize_domain(args.domain), args.types, args.timeout)
            emit(row, args.json)
        elif args.command == "research":
            domains = normalize_domains(args.domains)
            rows = research_domains(domains, args, build_namecheap_client(args))
            emit(rows, args.json, print_research)
        else:
            parser.error("Unknown command")
    except DomainResearchError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
