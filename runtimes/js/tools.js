/**
 * mesh: expanded javascript tool registry.
 * 80+ built-in tools for real-world agent workflows.
 *
 * categories: fs, git, crypto, time, string, math, net, system, docker, github, ai
 */

// ── helpers ───────────────────────────────────────────────────────────────────

const readStdin = () => {
  return new Promise(resolve => {
    let data = '';
    process.stdin.setEncoding('utf8');
    process.stdin.on('data', chunk => data += chunk);
    process.stdin.on('end', () => resolve(data.trim()));
  });
};

// ── fs tools ─────────────────────────────────────────────────────────────────

const fs = {
  'fs.read': async (d, ...a) => {
    const fs = await import('fs');
    return fs.readFileSync(a[0] || d, 'utf-8');
  },
  'fs.write': async (d, ...a) => {
    const fs = await import('fs');
    const path = a[0] || 'output.txt';
    fs.writeFileSync(path, String(d));
    return path;
  },
  'fs.append': async (d, ...a) => {
    const fs = await import('fs');
    const path = a[0] || 'output.txt';
    fs.appendFileSync(path, String(d) + '\n');
    return path;
  },
  'fs.exists': async (d, ...a) => {
    const fs = await import('fs');
    return fs.existsSync(a[0] || d);
  },
  'fs.list': async (d, ...a) => {
    const fs = await import('fs');
    return fs.readdirSync(a[0] || d || '.');
  },
  'fs.mkdir': async (d, ...a) => {
    const fs = await import('fs');
    const path = a[0] || d;
    fs.mkdirSync(path, { recursive: true });
    return path;
  },
  'fs.remove': async (d, ...a) => {
    const fs = await import('fs');
    fs.unlinkSync(a[0] || d);
    return true;
  },
  'fs.copy': async (d, ...a) => {
    const fs = await import('fs');
    const src = a[0] || d;
    const dst = a[1] || src + '.copy';
    fs.copyFileSync(src, dst);
    return dst;
  },
  'fs.move': async (d, ...a) => {
    const fs = await import('fs');
    const src = a[0] || d;
    const dst = a[1] || src + '.moved';
    fs.renameSync(src, dst);
    return dst;
  },
  'fs.info': async (d, ...a) => {
    const fs = await import('fs');
    const s = fs.statSync(a[0] || d);
    return { size: s.size, modified: s.mtimeMs, created: s.birthtimeMs, isDir: s.isDirectory() };
  },
  'fs.readdir': async (d, ...a) => {
    const fs = await import('fs');
    return fs.readdirSync(a[0] || d || '.', { withFileTypes: true })
      .map(e => ({ name: e.name, isDir: e.isDirectory(), isFile: e.isFile() }));
  },
  'fs.glob': async (d, ...a) => {
    const fs = await import('fs');
    const path = await import('path');
    const pattern = a[0] || d || '*';
    const dir = a[1] || '.';
    const entries = fs.readdirSync(dir);
    const regex = new RegExp('^' + pattern.replace(/\*/g, '.*').replace(/\?/g, '.') + '$');
    return entries.filter(e => regex.test(e));
  },
};

// ── git tools ────────────────────────────────────────────────────────────────

const git = {
  'git.status': async (d, ...a) => {
    const { execSync } = await import('child_process');
    const dir = a[0] || '.';
    const branch = execSync(`git -C ${dir} branch --show-current`).toString().trim();
    const dirty = execSync(`git -C ${dir} status --porcelain`).toString().trim().length > 0;
    const untracked = execSync(`git -C ${dir} ls-files --others --exclude-standard`).toString().trim().split('\n').filter(Boolean);
    return { branch, dirty, untracked: untracked.length };
  },
  'git.log': async (d, ...a) => {
    const { execSync } = await import('child_process');
    const dir = a[0] || '.';
    const count = a[1] || 10;
    const out = execSync(`git -C ${dir} log --oneline -${count} --format="%H|%s|%an|%ai"`).toString().trim();
    return out ? out.split('\n').map(l => {
      const [hash, message, author, date] = l.split('|');
      return { hash: hash.slice(0, 7), message, author, date };
    }) : [];
  },
  'git.commit': async (d, ...a) => {
    const { execSync } = await import('child_process');
    const msg = a[0] || d;
    const dir = a[1] || '.';
    execSync(`git -C ${dir} add -A`);
    execSync(`git -C ${dir} commit -m "${msg.replace(/"/g, '\\"')}"`);
    return execSync(`git -C ${dir} rev-parse --short HEAD`).toString().trim();
  },
  'git.push': async (d, ...a) => {
    const { execSync } = await import('child_process');
    const dir = a[2] || '.';
    return execSync(`git -C ${dir} push`).toString().trim();
  },
  'git.pull': async (d, ...a) => {
    const { execSync } = await import('child_process');
    const dir = a[2] || '.';
    return execSync(`git -C ${dir} pull`).toString().trim();
  },
  'git.diff': async (d, ...a) => {
    const { execSync } = await import('child_process');
    const dir = a[0] || '.';
    return execSync(`git -C ${dir} diff`).toString();
  },
  'git.branch': async (d, ...a) => {
    const { execSync } = await import('child_process');
    const dir = a[0] || '.';
    return execSync(`git -C ${dir} branch --format="%(refname:short)"`).toString().trim().split('\n').filter(Boolean);
  },
  'git.clone': async (d, ...a) => {
    const { execSync } = await import('child_process');
    const url = a[0] || d;
    const dir = a[1] || '.';
    return execSync(`git clone ${url} ${dir}`).toString().trim();
  },
  'git.checkout': async (d, ...a) => {
    const { execSync } = await import('child_process');
    const branch = a[0] || d;
    const dir = a[1] || '.';
    return execSync(`git -C ${dir} checkout ${branch}`).toString().trim();
  },
};

// ── crypto tools ─────────────────────────────────────────────────────────────

const crypto = {
  'hash.md5': async (d) => {
    const { createHash } = await import('crypto');
    return createHash('md5').update(String(d)).digest('hex');
  },
  'hash.sha1': async (d) => {
    const { createHash } = await import('crypto');
    return createHash('sha1').update(String(d)).digest('hex');
  },
  'hash.sha256': async (d) => {
    const { createHash } = await import('crypto');
    return createHash('sha256').update(String(d)).digest('hex');
  },
  'hash.sha512': async (d) => {
    const { createHash } = await import('crypto');
    return createHash('sha512').update(String(d)).digest('hex');
  },
  'base64.encode': async (d) => Buffer.from(String(d)).toString('base64'),
  'base64.decode': async (d) => Buffer.from(String(d), 'base64').toString('utf-8'),
  'random.int': async (d, ...a) => {
    const min = parseInt(a[0]) || 0;
    const max = parseInt(a[1]) || 100;
    return Math.floor(Math.random() * (max - min + 1)) + min;
  },
  'random.float': async () => Math.random(),
  'random.choice': async (d) => {
    if (Array.isArray(d)) return d[Math.floor(Math.random() * d.length)];
    return d;
  },
  'random.uuid': async () => crypto.randomUUID(),
};

// ── time tools ───────────────────────────────────────────────────────────────

const time = {
  'time.now': async () => new Date().toISOString(),
  'time.unix': async () => Math.floor(Date.now() / 1000),
  'time.ms': async () => Date.now(),
  'time.format': async (d, ...a) => {
    const fmt = a[0] || '%Y-%m-%d %H:%M:%S';
    const date = new Date(d);
    return fmt
      .replace('%Y', date.getFullYear())
      .replace('%m', String(date.getMonth() + 1).padStart(2, '0'))
      .replace('%d', String(date.getDate()).padStart(2, '0'))
      .replace('%H', String(date.getHours()).padStart(2, '0'))
      .replace('%M', String(date.getMinutes()).padStart(2, '0'))
      .replace('%S', String(date.getSeconds()).padStart(2, '0'))
      .replace('%w', ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'][date.getDay()])
      .replace('%b', ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][date.getMonth()]);
  },
  'time.sleep': async (d, ...a) => {
    const s = parseFloat(a[0]) || 1;
    return new Promise(r => setTimeout(() => r(d), s * 1000));
  },
  'time.parse': async (d) => {
    const date = new Date(d);
    return { iso: date.toISOString(), unix: Math.floor(date.getTime() / 1000), valid: !isNaN(date.getTime()) };
  },
  'time.diff': async (d, ...a) => {
    const start = new Date(a[0] || d);
    const end = new Date(a[1] || new Date());
    const ms = end - start;
    return {
      ms, seconds: Math.floor(ms / 1000),
      minutes: Math.floor(ms / 60000), hours: Math.floor(ms / 3600000),
      days: Math.floor(ms / 86400000), human: `${Math.floor(ms / 86400000)}d ${Math.floor((ms % 86400000) / 3600000)}h ${Math.floor((ms % 3600000) / 60000)}m`
    };
  },
};

// ── string tools ─────────────────────────────────────────────────────────────

const string = {
  'string.upper': async (d) => String(d).toUpperCase(),
  'string.lower': async (d) => String(d).toLowerCase(),
  'string.trim': async (d) => String(d).trim(),
  'string.split': async (d, ...a) => String(d).split(a[0] || ','),
  'string.join': async (d, ...a) => Array.isArray(d) ? d.join(a[0] || ',') : String(d),
  'string.replace': async (d, ...a) => String(d).split(a[0] || '').join(a[1] || ''),
  'string.contains': async (d, ...a) => String(d).includes(a[0] || ''),
  'string.starts': async (d, ...a) => String(d).startsWith(a[0] || ''),
  'string.ends': async (d, ...a) => String(d).endsWith(a[0] || ''),
  'string.length': async (d) => String(d).length,
  'string.reverse': async (d) => String(d).split('').reverse().join(''),
  'string.pad': async (d, ...a) => {
    const len = parseInt(a[0]) || 0;
    const char = a[1] || ' ';
    const side = a[2] || 'right';
    const s = String(d);
    if (side === 'left') return s.padStart(len, char);
    return s.padEnd(len, char);
  },
  'string.slice': async (d, ...a) => {
    const s = String(d);
    const start = parseInt(a[0]) || 0;
    const end = a[1] !== undefined ? parseInt(a[1]) : undefined;
    return end !== undefined ? s.slice(start, end) : s.slice(start);
  },
  'string.match': async (d, ...a) => {
    const m = String(d).match(new RegExp(a[0] || ''));
    return m ? m[0] : null;
  },
  'string.extract': async (d, ...a) => {
    const m = String(d).match(new RegExp(a[0] || '', 'g'));
    return m || [];
  },
  'string.lines': async (d) => String(d).split('\n'),
  'string.words': async (d) => String(d).split(/\s+/).filter(Boolean),
  'string.truncate': async (d, ...a) => {
    const max = parseInt(a[0]) || 80;
    const suffix = a[1] || '...';
    const s = String(d);
    return s.length > max ? s.slice(0, max - suffix.length) + suffix : s;
  },
};

// ── math tools ───────────────────────────────────────────────────────────────

const math = {
  'math.add': async (d, ...a) => Number(d) + Number(a[0] || 0),
  'math.sub': async (d, ...a) => Number(d) - Number(a[0] || 0),
  'math.mul': async (d, ...a) => Number(d) * Number(a[0] || 1),
  'math.div': async (d, ...a) => { const n = Number(a[0] || 1); return n !== 0 ? Number(d) / n : 0; },
  'math.mod': async (d, ...a) => Number(d) % Number(a[0] || 1),
  'math.pow': async (d, ...a) => Math.pow(Number(d), Number(a[0] || 2)),
  'math.sqrt': async (d) => Math.sqrt(Number(d)),
  'math.abs': async (d) => Math.abs(Number(d)),
  'math.round': async (d, ...a) => { const n = parseInt(a[0]) || 0; return Number(Number(d).toFixed(n)); },
  'math.floor': async (d) => Math.floor(Number(d)),
  'math.ceil': async (d) => Math.ceil(Number(d)),
  'math.min': async (d) => Array.isArray(d) ? Math.min(...d) : d,
  'math.max': async (d) => Array.isArray(d) ? Math.max(...d) : d,
  'math.sum': async (d) => Array.isArray(d) ? d.reduce((a, b) => a + Number(b), 0) : d,
  'math.avg': async (d) => Array.isArray(d) && d.length ? d.reduce((a, b) => a + Number(b), 0) / d.length : 0,
  'math.clamp': async (d, ...a) => {
    const v = Number(d); const lo = Number(a[0] || 0); const hi = Number(a[1] || 100);
    return Math.max(lo, Math.min(hi, v));
  },
  'math.range': async (d, ...a) => {
    const start = parseInt(d) || 0;
    const stop = parseInt(a[0]) || 10;
    const step = parseInt(a[1]) || 1;
    const result = [];
    for (let i = start; i < stop; i += step) result.push(i);
    return result;
  },
};

// ── net tools ────────────────────────────────────────────────────────────────

const net = {
  'net.ping': async (d, ...a) => {
    const host = a[0] || d;
    const start = Date.now();
    try {
      await fetch(`https://${host}`, { mode: 'no-cors', signal: AbortSignal.timeout(3000) });
      return { alive: true, time_ms: Date.now() - start };
    } catch { return { alive: false, time_ms: Date.now() - start }; }
  },
  'net.dns': async (d, ...a) => {
    const dns = await import('dns');
    const host = a[0] || d;
    return dns.promises.lookup(host);
  },
  'net.ip': async () => {
    const r = await fetch('https://api.ipify.org');
    return r.text();
  },
  'net.fetch': async (d, ...a) => {
    const url = a[0] || d;
    const r = await fetch(String(url));
    return { status: r.status, headers: Object.fromEntries(r.headers), body: await r.text() };
  },
  'net.status': async (d, ...a) => {
    const url = a[0] || d;
    const start = Date.now();
    try {
      const r = await fetch(String(url), { signal: AbortSignal.timeout(10000) });
      return { url, status: r.status, ok: r.ok, time_ms: Date.now() - start };
    } catch (e) { return { url, status: 0, ok: false, error: e.message, time_ms: Date.now() - start }; }
  },
};

// ── system tools ─────────────────────────────────────────────────────────────

const system = {
  'sys.os': async () => process.platform,
  'sys.arch': async () => process.arch,
  'sys.cpus': async () => { const os = await import('os'); return os.cpus().length; },
  'sys.memory': async () => {
    const os = await import('os');
    const total = os.totalmem();
    const free = os.freemem();
    return { total, free, used: total - free, used_pct: Math.round((total - free) / total * 100) };
  },
  'sys.disk': async (d, ...a) => {
    try {
      const { execSync } = await import('child_process');
      const path = a[0] || d || '/';
      const out = execSync(`df -m ${path} | tail -1`).toString().trim().split(/\s+/);
      return { total: parseInt(out[1]), used: parseInt(out[2]), free: parseInt(out[3]), used_pct: parseInt(out[4]) };
    } catch (e) { return { error: e.message }; }
  },
  'sys.uptime': async () => Math.floor(process.uptime()),
  'sys.env': async () => Object.assign({}, process.env),
  'sys.pid': async () => process.pid,
  'sys.user': async () => { const os = await import('os'); return os.userInfo().username; },
  'sys.cwd': async () => process.cwd(),
  'sys.hostname': async () => { const os = await import('os'); return os.hostname(); },
};

// ── docker tools ─────────────────────────────────────────────────────────────

const docker = {
  'docker.ps': async () => {
    try {
      const { execSync } = await import('child_process');
      const out = execSync("docker ps --format '{{.Names}}|{{.Status}}|{{.Image}}|{{.ID}}'").toString().trim();
      return out ? out.split('\n').map(l => {
        const [name, status, image, id] = l.split('|');
        return { name, status, image, id };
      }) : [];
    } catch (e) { return []; }
  },
  'docker.images': async () => {
    try {
      const { execSync } = await import('child_process');
      const out = execSync("docker images --format '{{.Repository}}|{{.Tag}}|{{.Size}}|{{.ID}}'").toString().trim();
      return out ? out.split('\n').map(l => {
        const [repo, tag, size, id] = l.split('|');
        return { repo, tag, size, id };
      }) : [];
    } catch (e) { return []; }
  },
  'docker.logs': async (d, ...a) => {
    const { execSync } = await import('child_process');
    const name = a[0] || d;
    const lines = a[1] || 100;
    return execSync(`docker logs --tail ${lines} ${name}`).toString();
  },
  'docker.exec': async (d, ...a) => {
    const { execSync } = await import('child_process');
    const name = a[0] || d;
    const cmd = a[1] || 'sh';
    try {
      const stdout = execSync(`docker exec ${name} ${cmd}`).toString();
      return { stdout, stderr: '', code: 0 };
    } catch (e) { return { stdout: '', stderr: e.message, code: e.status || 1 }; }
  },
  'docker.build': async (d, ...a) => {
    const { execSync } = await import('child_process');
    const path = a[0] || d || '.';
    const tag = a[1] || 'latest';
    return execSync(`docker build -t ${tag} ${path}`).toString();
  },
  'docker.run': async (d, ...a) => {
    const { execSync } = await import('child_process');
    const image = a[0] || d;
    const opts = a[1] || '';
    return execSync(`docker run ${opts} ${image}`).toString();
  },
};

// ── github tools ─────────────────────────────────────────────────────────────

const github = {
  'github.repos': async (d, ...a) => {
    const user = a[0] || d;
    const r = await fetch(`https://api.github.com/users/${user}/repos?per_page=30`);
    const data = await r.json();
    return data.map(r => ({ name: r.name, stars: r.stargazers_count, description: r.description, language: r.language, url: r.html_url }));
  },
  'github.commits': async (d, ...a) => {
    const repo = a[0] || d;
    const count = a[1] || 10;
    const r = await fetch(`https://api.github.com/repos/${repo}/commits?per_page=${count}`);
    const data = await r.json();
    return data.map(c => ({ sha: c.sha.slice(0, 7), message: c.commit.message, author: c.commit.author.name, date: c.commit.author.date }));
  },
  'github.issues': async (d, ...a) => {
    const repo = a[0] || d;
    const state = a[1] || 'open';
    const r = await fetch(`https://api.github.com/repos/${repo}/issues?state=${state}&per_page=30`);
    const data = await r.json();
    return data.map(i => ({ number: i.number, title: i.title, state: i.state, labels: i.labels.map(l => l.name), author: i.user.login, created: i.created_at }));
  },
  'github.stars': async (d, ...a) => {
    const repo = a[0] || d;
    const r = await fetch(`https://api.github.com/repos/${repo}`);
    const data = await r.json();
    return data.stargazers_count || 0;
  },
  'github.forks': async (d, ...a) => {
    const repo = a[0] || d;
    const r = await fetch(`https://api.github.com/repos/${repo}`);
    const data = await r.json();
    return data.forks_count || 0;
  },
  'github.search': async (d, ...a) => {
    const query = a[0] || d;
    const r = await fetch(`https://api.github.com/search/repositories?q=${encodeURIComponent(query)}&per_page=10`);
    const data = await r.json();
    return (data.items || []).map(r => ({ name: r.full_name, stars: r.stargazers_count, description: r.description, url: r.html_url }));
  },
};

// ── ai tools ─────────────────────────────────────────────────────────────────

const ai = {
  'ai.sentiment': async (d, ...a) => {
    const text = String(d || a[0] || '').toLowerCase();
    const pos = ['love', 'great', 'good', 'awesome', 'excellent', 'amazing', 'wonderful', 'fantastic', 'best', 'happy', 'thanks', 'nice'];
    const neg = ['hate', 'bad', 'terrible', 'awful', 'horrible', 'worst', 'angry', 'sad', 'disappointed', 'frustrated', 'annoying', 'useless'];
    const isPos = pos.some(w => text.includes(w));
    const isNeg = neg.some(w => text.includes(w));
    return { label: isPos ? 'positive' : isNeg ? 'negative' : 'neutral', score: isPos || isNeg ? 0.8 : 0.5 };
  },
  'ai.summarize': async (d, ...a) => {
    const text = String(d || a[0] || '');
    const max = parseInt(a[1]) || 200;
    if (text.length <= max) return text;
    // extract first few sentences
    const sentences = text.match(/[^.!?]+[.!?]+/g) || [text];
    let summary = '';
    for (const s of sentences) {
      if ((summary + s).length > max) break;
      summary += s;
    }
    return summary.trim() || text.slice(0, max) + '...';
  },
  'ai.extract': async (d, ...a) => {
    const text = String(d || a[0] || '');
    const schema = (a[1] || '').split(',').map(s => s.trim()).filter(Boolean);
    if (!schema.length || !text.includes(':')) return {};
    const result = {};
    for (const pair of text.split(',')) {
      const [key, ...rest] = pair.split(':');
      if (key && rest.length) {
        const k = key.trim();
        if (schema.includes(k)) result[k] = rest.join(':').trim();
      }
    }
    return result;
  },
  'ai.keywords': async (d, ...a) => {
    const text = String(d || a[0] || '').toLowerCase();
    const stopWords = new Set(['the','a','an','is','are','was','were','be','been','being','have','has','had','do','does','did','will','would','could','should','may','might','shall','can','need','dare','ought','used','to','of','in','for','on','with','at','by','from','as','into','through','during','before','after','above','below','between','out','off','over','under','again','further','then','once','here','there','when','where','why','how','all','each','every','both','few','more','most','other','some','such','no','nor','not','only','own','same','so','than','too','very','just','because','but','and','or','if','while','about','up','down']);
    const words = text.split(/\s+/).filter(w => w.length > 2 && !stopWords.has(w));
    const freq = {};
    for (const w of words) freq[w] = (freq[w] || 0) + 1;
    return Object.entries(freq).sort((a, b) => b[1] - a[1]).slice(0, 10).map(([word, count]) => ({ word, count }));
  },
  'ai.readability': async (d, ...a) => {
    const text = String(d || a[0] || '');
    const sentences = (text.match(/[.!?]+/g) || []).length || 1;
    const words = text.split(/\s+/).filter(Boolean).length;
    const syllables = text.split(/\s+/).reduce((acc, w) => acc + Math.max(1, (w.match(/[aeiouy]+/gi) || []).length), 0);
    const flesch = 206.835 - 1.015 * (words / sentences) - 84.6 * (syllables / words);
    return {
      words, sentences, syllables,
      flesch: Math.max(0, Math.min(100, Math.round(flesch))),
      grade: flesch > 90 ? '5th' : flesch > 80 ? '6th' : flesch > 70 ? '7th' : flesch > 60 ? '8th-9th' : flesch > 50 ? '10th-12th' : 'college',
      reading_time_min: Math.ceil(words / 200)
    };
  },
};

// ── collection tools (expanded) ─────────────────────────────────────────────

const collections = {
  'group.by': async (d, ...a) => {
    if (!Array.isArray(d)) return {};
    const key = a[0] || 'type';
    const result = {};
    for (const item of d) {
      const k = typeof item === 'object' ? (item[key] || 'unknown') : String(item);
      if (!result[k]) result[k] = [];
      result[k].push(item);
    }
    return result;
  },
  'group.count': async (d, ...a) => {
    if (!Array.isArray(d)) return {};
    const key = a[0] || 'type';
    const result = {};
    for (const item of d) {
      const k = typeof item === 'object' ? (item[key] || 'unknown') : String(item);
      result[k] = (result[k] || 0) + 1;
    }
    return result;
  },
  'zip': async (d, ...a) => {
    if (!Array.isArray(d) || !Array.isArray(a[0])) return [];
    const other = a[0];
    return d.map((item, i) => [item, other[i]]);
  },
  'enumerate': async (d) => {
    if (!Array.isArray(d)) return [];
    return d.map((item, i) => ({ index: i, value: item }));
  },
  'chunk': async (d, ...a) => {
    if (!Array.isArray(d)) return [];
    const size = parseInt(a[0]) || 2;
    const result = [];
    for (let i = 0; i < d.length; i += size) {
      result.push(d.slice(i, i + size));
    }
    return result;
  },
  'window': async (d, ...a) => {
    if (!Array.isArray(d)) return [];
    const size = parseInt(a[0]) || 2;
    const result = [];
    for (let i = 0; i <= d.length - size; i++) {
      result.push(d.slice(i, i + size));
    }
    return result;
  },
  'sample': async (d, ...a) => {
    if (!Array.isArray(d)) return [];
    const n = Math.min(parseInt(a[0]) || 1, d.length);
    const shuffled = [...d].sort(() => Math.random() - 0.5);
    return shuffled.slice(0, n);
  },
  'shuffle': async (d) => {
    if (!Array.isArray(d)) return d;
    return [...d].sort(() => Math.random() - 0.5);
  },
  'transpose': async (d) => {
    if (!Array.isArray(d) || !Array.isArray(d[0])) return d;
    return d[0].map((_, i) => d.map(row => row[i]));
  },
  'pivot': async (d, ...a) => {
    if (!Array.isArray(d)) return {};
    const keyField = a[0] || 'id';
    const result = {};
    for (const item of d) {
      if (typeof item === 'object') {
        const key = item[keyField];
        if (key !== undefined) result[key] = item;
      }
    }
    return result;
  },
};

// ── export all tools ─────────────────────────────────────────────────────────

export {
  fs, git, crypto, time, string, math, net, system, docker, github, ai, collections,
};

// combined registry
export const ALL_TOOLS = {
  ...fs, ...git, ...crypto, ...time, ...string, ...math, ...net, ...system, ...docker, ...github, ...ai, ...collections,
};

export const TOOL_COUNT = Object.keys(ALL_TOOLS).length;

export const TOOL_DOCS = {
  fs: { count: Object.keys(fs).length, description: 'file system operations' },
  git: { count: Object.keys(git).length, description: 'git version control' },
  crypto: { count: Object.keys(crypto).length, description: 'hashing, encoding, random' },
  time: { count: Object.keys(time).length, description: 'date and time operations' },
  string: { count: Object.keys(string).length, description: 'string manipulation' },
  math: { count: Object.keys(math).length, description: 'math operations' },
  net: { count: Object.keys(net).length, description: 'network utilities' },
  system: { count: Object.keys(system).length, description: 'system information' },
  docker: { count: Object.keys(docker).length, description: 'docker operations' },
  github: { count: Object.keys(github).length, description: 'github api' },
  ai: { count: Object.keys(ai).length, description: 'ai/llm operations' },
  collections: { count: Object.keys(collections).length, description: 'advanced collection operations' },
};
