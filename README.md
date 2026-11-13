### Memby

this app will manage memebers and memebership fee

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch develop
bench install-app memby
```

### AI connector (MCP, read-only)

Memby exposes a read-only [Model Context Protocol](https://modelcontextprotocol.io) endpoint so Claude
(or any MCP client) can answer questions about members and finances.

**Endpoint:** `https://<your-site>/api/method/memby.mcp.server.handle` (Streamable HTTP, stateless, JSON responses)

**Tools:** `search_members`, `get_member`, `list_members_with_arrears`, `get_member_payment_history`,
`financial_summary`, `expenses_by_category`, `search_bank_transactions`, `bank_balances`.

**Security model**

- Every call runs as the authenticated Frappe user, so normal role permissions apply
  (`memby-manager`, `memby-finance`, ...). A tool that needs a doctype the user can't read returns an error.
- The user must also have the **AI Reader** role (created on `bench migrate`), or be System Manager.
  This is the on/off switch per person.
- Sensitive member fields (mother's name, date of birth, photo, emergency contacts, relatives) are never
  returned. Bank account numbers are masked, and raw bank SMS text is searchable but never returned.
- Every tool call is written to **MCP Audit Log** (user, tool, arguments, status, duration, IP),
  kept for 180 days. Requests are rate-limited to 120/min per IP (hosted clients such as claude.ai share
  provider IPs, so this limit is shared across users connecting that way).

**Setup**

1. `bench --site <site> migrate` (creates the AI Reader role and MCP Audit Log doctype).
2. Give the AI Reader role to the users who should be allowed to connect.
3. Connect a client:
   - **Claude (claude.ai / Desktop) custom connector, OAuth:** in Frappe, open *OAuth Settings* and enable
     authorization server metadata, protected resource metadata and dynamic client registration
     (available in recent Frappe versions; check that `https://<site>/.well-known/oauth-authorization-server`
     returns JSON). Then in Claude: *Settings → Connectors → Add custom connector* and paste the endpoint URL.
     The user signs in to Memby and approves access. Site must be served over HTTPS and reachable from the internet.
   - **API key (Claude Code, scripts, testing):** generate an API key/secret for the user
     (*User → Settings → API Access*), then e.g.
     `claude mcp add --transport http memby https://<site>/api/method/memby.mcp.server.handle --header "Authorization: token <key>:<secret>"`

**Quick check**

```bash
curl -s -X POST https://<site>/api/method/memby.mcp.server.handle \
  -H "Authorization: token <key>:<secret>" -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/memby
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade

### License

mit
