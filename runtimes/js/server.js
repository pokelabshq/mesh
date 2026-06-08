/**
 * mesh server — HTTP API for running mesh programs.
 *
 * usage:
 *   node server.js              # start on port 3000
 *   node server.js --port 8080  # custom port
 *
 * endpoints:
 *   POST /run     — run mesh source code
 *   POST /check   — check syntax
 *   GET  /tools   — list available tools
 *   GET  /health  — health check
 *   GET  /        — server info
 */

import { run, check, lex, Parser, Executor, ToolRegistry } from './mesh.js';
import { ALL_TOOLS } from './tools.js';

const PORT = parseInt(process.argv.find(a => a.startsWith('--port='))?.split('=')[1] || process.env.PORT || 3000);

const registry = new ToolRegistry();
for (const [name, fn] of Object.entries(ALL_TOOLS)) registry.register(name, fn);

const server = Bun.serve({
  port: PORT,
  async fetch(req) {
    const url = new URL(req.url);

    // CORS
    const headers = {
      'Content-Type': 'application/json',
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type',
    };

    if (req.method === 'OPTIONS') return new Response(null, { headers });

    // GET /
    if (url.pathname === '/' && req.method === 'GET') {
      return new Response(JSON.stringify({
        name: 'mesh server',
        version: '0.1.0',
        tools: Object.keys(ALL_TOOLS).length,
        endpoints: {
          'POST /run': 'run mesh source code',
          'POST /check': 'check syntax',
          'GET /tools': 'list available tools',
          'GET /health': 'health check',
        },
      }, null, 2), { headers });
    }

    // GET /health
    if (url.pathname === '/health' && req.method === 'GET') {
      return new Response(JSON.stringify({ ok: true, uptime: process.uptime() }), { headers });
    }

    // GET /tools
    if (url.pathname === '/tools' && req.method === 'GET') {
      const category = url.searchParams.get('category');
      let tools = Object.keys(ALL_TOOLS);
      if (category) tools = tools.filter(t => t.startsWith(category + '.'));
      return new Response(JSON.stringify({ count: tools.length, tools }, null, 2), { headers });
    }

    // POST /check
    if (url.pathname === '/check' && req.method === 'POST') {
      const body = await req.json().catch(() => null);
      if (!body?.source) return new Response(JSON.stringify({ error: 'missing source' }), { status: 400, headers });
      const errors = check(body.source);
      return new Response(JSON.stringify({ ok: errors.length === 0, errors }, null, 2), { headers });
    }

    // POST /run
    if (url.pathname === '/run' && req.method === 'POST') {
      const body = await req.json().catch(() => null);
      if (!body?.source) return new Response(JSON.stringify({ error: 'missing source' }), { status: 400, headers });

      const timeout = body.timeout || 30000;
      const input = body.input || null;

      try {
        const result = await Promise.race([
          run(input, input, registry),
          new Promise((_, r) => setTimeout(() => r({ error: 'timeout' }), timeout)),
        ]);

        if (result?.error) {
          return new Response(JSON.stringify({ ok: false, error: result.error, step: result.step }, null, 2), { headers });
        }

        return new Response(JSON.stringify({ ok: true, result }, null, 2), { headers });
      } catch (e) {
        return new Response(JSON.stringify({ ok: false, error: e.message }, null, 2), { status: 500, headers });
      }
    }

    return new Response(JSON.stringify({ error: 'not found' }), { status: 404, headers });
  },
});

console.log(`mesh server running on http://localhost:${PORT}`);
console.log(`${Object.keys(ALL_TOOLS).length} tools loaded`);
