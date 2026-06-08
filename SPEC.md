# mesh: a flow-based programming language for agents

## what is mesh

mesh is a programming language designed for ai agents. it is:

- **flow-based**: data flows through pipes, left to right. no variables, no assignment.
- **tool-native**: every operation is a tool call. built-in and external tools are the same.
- **observable**: every step produces structured output. failures are first-class.
- **agent-readable**: syntax is close to natural language. agents can read and write it without special prompting.

## design principles

1. **no state** — no variables, no mutation. data flows through pipes.
2. **everything is a tool** — `http.get`, `json.parse`, `sentiment.analyze` are the same kind of thing.
3. **errors are data** — failures don't crash the pipeline. they flow through.
4. **parallel by default** — independent operations run concurrently unless ordered.
5. **self-describing** — every mesh program documents itself.

## syntax

### basic pipeline

```
fetch "https://api.example.com/data"
  → json.parse
  → .items[:5]
  → format as: "{{.name}}: {{.value}}"
  → print
```

each line is a step. `→` pipes output of the previous step to the next.

### tool calls

```
tool_name arg1 arg2 key=value
```

arguments can be:
- **positional**: `"https://example.com"`, `42`, `true`
- **named**: `method="POST"`, `timeout=30`
- **flags**: `--raw`, `--quiet`

### data access

```
.items          # access field
.items[0]       # index
.items[:5]      # slice
.items[1:3]     # range
.length         # built-in property
```

### conditionals

```
check http.get "https://example.com/health"
  → if .status != 200:
      alert "service is down"
  → if .status == 200:
      log "service is healthy"
```

### error handling

```
fetch "https://api.example.com/data"
  → retry 3, backoff 2s:
      http.get
  → on_error:
      log "failed after 3 retries"
      return {error: true}
```

### parallel execution

```
parallel:
  branch commits: github.repos.pokelabshq.council.commits[:5]
  branch issues:  github.repos.pokelabshq.council.issues[:5]
  → merge
  → format as: "{{.type}}: {{.title}}"
```

### tool definition

```
tool sentiment:
  description: "analyze text sentiment"
  input:
    text: string
  output:
    score: float
    label: string
  steps:
    call http.post "http://localhost:8764/api/analyze"
      body: {text: input.text}
    → json.parse
    → return {score: .score, label: .label}
```

### composition

```
# import tools from other files
import "./tools/social.mesh"

# use imported tools
fetch "https://news.ycombinator.com"
  → hackernews.parse
  → .stories[:10]
  → for each story:
      sentiment story.title
      → if .label == "negative":
          skip
      → otherwise:
          twitter.post "{{.title}} — {{.url}}"
```

## built-in tools

### data

| tool | description | example |
|------|-------------|---------|
| `json.parse` | parse json string | `→ json.parse` |
| `json.stringify` | serialize to json | `→ json.stringify` |
| `yaml.parse` | parse yaml string | `→ yaml.parse` |
| `base64.encode` | base64 encode | `→ base64.encode` |
| `base64.decode` | base64 decode | `→ base64.decode` |

### http

| tool | description | example |
|------|-------------|---------|
| `http.get` | http get request | `http.get "https://example.com"` |
| `http.post` | http post request | `http.post "https://example.com" body={}` |
| `http.put` | http put request | `http.put "https://example.com" body={}` |
| `http.delete` | http delete | `http.delete "https://example.com"` |

### flow control

| tool | description | example |
|------|-------------|---------|
| `filter` | filter items | `→ filter .active == true` |
| `map` | transform items | `→ map .name` |
| `sort` | sort items | `→ sort by: .date` |
| `take` | take first n | `→ take 5` |
| `skip` | skip first n | `→ skip 10` |
| `count` | count items | `→ count` |
| `first` | first item | `→ first` |
| `last` | last item | `→ last` |
| `unique` | deduplicate | `→ unique by: .id` |
| `flatten` | flatten nested | `→ flatten` |

### output

| tool | description | example |
|------|-------------|---------|
| `print` | print to stdout | `→ print` |
| `format` | format as string | `→ format as: "{{.name}}"` |
| `log` | log message | `→ log "info: {{.status}}"` |
| `return` | return value | `→ return {ok: true}` |
| `save` | save to file | `→ save "output.json"` |
| `load` | load from file | `→ load "input.json"` |

### utilities

| tool | description | example |
|------|-------------|---------|
| `wait` | wait seconds | `wait 5` |
| `shell` | run shell command | `shell "ls -la"` |
| `env` | read env var | `env "API_KEY"` |
| `now` | current timestamp | `→ now` |
| `uuid` | generate uuid | `→ uuid` |

## execution model

```
mesh source file
      ↓
  ┌───────────┐
  │  lexer     │  → token stream
  └─────┬─────┘
        ↓
  ┌───────────┐
  │  parser    │  → AST (directed graph of nodes)
  └─────┬─────┘
        ↓
  ┌───────────────┐
  │  resolver      │  → maps tool names to implementations
  └─────┬─────────┘
        ↓
  ┌───────────────┐
  │  executor      │  → runs the DAG
  │  - sequential  │     → pipes data left to right
  │  - parallel    │     → independent branches run concurrently
  │  - retry       │     → retries with backoff
  │  - error       │     → errors flow through, don't crash
  └─────┬─────────┘
        ↓
  ┌───────────────┐
  │  observability │  → structured log of every step
  └───────────────┘
```

## error model

errors in mesh are **data**, not exceptions. every step produces either:

```json
{"ok": true, "data": <value>}
{"ok": false, "error": "<message>", "step": "<tool_name>", "retryable": true}
```

the pipeline continues flowing. errors can be caught with `on_error:` and handled.

## examples

### monitor a service

```
# monitor.mesh
loop every 60s:
  check http.get "https://pokelabs.org/health"
    → timeout 10s
    → retry 2:
        http.get
    → if .status != 200:
        parallel:
          branch alert: telegram.send @thealxlabs "⚠️ pokelabs.org is down ({{.status}})"
          branch log:   log.error "health check failed: {{.status}}"
    → if .status == 200:
        log "pokelabs.org healthy ({{.response_time}}ms)"
```

### process github issues

```
# triage.mesh
import "./tools/ai.mesh"

fetch github.issues.pokelabshq.council
  → filter .state == "open"
  → for each issue:
      parallel:
        branch sentiment: ai.sentiment issue.title
        branch priority:  ai.classify issue.labels
      → merge
      → if .sentiment.label == "negative" and .priority == "high":
          slack.send "#alerts" "🚨 {{.issue.title}}"
      → otherwise:
          log "issue #{{.issue.number}}: {{.sentiment.label}}"
```

### daily briefing

```
# briefing.mesh
import "./tools/social.mesh"
import "./tools/github.mesh"

parallel:
  branch commits:  github.commits.pokelabshq.council.since:"1d"
  branch stars:    github.stars.pokelabshq.council
  branch mentions: twitter.mentions @thealxlabs.since:"1d"
→ merge
→ format as: |
    📊 daily briefing — {{now | format_date "Mon, 02 Jan 2006"}}

    📝 commits ({{.commits | count}}):
    {{.commits → map "  • {{.author}}: {{.message}}" → join "\n"}}

    ⭐ stars: {{.stars | count}} total

    🐦 mentions ({{.mentions | count}}):
    {{.mentions → map "  @{{.user}}: {{.text}}" → join "\n"}}
→ telegram.send @thealxlabs
```

## file structure

```
project/
  mesh.yaml          # project config
  main.mesh          # entry point
  tools/             # local tool definitions
    social.mesh
    github.mesh
  lib/               # reusable mesh modules
    format.mesh
    filters.mesh
```

## mesh.yaml

```yaml
name: my-project
version: 0.1.0
description: "what this project does"

tools:
  - name: sentiment
    url: http://localhost:8764
  - name: telegram
    token: "${TELEGRAM_TOKEN}"

defaults:
  retry: 3
  timeout: 30
  parallel: true
```

## comparison

| feature | yaml workflows | python scripts | mesh |
|---------|---------------|----------------|------|
| agent-readable | ✅ | ❌ | ✅ |
| tool-native | ⚠️ | ❌ | ✅ |
| error handling | ❌ | ✅ | ✅ |
| parallelism | ❌ | ✅ | ✅ |
| composability | ❌ | ✅ | ✅ |
| observability | ❌ | ❌ | ✅ |
| no boilerplate | ✅ | ❌ | ✅ |

## implementation

reference implementation: python 3.12, stdlib only.

```
mesh/
  parser.py      # lexer + parser
  ast.py         # node types
  resolver.py    # tool resolution
  executor.py    # DAG execution
  runtime.py     # built-in tools + registry
  cli.py         # `mesh run`, `mesh repl`, `mesh check`
  errors.py      # error types
```

## license

mit — poke labs
