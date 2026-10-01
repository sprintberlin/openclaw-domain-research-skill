# OpenClaw Domain Research Skill

A public OpenClaw skill for read-only domain research. It combines live Namecheap availability and pricing with public RDAP registration data and DNS-over-HTTPS records.

Repository: [`sprintberlin/openclaw-domain-research-skill`](https://github.com/sprintberlin/openclaw-domain-research-skill)

## Features

- Check one or many domains for availability through the Namecheap API
- Detect premium domains and expose premium registration and renewal quotes
- Query live registration, renewal, transfer, and reactivation prices by TLD
- Inspect registrar, lifecycle dates, status codes, and nameservers through RDAP
- Resolve A, AAAA, MX, NS, CNAME, and TXT records through DNS over HTTPS
- Combine availability, standard pricing, RDAP, and DNS in one research command
- Produce human-readable tables or structured JSON
- Remain read-only: no registration, transfer, renewal, DNS update, or account mutation commands

## Requirements

- Python 3.10 or newer
- A Namecheap account with API access enabled
- Your public IPv4 address on the Namecheap API allowlist
- The following environment variables for Namecheap-backed commands:

```dotenv
NAMECHEAP_API_KEY=your-api-key
NAMECHEAP_API_USER=your-namecheap-api-user
NAMECHEAP_USERNAME=your-namecheap-username
# Optional. Otherwise the script detects the current public IPv4 address.
NAMECHEAP_CLIENT_IP=1.2.3.4
```

`rdap` and `dns` work without Namecheap credentials.

Namecheap credentials are secrets. Keep them in a protected environment file such as `~/.openclaw/.env`; never commit them to this repository.

## Install in OpenClaw

Clone the repository:

```bash
mkdir -p ~/github_repos
git clone https://github.com/sprintberlin/openclaw-domain-research-skill.git \
  ~/github_repos/openclaw-domain-research-skill
```

Add the repository root to `skills.load.extraDirs` in your OpenClaw configuration:

```json
{
  "skills": {
    "load": {
      "extraDirs": [
        "~/github_repos/openclaw-domain-research-skill"
      ]
    }
  }
}
```

Restart or reload OpenClaw after changing its configuration. The discovered skill name is `domain-research`.

## Quick start

```bash
cd ~/github_repos/openclaw-domain-research-skill

# Availability
python3 scripts/domain_research.py check example.com brand-idea-12345.com

# Standard TLD price
python3 scripts/domain_research.py price com
python3 scripts/domain_research.py price com --action renew

# Public registration metadata
python3 scripts/domain_research.py rdap example.com --json

# DNS
python3 scripts/domain_research.py dns example.com --types A AAAA MX NS TXT --json

# Combined report
python3 scripts/domain_research.py research example.com brand-idea-12345.com
```

Every command accepts `--help`. Add `--json` when another program or agent will consume the result.

## Command reference

### `check`

```bash
python3 scripts/domain_research.py check DOMAIN [DOMAIN ...] [--json]
```

Comma-separated values are also accepted. The helper removes duplicates and splits large inputs into batches of 50 for the Namecheap API.

### `price`

```bash
python3 scripts/domain_research.py price TLD \
  [--action register|renew|transfer|reactivate] \
  [--years 1] [--json]
```

The displayed `total` is the returned base price plus Namecheap's returned additional cost. Currency comes directly from the API. Premium-domain prices come from `check`, not from the standard TLD price response.

### `rdap`

```bash
python3 scripts/domain_research.py rdap DOMAIN [--json]
```

Uses `rdap.org` as a public RDAP bootstrap service. A 404 is represented as `registered: false`.

### `dns`

```bash
python3 scripts/domain_research.py dns DOMAIN \
  [--types A AAAA CNAME MX NS TXT] [--json]
```

Uses Cloudflare's public DNS-over-HTTPS JSON endpoint.

### `research`

```bash
python3 scripts/domain_research.py research DOMAIN [DOMAIN ...] \
  [--no-pricing] [--no-rdap] [--no-dns] [--json]
```

RDAP and DNS are queried only for names reported unavailable by Namecheap. This keeps candidate searches fast and avoids unnecessary public lookups.

## Namecheap API behavior

- Production endpoint: `https://api.namecheap.com/xml.response`
- Override endpoint: `NAMECHEAP_API_URL`
- Override or pin client IPv4: `NAMECHEAP_CLIENT_IP` or `--client-ip`
- API credentials are sent in an HTTPS form-encoded POST body, not in the request URL
- Namecheap still validates the request's public IPv4 against its account allowlist
- Availability and pricing are live API observations, not guarantees of successful registration

## Security and privacy

- The bundled helper exposes no write or purchase operations.
- It never intentionally prints API credentials.
- Avoid verbose HTTP tracing because it may capture credential-bearing request bodies.
- RDAP and DNS requests disclose queried domain names to public lookup services.
- Domain availability can change at any time. Recheck immediately before any purchase.

## Development

The helper uses only Python's standard library.

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
python3 /usr/lib/node_modules/openclaw/skills/skill-creator/scripts/quick_validate.py .
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidance.

## License

MIT. See [LICENSE](LICENSE).
