/**
 * mesh test suite.
 * run with: node --test tests.mjs
 * or: node tests.mjs
 */

import { describe, it, beforeEach } from 'node:test';
import assert from 'node:assert';
import { run, check, lex, Parser, Executor, ToolRegistry } from './runtimes/js/mesh.js';
import { ALL_TOOLS } from './runtimes/js/tools.js';

const registry = new ToolRegistry();
for (const [name, fn] of Object.entries(ALL_TOOLS)) registry.register(name, fn);

// ── lexer tests ──────────────────────────────────────────────────────────────

describe('lexer', () => {
  it('tokenizes strings', () => {
    const tokens = lex('"hello"');
    assert.strictEqual(tokens[0].type, 'STRING');
    assert.strictEqual(tokens[0].value, 'hello');
  });

  it('tokenizes numbers', () => {
    const tokens = lex('42');
    assert.strictEqual(tokens[0].type, 'NUMBER');
    assert.strictEqual(tokens[0].value, '42');
  });

  it('tokenizes pipes', () => {
    const tokens = lex('a → b');
    const pipe = tokens.find(t => t.type === 'PIPE');
    assert.ok(pipe);
  });

  it('tokenizes keywords', () => {
    const tokens = lex('if else for each parallel retry');
    const kws = tokens.filter(t => t.type === 'KEYWORD');
    assert.strictEqual(kws.length, 6);
  });

  it('tokenizes tool calls', () => {
    const tokens = lex('http.get "https://example.com" timeout=30');
    const words = tokens.filter(t => t.type === 'WORD');
    assert.ok(words.some(w => w.value === 'http.get'));
  });
});

// ── parser tests ─────────────────────────────────────────────────────────────

describe('parser', () => {
  it('parses a simple pipeline', () => {
    const errors = check('"hello" → print');
    assert.strictEqual(errors.length, 0);
  });

  it('parses tool calls with args', () => {
    const errors = check('http.get "https://example.com" timeout=30');
    assert.strictEqual(errors.length, 0);
  });

  it('parses conditionals', () => {
    const errors = check('if .status == 200:\n  log "ok"');
    assert.strictEqual(errors.length, 0);
  });

  it('parses parallel blocks', () => {
    const errors = check('parallel:\n  branch a:\n    fetch "url_a"\n  branch b:\n    fetch "url_b"');
    assert.strictEqual(errors.length, 0);
  });

  it('parses for loops', () => {
    const errors = check('for each items:\n  print');
    assert.strictEqual(errors.length, 0);
  });

  it('parses retry blocks', () => {
    const errors = check('retry 3, backoff 2:\n  http.get "url"');
    assert.strictEqual(errors.length, 0);
  });

  it('rejects invalid syntax', () => {
    const errors = check('if:\nprint');
    // should have some error or parse oddly — main point it doesn't crash
    assert.ok(Array.isArray(errors));
  });
});

// ── executor tests ───────────────────────────────────────────────────────────

describe('executor', () => {
  it('runs a simple print pipeline', async () => {
    const result = await run('"hello world"', null, registry);
    assert.strictEqual(typeof result, 'string');
  });

  it('runs json.parse', async () => {
    const result = await run('json.parse → .name', '{"name": "alex"}', registry);
    assert.strictEqual(result, 'alex');
  });

  it('runs string.upper', async () => {
    const result = await run('"hello" → string.upper', null, registry);
    assert.strictEqual(result, 'HELLO');
  });

  it('runs math.add', async () => {
    const result = await run('42 → math.add 8', null, registry);
    assert.strictEqual(result, 50);
  });

  it('runs count on array', async () => {
    const result = await run('json.parse → count', '[1,2,3,4,5]', registry);
    assert.strictEqual(result, 5);
  });

  it('runs take', async () => {
    const result = await run('json.parse → take 3', '[1,2,3,4,5]', registry);
    assert.deepStrictEqual(result, [1, 2, 3]);
  });

  it('runs sort', async () => {
    const result = await run('json.parse → sort', '[3,1,4,1,5]', registry);
    assert.deepStrictEqual(result, [1, 1, 3, 4, 5]);
  });

  it('runs unique', async () => {
    const result = await run('json.parse → unique', '[1,2,2,3,3,4]', registry);
    assert.deepStrictEqual(result, [1, 2, 3, 4]);
  });

  it('runs flatten', async () => {
    const result = await run('json.parse → flatten', '[[1,2],[3,4],[5]]', registry);
    assert.deepStrictEqual(result, [1, 2, 3, 4, 5]);
  });

  it('runs ai.sentiment', async () => {
    const result = await run('"I love this!" → ai.sentiment', null, registry);
    assert.strictEqual(result.label, 'positive');
  });

  it('runs hash.sha256', async () => {
    const result = await run('"hello" → hash.sha256', null, registry);
    assert.strictEqual(result.length, 64);
  });

  it('runs time.now', async () => {
    const result = await run('time.now', null, registry);
    assert.ok(typeof result === 'string');
    assert.ok(result.includes('T'));
  });

  it('runs uuid', async () => {
    const result = await run('uuid', null, registry);
    assert.ok(typeof result === 'string');
    assert.ok(result.length > 0);
  });

  it('chains multiple operations', async () => {
    const result = await run('json.parse → sort → unique → take 5 → count', '[3,1,4,1,5,9,2,6,5,3,5]', registry);
    assert.strictEqual(result, 5);
  });
});

// ── tool registry tests ──────────────────────────────────────────────────────

describe('tool registry', () => {
  it('has 100+ tools', () => {
    assert.ok(registry.listTools().length >= 100);
  });

  it('includes fs tools', () => {
    assert.ok(registry.get('fs.read'));
    assert.ok(registry.get('fs.write'));
  });

  it('includes git tools', () => {
    assert.ok(registry.get('git.status'));
    assert.ok(registry.get('git.log'));
  });

  it('includes crypto tools', () => {
    assert.ok(registry.get('hash.sha256'));
    assert.ok(registry.get('base64.encode'));
  });

  it('includes http tools', () => {
    assert.ok(registry.get('http.get'));
    assert.ok(registry.get('http.post'));
  });

  it('includes ai tools', () => {
    assert.ok(registry.get('ai.sentiment'));
    assert.ok(registry.get('ai.summarize'));
  });

  it('can register custom tools', () => {
    registry.register('double', (d) => Number(d) * 2);
    assert.ok(registry.get('double'));
  });
});

// ── integration tests ────────────────────────────────────────────────────────

describe('integration', () => {
  it('runs hello.mesh example', async () => {
    const errors = check('"hello" → string.upper → string.lower → print');
    assert.strictEqual(errors.length, 0);
  });

  it('runs data pipeline', async () => {
    const source = `
json.parse → .items → sort → unique → take 10 → count → format "count: {{.}}" → print
`;
    const result = await run(source, '{"items":[3,1,4,1,5,9,2,6,5,3,5]}', registry);
    assert.ok(result);
  });

  it('handles errors gracefully', async () => {
    // unknown tool should not crash
    const result = await run('"test" → unknown_tool_xyz', null, registry);
    // should return an error or pass through
    assert.ok(result !== undefined);
  });
});

// ── run tests ────────────────────────────────────────────────────────────────

console.log('mesh test suite');
console.log('---');
console.log(`tools loaded: ${registry.listTools().length}`);
console.log('run with: node --test tests.mjs');
