# mesh

a flow-based programming language for ai agents.

## what is mesh

mesh is designed from the ground up for how agents think:

- **no state** — no variables, no mutation. data flows through pipes.
- **everything is a tool** — built-in and external tools are the same kind of thing.
- **errors are data** — failures flow through, they don't crash the pipeline.
- **parallel by default** — independent operations run concurrently.
- **self-describing** — every mesh program documents itself.

## quick start

```bash
# run a mesh file
mesh run examples/hello.mesh

# check syntax
mesh check examples/hello.mesh

# interactive repl
mesh repl

# list available tools
mesh --tools
```

## example

```mesh
# hello.mesh — fetch data, transform, output

http.get "https://api.github.com/repos/pokelabshq/council/commits"
  → json.parse
  → .[:3]
  → for each commit:
      format "{{.author.login}}: {{.commit.message}}"
  → print
```

## syntax

```
# pipeline
tool_call arg1 key=value
  → next_tool
  → .field[:5]
  → print

# conditionals
check http.get "https://example.com/health"
  → if .status != 200:
      alert "down"

# parallel
parallel:
  branch a: fetch "url/a"
  branch b: fetch "url/b"
  → merge
  → print

# retry
retry 3, backoff 2s:
  http.get "https://flaky-api.example.com"
  → on_error:
      log "failed after retries"
      return {error: true}
```

## language spec

see [SPEC.md](SPEC.md)  
website: [mesh.pokelabs.org](https://mesh.pokelabs.org)  
full docs: [docs.md](https://github.com/pokelabshq/mesh-website/blob/main/docs.md) for the full language specification.

## built-in tools

| category | tools |
|----------|-------|
| data | `json.parse`, `json.stringify`, `format`, `type`, `string`, `number` |
| http | `http.get`, `http.post` |
| collections | `filter`, `map`, `reduce`, `sort`, `unique`, `flatten`, `take`, `skip`, `count`, `first`, `last`, `merge`, `length`, `keys`, `values` |
| flow | `print`, `log`, `return`, `wait`, `if`, `for`, `retry`, `parallel` |
| system | `env`, `shell`, `now`, `uuid`, `save`, `load` |

## installation

```bash
git clone https://github.com/pokelabshq/mesh.git
cd mesh
python3 mesh.py --repl
```

## license

mit — poke labs
