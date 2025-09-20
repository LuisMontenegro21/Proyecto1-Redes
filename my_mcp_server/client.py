# 19/09/2025
# Reference: https://modelcontextprotocol.io/quickstart/client 
from typing import Any, Callable
import asyncio, os, traceback
from contextlib import AsyncExitStack
import re, json
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
# from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamablehttp_client
from dotenv import load_dotenv

load_dotenv() # load environmental variables


def _pp_content(items) -> str:
    chunks: list[str] = []
    for c in items:
        t = getattr(c, "type", None)
        if t == "text":
            chunks.append(c.text)
        elif t == "json":
            try:
                chunks.append(json.dumps(c.data, indent=2))
            except Exception:
                chunks.append(str(c.data))
        elif t == "image":
            url = getattr(c, "uri", None) or getattr(c, "url", None)
            chunks.append(f"[image] {url or '(binary)'}")
        elif t == "resource":
            rid = getattr(c, "id", None)
            uri = getattr(c, "uri", None)
            chunks.append(f"[resource] {rid or uri}")
        else:
            chunks.append(repr(c))
    return "\n".join(chunks) if chunks else "(no content)"

async def _list_tools(session: ClientSession) -> str:
    tools_resp = await session.list_tools()
    lines = []
    for i, t in enumerate(tools_resp.tools):
        desc = getattr(t, "description", "") or ""
        lines.append(f"TOOL{i}: {t.name} : {desc}")
    return "Available Tools\n" + "\n".join(lines)

async def _tool_map(session: ClientSession) -> dict[str, Any]:
    tools_resp = await session.list_tools()
    return {t.name: t for t in tools_resp.tools}

async def _show_schema(session: ClientSession, tool_name: str) -> str:
    tools: dict[str, Any] = await _tool_map(session)
    t = tools.get(tool_name, None)
    if t is None:
        return f"Tool {tool_name} was not found"
    schema = getattr(t, "inputSchema", None) or getattr(t, "input_schema", None)
    return json.dumps(schema, indent=2) if schema else "(no input schema)"

async def _call_tool(session: ClientSession, tool_name: str, args: dict[str, Any]) -> str:
    result = await session.call_tool(tool_name, args)
    return _pp_content(result.content) 

async def _tools_manifest(session:ClientSession) -> list[dict[str, Any]]:
    resp = session.list_tools()
    tools = []
    for t in resp.tools:
        tools.append({
            "name": t.name,
            "description": getattr(t, "description", "") or "",
            "input_schema": getattr(t, "inputSchema", getattr(t, "input_schema", None))
        })
    return tools

class Client:

    def __init__(self) -> None:
        self.session: ClientSession | None = None
        self.exit_stack = AsyncExitStack()
        self.llm_call: Callable[[str,str,str], str] | None = None


    async def connect_to_local_server(self, server_path:str):

        command = "python"
        server_params = StdioServerParameters(
            command=command,
            args=[server_path],
            env=None
        )
        stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
        self.stdio, self.write = stdio_transport
        self.session = await self.exit_stack.enter_async_context(ClientSession(self.stdio, self.write))
        await self.session.initialize()
        

    async def connect_to_remote_server(self, url:str, headers:dict, type:str="python"):

        read, write, _ = await self.exit_stack.enter_async_context(streamablehttp_client(url=url, headers=headers))
        self.session = await self.exit_stack.enter_async_context(ClientSession(read, write))
        await self.session.initialize()

    def set_llm(self, llm_fn: Callable[[str, str, str], str]):
        self.llm_call = llm_fn


    async def process_query(self, query:str) -> str:
        if query == ":tools":
            return await _list_tools(self.session)
        

        m = re.match(r"^:schema\s+([A-Za-z0-9._:-]+)\s*$", query)
        if m:
            tool = m.group(1)
            return await _show_schema(self.session, tool)
        
        m = re.match(r"^:call\s+([A-Za-z0-9._:-]+)\s*(\{.*\})?\s*$", query, re.DOTALL)
        if m:
            tool = m.group(1)
            raw = m.group(2)
            if raw:
                try:
                    args = json.loads(raw)
                    if not isinstance(args, dict):
                        return "Args must be a JSON object, e.g. :call tool {\"key\":\"val\"}"
                except json.JSONDecodeError as e:
                    return f"Invalid JSON: {e}"
            else:
                args = {}

            tools = await _tool_map(self.session)
            if tool not in tools:
                # fuzzy suggestion
                names = list(tools.keys())
                hint = ", ".join(names[:10]) + (" …" if len(names) > 10 else "")
                return f"Tool '{tool}' was not found. Try: {hint}"
            try:
                return await _call_tool(self.session, tool, args)
            except Exception as e:
                # Surface server-side validation nicely
                return f"Tool error from '{tool}': {e}"
            
        list_short = await _list_tools(self.session)
        return (
            "Commands:\n"
            "  :tools\n"
            "  :schema <tool>\n"
            "  :call <tool> { JSON args }\n\n"
            + list_short
        )    
                

    async def chat(self) -> None:
        '''
        Provides chat interface to generate questions and responses
        '''
        while True:
            try:
                query = str(input("\nAsk something to chat: ").strip())
                # exit command
                if query.lower() == "exit":
                    break

                response = await self.process_query(query=query)
                print("\nAgent Response: " + response + "\n")

            except KeyboardInterrupt:
                print(f"Session ended by keyboard interruption")
                break

            except Exception as exc:
                print(f"\nError: {exc}")
                break
                


    async def cleanup(self) -> None:
        await self.exit_stack.aclose()


async def main(mode: str, server: str):
    client = Client()
    servers: set[str] = {"Github", "NASA", "Cloud", "Filesystem"}
    try: 
        if mode == "local":
            if server == "NASA":
                server_path = "my_mcp_server/server.py" # path to local server script
                await client.connect_to_local_server(server_path=server_path)
            elif server == "Filesystem":
                server_path = ""
            
        elif mode == "remote":

            if server == "Github":
                TOKEN = os.getenv("GITHUB_TOKEN")
                if not TOKEN:
                    raise ValueError("Github  not found in environment variables")
                await client.connect_to_remote_server(
                    url="https://api.githubcopilot.com/mcp/",
                    headers={"Authorization" : f"Bearer {TOKEN}"})
                await client.chat()
                
            elif server == "Cloud":
                TOKEN = os.getenv("ANTHROPIC_API_KEY")
                if not TOKEN:
                    raise ValueError("ANTHROPIC_API_KEY not found in environment variables")


            
    except * Exception as eg:
        for i, exc in enumerate(eg.exceptions, 1):
            print(f"Excp: {i}: {type(exc).__name__} : {exc}")
            traceback.print_exception(exc)  
    finally:
        await client.cleanup()

def run() -> None:
    print("### Client ###")
    remotes: str = "Github\nCloud\n"
    locals: str = "Filesystem\nNASA\n"
    mode: str = str(input("Enter mode (remote | local): "))
    
    select_server: str 
    while True:
        
        if mode == "remote":
            print(remotes)
        elif mode == "local":
            print(locals)
            
        select_server = str(input("Select server to connect to: "))
        if select_server in {"Github", "Cloud", "Filesystem", "NASA"}:
            break
        else:
            print("Not a valid server")
            pass
    asyncio.run(main(mode=mode, server=select_server))

if __name__ == '__main__':
    run()

