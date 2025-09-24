# 19/09/2025
# Reference: https://modelcontextprotocol.io/quickstart/client 
from typing import Any
import asyncio, os, traceback, platform
from contextlib import AsyncExitStack
import json
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from openai import OpenAI
from mcp.client.streamable_http import streamablehttp_client
from dotenv import load_dotenv

load_dotenv() # load environmental variables    

# set agent config
AGENT_SYSTEM = (
"You can use tools via a single function mcp_call_tool.\n"
    "When a tool is needed, call mcp_call_tool with:\n"
    '{"tool_name":"<exact name>","arguments":{...}}\n'
    "If a user request is actionable by a tool, you MUST call mcp_call_tool rather than answering in plain text.\n"
    "If there are schema parameters missing for a tool call, reply what are the parameters and which ones are missing\n"
    "You must use exact tool names from the manifest when calling mcp_call_tool."
)


def get_documents_root() -> str:
    """
    Return the path to the user's Documents directory in a cross-platform way.
    Works on Windows, macOS, and Linux.
    """
    home = os.path.expanduser("~")

    system = platform.system()
    if system == "Windows":
        docs = os.path.join(home, "Documents")
    elif system == "Darwin":
        docs = os.path.join(home, "Documents")
    else:
        docs = os.path.join(home, "Documents")
    if os.path.isdir(docs):
        return docs
    else:
        return home

def _print_tool_use(tool_name: str, args: dict):
    print("Tool name: ", tool_name)
    for key, value in args.items():
        print(f" - {key} : {value}\n")

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



def _compact_manifest_items(tools_resp, include_schema: bool = True, max_chars: int = 12000) -> str:
    """Build a compact JSON manifest for the prompt from list_tools() response."""
    items = []
    for t in tools_resp.tools:
        obj = {
            "name": t.name,
            "description": getattr(t, "description", "") or ""
        }
        if include_schema:
            obj["input_schema"] = getattr(t, "inputSchema", getattr(t, "input_schema", None))
        items.append(obj)
    blob = json.dumps(items, indent=2)
    return blob[:max_chars]



async def small_chat(
    session: ClientSession,
    openai_client: OpenAI,
    user_prompt: str,
    model: str = "gpt-4o-mini",
    max_steps: int = 4,
) -> str:
    tools_resp = await session.list_tools()
    tools_manifest = _compact_manifest_items(tools_resp)

    tools_spec = [{
        "type": "function",
        "function": {
            "name": "mcp_call_tool",
            "description": "Invoke an MCP tool by name with JSON arguments.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tool_name": {"type": "string"},
                    "arguments": {"type": "object"},
                },
                "required": ["tool_name", "arguments"],
                "additionalProperties": False
            }
        }
    }]

    messages = [
        {"role": "system", "content": AGENT_SYSTEM + "\nAvailable tools:\n" + tools_manifest},
        {"role": "user", "content": user_prompt},
    ]

    last_tool_text: str | None = None

    for step in range(max_steps):
        resp = openai_client.chat.completions.create(
            model=model,
            messages=messages,
            tools=tools_spec,
            tool_choice="auto",
            temperature=0,
            max_tokens=700,
        )
        msg = resp.choices[0].message

        # 1) If the model is done (no tool_calls) -> return content or fallbacks
        if not getattr(msg, "tool_calls", None):
            content = (msg.content or "").strip()
            if content:
                return content

            # Defensive fallback: if content is empty, try to nudge once
            if last_tool_text and step + 1 < max_steps:
                messages.append({
                    "role": "assistant",
                    "content": "(acknowledged tool results; synthesizing answer)"
                })
                messages.append({
                    "role": "user",
                    "content": "Using the tool results above, answer plainly. If there were no results, say so explicitly."
                })
                continue

            # Final fallback
            return last_tool_text or "(no content)"

        # 2) Append the assistant tool-call “shell” message
        messages.append({
            "role": "assistant",
            "tool_calls": msg.tool_calls,
            "content": msg.content or ""
        })

        # 3) Execute each tool call
        for call in msg.tool_calls:
            if call.function.name != "mcp_call_tool":
                messages.append({
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": "Please use mcp_call_tool to invoke MCP tools."
                })
                continue

            # Parse args safely
            try:
                args = json.loads(call.function.arguments or "{}")
                tool_name = args["tool_name"]
                arguments = args.get("arguments", {})
            except Exception as e:
                messages.append({
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": f"(error) Invalid JSON in tool call: {e}"
                })
                continue

            # Call the MCP tool
            try:
                mcp_result = await session.call_tool(tool_name, arguments)
                tool_text = _pp_content(mcp_result)
            except Exception as e:
                tool_text = f"(error) {e}"

            last_tool_text = tool_text
            messages.append({
                "role": "tool",
                "tool_call_id": call.id,
                "content": tool_text
            })

        # 🔁 loop again so the model can read the tool outputs and answer
        continue

    return last_tool_text or "Ran out of steps without an answer"

class Client:

    def __init__(self) -> None:
        self.session: ClientSession | None = None
        self.exit_stack = AsyncExitStack()
        self.open_ai = OpenAI(api_key=os.getenv("OPEN_AI_KEY"))

    #TODO verify it works
    async def connect_to_local_server(self, root_path:str=None, personal_server: bool= True):
        if root_path is None:
            root_path = get_documents_root()
        
        if personal_server:
            directory: str= os.getcwd()
            full_path: str = os.path.join(directory, ".venv\\Scripts\\my-mcp-server.exe")
            server_params = StdioServerParameters(
                command=full_path,
                args=[],
                env=None
            )
        else:
            server_params = StdioServerParameters(
                command="npx",
                args=["-y", "@modelcontextprotocol/server-filesystem", root_path],
            )
        
        read,write = await self.exit_stack.enter_async_context(stdio_client(server_params))
        self.session = await self.exit_stack.enter_async_context(ClientSession(read, write))
        await self.session.initialize()
        

    async def connect_to_remote_server(self, url:str, headers:dict|None=None):

        read, write, _ = await self.exit_stack.enter_async_context(streamablehttp_client(url=url, headers=headers or {}))
        self.session = await self.exit_stack.enter_async_context(ClientSession(read, write))
        await self.session.initialize()
            

    async def chat(self) -> None:
        '''
        Provides chat interface to generate questions and responses
        '''
        while True:
            try:
                query = str(input("\nAsk something to chat: ").strip())
                if query == "exit":
                    break
                answer = await small_chat(self.session, self.open_ai, query)
                print("\nAgent: " + answer)

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
    try: 
        if mode == "local":
            if server == "NASA":
                await client.connect_to_local_server()
                await client.chat()
            elif server == "Filesystem":
                await client.connect_to_local_server(personal_server=False)
                await client.chat()
            
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
                await client.connect_to_remote_server(
                    url="http://18.188.123.189:5000/mcp",
                    headers={}
                )
                await client.chat()


            
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

