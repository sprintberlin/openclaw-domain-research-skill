## Description: <br>
Read-only domain research for agents. Checks Namecheap availability and pricing, public RDAP registration details, and DNS-over-HTTPS records through a single Python CLI. <br>

This skill is ready for commercial/non-commercial use. <br>

## Publisher: <br>
[sprintcx](https://clawhub.ai/user/sprintcx) <br>

### License/Terms of Use: <br>
MIT <br>

## Use Case: <br>
Developers, founders, and agents use this skill to research domain names: availability and premium quotes via the Namecheap API, standard registration/renewal/transfer pricing per TLD, registrar and lifecycle data via RDAP, and live DNS records via DNS over HTTPS. <br>

### Deployment Geography for Use: <br>
Global <br>

## Known Risks and Mitigations: <br>
Risk: Namecheap API credentials (API key, username) are secrets and could be exposed if echoed or logged. <br>
Mitigation: Store credentials in a protected environment file, send them only in HTTPS POST bodies, and never print them. <br>
Risk: Namecheap requires a whitelisted public IPv4 address; requests from other addresses fail. <br>
Mitigation: Set NAMECHEAP_CLIENT_IP explicitly or ensure the detected public IP is allowlisted in the Namecheap console. <br>
Risk: RDAP and DoH lookups disclose queried domain names to public services. <br>
Mitigation: Use only for legitimate research; avoid querying names whose confidentiality matters. <br>
Risk: Availability and prices are live observations, not purchase guarantees. <br>
Mitigation: Recheck immediately before any purchase; the skill is read-only and performs no mutations. <br>

## Reference(s): <br>
- [GitHub source repository](https://github.com/sprintberlin/openclaw-domain-research-skill) <br>
- [Namecheap API documentation](https://www.namecheap.com/support/api/methods/) <br>
- [rdap.org](https://rdap.org) <br>

## Skill Output: <br>
**Output Type(s):** [guidance, shell commands, structured research data] <br>
**Output Format:** [Markdown guidance with bash examples; table or JSON output from the bundled Python CLI] <br>
**Output Parameters:** [1D] <br>
**Other Properties Related to Output:** [Namecheap-backed commands require NAMECHEAP_API_KEY, NAMECHEAP_API_USER, NAMECHEAP_USERNAME, and a whitelisted IPv4; rdap and dns commands work without credentials.] <br>

## Skill Version(s): <br>
1.0.0 <br>

## Ethical Considerations: <br>
Users should verify availability and pricing before relying on results, respect registrar terms of service and rate limits, and avoid domain research that facilitates trademark abuse or cybersquatting. <br>
