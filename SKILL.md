---
name: "domain-research"
description: "Research domains with Namecheap availability and pricing, public RDAP registration details, and DoH DNS records."
---

# Domain Research

Read-only domain research using the Namecheap API for availability and pricing, plus public RDAP and DNS-over-HTTPS lookups for registered names.

Source: [sprintberlin/openclaw-domain-research-skill](https://github.com/sprintberlin/openclaw-domain-research-skill)

## Capabilities

- Batch domain availability checks via Namecheap (`namecheap.domains.check`)
- TLD registration and renewal pricing via Namecheap (`namecheap.users.getPricing`)
- Public RDAP queries for registrar, creation, update, and expiration dates (`https://rdap.org`)
- Public DNS record lookups via DNS over HTTPS (A, AAAA, MX, NS, TXT)
- Combined research pipeline with one command

This skill is strictly read-only. It performs searches and price checks; it never purchases, transfers, or modifies domains.

## Requirements

| Requirement | Details |
|---|---|
| Python | 3.10+ (standard library only; no third-party packages required) |
| Namecheap API credentials | `NAMECHEAP_API_KEY`, `NAMECHEAP_API_USER`, and `NAMECHEAP_USERNAME` |
| Whitelisted client IP | Must be allowlisted in the Namecheap console; auto-detected or provided via `NAMECHEAP_CLIENT_IP` |

Public RDAP and DNS commands work without Namecheap credentials.

## Setup

Store credentials in your agent environment, for example `~/.openclaw/.env`:

```bash
NAMECHEAP_API_KEY="your-api-key"
NAMECHEAP_API_USER="your-username"
NAMECHEAP_USERNAME="your-username"
# Optional overrides:
# NAMECHEAP_CLIENT_IP="1.2.3.4"
# NAMECHEAP_API_URL="https://api.namecheap.com/xml.response"
```

Verify your setup by running a test check:

```bash
python3 scripts/domain_research.py check example.com
```

## Usage

All commands support `--json` for machine consumption.

### 1. Combined research (recommended)

Runs availability, registration price, renewal price, RDAP, and DNS in one go:

```bash
python3 scripts/domain_research.py research mybrand123.com anotherbrand.ai
```

JSON output:

```bash
python3 scripts/domain_research.py research mybrand123.com --json
```

Skip specific sections when only partial data is needed:

```bash
python3 scripts/domain_research.py research mybrand123.com --no-dns --no-rdap
```

### 2. Availability check

Batch-check up to 50 domains per API request:

```bash
python3 scripts/domain_research.py check example.com brandnewidea99.com awesome-startup.net
```

### 3. TLD pricing

Inspect base price, ICANN fees, renewal, and transfer rates:

```bash
# 1-year registration
python3 scripts/domain_research.py price com

# Multi-year renewal
python3 scripts/domain_research.py price net --action renew --years 2

# Transfer pricing
python3 scripts/domain_research.py price org --action transfer
```

### 4. Public RDAP (whois alternative)

Fetches registration metadata without consuming registrar API quota:

```bash
python3 scripts/domain_research.py rdap github.com --json
```

### 5. DNS inspection

Queries Cloudflare DNS over HTTPS for live records:

```bash
python3 scripts/domain_research.py dns github.com --types A AAAA MX NS TXT --json
```

## Troubleshooting

- **Error `1011101: IP not allowed`**: Your current public IPv4 address is not in the Namecheap whitelist. Find your public IP with `curl https://api.ipify.org` and add it in the Namecheap API management panel.
- **Error `1011102: API key invalid`**: Recheck `NAMECHEAP_API_KEY` and ensure the API is active on your Namecheap account.
- **404 in RDAP**: The domain is either not registered or belongs to a TLD that does not yet publish an authoritative RDAP endpoint.
