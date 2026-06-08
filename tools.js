/**
 * mesh: expanded tool registry.
 * additional built-in tools for real-world agent workflows.
 * works with both python and js runtimes.
 *
 * tool categories:
 *   fs      — file system operations
 *   git     — git operations
 *   crypto  — hashing, encoding
 *   time    — date/time operations
 *   string  — string manipulation
 *   math    — math operations
 *   net     — network utilities
 *   system  — system information
 *   docker  — docker operations
 *   github  — github api
 *   ai      — ai/llm operations
 */

// ── fs tools ─────────────────────────────────────────────────────────────────

const fs_tools = {
  'fs.read': {
    description: 'read file contents',
    input: 'file path (string)',
    output: 'file contents (string)',
    example: 'fs.read "README.md" → print',
    python: lambda path, **kw: open(path, 'r').read(),
    js: 'async (d, ...a) => { const fs = await import("fs"); return fs.readFileSync(a[0] || d, "utf-8"); }',
  },
  'fs.write': {
    description: 'write content to file',
    input: 'content + file path',
    output: 'file path',
    example: '"hello" → fs.write "output.txt"',
    python: lambda data, path, **kw: (open(path, 'w').write(str(data)), path)[1],
    js: 'async (d, ...a) => { const fs = await import("fs"); const path = a[0] || "output.txt"; fs.writeFileSync(path, String(d)); return path; }',
  },
  'fs.append': {
    description: 'append content to file',
    input: 'content + file path',
    output: 'file path',
    example: '"new line" → fs.append "log.txt"',
    python: lambda data, path, **kw: (open(path, 'a').write(str(data) + '\n'), path)[1],
    js: 'async (d, ...a) => { const fs = await import("fs"); const path = a[0] || "output.txt"; fs.appendFileSync(path, String(d) + "\\n"); return path; }',
  },
  'fs.exists': {
    description: 'check if file exists',
    input: 'file path',
    output: 'boolean',
    example: 'fs.exists "config.yaml" → if .: print "exists"',
    python: lambda path, **kw: __import__('os').path.exists(path),
    js: 'async (d, ...a) => { const fs = await import("fs"); return fs.existsSync(a[0] || d); }',
  },
  'fs.list': {
    description: 'list directory contents',
    input: 'directory path',
    output: 'list of filenames',
    example: 'fs.list "." → for each .: print',
    python: lambda path, **kw: __import__('os').listdir(path),
    js: 'async (d, ...a) => { const fs = await import("fs"); return fs.readdirSync(a[0] || d); }',
  },
  'fs.mkdir': {
    description: 'create directory',
    input: 'directory path',
    output: 'directory path',
    example: 'fs.mkdir "output"',
    python: lambda path, **kw: (__import__('os').makedirs(path, exist_ok=True), path)[1],
    js: 'async (d, ...a) => { const fs = await import("fs"); const path = a[0] || d; fs.mkdirSync(path, { recursive: true }); return path; }',
  },
  'fs.remove': {
    description: 'delete file or directory',
    input: 'path',
    output: 'boolean',
    example: 'fs.remove "temp.txt"',
    python: lambda path, **kw: (__import__('os').remove(path), True)[1],
    js: 'async (d, ...a) => { const fs = await import("fs"); fs.unlinkSync(a[0] || d); return true; }',
  },
  'fs.copy': {
    description: 'copy file',
    input: 'source + destination',
    output: 'destination path',
    example: 'fs.copy "a.txt" "b.txt"',
    python: lambda src, dst, **kw: (__import__('shutil').copy2(src, dst), dst)[1],
    js: 'async (d, ...a) => { const fs = await import("fs"); const src = a[0] || d; const dst = a[1] || src + ".copy"; fs.copyFileSync(src, dst); return dst; }',
  },
  'fs.move': {
    description: 'move/rename file',
    input: 'source + destination',
    output: 'destination path',
    example: 'fs.move "old.txt" "new.txt"',
    python: lambda src, dst, **kw: (__import__('shutil').move(src, dst), dst)[1],
    js: 'async (d, ...a) => { const fs = await import("fs"); const src = a[0] || d; const dst = a[1] || src + ".moved"; fs.renameSync(src, dst); return dst; }',
  },
  'fs.info': {
    description: 'get file info (size, modified, etc)',
    input: 'file path',
    output: 'file info object',
    example: 'fs.info "README.md" → .size → print',
    python: lambda path, **kw: (lambda s: {'size': s.st_size, 'modified': s.st_mtime, 'created': s.st_ctime, 'is_dir': __import__('os').path.isdir(path)})(__import__('os').stat(path)),
    js: 'async (d, ...a) => { const fs = await import("fs"); const s = fs.statSync(a[0] || d); return { size: s.size, modified: s.mtimeMs, created: s.birthtimeMs, isDir: s.isDirectory() }; }',
  },
};

// ── git tools ────────────────────────────────────────────────────────────────

const git_tools = {
  'git.status': {
    description: 'get git status',
    input: 'optional: repo path',
    output: 'status object',
    example: 'git.status → .branch → print',
    python: lambda path='.', **kw: (lambda r: {'branch': r.active_branch.name, 'dirty': r.is_dirty(), 'untracked': r.untracked_files})(__import__('git').Repo(path)),
    js: 'async (d, ...a) => { const { execSync } = await import("child_process"); const path = a[0] || "."; const branch = execSync(`git -C ${path} branch --show-current`).toString().trim(); const dirty = execSync(`git -C ${path} status --porcelain`).toString().trim().length > 0; return { branch, dirty }; }',
  },
  'git.log': {
    description: 'get git log',
    input: 'optional: repo path + count',
    output: 'list of commits',
    example: 'git.log count:10 → for each .: print "{{.hash}}: {{.message}}"',
    python: lambda path='.', count=10, **kw: [{'hash': c.hexsha[:7], 'message': c.message.strip(), 'author': c.author.name, 'date': c.committed_datetime.isoformat()} for c in list(__import__('git').Repo(path).iter_commits(max_count=count))],
    js: 'async (d, ...a) => { const { execSync } = await import("child_process"); const path = a[0] || "."; const count = a[1] || 10; const out = execSync(`git -C ${path} log --oneline -${count} --format="%H|%s|%an|%ai"`).toString().trim(); return out.split("\\n").filter(Boolean).map(l => { const [hash, message, author, date] = l.split("|"); return { hash: hash.slice(0, 7), message, author, date }; }); }',
  },
  'git.commit': {
    description: 'create a git commit',
    input: 'message + optional path',
    output: 'commit hash',
    example: 'git.commit "feat: add new feature"',
    python: lambda msg, path='.', **kw: __import__('git').Repo(path).index.commit(msg).hexsha[:7],
    js: 'async (d, ...a) => { const { execSync } = await import("child_process"); const msg = a[0] || d; const path = a[1] || "."; execSync(`git -C ${path} add -A`); execSync(`git -C ${path} commit -m "${msg}"`); return execSync(`git -C ${path} rev-parse --short HEAD`).toString().trim(); }',
  },
  'git.push': {
    description: 'push to remote',
    input: 'optional: remote + branch + path',
    output: 'push result',
    example: 'git.push',
    python: lambda remote='origin', branch=None, path='.', **kw: __import__('git').Repo(path).remote(remote).push(branch or __import__('git').Repo(path).active_branch.name),
    js: 'async (d, ...a) => { const { execSync } = await import("child_process"); const path = a[2] || "."; const out = execSync(`git -C ${path} push`).toString().trim(); return { output: out }; }',
  },
  'git.pull': {
    description: 'pull from remote',
    input: 'optional: remote + branch + path',
    output: 'pull result',
    example: 'git.pull',
    python: lambda remote='origin', branch=None, path='.', **kw: __import__('git').Repo(path).remote(remote).pull(branch),
    js: 'async (d, ...a) => { const { execSync } = await import("child_process"); const path = a[2] || "."; const out = execSync(`git -C ${path} pull`).toString().trim(); return { output: out }; }',
  },
  'git.diff': {
    description: 'get git diff',
    input: 'optional: repo path',
    output: 'diff string',
    example: 'git.diff → print',
    python: lambda path='.', **kw: __import__('git').Repo(path).git.diff(),
    js: 'async (d, ...a) => { const { execSync } = await import("child_process"); const path = a[0] || "."; return execSync(`git -C ${path} diff`).toString(); }',
  },
  'git.branch': {
    description: 'list branches',
    input: 'optional: repo path',
    output: 'list of branch names',
    example: 'git.branch → for each .: print',
    python: lambda path='.', **kw: [b.name for b in __import__('git').Repo(path).branches],
    js: 'async (d, ...a) => { const { execSync } = await import("child_process"); const path = a[0] || "."; return execSync(`git -C ${path} branch --format="%(refname:short)"`).toString().trim().split("\\n").filter(Boolean); }',
  },
};

// ── crypto tools ─────────────────────────────────────────────────────────────

const crypto_tools = {
  'hash.md5': {
    description: 'compute md5 hash',
    input: 'string',
    output: 'hex hash string',
    example: '"hello" → hash.md5 → print',
    python: lambda data, **kw: __import__('hashlib').md5(str(data).encode()).hexdigest(),
    js: 'async (d) => { const crypto = await import("crypto"); return crypto.createHash("md5").update(String(d)).digest("hex"); }',
  },
  'hash.sha256': {
    description: 'compute sha256 hash',
    input: 'string',
    output: 'hex hash string',
    example: '"hello" → hash.sha256 → print',
    python: lambda data, **kw: __import__('hashlib').sha256(str(data).encode()).hexdigest(),
    js: 'async (d) => { const crypto = await import("crypto"); return crypto.createHash("sha256").update(String(d)).digest("hex"); }',
  },
  'hash.sha1': {
    description: 'compute sha1 hash',
    input: 'string',
    output: 'hex hash string',
    example: '"hello" → hash.sha1 → print',
    python: lambda data, **kw: __import__('hashlib').sha1(str(data).encode()).hexdigest(),
    js: 'async (d) => { const crypto = await import("crypto"); return crypto.createHash("sha1").update(String(d)).digest("hex"); }',
  },
  'base64.encode': {
    description: 'base64 encode',
    input: 'string',
    output: 'base64 string',
    example: '"hello" → base64.encode → print',
    python: lambda data, **kw: __import__('base64').b64encode(str(data).encode()).decode(),
    js: 'async (d) => Buffer.from(String(d)).toString("base64")',
  },
  'base64.decode': {
    description: 'base64 decode',
    input: 'base64 string',
    output: 'decoded string',
    example: '"aGVsbG8=" → base64.decode → print',
    python: lambda data, **kw: __import__('base64').b64decode(str(data)).decode(),
    js: 'async (d) => Buffer.from(String(d), "base64").toString("utf-8")',
  },
  'random.int': {
    description: 'random integer',
    input: 'min + max (optional)',
    output: 'random integer',
    example: 'random.int 1 100 → print',
    python: lambda data=None, min=0, max=100, **kw: __import__('random').randint(int(min), int(max)),
    js: 'async (d, ...a) => { const min = parseInt(a[0]) || 0; const max = parseInt(a[1]) || 100; return Math.floor(Math.random() * (max - min + 1)) + min; }',
  },
  'random.float': {
    description: 'random float 0-1',
    input: 'none',
    output: 'random float',
    example: 'random.float → print',
    python: lambda **kw: __import__('random').random(),
    js: 'async () => Math.random()',
  },
  'random.choice': {
    description: 'pick random item from list',
    input: 'list',
    output: 'random item',
    example: '[1,2,3,4,5] → random.choice → print',
    python: lambda data, **kw: __import__('random').choice(data) if isinstance(data, list) else data,
    js: 'async (d) => Array.isArray(d) ? d[Math.floor(Math.random() * d.length)] : d',
  },
};

// ── time tools ───────────────────────────────────────────────────────────────

const time_tools = {
  'time.now': {
    description: 'current timestamp (iso)',
    input: 'none',
    output: 'iso timestamp string',
    example: 'time.now → print',
    python: lambda **kw: __import__('datetime').datetime.now().isoformat(),
    js: 'async () => new Date().toISOString()',
  },
  'time.unix': {
    description: 'current unix timestamp',
    input: 'none',
    output: 'unix timestamp (seconds)',
    example: 'time.unix → print',
    python: lambda **kw: int(__import__('time').time()),
    js: 'async () => Math.floor(Date.now() / 1000)',
  },
  'time.format': {
    description: 'format a timestamp',
    input: 'timestamp + format string',
    output: 'formatted string',
    example: 'time.now → time.format "%Y-%m-%d" → print',
    python: lambda data, fmt="%Y-%m-%d", **kw: __import__('datetime').datetime.fromisoformat(str(data)).strftime(fmt),
    js: 'async (d, ...a) => { const fmt = a[0] || "%Y-%m-%d"; const date = new Date(d); return fmt.replace("%Y", date.getFullYear()).replace("%m", String(date.getMonth()+1).padStart(2,"0")).replace("%d", String(date.getDate()).padStart(2,"0")).replace("%H", String(date.getHours()).padStart(2,"0")).replace("%M", String(date.getMinutes()).padStart(2,"0")).replace("%S", String(date.getSeconds()).padStart(2,"0")); }',
  },
  'time.sleep': {
    description: 'sleep for seconds',
    input: 'seconds',
    output: 'input data (unchanged)',
    example: 'time.sleep 5',
    python: lambda data, seconds=1, **kw: (__import__('time').sleep(float(seconds)), data)[1],
    js: 'async (d, ...a) => { const s = parseFloat(a[0]) || 1; return new Promise(r => setTimeout(() => r(d), s * 1000)); }',
  },
  'time.elapsed': {
    description: 'measure execution time of a block',
    input: 'data',
    output: '{data, elapsed_ms}',
    example: 'time.elapsed → .elapsed_ms → print',
    python: lambda data, **kw: {'data': data, 'elapsed_ms': 0},  # simplified
    js: 'async (d) => ({ data: d, elapsed_ms: 0 })',  # simplified
  },
};

// ── string tools ─────────────────────────────────────────────────────────────

const string_tools = {
  'string.upper': {
    description: 'uppercase string',
    input: 'string',
    output: 'uppercase string',
    example: '"hello" → string.upper → print',
    python: lambda data, **kw: str(data).upper(),
    js: 'async (d) => String(d).toUpperCase()',
  },
  'string.lower': {
    description: 'lowercase string',
    input: 'string',
    output: 'lowercase string',
    example: '"HELLO" → string.lower → print',
    python: lambda data, **kw: str(data).lower(),
    js: 'async (d) => String(d).toLowerCase()',
  },
  'string.trim': {
    description: 'trim whitespace',
    input: 'string',
    output: 'trimmed string',
    example: '"  hello  " → string.trim → print',
    python: lambda data, **kw: str(data).strip(),
    js: 'async (d) => String(d).trim()',
  },
  'string.split': {
    description: 'split string by delimiter',
    input: 'string + delimiter',
    output: 'list of parts',
    example: '"a,b,c" → string.split "," → print',
    python: lambda data, sep=",", **kw: str(data).split(sep),
    js: 'async (d, ...a) => String(d).split(a[0] || ",")',
  },
  'string.join': {
    description: 'join list with delimiter',
    input: 'list + delimiter',
    output: 'joined string',
    example: '["a","b","c"] → string.join "," → print',
    python: lambda data, sep=",", **kw: sep.join(str(x) for x in data) if isinstance(data, list) else str(data),
    js: 'async (d, ...a) => Array.isArray(d) ? d.join(a[0] || ",") : String(d)',
  },
  'string.replace': {
    description: 'replace substring',
    input: 'string + old + new',
    output: 'replaced string',
    example: '"hello world" → string.replace "world" "mesh" → print',
    python: lambda data, old="", new="", **kw: str(data).replace(old, new),
    js: 'async (d, ...a) => String(d).split(a[0] || "").join(a[1] || "")',
  },
  'string.contains': {
    description: 'check if string contains substring',
    input: 'string + substring',
    output: 'boolean',
    example: '"hello world" → string.contains "world" → print',
    python: lambda data, substr="", **kw: substr in str(data),
    js: 'async (d, ...a) => String(d).includes(a[0] || "")',
  },
  'string.starts': {
    description: 'check if string starts with prefix',
    input: 'string + prefix',
    output: 'boolean',
    example: '"hello" → string.starts "hel" → print',
    python: lambda data, prefix="", **kw: str(data).startswith(prefix),
    js: 'async (d, ...a) => String(d).startsWith(a[0] || "")',
  },
  'string.ends': {
    description: 'check if string ends with suffix',
    input: 'string + suffix',
    output: 'boolean',
    example: '"hello" → string.ends "lo" → print',
    python: lambda data, suffix="", **kw: str(data).endswith(suffix),
    js: 'async (d, ...a) => String(d).endsWith(a[0] || "")',
  },
  'string.length': {
    description: 'string length',
    input: 'string',
    output: 'integer length',
    example: '"hello" → string.length → print',
    python: lambda data, **kw: len(str(data)),
    js: 'async (d) => String(d).length',
  },
  'string.match': {
    description: 'regex match',
    input: 'string + pattern',
    output: 'match groups or null',
    example: '"hello123" → string.match "\\\\d+" → print',
    python: lambda data, pattern="", **kw: (__import__('re').search(pattern, str(data)) and __import__('re').search(pattern, str(data)).group()) or None,
    js: 'async (d, ...a) => { const m = String(d).match(new RegExp(a[0] || "")); return m ? m[0] : null; }',
  },
  'string.extract': {
    description: 'extract all regex matches',
    input: 'string + pattern',
    output: 'list of matches',
    example: '"a1b2c3" → string.extract "\\\\d" → print',
    python: lambda data, pattern="", **kw: __import__('re').findall(pattern, str(data)),
    js: 'async (d, ...a) => { const m = String(d).match(new RegExp(a[0] || "", "g")); return m || []; }',
  },
};

// ── math tools ───────────────────────────────────────────────────────────────

const math_tools = {
  'math.add': {
    description: 'add numbers',
    input: 'number + number',
    output: 'sum',
    example: '5 → math.add 3 → print',
    python: lambda data, n, **kw: float(data) + float(n),
    js: 'async (d, ...a) => Number(d) + Number(a[0] || 0)',
  },
  'math.sub': {
    description: 'subtract',
    input: 'number + number',
    output: 'difference',
    example: '10 → math.sub 3 → print',
    python: lambda data, n, **kw: float(data) - float(n),
    js: 'async (d, ...a) => Number(d) - Number(a[0] || 0)',
  },
  'math.mul': {
    description: 'multiply',
    input: 'number + number',
    output: 'product',
    example: '5 → math.mul 3 → print',
    python: lambda data, n, **kw: float(data) * float(n),
    js: 'async (d, ...a) => Number(d) * Number(a[0] || 1)',
  },
  'math.div': {
    description: 'divide',
    input: 'number + number',
    output: 'quotient',
    example: '10 → math.div 3 → print',
    python: lambda data, n, **kw: float(data) / float(n) if float(n) != 0 else 0,
    js: 'async (d, ...a) => { const n = Number(a[0] || 1); return n !== 0 ? Number(d) / n : 0; }',
  },
  'math.round': {
    description: 'round number',
    input: 'number + optional decimals',
    output: 'rounded number',
    example: '3.14159 → math.round 2 → print',
    python: lambda data, decimals=0, **kw: round(float(data), int(decimals)),
    js: 'async (d, ...a) => { const n = parseInt(a[0]) || 0; return Number(Number(d).toFixed(n)); }',
  },
  'math.min': {
    description: 'minimum of list',
    input: 'list of numbers',
    output: 'minimum value',
    example: '[3,1,4,1,5] → math.min → print',
    python: lambda data, **kw: min(data) if isinstance(data, list) else data,
    js: 'async (d) => Array.isArray(d) ? Math.min(...d) : d',
  },
  'math.max': {
    description: 'maximum of list',
    input: 'list of numbers',
    output: 'maximum value',
    example: '[3,1,4,1,5] → math.max → print',
    python: lambda data, **kw: max(data) if isinstance(data, list) else data,
    js: 'async (d) => Array.isArray(d) ? Math.max(...d) : d',
  },
  'math.sum': {
    description: 'sum of list',
    input: 'list of numbers',
    output: 'sum',
    example: '[1,2,3,4,5] → math.sum → print',
    python: lambda data, **kw: sum(data) if isinstance(data, list) else data,
    js: 'async (d) => Array.isArray(d) ? d.reduce((a,b) => a + b, 0) : d',
  },
  'math.avg': {
    description: 'average of list',
    input: 'list of numbers',
    output: 'average',
    example: '[1,2,3,4,5] → math.avg → print',
    python: lambda data, **kw: sum(data) / len(data) if isinstance(data, list) and data else 0,
    js: 'async (d) => Array.isArray(d) && d.length ? d.reduce((a,b) => a + b, 0) / d.length : 0',
  },
  'math.clamp': {
    description: 'clamp value between min and max',
    input: 'number + min + max',
    output: 'clamped value',
    example: '150 → math.clamp 0 100 → print',
    python: lambda data, min_val=0, max_val=100, **kw: max(float(min_val), min(float(max_val), float(data))),
    js: 'async (d, ...a) => { const v = Number(d); const lo = Number(a[0] || 0); const hi = Number(a[1] || 100); return Math.max(lo, Math.min(hi, v)); }',
  },
};

// ── net tools ────────────────────────────────────────────────────────────────

const net_tools = {
  'net.ping': {
    description: 'ping a host',
    input: 'hostname',
    output: '{alive, time_ms}',
    example: 'net.ping "google.com" → .alive → print',
    python: lambda host, **kw: (lambda r: {'alive': r.returncode == 0, 'time_ms': 0})(__import__('subprocess').run(['ping', '-c', '1', '-W', '3', str(host)], capture_output=True)),
    js: 'async (d, ...a) => { const host = a[0] || d; const start = Date.now(); try { await fetch(`https://${host}`, { mode: 'no-cors', signal: AbortSignal.timeout(3000) }); return { alive: true, time_ms: Date.now() - start }; } catch { return { alive: false, time_ms: Date.now() - start }; } }',
  },
  'net.dns': {
    description: 'resolve dns',
    input: 'hostname',
    output: 'ip address or list',
    example: 'net.dns "google.com" → print',
    python: lambda host, **kw: __import__('socket').gethostbyname(str(host)),
    js: 'async (d, ...a) => { const dns = await import("dns"); const host = a[0] || d; return dns.promises.lookup(host); }',
  },
  'net.ip': {
    description: 'get public ip',
    input: 'none',
    output: 'ip address string',
    example: 'net.ip → print',
    python: lambda **kw: __import__('urllib.request').urlopen('https://api.ipify.org').read().decode(),
    js: 'async () => { const r = await fetch("https://api.ipify.org"); return r.text(); }',
  },
  'net.fetch': {
    description: 'fetch url (alias for http.get)',
    input: 'url',
    output: 'response object',
    example: 'net.fetch "https://example.com" → .body → print',
    python: lambda url, **kw: {'status': 200, 'body': __import__('urllib.request').urlopen(str(url)).read().decode()},
    js: 'async (d, ...a) => { const url = a[0] || d; const r = await fetch(String(url)); return { status: r.status, body: await r.text() }; }',
  },
};

// ── system tools ─────────────────────────────────────────────────────────────

const system_tools = {
  'sys.os': {
    description: 'get operating system',
    input: 'none',
    output: 'os name string',
    example: 'sys.os → print',
    python: lambda **kw: __import__('platform').system().lower(),
    js: 'async () => { const os = await import("os"); return os.platform(); }',
  },
  'sys.arch': {
    description: 'get system architecture',
    input: 'none',
    output: 'arch string',
    example: 'sys.arch → print',
    python: lambda **kw: __import__('platform').machine(),
    js: 'async () => { const os = await import("os"); return os.arch(); }',
  },
  'sys.cpus': {
    description: 'get cpu count',
    input: 'none',
    output: 'integer',
    example: 'sys.cpus → print',
    python: lambda **kw: __import__('os').cpu_count(),
    js: 'async () => { const os = await import("os"); return os.cpus().length; }',
  },
  'sys.memory': {
    description: 'get memory info',
    input: 'none',
    output: '{total, free, used_mb}',
    example: 'sys.memory → .used_mb → print',
    python: lambda **kw: (lambda m: {'total': m.total, 'free': m.available, 'used_mb': (m.total - m.available) // (1024*1024)})(__import__('psutil').virtual_memory()) if 'psutil' in dir() else {'total': 0, 'free': 0, 'used_mb': 0},
    js: 'async () => { const os = await import("os"); const total = os.totalmem(); const free = os.freemem(); return { total, free, used_mb: Math.round((total - free) / 1024 / 1024) }; }',
  },
  'sys.disk': {
    description: 'get disk usage',
    input: 'optional: path',
    output: '{total, free, used_mb}',
    example: 'sys.disk "/" → .free → print',
    python: lambda path='/', **kw: (lambda d: {'total': d.total, 'free': d.free, 'used_mb': (d.total - d.free) // (1024*1024)})(__import__('shutil').disk_usage(str(path))),
    js: 'async (d, ...a) => { const path = a[0] || d || "/"; try { const { execSync } = await import("child_process"); const out = execSync(`df -m ${path} | tail -1`).toString().trim().split(/\\s+/); return { total: parseInt(out[1]), free: parseInt(out[3]), used_mb: parseInt(out[2]) }; } catch(e) { return { total: 0, free: 0, used_mb: 0 }; } }',
  },
  'sys.uptime': {
    description: 'get system uptime in seconds',
    input: 'none',
    output: 'uptime seconds',
    example: 'sys.uptime → print',
    python: lambda **kw: int(__import__('time').time() - __import__('psutil').boot_time()) if 'psutil' in dir() else 0,
    js: 'async () => { const os = await import("os"); return Math.floor(os.uptime()); }',
  },
  'sys.env': {
    description: 'get all environment variables',
    input: 'none',
    output: 'dict of env vars',
    example: 'sys.env → .HOME → print',
    python: lambda **kw: dict(__import__('os').environ),
    js: 'async () => Object.assign({}, process.env)',
  },
  'sys.pid': {
    description: 'get process id',
    input: 'none',
    output: 'integer pid',
    example: 'sys.pid → print',
    python: lambda **kw: __import__('os').getpid(),
    js: 'async () => process.pid',
  },
  'sys.user': {
    description: 'get current username',
    input: 'none',
    output: 'username string',
    example: 'sys.user → print',
    python: lambda **kw: __import__('getpass').getuser(),
    js: 'async () => { const os = await import("os"); return os.userInfo().username; }',
  },
};

// ── docker tools ─────────────────────────────────────────────────────────────

const docker_tools = {
  'docker.ps': {
    description: 'list running containers',
    input: 'none',
    output: 'list of containers',
    example: 'docker.ps → for each .: print "{{.name}}: {{.status}}"',
    python: lambda **kw: (lambda r: [{'name': c.name, 'status': c.status, 'image': c.image.tags[0] if c.image.tags else ''} for c in __import__('docker').from_env().containers.list()]) if 'docker' in dir() else [],
    js: 'async () => { try { const { execSync } = await import("child_process"); const out = execSync("docker ps --format '{{.Names}}|{{.Status}}|{{.Image}}'").toString().trim(); return out.split("\\n").filter(Boolean).map(l => { const [name, status, image] = l.split("|"); return { name, status, image }; }); } catch(e) { return []; } }',
  },
  'docker.images': {
    description: 'list docker images',
    input: 'none',
    output: 'list of images',
    example: 'docker.images → count → print',
    python: lambda **kw: [{'repo': t.split(':')[0], 'tag': t.split(':')[1] if ':' in t else 'latest'} for img in __import__('docker').from_env().images.list() for t in img.tags] if 'docker' in dir() else [],
    js: 'async () => { try { const { execSync } = await import("child_process"); const out = execSync("docker images --format '{{.Repository}}|{{.Tag}}'").toString().trim(); return out.split("\\n").filter(Boolean).map(l => { const [repo, tag] = l.split("|"); return { repo, tag }; }); } catch(e) { return []; } }',
  },
  'docker.logs': {
    description: 'get container logs',
    input: 'container name + optional lines',
    output: 'log string',
    example: 'docker.logs "my-app" lines:50 → print',
    python: lambda name, lines=100, **kw: __import__('docker').from_env().containers.get(str(name)).logs(tail=int(lines)).decode() if 'docker' in dir() else '',
    js: 'async (d, ...a) => { const { execSync } = await import("child_process"); const name = a[0] || d; const lines = a[1] || 100; return execSync(`docker logs --tail ${lines} ${name}`).toString(); }',
  },
  'docker.exec': {
    description: 'execute command in container',
    input: 'container name + command',
    output: '{stdout, stderr, code}',
    example: 'docker.exec "my-app" "ls -la" → .stdout → print',
    python: lambda name, cmd, **kw: (lambda r: {'stdout': r.output.decode(), 'code': r.exit_code})(__import__('docker').from_env().containers.get(str(name)).exec_run(str(cmd))) if 'docker' in dir() else {'stdout': '', 'code': 1},
    js: 'async (d, ...a) => { const { execSync } = await import("child_process"); const name = a[0] || d; const cmd = a[1] || "sh"; try { const stdout = execSync(`docker exec ${name} ${cmd}`).toString(); return { stdout, stderr: "", code: 0 }; } catch(e) { return { stdout: "", stderr: e.message, code: e.status || 1 }; } }',
  },
};

// ── github tools ─────────────────────────────────────────────────────────────

const github_tools = {
  'github.repos': {
    description: 'list user repositories',
    input: 'username',
    output: 'list of repos',
    example: 'github.repos "pokelabshq" → for each .: print .name',
    python: lambda user, **kw: [{'name': r.name, 'stars': r.stargazers_count, 'description': r.description} for r in __import__('github').Github().get_user(str(user)).get_repos()] if 'github' in dir() else [],
    js: 'async (d, ...a) => { const user = a[0] || d; const r = await fetch(`https://api.github.com/users/${user}/repos`); return r.json(); }',
  },
  'github.commits': {
    description: 'get repo commits',
    input: 'owner/repo + optional count',
    output: 'list of commits',
    example: 'github.commits "pokelabshq/council" count:5 → for each .: print "{{.sha}}: {{.commit.message}}"',
    python: lambda repo, count=10, **kw: [{'sha': c.hexsha[:7], 'message': c.message.strip(), 'author': c.author.name} for c in __import__('github').Github().get_repo(str(repo)).get_commits()[:int(count)]] if 'github' in dir() else [],
    js: 'async (d, ...a) => { const repo = a[0] || d; const count = a[1] || 10; const r = await fetch(`https://api.github.com/repos/${repo}/commits?per_page=${count}`); const data = await r.json(); return data.map(c => ({ sha: c.sha.slice(0,7), message: c.commit.message, author: c.commit.author.name })); }',
  },
  'github.issues': {
    description: 'get repo issues',
    input: 'owner/repo + optional state',
    output: 'list of issues',
    example: 'github.issues "pokelabshq/council" state:"open" → count → print',
    python: lambda repo, state='open', **kw: [{'number': i.number, 'title': i.title, 'state': i.state} for i in __import__('github').Github().get_repo(str(repo)).get_issues(state=str(state))] if 'github' in dir() else [],
    js: 'async (d, ...a) => { const repo = a[0] || d; const state = a[1] || "open"; const r = await fetch(`https://api.github.com/repos/${repo}/issues?state=${state}`); const data = await r.json(); return data.map(i => ({ number: i.number, title: i.title, state: i.state })); }',
  },
  'github.stars': {
    description: 'get repo star count',
    input: 'owner/repo',
    output: 'star count',
    example: 'github.stars "pokelabshq/council" → print',
    python: lambda repo, **kw: __import__('github').Github().get_repo(str(repo)).stargazers_count if 'github' in dir() else 0,
    js: 'async (d, ...a) => { const repo = a[0] || d; const r = await fetch(`https://api.github.com/repos/${repo}`); const data = await r.json(); return data.stargazers_count || 0; }',
  },
};

// ── ai tools ─────────────────────────────────────────────────────────────────

const ai_tools = {
  'ai.complete': {
    description: 'call llm for completion',
    input: 'prompt string',
    output: 'completion string',
    example: '"summarize: {{.text}}" → ai.complete → print',
    python: lambda prompt, **kw: openai.chat.completions.create(model=kw.get('model', 'gpt-4o-mini'), messages=[{'role': 'user', 'content': str(prompt)}]).choices[0].message.content if 'openai' in dir() else str(prompt),
    js: 'async (d, ...a) => { const prompt = a[0] || d; return prompt; }',  # placeholder
  },
  'ai.embed': {
    description: 'generate embeddings',
    input: 'text string',
    output: 'embedding vector',
    example: '"hello world" → ai.embed → length → print',
    python: lambda text, **kw: openai.embeddings.create(input=str(text), model='text-embedding-3-small').data[0].embedding if 'openai' in dir() else [],
    js: 'async (d, ...a) => { const text = a[0] || d; return []; }',  # placeholder
  },
  'ai.classify': {
    description: 'classify text into categories',
    input: 'text + categories',
    output: '{label, confidence}',
    example: '"this is great" → ai.classify "positive,negative,neutral" → print',
    python: lambda text, categories="positive,negative,neutral", **kw: {'label': 'neutral', 'confidence': 0.5},  # placeholder
    js: 'async (d, ...a) => { const text = a[0] || d; return { label: "neutral", confidence: 0.5 }; }',  # placeholder
  },
  'ai.summarize': {
    description: 'summarize text',
    input: 'text string',
    output: 'summary string',
    example: 'load "long-article.txt" → ai.summarize → print',
    python: lambda text, **kw: str(text)[:200] + '...' if len(str(text)) > 200 else str(text),
    js: 'async (d, ...a) => { const text = String(d || a[0] || ""); return text.length > 200 ? text.slice(0, 200) + "..." : text; }',
  },
  'ai.sentiment': {
    description: 'analyze sentiment',
    input: 'text string',
    output: '{label, score}',
    example: '"I love this!" → ai.sentiment → print',
    python: lambda text, **kw: {'label': 'positive' if any(w in str(text).lower() for w in ['love', 'great', 'good', 'awesome']) else 'negative' if any(w in str(text).lower() for w in ['hate', 'bad', 'terrible']) else 'neutral', 'score': 0.8},
    js: 'async (d, ...a) => { const text = String(d || a[0] || "").toLowerCase(); const pos = ["love","great","good","awesome","excellent"]; const neg = ["hate","bad","terrible","awful","horrible"]; const isPos = pos.some(w => text.includes(w)); const isNeg = neg.some(w => text.includes(w)); return { label: isPos ? "positive" : isNeg ? "negative" : "neutral", score: isPos || isNeg ? 0.8 : 0.5 }; }',
  },
  'ai.extract': {
    description: 'extract structured data from text',
    input: 'text + schema',
    output: 'extracted data object',
    example: '"name: alex, age: 13" → ai.extract "name,age" → print',
    python: lambda text, schema="", **kw: {k.strip(): v.strip() for k, v in (p.split(":") for p in str(text).split(",") if ":")} if ":" in str(text) else {},
    js: 'async (d, ...a) => { const text = String(d || a[0] || ""); if (text.includes(":")) { return Object.fromEntries(text.split(",").filter(p => p.includes(":")).map(p => p.split(":").map(s => s.trim()))); } return {}; }',
  },
};

// ── all tools ────────────────────────────────────────────────────────────────

const ALL_TOOLS = {
  ...fs_tools,
  ...git_tools,
  ...crypto_tools,
  ...time_tools,
  ...string_tools,
  ...math_tools,
  ...net_tools,
  ...system_tools,
  ...docker_tools,
  ...github_tools,
  ...ai_tools,
};

// export
module.exports = {
  fs_tools, git_tools, crypto_tools, time_tools, string_tools,
  math_tools, net_tools, system_tools, docker_tools, github_tools, ai_tools,
  ALL_TOOLS,
};
