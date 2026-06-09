"""mesh_mcp — MCP server for mesh.

exposes mesh tools to any MCP client (Cursor, Claude Code, etc.).
supports stdio and http transports.

usage:
    python mesh_mcp.py              # stdio transport
    python mesh_mcp.py --port 8081  # http transport
"""

import json
import sys
import os
import asyncio
from mesh import run, check, ToolRegistry


# ── MCP protocol ──────────────────────────────────────────────────────────────

MCP_VERSION = "2024-11-05"

def make_response(id, result):
    return {"jsonrpc": "2.0", "id": id, "result": result}

def make_error(id, code, message):
    return {"jsonrpc": "2.0", "id": id, "error": {"code": code, "message": message}}

def tool_result(content):
    return {"content": [{"type": "text", "text": str(content)}]}

def tool_result_json(data):
    return {"content": [{"type": "text", "json": data}]}


# ── tool definitions ──────────────────────────────────────────────────────────

def get_tool_definitions(registry: ToolRegistry) -> list[dict]:
    """Generate MCP tool definitions from mesh registry."""
    tools = []

    # core mesh tools
    tools.append({
        "name": "mesh_run",
        "description": "Execute mesh source code. mesh is a flow-based language for agents. use pipe (→) to chain tools. example: '\"hello\" → upper → print'",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source": {"type": "string", "description": "mesh source code to execute"},
                "input": {"description": "optional input data (any type)"},
            },
            "required": ["source"],
        },
    })

    tools.append({
        "name": "mesh_check",
        "description": "Check mesh source code for syntax errors without executing.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source": {"type": "string", "description": "mesh source code to check"},
            },
            "required": ["source"],
        },
    })

    tools.append({
        "name": "mesh_list_tools",
        "description": "List all available mesh tools with descriptions and categories.",
        "inputSchema": {"type": "object", "properties": {}},
    })

    tools.append({
        "name": "mesh_tool_info",
        "description": "Get detailed info about a specific mesh tool.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "tool_name": {"type": "string", "description": "name of the mesh tool"},
            },
            "required": ["tool_name"],
        },
    })

    tools.append({
        "name": "mesh_run_file",
        "description": "Run a .mesh file from disk.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "path to .mesh file"},
                "input": {"description": "optional input data"},
            },
            "required": ["path"],
        },
    })

    # expose mesh built-in tools as MCP tools
    for name in registry.list_tools():
        meta = registry.get_meta(name)
        desc = meta.description if meta else f"mesh built-in tool: {name}"
        category = meta.category if meta else "core"

        tools.append({
            "name": f"mesh_{name.replace('.', '_')}",
            "description": f"[{category}] {desc}",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "data": {"description": "input data"},
                },
            },
        })

    return tools


# ── stdio transport ───────────────────────────────────────────────────────────

class StdioTransport:
    """MCP transport over stdin/stdout."""

    def __init__(self, registry: ToolRegistry):
        self.registry = registry

    async def read_message(self) -> dict | None:
        line = await asyncio.get_event_loop().run_in_executor(None, sys.stdin.readline)
        if not line:
            return None
        line = line.strip()
        if not line:
            return None
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            return None

    async def write_message(self, msg: dict):
        line = json.dumps(msg, default=str)
        await asyncio.get_event_loop().run_in_executor(None, lambda: sys.stdout.write(line + "\n"))
        await asyncio.get_event_loop().run_in_executor(None, sys.stdout.flush)

    async def handle(self):
        """Main MCP loop."""
        while True:
            msg = await self.read_message()
            if msg is None:
                break

            await self._handle_message(msg)

    async def _handle_message(self, msg: dict):
        method = msg.get("method", "")
        msg_id = msg.get("id")
        params = msg.get("params", {})

        if method == "initialize":
            await self.write_message(make_response(msg_id, {
                "protocolVersion": MCP_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "mesh-mcp", "version": "0.3.0"},
            }))

        elif method == "initialized":
            pass  # notification, no response

        elif method == "tools/list":
            tools = get_tool_definitions(self.registry)
            await self.write_message(make_response(msg_id, {"tools": tools}))

        elif method == "tools/call":
            result = await self._call_tool(params)
            await self.write_message(make_response(msg_id, result))

        elif method == "ping":
            await self.write_message(make_response(msg_id, {}))

        else:
            await self.write_message(make_error(msg_id, -32601, f"method not found: {method}"))

    async def _call_tool(self, params: dict) -> dict:
        name = params.get("name", "")
        args = params.get("arguments", {})

        try:
            if name == "mesh_run":
                source = args.get("source", "")
                input_data = args.get("input")
                result = run(source, input_data=input_data, registry=self.registry)
                if isinstance(result, (dict, list)):
                    return tool_result_json(result)
                return tool_result(result)

            elif name == "mesh_check":
                source = args.get("source", "")
                errs = check(source)
                if errs:
                    return tool_result({"errors": errs})
                return tool_result({"ok": True, "errors": []})

            elif name == "mesh_list_tools":
                tools = []
                for tname in self.registry.list_tools():
                    meta = self.registry.get_meta(tname)
                    tools.append({
                        "name": tname,
                        "description": meta.description if meta else "",
                        "category": meta.category if meta else "core",
                    })
                return tool_result_json({"tools": tools, "count": len(tools)})

            elif name == "mesh_tool_info":
                tname = args.get("tool_name", "")
                meta = self.registry.get_meta(tname)
                if meta:
                    return tool_result_json({
                        "name": meta.name,
                        "description": meta.description,
                        "category": meta.category,
                        "input_type": meta.input_type,
                        "output_type": meta.output_type,
                    })
                return tool_result({"error": f"tool not found: {tname}"})

            elif name == "mesh_run_file":
                path = args.get("path", "")
                input_data = args.get("input")
                if not os.path.isfile(path):
                    return tool_result({"error": f"file not found: {path}"})
                with open(path) as f:
                    source = f.read()
                result = run(source, input_data=input_data, registry=self.registry)
                if isinstance(result, (dict, list)):
                    return tool_result_json(result)
                return tool_result(result)

            elif name.startswith("mesh_"):
                # direct mesh tool call
                tool_name = name[5:].replace("_", ".")
                fn = self.registry.get(tool_name)
                if fn:
                    data = args.get("data")
                    result = fn(data)
                    if isinstance(result, (dict, list)):
                        return tool_result_json(result)
                    return tool_result(result)
                return tool_result({"error": f"unknown mesh tool: {tool_name}"})

            else:
                return tool_result({"error": f"unknown tool: {name}"})

        except Exception as e:
            return tool_result({"error": str(e)})


# ── http transport ────────────────────────────────────────────────────────────

async def run_http(registry: ToolRegistry, port: int):
    """Run MCP over HTTP (for web-based clients)."""
    try:
        from aiohttp import web
    except ImportError:
        print("aiohttp not installed. install with: pip install aiohttp")
        print("or use stdio transport: python mesh_mcp.py")
        sys.exit(1)

    async def handle_mcp(request):
        try:
            body = await request.json()
        except Exception:
            return web.json_response(make_error(None, -32700, "parse error"))

        method = body.get("method", "")
        msg_id = body.get("id")
        params = body.get("params", {})

        if method == "initialize":
            return web.json_response(make_response(msg_id, {
                "protocolVersion": MCP_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "mesh-mcp", "version": "0.3.0"},
            }))

        elif method == "tools/list":
            tools = get_tool_definitions(registry)
            return web.json_response(make_response(msg_id, {"tools": tools}))

        elif method == "tools/call":
            name = params.get("name", "")
            args = params.get("arguments", {})
            # reuse stdio logic
            transport = StdioTransport(registry)
            result = await transport._call_tool(params)
            return web.json_response(make_response(msg_id, result))

        return web.json_response(make_error(msg_id, -32601, f"method not found: {method}"))

    app = web.Application()
    app.router.add_post("/mcp", handle_mcp)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", port)
    print(f"mesh-mcp http on 127.0.0.1:{port}/mcp")
    await site.start()
    while True:
        await asyncio.sleep(3600)


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    import argparse
    p = argparse.ArgumentParser(description="mesh MCP server")
    p.add_argument("--port", type=int, default=0, help="http port (0 = stdio)")
    args = p.parse_args()

    registry = ToolRegistry()

    if args.port > 0:
        asyncio.run(run_http(registry, args.port))
    else:
        transport = StdioTransport(registry)
        asyncio.run(transport.handle())


if __name__ == "__main__":
    main()
